"""A doctor's partial book folded into his full book without losing its alignment (owner, 2026-11-10).

The owner first hands over "Partial doctor book, first chapter only, will later be merged with the full one" and later the
full book. The partial's pages are the first pages of the full book, so what the fleet already aligned stays true:

1. pages are matched by their text (hash of the page's words), never by position alone; one consistent offset is
   required for at least 90% of the partial's text pages (else nothing is touched and the report says so);
2. every job of the full book whose pages are all aligned in the partial is marked passed with the partial's rows
   (book id rewritten, page numbers shifted by the offset): `jobs/books/<key>/aligned.jsonl`, queue note "carried from ...";
   the other jobs stay queued for the fleet;
3. the partial is retired: its PDFs (the owner's file and our copy) move to `modules/<m>/old/partial_books/`, nothing is
   deleted; `modules/<m>/site/book_replaces.json` records {full book: [partial keys]} for importSiteBook `--replaces`.

`merge_partials(q, books)` is called by `doctors_folder.import_all`; it is safe to run again.
"""
import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIN_TEXT = 50      # a page with fewer letters than this is a picture page: it has no text to match
MIN_SHARE = 0.9    # share of the partial's text pages that must match at the one offset


def page_hashes(pdf):
    """[hash or None per page]: None for a page with (almost) no text."""
    import fitz
    out = []
    with fitz.open(pdf) as doc:
        for p in doc:
            t = re.sub(r"\W+", "", p.get_text()).lower()
            out.append(hashlib.sha1(t.encode("utf-8")).hexdigest() if len(t) >= MIN_TEXT else None)
    return out


def page_offset(partial_pdf, full_pdf):
    """(offset, matched, text_pages, partial_pages): partial page i is full page i + offset. offset is None when no
    consistent offset covers MIN_SHARE of the partial's text pages."""
    a, b = page_hashes(partial_pdf), page_hashes(full_pdf)
    where = {}
    for j, h in enumerate(b):
        if h:
            where.setdefault(h, []).append(j)
    texts = [(i, h) for i, h in enumerate(a) if h]
    votes = Counter(j - i for i, h in texts for j in where.get(h, []))
    if not texts or not votes:
        return None, 0, len(texts), len(a)
    d, _ = votes.most_common(1)[0]
    matched = sum(1 for i, h in texts if i + d in where.get(h, []))
    ok = matched >= MIN_SHARE * len(texts) and len(a) + d <= len(b)
    return (d if ok else None), matched, len(texts), len(a)


def same_prefix(old_pdf, new_pdf):
    """True when the old (shorter) book is the first pages of the new one, page for page (offset 0)."""
    d, *_ = page_offset(old_pdf, new_pdf)
    return d == 0


def read_rows(f):
    return [json.loads(x) for x in Path(f).read_text(encoding="utf-8").splitlines() if x.strip()]


def aligned_rows(q, module, book):
    """{page: row} of every passed books job of `book`."""
    rows = {}
    for (key,) in q.db.execute("SELECT key FROM jobs WHERE flow='books' AND status='passed' AND key LIKE ?",
                               (f"{module}-{book}-p%",)):
        f = ROOT / "jobs" / "books" / key / "aligned.jsonl"
        if f.exists():
            for r in read_rows(f):
                rows[r["page"]] = r
    return rows


def carry(q, module, partial, full, offset):
    """Marks every full-book job whose pages the partial already aligned as passed. Returns (jobs carried, jobs left)."""
    import dm
    rows = aligned_rows(q, module, partial)
    pdf = ROOT / "modules" / module / "books" / f"{full}.pdf"
    carried = left = 0
    for job in dm.book_jobs(module, full, dm.book_pages(pdf, full)):
        status = q.db.execute("SELECT status FROM jobs WHERE id=?", (f"books:{job['key']}",)).fetchone()
        if status is None:
            q.add_jobs("books", [job])
        elif status["status"] == "passed":
            continue
        pages = [p["page"] for p in job["payload"]["pages"]]
        if not all(p - offset in rows for p in pages):
            left += 1
            continue
        out = []
        for p in pages:
            r = dict(rows[p - offset])
            r["book_id"], r["page"] = full, p
            out.append(r)
        d = ROOT / "jobs" / "books" / job["key"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "aligned.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
        (d / "carried.json").write_text(json.dumps({"from": partial, "offset": offset}), encoding="utf-8")
        if q.db.execute("SELECT status FROM jobs WHERE id=?", (f"books:{job['key']}",)).fetchone()["status"] == "queued":
            q.finish(f"books:{job['key']}", "passed", f"carried from {partial}")
        carried += 1
    return carried, left


def retire(module, partial_key, file):
    """Moves the partial's PDFs and book card out of the way (nothing is deleted)."""
    old = ROOT / "modules" / module / "old" / "partial_books"
    old.mkdir(parents=True, exist_ok=True)
    moved = []
    own = [ROOT / "modules" / module / "books" / f"{partial_key}{ext}" for ext in (".pdf", ".json")] if partial_key else []
    for src in [Path(file) if file else None, *own]:
        if src and src.exists():
            dst = old / src.name
            n = 1
            while dst.exists():
                dst = old / f"{src.stem} ({n}){src.suffix}"
                n += 1
            shutil.move(str(src), str(dst))
            moved.append(dst.name)
    return moved


def note_replaces(module, full, partial):
    f = ROOT / "modules" / module / "site" / "book_replaces.json"
    cur = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    cur.setdefault(full, [])
    if partial not in cur[full]:
        cur[full].append(partial)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(cur, indent=1), encoding="utf-8")


def merge_partials(q, books):
    """For each doctor+subject with a full book and partial books (from doctors_folder.plan): carry, then retire."""
    report = []
    groups = {}
    for b in books:
        groups.setdefault((b["module"], b["subject"], b["doctor_folder"]), []).append(b)
    for (module, subject, doc), items in groups.items():
        fulls = [b for b in items if b["kind"] == "full"]
        full_pdf = lambda b: ROOT / "modules" / module / "books" / f"{b['book']}.pdf"
        for part in (b for b in items if b["kind"] == "partial"):
            full = next((f for f in fulls if full_pdf(f).exists()), None)
            if not full:
                continue
            own = ROOT / "modules" / module / "books" / f"{part['book']}.pdf"
            src = own if own.exists() else Path(part["file"])
            offset, matched, texts, pages = page_offset(src, full_pdf(full))
            if offset is None:
                report.append(f"{part['book']}: NOT folded into {full['book']}: only {matched} of {texts} text pages match one "
                              f"offset; left as it is (owner decides)")
                continue
            carried, left = carry(q, module, part["book"], full["book"], offset)
            note_replaces(module, full["book"], part["book"])
            moved = retire(module, part["book"], part["file"])
            q.db.execute("UPDATE jobs SET status='held', note='folded into the full book' WHERE flow='books' "
                         "AND status='queued' AND key LIKE ?", (f"{module}-{part['book']}-p%",))
            report.append(f"{part['book']} folded into {full['book']} (pages {1 + offset}-{pages + offset}, offset {offset}): "
                          f"{carried} alignment jobs carried, {left} left for the fleet; old files moved to "
                          f"modules/{module}/old/partial_books/ ({len(moved)})")
        # an MCQ book cut to the first chapter next to the full one: same book id, same first pages
        full_mcq = [b for b in items if b["kind"] == "mcq"]
        for part in (b for b in items if b["kind"] == "mcq_partial"):
            full = next((f for f in full_mcq if f["file"] != part["file"]), None)
            if not full:
                continue
            if not same_prefix(part["file"], full["file"]):
                report.append(f"mcq {Path(part['file']).name}: its pages are not the first pages of {Path(full['file']).name}; left")
                continue
            moved = retire(module, None, part["file"])
            report.append(f"mcq {Path(part['file']).name}: first pages of the full MCQ book (same page numbers, extracted "
                          f"questions stay); file moved to modules/{module}/old/partial_books/")
    return report

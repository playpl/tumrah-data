"""A doctor's MCQ book (owner, 2026-11-08): its questions are copied out by the fleet, never aligned as a book.

    py dm.py doctors   (doctors_folder.import_all) queues every MCQ book it finds: jobs of 10 pages
    modules/<module>/mcq/<book>.jsonl   every copied question, once its jobs pass: {qid, book, doctor, subject, page, n,
                                        question, options, key, key_from}

Keys come only from the book: `key_from` says how the book shows it ("marked" on the option, or an "answer_list"); with
neither, the key stays null. Code never picks a key.
"""
import hashlib
import json
from pathlib import Path

from flows.common import read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parent
PAGES_PER_JOB = 10


def styled_text(page):
    """The page's text with the marks a key hides in, so workers never need a picture (owner, 2026-11-09):
    bold runs as [b]...[/b], coloured (non-black) runs as [c]...[/c]."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            parts = []
            for s in line["spans"]:
                t = s["text"]
                if not t.strip():
                    parts.append(t)
                    continue
                if s["flags"] & 16 or "bold" in s.get("font", "").lower():
                    t = f"[b]{t}[/b]"
                if s.get("color", 0) not in (0, 0x231F20, 0x000001):
                    t = f"[c]{t}[/c]"
                parts.append(t)
            out.append("".join(parts))
    return "\n".join(out)


def book_pages(pdf, first=None, last=None):
    import fitz
    with fitz.open(pdf) as doc:
        a, b = first or 1, min(last or doc.page_count, doc.page_count)
        return [{"page": n, "text": styled_text(doc[n - 1])} for n in range(a, b + 1)]


def queue_book(q, module, book, pdf, doctor, subject):
    keep = ROOT / "modules" / module / "mcq" / f"{book}.pdf"
    keep.parent.mkdir(parents=True, exist_ok=True)
    if not keep.exists():
        keep.write_bytes(Path(pdf).read_bytes())
    pages = book_pages(keep)
    jobs = [{"key": f"{module}-{book}-p{pages[i]['page']:04d}",
             "payload": {"module": module, "book": book, "doctor": doctor, "subject": subject,
                         "pdf": str(keep), "pages": pages[i:i + PAGES_PER_JOB]}}
            for i in range(0, len(pages), PAGES_PER_JOB)]
    added = q.add_jobs("mcq", jobs)
    return f"{len(pages)} pages, {len(jobs)} jobs, {added} new"


def qid(book, page, n):
    return f"mcq:{book}:p{page}:{n}"


def collect(module, book, queue, jobs_root=ROOT / "jobs"):
    """Every passed job's rows into modules/<module>/mcq/<book>.jsonl, in page order. Returns the row count."""
    rows = []
    for (key,) in queue.db.execute("SELECT key FROM jobs WHERE flow='mcq' AND status='passed' AND key LIKE ?",
                                   (f"{module}-{book}-p%",)):
        f = jobs_root / "mcq" / key / "mcqs.jsonl"
        if f.exists():
            rows += read_jsonl(f)
    payload_of = {}
    for (p,) in queue.db.execute("SELECT payload FROM jobs WHERE flow='mcq' AND key LIKE ?", (f"{module}-{book}-p%",)):
        payload_of = json.loads(p)
        break
    rows.sort(key=lambda r: (r["page"], r["n"]))
    out = [{"qid": qid(book, r["page"], r["n"]), "book": book, "doctor": payload_of.get("doctor"),
            "subject": payload_of.get("subject"), **r} for r in rows]
    write_jsonl(ROOT / "modules" / module / "mcq" / f"{book}.jsonl", out)
    return len(out)


def all_rows(module):
    d = ROOT / "modules" / module / "mcq"
    return [r for f in sorted(d.glob("*.jsonl")) for r in read_jsonl(f)] if d.exists() else []


def short(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

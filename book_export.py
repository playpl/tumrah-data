"""A fully aligned doctor book -> the site (owner, 2026-11-09: upload every alignment from all the books).

Joins every passed books job's `aligned.jsonl` for one book into importSiteBook's alignment layout
(<root>/out/aligned/<book>.jsonl: a triage row, then one row per page) and prints the import command. A book with a
job not yet passed is refused (a half-aligned book would hide its other pages). Never for Dr. Elazouny's books.

    py book_export.py <book>        e.g. zahran-hist-full
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULE = "year2-cns"
OUT = ROOT / "modules" / MODULE / "site" / "alignment"
SUBJECT = {"hist": "histology", "phys": "physiology", "anat": "anatomy"}


def export(book):
    if book.startswith("azouny"):
        sys.exit("Dr. Elazouny's books are never aligned (owner, 2026-11-09)")
    db = sqlite3.connect(ROOT / "queue.db")
    rows = db.execute("SELECT key, status FROM jobs WHERE flow='books' AND key LIKE ?", (f"{MODULE}-{book}-p%",)).fetchall()
    if not rows:
        sys.exit(f"no books jobs for {book}")
    waiting = [k for k, s in rows if s != "passed"]
    if waiting:
        sys.exit(f"{book}: {len(waiting)} of {len(rows)} jobs not passed yet")
    pages = {}
    for key, _ in rows:
        for line in open(ROOT / "jobs" / "books" / key / "aligned.jsonl", encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                pages[r["page"]] = r
    pdf = ROOT / "modules" / MODULE / "books" / f"{book}.pdf"
    import fitz
    with fitz.open(pdf) as doc:
        count = doc.page_count
    subject = next((v for k, v in SUBJECT.items() if f"-{k}" in book), None)
    triage = {"book_id": book, "kind": "lecture_notes", "page_count": count, **({"subject": subject} if subject else {}), "align": True}
    out = OUT / "out" / "aligned" / f"{book}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in [triage, *[pages[p] for p in sorted(pages)]]),
                   encoding="utf-8")
    meta = json.loads((ROOT / "modules" / MODULE / "books" / f"{book}.json").read_text(encoding="utf-8"))
    print(json.dumps({"book": book, "pages": count, "aligned_pages": len(pages), "doctor": meta.get("doctor"),
                      "title": meta.get("title"), "subject": subject, "file": str(out), "pdf": str(pdf)}))


if __name__ == "__main__":
    export(sys.argv[1])

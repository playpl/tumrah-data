"""Prints this job's doctor-book pages (from batch.jsonl), so a reader can split them into blocks.

    python tools/book.py          # every page of the job
    python tools/book.py 34       # one page
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handout import JOB, read_jsonl  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
want = int(sys.argv[1]) if len(sys.argv) > 1 else None
for p in read_jsonl(JOB / "batch.jsonl"):
    if want in (None, p["page"]):
        print(f"===== book {p['book_id']} page {p['page']} =====")
        print(p["text"] if len(p["text"].strip()) >= 20 else "[almost no text: an image page; mark it not_content]")

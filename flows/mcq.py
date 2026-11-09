"""MCQ flow: a worker copies out every question of 10 pages of a doctor's MCQ book (owner, 2026-11-08).

Payload: {"module", "book", "doctor", "subject", "pdf", "pages": [{"page", "text"}]}. When the checker passes,
`mcqs.jsonl` joins the book's question file (mcq.collect).
"""
import shutil
from pathlib import Path

import checks
import mcq
from flows import common

BRIEF = """# Brief: copy out a doctor's MCQ book

Tumrah is a study website for medical students. Dr. {doctor} ({subject}) gave his students an MCQ book. You copy its
questions, exactly as printed, so each can be linked to the handout. You never answer them.

## Inputs (read only)
- `python tools/mcqpage.py` prints every page's text; `python tools/mcqpage.py 7` prints one page.
- The text marks bold runs as `[b]...[/b]` and coloured runs as `[c]...[/c]`: that is how the book shows a right
  option. Leave the marks out of what you copy.
- There are no pictures in this job. Never open, render or analyse a picture or a PDF (no screenshots, no
  pdftoppm, no get_pixmap). A page whose text is too short or garbled to read: skip it and name it in your reply.

## Output: `mcqs.jsonl`, one JSON object per question, in page order
```json
{{"page": 7, "n": 1, "question": "<the stem as printed>", "options": ["<option a>", "<option b>", ...],
 "key": null, "key_from": null}}
```
- `n`: 1, 2, 3 ... on each page, in the order printed. A question that starts on one page and ends on the next
  belongs to the page where it starts.
- `question` and `options` are copied word for word as printed: no fixing, no translating, no summarising. Leave out
  the option letters ("a)", "B.") and the question number. A case text that goes with the stem is part of `question`.
- `key`: the 0-based index of the right option **only when the book itself shows it**: then `key_from` is "marked"
  (the option is coloured, bold, ticked or circled) or "answer_list" (a key list such as "1-c 2-a" on these pages).
  Otherwise both stay null. Never work out an answer yourself, never guess: a wrong key is far worse than none.
- Every question on every page. Skip only headings, page numbers and pages with no questions.

## Finish
Run `python tools/check.py`. Fix every error by reading the page again. Repeat until it prints PASS.
Final reply: the PASS line, how many questions, and how many have a key from the book.
"""

PAGE_TOOL = '''"""Prints this job's MCQ book pages.

    python tools/mcqpage.py        # every page
    python tools/mcqpage.py 7      # one page
"""
import json
import sys
import shutil
from pathlib import Path

JOB = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
want = int(sys.argv[1]) if len(sys.argv) > 1 else None
for line in open(JOB / "batch.jsonl", encoding="utf-8"):
    p = json.loads(line)
    if want in (None, p["page"]):
        print(f"===== page {p['page']} =====")
        print(p["text"] if len(p["text"].strip()) >= 20 else "[almost no text: skip this page, never look for a picture]")
'''


class MCQFlow:
    lane = "mcq"
    timeout = 90

    def prepare(self, job, job_dir: Path):
        p = job["payload"]
        # Text only, with bold/colour marks; no page pictures ever (owner, 2026-11-09: pictures make workers slow).
        import fitz
        with fitz.open(p["pdf"]) as doc:
            pages = [{**pg, "text": mcq.styled_text(doc[pg["page"] - 1])} for pg in p["pages"]]
        common.build(job_dir, None, pages, "check_mcq", "mcqs.jsonl",
                     BRIEF.format(doctor=p.get("doctor") or "the doctor", subject=p.get("subject") or ""))
        (job_dir / "tools" / "mcqpage.py").write_text(PAGE_TOOL, encoding="utf-8")
        shutil.rmtree(job_dir / "pages", ignore_errors=True)  # pictures left by older runs
        prompt = job_dir / "prompt.md"
        prompt.write_text(f"Read BRIEF.md in this folder to the end and follow it exactly. Your job has "
                          f"{len(p['pages'])} pages. {common.SUBAGENTS}\n", encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        rows = common.output_rows(job_dir)
        if rows is None:
            return ["mcqs.jsonl is missing"]
        # The pages the worker saw (styled text from prepare), not the payload's older plain text: an answer-list
        # page reads as "options without questions" in the plain text (2026-11-09).
        batch = job_dir / "batch.jsonl"
        pages = common.read_jsonl(batch) if batch.exists() and batch.stat().st_size else job["payload"]["pages"]
        return checks.check_mcq(rows, pages)

    def then(self, job, job_dir):
        """The book's question file is rebuilt from every passed job, so a finished book is whole."""
        import queue_db
        q = queue_db.Queue()
        try:
            mcq.collect(job["payload"]["module"], job["payload"]["book"], q)
        finally:
            q.close()
        return []

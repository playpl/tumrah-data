"""Book alignment flow: 5 doctor-book pages per job; a worker links every line to the handout lines it teaches.

Payload: {"module": code, "book_id": id, "pages": [{"book_id", "page", "text"}]}. After the checker passes,
`aligned.jsonl` holds importSiteBook page rows with each block's handout line IDs.
"""
import json
from pathlib import Path

import checks
from flows import common

BRIEF = """# Brief: align a doctor's book with the handout

Tumrah is a study website for medical students. The handout (the College Book) is the root: every other book is
shown beside it, line by line, so a student sees which handout lines each doctor's line teaches.

**Your job:** for each book page in `batch.jsonl`, split the page into blocks and link each block to the handout.

## Inputs (read only)
- `python tools/book.py` (or `python tools/book.py 34`) prints your book pages.
- `python tools/find.py "<phrase>"` lists the handout pages that hold a phrase (to find pages to read, never to choose).
- `python tools/page.py 57 59` prints handout pages line by line with their printed page numbers.
- `inputs/reference.json` (when present): `lectures` (`lecture_id`, `title`, optional `pdf_pages`).

## Rules
1. **Read; never let code choose.** No string or fuzzy matching, diff tools, word-overlap scores or "most similar
   sentence" scripts to choose a span or a match, even when two lines look identical: read both.
2. **Never change the books.** Copy book lines and handout lines verbatim; never correct, translate or summarise.
   Lines in Arabic or mixed Arabic and English are copied as book.py prints them.
3. **Never guess.** If you are not sure the handout says the same thing: `extra`.
4. Do not look at or analyse pictures. A page that is only a picture or diagram is `page_kind: "not_content"`, `blocks: []`.

## Output: `out.jsonl`, one JSON object per book page
```json
{"book_id": "b012", "page": 34, "page_kind": "content", "lecture_id": "<from reference.json or null>",
 "blocks": [
  {"n": 1, "text": "Thyroid gland", "figure": null, "match": "not_content", "handout": []},
  {"n": 2, "text": "It is formed of two lobes connected by an isthmus.", "figure": null, "match": "same",
   "handout": [{"pdf_page": 48, "printed_page": 40, "text": "It consists of two lobes connected by isthmus.", "figure": null}]},
  {"n": 3, "text": "Mnemonic: TIP for the relations", "figure": null, "match": "extra", "handout": []}],
 "note": null}
```
- **blocks**: every line of the page in reading order, `n` = 1, 2, 3... A block is one printed line, bullet, sentence
  or table row (at most 60 words; split longer ones). Blocks must cover at least 90% of the page's text (headers,
  page numbers and footers included, as `not_content`).
- **match**: `same` (same or nearly the same words), `reworded` (same fact, other words or language), `partial`
  (the handout teaches part of it; link that part), `extra` (not in the handout), `not_content` (titles, page
  numbers, headers, footers, names, decoration).
- **handout**: the smallest whole handout lines for `same`, `reworded`, `partial` (most important first; at most 80
  words each); `[]` for `extra` and `not_content`.
- **lecture_id**: the lecture most of the page's linked lines belong to; null when none.
- **note**: null, or under 25 words on anything unusual.

## Finish
Run `python tools/check.py`. Fix every error by re-reading, never by editing text just to pass. Repeat until PASS.
Final reply: the PASS line, and per page how many blocks are linked / extra.
"""


class BookFlow:
    lane = "books"
    timeout = 60

    def prepare(self, job, job_dir: Path):
        p = job["payload"]
        common.build(job_dir, p["module"], p["pages"], "check_alignment", "out.jsonl", BRIEF)
        prompt = job_dir / "prompt.md"
        prompt.write_text("Read BRIEF.md in this folder to the end and follow it exactly. "
                          f"Your job has {len(p['pages'])} book pages. {common.SUBAGENTS}\n", encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        rows = common.output_rows(job_dir)
        if rows is None:
            return ["out.jsonl is missing"]
        lines = common.read_jsonl(job_dir / "inputs" / "lines.jsonl")
        ref_path = job_dir / "inputs" / "reference.json"
        ref = json.loads(ref_path.read_text(encoding="utf-8")) if ref_path.exists() else {}
        errors = checks.check_alignment(rows, job["payload"]["pages"], lines, ref)
        if not errors:
            common.write_jsonl(job_dir / "aligned.jsonl", checks.alignment_import_rows(rows, lines))
        return errors

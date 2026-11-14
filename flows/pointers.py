"""Pointer flow: 25 questions per job; a worker points each at the exact handout lines.

Payload: {"module": code, "batch": [{"qid": site _id, "stem", "case_text", "options": [...], "correct_index",
"subject_hint"}]}. After the checker passes, `pointers.jsonl` holds importHubData pointer rows.
"""
import json
from pathlib import Path

import checks
from flows import common

BRIEF = """# Brief: point questions at the exact handout lines

Tumrah is a study website for medical students. After a student answers a question, the site shows
"Read this in your College Book" with the page and the exact lines. The handout is the College Book.

**Your job:** for each question in `batch.jsonl`, find the finest place in the handout that holds what a student
needs to understand the keyed option.

## Inputs (read only)
- `batch.jsonl`: one question per line: `qid`, `subject_hint`, `stem`, `case_text`, `options` (list), `correct_index` (0-based or null).
- `inputs/lines.jsonl`: the handout, line by line. Read it with the tools, not by opening the file.
- `inputs/reference.json` (when present): `lectures` (`lecture_id`, `title`, `subject`, optional `pdf_pages` [first, last]).
- `python tools/find.py "<phrase>"` lists the pages that hold a phrase (to find pages to read, never to choose).
- `python tools/page.py 57` or `python tools/page.py 57 59` prints pages, line by line, with the printed page number.
  A figure shows as `[FIGURE: <text next to it>]`.

## Rules
1. **Read; never let code choose.** You read the question and the lines you cite. No keyword scoring, fuzzy
   matching or "top sentence" scripts to pick lines.
2. **Never touch the key.** `correct_index` is context only. Never judge, check or mention it.
3. **Just right:** the exact sentence(s), bullet(s) or table row(s). Not a paragraph, not a page, and never a line
   that only shares a word with the question. If the information is split, give every piece.
4. **Never guess.** If the handout does not teach it after a real search: `found: false` with a reason.
   A wrong pointer is worse than an honest "not found".
5. **Copy verbatim** from the page as `page.py` prints it (spacing may differ; one span may run across lines).

## Method
1. Read stem, case text, every option and the keyed option. Decide what a student must know.
2. Find the pages with find.py, then read the whole passage with page.py. Questions in a batch often share a
   lecture: read its pages once, keep notes, then link every question.
3. Choose the smallest set of whole lines that teaches all of it. Check each line really teaches the fact.

## Output: `out.jsonl`, one JSON object per question, in batch order
```json
{"qid": "...", "found": true, "lecture_id": "<from reference.json, or null when it has no lectures>",
 "spans": [{"pdf_page": 48, "printed_page": 39, "text": "verbatim line", "figure": null, "for_option": null}],
 "partial": false, "tested_fact": "what the student must know, under 15 words",
 "reason": null, "other_module": null}
```
- `for_option`: the 0-based option a span explains (EXCEPT / "all of the following" / matching), else null.
- Figure-only information: `"text": "FIGURE"` and the figure's nearby text (as page.py shows it) in `figure`.
- `partial: true` when the handout teaches only part of what is needed.
- Not found: `"found": false, "lecture_id": null, "spans": [], "partial": false`, `reason` one of `not_in_book`,
  `other_module` (then set `other_module`, e.g. `Musculoskeletal`, `CNS & Special Senses`, `other`), `question_unclear`.
- `tested_fact` and `reason` never contain the words "answer", "correct", "incorrect" or "keyed".

## Finish
Run `python tools/check.py`. Fix every error it prints by re-reading the page, never by editing text just to pass.
Repeat until it prints PASS. Final reply: the PASS line, and how many questions are found / not found.
"""


LECTURE_SCOPE = """
## This batch belongs to one lecture
The owner named the lecture **{title}** (`lecture_id` `{lecture}`). It is taught on pdf pages {pages}. These questions
were picked by code as maybe belonging to it: some do not.
- Look for each question **only on those pages** (`python tools/page.py <first> <last>`). Use `"lecture_id": "{lecture}"`.
- When a question is not taught on those pages: `"found": false, "reason": "other_lecture"`. Do not search the rest
  of the handout for it. A wrong pointer is worse than "other_lecture".
"""


PAGES_SCOPE = """
## Where to look
These questions were posted under the title **{title}**, which names the handout pages {pages}.
- Look for each question **only on those pages** (`python tools/page.py <first> <last>`). Use the `lecture_id` of the
  reference.json lecture whose pages hold your lines.
- When a question is not taught on those pages: `"found": false, "reason": "other_lecture"`. Do not search the rest
  of the handout for it. A wrong pointer is worse than "other_lecture".
"""


class PointerFlow:
    lane = "pointers"
    timeout = 60

    def prepare(self, job, job_dir: Path):
        p = job["payload"]
        brief = BRIEF
        if p.get("lecture"):  # owner-named lecture: only its pages, "other_lecture" when the question is not taught there
            import lectures
            meta = lectures.load(p["lecture"])
            pages = lectures.page_ranges(meta)
            brief = BRIEF + LECTURE_SCOPE.format(title=meta["title"], lecture=meta["id"],
                                                 pages=", ".join(f"{a}-{b}" for a, b in pages))
        if p.get("scope"):  # owner 2026-11-14: the poll's title names the handout lectures to search (titles.py)
            sc = p["scope"]
            brief = BRIEF + PAGES_SCOPE.format(title=sc["title"], pages=", ".join(f"{a}-{b}" for a, b in sc["ranges"]))
        common.build(job_dir, p["module"], p["batch"], "check_pointers", "out.jsonl", brief)
        if p.get("scope"):
            (job_dir / "inputs" / "reference.json").write_text(json.dumps(
                {"lecture_scope": True, "lectures": p["scope"]["lectures"]}, ensure_ascii=False), encoding="utf-8")
        if p.get("lecture"):
            (job_dir / "inputs" / "reference.json").write_text(json.dumps(
                {"lecture_scope": True, "lectures": [{"lecture_id": meta["id"], "title": meta["title"], "pdf_pages": pages}]},
                ensure_ascii=False), encoding="utf-8")
        prompt = job_dir / "prompt.md"
        prompt.write_text("Read BRIEF.md in this folder to the end and follow it exactly. "
                          f"Your batch has {len(p['batch'])} questions. {common.SUBAGENTS}\n", encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        rows = common.output_rows(job_dir)
        if rows is None:
            return ["out.jsonl is missing"]
        lines = common.read_jsonl(job_dir / "inputs" / "lines.jsonl")
        ref_path = job_dir / "inputs" / "reference.json"
        ref = json.loads(ref_path.read_text(encoding="utf-8")) if ref_path.exists() else {}
        errors = checks.check_pointers(rows, job["payload"]["batch"], lines, ref)
        if not errors:
            common.write_jsonl(job_dir / "pointers.jsonl", checks.pointer_import_rows(rows, lines))
        return errors

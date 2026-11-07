"""Label flow (plan task 13): the fleet labels headers, then single questions, from closed lists.

Payload: {"stage": "headers" | "questions", "lists": {modules, lectures, doctors}, "batch": [...]}. When the checker
passes, the rows land in labels/<stage>/<job key>.jsonl, which labels.py reads.
"""
import json
from pathlib import Path

import checks
from flows import common

OUT = Path(__file__).resolve().parent.parent / "labels"

LISTS = """## Closed lists: `inputs/reference.json`
- `modules`: module code -> name. Use the code.
- `lectures`: module code -> its lectures (`lecture_id`, `title`, `subject`, `pdf_pages`). Only these modules have
  lectures; for any other module `lecture_id` is null.
- `doctors`: the doctors' names. Use a name exactly as listed.
"""

HEADERS = """# Brief: label Telegram headers by module, lecture, doctor and kind

Tumrah is a study website for medical students. Its question bank comes from Telegram channels where students post
questions under a header (the file or quiz name, e.g. a doctor's name and a lecture). You label each header once, so
every question under it is labelled.

## Input: `batch.jsonl`
One header per line: `hid`, `chat` (the channel), `header`, `count` (questions under it), `first` and `last` (dates
posted), `samples` (up to 3 of its questions).

{lists}
## Output: `out.jsonl`, one line per header, in batch order
`{{"hid": "...", "module": "<code>" | "mixed" | "none", "lecture_id": "<id>" | null, "doctor": "<name>" | null,
"kind": "doctor" | "past_exam" | "ai" | "student" | "other"}}`
- `module`: the module its questions teach. `mixed` when they span several modules (a final revision, "all
  topics"). `none` when they are not medical study questions.
- `lecture_id`: only when the header and its samples clearly belong to one lecture of that module; else null.
- `doctor`: the doctor the header names (written in any language or spelling) when that doctor is in the list; else
  null. Never guess a doctor from the subject.
- `kind`: `doctor` (a doctor's own questions), `past_exam` (an exam's questions with no doctor named), `ai` (made by
  AI), `student` (a student's or team's collection), `other`.
- Read the header and the samples. Never use keyword-matching code to choose a label.

## Finish
Run `python tools/check.py`; fix every error it prints; repeat until PASS. Final reply: the PASS line.
"""

QUESTIONS = """# Brief: label questions by module and lecture

Tumrah is a study website for medical students. These questions sat under a header that did not settle their module
or lecture (a mixed revision, or a header with no lecture). You label each question from its own words.

## Input: `batch.jsonl`
One question per line: `wid`, `header` (where it was posted), `question`, `options`.

{lists}
## Output: `out.jsonl`, one line per question, in batch order
`{{"wid": "...", "module": "<code>" | "none", "lecture_id": "<id>" | null}}`
- `module`: the module whose content the question tests; `none` when it is not a medical study question.
- `lecture_id`: the one lecture of that module that teaches what the question tests. Open the lecture's pages with
  `python tools/page.py <first> <last>` when unsure (only for modules whose handout is in `inputs/`). Null when no
  single lecture fits.
- Never judge or mention which option is right. Never use keyword-matching code to choose a label.

## Finish
Run `python tools/check.py`; fix every error it prints; repeat until PASS. Final reply: the PASS line.
"""


class LabelFlow:
    lane = "labels"
    timeout = 60

    def prepare(self, job, job_dir: Path):
        p = job["payload"]
        brief = (HEADERS if p["stage"] == "headers" else QUESTIONS).format(lists=LISTS)
        # question jobs read lecture pages: give them the handout of the one module with lectures, when there is one
        module = next(iter(p["lists"].get("lectures") or {}), None) if p["stage"] == "questions" else None
        common.build(job_dir, module, p["batch"], "check_labels", "out.jsonl", brief)
        (job_dir / "inputs" / "reference.json").write_text(json.dumps(p["lists"], ensure_ascii=False, indent=1),
                                                           encoding="utf-8")
        prompt = job_dir / "prompt.md"
        prompt.write_text(f"Read BRIEF.md in this folder to the end and follow it exactly. Your batch has "
                          f"{len(p['batch'])} items. {common.SUBAGENTS}\n", encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        p = job["payload"]
        rows = common.output_rows(job_dir)
        if rows is None:
            return ["out.jsonl is missing"]
        errors = checks.check_labels(rows, p["batch"], [], p["lists"])
        if not errors:
            (OUT / p["stage"]).mkdir(parents=True, exist_ok=True)
            common.write_jsonl(OUT / p["stage"] / f"{job['key']}.jsonl", rows)
        return errors

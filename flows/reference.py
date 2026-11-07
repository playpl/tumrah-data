"""Reference flow: one worker reads a module's handout and writes its closed lecture list (reference.json).

Payload: {"module": code}. When the checker passes, the list lands in modules/<code>/reference.json, where the
pointer, book and label flows read it.
"""
import json
import shutil
from pathlib import Path

import checks
from flows import common

BRIEF = """# Brief: list the lectures of a handout

Tumrah is a study website for medical students. The handout (the College Book) of module `{module}` is the centre of
all its data, and every question, book page and lecture recording is labelled with one of its lectures. You write
that list of lectures.

## Inputs (read only)
- `python tools/page.py 1 6` prints pages (here the first six: look for a contents page). The handout has {pages} pdf
  pages. `python tools/find.py "<phrase>"` lists the pages that hold a phrase.

## Output: `reference.json`
```json
{{"lectures": [
  {{"lecture_id": "{module}:L01", "title": "<the lecture's title as the handout prints it>", "subject": "<Anatomy,
   Physiology, Histology, Biochemistry, Pathology, Pharmacology, Microbiology, Embryology, ... as the handout names it>",
   "pdf_pages": [<first pdf page>, <last pdf page>]}}
]}}
```
- One entry per lecture, in handout order, numbered `{module}:L01`, `{module}:L02`, ...
- `pdf_pages`: from the page where the lecture starts to the last page before the next lecture starts. Two lectures
  may share the page where one ends and the next begins; they never overlap more than that.
- Every teaching page belongs to a lecture. Pages before the first lecture (cover, contents) stay out.
- Use the contents page to find the lectures, then open the pages to check where each one really starts.

## Finish
Run `python tools/check.py`. Fix every error it prints by reading the pages again. Repeat until it prints PASS.
Final reply: the PASS line and the number of lectures.
"""


class ReferenceFlow:
    lane = "reference"
    timeout = 60

    def prepare(self, job, job_dir: Path):
        module = job["payload"]["module"]
        lines = common.read_jsonl(common.module_dir(module) / "lines.jsonl")
        pages = max(ln["page"] for ln in lines)
        common.build(job_dir, module, [], "check_reference", "reference.json", BRIEF.format(module=module, pages=pages))
        prompt = job_dir / "prompt.md"
        prompt.write_text(f"Read BRIEF.md in this folder to the end and follow it exactly. {common.SUBAGENTS}\n",
                          encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        module = job["payload"]["module"]
        out = job_dir / "reference.json"
        if not out.exists():
            return ["reference.json is missing"]
        try:
            ref = json.loads(out.read_text(encoding="utf-8"))
        except ValueError as e:
            return [f"reference.json is not JSON ({e})"]
        errors = checks.check_reference(ref, module, common.read_jsonl(job_dir / "inputs" / "lines.jsonl"))
        if not errors:
            shutil.copy2(out, common.module_dir(module) / "reference.json")
        return errors

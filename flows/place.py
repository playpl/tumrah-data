"""Place flow: one worker finds where an owner-named lecture is taught in the handout.

Payload: {"lecture": id}. When the checker passes, the pages become the lecture's line-ID ranges in
lectures/<id>/lecture.json (placed_by "agent"); the owner sees them on the admin page and can change them.
"""
import json
from pathlib import Path

import checks
import lectures
from flows import common

BRIEF = """# Brief: find where a lecture is taught in the handout

Tumrah is a study website for medical students. The handout (the College Book) of module `{module}` is the centre of
all its data. The owner has named one lecture. You find the handout pages that lecture teaches, so questions, book
pages and the recording can be tied to it.

## The lecture
- Title: **{title}**
- Doctor: {doctor}
{others}
## Inputs (read only)
- `python tools/page.py 1 6` prints pages (here the first six: look for a contents page). The handout has {pages} pdf
  pages. `python tools/find.py "<phrase>"` lists the pages that hold a phrase.

## Output: `place.json`
```json
{{"ranges": [{{"first_page": <pdf page>, "last_page": <pdf page>}}], "note": "<how you found it, under 40 words>"}}
```
- Pdf page numbers (as page.py prints them after `pdf_page`), not the printed page numbers.
- `first_page`: the page where the lecture's topic starts. `last_page`: the last page before the next topic starts.
- Usually one range. Give two or more only when the handout teaches this lecture in separate places, in handout order.
- Use the contents page and find.py to find candidates, then open the pages and read them: the title words alone
  are not enough. Never guess: if the handout does not teach this lecture, write the closest pages and say so in `note`.

## Finish
Run `python tools/check.py`. Fix every error it prints by reading the pages again. Repeat until it prints PASS.
Final reply: the PASS line and the ranges.
"""


class PlaceFlow:
    lane = "place"
    timeout = 40

    def prepare(self, job, job_dir: Path):
        meta = lectures.load(job["payload"]["lecture"])
        module = meta["module"]
        lines = common.read_jsonl(common.module_dir(module) / "lines.jsonl")
        placed = [m for m in lectures.all_lectures(module) if m["id"] != meta["id"] and m.get("ranges")]
        others = ("\nOther lectures the owner already placed (they may share pages with this one):\n" +
                  "".join(f"- {m['title']}: pdf pages {', '.join(f'{a}-{b}' for a, b in lectures.page_ranges(m))}\n"
                          for m in placed)) if placed else ""
        common.build(job_dir, module, [], "check_place", "place.json",
                     BRIEF.format(module=module, title=meta["title"], doctor=meta.get("doctor") or "not given",
                                  others=others, pages=max(ln["page"] for ln in lines)))
        prompt = job_dir / "prompt.md"
        prompt.write_text("Read BRIEF.md in this folder to the end and follow it exactly.\n", encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        out = job_dir / "place.json"
        if not out.exists():
            return ["place.json is missing"]
        try:
            place = json.loads(out.read_text(encoding="utf-8"))
        except ValueError as e:
            return [f"place.json is not JSON ({e})"]
        lines = common.read_jsonl(job_dir / "inputs" / "lines.jsonl")
        errors = checks.check_place(place, lines)
        if not errors:
            meta = lectures.load(job["payload"]["lecture"])
            if meta.get("placed_by") != "owner":  # the owner's own pages are never overwritten
                lectures.set_ranges(meta, lines, [[r["first_page"], r["last_page"]] for r in place["ranges"]], "agent")
                meta["place_note"] = place["note"]
                lectures.save(meta)
        return errors

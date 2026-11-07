"""Lecture flows (owner, 2026-11-07).

transcribe      one worker hears the WHOLE lecture (audio.ogg) and writes raw.txt word for word with [mm:ss].
lecture_links   one worker, one context: the full raw transcript plus the lecture's handout lines. It lays the speech
                out (clean.txt, never a word changed), flags misheard words (fixes.jsonl; 0.9 or more replaces the
                word), and splits the lecture into parts with times and handout line IDs (parts.jsonl).
Payload for both: {"lecture": id}. The lecture's folder holds the files (lectures.py).
"""
import json
import shutil
from pathlib import Path

import checks
import lectures
from flows import common

TRANSCRIBE = """Open {audio} with read_file: you can hear audio files directly. Do not run any shell commands and do not
split the file. Write a verbatim transcript of the WHOLE recording to transcript.txt: every word as spoken (Arabic
speech in Arabic script, English terms in English), with a [mm:ss] timestamp at the start of each paragraph and a new
paragraph at least every minute. Never summarise, translate, correct or skip a part, and keep going to the very end.
Then run `python tools/check.py` and fix what it reports by listening again. Final reply: the PASS line and the last
timestamp you wrote."""

BRIEF = """# Brief: lay out a lecture transcript and link it to the handout

Tumrah is a study website for medical students. A recorded lecture becomes text linked to the handout (the College
Book), so a student can jump from any handout line to the minute the doctor explains it. You do the whole lecture in
this one job, so you keep its full context from start to end.

## Inputs (read only)
- `raw.txt`: the lecture word for word, with [mm:ss] at each paragraph. It is what was heard. Never edit it.
- The lecture: {title}. Its handout pages: {pages}. Print them with `python tools/page.py <first> <last>`;
  `python tools/find.py "<phrase>"` finds other pages. Every printed handout line has an ID you get from
  `python tools/lineids.py <pdf_page>` (one ID per line, in the order page.py prints them).

## Step 1. clean.txt: lay out only
Copy raw.txt into paragraphs, with punctuation, capitals and line breaks, keeping every [mm:ss] at the start of its
paragraph. **Never change, add, drop or reorder a word.** The only exception is step 2.

## Step 2. fixes.jsonl: misheard words
Read the lecture as someone who knows this subject. When a word cannot be what the doctor said (a misheard term,
a wrong drug or structure name), write one line: `{{"at": "mm:ss", "heard": "<word(s) in raw.txt>", "meant": "<the
word(s) the doctor said>", "confidence": 0.0-1.0, "reason": "<under 15 words>"}}`.
- confidence 0.9 or more: put `meant` in clean.txt in place of `heard`.
- under 0.9: keep `heard` in clean.txt; the owner decides later.
- Fixes are listed in the order they appear. An empty file means no fixes.

## Step 3. parts.jsonl: the lecture's parts
Split the lecture into parts (sub 0) and sub-parts (sub 1, 2, ...), each one line:
`{{"part": 1, "sub": 0, "title": "<short title>", "start": <seconds>, "end": <seconds>, "line_ids": ["<IDs>"]}}`
- Parts are numbered 1, 2, 3..., follow each other and never overlap; a sub-part sits inside its part's times.
- `line_ids`: the handout lines that part explains (read both: the doctor must really explain that line). A part with
  no handout line (greetings, exam news) has `[]`.
- Cover the whole recording, {duration:.0f} seconds.

## Finish
Run `python tools/check.py`. Fix every error by re-reading, never by editing words just to pass. Repeat until PASS.
Final reply: the PASS line, the number of parts, applied fixes and fixes left for the owner.
"""

LINEIDS = '''"""Prints the handout line IDs of one pdf page, in the order page.py prints its lines.

    python tools/lineids.py 57
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handout import lines  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
page = int(sys.argv[1])
for ln in lines():
    if ln["page"] == page:
        print(ln["id"], "|", (ln["text"] if ln.get("figure") is None else "[FIGURE: " + (ln["figure"] or "") + "]")[:70])
'''


class TranscribeFlow:
    lane = "transcribe"
    timeout = 120

    def prepare(self, job, job_dir: Path):
        meta = lectures.load(job["payload"]["lecture"])
        src = lectures.folder(meta["id"]) / "audio.ogg"
        common.build(job_dir, meta["module"], [], "check_transcript", "transcript.txt", "", extra={"duration_s": meta["duration_s"]})
        if not (job_dir / "audio.ogg").exists():
            shutil.copy2(src, job_dir / "audio.ogg")
        prompt = job_dir / "prompt.md"
        prompt.write_text(TRANSCRIBE.format(audio="audio.ogg"), encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        meta = lectures.load(job["payload"]["lecture"])
        out = job_dir / "transcript.txt"
        if not out.exists():
            return ["transcript.txt is missing"]
        errors = checks.check_transcript(out.read_text(encoding="utf-8"), meta["duration_s"])
        if not errors:
            raw = lectures.folder(meta["id"]) / "raw.txt"
            if not raw.exists():  # raw.txt is written once and never edited after
                shutil.copy2(out, raw)
        return errors

    def then(self, job, job_dir):
        return [("lecture_links", [{"key": job["payload"]["lecture"], "payload": job["payload"]}])]


class LectureLinkFlow:
    lane = "links"
    timeout = 120

    def prepare(self, job, job_dir: Path):
        meta = lectures.load(job["payload"]["lecture"])
        pages = meta.get("pdf_pages")
        brief = BRIEF.format(title=meta["title"], duration=meta["duration_s"],
                             pages=f"pdf {pages[0]} to {pages[1]}" if pages else "find them with find.py")
        common.build(job_dir, meta["module"], [], "check_lecture_dir", "parts.jsonl", brief,
                     extra={"duration_s": meta["duration_s"], "pdf_pages": pages})
        (job_dir / "tools" / "lineids.py").write_text(LINEIDS, encoding="utf-8")
        shutil.copy2(lectures.folder(meta["id"]) / "raw.txt", job_dir / "raw.txt")
        prompt = job_dir / "prompt.md"
        prompt.write_text("Read BRIEF.md in this folder to the end and follow it exactly. Keep the whole lecture in "
                          "your own context; you may hand page look-ups to subagents, never the lecture's text.\n",
                          encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        meta = lectures.load(job["payload"]["lecture"])
        lines = common.read_jsonl(job_dir / "inputs" / "lines.jsonl")
        errors = checks.check_lecture_dir(job_dir, lines, meta["duration_s"], meta.get("pdf_pages"))
        if errors:
            return errors
        d = lectures.folder(meta["id"])
        for name in ("clean.txt", "fixes.jsonl", "parts.jsonl"):
            shutil.copy2(job_dir / name, d / name)
        parts = common.read_jsonl(d / "parts.jsonl")
        common.write_jsonl(d / "links.jsonl", parts)
        meta["report"] = checks.link_report(parts, meta["duration_s"], lines, meta.get("pdf_pages"))
        fixes = common.read_jsonl(d / "fixes.jsonl")
        meta["fixes"] = {"applied": len(checks.applied(fixes)), "for_owner": len(fixes) - len(checks.applied(fixes))}
        lectures.save(meta)
        return []

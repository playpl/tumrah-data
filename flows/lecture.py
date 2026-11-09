"""Lecture flows (owner, 2026-11-07).

transcribe      no worker (owner 2026-11-09: faster, fewer tokens): cuts audio.ogg into 5-minute pieces and queues one
                `piece` job per piece.
piece           one worker hears ONE piece (piece.ogg) and writes piece.txt word for word with [mm:ss] from the piece's
                start; no brief, no tools, no subagents. When a lecture's last piece passes, code joins them with exact
                offsets into raw.txt and queues lecture_links.
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

# Owner 2026-11-09: one read of a whole 55-minute recording ran into the model's 5-minute stream timeout after 48 minutes
# of work, every time. Each worker now hears only {minutes}-minute pieces; tools/merge.py joins them with exact offsets.
TRANSCRIBE = """Never open, view or analyse any image or PDF; you only listen to audio and write text.

The recording is cut into {chunks} pieces of {minutes} minutes in chunks/ (c00.ogg, c01.ogg, ...). Never open the
whole recording (audio.ogg): it is too long for one read.

Start 4 subagents in parallel and give each a share of the pieces (for example c00-c02, c03-c05, ...). Tell each:
"Never open, view or analyse any image or PDF. For each of your pieces, open chunks/cNN.ogg with read_file (you can hear
audio files directly) and write chunks/cNN.txt: a verbatim transcript of that piece only, every word as spoken (Arabic
speech in Arabic script, English terms in English), with a [mm:ss] timestamp at the start of each paragraph, counted
from the START OF THAT PIECE (the first paragraph is [00:00]), and a new paragraph at least every minute. Never
summarise, translate, correct or skip a part. A piece with no speech at all: write an empty file."

When every piece has its .txt, run `python tools/merge.py` (it joins them into transcript.txt and timing.jsonl with the
right times), then `python tools/check.py`. Fix what it reports by listening to that piece again and rewriting its
.txt, then merge again. Final reply: the PASS line."""

MERGE = '''"""Joins chunks/cNN.txt (times from each piece's start) into transcript.txt (times from the recording's start) and
writes timing.jsonl (each piece's first words as its anchor). Prints counts only.

    python tools/merge.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks  # noqa: E402

JOB = Path(__file__).resolve().parent.parent
job = json.loads((JOB / "job.json").read_text(encoding="utf-8"))
n, size = job["chunks"], job["chunk_s"]
out, timing, para, missing = [], [], 0, []
for c in range(n):
    f = JOB / "chunks" / f"c{c:02d}.txt"
    if not f.exists():
        missing.append(c)
        continue
    paras = checks.paragraphs(f.read_text(encoding="utf-8"))
    if not paras:
        timing.append({"chunk": c, "silent": True})
        continue
    for i, (s, body) in enumerate(paras):
        t = int(c * size + min(s, size - 1))
        out.append(f"[{t // 60:02d}:{t % 60:02d}] {body}")
        if i == 0:
            words = checks.TOKEN.findall(body)
            timing.append({"chunk": c, "paragraph": para + 1, "first_words": " ".join(words[:8])})
        para += 1
if missing:
    sys.exit(f"pieces with no .txt yet: {missing}")
(JOB / "transcript.txt").write_text("\\n".join(out) + "\\n", encoding="utf-8")
(JOB / "timing.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\\n" for r in timing), encoding="utf-8")
print(f"{n} pieces, {para} paragraphs -> transcript.txt, timing.jsonl")
'''

PARAS = '''"""Prints each paragraph of transcript.txt with its number and its first words.

    python tools/paras.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
text = (Path(__file__).resolve().parent.parent / "transcript.txt").read_text(encoding="utf-8")
for n, (_, body) in enumerate(checks.paragraphs(text), 1):
    print(n, "|", body[:80])
'''

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


PIECE_PROMPT = """Never open, view or analyse any image or PDF. Do not start subagents. Do not read any other file.

Open piece.ogg with read_file (you can hear audio files directly): it is a {minutes}-minute piece of a medical lecture.
Write piece.txt: a verbatim transcript of it, every word as spoken (Arabic speech in Arabic script, English terms in
English), with a [mm:ss] timestamp at the start of each paragraph counted from the start of this piece (the first is
[00:00]) and a new paragraph at least every minute. Never summarise, translate, correct or skip a part. If the piece
has no speech at all, write an empty piece.txt. Final reply: done."""


def pieces_dir(lecture_id):
    return lectures.folder(lecture_id) / "pieces"


def merge_pieces(lecture_id, size=checks.CHUNK_SECONDS):
    """raw.txt from every pieces/cNN.txt, times shifted by each piece's start. (text, errors); errors when a piece is
    missing or the whole fails the transcript check."""
    d = pieces_dir(lecture_id)
    n = len(list(d.glob("c[0-9][0-9].ogg")))
    out, missing = [], []
    for c in range(n):
        f = d / f"c{c:02d}.txt"
        if not f.exists():
            missing.append(c)
            continue
        for s, body in checks.paragraphs(f.read_text(encoding="utf-8")):
            t = int(c * size + min(s, size - 1))
            out.append(f"[{t // 60:02d}:{t % 60:02d}] {body}")
    if missing:
        return None, [f"pieces not done yet: {missing}"]
    text = "\n".join(out) + "\n"
    meta = lectures.load(lecture_id)
    return text, checks.check_transcript(text, meta.get("duration_s") or n * size)


class TranscribeFlow:
    lane = "transcribe"
    timeout = 120

    def expand(self, job):
        """No worker: cut the lecture into pieces and queue one piece job each (dispatch.py runs this instead)."""
        lid = job["payload"]["lecture"]
        n = lectures.chunks(lectures.folder(lid) / "audio.ogg", pieces_dir(lid), checks.CHUNK_SECONDS)
        return [("piece", [{"key": f"{lid}-c{c:02d}", "payload": {"lecture": lid, "chunk": c}} for c in range(n)])]

    def prepare(self, job, job_dir: Path):
        meta = lectures.load(job["payload"]["lecture"])
        src = lectures.folder(meta["id"]) / "audio.ogg"
        if not (job_dir / "audio.ogg").exists():
            job_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, job_dir / "audio.ogg")
        n = lectures.chunks(job_dir / "audio.ogg", job_dir / "chunks", checks.CHUNK_SECONDS)
        common.build(job_dir, meta["module"], [], "check_transcript", "transcript.txt", "",
                     extra={"duration_s": meta["duration_s"], "chunks": n, "chunk_s": checks.CHUNK_SECONDS})
        (job_dir / "tools" / "paras.py").write_text(PARAS, encoding="utf-8")
        (job_dir / "tools" / "merge.py").write_text(MERGE, encoding="utf-8")
        prompt = job_dir / "prompt.md"
        prompt.write_text(TRANSCRIBE.format(audio="audio.ogg", chunks=n, minutes=checks.CHUNK_SECONDS // 60),
                          encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        meta = lectures.load(job["payload"]["lecture"])
        errors, timed = checks.check_job_transcript(job_dir)
        if not errors:
            raw = lectures.folder(meta["id"]) / "raw.txt"
            if not raw.exists():  # raw.txt (times from the audio) is written once and never edited after
                raw.write_text(timed, encoding="utf-8")
        return errors

    def then(self, job, job_dir):
        """Linking needs the lecture's handout pages: without them the place flow queues it when it passes."""
        if not lectures.load(job["payload"]["lecture"]).get("ranges"):
            return []
        return [("lecture_links", [{"key": job["payload"]["lecture"], "payload": job["payload"]}])]


class PieceFlow:
    lane = "piece"
    timeout = 20

    def prepare(self, job, job_dir: Path):
        p = job["payload"]
        job_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pieces_dir(p["lecture"]) / f"c{p['chunk']:02d}.ogg", job_dir / "piece.ogg")
        prompt = job_dir / "prompt.md"
        prompt.write_text(PIECE_PROMPT.format(minutes=checks.CHUNK_SECONDS // 60), encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        f = job_dir / "piece.txt"
        if not f.exists():
            return ["piece.txt is missing"]
        text = f.read_text(encoding="utf-8")
        if not text.strip():
            return []  # a silent piece
        seconds = lectures.duration(job_dir / "piece.ogg")
        errors = checks.check_transcript(text, seconds, end_slack=90)
        return [e for e in errors if "before the end" not in e or seconds > 120]

    def then(self, job, job_dir):
        """Keep the piece; the lecture's last piece joins them all into raw.txt and queues linking."""
        p = job["payload"]
        shutil.copy2(job_dir / "piece.txt", pieces_dir(p["lecture"]) / f"c{p['chunk']:02d}.txt")
        text, errors = merge_pieces(p["lecture"])
        if text is None or errors:
            return []
        raw = lectures.folder(p["lecture"]) / "raw.txt"
        if not raw.exists():
            raw.write_text(text, encoding="utf-8")
        meta = lectures.load(p["lecture"])
        if not meta.get("ranges"):
            return []  # the place flow queues linking once the lecture has pages
        return [("lecture_links", [{"key": p["lecture"], "payload": {"lecture": p["lecture"]}}])]


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

    def then(self, job, job_dir):
        """A linked lecture re-highlights every book lesson it explains (owner 2026-11-08). The MCQs come from the
        live site; when it cannot be reached the owner queues the lessons from the admin page."""
        import db
        import highlights
        import queue_db
        try:
            reader = db.Reader.live()
        except Exception:  # noqa: BLE001 - the lecture itself passed; highlighting waits for the button
            return []
        q = queue_db.Queue()
        try:
            for lesson in highlights.lessons_for_lecture(job["payload"]["lecture"]):
                highlights.queue(q, reader, lesson)
        finally:
            q.close()
        return []

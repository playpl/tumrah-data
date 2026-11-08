"""Importance highlights flows (owner 2026-11-08).

highlights  one worker, one book lesson: reads every doctor's lecture transcript on the lesson's pages and the pointed
            MCQs, and marks the key handout words (marks.jsonl). Code gives each mark its level (highlights.py).
hl_audit    a fresh worker re-reads every MCQ mark, every red mark and a sample of the rest against its evidence:
            keep or drop. Then the lesson's marks are final and the module export is rebuilt.
Payloads: highlights {"lesson", "questions", "lectures"} (highlights.job_payload); hl_audit {"module", "key"}.
"""
import json
import shutil
from pathlib import Path

import checks
import highlights
import lectures
from flows import common
from flows.lecture import LINEIDS

BRIEF = """# Brief: mark what the doctors say is important

Tumrah makes a study book from the college handout, word for word. Your marks colour the handout's own words so a
student sees at a glance what the doctors treat as important, and which words the doctor said will come as an MCQ.
You are the reviewer: read the doctors' lectures and their MCQs as a student would who wants to know exactly what
the exam asks, then mark the words.

The lesson: {name} ({subject}, chapter "{chapter}"), handout pdf pages {first} to {last}.

## Inputs (read only)
- `python tools/page.py {first} {last}` prints the lesson's handout pages line by line; `python tools/lineids.py <pdf_page>`
  gives each printed line's ID, in the same order.
- `lectures/<id>/clean.txt`: a lecture word for word with [mm:ss] times ({n_lectures} lectures). `lecture.json` names
  the doctor. `python tools/lecture.py <pdf_page>` prints, for every lecture, the parts that explain that page with
  their transcript. Read every lecture that teaches these pages from start to end: it is the main source.
- `batch.jsonl`: the important MCQs pointed at these pages ({n_questions}). Each has `qid`, `kind` (`doctor`: from a
  doctor's own collection; `other`: polls and quizzes that repeat), `doctors`, `stem`, `options`, `keyed` (the text
  of the keyed option), `repeats`, and `line_ids` (the handout lines it is pointed at).

## The constitution: what to mark
1. **Mark the key word, not the sentence.** A word mark is 1 to 3 words: the term, number, structure, site,
   function or exception a student must recall. Never an article, a linking word or a whole phrase.
2. **Only with evidence.** Every mark names its evidence. No evidence, no mark: your own sense of importance is not
   evidence. Evidence types:
   - `said_mcq`: the doctor says this will come as an MCQ, to write MCQ on it, that it comes in the exam or is an
     exam question (in Arabic or English). Give `lecture`, `at` (mm:ss) and `quote`: the doctor's words copied
     exactly from clean.txt, 1 to 30 words.
   - `said_important`: the doctor says it is important, to focus on it, to memorise it, or a similar instruction.
     Same fields as said_mcq.
   - `stressed`: the doctor comes back to it, repeats it, or spends a long time on it, with no instruction. Give
     `lecture` and `at` as a list of 2 or more mm:ss times where it is said.
   - `doctor_mcq`: a `doctor` MCQ in batch.jsonl tests exactly these words (its keyed option or its stem turns on
     them). Give `qid`.
   - `other_mcq`: the same for an `other` MCQ. Give `qid`.
   An MCQ counts only for the words it really tests, and only on the lines it is pointed at.
3. **Merge.** One row per mark, with all its evidence: from every doctor, every lecture and every MCQ.
4. **Sentences.** When the doctor stresses a whole statement (said_mcq, said_important or stressed), add one
   `sentence` mark (4 to 40 words) for the statement, and word marks for its 1 to 3 key words inside it.
   A sentence mark never stands for a list or a paragraph.
5. **MCQ words are the most precious.** Look hard for every place the doctor names an MCQ or the exam. The mark
   goes on the exact handout words the doctor was talking about at that moment, never on the nearest word that looks
   similar. If the doctor names an MCQ about something the handout does not say, make no mark.
6. **The handout's words only.** `text` is copied exactly from the printed lines (typos kept); it may run across
   two lines. Never mark a figure, a heading alone, or a word the lecture only mentions in passing.
7. **Code decides the colour**, from your evidence. Do not rank, score or colour anything yourself; give true,
   complete evidence and a short `why`.
8. A lesson with good lectures has many marks: every fact the doctors stress or ask. Do not mark everything: a page
   where every line is marked teaches nothing.

## Output: `marks.jsonl`, one JSON object per mark, in reading order
```json
{{"line_ids": ["<ID>"], "text": "exact handout words", "kind": "word",
 "evidence": [{{"type": "said_mcq", "lecture": "<id>", "at": "12:40", "quote": "exact words from clean.txt"}},
              {{"type": "doctor_mcq", "qid": "<qid>"}}],
 "why": "under 15 words: what the doctor or the MCQ asks about it"}}
```
`line_ids`: the line(s) the text sits on, in order, no extra lines.

## Finish
Run `python tools/check.py`. Fix every error by re-reading, never by editing words just to pass. Repeat until PASS.
You may give lectures or pages to subagents to read; you own marks.jsonl and merge their rows yourself.
Final reply: the PASS line and the number of marks, MCQ marks and sentences.
"""

LECTURE_TOOL = '''"""Prints, for every lecture in lectures/, the parts that explain one handout pdf page, with their transcript.

    python tools/lecture.py 57
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks  # noqa: E402
from handout import JOB, lines, read_jsonl  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
page = int(sys.argv[1])
on_page = {ln["id"] for ln in lines() if ln["page"] == page}
for d in sorted(p for p in (JOB / "lectures").glob("*") if p.is_dir()):
    meta = json.loads((d / "lecture.json").read_text(encoding="utf-8"))
    paras = checks.paragraphs((d / "clean.txt").read_text(encoding="utf-8"))
    for part in read_jsonl(d / "parts.jsonl"):
        if not on_page & set(part["line_ids"]):
            continue
        print(f"== lecture {d.name} ({meta.get('doctor') or 'doctor unknown'}) part {part['part']}.{part['sub']} "
              f"{part['title']} [{part['start'] // 60:02d}:{part['start'] % 60:02d}-{part['end'] // 60:02d}:{part['end'] % 60:02d}]")
        for t, text in paras:
            if part["start"] - 30 <= t < part["end"]:
                print(f"[{t // 60:02d}:{t % 60:02d}] {text}")
'''

AUDIT = """# Brief: keep or drop each highlight

Tumrah colours the handout words that the doctors treat as important. Another worker made these marks; you check
the most important ones with fresh eyes. Each item in `batch.jsonl` has `n`, the marked `text`, its `kind`, the
handout `line` it sits on, the worker's `why`, and its `evidence`: the doctor's `quote` with the transcript around
it (`transcript`), and the MCQs with their `stem`, `options` and `keyed` option.

**Keep** a mark only when its evidence really is about these exact words:
- `said_mcq`: the doctor really says this will be an MCQ or comes in the exam, and is talking about these words.
- `said_important`: the doctor really calls this important (or says to focus on or memorise it).
- `stressed`: the doctor really returns to these words at those times.
- `doctor_mcq` / `other_mcq`: the MCQ really turns on these words.
Drop it when the evidence is about something else, the quote does not say that, or the marked words are the wrong
ones (a neighbour of what the doctor meant). One wrong item of evidence among good ones: keep, and say which.

## Output: `audit.jsonl`, one row per item: `{"n": 1, "keep": true, "reason": "under 15 words"}`
Run `python tools/check.py` until it prints PASS. Final reply: the PASS line, kept and dropped counts.
"""


def jobs_root(job_dir):
    return Path(job_dir).parent.parent


class HighlightFlow:
    lane = "highlights"
    timeout = 120

    def prepare(self, job, job_dir: Path):
        p = job["payload"]
        L = p["lesson"]
        brief = BRIEF.format(name=L["name"], subject=L["subject"], chapter=L["chapter"], first=L["pages"][0],
                             last=L["pages"][1], n_lectures=len(p["lectures"]), n_questions=len(p["questions"]))
        common.build(job_dir, L["module"], p["questions"], "check_job_marks", "marks.jsonl", brief,
                     extra={"pages": L["pages"], "lesson": L["key"]})
        (job_dir / "tools" / "lineids.py").write_text(LINEIDS, encoding="utf-8")
        (job_dir / "tools" / "lecture.py").write_text(LECTURE_TOOL, encoding="utf-8")
        for lid in p["lectures"]:
            src, dst = lectures.folder(lid), job_dir / "lectures" / lid
            dst.mkdir(parents=True, exist_ok=True)
            for name in ("clean.txt", "parts.jsonl", "lecture.json"):
                shutil.copy2(src / name, dst / name)
        prompt = job_dir / "prompt.md"
        prompt.write_text(f"Read BRIEF.md in this folder to the end and follow it exactly. {common.SUBAGENTS}\n",
                          encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        errors = checks.check_job_marks(job_dir)
        if errors:
            return errors
        p = job["payload"]
        lines = common.read_jsonl(job_dir / "inputs" / "lines.jsonl")
        docs = {k: v["doctor"] for k, v in checks.job_lectures(job_dir, lines).items()}
        marks = highlights.scored(common.read_jsonl(job_dir / "marks.jsonl"), p["questions"], docs, lines)
        out = highlights.OUT / p["lesson"]["module"]
        out.mkdir(parents=True, exist_ok=True)
        common.write_jsonl(out / f"{p['lesson']['key']}.scored.jsonl", marks)
        return []

    def then(self, job, job_dir):
        L = job["payload"]["lesson"]
        marks = common.read_jsonl(highlights.OUT / L["module"] / f"{L['key']}.scored.jsonl")
        if not highlights.audit_items(marks):
            highlights.finish(L["module"], L["key"], marks)
            return []
        return [("hl_audit", [{"key": job["key"], "payload": {"module": L["module"], "key": L["key"], "job": job["key"]}}])]


def audit_batch(marks, hl_dir):
    """The items a fresh worker checks, with the transcript around each quote and each MCQ's text."""
    qs = {q["qid"]: q for q in common.read_jsonl(hl_dir / "batch.jsonl")}
    paras = {}
    out = []
    for n, m in enumerate(highlights.audit_items(marks), 1):
        ev = []
        for e in m["evidence"]:
            if "qid" in e:
                q = qs[e["qid"]]
                ev.append({"type": e["type"], "stem": q["stem"], "options": q["options"], "keyed": q["keyed"]})
                continue
            lid = e["lecture"]
            if lid not in paras:
                paras[lid] = checks.paragraphs((hl_dir / "lectures" / lid / "clean.txt").read_text(encoding="utf-8"))
            times = [checks.stamp_seconds(f"[{t}]") for t in (e["at"] if isinstance(e["at"], list) else [e["at"]])]
            near = [f"[{t // 60:02d}:{t % 60:02d}] {x}" for t, x in paras[lid] if any(abs(t - s) <= 75 for s in times)]
            ev.append({k: e[k] for k in ("type", "at", "quote") if k in e} | {"transcript": "\n".join(near)})
        out.append({"n": n, "text": m["text"], "kind": m["kind"], "line": m["line_text"], "why": m["why"],
                    "evidence": ev, "_key": [m["line_ids"], m["text"], m["kind"]]})
    return out


class AuditFlow:
    lane = "highlights"
    timeout = 60

    def prepare(self, job, job_dir: Path):
        p = job["payload"]
        marks = common.read_jsonl(highlights.OUT / p["module"] / f"{p['key']}.scored.jsonl")
        batch = [{k: v for k, v in b.items() if k != "_key"}
                 for b in audit_batch(marks, jobs_root(job_dir) / "highlights" / p["job"])]
        common.build(job_dir, None, batch, "check_audit", "audit.jsonl", AUDIT)
        prompt = job_dir / "prompt.md"
        prompt.write_text(f"Read BRIEF.md in this folder to the end and follow it exactly. "
                          f"There are {len(batch)} items.\n", encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        rows = common.output_rows(job_dir)
        if rows is None:
            return ["audit.jsonl is missing"]
        batch = common.read_jsonl(job_dir / "batch.jsonl")
        errors = checks.check_audit(rows, batch)
        if errors:
            return errors
        p = job["payload"]
        marks = common.read_jsonl(highlights.OUT / p["module"] / f"{p['key']}.scored.jsonl")
        items = audit_batch(marks, jobs_root(job_dir) / "highlights" / p["job"])
        drop = {json.dumps(it["_key"]) for it in items for r in rows if r["n"] == it["n"] and not r["keep"]}
        kept = [m for m in marks if json.dumps([m["line_ids"], m["text"], m["kind"]]) not in drop]
        common.write_jsonl(job_dir / "dropped.jsonl", [m for m in marks if m not in kept])
        highlights.finish(p["module"], p["key"], kept)
        return []

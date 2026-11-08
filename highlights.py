"""Importance highlights (owner 2026-11-08). Spec: tumrah repo docs/superpowers/specs/2026-11-08-importance-highlights-design.md.

A fleet worker reads one book lesson's lecture transcripts and pointed MCQs and marks the key handout words
(flows/highlights.py). This file holds what code decides: the lesson list (from tumrah-book), the job inputs, each
mark's level (never the worker), the per-page cap and the module export the Tumrah book applies.

    highlights/<module>/<key>.scored.jsonl   checked marks with their level, waiting for the audit
    highlights/<module>/<key>.jsonl          the lesson's final marks
    exports/<module>/highlights.jsonl        all lessons merged across doctors: what tumrah-book reads
Levels: 1 red (must know), 2 blue (important), 3 green (good to know); the book swaps the subject's own colour for yellow.
"""
import json
import re
import time
from pathlib import Path

import checks
import lectures
from flows.common import read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "highlights"
EXPORTS = ROOT / "exports"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
QUESTION_FIELDS = {"question_text": 1, "options": 1, "correct_option": 1, "test_type": 1, "doctor": 1,
                   "repetition_count": 1, "importance_score": 1, "is_high_yield": 1, "appearance_sources": 1,
                   "book_refs.line_ids": 1}


def cfg():
    return CONFIG["highlights"]


def lessons(module):
    """The book's lessons with their handout pdf pages, from tumrah-book's chapter.json files."""
    out = []
    for f in sorted((Path(CONFIG["book_root"]) / "modules" / module).glob("*/*/_work/chapter.json")):
        chapter = f.parent.parent
        num, title = chapter.name.split(" - ", 1)
        subject = chapter.parent.name
        for L in json.loads(f.read_text(encoding="utf-8"))["lessons"]:
            out.append({"key": f"{module}__{re.sub(r'\W+', '', subject)}-{int(num)}-{L['dir']}", "module": module,
                        "subject": subject, "chapter": title, "name": L["name"], "pages": [L["first"], L["last"]]})
    return out


def module_lines(module):
    return read_jsonl(ROOT / "modules" / module / "lines.jsonl")


def lesson_lectures(module, pages, lines):
    """Lectures of the module with a clean transcript and a part on the lesson's pages."""
    page_of = {ln["id"]: ln["page"] for ln in lines}
    out = []
    for f in sorted(lectures.LECTURES.glob("*/parts.jsonl")):
        meta = json.loads((f.parent / "lecture.json").read_text(encoding="utf-8"))
        if meta.get("module") != module or not (f.parent / "clean.txt").exists():
            continue
        hit = {page_of.get(i) for p in read_jsonl(f) for i in p["line_ids"]} - {None}
        if any(pages[0] <= pg <= pages[1] for pg in hit):
            out.append(meta["id"])
    return out


def question_row(q):
    """A site question as the worker sees it, or None when it is not important enough (owner: only the important
    pointed MCQs). A doctor-collection MCQ always counts; another one when it repeats, carries importance or came
    from a past exam. importfile.py writes source_type as the comma-joined label kinds ("doctor,student")."""
    c = cfg()
    srcs = q.get("appearance_sources") or []
    kinds = {k.strip() for s in srcs for k in (s.get("source_type") or "").split(",")}
    doctor_set = q.get("test_type") == "doctor" or bool(kinds & {"doctor", "doctor_collection"})
    repeats = q.get("repetition_count") or 1
    if not (doctor_set or repeats >= c["min_repeats"] or (q.get("importance_score") or 1) >= c["min_importance"]
            or q.get("is_high_yield") or "past_exam" in kinds):
        return None
    opts = q.get("options") or {}
    pairs = opts.items() if isinstance(opts, dict) else zip("ABCDE", opts)
    options = {k: (v.get("text") if isinstance(v, dict) else v) for k, v in pairs if v}
    return {"qid": str(q["_id"]), "kind": "doctor" if doctor_set else "other",
            "doctors": sorted({d for d in [q.get("doctor"), *(s.get("doctor") for s in srcs)] if d}),
            "stem": q.get("question_text"), "options": options, "keyed": options.get(q.get("correct_option")),
            "repeats": repeats, "line_ids": sorted({i for r in q.get("book_refs") or [] for i in r.get("line_ids") or []})}


def lesson_questions(reader, line_ids):
    flt = {"type": "med_question", "book_refs.line_ids": {"$in": line_ids}}
    rows, skip = [], 0
    while True:
        page = reader.find("questions", flt, QUESTION_FIELDS, limit=500, sort=[("_id", 1)], skip=skip)
        rows += page
        skip += len(page)
        if len(page) < 500:
            break
    return [r for r in map(question_row, rows) if r]


def lessons_for_lecture(lecture_id):
    """The book lessons whose pages a lecture's parts explain."""
    meta = lectures.load(lecture_id)
    page_of = {ln["id"]: ln["page"] for ln in module_lines(meta["module"])}
    hit = {page_of.get(i) for p in read_jsonl(lectures.folder(lecture_id) / "parts.jsonl") for i in p["line_ids"]}
    return [L for L in lessons(meta["module"]) if any(L["pages"][0] <= pg <= L["pages"][1] for pg in hit - {None})]


def queue(q, reader, lesson):
    """Queues a highlights job for the lesson unless one is already waiting; a re-run gets a new key (the queue
    never repeats a key). Returns the key, or None."""
    if q.db.execute("SELECT 1 FROM jobs WHERE flow='highlights' AND status='queued' AND key LIKE ?",
                    (lesson["key"] + ".%",)).fetchone():
        return None
    key = f"{lesson['key']}.{time.strftime('%Y%m%d-%H%M%S')}"
    q.add_jobs("highlights", [{"key": key, "payload": job_payload(reader, lesson)}])
    return key


def state(q, lesson_key):
    """The newest highlights or audit job of a lesson: {flow, status, note} or None."""
    r = q.db.execute("SELECT flow, status, note FROM jobs WHERE flow IN ('highlights', 'hl_audit') AND key LIKE ? "
                     "ORDER BY added DESC, flow DESC LIMIT 1", (lesson_key + ".%",)).fetchone()
    return dict(r) if r else None


def job_payload(reader, lesson):
    """Everything a highlights job needs, read once when it is queued."""
    lines = module_lines(lesson["module"])
    first, last = lesson["pages"]
    ids = [ln["id"] for ln in lines if first <= ln["page"] <= last]
    return {"lesson": lesson, "questions": lesson_questions(reader, ids) if reader else [],
            "lectures": lesson_lectures(lesson["module"], lesson["pages"], lines)}


# ---- level, cap, export -------------------------------------------------------------------------------------------
def enrich(mark, questions, lecture_doctors, lines):
    """The checked mark with what its level needs written into it, so a merge across lessons needs no inputs."""
    qs = {q["qid"]: q for q in questions}
    by_id = {ln["id"]: ln for ln in lines}
    ev = []
    for e in mark["evidence"]:
        e = dict(e)
        if "qid" in e:
            e.update(doctors=qs[e["qid"]]["doctors"], repeats=qs[e["qid"]]["repeats"])
        else:
            e["doctors"] = [d for d in [lecture_doctors.get(e["lecture"])] if d]
        ev.append(e)
    first = by_id[mark["line_ids"][0]]
    return {**mark, "text": checks.squash(mark["text"]), "evidence": ev, "page": first["page"],
            "line_text": checks.squash(" ".join(by_id[i]["text"] for i in mark["line_ids"]))}


def level(mark):
    """Code decides the colour: said MCQ is always level 1; otherwise points from distinct evidence."""
    c, w = cfg(), cfg()["weights"]
    pts, doctors, mcq, seen = 0, set(), False, set()
    for e in mark["evidence"]:
        src = (e["type"], e.get("qid") or e.get("lecture"))
        if src in seen:
            continue
        seen.add(src)
        mcq = mcq or e["type"] == "said_mcq"
        pts += w[e["type"]] + (w["repeat_bonus"] if e.get("repeats", 1) >= 2 else 0)
        doctors |= set(e.get("doctors") or [])
    pts += w["extra_doctor"] * max(0, len(doctors) - 1)
    lv = 1 if mcq or pts >= c["red_at"] else 2 if pts >= c["blue_at"] else 3
    return {**mark, "level": lv, "mcq": mcq, "score": pts, "doctors": sorted(doctors)}


def cap(marks):
    """Calm pages: per pdf page keep the strongest word marks and sentences; an MCQ mark is never dropped."""
    c, groups = cfg(), {}
    for i, m in enumerate(marks):
        groups.setdefault((m["page"], m["kind"]), []).append((i, m))
    keep = []
    for (_, kind), ms in groups.items():
        ms.sort(key=lambda im: (not im[1]["mcq"], im[1]["level"], -im[1]["score"], im[0]))
        limit = c["max_words_per_page"] if kind == "word" else c["max_sentences_per_page"]
        keep += [im for n, im in enumerate(ms) if im[1]["mcq"] or n < limit]
    return [m for _, m in sorted(keep, key=lambda im: im[0])]


def scored(marks, questions, lecture_doctors, lines):
    return cap([level(enrich(m, questions, lecture_doctors, lines)) for m in marks])


def audit_items(marks):
    """Every MCQ mark and red mark, plus every n-th of the rest, for a fresh worker to keep or drop."""
    every = cfg()["audit_every"]
    rest = [m for m in marks if not (m["mcq"] or m["level"] == 1)]
    pick = [m for m in marks if m["mcq"] or m["level"] == 1] + rest[::every]
    return [m for m in marks if any(m is p for p in pick)]


def mark_key(m):
    return (tuple(m["line_ids"]), m["text"], m["kind"])


def finish(module, key, marks):
    """Writes the lesson's final marks and rebuilds the module export."""
    d = OUT / module
    d.mkdir(parents=True, exist_ok=True)
    write_jsonl(d / f"{key}.jsonl", marks)
    return export(module)


def export(module):
    """All lessons merged across doctors: one row per mark, evidence united, level recomputed, page cap again."""
    merged = {}
    for f in sorted((OUT / module).glob("*.jsonl")):
        if f.name.endswith(".scored.jsonl"):
            continue
        for m in read_jsonl(f):
            k = mark_key(m)
            if k in merged:
                have = {json.dumps(e, sort_keys=True) for e in merged[k]["evidence"]}
                merged[k]["evidence"] += [e for e in m["evidence"] if json.dumps(e, sort_keys=True) not in have]
            else:
                merged[k] = m
    rows = cap([level(m) for m in merged.values()])
    out = EXPORTS / module / "highlights.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out, [{"module": module, "page": m["page"], "line_ids": m["line_ids"], "line_text": m["line_text"],
                       "text": m["text"], "kind": m["kind"], "level": m["level"], "mcq": m["mcq"],
                       "doctors": m["doctors"], "score": m["score"]} for m in rows])
    return {"marks": len(rows), "file": str(out)}


def summary(module, key):
    """Counts for the admin page: final marks by level, MCQ marks and sentences."""
    f = OUT / module / f"{key}.jsonl"
    if not f.exists():
        return None
    ms = read_jsonl(f)
    return {"marks": len(ms), "red": sum(m["level"] == 1 for m in ms), "blue": sum(m["level"] == 2 for m in ms),
            "green": sum(m["level"] == 3 for m in ms), "mcq": sum(m["mcq"] for m in ms),
            "sentences": sum(m["kind"] == "sentence" for m in ms)}


def preview(module, key):
    """The lesson's handout lines with their marks, for the admin page."""
    f = OUT / module / f"{key}.jsonl"
    marks = read_jsonl(f) if f.exists() else []
    lesson = next((L for L in lessons(module) if L["key"] == key), None)
    if not lesson:
        return {"lines": [], "marks": []}
    first, last = lesson["pages"]
    lines = [{"id": ln["id"], "page": ln["page"], "text": ln["text"]} for ln in module_lines(module)
             if first <= ln["page"] <= last and ln.get("figure") is None]
    return {"lines": lines, "marks": [{k: m[k] for k in ("line_ids", "text", "kind", "level", "mcq", "doctors", "why")}
                                      for m in marks]}

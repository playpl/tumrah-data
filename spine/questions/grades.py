"""The owner's question grades on every site question (CLAUDE.md "Owner answers (2026-11-20)"), by code:

    1  the lesson doctor's own quizzes (a Google Form, his own test file, a Telegram quiz he posted)
    2  his own MCQ file; 1 when that lecture has no quiz from him
    3  another doctor's MCQ file or quiz
    4  polls
    5  archive (not a lesson question: the site's "AI questions" reservoir, owner 2026-11-21)

Who wrote a question = its `doctorId` (the source's doctor); whose lesson it is = the lesson's `doctorId`.
Every quiz or file question is matched to its poll (the same `word_key`) so its votes can be shown.

    py -m spine questions grades year2-cns     -> modules/<m>/site/grades.jsonl, prints the counts
"""
import json
import sys
from collections import Counter

from spine import ROOT, module_dir, read_jsonl, write_jsonl

sys.path.insert(0, str(ROOT / "polls"))
from engine import option_word, word_key  # noqa: E402

from spine import text as T  # noqa: E402

QUIZ, FILE, POLL = ("own", "form"), ("mcq",), ("bank",)
FILES = {"year2-cns": "questions.json", "year1-musculoskeletal": "msk_questions.json"}


def source(q):
    """quiz | file | poll | archive of one question."""
    pre = q["source_id"].split(":")[0]
    if pre in QUIZ or pre in POLL and any(a.get("source_type") == "doctor_quiz" for a in q.get("appearances") or []):
        return "quiz"
    if pre in FILE:
        return "file"
    if pre in POLL:
        return "poll"
    return "archive"


def _options(q):
    return "|".join(sorted(option_word(o) for o in q["options"]))


def ready_polls(path=ROOT / "polls" / "ready" / "questions.jsonl"):
    """Every poll the polls job holds, as questions: {"source_id": "poll:<chat>:<msg>", "stem", "options"}."""
    out = []
    for r in read_jsonl(path) if path.exists() else []:
        s = (r.get("sightings") or [{}])[0]
        out.append({"source_id": f"poll:{s.get('chat')}:{s.get('msg_id')}", "stem": r["question"], "options": r["options"]})
    return out


def grade(questions, lesson_doctor, more_polls=()):
    """[{"source_id", "lesson", "grade", "why", "poll"}]: one row per question. `more_polls`: polls not on the site
    that a quiz or file question may still match (its votes)."""
    kind = {q["source_id"]: source(q) for q in questions}
    own = lambda q: q.get("doctorId") and q.get("doctorId") == lesson_doctor.get(q.get("lesson"))  # noqa: E731
    quizzed = {q.get("lesson") for q in questions if kind[q["source_id"]] == "quiz" and own(q)}
    polls, by_options = {}, {}
    for q in [q for q in questions if kind[q["source_id"]] == "poll"] + list(more_polls):
        polls.setdefault(word_key(q["stem"], q["options"]), q["source_id"])
        by_options.setdefault(_options(q), []).append((set(T.content(q["stem"])), q["source_id"]))

    def poll_of(q):
        """The same question among the polls: the same key, else the same options and a stem with >= 0.8 of its
        content words shared (a file's "Q3." or a typo in the poll's copy)."""
        hit = polls.get(word_key(q["stem"], q["options"]))
        if hit:
            return hit
        a = set(T.content(q["stem"]))
        best = max(((len(a & b) / len(a | b), sid) for b, sid in by_options.get(_options(q), []) if a | b), default=None)
        return best[1] if best and best[0] >= 0.8 else None
    out = []
    for q in questions:
        k = kind[q["source_id"]]
        if k == "quiz":
            g, why = (1, "his own quiz") if own(q) else (3, "another doctor's quiz")
        elif k == "file":
            if own(q):
                g, why = (2, "his own MCQ file") if q.get("lesson") in quizzed else (1, "his own MCQ file, no quiz from him")
            else:
                g, why = 3, "another doctor's MCQ file"
        elif k == "poll":
            g, why = 4, "poll"
        else:
            g, why = 5, "archive"
        row = {"source_id": q["source_id"], "lesson": q.get("lesson"), "grade": g, "why": why}
        if k in ("quiz", "file"):
            row["poll"] = poll_of(q)
        out.append(row)
    return out


def run(module):
    site = module_dir(module) / "site"
    data = json.loads((site / FILES[module]).read_text(encoding="utf-8"))
    lesson_doctor = {r["key"]: r.get("doctorId") for r in read_jsonl(site / "lessons.jsonl")}
    rows = grade(data["questions"], lesson_doctor, ready_polls())
    write_jsonl(site / "grades.jsonl", rows)
    n = Counter(r["grade"] for r in rows)
    matched = sum(1 for r in rows if r.get("poll"))
    asked = sum(1 for r in rows if "poll" in r)
    no_lesson = sum(1 for r in rows if not r["lesson"])
    return [f"{module}: {len(rows)} questions, grades " + ", ".join(f"{g}: {n[g]}" for g in sorted(n)),
            f"  quiz/file questions matched to a poll (votes): {matched} of {asked}",
            f"  without a lesson: {no_lesson}",
            f"  -> {(site / 'grades.jsonl').relative_to(ROOT)}"]


def register(sub):
    p = sub.add_parser("questions", help="Phase 3: question grades").add_subparsers(dest="questions_cmd")
    g = p.add_parser("grades", help="the owner's grades 1-5 on every site question, quiz/file questions matched to polls")
    g.add_argument("modules", nargs="*", default=list(FILES))
    g.set_defaults(run=lambda a: print("\n".join(line for m in a.modules for line in run(m))))

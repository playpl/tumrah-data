"""Required = the doctor's own quizzes; a lesson with no quiz gets the questions of the doctor's MCQ book that teach it
(owner, 2026-11-12: "quizzes are the requireds on site; if no quiz get the questions related to the lesson from the doctor
MCQ file").

    py required_rule.py            counts only, changes nothing
    py required_rule.py --apply    writes lectures/<id>/lecture.json

1. Every question in a lecture's `doctor_questions` (the doctor's own Google Form quizzes the owner put in the folder) moves
   to `required`. Nothing is lost: a question already required is not added twice.
2. A lecture left with no required question gets the doctor's MCQ-book questions whose handout lines fall inside it
   (fast_points.json `homes`, made by `fast_lessons.py build` from the book's own answer key). They are marked
   `by: "rule:mcq_book"` and rebuilt on every run, so a better placement later replaces them.
Keys are the sources' own (a form's score page, QuizBot's flag, the book's answer list): code never picks one.
Run `py fast_lessons.py build` first (it refreshes fast_points.json), and `py site_questions.py year2-cns` after.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import lectures

ROOT = Path(__file__).resolve().parent
MODULE = "year2-cns"
RULE = "rule:mcq_book"


def main(apply):
    points = json.loads((ROOT / "modules" / MODULE / "site" / "fast_points.json").read_text(encoding="utf-8"))
    by_home = {}
    for wk, p in points.items():
        if wk.startswith("mcqbook:") and p.get("homes"):
            by_home.setdefault(p["homes"][0], []).append(wk)
    stats = Counter()
    for m in sorted(lectures.all_lectures(MODULE), key=lambda m: m["id"]):
        if m.get("kind", "lecture") != "lecture" or m.get("hold") or not m.get("lesson"):
            continue
        req = [r for r in m.get("required") or [] if r.get("by") != RULE]  # the rule's own rows are rebuilt
        have = {(r.get("file"), r.get("n")) for r in req}
        for r in m.get("doctor_questions") or []:
            if (r.get("file"), r.get("n")) not in have:
                req.append({**r, "moved_from": "doctor_questions"})
                have.add((r.get("file"), r.get("n")))
                stats["moved_to_required"] += 1
        if req:
            stats["lessons_with_quiz"] += 1
            added = []
        else:
            added = [{"by": RULE, "word_key": wk, "file": "mcq_book", "n": i}
                     for i, wk in enumerate(sorted(by_home.get(m["id"], [])))]
            stats["lessons_from_mcq_book" if added else "lessons_with_nothing"] += 1
            stats["mcq_book_questions"] += len(added)
        if apply:
            m["required"] = req + added
            if req:
                m["doctor_questions"] = []
            lectures.save(m)
    return stats


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(main("--apply" in sys.argv), indent=1))

"""The owner's lecture questions as an importSfQuestions file (owner, 2026-11-08: upload the first lectures now).

Every bank question in a lecture's Required or Doctor's other list that has a source key and no key conflict goes in,
filed under that lecture's site lesson (by id: the lesson must be on the site). Questions with no key stay out and are
counted: a key never comes from code.

    py site_questions.py year2-cns   -> modules/<module>/site/questions.json (+ counts)
"""
import json
import sys
from collections import Counter
from pathlib import Path

import labels as L
import lectures
from flows.common import read_jsonl

ROOT = Path(__file__).resolve().parent
SHORT = {"year1-musculoskeletal": "msk", "year2-cns": "cns"}
NAMES = {"year1-musculoskeletal": "Musculoskeletal", "year2-cns": "Central Nervous System"}


def sid_of(word_key):
    """The site source_id of a question (the same as fast_lessons.sid_of): bank:, form: (Nagib's quiz) or mcq: (a doctor's MCQ book)."""
    prefix = "form:" if word_key.startswith("nagibform:") else "mcq:" if word_key.startswith("mcqbook:") else "bank:"
    return prefix + L.short(word_key)


def build(module, bank):
    by_key = {q["word_key"]: q for q in bank}
    lessons, questions, skipped, seen = [], [], Counter(), set()
    for m in lectures.all_lectures(module):
        if not m.get("lesson") or m.get("kind", "lecture") != "lecture":
            continue
        subject = (m.get("subject") or "").lower()
        key = f"lecture:{m['id']}"
        lessons.append({"key": key, "subject": subject, "id": m["lesson"]})
        for listname in ("required", "doctor_questions"):
            for item in m.get(listname) or []:
                q = by_key.get(item.get("word_key"))
                if q is None and (item.get("row") or {}).get("key") is not None:
                    # A question the owner's own source brought, not in the bank (Elsamahy's QuizBot test): it carries
                    # the source's own key, so it goes in under a stable id of its file and row.
                    row = item["row"]
                    sid = "own:" + L.short(f"{item.get('file')}:{item.get('n')}")
                    if not 2 <= len(row["options"]) <= 5 or not 0 <= row["key"] < len(row["options"])                             or any(not str(o).strip() for o in row["options"]):
                        skipped["options_or_key"] += 1
                    elif sid in seen:
                        skipped["in_two_lectures"] += 1
                    else:
                        seen.add(sid)
                        questions.append({
                            "source_id": sid, "batch": "58", "lesson": key, "subject": subject,
                            "doctorId": m["doctor"] if (m.get("doctor") or "").startswith("dr-") else None,
                            "topic": m["title"], "stem": row["question"], "options": row["options"], "correct_index": row["key"],
                            "explanation": None, "importance": 3, "repetition": 1, "past_exam": False, "source_url": None,
                            "appearances": [], "_list": listname, "_lecture": m["id"]})
                    continue
                if q is None:
                    skipped["not_in_bank_no_key"] += 1
                    continue
                reason = ("no_key" if q["key"] is None else "key_conflict" if q.get("key_conflict") else
                          "options_count" if not 2 <= len(q["options"]) <= 5 else
                          "empty_option" if any(not str(o).strip() for o in q["options"]) else None)
                if reason:
                    skipped[reason] += 1
                    continue
                if q["word_key"] in seen:
                    skipped["in_two_lectures"] += 1
                    continue
                seen.add(q["word_key"])
                votes, total = q.get("votes") or [], q.get("total") or 0
                questions.append({
                    "source_id": sid_of(q["word_key"]), "batch": "58", "lesson": key, "subject": subject,
                    "doctorId": m["doctor"] if (m.get("doctor") or "").startswith("dr-") else None,
                    "topic": m["title"], "stem": q["question"], "options": q["options"], "correct_index": q["key"],
                    "explanation": q.get("solution") or None, "importance": max(2, q.get("importance_score") or 1),
                    "repetition": q.get("repetition_count") or 1, "past_exam": False, "source_url": q.get("source_url"),
                    "appearances": [{"source_name": s.get("header"), "source_type": "doctor_quiz", "doctor": s.get("doctor"),
                                     "year_or_exam": (s.get("date") or "")[:10] or None, "source_url": s.get("link"),
                                     "source_id": f"{s.get('chat')}:{s.get('msg_id')}"} for s in q["sightings"][:30]],
                    **({"stats": {"attempts": total, "correct": votes[q["key"]]}} if total and q["key"] < len(votes) else {}),
                    "_list": listname, "_lecture": m["id"],
                })
    return {"module": SHORT[module], "module_name": NAMES[module], "lessons": lessons, "questions": questions}, skipped


def run(module):
    data, skipped = build(module, read_jsonl(ROOT / "bank" / "questions.jsonl"))
    lists = [{"lecture": q.pop("_lecture"), "list": q.pop("_list"), "source_id": q["source_id"]} for q in data["questions"]]
    out = ROOT / "modules" / module / "site"
    out.mkdir(parents=True, exist_ok=True)
    (out / "questions.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (out / "question_lists.json").write_text(json.dumps(lists), encoding="utf-8")
    print(json.dumps({"lessons": len(data["lessons"]), "questions": len(data["questions"]),
                      "by_list": Counter(x["list"] for x in lists), "skipped": skipped}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    run(sys.argv[1] if len(sys.argv) > 1 else "year2-cns")

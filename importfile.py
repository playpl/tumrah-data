"""The question import file for one module (plan task 13): bank + labels + the handout's lecture list, in the shape
backend/src/scripts/importSfQuestions.ts reads (`--file`, dry run first).

Only questions that carry a source key, no key conflict, 2-5 options and a lecture of a subject the site has go in;
every other row is counted by reason and stays out. One lesson per handout lecture (`telegram-q:<lecture_id>`).

    py dm.py importfile year2-cns      -> bank/import_cns.json and its counts
"""
import json
from collections import Counter
from pathlib import Path

import labels as L
from merge import read_jsonl

ROOT = Path(__file__).resolve().parent
SHORT = {"year1-musculoskeletal": "msk", "year2-cns": "cns"}
NAMES = {"year1-musculoskeletal": "Musculoskeletal", "year2-cns": "Central Nervous System"}
# Handout subject -> site subject slug. A subject the site does not have stays out (counted) until the owner adds it.
SLUG = {"anatomy": "anatomy", "neuroanatomy": "anatomy", "embryology": "anatomy", "physiology": "physiology",
        "neurophysiology": "physiology", "biochemistry": "biochemistry", "histology": "histology"}
SUFFIX = {"anatomy": "anat", "physiology": "phys", "biochemistry": "biochem", "histology": "hist"}
DOCTOR_KINDS = {"doctor"}


def doctor_ids():
    import sys
    sys.path.insert(0, str(L.PHASE1))
    from build_question_import import DOCTOR_IDS
    return DOCTOR_IDS


def slug_of(subject):
    return SLUG.get(" ".join(str(subject).lower().split()))


def build(module, bank, label_rows, lectures, doctor_id_map, batches=None):
    """(file dict, skipped Counter). batches: chat -> 58 or 59 (labels.batch_of)."""
    labels = {r["word_key"]: r for r in label_rows}
    lec = {x["lecture_id"]: (n, x) for n, x in enumerate(lectures, 1)}
    lessons, questions, skipped = {}, [], Counter()
    for q in bank:
        lab = labels.get(q["word_key"])
        if not lab or lab["module"] != module:
            continue
        reason = ("no_key" if q["key"] is None else "key_conflict" if q.get("key_conflict") else
                  "options_count" if not 2 <= len(q["options"]) <= 5 else
                  "empty_option" if any(not str(o).strip() for o in q["options"]) else
                  "no_lecture" if lab["lecture_id"] not in lec else None)
        if reason is None and not slug_of(lec[lab["lecture_id"]][1]["subject"]):
            reason = "subject_not_on_site"
        if reason:
            skipped[reason] += 1
            continue
        order, lecture = lec[lab["lecture_id"]]
        slug = slug_of(lecture["subject"])
        key = f"telegram-q:{lab['lecture_id']}"
        lessons.setdefault(key, {"key": key, "subject": slug, "name": lecture["title"], "order": order,
                                 "chapter": {"title": NAMES[module], "order": 1, "existing": False}})
        sightings = q["sightings"]
        did = doctor_id_map.get(lab["doctors"][0]) if len(lab["doctors"]) == 1 else None
        did = did if did and did.endswith("-" + SUFFIX[slug]) else None
        votes, total = q.get("votes") or [], q.get("total") or 0
        questions.append({
            "source_id": "bank:" + L.short(q["word_key"]), "batch": str(min({(batches or {}).get(s.get("chat"), 58) for s in sightings} or {58})), "lesson": key, "subject": slug, "doctorId": did,
            "topic": lecture["title"], "stem": q["question"], "options": q["options"], "correct_index": q["key"],
            "explanation": q.get("solution") or None, "importance": q.get("importance_score") or 1,
            "repetition": q.get("repetition_count") or 1, "past_exam": "past_exam" in lab["kinds"],
            "source_url": q.get("source_url"),
            "appearances": [{"source_name": s.get("header"), "source_type": ",".join(lab["kinds"]) or None,
                             "doctor": s.get("doctor"), "year_or_exam": (s.get("date") or "")[:10] or None,
                             "source_url": s.get("link"), "source_id": f"{s.get('chat')}:{s.get('msg_id')}"}
                            for s in sightings[:30]],
            **({"stats": {"attempts": total, "correct": votes[q["key"]]}} if total and q["key"] < len(votes) else {}),
        })
    return {"module": SHORT[module], "module_name": NAMES[module], "lessons": sorted(lessons.values(), key=lambda x: x["order"]),
            "questions": questions}, skipped


def run(module):
    if module not in SHORT:
        raise SystemExit(f"importfile knows {sorted(SHORT)}")
    ref = ROOT / "modules" / module / "reference.json"
    if not ref.exists():
        raise SystemExit(f"no lecture list: run `py dm.py add reference {module}` and `py dm.py run` first")
    if not (ROOT / "bank" / "labels.jsonl").exists():
        raise SystemExit("no labels: run `py dm.py labels` until it writes bank/labels.jsonl")
    data, skipped = build(module, read_jsonl(ROOT / "bank" / "questions.jsonl"), read_jsonl(ROOT / "bank" / "labels.jsonl"),
                          json.loads(ref.read_text(encoding="utf-8"))["lectures"], doctor_ids(),
                          L.batch_of(json.loads((ROOT / "config.json").read_text(encoding="utf-8"))))
    out = ROOT / "bank" / f"import_{SHORT[module]}.json"
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"file": str(out), "lessons": len(data["lessons"]), "questions": len(data["questions"]),
                      "with_doctor": sum(1 for q in data["questions"] if q["doctorId"]), "skipped": dict(skipped)}, indent=1))

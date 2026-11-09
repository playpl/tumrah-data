"""Lesson question tiers (owner, 2026-11-09).

Order: required, then the lesson doctor's own, then everything else (other doctors, past years, AI "Code blue").
- required: the owner's quiz for the lesson (lecture.json `required`); when the owner gave none, the lesson doctor's
  NEW questions (channel index branch `new`) that point into this lesson's pages.
- doctor: the rest of the lesson doctor's questions (old, or new when required came from the owner) on its pages,
  plus the owner's "Doctor's other" list.
- extra: everything else pointed at the lesson's pages; the site makes these from the pointers (recomputeExtras).

    py tiers.py   -> modules/year2-cns/site/tier_<required|doctor>_<lecture>.jsonl (question ids on the site) + counts
"""
import json
import sys
from collections import Counter
from pathlib import Path

import db
import index_map
import labels as L
import lectures

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "modules" / "year2-cns" / "site"


def run():
    points = json.loads((SITE / "fast_points.json").read_text(encoding="utf-8"))
    owner = {}
    for x in json.loads((SITE / "question_lists.json").read_text(encoding="utf-8")):
        owner.setdefault(x["lecture"], {}).setdefault("required" if x["list"] == "required" else "doctor", set()).add(x["source_id"])
    rows, counts = {}, Counter()
    for m in lectures.all_lectures("year2-cns"):
        if m.get("kind", "lecture") != "lecture" or not m.get("lesson"):
            continue
        doc = index_map.LESSON_DOCTOR.get(m.get("doctor"))
        has_required = bool(owner.get(m["id"], {}).get("required"))
        req, dr = set(owner.get(m["id"], {}).get("required", set())), set(owner.get(m["id"], {}).get("doctor", set()))
        by_transcript = m.get("doctor") in index_map.TRANSCRIPT_REQUIRED
        linked = set()
        if by_transcript and (lectures.folder(m["id"]) / "links.jsonl").exists():
            for x in open(lectures.folder(m["id"]) / "links.jsonl", encoding="utf-8"):
                linked |= set(json.loads(x).get("line_ids") or [])
        # The owner's quiz for this doctor (Nagib's forms), split by where each question points: Required.
        quiz = {"form:" + L.short(wk) for wk, p in points.items()
                if p.get("branch") == "owner_quiz" and m["id"] in p.get("homes", [])}
        req |= quiz
        has_required = has_required or bool(quiz)
        for wk, p in points.items():
            if m["id"] not in p.get("homes", []) or p.get("doctor") != doc or not doc or p.get("branch") == "owner_quiz":
                continue
            sid = ("form:" if wk.startswith("nagibform:") else "bank:") + L.short(wk)
            if has_required:
                dr.add(sid)
            elif by_transcript:  # his poll questions on what his recording explains
                (req if linked & set(p["lines"]) else dr).add(sid)
            elif p.get("branch") == "new":
                req.add(sid)
            else:
                dr.add(sid)
        owner_dr = owner.get(m["id"], {}).get("doctor", set())
        req -= owner_dr  # the owner's own "Doctor's other" pick is never promoted to required
        dr = (dr - req) | owner_dr
        rows[m["id"]] = (m["lesson"], req, dr)
        counts[m["id"]] = f"required {len(req)}, doctor {len(dr)} ({doc})"
    r = db.Reader.live()
    allsid = list({s for _, a, b in rows.values() for s in a | b})
    ids = {}
    for i in range(0, len(allsid), 400):
        for d in r.find("questions", {"source_id": {"$in": allsid[i:i + 400]}}, {"source_id": 1}, limit=500):
            ids[d["source_id"]] = str(d["_id"])
    missing = Counter()
    for lid, (lesson, req, dr) in rows.items():
        for kind, sids in (("required", req), ("doctor", dr)):
            have = [{"question_id": ids[s]} for s in sorted(sids) if s in ids]
            missing[kind] += len(sids) - len(have)
            (SITE / f"tier_{kind}_{lid}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in have), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"lessons": counts, "not_on_site_yet": missing}, indent=1))


if __name__ == "__main__":
    run()

"""MSK (year 1 Musculoskeletal) questions onto the site's MSK lessons (owner, 2026-11-21: "just run them").

Source: the batch 59 polls channel (polls/ready/questions.jsonl, chat ZAG_59_Polls), only sightings posted from
2026-11-14 (the MSK polls; everything before is the first term) under a topic header in HEADERS. Keys come only from
Telegram's correct flag (the polls engine). Grade 4 (polls).

    header -> the handout lessons it names (L01..L39, reference.json; graph/sentences.jsonl `lesson` cuts)
    question stem + keyed answer -> the best handout line inside those lessons (IDF word overlap with the line before
        and after as context, the fast_lessons.py scoring); a weak match keeps the header's lessons, no pointer
    -> the site lessons whose placement (modules/year1-musculoskeletal/site/placement.json) holds that handout lesson;
       the least loaded one gets it (fast_lessons.py: one lesson per question, spread)
    A question whose handout lesson has no live site lesson yet waits (reported); a later run files it.

    py msk_questions.py build      -> site/msk_questions.json (importSfQuestions, module "msk") + msk_points.json
    py msk_questions.py pointers   -> site/msk_pointers.jsonl (importHubData pointers; needs the questions on the site)
    py msk_questions.py import     build, importSfQuestions --apply, pointers, importHubData pointers --apply,
                                   recomputeLessonExtras for the MSK lessons
"""
import json
import math
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "polls"))
from engine import word_key  # noqa: E402

import fast_lessons as F  # noqa: E402
import labels as L  # noqa: E402

MODULE = "year1-musculoskeletal"
MDIR = ROOT / "modules" / MODULE
SITE = MDIR / "site"
POLLS = ROOT / "polls" / "ready" / "questions.jsonl"
CHAT, SINCE = "ZAG_59_Polls", "2026-11-14"
LL = [f"L{i:02d}" for i in range(11, 21)]
ALL = [f"L{i:02d}" for i in range(1, 40)]          # "Case Q5:" headers: any lesson, kept only on a strong line match
# Header (as posted, the pointing hand and spaces stripped, lower case) -> handout lessons. Written by Claude from the
# headers of ZAG_59_Polls since 2026-11-14 and the handout's lesson list (reference.json), 2026-11-21.
HEADERS = {
    "pectoral region": ["L01"], "brachial plexus and axilla": ["L02", "L09"], "brachial plexus": ["L02", "L09"],
    "pectoral region & axilla": ["L01", "L02"], "shoulder region": ["L03"], "the muscles of the back": ["L04"],
    "muscles of the back": ["L04"], "the arm": ["L05"], "the forearm": ["L06"], "the hand": ["L07"],
    "blood vessels of the upper limb": ["L08"], "nerves of the upper limb and injuries": ["L09"],
    "joints of upper limb": ["L10"], "muscles of the front of thigh": ["L12", "L13"], "back of the thigh": ["L15"],
    "gluteal region": ["L14"], "the leg & popliteal fossa": ["L16", "L17"], "arteries of lower limb": LL,
    "nerves of the lower limb and injuries": ["L19"], "joints of lower limb": ["L20"],
    "histology of cartilage": ["L21"], "histology of bone": ["L22"], "histology of skeletal muscle": ["L23"],
    "neuromuscular junction": ["L23", "L34"], "histology of skin": ["L24"],
    "resting membrane potential (rmp)": ["L29"], "resting membrane potential": ["L29"],
    "nerve action potential": ["L30"], "action potential": ["L30"], "nerve potentials": ["L29", "L30", "L31"],
    "local response and electrotonus": ["L31"], "nerve conduction": ["L32"], "nerve fiber types": ["L27", "L32"],
    "synapse": ["L33"], "muscle proteins": ["L35"], "muscle contraction": ["L36", "L37"],
    "muscle denervation": ["L35", "L36", "L37"], "smooth muscle": ["L38"], "cardiac muscle action potential": ["L39"],
    "chapter 1: cartilage": ["L21"], "chapter 2: bone": ["L22"], "chapter 3: muscle": ["L23"],
    "chapter 4: skin": ["L24"], "cartilage": ["L21"], "skin physiology": ["L25"], "calcium homeostasis": ["L26"],
    "neuron and reflex arc": ["L27"], "excitability": ["L28"], "excitability factors": ["L28"],
    "excitability changes": ["L28", "L31"], "muscle fiber types": ["L23", "L35"],
}


def norm_header(h):
    return re.sub(r"^[^\w(]+", "", (h or "").strip()).strip().lower()


def read_jsonl(f):
    return [json.loads(x) for x in Path(f).read_text(encoding="utf-8").splitlines() if x.strip()]


def handout():
    """(text lines by id in order, {L01: [line ids in order]})."""
    lines = [ln for ln in read_jsonl(MDIR / "lines.jsonl")]
    lessons = {}
    for s in read_jsonl(MDIR / "graph" / "sentences.jsonl"):
        k = (s.get("lesson") or "").rpartition(":")[2]
        if k:
            lessons.setdefault(k, []).extend(r for r in s.get("rows") or [] if r.rpartition(":")[2].startswith("l"))
    return lines, {k: list(dict.fromkeys(v)) for k, v in lessons.items()}


def site_lessons():
    """{handout lesson: [site lesson key]}, {key: (id, subject, name)} for the live MSK lessons."""
    import db
    rows = read_jsonl(SITE / "lessons.jsonl")
    places = (json.loads((SITE / "placement.json").read_text(encoding="utf-8")) or {}).get("records") or {}
    keys = [r["key"] for r in rows]
    found = {d["sourceRef"]: str(d["_id"]) for d in db.Reader.live().find(
        "lessons", {"sourceRef": {"$in": keys}, "status": "published"}, {"sourceRef": 1}, limit=1000)}
    from spine.records.flow import site_key
    rec_of = {site_key(rid): rid for rid in places}
    meta, home = {}, {}
    for r in rows:
        if r["key"] not in found:
            continue
        meta[r["key"]] = (found[r["key"]], r["subject"], r["name"], r.get("doctorId"))
        for h in places.get(rec_of.get(r["key"])) or []:
            home.setdefault(h, []).append(r["key"])
    return home, meta


def msk_polls():
    """[(question row, [handout lessons], [MSK sightings])] of the MSK polls with a clean key."""
    out, stats = [], Counter()
    for q in read_jsonl(POLLS):
        sights = [s for s in q.get("sightings") or [] if s.get("chat") == CHAT and (s.get("date") or "") >= SINCE]
        if not sights:
            continue
        hs = [norm_header(s.get("header")) for s in sights]
        lessons = sorted({x for h in hs for x in (ALL if h.startswith("case q") else HEADERS.get(h, []))})
        if not lessons:
            stats["header not mapped"] += 1
            stats["unmapped:" + (hs[0] or "")[:40]] += 1
            continue
        if q.get("key") is None or q.get("key_conflict") or not 2 <= len(q["options"]) <= 5 \
                or any(not str(o).strip() for o in q["options"]):
            stats["no clean key"] += 1
            continue
        out.append((q, lessons, sights))
    return out, stats


def build(say=print):
    lines, lesson_ids = handout()
    text = {ln["id"]: ln for ln in lines if ln.get("text")}
    toks = {i: set(F.words(ln["text"])) for i, ln in text.items()}
    df = Counter(w for t in toks.values() for w in t)
    idf = {w: math.log(len(toks) / (1 + n)) for w, n in df.items()}
    home, meta = site_lessons()
    qs, stats = msk_polls()
    kept, pending, points = [], [], {}
    for q, lessons, sights in qs:
        qw = Counter(F.words(q["question"]))
        for w in F.words(q["options"][q["key"]]):
            qw[w] += 2
        best = (0.0, 0, None, None)
        for k in lessons:
            ids = [i for i in lesson_ids.get(k, []) if i in toks]
            for j, i in enumerate(ids):
                ctx = toks[i] | (toks[ids[j - 1]] if j else set()) | (toks[ids[j + 1]] if j + 1 < len(ids) else set())
                hit = [w for w in qw if w in ctx]
                s = sum(idf.get(w, 0) * (1 + 0.5 * (qw[w] > 1)) for w in hit)
                if s > best[0]:
                    best = (s, len(hit), k, (ids, j))
        score, nhit, k, at = best
        strong = k is not None and score >= F.MIN_SCORE and nhit >= F.MIN_WORDS
        if not strong and lessons == ALL:
            stats["case question with no strong line"] += 1
            continue
        where = [k] if strong else lessons
        homes = sorted({h for x in where for h in home.get(x, [])})
        if not homes:
            stats["waits: no live lesson for " + "+".join(where)] += 1
            continue
        wk = word_key(q["question"], q["options"])
        sid = "bank:" + L.short(wk)
        if strong:
            ids, j = at
            span = [x for x in ids[max(0, j - 1):j + 2] if toks[x] & set(qw)] or [ids[j]]
            points[sid] = {"lecture_id": f"{MODULE}:{k}", "lines": span, "page": text[span[0]]["page"],
                           "printed": text[span[0]].get("printed"), "score": round(score, 1)}
            stats["pointed"] += 1
        else:
            stats["lesson by header only (weak line match)"] += 1
        votes, total = q.get("votes") or [], q.get("total") or 0
        kept.append({
            "source_id": sid, "batch": "59", "lesson": homes[0], "subject": "", "doctorId": None, "topic": None,
            "stem": q["question"], "options": q["options"], "correct_index": q["key"],
            "explanation": q.get("solution") or None, "importance": 2, "repetition": len(q.get("sightings") or []) or 1,
            "past_exam": False, "source_url": f"https://t.me/{CHAT}/{sights[0].get('msg_id')}",
            "appearances": [{"source_name": s.get("header"), "source_type": "telegram_poll", "doctor": None,
                             "year_or_exam": (s.get("date") or "")[:10] or None,
                             "source_url": f"https://t.me/{s.get('chat')}/{s.get('msg_id')}",
                             "source_id": f"{s.get('chat')}:{s.get('msg_id')}"} for s in (q.get("sightings") or [])[:30]],
            **({"stats": {"attempts": total, "correct": votes[q["key"]]}} if total and q["key"] < len(votes) else {}),
        })
        pending.append(homes)
    load = Counter()
    for i in sorted(range(len(kept)), key=lambda i: (len(pending[i]), kept[i]["source_id"])):
        h = min(pending[i], key=lambda h: (load[h], h))
        kept[i].update(lesson=h, subject=meta[h][1], topic=meta[h][2])
        load[h] += 1
    seen, uniq = set(), []
    for x in kept:
        if x["source_id"] not in seen:
            seen.add(x["source_id"])
            uniq.append(x)
    used = sorted({x["lesson"] for x in uniq})
    data = {"module": "msk", "module_name": "Musculoskeletal",
            "lessons": [{"key": k, "subject": meta[k][1], "id": meta[k][0]} for k in used], "questions": uniq}
    (SITE / "msk_questions.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    (SITE / "msk_points.json").write_text(json.dumps(points, ensure_ascii=False), encoding="utf-8")
    stats["file questions"] = len(uniq)
    for h, n in sorted(load.items()):
        stats[f"lesson {meta[h][2]} ({h[-14:]})"] = n
    say(json.dumps(dict(sorted(stats.items())), ensure_ascii=False, indent=1))
    return data


def pointers(say=print):
    import db
    points = json.loads((SITE / "msk_points.json").read_text(encoding="utf-8"))
    keys, ids = list(points), {}
    r = db.Reader.live()
    for i in range(0, len(keys), 400):
        for d in r.find("questions", {"source_id": {"$in": keys[i:i + 400]}}, {"source_id": 1}, limit=500):
            ids[d["source_id"]] = str(d["_id"])
    lines = {ln["id"]: ln for ln in read_jsonl(MDIR / "lines.jsonl")}
    rows = []
    for s, p in points.items():
        if s in ids:
            rows.append({"question_id": ids[s], "found": True, "partial": False, "lecture_id": p["lecture_id"],
                         "reason": None, "other_module": None,
                         "spans": [{"pdf_page": p["page"], "printed_page": p["printed"],
                                    "text": " ".join(lines[x]["text"] for x in p["lines"]), "figure": None,
                                    "for_option": None, "line_ids": p["lines"]}]})
    out = SITE / "msk_pointers.jsonl"
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    say(json.dumps({"points": len(points), "on_site": len(ids), "rows": len(rows)}))


def run_import():
    import site_import as S
    env = S.node_env()
    data = build()
    if not data["questions"]:
        print("no MSK question to import")
        return
    S.run(S.TSX + ["src/scripts/importSfQuestions.ts", "--file", str(SITE / "msk_questions.json"), "--backups",
                   str(MDIR / "backups"), "--apply"], cwd=S.BACKEND, env=env,
          keep=["question_writes", "inserted", "updated", "hidden", "key_holds", "refused", "Error"])
    pointers()
    S.run(S.TSX + ["src/scripts/importHubData.ts", "pointers", "--module", MODULE, "--file",
                   str(SITE / "msk_pointers.jsonl"), "--source", "script-index-" + time.strftime("%Y-%m-%d"), "--apply"],
          cwd=S.BACKEND, env=env)
    ids = sorted({x["id"] for x in data["lessons"]})
    out = S.run(S.TSX + ["src/scripts/recomputeLessonExtras.ts"] + ids, cwd=S.BACKEND, env=env, keep=["\x00"])
    print(f"{len([l for l in out.splitlines() if l.strip()])} MSK lessons recomputed")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"build": build, "pointers": pointers, "import": run_import}[sys.argv[1]]()

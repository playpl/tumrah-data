"""Which bank questions might belong to one lecture: code ranks, agents only read the top (owner 2026-11-08).

The pointer agents never read the whole bank. For one lecture:
1. Lecture terms: words on the lecture's handout pages that are rare in the rest of the handout (a word found mostly
   inside the lecture's pages, on few pages overall). Weight = share of its pages inside the lecture x log(rarity).
   Common words ("nerve", "cell") get almost nothing; the lecture's own terms (nuclei, tracts, drugs) get a lot.
2. A question's score is the sum of the lecture terms it shares (stem and options), times its module fit
   (label or posting window: 1.5 when it fits, 0.2 when it is labelled another module) and 1.2 when doctors repeat it.
3. The shortlist is every question above `floor`, at most `cap`. The owner's own questions are the answer key: if any
   of them ranks below the cap, the cap grows to cover it (up to `max`), and the summary says so.
4. `send` turns the owner's questions (first) and the shortlist into lecture-scoped pointer jobs of 25.

Code never decides that a question belongs to the lecture: it only orders what the agents read.

    lectures/<id>/shortlist.jsonl   {word_key, qid, score, rank} per question kept (no question text)
    lectures/<id>/shortlist.json    counts, cap, the owner questions' ranks
"""
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

import labels as L
import lectures
from flows.common import read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parent
BANK = ROOT / "bank"
WORD = re.compile(r"[^\W\d_]{4,}")
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DEFAULTS = {"cap": 400, "max": 1500, "floor": 2.0, "share": 0.5, "max_df": 0.2}
POINTER_BATCH = 25


def cfg():
    return {**DEFAULTS, **CONFIG.get("shortlist", {})}


def words(text):
    return {w.lower() for w in WORD.findall(text or "")}


def qid_of(word_key):
    """The bank question's id everywhere outside the bank (importfile's source_id is "bank:" + the same hash)."""
    return "bank:" + L.short(word_key)


def lecture_terms(module_lines, page_ranges, c=None):
    """{word: weight} for the words that mark this lecture's pages."""
    c = c or cfg()
    pages = {}
    for ln in module_lines:
        pages.setdefault(ln["page"], set()).update(words(f"{ln.get('text') or ''} {ln.get('figure') or ''}"))
    inside = {p for p in pages if any(a <= p <= b for a, b in page_ranges)}
    n = len(pages)
    df = Counter(w for ws in pages.values() for w in ws)
    hits = Counter(w for p in inside for w in pages[p])
    terms = {}
    for w, k in hits.items():
        share = k / df[w]
        if share >= c["share"] and df[w] <= max(1, c["max_df"] * n):
            terms[w] = share * math.log(n / df[w]) if n > df[w] else 0.0
    return {w: v for w, v in terms.items() if v > 0}


def fit(q, module, label):
    if label and label.get("module"):
        return 1.5 if label["module"] == module else 0.2
    return 1.5 if module in L.window_modules(q, CONFIG) else 1.0


def rank(bank, terms, module, label_rows=None):
    """[(score, word_key)] best first, every bank question that shares at least one lecture term."""
    label_rows = label_rows or {}
    out = []
    for q in bank:
        shared = words(" ".join([q.get("question") or "", *(o or "" for o in q.get("options") or [])])) & terms.keys()
        if not shared:
            continue
        s = sum(terms[w] for w in shared) * fit(q, module, label_rows.get(q["word_key"]))
        s *= 1.2 if q.get("repetition_count", 1) > 1 else 1.0
        out.append((round(s, 3), q["word_key"]))
    out.sort(key=lambda x: (-x[0], x[1]))
    return out


def owner_keys(meta):
    """The owner's questions that are bank questions (word_keys), Required first."""
    return [r["word_key"] for r in (meta.get("required") or []) + (meta.get("doctor_questions") or []) if r.get("word_key")]


def cut(ranked, owner, c=None):
    """(kept rows, summary). The owner's questions never count toward the cap; they go to the agents anyway."""
    c = c or cfg()
    pos = {k: i for i, (_, k) in enumerate(ranked)}
    owner_ranks = {k: pos.get(k) for k in owner}
    above = [i for i, (s, _) in enumerate(ranked) if s >= c["floor"]]
    found = [r for r in owner_ranks.values() if r is not None]
    cap = c["cap"]
    if found and max(found) >= cap:
        cap = min(c["max"], math.ceil((max(found) + 1) * 1.25))
    owned = set(owner)
    kept = [{"word_key": k, "qid": qid_of(k), "score": s, "rank": i + 1}
            for i, (s, k) in enumerate(ranked[:cap]) if k not in owned and s >= c["floor"]]
    summary = {"ranked": len(ranked), "above_floor": len(above), "cap": cap, "grew": cap != c["cap"], "kept": len(kept),
               "owner_in_bank": len(owner), "owner_ranked": len(found),
               "owner_within_default_cap": sum(r < c["cap"] for r in found),
               "owner_ranks": sorted(r + 1 for r in found)}
    return kept, summary


def label_rows():
    f = BANK / "labels.jsonl"
    return {r["word_key"]: r for r in read_jsonl(f)} if f.exists() else {}


def build(lecture_id, bank=None):
    """Writes lectures/<id>/shortlist.jsonl and shortlist.json; returns the summary."""
    meta = lectures.load(lecture_id)
    if not meta.get("ranges"):
        raise ValueError("place the lecture in the handout first")
    module_lines = read_jsonl(ROOT / "modules" / meta["module"] / "lines.jsonl")
    terms = lecture_terms(module_lines, lectures.page_ranges(meta))
    bank = bank if bank is not None else read_jsonl(BANK / "questions.jsonl")
    kept, summary = cut(rank(bank, terms, meta["module"], label_rows()), owner_keys(meta))
    d = lectures.folder(lecture_id)
    write_jsonl(d / "shortlist.jsonl", kept)
    summary.update(terms=len(terms), at=__import__("time").strftime("%Y-%m-%d %H:%M"))
    (d / "shortlist.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def batch_row(q, subject_hint=None):
    """A bank question as a pointer batch row; `correct_index` is context only (the worker never judges it)."""
    return {"qid": qid_of(q["word_key"]), "word_key": q["word_key"], "subject_hint": subject_hint, "stem": q["question"],
            "case_text": None, "options": q["options"], "correct_index": q.get("key")}


def send(lecture_id, queue, bank=None):
    """Queues lecture-scoped pointer jobs: the owner's bank questions first, then the shortlist. A question already
    sent for this lecture is never sent again. Returns counts."""
    meta = lectures.load(lecture_id)
    d = lectures.folder(lecture_id)
    if not (d / "shortlist.jsonl").exists():
        raise ValueError("build the shortlist first")
    order = owner_keys(meta) + [r["word_key"] for r in read_jsonl(d / "shortlist.jsonl")]
    sent_file = d / "sent.json"
    sent = set(json.loads(sent_file.read_text(encoding="utf-8"))) if sent_file.exists() else set()
    want = [k for k in dict.fromkeys(order) if k not in sent]
    by_key = {q["word_key"]: q for q in (bank if bank is not None else read_jsonl(BANK / "questions.jsonl"))
              if q["word_key"] in set(want)}
    rows = [batch_row(by_key[k], meta["title"]) for k in want if k in by_key]
    jobs = []
    for i in range(0, len(rows), POINTER_BATCH):
        b = rows[i:i + POINTER_BATCH]
        key = f"{lecture_id}-" + hashlib.sha1(",".join(r["qid"] for r in b).encode()).hexdigest()[:12]
        jobs.append({"key": key, "payload": {"module": meta["module"], "lecture": lecture_id, "batch": b}})
    added = queue.add_jobs("pointers", jobs) if jobs else 0
    sent_file.write_text(json.dumps(sorted(sent | {r["word_key"] for r in rows})), encoding="utf-8")
    return {"questions": len(rows), "jobs": len(jobs), "new_jobs": added,
            "owner_first": sum(k in set(owner_keys(meta)) for k in (r["word_key"] for r in rows))}


def results(lecture_id, queue, jobs_root=ROOT / "jobs"):
    """What the pointer agents found for this lecture: {word_key: {found, reason, line_ids}} from passed jobs."""
    out = {}
    for r in queue.db.execute("SELECT key, payload FROM jobs WHERE flow='pointers' AND status='passed' AND key LIKE ?",
                              (f"{lecture_id}-%",)):
        p = json.loads(r["payload"])
        if p.get("lecture") != lecture_id:
            continue
        wk = {b["qid"]: b["word_key"] for b in p["batch"]}
        d = jobs_root / "pointers" / r["key"]
        rows = {x["qid"]: x for x in read_jsonl(d / "out.jsonl")} if (d / "out.jsonl").exists() else {}
        ptr = {x["question_id"]: x for x in read_jsonl(d / "pointers.jsonl")} if (d / "pointers.jsonl").exists() else {}
        for qid, k in wk.items():
            x = rows.get(qid, {})
            spans = (ptr.get(qid) or {}).get("spans", [])
            out[k] = {"found": bool(x.get("found")), "reason": x.get("reason"),
                      "line_ids": [i for s in spans for i in s.get("line_ids") or []]}
    return out

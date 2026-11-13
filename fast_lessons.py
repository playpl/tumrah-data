"""Fast path (owner, 2026-11-09: everything for the named lessons on the site within the hour).

Bank questions labelled to the handout lectures that the named lessons teach are pointed at handout lines by script
(no fleet): the question stem plus its keyed answer are scored against each handout line of the label's pages
(IDF-weighted word overlap, with the line before and after as context). A question is kept only when its best line
lies inside a named lesson's handout range and the match is strong enough. Scores only; Claude reads no text.

    py fast_lessons.py build      -> modules/year2-cns/site/questions.json (owner lists + kept questions, for
                                     importSfQuestions) and fast_points.json (word_key -> line ids)
    py fast_lessons.py pointers   -> modules/year2-cns/site/pointers_fast.jsonl (needs the questions on the site)
"""
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import labels as L
import index_map
import lectures
import site_questions
from flows.common import read_jsonl

ROOT = Path(__file__).resolve().parent
MODULE = "year2-cns"
SITE = ROOT / "modules" / MODULE / "site"
# Handout lecture (label list) -> its pages. The named lessons that teach them are found from their ranges.
_REF = ROOT / "modules" / MODULE / "old" / "agent-lecture-list-2026-11-08" / "reference.json"
# Every handout lecture: a question is searched only inside its own lecture's pages, and kept only when it lands in a
# named lesson (owner, 2026-11-09: all doctors' lessons).
LABEL_PAGES = {x["lecture_id"]: tuple(x["pdf_pages"]) for x in json.loads(_REF.read_text(encoding="utf-8"))["lectures"]}
MIN_SCORE = 9.0     # summed IDF of matched words
MIN_WORDS = 3       # distinct matched content words
STOP = set("""the and for with that this from which what are was were has have had not but all any can its into
than then they them their there these those most more less least each other only also been being does did
will would should could may might must shall about between during after before under over above below such
following true false except regarding concerning correct incorrect statement statements none both either
one two three four five due because where when while how why who whom whose very much many some""".split())
WORD = re.compile(r"[a-z][a-z0-9]{2,}")


def sid_of(word_key):
    """The site source_id of a question: bank:, form: (Nagib's quiz) or mcq: (a doctor's MCQ book)."""
    prefix = "form:" if word_key.startswith("nagibform:") else "mcq:" if word_key.startswith("mcqbook:") else "bank:"
    return prefix + L.short(word_key)


def words(text):
    return [w for w in WORD.findall(str(text or "").lower()) if w not in STOP]


def lesson_lines(lines=None):
    """lecture id -> set of handout line ids inside its ranges, for the lectures that are lessons on the site
    (ledger.lesson_ids: a range cut at a heading is read line by line, an older one by whole pages)."""
    import ledger
    site = {m["id"] for m in lectures.all_lectures(MODULE) if m.get("lesson")}
    return {lid: ids for lid, ids in ledger.lesson_ids(MODULE).items() if lid in site}


def labelled():
    """(bank, labels, index, n_bank): every question that has a place to be searched in. bank = the bank's rows, then
    the owner's quiz rows and the doctors' MCQ-book rows (after n_bank); labels = word_key -> {lecture_id | pages, by}."""
    labels = {r["word_key"]: r for r in read_jsonl(ROOT / "bank" / "labels.jsonl")
              if r["module"] == MODULE and r.get("lecture_id") in LABEL_PAGES}
    # The channel index (index_map.py) names the exact lecture, doctor and branch; it wins over the label.
    imap = ROOT / "sources" / "index" / "cns_question_map.json"
    index = json.loads(imap.read_text(encoding="utf-8")) if imap.exists() else {}
    for wk, hits in index.items():
        lec = next((h["lecture_id"] for h in hits if h.get("lecture_id")), None)
        if lec in LABEL_PAGES:
            labels[wk] = {**labels.get(wk, {}), "word_key": wk, "lecture_id": lec, "by": "index"}
        elif lec and wk in labels:
            del labels[wk]  # the index puts it in a lecture no named lesson teaches
    bank = read_jsonl(ROOT / "bank" / "questions.jsonl")
    n_bank = len(bank)
    # Dr. Nagib's chapter quizzes (nagib_quizzes.py, keys from the forms' own score pages): the owner's Required set,
    # split to the Nagib lecture whose pages hold each question (owner, 2026-11-09).
    quiz_lecture = {"receptor quiz": "year2-cns:L19", "Pain quiz": "year2-cns:L20", "Sensation Types Quiz": "year2-cns:L20"}
    nagib = {m["id"] for m in lectures.all_lectures(MODULE) if m.get("doctor") == "dr-naguib-el-husseiny-phys"}
    keyed = SITE / "nagib_quiz_keyed.jsonl"
    for r in read_jsonl(keyed) if keyed.exists() else []:
        if r["key"] is None:
            continue
        wk = f"nagibform:{r['item_id']}"
        bank.append({"word_key": wk, "question": r["question"], "options": r["options"], "key": r["key"], "sightings": [],
                     "source_url": r["url"], "quiz": True, "importance_score": 3})
        labels[wk] = {"word_key": wk, "lecture_id": quiz_lecture.get(r["form"], "year2-cns:L20"), "by": "owner_quiz"}
    # Doctors' MCQ books (mcq.py), keyed by the book's own answer list: the doctor's own questions, searched only in
    # the pages of that doctor's lessons (owner, 2026-11-09: MCQ book questions are the doctor's).
    for f in sorted((ROOT / "modules" / MODULE / "mcq").glob("*.jsonl")):
        for r in read_jsonl(f):
            if r.get("key") is None or not r.get("doctor"):
                continue
            mine = [m for m in lectures.all_lectures(MODULE) if m.get("doctor") == r["doctor"] and m.get("pdf_pages")]
            if not mine:
                continue
            wk = f"mcqbook:{r['qid']}"
            bank.append({"word_key": wk, "question": r["question"], "options": r["options"], "key": r["key"], "sightings": [],
                         "source_url": None, "mcq_doctor": r["doctor"], "importance_score": 3})
            labels[wk] = {"word_key": wk, "lecture_id": None, "by": "mcq_book",
                          "pages": (min(m["pdf_pages"][0] for m in mine), max(m["pdf_pages"][1] for m in mine))}
    return bank, labels, index, n_bank


def build():
    lines = read_jsonl(ROOT / "modules" / MODULE / "lines.jsonl")
    text_lines = [ln for ln in lines if ln.get("text")]
    df = Counter()
    toks = {}
    for ln in text_lines:
        toks[ln["id"]] = set(words(ln["text"]))
        df.update(toks[ln["id"]])
    idf = {w: math.log(len(text_lines) / (1 + n)) for w, n in df.items()}
    by_page = {}
    for ln in text_lines:
        by_page.setdefault(ln["page"], []).append(ln)
    in_lesson = lesson_lines(lines)
    bank, labels, index, n_bank = labelled()
    base, skipped = site_questions.build(MODULE, bank)  # the full bank: Required items may be MCQ-book questions (required_rule.py)
    # The ledger's better readings (owner, agreed, or an AI reader that passed its spot checks) replace the word-overlap
    # choice, and a link the owner marked wrong is dropped (owner, 2026-11-10: lowest error rate).
    import ledger
    ldb = ledger.connect()
    better = {src: json.loads(r["lines"]) for src, r in ledger.ready(ldb, MODULE, "question").items() if r["runner"] != "script"}
    rejected = {r["src"] for r in ldb.execute("SELECT src FROM links WHERE kind='question' AND runner='script' AND state='rejected'")}
    ldb.close()
    by_id = {ln["id"]: ln for ln in lines}
    nagib = {m["id"] for m in lectures.all_lectures(MODULE) if m.get("doctor") == "dr-naguib-el-husseiny-phys"}
    have = {q["source_id"] for q in base["questions"]}
    metas = {m["id"]: m for m in lectures.all_lectures(MODULE)}
    lesson_key = {lid: f"lecture:{lid}" for lid in in_lesson}
    kept, points, stats = [], {}, Counter()
    for q in bank:
        lab = labels.get(q["word_key"])
        if not lab:
            continue
        if q["key"] is None or q.get("key_conflict") or not 2 <= len(q["options"]) <= 5 \
                or any(not str(o).strip() for o in q["options"]):
            stats["no_clean_key"] += 1
            continue
        ai = [x for x in better.get(q["word_key"], []) if x in by_id]
        if ai:
            ln, score, span_ids = by_id[ai[0]], 0.0, ai
            homes = [lid for lid, ids in in_lesson.items() if set(ai) & ids]
            stats["better_reading"] += 1
        else:
            if q["word_key"] in rejected:
                stats["rejected_by_owner"] += 1
                continue
            qw = Counter(words(q["question"]))
            for w in words(q["options"][q["key"]]):
                qw[w] += 2  # the keyed answer is what the handout line must say
            lo, hi = lab.get("pages") or LABEL_PAGES[lab["lecture_id"]]
            best = (0.0, 0, None, None)
            for page in range(lo, hi + 1):
                pl = by_page.get(page, [])
                for i, ln in enumerate(pl):
                    ctx = toks[ln["id"]] | (toks[pl[i - 1]["id"]] if i else set()) | (toks[pl[i + 1]["id"]] if i + 1 < len(pl) else set())
                    hit = [w for w in qw if w in ctx]
                    s = sum(idf.get(w, 0) * (1 + 0.5 * (qw[w] > 1)) for w in hit)
                    if s > best[0]:
                        best = (s, len(hit), ln, i)
            score, nhit, ln, i = best
            if ln is None or score < MIN_SCORE or nhit < MIN_WORDS:
                stats["weak_match"] += 1
                continue
            homes = [lid for lid, ids in in_lesson.items() if ln["id"] in ids]
            pl = by_page[ln["page"]]
            span_ids = [x["id"] for x in pl[max(0, i - 1):i + 2] if toks[x["id"]] & set(qw)] or [ln["id"]]
        if q.get("quiz"):
            homes = [h for h in homes if h in nagib]
        if q.get("mcq_doctor"):
            homes = [h for h in homes if metas[h].get("doctor") == q["mcq_doctor"]]
        if not homes:
            stats["outside_named_lessons"] += 1
            continue
        ih = index.get(q["word_key"]) or ([{"branch": "owner_quiz", "doctor": "Nagib El-Husseiny"}] if q.get("quiz") else
                                         [{"branch": "mcq_book", "doctor": index_map.LESSON_DOCTOR.get(q["mcq_doctor"])}]
                                         if q.get("mcq_doctor") else [{}])
        points[q["word_key"]] = {"lecture_id": lab["lecture_id"], "lines": span_ids,
                                 "page": ln["page"], "printed": ln.get("printed"), "score": round(score, 1),
                                 "homes": homes, "by": lab.get("by", "label"),
                                 "branch": ih[0].get("branch"), "doctor": ih[0].get("doctor"),
                                 **({"reader": "ledger"} if ai else {})}  # not the script's own choice: ledger.sync skips it
        stats["by:" + lab.get("by", "label")] += 1
        sid = sid_of(q["word_key"])
        stats["kept"] += 1
        if sid in have:
            stats["already_in_owner_lists"] += 1
            continue
        m = metas[homes[0]]
        votes, total = q.get("votes") or [], q.get("total") or 0
        kept.append({
            "source_id": sid, "batch": "58", "lesson": lesson_key[homes[0]], "subject": (m.get("subject") or "").lower(),
            "doctorId": None, "topic": m["title"], "stem": q["question"], "options": q["options"], "correct_index": q["key"],
            "explanation": q.get("solution") or None, "importance": max(1, q.get("importance_score") or 1),
            "repetition": q.get("repetition_count") or 1, "past_exam": False, "source_url": q.get("source_url"),
            **({"doctorId": "dr-naguib-el-husseiny-phys"} if q.get("quiz") else {"doctorId": q["mcq_doctor"]} if q.get("mcq_doctor") else {}),
            "appearances": [{"source_name": s.get("header"), "source_type": "telegram_poll", "doctor": s.get("doctor"),
                             "year_or_exam": (s.get("date") or "")[:10] or None, "source_url": s.get("link"),
                             "source_id": f"{s.get('chat')}:{s.get('msg_id')}"} for s in q["sightings"][:30]],
            **({"stats": {"attempts": total, "correct": votes[q["key"]]}} if total and q["key"] < len(votes) else {}),
        })
        stats["by_lesson:" + homes[0]] += 1
    base["questions"].extend(kept)
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "questions.json").write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    (SITE / "fast_points.json").write_text(json.dumps(points), encoding="utf-8")
    print(json.dumps({"file_questions": len(base["questions"]), "stats": stats, "owner_lists_skipped": skipped}, indent=1))


def pointers():
    import db
    points = json.loads((SITE / "fast_points.json").read_text(encoding="utf-8"))
    sid = {sid_of(k): k for k in points}
    r = db.Reader.live()
    ids = {}
    keys = list(sid)
    for i in range(0, len(keys), 400):
        for d in r.find("questions", {"source_id": {"$in": keys[i:i + 400]}}, {"source_id": 1}, limit=500):
            ids[d["source_id"]] = str(d["_id"])
    lines = {ln["id"]: ln for ln in read_jsonl(ROOT / "modules" / MODULE / "lines.jsonl")}
    rows = []
    for s, wk in sid.items():
        if s not in ids:
            continue
        p = points[wk]
        rows.append({"question_id": ids[s], "found": True, "partial": False, "lecture_id": p["lecture_id"], "reason": None,
                     "other_module": None, "spans": [{"pdf_page": p["page"], "printed_page": p["printed"],
                                                      "text": " ".join(lines[x]["text"] for x in p["lines"]),
                                                      "figure": None, "for_option": None, "line_ids": p["lines"]}]})
    out = SITE / "pointers_fast.jsonl"
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    print(json.dumps({"points": len(points), "on_site": len(ids), "rows": len(rows), "file": str(out)}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"build": build, "pointers": pointers}[sys.argv[1]]()

"""Poll titles -> handout lectures (owner, 2026-11-14: every message that is not a poll is a title or subtitle that
organizes the polls under it; use them so a pointer worker searches one lecture's pages, not the whole handout).

A poll's title is the last text message above it in its channel, all its lines ("Dr.Khaled Abualfadle / Sensory
receptors", "Eye / Hard"). The poll engine kept only the first line (`header`), which lost the topic.
For each CNS question with no lecture from the channel index (index_map.py):
1. topic: the title's words through index_map.LECTURE_RULES, in the subject the channel index gives the poll
   (its subject list: Code Blue specials are listed per subject), else the subject of the doctor the title names,
   else every subject (a topic like "Eye" then names its anatomy, histology and physiology lectures);
2. doctor: a title that names a doctor and no topic ("Dr.Amr Mosafer Notebook / Final Zatoona", "Mid", "TBL") ->
   the lectures that doctor teaches on the site;
3. otherwise an orphan (past exams, embryology, mixed chapters): kept with its title for an AI reader.
Code only narrows where to search; it never decides the lines.

    py titles.py    -> sources/index/title_map.json {word_key: {lectures, how, title}} and counts
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import index_map as IM

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "polls" / "raw"
OUT = ROOT / "sources" / "index" / "title_map.json"
MODULE = "year2-cns"
SUBJECTS = ("anatomy", "histology", "physiology")
SUFFIX = {"anat": "anatomy", "hist": "histology", "phys": "physiology"}


def titles():
    """{(chat, msg_id): full text of the last title above that poll}, for every channel the engine saved."""
    out = {}
    for f in sorted(RAW.glob("*/messages.jsonl")):
        ms = sorted((json.loads(line) for line in open(f, encoding="utf-8")), key=lambda m: m["msg_id"])
        cur = ""
        for m in ms:
            if not m.get("poll"):
                if (m.get("text") or "").strip():
                    cur = m["text"].strip()
                continue
            out[(f.parent.name, m["msg_id"])] = cur
    return out


def doctor_lectures():
    """{bank doctor name: (subject, [handout lecture ids the doctor's site lessons teach])}."""
    import dm
    import lectures
    chapters = dm.handout_chapters(MODULE)
    names = {v: k for k, v in IM.LESSON_DOCTOR.items()}
    out = {}
    for name, did in names.items():
        subject = SUFFIX.get(did.rsplit("-", 1)[-1])
        lecs = set()
        for m in lectures.all_lectures(MODULE):
            if m.get("doctor") == did and m.get("ranges"):
                chap, how = dm.chapter_of(m, subject, chapters)
                if chap and how == "pages":
                    lecs.add(chap["id"])
        out[name] = (subject, sorted(lecs))
    return out


def doctor_in(text):
    s = " " + " ".join(re.sub(r"[^a-z]+", " ", text.lower()).split()) + " "
    return next((v for k, v in IM.DOCTORS.items() if f" {k} " in s or f"dr {k}" in s), None)


def topics(subject, text):
    """Every handout lecture a title names in one subject ("Face & Blood supply" -> face and arterial supply), not
    only the first rule that matches (index_map.lecture_of)."""
    s = " " + " ".join(IM.STRIP.sub(" ", (text or "").lower()).split()) + " "
    out, taken = set(), s
    for key, lec in IM.LECTURE_RULES[subject]:
        pat = r"(?<![a-z0-9])" + re.escape(key.strip()) + r"(?:s|es)?(?![a-z0-9])"
        if re.search(pat, taken):
            out.add(f"{MODULE}:{lec}")
            taken = re.sub(pat, " ", taken)  # "basal lesion" is used up, so "lesion" alone cannot match again
    return out


def scope(text, subjects, docs):
    """(lectures, how) for one title."""
    doctor = doctor_in(text)
    if not subjects and doctor and docs.get(doctor, (None,))[0]:
        subjects = {docs[doctor][0]}
    found = set().union(*(topics(sub, text) for sub in (subjects or SUBJECTS)))
    if found:
        return sorted(found), "title" + ("+index" if subjects else "")
    if doctor and docs.get(doctor, (None, []))[1]:
        return docs[doctor][1], "doctor"
    return [], None


def run():
    sys.stdout.reconfigure(encoding="utf-8")
    tmap = titles()
    imap = json.loads((ROOT / "sources" / "index" / "cns_question_map.json").read_text(encoding="utf-8"))
    labels = {r["word_key"]: r for r in map(json.loads, open(ROOT / "bank" / "labels.jsonl", encoding="utf-8"))}
    docs = doctor_lectures()
    out, stats, orphans = {}, Counter(), Counter()
    with open(ROOT / "bank" / "questions.jsonl", encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            wk = q["word_key"]
            hits = imap.get(wk, [])
            if any(h.get("lecture_id") for h in hits) or labels.get(wk, {}).get("module") != MODULE:
                continue
            subjects = {h["subject"] for h in hits}
            lecs, how, first = set(), None, ""
            for s in q["sightings"]:
                text = tmap.get((s.get("chat"), s.get("msg_id")), "")
                first = first or text
                got, h = scope(text, subjects, docs)
                if got and (how is None or h.startswith("title") or how == "doctor" and h == "doctor"):
                    if h.startswith("title") and how == "doctor":
                        lecs = set()  # a topic title beats a doctor-only title
                    lecs |= set(got)
                    how = h if how is None or h.startswith("title") else how
            title = " / ".join(x.strip() for x in first.split("\n") if x.strip())[:120]
            out[wk] = {"lectures": sorted(lecs), "how": how, "title": title}
            stats[(how or "orphan") + (f":{min(len(lecs), 3)}" if lecs else "")] += 1
            if not lecs:
                orphans[title[:50]] += 1
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"questions": len(out), **dict(sorted(stats.items()))}, indent=1))
    print("top orphan titles:")
    for t, n in orphans.most_common(15):
        print(f"  {n:5}  {t}")


def jobs(queue=True):
    """Haiku pointer jobs (flows/pointers.py, 25 questions each) for the labelled, cleanly keyed questions no AI has read,
    one scope per set of handout pages (owner, 2026-11-14: no Gemini, small context per worker)."""
    import hashlib
    import fast_lessons
    import gemini_run
    import ledger
    import outline
    import queue_db
    from shortlist import batch_row
    names = {r["lecture_id"]: r["title"] for r in outline.reference(MODULE)}
    tmap = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    _, labels, _, _ = fast_lessons.labelled()
    db = ledger.connect()
    groups = gemini_run.pointer_groups(MODULE, db)
    db.close()
    out = []
    for ranges, qs in sorted(groups.items(), key=lambda kv: kv[0]):
        lecs = sorted({x for q in qs for x in (labels[q["word_key"]].get("lectures") or [labels[q["word_key"]].get("lecture_id")]) if x})
        if not lecs:  # an MCQ-book question: the handout lectures its doctor's lesson pages fall in
            lecs = sorted(x for x, (a, b) in fast_lessons.LABEL_PAGES.items() if any(a <= hi and lo <= b for lo, hi in ranges))
        title = Counter(tmap.get(q["word_key"], {}).get("title") or names.get(labels[q["word_key"]].get("lecture_id"), "")
                        for q in qs).most_common(1)[0][0] or "this lecture"
        scope = {"title": title, "ranges": [list(r) for r in ranges],
                 "lectures": [{"lecture_id": x, "title": names.get(x, x), "pdf_pages": list(fast_lessons.LABEL_PAGES[x])}
                              for x in lecs if x in fast_lessons.LABEL_PAGES]}
        for i in range(0, len(qs), 25):
            batch = [batch_row(q, title) for q in qs[i:i + 25]]
            key = f"{MODULE}-t-" + hashlib.sha1(",".join(r["qid"] for r in batch).encode()).hexdigest()[:12]
            out.append({"key": key, "payload": {"module": MODULE, "batch": batch, "scope": scope}})
    pages = [sum(b - a + 1 for a, b in j["payload"]["scope"]["ranges"]) for j in out]
    print(f"{len(out)} pointer jobs, {sum(len(j['payload']['batch']) for j in out)} questions, "
          f"pages per job: median {sorted(pages)[len(pages) // 2] if pages else 0}, max {max(pages or [0])}")
    if queue:
        q = queue_db.Queue()
        print("queued", q.add_jobs("pointers", out))
        q.close()
    return out


class Scorer:
    """Rare-word overlap of a question (stem + keyed option twice) with each handout line, to check a scope: code only
    narrows where the reader looks; the reader picks the lines."""

    def __init__(self):
        import math
        import fast_lessons as F
        self.F = F
        lines = [ln for ln in map(json.loads, open(ROOT / "modules" / MODULE / "lines.jsonl", encoding="utf-8"))
                 if ln.get("text")]
        self.lines = lines
        toks = [set(F.words(ln["text"])) for ln in lines]
        df = Counter(w for t in toks for w in t)
        self.idf = {w: math.log(len(lines) / (1 + n)) for w, n in df.items()}
        self.post = {}
        for i, t in enumerate(toks):
            for w in t:
                if df[w] <= 300:
                    self.post.setdefault(w, []).append(i)
        self.page_lec = {}
        for lec, (a, b) in F.LABEL_PAGES.items():
            for p in range(a, b + 1):
                self.page_lec.setdefault(p, []).append(lec)

    def best(self, q):
        """{handout lecture: (best score, page of that line)}."""
        qw = Counter(self.F.words(q["question"]))
        if q.get("key") is not None and q["key"] < len(q["options"]):
            for w in self.F.words(q["options"][q["key"]]):
                qw[w] += 2
        score = Counter()
        for w in qw:
            for i in self.post.get(w, ()):
                score[i] += self.idf[w] * (1.5 if qw[w] > 1 else 1)
        out = {}
        for i, s in score.items():
            for lec in self.page_lec.get(self.lines[i]["page"], ()):
                if s > out.get(lec, (0, 0))[0]:
                    out[lec] = (s, self.lines[i]["page"])
        return out


WINDOW = 20      # pages per read (Fable, 2026-11-14: more dilutes Haiku's attention)
MOVE = 1.5       # another lecture must beat the scope this many times over to move a question


def windows(ranges):
    out = []
    for a, b in ranges:
        while a <= b:
            out.append((a, min(b, a + WINDOW - 1)))
            a += WINDOW
    return out


def one_jobs(reader, only=None, queue=True):
    """One-read pointer jobs (flows/pointers_one.py) for reader A or B: scope checked by code, at most 20 pages, 25
    questions and 2 decoys each. `only`: word_keys to limit to (a pilot)."""
    import hashlib
    import random
    import fast_lessons
    import gemini_run
    import ledger
    import outline
    import queue_db
    from shortlist import batch_row
    names = {r["lecture_id"]: r["title"] for r in outline.reference(MODULE)}
    tmap = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    _, labels, _, _ = fast_lessons.labelled()
    db = ledger.connect()
    groups = gemini_run.pointer_groups(MODULE, db)
    db.close()
    sc = Scorer()
    placed, moved, best_of = {}, 0, {}
    for ranges, qs in groups.items():
        for q in qs:
            if only and q["word_key"] not in only:
                continue
            lab = labels[q["word_key"]]
            lecs = set(lab.get("lectures") or ([lab["lecture_id"]] if lab.get("lecture_id") else []))
            if not lecs:
                lecs = {x for x, (a, b) in fast_lessons.LABEL_PAGES.items() if any(a <= hi and lo <= b for lo, hi in ranges)}
            best = sc.best(q)
            best_of[q["word_key"]] = best
            inside = max([best[x][0] for x in lecs if x in best] or [0])
            top = max(best.items(), key=lambda kv: kv[1][0]) if best else None
            if top and top[0] not in lecs and top[1][0] >= fast_lessons.MIN_SCORE and top[1][0] >= MOVE * inside:
                lecs = {top[0]} | ({max((x for x in lecs if x in best), key=lambda x: best[x][0])}
                                   if inside >= fast_lessons.MIN_SCORE else set())
                moved += 1
            # the main lecture: the one in the scope holding the question's best line (a reader B that disagrees,
            # or an "other_lecture", sends it on); the window of at most 20 pages around that line
            main = max(lecs, key=lambda x: best.get(x, (0, 0))[0]) if any(x in best for x in lecs) else sorted(lecs)[0]
            wins = windows([fast_lessons.LABEL_PAGES[main]])
            page = best.get(main, (0, None))[1]
            win = next((w for w in wins if page and w[0] <= page <= w[1]), wins[0])
            placed.setdefault((win, main), []).append(q)
    # full batches of 25 per unit; the remainders packed with their neighbours (page order) up to 25 questions, 20 pages
    pool = [q for qs in placed.values() for q in qs]
    packs, rest = [], []
    for (win, main), qs in sorted(placed.items()):
        qs = sorted(qs, key=lambda q: q["word_key"])
        random.Random(f"{reader}:{win}").shuffle(qs)  # reader B gets other batch mates
        n = len(qs) - len(qs) % 25
        packs += [([(win, main)], qs[i:i + 25]) for i in range(0, n, 25)]
        if qs[n:]:
            rest.append(((win, main), qs[n:]))
    cur_units, cur_qs = [], []
    for unit, qs in rest:
        pages = sum(b - a + 1 for a, b in fast_lessons.merge_ranges([u[0] for u in cur_units] + [unit[0]]))
        if cur_qs and (len(cur_qs) + len(qs) > 25 or pages > WINDOW):
            packs.append((cur_units, cur_qs))
            cur_units, cur_qs = [], []
        cur_units.append(unit)
        cur_qs = cur_qs + qs
        while len(cur_qs) > 25:
            packs.append((cur_units, cur_qs[:25]))
            cur_qs = cur_qs[25:]
    if cur_qs:
        packs.append((cur_units, cur_qs))
    jobs = []
    for units, qs in packs:
        ranges = fast_lessons.merge_ranges(u[0] for u in units)
        lecs = sorted({u[1] for u in units})
        keep = {p for a, b in ranges for p in range(a, b + 1)}
        title = Counter(tmap.get(q["word_key"], {}).get("title") or names.get(lecs[0], "") for q in qs).most_common(1)[0][0]
        scope = {"title": title or names.get(lecs[0], ""), "ranges": [list(r) for r in ranges],
                 "lectures": [{"lecture_id": x, "title": names.get(x, x), "pdf_pages": list(fast_lessons.LABEL_PAGES[x])}
                              for x in lecs]}
        batch = [batch_row(q, title) for q in qs]
        key = f"{MODULE}-o{reader}-" + hashlib.sha1(",".join(r["qid"] for r in batch).encode()).hexdigest()[:12]
        far = [q for q in pool if (b := best_of.get(q["word_key"])) and
               (t := max(b.items(), key=lambda kv: kv[1][0]))[1][0] >= 15 and t[1][1] not in keep and t[0] not in lecs
               and max([b[x][0] for x in lecs if x in b] or [0]) < 0.4 * t[1][0]]  # nothing like it on these pages
        decoys = [batch_row(q) for q in random.Random(key).sample(far, min(2, len(far)))]
        jobs.append({"key": key, "payload": {"module": MODULE, "reader": reader, "scope": scope,
                                             "batch": batch, "decoys": decoys}})
    # owner 2026-11-14: the lessons on the site now first, then the most important questions (repeated across doctors)
    import lectures
    site_pages = {p for m in lectures.all_lectures(MODULE) if m.get("lesson")
                  for a, b in lectures.page_ranges(m) for p in range(a, b + 1)}
    imp = {q["word_key"]: q.get("importance_score") or 1 for q in pool}
    for j in jobs:
        on_site = len(site_pages & {p for a, b in j["payload"]["scope"]["ranges"] for p in range(a, b + 1)})
        j["payload"]["priority"] = [0 if on_site else 1, -on_site,
                                    -round(sum(imp.get(r["word_key"], 1) for r in j["payload"]["batch"]), 1)]
    jobs.sort(key=lambda j: j["payload"]["priority"])
    print(f"reader {reader}: {len(jobs)} jobs ({sum(j['payload']['priority'][0] == 0 for j in jobs)} on site lessons), {sum(len(j['payload']['batch']) for j in jobs)} questions, "
          f"{moved} moved to another lecture by the scope check, windows of at most {WINDOW} pages")
    if queue:
        q = queue_db.Queue()
        print("queued", q.add_jobs("pointers_one", jobs))
        q.db.commit()
        q.close()
    return jobs


if __name__ == "__main__":
    if sys.argv[1:2] == ["jobs"]:
        jobs(queue="--dry" not in sys.argv)
    else:
        run()

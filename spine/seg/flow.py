"""Phase 2 segmentation, in shadow (nothing the site or the Today screen reads is written).

    py -m spine seg prior <lecture>        the zero-token prior and the book slice
    py -m spine seg jobs [lecture ...]     one job folder per lecture and reader: jobs/sp_seg/<lecture>/<A|B>/
    py -m spine seg run [lecture ...]      Gemini web (4 Hydrogen) answers the unanswered job folders
    py -m spine seg dry [lecture ...]      what collect would decide, writing nothing
    py -m spine seg collect [lecture ...]  writes lectures/<id>/segments.jsonl for the accepted lectures
    py -m spine seg audit <lecture>        segments with times, book lines and handout pages vs the old placement
    py -m spine parity p2                  every segmented lecture against its old placement

Rebuilt 2026-11-18 (owner: the fleet-era flow was over-engineered; Gemini web reads, the fleet is retired, Haiku
reads no Arabic). Two readers per lecture (A, B: two separate Gemini chats). Each answers per paragraph
(`segment.PROMPT`). A lecture is accepted when both answers are whole and they agree on `ACCEPT` of the paragraphs;
the paragraphs they agree on carry reader A's lines, the rest are written as NONE flagged "disputed". A disputed
pair gets a third reader (C, same task); two of the three then decide each paragraph (`segment.agreed3`).
"""
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor

from spine import ROOT, graph_dir, now, read_json, read_jsonl, write_json, write_jsonl
from spine.seg import prior, scope, segment

JOBS = ROOT / "jobs" / "sp_seg"
READERS = ("A", "B")
THIRD = "C"                         # a third chat for a disputed pair: two of three decide each paragraph
MODEL = "hydrogen"                  # Gemini web, 4 Hydrogen (owner 2026-11-18)
WAIT = 900                          # seconds for one answer (a task is up to 170 KB)
TRIES = 2                           # chats per job when a reply has no answer line (an attachment can fail)
ACCEPT = 0.8                        # share of paragraphs the two readers must agree on
TALKY_NONE = 0.7                    # a talky lecture: both readers may call up to this share NONE ...
TALKY_MIN = 5                       # ... when they agree (ACCEPT) on at least this many paragraphs they did link
SHADOW = ("segments.jsonl",)        # derived files collect owns: removed when a lecture is not accepted (any more)
SHADOW_SPINE = ("links.jsonl", "ranges.json")    # compat shapes written from segments.jsonl (lectures/<id>/spine/)
CAPPED = {"until": 0.0}              # the latest "every account is capped" renewal seen (epoch seconds)
ANSWER_FILES = ("answer.txt", "reader.json", "browser.json", "reply_failed.txt", "result.json", "done", "prompt.md",
                "answer_rejected.txt")


def fingerprint(task, sents):
    """What an answer depends on: the task text and the sentence ids behind B1..Bk."""
    h = hashlib.sha256(task.encode("utf-8"))
    h.update(json.dumps([s["id"] for s in sents], ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()


def raw_of(lid):
    f = scope.home(lid) / "raw.txt"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def lectures_with_books(module="year2-cns", handout=False):
    """Lecture ids with a transcript whose doctor has a split book; with `handout`, also those whose doctor has none
    but whose lecture has a handout placement (read against the handout itself)."""
    books = scope.doctor_books(module)
    out = []
    recs = [(d, scope.home(lid)) for lid, d in scope._record_lessons().items()]
    for d, folder in [(read_json(f), f.parent) for f in sorted((ROOT / "lectures").glob("*/lecture.json"))] + recs:
        if d.get("module") != module or d.get("hold") or not (folder / "raw.txt").exists():
            continue
        if d.get("doctor") in books or (handout and (d.get("ranges") or d.get("covers"))):
            out.append(d["id"])
    return sorted(out)


def prepare(lid, module="year2-cns", cache=None):
    """{paras, scope, slice} of one lecture, or None (no transcript, no book or an empty slice)."""
    paras = prior.paragraphs(raw_of(lid))
    if not paras:
        return None
    sc = scope.pick(lid, module, paras, cache)
    if not sc:
        return None
    sl = sc["sents"][max(0, sc["lo"]):sc["hi"] + 1]
    return {"paras": paras, "scope": sc, "slice": sl} if sl else None


def job_dir(lid, reader):
    return JOBS / lid / reader


def make_jobs(lids, module="year2-cns", say=print):
    """Write task.txt + meta.json per lecture and reader. A job whose task did not change keeps its answer; a
    changed one loses it. Returns the number of job folders written."""
    cache, made = {}, 0
    for lid in lids:
        p = prepare(lid, module, cache)
        if not p:
            say(f"  {lid}: no transcript or no book")
            continue
        task = segment.render(p["paras"], p["slice"])
        fp = fingerprint(task, p["slice"])
        for r in READERS:
            d = job_dir(lid, r)
            if (read_json(d / "meta.json") or {}).get("fp") == fp:
                continue
            d.mkdir(parents=True, exist_ok=True)
            for f in ANSWER_FILES:
                (d / f).unlink(missing_ok=True)
            (d / "task.txt").write_text(task, encoding="utf-8")
            write_json(d / "meta.json", {"lecture": lid, "book": p["scope"]["book"], "lo": p["scope"]["lo"],
                                         "hi": p["scope"]["hi"], "paras": len(p["paras"]), "version": segment.VERSION,
                                         "at": now(), "fp": fp})
            made += 1
        say(f"  {lid}: {len(p['paras'])} paragraphs, book {p['scope']['book']} B{p['scope']['lo']}-B{p['scope']['hi']}"
            f" ({len(p['slice'])} lines), {len(task):,} characters")
    return made


def answered(d):
    return (d / "answer.txt").exists()


def answered_by(d):
    """Who wrote this job's answer: reader.json {"by"}, else browser.json = Gemini web, else the retired fleet."""
    by = (read_json(d / "reader.json") or {}).get("by")
    return str(by) if by else ("browser" if (d / "browser.json").exists() else "fleet")


def ask_gemini(d, ask=None, tries=TRIES):
    """Gemini web chats on d/task.txt (the prompt in the message, task.txt attached) until one reply has an answer
    line, at most `tries`. Answered: answer.txt, reader.json {"by": "gemini"}, browser.json. Every account at the
    model's usage cap: "capped" (nothing written; CAPPED["until"] = the first renewal). Else the last reply is kept in
    reply_failed.txt. `ask` is gemini_browser.ask (tests pass a fake)."""
    if ask is None:
        import functools
        import gemini_browser
        # Linking never runs on the free model (owner 2026-11-21: "We won't link with the light model"): a capped
        # account is skipped and the job waits for a renewal instead of answering with Flash-Lite.
        ask = functools.partial(gemini_browser.ask, fallback=False)
    task = (d / "task.txt").read_text(encoding="utf-8")
    head = task.partition("\nBOOK\n")[0] + "\nThe BOOK and TRANSCRIPT blocks are in the attached file task.txt."
    text, meta = None, {}
    for _ in range(max(1, tries)):
        text, meta = ask(head, model=MODEL, attach=[str(d / "task.txt")], wait=WAIT)
        if text is None and meta.get("until"):
            CAPPED["until"] = max(CAPPED["until"], float(meta["until"]))
            return "capped"
        err = str(meta.get("error") or "")
        if text is None and err.startswith("no account ready") and "capped" in err:
            # some accounts capped, the rest failed to open (a menu click timing out as the cap lands, 2026-11-21):
            # wait like a full cap, for the first renewal or 20 minutes
            CAPPED["until"] = max(CAPPED["until"], time.time() + 1200)
            return "capped"
        if text and any(segment.LINE.match(segment.norm(x)) for x in text.splitlines()):
            (d / "answer.txt").write_text(text, encoding="utf-8")
            (d / "reply_failed.txt").unlink(missing_ok=True)
            write_json(d / "browser.json", meta)
            write_json(d / "reader.json", {"by": "gemini", "model": MODEL})
            return "answered"
    (d / "reply_failed.txt").write_text(text or json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return "failed"


def todo(lids=None):
    """[(lecture, reader, job dir)] of every job with a task and no answer."""
    lids = lids or sorted(p.name for p in JOBS.glob("*") if p.is_dir())
    return [(lid, r, job_dir(lid, r)) for lid in lids for r in READERS + (THIRD,)
            if (job_dir(lid, r) / "task.txt").exists() and not answered(job_dir(lid, r))]


def run(lids=None, say=print, limit=None, workers=1, wait_caps=False, sleep=time.sleep):
    """Gemini web answers every unanswered job folder, `workers` chats at a time (at most 4, one per account).
    With `wait_caps`, a job that finds every account at its usage cap waits for the first renewal and is asked
    again; without it the job is left unanswered ("capped")."""
    jobs = todo(lids)
    jobs = jobs[:limit] if limit is not None else jobs      # --limit 0 asks nothing (it must never mean "all")
    stats = {}

    def work(job):
        while True:
            verdict = ask_gemini(job[2])
            if verdict != "capped" or not wait_caps:
                break
            secs = max(60, CAPPED["until"] - time.time() + 60)
            say(f"  {job[0]}/{job[1]}: every account capped; waiting {secs / 60:.0f} min")
            sleep(secs)
        say(f"  {job[0]}/{job[1]}: {verdict}")
        return verdict

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as pool:
        for v in pool.map(work, jobs):
            stats[v] = stats.get(v, 0) + 1
    return stats


def read_answer(d, n_paras, n_book, raw=False):
    """(per paragraph answer or None when unusable, problems); with `raw` the answer even when unusable."""
    if not answered(d):
        return None, ["no answer"]
    per, notes = segment.parse((d / "answer.txt").read_bytes().decode("utf-8", errors="replace"), n_paras, n_book)
    why = segment.problems(per, notes)
    return (per if raw or not why else None), why


def talky(a, b, why_a, why_b):
    """Both answers are whole but call much of the lecture NONE (a doctor who talks around the text: questions,
    stories, revision chat). Usable when NONE is their only problem, each reader's NONE share is at most TALKY_NONE,
    and on the paragraphs either of them linked they agree (ACCEPT) on at least TALKY_MIN."""
    if a is None or b is None or any(not x.startswith("NONE for") for x in why_a + why_b):
        return False
    n = len(a) or 1
    if max(sum(x is None for x in a), sum(x is None for x in b)) / n > TALKY_NONE:
        return False
    linked = [(x, y) for x, y in zip(a, b) if x is not None or y is not None]
    same = sum(segment.same(x, y) for x, y in linked)
    return same >= TALKY_MIN and same / len(linked) >= ACCEPT


def _judge_lecture(lid, module, cache):
    """(state dict, rows or None): one lecture judged against its current slice. Never writes."""
    p = prepare(lid, module, cache)
    if p is None:
        return {"state": "no source", "why": "no transcript, no book, or an empty slice"}, None
    fp = fingerprint(segment.render(p["paras"], p["slice"]), p["slice"])
    stale = [r for r in READERS if (read_json(job_dir(lid, r) / "meta.json") or {}).get("fp") != fp]
    if stale:
        return {"state": "stale", "stale_readers": stale,
                "why": f"the slice, placement, transcript or prompt changed: py -m spine seg jobs {lid}"}, None
    n, nb = len(p["paras"]), len(p["slice"])
    got = {r: read_answer(job_dir(lid, r), n, nb) for r in READERS}
    state = {"fp": fp[:12], "readers": {r: g[1][:4] for r, g in got.items()}}
    a, b = got["A"][0], got["B"][0]
    if a is None or b is None:
        if not all(answered(job_dir(lid, r)) for r in READERS):
            state["state"] = "waiting"
            return state, None
        raw = {r: read_answer(job_dir(lid, r), n, nb, raw=True) for r in READERS}
        if not talky(raw["A"][0], raw["B"][0], raw["A"][1], raw["B"][1]):
            state["state"] = "rejected"
            return state, None
        a, b = raw["A"][0], raw["B"][0]
        state["talky"] = True
    per, share = segment.agreed(a, b)
    state["agree"] = round(share, 3)
    readers = READERS
    if share < ACCEPT:
        state["state"] = "disputed"
        d3 = job_dir(lid, THIRD)
        if (read_json(d3 / "meta.json") or {}).get("fp") != fp:
            return state, None
        if not answered(d3):
            state["third"] = "waiting"
            return state, None
        c, why = read_answer(d3, n, nb)
        state["third"] = why[:4] or "answered"
        if c is None:
            return state, None
        per, share = segment.agreed3(a, b, c)
        state["agree3"] = round(share, 3)
        if share < ACCEPT:
            return state, None
        readers = READERS + (THIRD,)
    state["state"] = "accepted"
    if p["scope"].get("target") == "handout":           # read against the handout: B lines are handout sentences
        links = {x["id"]: [x["id"]] for x in p["slice"]}
    else:
        links = cache.setdefault(("edges", p["scope"]["book"]), scope.edges(module, p["scope"]["book"]))
    by = "+".join(f"{answered_by(job_dir(lid, r))}{r}" for r in readers)
    return state, segment.record(segment.segments(per), p["paras"], p["slice"], links, by, round(share, 3))


def ask_third(lid, state):
    """A disputed pair gets a third reader: job folder C with the same task (A's), once per task. Returns True when
    the folder was written now."""
    if state.get("state") != "disputed" or "third" in state:
        return False
    a, d = job_dir(lid, "A"), job_dir(lid, THIRD)
    d.mkdir(parents=True, exist_ok=True)
    for f in ANSWER_FILES:
        (d / f).unlink(missing_ok=True)
    (d / "task.txt").write_bytes((a / "task.txt").read_bytes())
    (d / "meta.json").write_bytes((a / "meta.json").read_bytes())
    return True


def slice_missed(state):
    """Both readers answered and both found (almost) nothing of the lecture in the slice."""
    readers = state.get("readers") or {}
    return state.get("state") == "rejected" and all(
        any(x.startswith("NONE for") for x in readers.get(r) or []) for r in READERS)


def widen(lid, state, module="year2-cns"):
    """One step up the slice ladder (`scope` docstring) after a rejection for a missed slice, once per answer pair.
    Returns the new step, or None (not a missed slice, already widened for this pair, or at the top: owner)."""
    if not slice_missed(state):
        return None
    f = JOBS / lid / "widen.json"
    w = read_json(f) or {}
    if w.get("after") == state.get("fp"):
        return None
    step = w.get("step", 0)
    if step >= scope.last_step(lid, module):
        if not w.get("owner"):
            write_json(f, {**w, "owner": True, "after": state.get("fp"), "at": now()})
        return None
    write_json(f, {"step": step + 1, "after": state.get("fp"), "at": now(),
                   "why": "; ".join(f"{r}: {', '.join(p)}" for r, p in state["readers"].items())})
    return step + 1


def retry(lid, state):
    """One reader's answer unusable while the other's is whole: that reader is asked once more in a fresh chat (its
    answer kept as answer_rejected.txt), once per answer pair. Returns the reader asked again, or None."""
    readers = state.get("readers") or {}
    bad = [r for r in READERS if readers.get(r)]
    if state.get("state") != "rejected" or len(bad) != 1:
        return None
    f = JOBS / lid / "retry.json"
    w = read_json(f) or {}
    if w.get("after") == state.get("fp"):
        return None
    d = job_dir(lid, bad[0])
    if not answered(d):
        return None
    (d / "answer_rejected.txt").write_bytes((d / "answer.txt").read_bytes())
    for x in ("answer.txt", "reader.json", "browser.json"):
        (d / x).unlink(missing_ok=True)
    write_json(f, {"reader": bad[0], "after": state.get("fp"), "at": now(), "why": "; ".join(readers[bad[0]])})
    return bad[0]


def for_owner(module="year2-cns"):
    """Lectures rejected at the top of the ladder: the readers found nothing even in the widest slice."""
    return sorted(f.parent.name for f in JOBS.glob("*/widen.json") if (read_json(f) or {}).get("owner")
                  and (read_json(f.parent / "state.json") or {}).get("state") != "accepted"
                  and (read_json(f.parent / "A" / "meta.json") or {}).get("lecture") is not None
                  and scope.lecture(f.parent.name).get("module", module) == module)


def _drop_shadow(lid):
    """Remove the derived files of a lecture that is not accepted now, so an old output cannot outlive it."""
    for f in SHADOW:
        (scope.home(lid) / f).unlink(missing_ok=True)
    for f in SHADOW_SPINE:
        (scope.home(lid) / "spine" / f).unlink(missing_ok=True)


def _lids(lids, module="year2-cns"):
    """The lectures asked for, else every lecture of this module with job folders (another module's jobs are
    never judged against this module's books: that would drop their segments)."""
    return lids or sorted(p.name for p in JOBS.glob("*") if p.is_dir() and (p / "A" / "meta.json").exists()
                          and scope.lecture(p.name).get("module", module) == module)


def _line(lid, state):
    return (f"  {lid}: {state['state']}" + (f" (agree {state['agree']:.0%}" + (", talky" if state.get("talky") else "")
                                             + (f", 2 of 3 agree {state['agree3']:.0%}" if "agree3" in state else "")
                                             + ")" if "agree" in state else "")
            + (f" {state['why']}" if state.get("why") else "")
            + "".join(f"; {r}: {'; '.join(p[:2])}" for r, p in (state.get("readers") or {}).items() if p))


def dry(lids=None, module="year2-cns", say=print):
    """What `collect` would decide for each lecture, writing nothing."""
    stats, cache = {}, {}
    for lid in _lids(lids, module):
        try:
            state, _ = _judge_lecture(lid, module, cache)
        except Exception as e:
            state = {"state": "error", "why": f"{type(e).__name__}: {e}"}
        stats[state["state"]] = stats.get(state["state"], 0) + 1
        say(_line(lid, state))
    return stats


def collect(lids=None, module="year2-cns", say=print):
    """Judge each lecture; write segments.jsonl (+ the compat shadow files) for the accepted ones, remove them for
    the rest. One lecture's error never stops the others."""
    stats, cache = {}, {}
    for lid in _lids(lids, module):
        try:
            state, rows = _judge_lecture(lid, module, cache)
        except Exception as e:
            state, rows = {"state": "error", "why": f"{type(e).__name__}: {e}"}, None
        try:
            if state["state"] == "accepted":
                write_jsonl(scope.home(lid) / "segments.jsonl", rows)
                from spine import compat
                compat.lecture_files(lid, module, cache.setdefault("handout", compat._handout(module)))
            else:
                _drop_shadow(lid)
                step = widen(lid, state, module)
                if step:
                    state["why"] = f"the slice missed: widened to step {step}, run py -m spine seg jobs {lid}"
                again = None if step else retry(lid, state)
                if again:
                    state["why"] = f"reader {again} asked again (its answer was unusable): py -m spine seg run {lid}"
                if ask_third(lid, state):
                    state["why"] = f"a third reader asked (C): py -m spine seg run {lid}"
        except Exception as e:
            _drop_shadow(lid)
            state = {"state": "error", "why": f"write: {type(e).__name__}: {e}"}
        write_json(JOBS / lid / "state.json", {"lecture": lid, "at": now(), **state})
        stats[state["state"]] = stats.get(state["state"], 0) + 1
        say(_line(lid, state))
    return stats


# --- audit and parity ------------------------------------------------------------------------------------------
def placement_pages(lec):
    pages = set()
    for r in lec.get("ranges") or []:
        a, b = (r.get("pages") or [None, None])[:2]
        if a is not None:
            pages |= set(range(a, (b or a) + 1))
    return pages


def page_of(hid):
    from spine import ids
    return ids.parse(hid)["page"]


def audit(lid, out=print):
    rows = read_jsonl(scope.home(lid) / "segments.jsonl")
    if not rows:
        st = read_json(JOBS / lid / "state.json") or {}
        out(f"{lid}: no segments ({st.get('state', 'no job')})")
        return None
    lec = scope.lecture(lid)
    want = placement_pages(lec)
    from spine import ids
    mapped = [r for r in rows if r.get("book")]
    spaces = {ids.parse(r["book"][0]).get("space") for r in mapped}
    if spaces == {"handout"}:                                  # read against the handout: no book to name
        sents = {x["id"]: x for x in read_jsonl(graph_dir(lec.get("module", "year2-cns")) / "sentences.jsonl")}
    else:
        book = ids.parse(mapped[0]["book"][0])["book"] if mapped else None
        sents = {s["id"]: s for s in scope.book_sentences(lec.get("module", "year2-cns"), book)} if book else {}
    inside = total = 0
    for r in rows:
        t = f"{prior.stamp(r['start'])}-{prior.stamp(r['end']) if r['end'] is not None else 'end'}"
        if not r.get("book"):
            out(f"  {r['n']:>3} P{r['p'][0]}-P{r['p'][1]} {t}  NONE" + (f"  [{r['flag']}]" if r.get("flag") else ""))
            continue
        pages = sorted({page_of(h) for h in r.get("handout") or []})
        ok = sum(p in want for p in pages)
        inside, total = inside + ok, total + len(pages)
        first = sents.get(r["book"][0], {})
        out(f"  {r['n']:>3} P{r['p'][0]}-P{r['p'][1]} {t}  book p{first.get('page', '?')} "
            f"'{(first.get('text') or '')[:50]}' -> handout pages {pages[:6]}{'...' if len(pages) > 6 else ''}")
    share = inside / total if total else None
    out(f"{lid}: {len(rows)} segments; handout pages inside the old placement {sorted(want)[:1]}..{sorted(want)[-1:]}: "
        + (f"{share:.0%}" if share is not None else "n/a"))
    return share

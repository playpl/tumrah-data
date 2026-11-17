"""Phase 2 segmentation, end to end, in shadow (nothing the site or the Today screen reads is written).

    py -m spine seg prior <lecture>            the zero-token prior and the book slice
    py -m spine seg jobs [lecture ...]         one job folder per lecture and reader: jobs/sp_seg/<lecture>/<reader>/
    py -m spine seg run [--via fleet|browser]  readers answer (fleet: the 4 accounts; browser: Gemini web profiles)
    py -m spine seg collect                    parse, check, repair, agree; writes lectures/<id>/segments.jsonl
    py -m spine seg dry                        the same decisions as collect, writing nothing
    py -m spine seg audit <lecture>            segments with times, book lines and handout pages, against the
                                               lecture's old placement
    py -m spine parity p2                      every segmented lecture against its old placement

Two readers per lecture (A, B on different accounts). Accepted when both answers are usable (after repair under
20% of paragraphs offending) and agree on 90% of paragraphs (within 5 book lines); then reader A's repaired
segments are written with conf = the agreement. Else the lecture is `disputed` and its runs are listed.
"""
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from spine import ROOT, graph_dir, now, read_json, read_jsonl, write_json, write_jsonl
from spine.seg import prior, scope, segment

JOBS = ROOT / "jobs" / "sp_seg"
FLEET = Path(r"C:\Users\Ahmed\agy-fleet\fleet.py")
ACCOUNTS = ["zero", "work", "personal", "other"]
READERS = {"A": 0, "B": 1}          # reader -> account offset, so A and B of one lecture never share an account
MAX_OFFEND = segment.MAX_OFFEND
SHADOW = ("segments.jsonl",)        # derived files collect owns: removed when a lecture is not accepted (any more)
SHADOW_SPINE = ("links.jsonl", "ranges.json")    # compat shapes written from segments.jsonl (lectures/<id>/spine/)


def fingerprint(task, sents):
    """What a reader's answer depends on: the exact task text (prompt, BOOK numbering, TRANSCRIPT with stamps) and
    the sentence ids behind B1..Bk (record() writes those ids). A job is only judged against the fingerprint it was
    written with; a moved placement, a re-split book or a new transcript makes the job stale, never silently reused."""
    h = hashlib.sha256()
    h.update(task.encode("utf-8"))
    h.update(json.dumps([s["id"] for s in sents], ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()

FLEET_NOTE = """The task is in the file task.txt in this folder (prompt, BOOK block, TRANSCRIPT block).
Read all of task.txt, do what it says, and give your answer as your final message: the segment lines only.
Do not write any file. Do not run any program.
"""


def raw_of(lid):
    f = ROOT / "lectures" / lid / "raw.txt"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def lectures_with_books(module="year2-cns", handout=False):
    """Lecture ids that have a transcript and whose doctor has a split book; with `handout`, also those whose doctor
    has none but whose lecture has a handout placement (they are read against the handout itself)."""
    books = scope.doctor_books(module)
    out = []
    for f in sorted((ROOT / "lectures").glob("*/lecture.json")):
        d = read_json(f)
        if d.get("module") != module or d.get("hold") or not (f.parent / "raw.txt").exists():
            continue
        if d.get("doctor") in books or (handout and (d.get("ranges") or d.get("covers"))):
            out.append(d["id"])
    return out


def prepare(lid, module="year2-cns", cache=None):
    """{paras, scope, slice, prior} of one lecture, or None (no transcript or no book)."""
    paras = prior.paragraphs(raw_of(lid))
    if not paras:
        return None
    sc = scope.pick(lid, module, paras, cache)
    if not sc:
        return None
    sl = sc["sents"][max(0, sc["lo"]):sc["hi"] + 1]
    if not sl:                                         # an empty book or slice has nothing to read against
        return None
    return {"paras": paras, "scope": sc, "slice": sl, "prior": prior.prior(paras, sl)}


def job_dir(lid, reader):
    return JOBS / lid / reader


def make_jobs(lids, module="year2-cns", readers=("A", "B"), say=print):
    cache, made = {}, 0
    for lid in lids:
        p = prepare(lid, module, cache)
        if not p:
            say(f"  {lid}: no transcript or no book")
            continue
        task = segment.render(p["paras"], p["slice"])
        meta = {"lecture": lid, "book": p["scope"]["book"], "lo": p["scope"]["lo"], "hi": p["scope"]["hi"],
                "how": p["scope"]["how"], "paras": len(p["paras"]), "book_lines": len(p["slice"]),
                "version": segment.VERSION, "at": now(), "fp": fingerprint(task, p["slice"])}
        for r in readers:
            d = job_dir(lid, r)
            old = read_json(d / "meta.json") or {}
            same = (d / "task.txt").exists() and old.get("version") == meta["version"] \
                and (d / "task.txt").read_text(encoding="utf-8") == task \
                and old.get("fp", meta["fp"]) == meta["fp"]
            if same:                                         # same task text and slice: keep its answer
                if "fp" not in old:
                    write_json(d / "meta.json", dict(old, fp=meta["fp"]))
                continue
            d.mkdir(parents=True, exist_ok=True)
            for f in ("result.json", "answer.txt", "done", "browser.json", "reader.json"):
                (d / f).unlink(missing_ok=True)
            (d / "task.txt").write_text(task, encoding="utf-8")
            (d / "prompt.md").write_text(FLEET_NOTE, encoding="utf-8")
            write_json(d / "meta.json", meta)
            made += 1
        say(f"  {lid}: {meta['paras']} paragraphs, book {meta['book']} B{meta['lo']}-B{meta['hi']} "
            f"({meta['book_lines']} lines, {meta['how']}), {len(task):,} characters")
    return made


def answered(d):
    return (d / "answer.txt").exists()


def answered_by(d):
    """Who wrote this job's answer.txt, for the `by` field of segments.jsonl. Any runner may write reader.json
    {"by": "<reader>"} next to answer.txt (a Haiku runner must); else browser.json means Gemini web; else the fleet."""
    by = (read_json(d / "reader.json") or {}).get("by")
    if by:
        return str(by)
    return "browser" if (d / "browser.json").exists() else "fleet"


def ask_fleet(d, account):
    subprocess.run(["py", str(FLEET), "run", "-a", account, "--cwd", str(d), "-f", "prompt.md", "--out", "result.json",
                    "--timeout", "25"], capture_output=True, text=True, cwd=d)
    r = read_json(d / "result.json") or {}
    if r.get("status") == "SUCCESS" and (r.get("response") or "").strip():
        (d / "answer.txt").write_text(r["response"], encoding="utf-8")
        return "answered"
    return "quota" if r.get("failure") == "quota" else "failed"


def ask_browser(d, account=None, model="flash-lite"):
    import gemini_browser
    task = (d / "task.txt").read_text(encoding="utf-8")
    head, _, body = task.partition("\nBOOK\n")
    text, meta = gemini_browser.ask(head + "\nThe BOOK and TRANSCRIPT blocks are in the attached file task.txt.",
                                    model=model, attach=[str(d / "task.txt")], wait=600, account=account)
    if text and segment.parse(text)[0]:
        (d / "answer.txt").write_text(text, encoding="utf-8")
        write_json(d / "browser.json", meta)
        return "answered"
    return "failed"


def run(lids=None, via="fleet", accounts=None, say=print, limit=None):
    """Answer every unanswered job folder. Fleet: one job per account at a time, A and B on different accounts."""
    accounts = list(accounts or ACCOUNTS)
    todo = []
    for lid in lids or sorted(p.name for p in JOBS.glob("*") if p.is_dir()):
        for r in READERS:
            d = job_dir(lid, r)
            if (d / "task.txt").exists() and not answered(d):
                todo.append((lid, r, d))
    todo = todo[:limit] if limit is not None else todo      # --limit 0 asks nothing (it must never mean "all")
    stats, resting = {}, set()

    def work(k_job):
        k, (lid, r, d) = k_job
        if via == "browser":
            verdict = ask_browser(d)
        else:
            verdict = "failed"
            for attempt in range(len(accounts)):
                acc = accounts[(k + READERS[r] + attempt) % len(accounts)]
                if acc in resting:
                    continue
                verdict = ask_fleet(d, acc)
                if verdict == "quota":
                    resting.add(acc)
                    continue
                if verdict == "answered":
                    break
        say(f"  {lid}/{r}: {verdict}")
        return verdict

    with ThreadPoolExecutor(max_workers=1 if via == "browser" else len(accounts)) as pool:
        for v in pool.map(work, enumerate(todo)):
            stats[v] = stats.get(v, 0) + 1
    stats["accounts out of quota"] = len(resting)
    return stats


def judge(d, n_paras, n_book):
    """(repaired segments or None, problems, offending share) of one reader's answer."""
    if not answered(d):
        return None, ["no answer"], 1.0
    segs, bad = segment.parse((d / "answer.txt").read_bytes().decode("utf-8", errors="replace"))
    return segment.judge_segs(segs, n_paras, n_book, bad)


def _drop_shadow(lid):
    """Remove the derived files of a lecture that is not accepted now, so an old accepted output cannot outlive
    the judgement that made it (both the segments file and the compat shapes written from it)."""
    for f in SHADOW:
        (ROOT / "lectures" / lid / f).unlink(missing_ok=True)
    for f in SHADOW_SPINE:
        (ROOT / "lectures" / lid / "spine" / f).unlink(missing_ok=True)


def _stale(lid, task, fp):
    """Readers whose job was written for a different task or slice than the one collect would judge now."""
    out = []
    for r in READERS:
        d = job_dir(lid, r)
        m = read_json(d / "meta.json") or {}
        if not (d / "task.txt").exists():
            out.append(r)
        elif m.get("fp"):
            if m["fp"] != fp:
                out.append(r)
        elif (d / "task.txt").read_text(encoding="utf-8") != task:      # a job from before fingerprints
            out.append(r)
    return out


def _judge_lecture(lid, module, cache):
    """(state dict, rows or None): one lecture judged against its current slice. Never writes."""
    p = prepare(lid, module, cache)
    if p is None:
        return {"state": "no source", "why": "no transcript, no book, or an empty slice"}, None
    n, nb = len(p["paras"]), len(p["slice"])
    task = segment.render(p["paras"], p["slice"])
    fp = fingerprint(task, p["slice"])
    stale = _stale(lid, task, fp)
    if stale:
        return {"state": "stale", "stale_readers": stale,
                "why": "the book slice, placement or transcript changed since these jobs were written: "
                       f"py -m spine seg jobs {lid}"}, None
    got = {r: judge(job_dir(lid, r), n, nb) for r in READERS}
    state = {"fp": fp[:12], "readers": {r: {"usable": g[0] is not None, "problems": g[1][:6],
                                            "offending": round(g[2], 3)} for r, g in got.items()}}
    a, b = got["A"][0], got["B"][0]
    rows = None
    if a is not None and b is not None:
        share = segment.agree(a, b, n)
        state["agree"] = round(share, 3)
        if share >= segment.AGREE_SHARE:
            state["state"] = "accepted"
            if p["scope"].get("target") == "handout":   # read against the handout: B lines are handout sentences
                links = {x["id"]: [x["id"]] for x in p["slice"]}
            else:
                links = cache.setdefault(("edges", p["scope"]["book"]), scope.edges(module, p["scope"]["book"]))
            by = "+".join(f"{answered_by(job_dir(lid, r))}{r}" for r in READERS)    # "fleetA+fleetB"
            rows = segment.record(a, p["paras"], p["slice"], links, by, round(share, 3))
        else:
            state["state"] = "disputed"
            state["runs"] = segment.disputed(a, b, n)
    else:
        state["state"] = "waiting" if not all(answered(job_dir(lid, r)) for r in READERS) else "rejected"
    return state, rows


def dry(lids=None, module="year2-cns", say=print):
    """What `collect` would decide for each job folder, writing nothing (no segments, no shadow files, no state)."""
    stats, cache = {}, {}
    for lid in lids or sorted(p.name for p in JOBS.glob("*") if p.is_dir()):
        if not read_json(job_dir(lid, "A") / "meta.json"):
            continue
        try:
            state, _ = _judge_lecture(lid, module, cache)
        except Exception as e:
            state = {"state": "error", "why": f"{type(e).__name__}: {e}"}
        stats[state["state"]] = stats.get(state["state"], 0) + 1
        say(f"  {lid}: {state['state']}" + (f" (agree {state['agree']:.0%})" if "agree" in state else "")
            + (f" {state['why']}" if state.get("why") else ""))
    return stats


def collect(lids=None, module="year2-cns", say=print):
    """Judge each lecture's answers; write segments.jsonl for the accepted ones. Returns counts.

    One lecture's failure never stops the others: it is recorded as state "error" in its state.json. A lecture that
    is not accepted loses its shadow files (see `_drop_shadow`)."""
    stats, cache = {}, {}
    for lid in lids or sorted(p.name for p in JOBS.glob("*") if p.is_dir()):
        if not read_json(job_dir(lid, "A") / "meta.json"):
            continue
        try:
            state, rows = _judge_lecture(lid, module, cache)
        except Exception as e:                               # recorded, visible, and the batch goes on
            state, rows = {"state": "error", "why": f"{type(e).__name__}: {e}"}, None
        state = {"lecture": lid, "at": now(), **state}
        try:
            if state["state"] == "accepted":
                write_jsonl(ROOT / "lectures" / lid / "segments.jsonl", rows)
                from spine import compat             # shadow legacy files: lectures/<id>/spine/
                compat.lecture_files(lid, module, cache.setdefault("handout", compat._handout(module)))
            else:
                _drop_shadow(lid)
        except Exception as e:                       # a write that fails is an error on this lecture, not a crash
            _drop_shadow(lid)
            state = {"lecture": lid, "at": now(), "state": "error", "why": f"write: {type(e).__name__}: {e}"}
        write_json(JOBS / lid / "state.json", state)
        stats[state["state"]] = stats.get(state["state"], 0) + 1
        readers = state.get("readers") or {}
        notes = "".join(f"; {r}: {'; '.join(g['problems'][:2])}" for r, g in readers.items() if g["problems"])
        say(f"  {lid}: {state['state']}" + (f" (agree {state['agree']:.0%})" if "agree" in state else "")
            + (f" {state['why']}" if state.get("why") else "") + notes)
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
    rows = read_jsonl(ROOT / "lectures" / lid / "segments.jsonl")
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

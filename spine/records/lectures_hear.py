"""Year 2 transcripts on Gemini web, 4 Hydrogen (owner 2026-11-18: the fleet is retired; Arabic is Gemini's work).

    py -m spine records hear2 [lecture ...] [--limit N] [--dry]

A lecture with no raw.txt is heard piece by piece, the same way as the year 1 records (`transcribe.hear` with
`gemini_run.PIECE_PROMPT`, the 450 characters a minute floor), on the owner's four signed-in Chrome profiles:

    lectures/<id>/audio.ogg              the lecture's audio (old PC downloads), else
    lectures/<id>/hear.16k.ogg           the runner's 16 kbps copy (lecture.json source.cloud.hear_key; a few MB)
    lectures/<id>/pieces/cNN.ogg|txt     5-minute pieces and what was heard (the layout flows/lecture.py used)
    lectures/<id>/raw.txt                written once, when every piece has its text and the whole passes the check

A piece that fails goes back for another account; an account at its usage cap is skipped. Nothing is uploaded.
"""
import json

from spine import ROOT

MODEL = "hydrogen"
LECTURES = ROOT / "lectures"


def _meta(lid):
    try:
        return json.loads((LECTURES / lid / "lecture.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def hear_key(meta):
    c = (meta.get("source") or {}).get("cloud")
    return c.get("hear_key") if isinstance(c, dict) else None


def todo(module="year2-cns", lids=None):
    """Lecture ids with no raw.txt and some audio to hear (local audio.ogg or a cloud hear key)."""
    out = []
    for f in sorted(LECTURES.glob("*/lecture.json")):
        lid = f.parent.name
        if lids and lid not in lids:
            continue
        m = _meta(lid)
        if m.get("module") != module or m.get("hold") or (f.parent / "raw.txt").exists():
            continue
        if (f.parent / "audio.ogg").exists() or (f.parent / "hear.16k.ogg").exists() or hear_key(m):
            out.append(lid)
    return out


def audio(lid, get=None):
    """The file to hear, fetched from the bucket when only the runner's small copy exists. None when absent."""
    d = LECTURES / lid
    for name in ("audio.ogg", "hear.16k.ogg"):
        if (d / name).exists():
            return d / name
    key = hear_key(_meta(lid))
    if not key:
        return None
    if get is None:
        from cloud import r2
        get = r2.get_file
    return d / "hear.16k.ogg" if get(key, d / "hear.16k.ogg") else None


def pieces(lid, get=None):
    """[cNN.ogg] of the lecture, cut once."""
    import checks
    import lectures
    from flows.lecture import pieces_dir
    d = pieces_dir(lid)
    have = sorted(d.glob("c[0-9][0-9].ogg"))
    if have:
        return have
    src = audio(lid, get)
    if src is None:
        return []
    n = lectures.chunks(src, d, checks.CHUNK_SECONDS)
    return [d / f"c{i:02d}.ogg" for i in range(n)]


def finish(lid):
    """raw.txt once every piece has text and the whole passes the transcript check. (written, errors)."""
    from flows.lecture import merge_pieces
    raw = LECTURES / lid / "raw.txt"
    if raw.exists():
        return False, []
    text, errors = merge_pieces(lid)
    if text is None or errors:
        return False, errors
    raw.write_text(text, encoding="utf-8")
    return True, []


def plan(lids=None, module="year2-cns", say=print, get=None):
    """[(lecture, piece)] still to hear; lectures whose pieces are all heard are finished here."""
    jobs = []
    for lid in todo(module, lids):
        ps = pieces(lid, get)
        if not ps:
            say(f"  {lid}: no audio")
            continue
        left = [p for p in ps if not p.with_suffix(".txt").exists()]
        if not left:
            done, errors = finish(lid)
            say(f"  {lid}: " + ("transcript ready" if done else f"all pieces heard, check: {'; '.join(errors)[:150]}"))
            continue
        jobs += [(lid, p) for p in left]
        say(f"  {lid}: {len(left)} of {len(ps)} pieces to hear")
    return jobs


def run(lids=None, module="year2-cns", limit=None, say=print, via="browser", accounts=None, runner=None):
    """Hear the pieces on the four accounts at once; each lecture's raw.txt is written when its last piece is in.
    `via` "fleet": the Antigravity fleet (owner 2026-11-21), one worker per account; a piece passes
    transcribe.check_piece (length, loop) or waits; heard pieces get a cNN.fleet marker for a later re-hearing."""
    from spine.records import transcribe
    jobs = plan(lids, module, say)
    jobs = jobs[:limit] if limit is not None else jobs
    say(f"  {len(jobs)} pieces to hear now")
    if not jobs:
        return {}
    if via == "fleet":
        return _run_fleet(jobs, accounts or transcribe.ACCOUNTS, runner, say)
    import gemini_browser

    def one(pw, n, job):              # raising hands the piece to another account (browser.parallel)
        lid, p = job
        if transcribe.STOP.exists():
            return
        def asker(prompt, model, attach, timeout):   # a capped account answers with its free model (owner 11-20)
            text, used = gemini_browser.ask_on_fallback(pw, n, prompt.read_text(encoding="utf-8"), [attach[0]], timeout, model)
            return text, {"account": n, "model": used}
        if transcribe.hear(p, model=MODEL, tries=1, ask=asker, say=say) is None:
            raise RuntimeError("the answer failed the piece check")
        if not any(not q.with_suffix(".txt").exists() for q in p.parent.glob("c[0-9][0-9].ogg")):
            done, errors = finish(lid)
            say(f"  {lid}: " + ("transcript ready" if done else f"check: {'; '.join(errors)[:150]}"))

    return gemini_browser.driver().parallel(jobs, one, lambda j: f"{j[0]}/{j[1].stem}")


def _run_fleet(jobs, accounts, runner, say):
    """Fleet workers take pieces from one queue; a piece that fails twice waits for the next run."""
    import queue
    import threading
    from spine.records import transcribe
    work, lock, out = queue.Queue(), threading.Lock(), {"heard": 0, "failed": 0, "ready": []}
    for j in jobs:
        work.put((j, 0))

    def worker(account):
        while not transcribe.STOP.exists():
            try:
                (lid, p), tries = work.get_nowait()
            except queue.Empty:
                return
            if p.with_suffix(".txt").exists():
                continue
            if transcribe.hear_fleet(p, account, runner=runner, say=say) is None:
                if tries + 1 < 2:
                    work.put(((lid, p), tries + 1))
                else:
                    with lock:
                        out["failed"] += 1
                continue
            with lock:
                out["heard"] += 1
                if not any(not q.with_suffix(".txt").exists() for q in p.parent.glob("c[0-9][0-9].ogg")):
                    done, errors = finish(lid)
                    if done:
                        mark_fleet(lid)
                        out["ready"].append(lid)
                    say(f"  {lid}: " + ("transcript ready (fleet)" if done else f"check: {'; '.join(errors)[:150]}"))

    threads = [threading.Thread(target=worker, args=(a,)) for a in accounts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def mark_fleet(lid):
    """lecture.json source.heard_by_fleet = pieces heard by the fleet (re-hear on Hydrogen later)."""
    from flows.lecture import pieces_dir
    n = len(list(pieces_dir(lid).glob("c[0-9][0-9].fleet")))
    m = _meta(lid)
    if n and m:
        import lectures
        m.setdefault("source", {})["heard_by_fleet"] = n
        lectures.save(m)

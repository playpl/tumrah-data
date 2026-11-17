"""Transcripts of the records machine's recordings: 5-minute pieces heard on Flash-Lite (the owner's transcription
model), outside queue.db so the year 2 flow never sees a year 1 job. Two ways to hear a piece:

    --via fleet    (default, owner 2026-11-17) the Antigravity fleet, one worker per account, model `lite`, the year 2
                   piece prompt and check (flows/lecture.py PIECE_PROMPT, PieceFlow.check); job folders pieces/jobs/cNN/
    --via gemini   Gemini web: `gweb wake` first, as tumrah-book's image step does (exit 3 = login dead: stop), then
                   `gemini_run.ask` with `gemini_run.PIECE_PROMPT` / `piece_text` and the 450 characters a minute floor

    modules/<m>/records/<id>/pieces/c00.ogg ...   5-minute pieces, mono Opus 16 kbps (lectures.chunks)
    modules/<m>/records/<id>/pieces/c00.txt ...   what was heard, [mm:ss] inside the piece; a stopped run keeps these
    modules/<m>/records/<id>/raw.txt              all pieces joined, times shifted to the whole recording

A record is done when every piece has its text; then raw.txt is written and the state log gets transcript "gemini".
A YouTube record with captions already has raw.txt (transcript "youtube") and is never heard again.
"""
import json
import queue
import re
import shutil
import subprocess
import sys
import threading

from spine import ROOT
from spine.records import machine

PIECE = 300
STAMP = re.compile(r"^\[(\d+):(\d{2})\]", re.M)
STOP = ROOT / "jobs" / "gemini.stop"
FLEET = [sys.executable, r"C:\Users\Ahmed\agy-fleet\fleet.py"]
ACCOUNTS = ("zero", "work", "personal", "other")
GWEB = r"C:\Users\Ahmed\gemini-web\gweb.cmd"


def audio_of(rec, st):
    """What is heard: the compressed recording, or a YouTube record's audio. None when not there yet."""
    if rec["source"] == "telegram" and machine.reached(st, rec["id"], "compressed"):
        f = machine.compressed_path(rec)
        return f if f.exists() else None
    if rec["source"] == "youtube":
        row = st.get(rec["id"]) or {}
        if row.get("transcript") == "youtube" or not row.get("file"):
            return None
        f = ROOT / row["file"]
        return f if f.exists() else None
    return None


def todo(recs, st):
    return [r for r in recs if not (st.get(r["id"]) or {}).get("transcript") and audio_of(r, st)]


def shift(text, offset):
    """[mm:ss] stamps of one piece moved by `offset` seconds (minutes may pass 59, as in lectures.vtt_to_raw)."""
    def one(m):
        t = int(m.group(1)) * 60 + int(m.group(2)) + offset
        return f"[{t // 60:02d}:{t % 60:02d}]"
    return STAMP.sub(one, text)


def join(piece_texts, seconds=PIECE):
    """raw.txt from the pieces' texts in order (a silent piece is '')."""
    out = [shift(t, i * seconds).rstrip("\n") for i, t in enumerate(piece_texts)]
    return "\n".join(t for t in out if t) + "\n"


def cut(rec, audio):
    import lectures
    d = machine.record_dir(rec) / "pieces"
    n = lectures.chunks(audio, d, PIECE)
    return [d / f"c{i:02d}.ogg" for i in range(n)]


def hear(piece, model="flash-lite", tries=3, ask=None, say=print):
    """Text of one piece, or None after `tries` bad answers. Written next to the piece."""
    import checks
    import gemini_run
    import lectures
    ask = ask or gemini_run.ask
    prompt = piece.with_name("prompt.txt")
    if not prompt.exists():
        prompt.write_text(gemini_run.PIECE_PROMPT, encoding="utf-8")
    seconds = lectures.duration(piece)
    for t in range(1, tries + 1):
        answer, meta = ask(prompt, model, [piece], timeout=900)
        if answer is None:
            say(f"    {piece.parent.parent.name}/{piece.stem}: try {t}: {meta.get('error')}"[:200])
            if "no account ready" in str(meta.get("error")):
                return None
            continue
        text = gemini_run.piece_text(answer, seconds)
        rate = sum(len(b) for _, b in checks.paragraphs(text)) / max(seconds / 60, 1)
        if seconds > 90 and rate < gemini_run.MIN_CHARS_PER_MIN:
            say(f"    {piece.parent.parent.name}/{piece.stem}: try {t}: condensed ({rate:.0f} chars/min)")
            continue
        piece.with_suffix(".txt").write_text(text, encoding="utf-8")
        return text
    return None


def check_piece(text, seconds):
    """The year 2 piece check (PieceFlow.check): [] when the text is a whole transcript of `seconds`."""
    import checks
    if not text.strip():
        return []                      # a silent piece
    errors = checks.check_transcript(text, seconds, end_slack=90)
    return [e for e in errors if "before the end" not in e or seconds > 120]


def hear_fleet(piece, account, runner=None, say=print):
    """One fleet worker hears one piece. Text, or None (the piece stays for the next run)."""
    import lectures
    from flows.lecture import PIECE_PROMPT
    d = piece.parent / "jobs" / piece.stem
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(piece, d / "piece.ogg")
    (d / "piece.txt").unlink(missing_ok=True)
    (d / "prompt.md").write_text(PIECE_PROMPT.format(minutes=PIECE // 60), encoding="utf-8")
    cmd = FLEET + ["run", "-a", account, "--cwd", str(d), "-f", str(d / "prompt.md"), "--out", str(d / "result.json"),
                   "--timeout", "20", "--model", "lite"]
    (runner or (lambda c: subprocess.run(c, cwd=d, capture_output=True, text=True, encoding="utf-8", errors="replace")))(cmd)
    name = f"{piece.parent.parent.name}/{piece.stem}"
    if not (d / "piece.txt").exists():
        res = read_result(d / "result.json")
        say(f"    {name} on {account}: no piece.txt ({res.get('error') or res.get('status') or 'no result'})"[:200])
        return None
    text = (d / "piece.txt").read_text(encoding="utf-8")
    errors = check_piece(text, lectures.duration(piece))
    if errors:
        say(f"    {name} on {account}: check: {'; '.join(errors)[:150]}")
        return None
    piece.with_suffix(".txt").write_text(text, encoding="utf-8")
    return text


def read_result(f):
    try:
        out = json.loads(f.read_text(encoding="utf-8"))
        return out if isinstance(out, dict) else {}
    except (OSError, ValueError):
        return {}


def wake():
    """`gweb wake` (tumrah-book's way in): (ok, last line). Exit 3 = the login is dead and waits for the owner."""
    try:
        r = subprocess.run([GWEB, "wake"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    except (subprocess.TimeoutExpired, OSError) as e:
        return False, str(e)
    lines = (r.stdout + r.stderr).strip().splitlines() or ["gweb wake: no output"]
    return r.returncode == 0, lines[-1]


def finish(rec, pieces):
    """raw.txt once every piece has its text. True when written."""
    texts = [p.with_suffix(".txt") for p in pieces]
    if not all(t.exists() for t in texts):
        return False
    raw = join([t.read_text(encoding="utf-8") for t in texts])
    (machine.record_dir(rec) / "raw.txt").write_text(raw, encoding="utf-8")
    machine.mark(rec["module"], rec["id"], transcript="gemini", pieces=len(pieces))
    return True


def run(recs, limit=None, workers=4, model="flash-lite", say=print, ask=None, via="fleet", accounts=ACCOUNTS,
        runner=None):
    """Hears up to `limit` pieces, record by record; reports each record that is finished. Fleet: one worker per
    account, each takes the next piece; a piece that fails twice waits for the next run."""
    if not recs:
        return 0
    if via == "gemini" and ask is None:
        ok, line = wake()
        if not ok:
            say(f"  Gemini web is not usable: {line}")
            return 0
    st = machine.states(recs[0]["module"])
    jobs, by_rec = [], {}
    for r in todo(recs, st):
        pieces = cut(r, audio_of(r, st))
        by_rec[r["id"]] = (r, pieces)
        if finish(r, pieces):
            say(f"  {r['id']}: transcript ready ({len(pieces)} pieces)")
            continue
        jobs += [(r, p) for p in pieces if not p.with_suffix(".txt").exists()]
    jobs = jobs[:limit]
    say(f"  {len(jobs)} pieces to hear now ({len(by_rec)} records waiting)")
    lock, heard, work = threading.Lock(), [0], queue.Queue()
    for j in jobs:
        work.put((j, 0))

    def worker(account):
        while not STOP.exists():
            try:
                (r, p), tries = work.get_nowait()
            except queue.Empty:
                return
            text = hear_fleet(p, account, runner=runner, say=say) if via == "fleet" else hear(p, model, ask=ask, say=say)
            if text is None:
                if tries + 1 < 2:
                    work.put(((r, p), tries + 1))
                continue
            with lock:
                heard[0] += 1
                rec, pieces = by_rec[r["id"]]
                if finish(rec, pieces):
                    say(f"  {r['id']}: transcript ready ({len(pieces)} pieces)")
    names = list(accounts) if via == "fleet" else [None] * workers
    threads = [threading.Thread(target=worker, args=(a,)) for a in names]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return heard[0]

"""Uploads every recording in modules/<module>/site/media.json to the site's private storage (uploadLessonMedia.ts).

    py upload_media.py [module]      a key already holding a file of the same size is skipped by the uploader itself

Audio is compressed before upload (owner, 2026-11-11): speech needs little, so every audio recording (also an audio row
whose source is a video file) becomes AAC mono 48 kbps `.m4a` (about 21 MB an hour, plays in every browser), cached in
modules/<module>/site/compressed/ and uploaded under its own key (`recording.48k.m4a`); media.json then points at that
key, so `site_lessons.py write` sends students the small file. Video rows are uploaded as they are.

Recordings already uploaded under their own keys (`site_lessons.MEDIA`) are not sent again. Prints one line per file.

Automatic (owner, 2026-11-12): `update_data.py` starts this in the background (`start_background`), then rewrites the site
files again. A row is marked `uploaded_size` (the source file's size) when its upload succeeds and is not tried again until
the file changes. One run at a time (`upload_media.lock`); the media.json it writes at the end is merged into the file as
it is then, so rows added while it ran are kept.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import site_lessons

ROOT = Path(__file__).resolve().parent
WORKERS = 3  # 6 parallel streams on this link broke most uploads (2026-11-11)
TRIES = 4
BACKEND = Path(r"C:\Users\Ahmed\Desktop\tumrah\backend")
AUDIO_KBPS = 48
SUFFIX = f".{AUDIO_KBPS}k.m4a"


def compressed_key(key):
    """lectures/year2-cns/cns-021/recording.mp3 -> lectures/year2-cns/cns-021/recording.48k.m4a (idempotent)."""
    if key.endswith(SUFFIX):
        return key
    head, _, name = key.rpartition("/")
    return f"{head}/{name.split('.')[0]}{SUFFIX}"


def compress(src, out):
    """AAC mono 48 kbps, moov atom first so playback starts before the whole file arrives. Cached: skipped when `out`
    is newer than `src`."""
    src, out = Path(src), Path(out)
    if out.exists() and out.stat().st_size > 0 and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.m4a")
    res = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-map", "0:a:0", "-ac", "1", "-c:a", "aac",
                          "-b:a", f"{AUDIO_KBPS}k", "-movflags", "+faststart", str(tmp)], capture_output=True, text=True)
    if res.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed on {src}: {res.stderr.strip()[-200:]}")
    tmp.replace(out)
    return out


LOCK = ROOT / "upload_media.lock"


def alive(pid):
    if os.name != "nt":                          # the GitHub runner (Linux)
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return str(pid) in out


def running():
    """The pid of an upload run that is alive, else None."""
    try:
        pid = int(LOCK.read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if alive(pid) else None


def size_of(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def pending(module="year2-cns"):
    """Rows whose recording is not uploaded yet (or whose file changed since): [(lecture, why)]."""
    mf = ROOT / "modules" / module / "site" / "media.json"
    rows = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else []
    return [r for r in rows if r["lecture"] not in site_lessons.MEDIA and (r.get("uploaded_size") is None or r["uploaded_size"] != size_of(r["file"]))]


def start_background(module="year2-cns"):
    """Starts `upload_media.py <module>` and then `site_lessons.py write` in a detached process (log: upload_media_auto.log).
    Returns a report line."""
    if (pid := running()):
        return f"upload already running (pid {pid})"
    todo = pending(module)
    if not todo:
        return "no recording waits for upload"
    missing = [r["lecture"] for r in todo if size_of(r["file"]) is None]
    log = open(ROOT / "logs" / "upload_media_auto.log", "a", encoding="utf-8")
    cmd = f'py "{ROOT / "upload_media.py"}" {module} && py "{ROOT / "site_lessons.py"}" write'
    subprocess.Popen(cmd, shell=True, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0))
    line = f"upload started in the background for {len(todo)} recording(s) (log: upload_media_auto.log)"
    return line + (f"; source file missing for {', '.join(missing)}" if missing else "")


def main(module="year2-cns"):
    if (pid := running()):
        print(f"another upload run is alive (pid {pid}); not starting a second one")
        return
    LOCK.write_text(str(os.getpid()))
    try:
        run(module)
    finally:
        LOCK.unlink(missing_ok=True)


def run(module):
    mf = ROOT / "modules" / module / "site" / "media.json"
    rows = json.loads(mf.read_text(encoding="utf-8"))
    todo = [r for r in rows if r["lecture"] not in site_lessons.MEDIA and (r.get("uploaded_size") is None or r["uploaded_size"] != size_of(r["file"]))]
    from concurrent.futures import ThreadPoolExecutor

    def prepare(r):
        if r["field"] != "audioUrl":
            return r["file"]
        out = ROOT / "modules" / module / "site" / "compressed" / f"{r['lecture']}{SUFFIX}"
        return str(compress(r["file"], out))

    def one(job):
        i, r = job
        try:
            file = prepare(r)
        except Exception as e:  # one bad source must not stop the others
            print(f"{i}/{len(todo)} {r['lecture']} FAILED {str(e)[-160:]}", flush=True)
            return True
        key = compressed_key(r["key"]) if r["field"] == "audioUrl" else r["key"]
        for attempt in range(TRIES):  # a streamed body is never retried by the S3 client: retry the whole file here
            res = subprocess.run(["node", "../node_modules/tsx/dist/cli.mjs", "src/scripts/uploadLessonMedia.ts", "--file", file,
                                  "--key", key], cwd=BACKEND, capture_output=True, text=True, encoding="utf-8")
            if res.returncode == 0:
                break
            time.sleep(15 * (attempt + 1))
        ok = res.returncode == 0
        if ok and key != r["key"]:
            r["original_key"], r["key"] = r["key"], key  # media.json now points at the small file
        if ok:
            r["uploaded_size"] = size_of(r["file"])
        print(f"{i}/{len(todo)} {r['lecture']} {'ok' if ok else f'FAILED (exit {res.returncode})'} {(res.stdout or res.stderr).strip()[-160:]}", flush=True)
        return not ok
    with ThreadPoolExecutor(WORKERS) as pool:  # one connection is slow (about 150 KB/s): several files at once
        bad = sum(pool.map(one, enumerate(todo, 1)))
    done = {r["lecture"]: r for r in todo}  # rows may have been added or replaced meanwhile: merge, never overwrite
    now = json.loads(mf.read_text(encoding="utf-8"))
    for n in now:
        d = done.get(n["lecture"])
        if d and n["file"] == d["file"]:
            n.update({k: d[k] for k in ("key", "original_key", "uploaded_size") if k in d})
    mf.write_text(json.dumps(now, indent=1), encoding="utf-8")
    print(f"done: {len(todo) - bad} uploaded, {bad} failed")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(*sys.argv[1:])

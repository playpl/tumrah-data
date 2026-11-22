"""YouTube lectures heard again by Gemini (quality report 2026-11-20: YouTube captions drop the English terms).

The PC downloads no recording (owner 2026-11-18), so the runner makes the hearing copy: yt-dlp takes the audio,
ffmpeg makes Opus mono 16 kbps (about 7 MB an hour), and it goes to the bucket at `key(lid)`. The PC then fetches
that small copy and hears it like any other lecture (`py -m spine records rehear-youtube`, then `hear2`).

    python -m cloud.youtube            every lecture in REHEAR without a copy in the bucket yet
The list is cloud/rehear_youtube.json: [{"lecture": "cns-006", "url": "https://youtu.be/..."}].
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from cloud import r2

ROOT = Path(__file__).resolve().parent.parent
REHEAR = ROOT / "cloud" / "rehear_youtube.json"
MODULE = "year2-cns"


def key(lid):
    return r2.OPS + f"hear/{MODULE}/{lid}.youtube.16k.ogg"


def run(say=print):
    rows = json.loads(REHEAR.read_text(encoding="utf-8"))
    made = 0
    for row in rows:
        lid, url = row["lecture"], row["url"]
        if r2.size(key(lid)):
            say(f"  {lid}: already in the bucket")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "audio"
            got = subprocess.run([sys.executable, "-m", "yt_dlp", "-q", "--no-playlist", "-f", "bestaudio/best",
                                  "-o", str(src) + ".%(ext)s", url], capture_output=True, text=True)
            files = list(Path(tmp).glob("audio.*"))
            if got.returncode or not files:
                say(f"  {lid}: yt-dlp FAILED {(got.stderr or got.stdout).strip()[-200:]}")
                continue
            out = Path(tmp) / "hear.ogg"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(files[0]), "-vn", "-ac", "1", "-c:a", "libopus",
                            "-b:a", "16k", str(out)], check=True)
            r2.put_bytes(key(lid), out.read_bytes(), "audio/ogg")
            made += 1
            say(f"  {lid}: hearing copy {out.stat().st_size / 1e6:.1f} MB -> bucket")
    say(f"youtube: {made} hearing copies made")
    return made


if __name__ == "__main__":
    run()

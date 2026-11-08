"""Lectures: one folder each under lectures/<id>/ (gitignored; transcripts are internal, never for students).

    lecture.json   id, module, title, doctor, lesson (site id or null), pdf_pages [a, b] or null, transcribe, source, duration_s
    audio.ogg      the recording compressed so one worker hears all of it (config.json lecture_audio)
    raw.txt        what was heard, word for word with [mm:ss]; never edited after it is written
    clean.txt      the same words laid out in paragraphs with punctuation, plus fixes at 0.9 confidence or more
    fixes.jsonl    every suspected misheard word {at, heard, meant, confidence, reason}; under 0.9 waits for the owner
    parts.jsonl    the lecture's parts and sub-parts with times and handout line IDs
    links.jsonl    parts in importHubData lectures format, written when the checks pass

Sources: a local file, or a YouTube link (YouTube's own transcript when there is one, else its audio).
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LECTURES = ROOT / "lectures"
VTT_TIME = re.compile(r"^(\d+):(\d{2}):(\d{2})\.\d{3} --> ")
TAG = re.compile(r"<[^>]+>")
PARAGRAPH_SECONDS = 30


def folder(lecture_id):
    return LECTURES / lecture_id


def load(lecture_id):
    return json.loads((folder(lecture_id) / "lecture.json").read_text(encoding="utf-8"))


def save(meta):
    d = folder(meta["id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "lecture.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def compress(src, dst, kbps):
    """Mono Opus at kbps: a 2-hour lecture at 16 kbps is about 14 MB."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-c:a", "libopus",
                    "-b:a", f"{kbps}k", str(dst)], check=True)


def chunks(src, out_dir, seconds):
    """Cuts src into seconds-long pieces out_dir/c00.ogg, c01.ogg, ... with exact offsets (the timing pass).
    Returns how many. Already cut: counts them."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not any(out_dir.glob("c*.ogg")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-f", "segment", "-segment_time", str(seconds),
                        "-reset_timestamps", "1", "-ac", "1", "-c:a", "libopus", "-b:a", "16k",
                        str(out_dir / "c%02d.ogg")], check=True)
    return len(list(out_dir.glob("c*.ogg")))


def vtt_to_raw(vtt_text):
    """YouTube captions to raw.txt: rolling auto-caption repeats dropped, a [mm:ss] paragraph every ~30 s."""
    paras, last_line, start = [], None, None
    for block in vtt_text.split("\n\n"):
        rows = block.strip().splitlines()
        stamp = next((VTT_TIME.match(r) for r in rows if VTT_TIME.match(r)), None)
        if not stamp:
            continue
        h, m, s = (int(x) for x in stamp.groups())
        t = h * 3600 + m * 60 + s
        for row in rows[[i for i, r in enumerate(rows) if VTT_TIME.match(r)][0] + 1:]:
            text = " ".join(TAG.sub("", row).split())
            if not text or text == last_line:
                continue
            last_line = text
            if start is None or t - start >= PARAGRAPH_SECONDS:
                start = t
                paras.append([t, text])
            else:
                paras[-1][1] += " " + text
    return "\n".join(f"[{t // 60:02d}:{t % 60:02d}] {text}" for t, text in paras) + ("\n" if paras else "")


def youtube(url, workdir):
    """(raw transcript or None, audio path or None). Captions first; audio only when there are none."""
    workdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "ar.*,en.*,ar,en",
                    "--sub-format", "vtt", "-o", str(workdir / "yt.%(ext)s"), url], capture_output=True, text=True)
    subs = sorted(workdir.glob("yt*.vtt"), key=lambda p: (".orig" not in p.name, "auto" in p.name))
    if subs:
        raw = vtt_to_raw(subs[0].read_text(encoding="utf-8"))
        if raw.strip():
            return raw, None
    subprocess.run(["yt-dlp", "-x", "--audio-format", "opus", "-o", str(workdir / "yt_audio.%(ext)s"), url], check=True)
    return None, next(workdir.glob("yt_audio.*"))


def add(lecture_id, module, title, kbps, file=None, url=None, lesson=None, pdf_pages=None, transcribe=True, doctor=None):
    """Registers a lecture and prepares its audio or transcript. Returns the next flow to queue, or None."""
    d = folder(lecture_id)
    d.mkdir(parents=True, exist_ok=True)
    meta = {"id": lecture_id, "module": module, "title": title, "doctor": doctor, "lesson": lesson, "pdf_pages": pdf_pages,
            "transcribe": transcribe, "source": {"file": str(file)} if file else {"youtube": url}, "duration_s": None}
    audio = Path(file) if file else None
    if url:
        raw, audio = youtube(url, d / "download")
        if raw:
            (d / "raw.txt").write_text(raw, encoding="utf-8")
            meta["source"]["transcript"] = "youtube"
            last = re.findall(r"^\[(\d+):(\d{2})\]", raw, re.M)
            meta["duration_s"] = int(last[-1][0]) * 60 + int(last[-1][1]) + PARAGRAPH_SECONDS if last else None
    if audio:
        compress(audio, d / "audio.ogg", kbps)
        meta["duration_s"] = round(duration(d / "audio.ogg"), 1)
    save(meta)
    if not transcribe:
        return None
    return "lecture_links" if (d / "raw.txt").exists() else "transcribe"

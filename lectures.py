"""Lectures: one folder each under lectures/<id>/ (gitignored; transcripts are internal, never for students).

    lecture.json   id, module, title, doctor (site doctorId), kind, lesson (site id or null), ranges [{from, to, pages}]
                   (handout line-ID ranges, placed by the agent or the owner), placed_by, required and doctor_questions
                   (the owner's picks, [{ref, ...}]), pdf_pages [a, b] or null, transcribe, source, duration_s
    shortlist.jsonl  the bank questions code ranks for this lecture (shortlist.py); only these go to the pointer agents
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
import time
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


# The website's Lesson kinds (website session, 2026-11-08): a summary (mini lecture) is the short form of one lesson; a
# revision reviews several lessons of its chapter. Both name what they cover in `covers` and take its handout pages.
KINDS = ("lecture", "summary", "revision")


def new_id(module):
    """cns-001, cns-002, ...: the module's short name and the next free number."""
    short = module.split("-", 1)[1] if "-" in module else module
    used = {int(m.group(1)) for p in LECTURES.glob(f"{short}-*") if (m := re.fullmatch(rf"{re.escape(short)}-(\d+)", p.name))} \
        if LECTURES.exists() else set()
    return f"{short}-{max(used, default=0) + 1:03d}"


def create(module, title, doctor, kind="lecture", **context):
    """The owner names a lecture (owner 2026-11-08: there are no lectures until the owner names one). The agents then
    place it in the handout (flows/place.py) and fill the rest. `context` (subject, chapter, chapter_lessons) comes
    from the owner's doctors/ folder and helps the place agent."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if not (title or "").strip() or not (doctor or "").strip():
        raise ValueError("a lecture needs a title and a doctor")
    covers = [c for c in context.get("covers") or [] if c]
    if kind == "summary" and len(covers) != 1:
        raise ValueError("a mini lecture (summary) covers exactly one lecture")
    if kind == "revision" and not covers:
        raise ValueError("a revision names the lectures it reviews")
    for c in covers:
        if load(c)["module"] != module:
            raise ValueError(f"{c} is not in {module}")
    meta = {"id": new_id(module), "module": module, "title": title.strip(), "doctor": doctor.strip(), "kind": kind,
            "covers": covers, "lesson": None, "ranges": [], "placed_by": None, "required": [], "doctor_questions": [],
            "transcribe": False, "source": {}, "duration_s": None, "pdf_pages": None,
            "created": time.strftime("%Y-%m-%d %H:%M"),
            **{k: v for k, v in context.items() if k in ("subject", "chapter", "chapter_lessons") and v}}
    save(meta)
    if covers:
        cover_ranges(meta)
    return meta


def cover_ranges(meta):
    """A summary or revision takes the handout ranges of the lectures it covers (joined, handout order). Run again when a
    covered lecture's pages change."""
    rs = []
    for c in meta.get("covers") or []:
        rs += [r for r in load(c).get("ranges") or [] if r not in rs]
    rs.sort(key=lambda r: tuple(r["pages"]))
    meta.update(ranges=rs, placed_by="covers" if rs else None,
                pdf_pages=[rs[0]["pages"][0], max(r["pages"][1] for r in rs)] if rs else None)
    save(meta)
    return meta


def page_ranges(meta):
    """[[first_pdf_page, last_pdf_page], ...] from the lecture's line-ID ranges."""
    return [r["pages"] for r in meta.get("ranges") or []]


def set_ranges(meta, module_lines, pages, by):
    """Whole-page ranges [[a, b], ...] to line-ID ranges {from, to, pages}: the first line of page a to the last of b."""
    by_page = {}
    for ln in module_lines:
        by_page.setdefault(ln["page"], []).append(ln)
    out = []
    for a, b in sorted(pages):
        first = min(by_page[a], key=lambda ln: ln["n"])
        last = max(by_page[b], key=lambda ln: ln["n"])
        out.append({"from": first["id"], "to": last["id"], "pages": [a, b]})
    return _place(meta, out, by)


def set_line_ranges(meta, module_lines, spans, by):
    """Ranges cut at exact lines: spans [(first index, last index)] in lines.jsonl order (placement.py cuts at
    headings). Marked `cut`, so ledger.range_ids reads them line by line and two lessons can split one page."""
    out = [{"from": module_lines[a]["id"], "to": module_lines[b]["id"],
            "pages": [module_lines[a]["page"], module_lines[b]["page"]], "cut": True} for a, b in sorted(spans)]
    return _place(meta, out, by)


def _place(meta, out, by):
    meta.update(ranges=out, placed_by=by, pdf_pages=[out[0]["pages"][0], out[-1]["pages"][1]] if out else None)
    save(meta)
    for other in all_lectures(meta["module"]):  # mini lectures and revisions follow the pages of what they cover
        if meta["id"] in (other.get("covers") or []):
            cover_ranges(other)
    return meta


def lecture_lines(meta, module_lines):
    """The handout lines inside the lecture's ranges, in handout order."""
    spans = page_ranges(meta)
    return [ln for ln in module_lines if any(a <= ln["page"] <= b for a, b in spans)]


def all_lectures(module=None):
    if not LECTURES.exists():
        return []
    out = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(LECTURES.glob("*/lecture.json"))]
    return [m for m in out if module is None or m["module"] == module]


BACKUP_FILES = ("raw.txt", "clean.txt", "fixes.jsonl", "parts.jsonl", "links.jsonl", "audio.ogg")


def add(lecture_id, module, title, kbps, file=None, url=None, lesson=None, pdf_pages=None, transcribe=True, doctor=None,
        backup=None):
    """Adds a recording (file or YouTube) to a lecture, registering the lecture first when the owner has not named it
    yet, and prepares its audio or transcript. Returns the next flow to queue, or None.

    `backup` marks the recording as the previous batch's (backup.py: "use backup for lecture X until the new one is
    provided"): meta["backup"] holds that dict and the site warns "old data". Adding any other recording to a lecture
    that holds a backup replaces it: the old transcript and audio move to `old_backup_recording/` (they describe the old
    batch's lecture) and the flag goes."""
    d = folder(lecture_id)
    d.mkdir(parents=True, exist_ok=True)
    if backup is None and (d / "lecture.json").exists() and load(lecture_id).get("backup"):
        import shutil
        old = d / "old_backup_recording"
        old.mkdir(exist_ok=True)
        for name in BACKUP_FILES:
            if (d / name).exists():
                shutil.move(str(d / name), str(old / name))
    meta = load(lecture_id) if (d / "lecture.json").exists() else \
        {"id": lecture_id, "module": module, "title": title, "doctor": doctor, "kind": "lecture", "lesson": lesson,
         "ranges": [], "placed_by": None, "required": [], "doctor_questions": [], "pdf_pages": pdf_pages}
    meta.update({k: v for k, v in (("lesson", lesson), ("pdf_pages", pdf_pages), ("doctor", doctor)) if v},
                transcribe=transcribe, source={"file": str(file)} if file else {"youtube": url}, duration_s=None)
    meta.pop("backup", None)
    if backup:
        meta["backup"] = backup
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

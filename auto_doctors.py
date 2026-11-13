"""Auto doctors (owner, 2026-11-10): a doctor's folder holds `all here updates (auto).txt` with the link of a list message
in RecordsBatch58ATM that the channel keeps editing. Reading it again finds the doctor's new lectures.

    py auto_doctors.py plan       read the lists (Telegram, read only) and say what is new; changes nothing
    py auto_doctors.py sync       the same, then name each new lecture, fetch its recording, queue its place job

Each lecture part of a list becomes one lecture: "<item> part N (Dr. <first name>)" (no "part" when the item has one
part). A YouTube link is the recording (YouTube's transcript first); an audio or video post is downloaded to
sources/records/<post>/ (a video over BIG_MB waits: the owner decides). A part is already ours when its post id, its
YouTube id, or the size of its local file matches a lecture we have. PDFs the lists link are only reported (owner
decides partial or full by the file name in the doctor's folder). Revisions become revision lectures covering the
doctor's lectures of the chapter. A doctor with no site doctor id is reported, not guessed (Cocci, 2026-11-10).
Nothing here reads recordings, questions or Arabic text: counts, sizes and English titles only.
"""
import json
import re
import sys
from pathlib import Path

import doctors_folder
import lectures
import tg_lists

ROOT = Path(__file__).resolve().parent
MODULES = doctors_folder.MODULES
BIG_MB = 200
KBPS = 16
TAGS = {"azony": "Dr. Azouny"}  # the name the first lectures were given
YT_ID = re.compile(r"(?:youtu\.be/|v=)([\w-]{11})")


def auto_doctors():
    """[{module, subject, folder, key, doctor_id, tag, auto, old}] for every doctor folder that has a list file."""
    out = []
    root = doctors_folder.DOCTORS
    for mod in sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []:
        for subj in sorted(p for p in mod.iterdir() if p.is_dir()):
            for doc in sorted(p for p in subj.iterdir() if p.is_dir()):
                lf = doctors_folder.list_files(doc)
                if lf:
                    key = doctors_folder.key_of(doc.name)
                    out.append({"module": MODULES.get(mod.name, mod.name), "subject": subj.name, "folder": doc,
                                "key": key, "doctor_id": doctors_folder.ALIASES.get(key),
                                "tag": TAGS.get(key) or "Dr. " + key.split()[0].title(), "auto": lf.get("auto"), "old": lf.get("old")})
    return out


def yt_id(url):
    m = YT_ID.search(url or "")
    return m.group(1) if m else None


def known(module, posts):
    """{post id: lecture id} for every post one of our lectures already holds: by Telegram post id, YouTube id, or the
    size of its local recording. `posts` is {post id: post meta} of every list read."""
    by_size = {}
    for pid, p in posts.items():
        if p.get("size"):
            by_size.setdefault(p["size"], []).append(int(pid))
    out = {}
    for m in lectures.all_lectures(module):
        src = m.get("source") or {}
        if src.get("telegram"):
            pid = tg_lists.message_id(src["telegram"])
            if pid:
                out[pid] = m["id"]
        yid = yt_id(src.get("youtube"))
        if yid:
            for pid, p in posts.items():
                if yid in (yt_id(u) for u in p.get("youtube") or []):
                    out[int(pid)] = m["id"]
        f = src.get("file")
        if f and Path(f).exists():
            for pid in by_size.get(Path(f).stat().st_size, []):
                out[pid] = m["id"]
    return out


def local_pdf_sizes(folder):
    return {f.stat().st_size for f in Path(folder).glob("*.pdf")}


def parts_of(lst, section):
    """[(item title, part no, parts in item, part, post meta)] of one section of a fetched list."""
    out = []
    for it in lst["sections"].get(section, []):
        seen, parts = set(), []
        for part in it["parts"]:  # a list may link one post twice
            if part["post"] is None or part["post"] not in seen:
                seen.add(part["post"])
                parts.append(part)
        for n, part in enumerate(parts, 1):
            out.append((it["title"], n, len(parts), part, lst["posts"].get(str(part["post"])) or {}))
    return out


def lecture_title(d, item, n, count):
    # No doctor tag in the title (owner, 2026-11-11): the site shows the doctor beside every lecture already.
    return f"{doctors_folder.nice(item)}{f' part {n}' if count > 1 else ''}"


def plan(lists=None):
    """What a sync would do: per doctor, new lecture parts, big videos, PDFs not in the folder, revisions."""
    lists = lists or {i: tg_lists.load(i) for d in auto_doctors() for i in [d["auto"]] if i}
    posts = {pid: p for l in lists.values() if l for pid, p in l["posts"].items()}
    out = []
    for d in auto_doctors():
        lst = lists.get(d["auto"]) if d["auto"] else None
        if not lst:
            continue
        have = known(d["module"], posts)
        by_title = {m["title"].lower(): m for m in lectures.all_lectures(d["module"]) if m.get("doctor") == d["doctor_id"]}
        row = {"doctor": d, "new": [], "have": 0, "pdfs": [], "revisions": []}
        sizes = local_pdf_sizes(d["folder"])
        for section in ("lectures", "revisions"):
            for item, n, count, part, post in parts_of(lst, section):
                if post and post.get("kind") in ("pdf", "file") and section == "lectures":
                    row["pdfs"].append({"title": item, "post": part["post"], "size": post.get("size")})  # a diagram sheet, not a recording
                    continue
                if part["post"] in have or not post or post.get("kind") in (None, "none", "text") and not post.get("youtube"):
                    row["have"] += part["post"] in have
                    continue
                title = lecture_title(d, item, n, count)
                same = by_title.get(title.lower())
                if same and not same.get("backup"):
                    row["have"] += 1
                    continue
                row["new" if section == "lectures" else "revisions"].append({
                    "title": title, "item": item, "post": part["post"], "kind": post["kind"], "size": post.get("size"),
                    "duration": post.get("duration"), "youtube": (post.get("youtube") or [None])[0], "url": part["url"],
                    "replace": same["id"] if same else None})  # the batch's own recording for a lecture on a backup
        for item, n, count, part, post in parts_of(lst, "pdfs"):
            if post and post.get("size") not in sizes:
                row["pdfs"].append({"title": item, "post": part["post"], "size": post.get("size")})
        out.append(row)
    return out


def describe(rows):
    lines = []
    for r in rows:
        d = r["doctor"]
        head = f"{d['key']} ({d['subject']}, {d['doctor_id'] or 'NO SITE DOCTOR'}): {r['have']} known, {len(r['new'])} new lecture(s), " \
               f"{len(r['revisions'])} revision(s), {len(r['pdfs'])} PDF(s) not in the folder"
        lines.append(head)
        for x in r["new"] + r["revisions"]:
            mb = f"{x['size'] / 1e6:.0f} MB" if x.get("size") else "link"
            lines.append(f"   + {tg_lists.ascii_label(x['title'])} [{x['kind']}, {mb}, post {x['post']}]"
                         + (f" replaces the backup of {x['replace']}" if x.get("replace") else ""))
        for x in r["pdfs"]:
            lines.append(f"   PDF post {x['post']} ({tg_lists.ascii_label(x['title'])}, {(x['size'] or 0) / 1e6:.1f} MB): not in the folder")
    return lines


def sync(q, dry=False, big_mb=BIG_MB):
    """Reads every auto list, then makes each new lecture. Returns report lines. Telegram unreachable: says so."""
    docs = [d for d in auto_doctors() if d["auto"]]
    report = []
    try:
        lists = tg_lists.fetch_many([d["auto"] for d in docs])
    except Exception as e:  # noqa: BLE001 - login prompt, flood wait, no network: stop reading, keep the rest of the update
        return [f"Telegram lists NOT read ({type(e).__name__}: {str(e)[:120]}); auto doctors not updated"]
    rows = plan(lists)
    report += describe(rows)
    if dry:
        return report
    for r in rows:
        d = r["doctor"]
        for kind, items in (("lecture", r["new"]), ("revision", r["revisions"])):
            for x in items:
                report += make(q, d, x, kind, big_mb)
    return report


def make(q, d, x, kind, big_mb):
    doctor = d["doctor_id"] or doctors_folder.clean_name(d["folder"].name)
    chapter = None  # a list spans chapters: the place job decides where each lecture goes
    ctx = {}
    if x.get("replace"):
        meta, lid = lectures.load(x["replace"]), x["replace"]
        note = f"{lid}: '{x['title']}' (the batch's own recording replaces the backup)"
        return add_recording(q, d, x, lid, doctor, note, big_mb)
    if kind == "revision":
        ctx["covers"] = doctors_folder.revision_covers({"module": d["module"], "doctor_id": d["doctor_id"], "doctor_folder": d["folder"].name,
                                                        "chapter": chapter, "title": x["item"]})
        if not ctx["covers"]:
            return [f"revision '{x['title']}': no lecture of {d['key']} to cover yet, waits"]
    meta = lectures.create(d["module"], x["title"], doctor, kind=kind, subject=d["subject"], chapter=chapter, **ctx)
    lid = meta["id"]
    q.add_jobs("place", [{"key": lid, "payload": {"lecture": lid}}])
    note = f"{lid}: '{x['title']}' ({kind}, {d['doctor_id'] or 'no site doctor: ask the owner'})"
    return add_recording(q, d, x, lid, doctor, note, big_mb)


def add_recording(q, d, x, lid, doctor, note, big_mb):
    """The recording of one list part into its lecture: a YouTube link, or the post's audio/video downloaded."""
    if x["youtube"]:
        nxt = lectures.add(lid, d["module"], x["title"], KBPS, url=x["youtube"], doctor=doctor)
        meta = lectures.load(lid)
        if nxt:
            q.add_jobs(nxt, [{"key": lid, "payload": {"lecture": lid}}])
        return [f"{note}: YouTube, transcript from {meta['source'].get('transcript', 'the fleet')}"]
    meta = lectures.load(lid)
    meta["source"] = {"telegram": x["url"]}
    lectures.save(meta)
    if (x["size"] or 0) > big_mb * 1e6:
        return [f"{note}: {x['kind']} of {x['size'] / 1e6:.0f} MB not downloaded (over {big_mb} MB): say 'download {lid}'"]
    got = tg_lists.download([x["post"]])
    f = got.get(x["post"])
    if not f:
        return [f"{note}: no file in post {x['post']}"]
    nxt = lectures.add(lid, d["module"], x["title"], KBPS, file=f, doctor=doctor)
    doctors_folder.media_merge(d["module"], [doctors_folder.media_row(d["module"], lid, f)])
    if nxt:
        q.add_jobs(nxt, [{"key": lid, "payload": {"lecture": lid}}])
    meta = lectures.load(lid)
    meta["source"]["telegram"] = x["url"]
    lectures.save(meta)
    return [f"{note}: {x['kind']} downloaded, {meta.get('duration_s')} s, transcript waits for the fleet"]


def download_waiting(q, lid):
    """A big video that waited for the owner's word: downloads the post its lecture points at and adds it."""
    meta = lectures.load(lid)
    url = (meta.get("source") or {}).get("telegram")
    post = tg_lists.message_id(url)
    if not post or (meta["source"].get("file")):
        return [f"{lid}: no waiting Telegram recording"]
    d = next((x for x in auto_doctors() if x["doctor_id"] and x["doctor_id"] == meta.get("doctor")), None)
    if not d:
        return [f"{lid}: no doctor folder for {meta.get('doctor')}"]
    x = {"title": meta["title"], "post": post, "url": url, "youtube": None, "size": 0, "kind": "file"}
    return add_recording(q, d, x, lid, meta["doctor"], f"{lid}: '{meta['title']}'", 10 ** 9)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    import queue_db
    q = queue_db.Queue()
    for line in (download_waiting(q, sys.argv[2]) if cmd == "download" else sync(q, dry=(cmd != "sync"))):
        print(line)

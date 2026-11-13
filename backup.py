"""Backup data (owner, 2026-11-10): "use backup for lecture X, doctor Y, till new is provided".

A doctor's folder holds `old data.txt`: the link of a list message in RecordsBatch58ATM with the PREVIOUS batch's
recordings. When the owner says to use the backup for one lecture, this takes that lecture's old recording from
Telegram and uses it for now. The lesson is flagged (`backup` in lecture.json; `oldData: true` in the site lesson row),
and the website shows "Old data" with a "More info" button: waiting for your peers to upload a record; subscribed
students can help by uploading records through the data bot @ZMSU58_bot.

    py backup.py use <lecture id or title words> [--doctor <name>] [--item "<old list title>"] [--big]
    py backup.py list <lecture id or title words> [--doctor <name>]       what the old list offers for it
    py backup.py status                                                   lectures now on a backup
    py backup.py clear <lecture id>                                       drop the flag (the real recording is in)

The real recording replaces the backup by itself: any recording added to the lecture later (the doctor's folder, an auto
list, `dm.py lecture`) moves the old transcript aside (lectures.add) and clears the flag. A match that is not clear is
never guessed: the command lists the candidates (English titles) and stops.
"""
import re
import unicodedata
import subprocess
import sys
import time
from pathlib import Path

import auto_doctors
import doctors_folder
import lectures
import tg_lists

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "sources" / "backup"
STOP = {"dr", "part", "the", "of", "and", "revision"}


def words(title):
    """Comparable words of a lecture title: the "(Dr. X)" tag dropped, lower case, filler words dropped."""
    t = re.sub(r"\([^)]*\)", " ", unicodedata.normalize("NFKC", title or "").lower())
    return {w for w in re.findall(r"[a-z0-9]+", t) if w not in STOP}


def find_lectures(what, doctor=None):
    """Lectures whose id is `what`, else whose title holds every word of it (of the named doctor, when given)."""
    every = lectures.all_lectures()
    exact = [m for m in every if m["id"] == what]
    if exact:
        return exact
    want = words(what)
    out = [m for m in every if want and want <= words(m["title"])]
    if doctor:
        d = doctor.lower()
        out = [m for m in out if d in (m.get("doctor") or "").lower() or d in m["title"].lower()]
    return out


def doctor_entry(meta):
    """The auto_doctors entry (folder, old-list id) of a lecture's doctor."""
    return next((d for d in auto_doctors.auto_doctors() if d["doctor_id"] and d["doctor_id"] == meta.get("doctor")), None)


def old_items(entry, refresh=False):
    lst = tg_lists.load(entry["old"])
    if not lst or refresh:
        lst = tg_lists.fetch_many([entry["old"]])[entry["old"]]
    return lst, [(sec, it) for sec in ("lectures", "revisions", "other") for it in lst["sections"].get(sec, [])]


def candidates(meta, items):
    """Old items ranked by how many of the lecture's words they hold (numbers must agree: "spinal cord 2" is not "3")."""
    want = words(meta["title"])
    nums = {w for w in want if w.isdigit()}
    out = []
    for sec, it in items:
        have = words(it["title"])
        if nums and {w for w in have if w.isdigit()} != nums:
            continue
        if not want or not have:
            continue
        score = len(want & have) / len(want | have)
        if score > 0:
            out.append((score, sec, it))
    return sorted(out, key=lambda x: -x[0])


def parts_file(lst, item, lid, big_mb):
    """(file, youtube url, note): the old item's recording. Several audio parts are joined into one file."""
    posts = [lst["posts"].get(str(p["post"])) or {} for p in item["parts"]]
    yt = [u for p in posts for u in p.get("youtube") or []]
    media = [p for p in posts if p.get("kind") in ("audio", "video")]
    if not media:
        return None, (yt[0] if yt else None), "youtube link" if yt else "no recording in its posts"
    size = sum(p.get("size") or 0 for p in media)
    if size > big_mb * 1e6:
        return None, None, f"{size / 1e6:.0f} MB is over {big_mb} MB: add --big"
    got = tg_lists.download([p["id"] for p in media])
    files = [got[p["id"]] for p in media if p["id"] in got]
    if len(files) == 1:
        return files[0], None, f"{files[0].name}"
    OUT.mkdir(parents=True, exist_ok=True)
    joined = OUT / f"{lid}-old.ogg"
    listing = OUT / f"{lid}-old.txt"
    listing.write_text("".join(f"file '{Path(f).as_posix()}'\n" for f in files), encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-vn", "-ac", "1",
                    "-c:a", "libopus", "-b:a", "24k", str(joined)], check=True)
    return joined, None, f"{len(files)} parts joined"


def use(q, what, doctor=None, item=None, big=False):
    ms = find_lectures(what, doctor)
    if len(ms) != 1:
        return [f"'{what}': {len(ms)} lectures match" + "".join(f"\n   {m['id']} {tg_lists.ascii_label(m['title'])}" for m in ms[:10])
                + ("\n   say which one (lecture id)" if ms else "")]
    meta = ms[0]
    lid = meta["id"]
    entry = doctor_entry(meta)
    if not entry or not entry.get("old"):
        return [f"{lid}: no `old data.txt` in the doctor folder of {meta.get('doctor')}: no backup list to read"]
    try:
        lst, items = old_items(entry)
    except Exception as e:  # noqa: BLE001 - Telegram unreachable
        return [f"{lid}: Telegram old list NOT read ({type(e).__name__}: {str(e)[:100]})"]
    ranked = candidates(meta, items)
    if item:
        ranked = [r for r in ranked if item.lower() in r[2]["title"].lower()] or \
                 [(1.0, s, it) for s, it in items if item.lower() in it["title"].lower()]
    if not ranked or (not item and len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.2 and ranked[0][0] < 1):
        return [f"{lid} '{meta['title']}': the old list ({entry['key']}) has no clear match; closest:"] + \
               [f"   {s:.2f} {sec}: {tg_lists.ascii_label(it['title'])} ({len(it['parts'])} part(s))" for s, sec, it in ranked[:5]] + \
               ["   rerun with --item \"<one of these titles>\""]
    score, sec, it = ranked[0]
    f, url, note = parts_file(lst, it, lid, 400 if big else 200)
    if not f and not url:
        return [f"{lid}: old item '{tg_lists.ascii_label(it['title'])}' not used: {note}"]
    stamp = {"since": time.strftime("%Y-%m-%d"), "item": it["title"], "list": entry["old"],
             "posts": [p["post"] for p in it["parts"]]}
    nxt = lectures.add(lid, meta["module"], meta["title"], auto_doctors.KBPS, file=f, url=url, backup=stamp)
    if f:
        doctors_folder.media_merge(meta["module"], [doctors_folder.media_row(meta["module"], lid, f)])
    if nxt:
        q.add_jobs(nxt, [{"key": lid, "payload": {"lecture": lid}}])
    return [f"{lid} '{meta['title']}': now on the BACKUP recording '{tg_lists.ascii_label(it['title'])}' ({note}); "
            f"the site lesson will say 'old data' (run `py dm.py site`, then importHubData lessons). "
            f"The new recording replaces it by itself when it is added."]


def status():
    return [f"{m['id']} {tg_lists.ascii_label(m['title'])}: backup '{tg_lists.ascii_label(m['backup']['item'])}' since {m['backup']['since']}"
            for m in lectures.all_lectures() if m.get("backup")] or ["no lecture is on a backup"]


def clear(lid):
    m = lectures.load(lid)
    m.pop("backup", None)
    lectures.save(m)
    return [f"{lid}: backup flag cleared (the recording stays; add the real one to replace it)"]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "status"
    rest = [a for a in argv[1:]]

    def opt(name):
        if name in rest:
            i = rest.index(name)
            v = rest[i + 1]
            del rest[i:i + 2]
            return v
    doctor, item = opt("--doctor"), opt("--item")
    big = "--big" in rest
    rest = [a for a in rest if a != "--big"]
    what = " ".join(rest)
    import queue_db
    q = queue_db.Queue()
    if cmd == "use":
        out = use(q, what, doctor, item, big)
    elif cmd == "list":
        ms = find_lectures(what, doctor)
        out = []
        for m in ms[:1]:
            e = doctor_entry(m)
            if e and e.get("old"):
                _, items = old_items(e)
                out = [f"{m['id']} '{m['title']}' ({e['key']}):"] + \
                      [f"   {s:.2f} {sec}: {tg_lists.ascii_label(it['title'])}" for s, sec, it in candidates(m, items)[:8]]
        out = out or [f"'{what}': no single lecture or no old list"]
    elif cmd == "clear":
        out = clear(what)
    else:
        out = status()
    for line in out:
        print(line)

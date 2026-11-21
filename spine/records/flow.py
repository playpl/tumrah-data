"""The year 1 records inside the two owner commands (owner, 2026-11-17: "merge importation with py update_data.py,
py site_import.py").

`py update_data.py` -> `update()`: one download batch from Telegram (YouTube captions, then recordings, first lessons
of every subject first; `spine.config()["records_batch_mb"]` MB, default 400), then `py -m spine records finish` in
a detached background run (compress, upload, transcribe on the fleet; log logs/records_y1.log; one at a time).

`py site_import.py` -> `write_site()` then the lessons importer for year1-musculoskeletal: one lesson per record whose
doctor has a site doctor id (spine/tg/trees.json `site`) and whose recording is on the site (uploaded, or YouTube).
Every year 1 lesson carries `oldData` (owner: all first-year data is old data; the lesson page says so).
A doctor with no site id, a subject the module has no curriculum for, a record not uploaded yet: reported, left out.
"""
import json
import re
import subprocess
from pathlib import Path

from spine import ROOT, config, module_dir, read_json
from spine.records import machine

LOG = ROOT / "logs" / "records_y1.log"
BG_LOCK = machine.SOURCES / "finish.lock"
# Curriculum modules of year1-musculoskeletal on the site (tumrah backend doctorRoster: "Musculoskeletal and CNS teach
# no biochemistry"). Biochemistry lessons wait until the website session adds the subject to the module.
SITE_SUBJECTS = {"anatomy", "histology", "physiology"}
KIND = {"lecture": "lesson", "mini": "summary", "revision": "revision"}


def bg_running():
    import upload_media
    try:
        pid = int(BG_LOCK.read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if upload_media.alive(pid) else None


def start_finish(via="browser"):
    if (pid := bg_running()):
        return f"year 1 compress/upload/transcribe already running (pid {pid})"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG, "a", encoding="utf-8")
    proc = subprocess.Popen(["py", "-m", "spine", "records", "finish", "--via", via], cwd=ROOT, stdout=log,
                            stderr=subprocess.STDOUT, env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0))
    BG_LOCK.parent.mkdir(parents=True, exist_ok=True)
    BG_LOCK.write_text(str(proc.pid))
    return f"year 1 compress, upload and transcription started in the background (log: {LOG.relative_to(ROOT)})"


def summary(recs):
    st = machine.states(recs[0]["module"]) if recs else {}
    tg = [r for r in recs if r["source"] == "telegram"]
    yt = [r for r in recs if r["source"] == "youtube"]
    n = {s: sum(machine.reached(st, r["id"], s) for r in tg) for s in ("downloaded", "compressed", "uploaded")}
    heard = sum(bool((st.get(r["id"]) or {}).get("transcript")) for r in recs)
    left_mb = sum((r["size"] or 0) - machine.partial_size(r) for r in tg if not machine.reached(st, r["id"], "downloaded")) / 1e6
    return [f"year 1: {len(recs)} records; Telegram {len(tg)}: downloaded {n['downloaded']}, compressed {n['compressed']},"
            f" uploaded {n['uploaded']}; YouTube {len(yt)}: captions {sum(machine.reached(st, r['id'], 'downloaded') for r in yt)};"
            f" transcripts {heard}", f"year 1: {left_mb:.0f} MB still to download from Telegram"]


def update(dry=False, telegram=True, background=True):
    """Update data's year 1 step. Returns report lines."""
    problems, out = [], []
    recs = machine.plan(1, problems=problems)
    out += [f"SKIPPED {p}" for p in problems]
    if not recs:
        return out + ["year 1: no records (run `py -m spine mother run --year 1`)"]
    cloud = config().get("records_cloud")            # the GitHub runner downloads (cloud/records.py), not this PC
    if cloud and not dry:
        from cloud import state
        before, after = state.pull_log()
        out.append(f"year 1 cloud: records log {before} -> {after} rows from the bucket; inputs pushed "
                   f"({state.push_inputs()} files)")
    if not dry and telegram:
        budget = machine.Budget(config().get("records_batch_mb", 400))
        got = []
        machine.download([r for r in recs if r["source"] == "youtube"] if cloud else recs, budget, say=got.append)
        out += [ln.strip() for ln in got if "downloaded" in ln or "so far" in ln or "stopped" in ln or "no file" in ln]
        out += [f"year 1 YouTube captions: {sum('YouTube captions' in ln for ln in got)} new"]
    if not dry and background:
        out.append(start_finish())
    return out + summary(recs)


# --- the site ---------------------------------------------------------------------------------------------------
def youtube_url(url):
    vid = machine.yt_id(url)
    return f"https://youtu.be/{vid}" if vid else url


def site_key(rid):
    """The site lesson key of a record: `lecture:<id>`, where the site allows only [a-z0-9-]. A YouTube record id
    holds the video id (capitals, `_`): lowered, other signs to `-`, plus 6 hex of the real id so two never meet."""
    import hashlib
    import re
    safe = re.sub(r"[^a-z0-9-]", "-", rid.lower())
    if safe != rid:
        safe += "-" + hashlib.sha1(rid.encode("utf-8")).hexdigest()[:6]
    return f"lecture:{safe}"


def lesson_spans(module="year1-musculoskeletal"):
    """{handout lesson (L01..): (first line id, last line id, first page, last page)} from the graph's lesson cuts
    (graph/sentences.jsonl `lesson`); only text lines (":l"), never figures, as range ends."""
    f = module_dir(module) / "graph" / "sentences.jsonl"
    out = {}
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        s = json.loads(line)
        k = (s.get("lesson") or "").rpartition(":")[2]
        rows = [r for r in s.get("rows") or [] if r.rpartition(":")[2].startswith("l")]
        if not k or not rows:
            continue
        if k not in out:
            out[k] = [rows[0], rows[-1], s["page"], s["page"]]
        out[k][1], out[k][3] = rows[-1], s["page"]
    return {k: tuple(v) for k, v in out.items()}


def placement(module="year1-musculoskeletal"):
    """{record id: [L01, ...]} from site/placement.json (written by hand, coarse, by title)."""
    return (read_json(module_dir(module) / "site" / "placement.json") or {}).get("records") or {}


def ranges_of(lessons, spans):
    """Handout ranges of a record's lessons: neighbours (L01+L02) join into one range."""
    out = []
    for k in sorted(set(lessons)):
        if k not in spans:
            continue
        a, b, pa, pb = spans[k]
        if out and out[-1]["_next"] == k:
            out[-1].update(to=b, pages=[out[-1]["pages"][0], pb])
        else:
            out.append({"from": a, "to": b, "pages": [pa, pb]})
        out[-1]["_next"] = f"L{int(k[1:]) + 1:02d}"
    return [{k: v for k, v in r.items() if k != "_next"} for r in out]


def site_rows(recs, st):
    """(rows for importHubData lessons, report lines). Chapters and order follow the doctor's list."""
    keep, out, why = [], [], {}
    for r in recs:
        row = st.get(r["id"]) or {}
        if not r.get("site"):
            why.setdefault("no site doctor id", set()).add(r["doctor"])
            continue
        if r["subject"] not in SITE_SUBJECTS:
            why.setdefault(f"no {r['module']} curriculum for {r['subject']} on the site", set()).add(r["doctor"])
            continue
        if r["source"] == "telegram" and row.get("state") != "uploaded":
            why.setdefault("recording not uploaded yet", set()).add(r["id"])
            continue
        if r["source"] == "youtube" and not r.get("youtube"):
            continue
        if r["source"] is None:
            why.setdefault("no recording in the post", set()).add(r["id"])
            continue
        keep.append(r)
    # A revision or mini lecture that carries the same video as one of the doctor's lectures is that lecture posted
    # twice (Ammar's "All Cartilage" 231 = his Cartilage 2 video, owner 2026-11-21: "You have to deal"): left out.
    lecture_videos = {(r["doctor"], machine.yt_id(r["youtube"])) for r in keep
                      if KIND[r["role"]] == "lesson" and r["source"] == "youtube"}
    for r in [r for r in keep if KIND[r["role"]] != "lesson" and r["source"] == "youtube"]:
        if (r["doctor"], machine.yt_id(r["youtube"])) in lecture_videos:
            keep.remove(r)
            why.setdefault("same video as one of the doctor's lectures", set()).add(r["id"])
    keys = {site_key(r["id"]) for r in keep}
    spans, places = lesson_spans(recs[0]["module"]) if recs else {}, placement(recs[0]["module"]) if recs else {}
    chapters, order = {}, {}
    rows = []
    for r in sorted(keep, key=lambda r: (r["doctor_order"], r["rank"])):
        ck = (r["doctor"], r["chapter"])
        chapters.setdefault(r["doctor"], {})
        if r["chapter"] not in chapters[r["doctor"]]:
            chapters[r["doctor"]][r["chapter"]] = len(chapters[r["doctor"]]) + 1
        order[ck] = order.get(ck, 0) + 1
        covers = [site_key(c) for c in r["covers"] if site_key(c) in keys]
        kind = KIND[r["role"]]
        if kind == "summary" and len(covers) != 1:
            why.setdefault("mini lecture whose lecture is not on the site yet", set()).add(r["id"])
            continue
        row = {"key": site_key(r["id"]), "subject": r["subject"],
               "chapter": {"title": r["chapter"] or r["name"], "order": chapters[r["doctor"]][r["chapter"]]},
               "name": r["name"], "order": order[ck], "kind": kind, "doctorId": r["site"], "covers": covers if kind != "lesson" else [],
               "oldData": True,
               "ranges": [{"from": x["from"], "to": x["to"]} for x in ranges_of(
                   places.get(r["id"]) or [k for c in r["covers"] for k in places.get(c) or []], spans)]}
        if not row["ranges"]:
            why.setdefault("no handout placement (site/placement.json)", set()).add(r["id"])
        if r["source"] == "youtube":
            row["videoUrl"] = youtube_url(r["youtube"])
        else:
            row["audioUrl"] = "r2:" + row_key(st, r)
        rows.append(row)
    for reason, items in why.items():
        out.append(f"year 1 left out ({reason}): {len(items)}" + (f": {', '.join(sorted(items))[:300]}" if len(items) <= 25 else ""))
    return rows, out


def row_key(st, r):
    return (st.get(r["id"]) or {}).get("key") or machine.upload_key(r)


def site_file(module="year1-musculoskeletal"):
    return module_dir(module) / "site" / "lessons.jsonl"


def write_site():
    """Writes modules/year1-musculoskeletal/site/lessons.jsonl. Returns (number of rows, report lines)."""
    recs = machine.plan(1)
    if not recs:
        return 0, ["year 1: no records"]
    rows, out = site_rows(recs, machine.states(recs[0]["module"]))
    f = site_file(recs[0]["module"])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return len(rows), [f"year 1: {len(rows)} lessons of {len(recs)} records -> {f.relative_to(ROOT)}"] + out


def save_ids(result_line, module="year1-musculoskeletal"):
    """The importer's result (last output line, JSON): each lesson id into the state log (`lesson`)."""
    res = json.loads(result_line)
    st = machine.states(module)
    back = {site_key(rid): rid for rid in st}
    n = 0
    for key, lesson in (res.get("lessons") or {}).items():
        rid = back.get(key, key.split(":", 1)[1])
        if lesson and (st.get(rid) or {}).get("lesson") != lesson:
            machine.mark(module, rid, lesson=lesson)
            n += 1
    return n

"""Year 2 recordings through the GitHub runner (owner, 2026-11-18: no heavy uploads or downloads on the PC).

PC side (Update data, `pc_transfers: false`):
    todo()   the year 2 lectures whose recording is not on the site yet; pushed to the bucket by `state.push_year2_todo`
    pull()   the runner's year 2 log back into each lecture: `source.cloud` in lecture.json and a `cloud: true` row in
             media.json, so `site_lessons.py write` serves the key the runner uploaded. No audio is downloaded.

Runner side: `cloud/records.py --year 2` turns `todo()` rows into records (`records()`), downloads each Telegram post,
compresses it to AAC mono 48 kbps (videos too: compress first, owner 2026-11-17) and uploads it under
`lectures/year2-cns/<id>/recording.48k.m4a`, the key the site plays.
"""
import tg_lists

CHANNEL = "RecordsBatch58ATM"
MODULE = "year2-cns"


def key(lid):
    return f"lectures/{MODULE}/{lid}/recording.48k.m4a"


def _media_rows():
    import json
    import upload_media
    f = upload_media.ROOT / "modules" / MODULE / "site" / "media.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def todo():
    """[{lecture, module, channel, post, title, doctor, subject, size}]: lectures whose `source.telegram` is a post of
    the batch channel (a /c/ link is a private chat the runner never reads), with no YouTube link and no cloud upload,
    and with no file yet or a file whose upload is still pending (downloaded on the PC before the rule; the PC does
    not upload it)."""
    import lectures
    import upload_media
    pending = {r["lecture"]: r for r in upload_media.pending(MODULE)}
    out = []
    for m in lectures.all_lectures(MODULE):
        src = m.get("source") or {}
        url = src.get("telegram") or ""
        post = tg_lists.message_id(url)
        if not post or "/c/" in url or f"/{CHANNEL}/" not in url or src.get("youtube") or src.get("cloud"):
            continue
        if src.get("file") and m["id"] not in pending:
            continue
        f = (pending.get(m["id"]) or {}).get("file")
        out.append({"lecture": m["id"], "module": MODULE, "channel": CHANNEL, "post": post, "title": m.get("title"),
                    "doctor": m.get("doctor"), "subject": m.get("subject"), "size": upload_media.size_of(f) if f else None})
    return out


def records(rows):
    """todo() rows as records for spine.records.machine (download, compress, upload, hear copy)."""
    return [{"id": r["lecture"], "module": r.get("module") or MODULE, "channel": r.get("channel") or CHANNEL,
             "post": r["post"], "source": "telegram", "subject": r.get("subject"), "doctor": r.get("doctor"),
             "list": None, "name": r.get("title"), "size": r.get("size"), "rank": i, "doctor_order": 0}
            for i, r in enumerate(rows)]


def pull(say=print):
    """The year 2 log from the bucket into lecture.json and media.json. Returns report lines."""
    import doctors_folder
    import lectures
    from cloud import state
    from spine.records import machine
    before, after = state.pull_log(MODULE)
    out = [f"year 2 cloud: records log {before} -> {after} rows from the bucket"]
    st = machine.states(MODULE)
    rows, media = [], {r["lecture"]: r for r in _media_rows()}
    for lid, row in sorted(st.items()):
        if row.get("state") != "uploaded" or not (lectures.folder(lid) / "lecture.json").exists():
            continue
        meta = lectures.load(lid)
        cloud = {"key": row.get("key") or key(lid), "size": row.get("uploaded_size"), "hear_key": row.get("hear_key"),
                 "duration_s": row.get("duration_s")}
        m = media.get(lid) or {}
        if (meta.get("source") or {}).get("cloud") == cloud and m.get("cloud") and m.get("key") == cloud["key"]:
            continue
        meta.setdefault("source", {})["cloud"] = cloud
        if row.get("duration_s"):
            meta["duration_s"] = row["duration_s"]
        lectures.save(meta)
        rows.append({"lecture": lid, "file": "", "key": cloud["key"], "field": "audioUrl", "cloud": True,
                     "uploaded_size": cloud["size"]})
        out.append(f"{lid}: on the site from the runner ({(cloud['size'] or 0) / 1e6:.1f} MB)")
    if rows:
        doctors_folder.media_merge(MODULE, rows)
    return out

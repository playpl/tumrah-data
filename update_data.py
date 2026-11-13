"""`Update data`: the owner says it, Claude runs this one command and reads its report (owner, 2026-11-10).

    py update_data.py                 everything below, then the report
    py update_data.py --no-telegram   skip the Telegram steps (lists, waiting downloads); the folder is still imported
    py update_data.py --dry           what would change; changes nothing
    py update_data.py --no-upload     do not start the recording upload

What it does, in order (each step on its own: one failing step never stops the others):
 1. doctors/ folder look (doctors_watch): new, changed and removed files since the last update.
 2. repair_paths: recordings that moved with a renamed doctor folder.
 3. auto doctors (Telegram, read only): every `all here updates (auto).txt` list is read; each new lecture is named,
    its recording fetched (YouTube transcript first, audio posts downloaded), its place job queued (auto_doctors.py).
 4. the folder import (doctors_folder.import_all): new lessons, recordings, quizzes, books (a full book folds the
    partial one in and keeps its alignment), MCQ books, mini lectures, revisions.
 5. Telegram recordings that waited for a session (mini lectures).
 6. site files: `dm.py site` rewrites modules/<m>/site/lessons.jsonl (old-data flags included).
    Uploads (owner, 2026-11-12, "make it automatic"): every recording not yet uploaded is sent to the site's private storage
    by upload_media.py in a detached background run (not in --dry; --no-upload skips it); it rewrites the site files when done.
 7. the ledger and the owner's cards (not in --dry): ledger.sync, decisions.refresh; "N decisions wait on the Today screen".
 8. the report: what changed, what waits (the fleet is down: transcribe, place, align, MCQ copy), what needs the owner.
The website itself is NOT touched here: importers write production (dry run first, `--apply` writes an undo file).
The pending list is cleared only when nothing is still being written.
"""
import json
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def step(report, name, fn):
    try:
        out = fn()
        report.append((name, out if isinstance(out, list) else [str(out)] if out else []))
    except Exception as e:  # noqa: BLE001 - one step failing must not hide the others
        report.append((name, [f"FAILED {type(e).__name__}: {str(e)[:200]}", *traceback.format_exc().splitlines()[-3:-1]]))


def folder_look():
    import doctors_watch
    doctors_watch.check(quiet=True)
    pend = json.loads(doctors_watch.PENDING.read_text(encoding="utf-8")) if doctors_watch.PENDING.exists() else []
    return [f"{len(pend)} file change(s) since the last update: {doctors_watch.summary(pend)}"] if pend else ["no file changes since the last update"]


def nagib_forms_changed():
    import doctors_watch
    pend = json.loads(doctors_watch.PENDING.read_text(encoding="utf-8")) if doctors_watch.PENDING.exists() else []
    return any("nageb" in p["file"].lower() and p["file"].lower().endswith(".url") and p["what"] != "gone" for p in pend)


def nagib_quizzes_run():
    """Nagib's top-level quiz forms (read only) into the bank and his lectures: nagib_quizzes.py."""
    res = subprocess.run(["py", str(ROOT / "nagib_quizzes.py")], capture_output=True, text=True, cwd=ROOT, encoding="utf-8")
    return (res.stdout + res.stderr).strip().splitlines()[-6:]


def waiting_telegram(q, dry):
    """Lectures that point at a Telegram post and have no recording yet (mini lectures): download when it is small."""
    import auto_doctors
    import doctors_folder
    import lectures
    import tg_lists
    out = []
    todo = {}
    for m in lectures.all_lectures():
        src = m.get("source") or {}
        post = tg_lists.message_id(src["telegram"]) if src.get("telegram") and "/c/" not in src["telegram"] else None
        if post and not src.get("file") and not src.get("youtube"):
            todo[post] = m
    if not todo:
        return ["no recording waits for Telegram"]
    infos = tg_lists.info(list(todo))
    for post, m in todo.items():
        i = infos.get(post) or {}
        if i.get("youtube"):
            if not dry:
                nxt = lectures.add(m["id"], m["module"], m["title"], auto_doctors.KBPS, url=i["youtube"][0], doctor=m.get("doctor"))
                if nxt:
                    q.add_jobs(nxt, [{"key": m["id"], "payload": {"lecture": m["id"]}}])
            out.append(f"{m['id']}: YouTube link from post {post}")
        elif i.get("kind") in ("audio", "video"):
            mb = (i.get("size") or 0) / 1e6
            if mb > auto_doctors.BIG_MB:
                out.append(f"{m['id']}: post {post} is {mb:.0f} MB, not downloaded: say 'download {m['id']}'")
            elif not dry:
                got = tg_lists.download([post]).get(post)
                nxt = lectures.add(m["id"], m["module"], m["title"], auto_doctors.KBPS, file=got, doctor=m.get("doctor"))
                doctors_folder.media_merge(m["module"], [doctors_folder.media_row(m["module"], m["id"], got)])
                meta = lectures.load(m["id"])
                meta["source"]["telegram"] = f"https://t.me/RecordsBatch58ATM/{post}"
                lectures.save(meta)
                if nxt:
                    q.add_jobs(nxt, [{"key": m["id"], "payload": {"lecture": m["id"]}}])
                out.append(f"{m['id']}: post {post} downloaded ({mb:.0f} MB), transcript waits for the fleet")
            else:
                out.append(f"{m['id']}: post {post} would be downloaded ({mb:.0f} MB)")
        else:
            out.append(f"{m['id']}: post {post} holds no recording ({i.get('kind')})")
    return out


def site_files():
    res = subprocess.run(["py", str(ROOT / "site_lessons.py"), "write"], capture_output=True, text=True, cwd=ROOT, encoding="utf-8")
    return [ln for ln in res.stdout.splitlines() if "lessons" in ln] or [res.stderr.strip()[-200:]]


def state(q):
    """Counts the owner needs: queue by flow, lectures without a recording, lectures on a backup."""
    import lectures
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    prog = q.progress()
    queued = {f: v["queued"] for f, v in prog.items() if v.get("queued")}
    metas = lectures.all_lectures()
    bare = [m["id"] for m in metas if not m.get("source")]
    out = [f"queued for the fleet: {queued or 'nothing'}" + ("  (fleet is DOWN: they only wait)" if cfg.get("fleet", {}).get("down") else "")]
    if bare:
        out.append(f"{len(bare)} lecture(s) have no recording yet: {', '.join(bare)}")
    old = [m["id"] for m in metas if m.get("backup")]
    if old:
        out.append(f"{len(old)} lecture(s) on a backup (site says 'old data'): {', '.join(old)}")
    return out


def today_cards():
    """The ledger re-read from every flow's files, then the owner's cards (decisions.py). Writes ledger.db only."""
    import decisions
    import ledger
    db = ledger.connect()
    try:
        n = ledger.sync(db=db)
        cards = decisions.refresh(db=db)
    finally:
        db.close()
    return [f"ledger: {n}", f"{len(cards)} decisions wait on the Today screen (py dm.py page)"]


def noise(line):
    """import_all lines that say nothing happened."""
    return (line.startswith("skip ") and ("not a numbered lesson" in line or "no doctor folder" in line))         or "already queued" in line or "not aligned" in line


def main(argv):
    dry = "--dry" in argv
    tele = "--no-telegram" not in argv
    upload = "--no-upload" not in argv
    sys.stdout.reconfigure(encoding="utf-8")
    import doctors_folder
    import queue_db
    q = queue_db.Queue()
    report = []
    step(report, "folder", folder_look)
    step(report, "paths", doctors_folder.repair_paths if not dry else lambda: [])
    if tele:
        import auto_doctors
        step(report, "auto doctors (Telegram)", lambda: auto_doctors.sync(q, dry=dry))
    if dry:
        step(report, "folder import (what would change)", lambda: [
            f"{x['action']}: {x['title']} ({x['doctor_folder']})" for x in doctors_folder.plan()[0]
            if not x["action"].startswith(("skip", "exists"))] or ["nothing new in the folder"])
    else:
        step(report, "folder import", lambda: [ln for ln in doctors_folder.import_all(q) if not noise(ln)])
        if nagib_forms_changed():
            step(report, "Nagib quizzes", nagib_quizzes_run)
        if tele:
            step(report, "waiting Telegram recordings", lambda: waiting_telegram(q, dry))
        step(report, "site files", site_files)
        if upload:
            import upload_media
            step(report, "uploads", upload_media.start_background)
    step(report, "state", lambda: state(q))
    if not dry:
        step(report, "ledger and decisions", today_cards)
    for name, lines in report:
        print(f"== {name}")
        for ln in lines:
            print("  " + ln)
    waiting = [ln for _, lines in report for ln in lines if "still being written" in ln or "FAILED" in ln or "NOT read" in ln]
    if not dry and not waiting:
        import doctors_watch
        doctors_watch.PENDING.unlink(missing_ok=True)
        print("== pending list cleared")
    elif waiting:
        print("== pending list kept (something is unfinished above); run Update data again")


if __name__ == "__main__":
    main(sys.argv[1:])

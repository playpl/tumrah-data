"""Transcription jobs run outside the dispatcher (2026-11-09: the running dispatcher kept the old whole-file prompt).

    py oob_transcribe.py start cns-008 cns-009 ...   hold the queue rows, prepare with the current code, launch workers
    py oob_transcribe.py finish                      check each finished job; passed -> queue row passed, links queued
"""
import json
import subprocess
import sys
from pathlib import Path

import queue_db
from flows import REGISTRY

ROOT = Path(__file__).resolve().parent
FLEET = [sys.executable, r"C:\Users\Ahmed\agy-fleet\fleet.py"]
NOTE = "out-of-band chunked transcription (Claude)"


def start(ids, account="zero"):
    q = queue_db.Queue()
    flow = REGISTRY["transcribe"]
    for lid in ids:
        jid = f"transcribe:{lid}"
        q.db.execute("UPDATE jobs SET status='held', note=?, pid=NULL WHERE id=?", (NOTE, jid))
        job = {"id": jid, "flow": "transcribe", "key": lid, "payload": {"lecture": lid}}
        d = ROOT / "jobs" / "transcribe" / lid
        for f in [*(d / "chunks").glob("*.txt"), d / "transcript.txt", d / "timing.jsonl", d / "result.json"]:
            f.unlink(missing_ok=True)
        prompt = flow.prepare(job, d)
        log = open(d / "fleet.log", "w", encoding="utf-8")
        subprocess.Popen(FLEET + ["run", "-a", account, "--cwd", str(d), "-f", str(prompt), "--out", str(d / "result.json"),
                                  "--timeout", str(flow.timeout)], stdout=log, stderr=subprocess.STDOUT, cwd=d,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(lid, "started")
    q.close()


def finish():
    q = queue_db.Queue()
    flow = REGISTRY["transcribe"]
    for r in q.db.execute("SELECT id, key FROM jobs WHERE flow='transcribe' AND status='held' AND note=?", (NOTE,)).fetchall():
        d = ROOT / "jobs" / "transcribe" / r["key"]
        if not (d / "result.json").exists():
            print(r["key"], "still running")
            continue
        job = {"id": r["id"], "flow": "transcribe", "key": r["key"], "payload": {"lecture": r["key"]}}
        errors = flow.check(job, d)
        if errors:
            print(r["key"], "failed:", errors[:2])
            continue
        q.finish(r["id"], "passed")
        for name, jobs in flow.then(job, d):
            q.add_jobs(name, jobs)
        print(r["key"], "passed; linking queued")
    q.close()


if __name__ == "__main__":
    start(sys.argv[2:]) if sys.argv[1] == "start" else finish()

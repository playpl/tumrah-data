"""Jobs run outside the dispatcher with the current code (2026-11-09: the running dispatcher kept old prompts, and its
stop flag left place and MCQ work waiting).

    py oob_transcribe.py start <account> <flow:key> ...   hold the queue rows, prepare with today's code, launch workers
    py oob_transcribe.py finish                            check each finished job: passed -> row passed, next steps queued
"""
import json
import subprocess
import sys
from pathlib import Path

import queue_db
from flows import REGISTRY

ROOT = Path(__file__).resolve().parent
FLEET = [sys.executable, r"C:\Users\Ahmed\agy-fleet\fleet.py"]
NOTE = "out-of-band chunked transcription (Claude)"  # rows started here carry this note (the name is historical)


def start(account, ids):
    q = queue_db.Queue()
    for jid in ids:
        if ":" not in jid:
            jid = f"transcribe:{jid}"
        row = q.db.execute("SELECT id, flow, key, payload FROM jobs WHERE id=?", (jid,)).fetchone()
        flow = REGISTRY[row["flow"]]
        q.db.execute("UPDATE jobs SET status='held', note=?, pid=NULL WHERE id=?", (NOTE, jid))
        job = {"id": jid, "flow": row["flow"], "key": row["key"], "payload": json.loads(row["payload"])}
        d = ROOT / "jobs" / row["flow"] / row["key"]
        d.mkdir(parents=True, exist_ok=True)
        if row["flow"] == "transcribe":
            for f in [*(d / "chunks").glob("*.txt"), d / "transcript.txt", d / "timing.jsonl"]:
                f.unlink(missing_ok=True)
        (d / "result.json").unlink(missing_ok=True)
        prompt = flow.prepare(job, d)
        log = open(d / "fleet.log", "w", encoding="utf-8")
        cmd = FLEET + ["run", "-a", account, "--cwd", str(d), "-f", str(prompt), "--out", str(d / "result.json"),
                       "--timeout", str(getattr(flow, "timeout", 30))]
        if getattr(flow, "model", None):
            cmd += ["--model", flow.model]
        subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=d, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(jid, "started on", account)
    q.close()


def finish():
    q = queue_db.Queue()
    for r in q.db.execute("SELECT id, flow, key, payload FROM jobs WHERE status='held' AND note=?", (NOTE,)).fetchall():
        flow = REGISTRY[r["flow"]]
        d = ROOT / "jobs" / r["flow"] / r["key"]
        if not (d / "result.json").exists():
            print(r["id"], "still running")
            continue
        job = {"id": r["id"], "flow": r["flow"], "key": r["key"], "payload": json.loads(r["payload"])}
        errors = flow.check(job, d)
        if errors:
            print(r["id"], "failed:", errors[:2])
            continue
        q.finish(r["id"], "passed")
        for name, jobs in (flow.then(job, d) if hasattr(flow, "then") else []):
            q.add_jobs(name, jobs)
        print(r["id"], "passed; next steps queued")
    q.close()


if __name__ == "__main__":
    if sys.argv[1] == "start":
        start(sys.argv[2], sys.argv[3:])
    else:
        finish()

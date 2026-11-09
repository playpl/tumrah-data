"""Jobs done by Claude Haiku subagents while the Gemini fleet is out of quota (owner, 2026-11-09: Haiku, most
token-efficient run that is still good enough).

    py haiku_run.py prepare <flow:key> ...   hold the queue rows, prepare each job folder with today's code, print
                                             each folder and its prompt file (one Haiku subagent per folder)
    py haiku_run.py finish                   run each held job's checker: passed -> row passed, next steps queued;
                                             failed -> errors printed, row stays held for another try
"""
import json
import sys
from pathlib import Path

import queue_db
from flows import REGISTRY

ROOT = Path(__file__).resolve().parent
NOTE = "haiku subagent (Claude)"


def job_of(row):
    return {"id": row["id"], "flow": row["flow"], "key": row["key"], "payload": json.loads(row["payload"])}


def prepare(ids):
    q = queue_db.Queue()
    for jid in ids:
        row = q.db.execute("SELECT id, flow, key, payload FROM jobs WHERE id=?", (jid,)).fetchone()
        if row is None:
            print(jid, "not in the queue")
            continue
        q.db.execute("UPDATE jobs SET status='held', note=?, pid=NULL WHERE id=?", (NOTE, jid))
        d = ROOT / "jobs" / row["flow"] / row["key"]
        d.mkdir(parents=True, exist_ok=True)
        prompt = REGISTRY[row["flow"]].prepare(job_of(row), d)
        print(jid, "|", d, "|", prompt)
    q.db.commit()
    q.close()


def finish():
    q = queue_db.Queue()
    for r in q.db.execute("SELECT id, flow, key, payload FROM jobs WHERE status='held' AND note=?", (NOTE,)).fetchall():
        flow, job = REGISTRY[r["flow"]], job_of(r)
        d = ROOT / "jobs" / r["flow"] / r["key"]
        try:
            errors = flow.check(job, d)
        except Exception as e:  # noqa: BLE001 - no usable output yet
            errors = [f"{type(e).__name__}: {e}"]
        if errors:
            print(r["id"], "failed:", len(errors), "errors;", "; ".join(errors[:3])[:400])
            continue
        q.finish(r["id"], "passed")
        for name, jobs in (flow.then(job, d) if hasattr(flow, "then") else []):
            q.add_jobs(name, jobs)
        print(r["id"], "passed")
    q.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    prepare(sys.argv[2:]) if sys.argv[1] == "prepare" else finish()

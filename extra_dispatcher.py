"""A second dispatcher next to the running one (owner 2026-11-14: "exhaust the quota"): more slots without stopping the
first. Claims are atomic, so two dispatchers never run the same job. Stops with jobs/stop.flag like the first.

    py extra_dispatcher.py zero=2 work=2 personal=2 other=2
"""
import json
import sys
from pathlib import Path

import dispatch
import flows
import queue_db

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    slots = {a: int(n) for a, n in (x.split("=") for x in sys.argv[1:])}
    q = queue_db.Queue()
    d = dispatch.Dispatcher(q, slots=slots, lanes=cfg["lanes"], flows=flows.REGISTRY, jobs_root=ROOT / "jobs")
    print(f"extra dispatcher: {slots}, lanes {cfg['lanes']}", flush=True)
    print(json.dumps(d.run()))
    q.close()

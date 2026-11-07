"""The dispatcher: one process, one thread per fleet slot, one owner per job.

Each thread claims a job for its account, lets the flow write the job folder and prompt, runs
`fleet.py run -a <account>` in that folder, then runs the flow's own checker. A worker's PASS is never
trusted. A quota error frees the job (no try counted) and rests the account through the fleet's cooldown.
"""
import json
import subprocess
import sys
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path

import queue_db

FLEET = Path(r"C:\Users\Ahmed\agy-fleet")


def cooling(state_path, account):
    """True while the fleet's state.json rests this account after a quota error."""
    try:
        until = json.loads(Path(state_path).read_text(encoding="utf-8")).get("cooldown", {}).get(account)
    except (OSError, ValueError):
        return False
    return bool(until) and datetime.fromisoformat(until) > datetime.now()


class Dispatcher:
    def __init__(self, queue, slots, lanes, flows, jobs_root, fleet_cmd=None, fleet_state=FLEET / "state.json"):
        self.qpath, self.slots, self.lanes, self.flows = queue.path, slots, lanes, flows
        self.jobs_root = Path(jobs_root)
        self.fleet_cmd = fleet_cmd or ["py", str(FLEET / "fleet.py")]
        self.fleet_state = fleet_state
        self.stop = threading.Event()
        self.stats, self._lock = Counter(), threading.Lock()

    def stopping(self):
        return self.stop.is_set() or (self.jobs_root / "stop.flag").exists()

    def work(self, q, job, account):
        flow = self.flows.get(job["flow"])
        if flow is None:
            q.finish(job["id"], "held", f"no flow named {job['flow']}")
            return "held"
        job_dir = self.jobs_root / job["flow"] / job["key"]
        job_dir.mkdir(parents=True, exist_ok=True)
        prompt = flow.prepare(job, job_dir)
        result = job_dir / "result.json"
        result.unlink(missing_ok=True)
        cmd = self.fleet_cmd + ["run", "-a", account, "--cwd", str(job_dir), "-f", str(prompt), "--out", str(result),
                                "--timeout", str(getattr(flow, "timeout", 30))]
        if getattr(flow, "model", None):
            cmd += ["--model", flow.model]
        run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        (job_dir / "fleet.log").write_text(run.stdout[-4000:] + run.stderr[-4000:], encoding="utf-8")
        try:
            r = json.loads(result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            r = {"status": "ERROR", "error": (run.stderr or run.stdout).strip()[-300:]}
        if r.get("status") != "SUCCESS":
            if r.get("failure") == "quota" or cooling(self.fleet_state, account):
                q.release(job["id"])
                return "released"
            q.finish(job["id"], "failed", f"fleet: {r.get('failure') or r.get('error') or r.get('status')}"[:500])
            return "failed"
        errors = flow.check(job, job_dir)
        if errors:
            q.finish(job["id"], "failed", "; ".join(errors)[:500])
            return "failed"
        q.finish(job["id"], "passed")
        for flow_name, jobs in (flow.then(job, job_dir) if hasattr(flow, "then") else []):
            q.add_jobs(flow_name, jobs)  # the next step of a chain (transcribe, then clean and link)
        return "passed"

    def slot(self, account, once):
        lane = self.lanes.get(account)
        q = queue_db.Queue(self.qpath)
        try:
            while not self.stopping():
                if cooling(self.fleet_state, account):
                    if once:
                        return
                    self.stop.wait(60)
                    continue
                job = q.claim(lane, account)
                if job is None:
                    busy = sum(c.get("running", 0) for c in q.progress().values())
                    if once and not busy:
                        return
                    self.stop.wait(0.2 if once else 30)
                    continue
                outcome = self.work(q, job, account)
                with self._lock:
                    self.stats[outcome] += 1
        finally:
            q.close()

    def run(self, once=False):
        """once: return when no job is queued or running (tests, one-shot runs); else run until stop.flag."""
        q = queue_db.Queue(self.qpath)
        q.recover()
        q.close()
        threads = [threading.Thread(target=self.slot, args=(account, once), name=f"{account}-{i}", daemon=True)
                   for account, n in self.slots.items() for i in range(n)]
        for t in threads:
            t.start()
        try:
            for t in threads:
                while t.is_alive():
                    t.join(1)
        except KeyboardInterrupt:
            self.stop.set()
            print("stopping after the current jobs", file=sys.stderr)
            for t in threads:
                t.join()
        return dict(self.stats)

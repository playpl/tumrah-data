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
        if hasattr(flow, "expand"):  # a fan-out step done by code, no worker (transcribe -> one piece job per piece)
            for flow_name, jobs in flow.expand(job):
                q.add_jobs(flow_name, jobs)
            q.finish(job["id"], "passed")
            return "passed"
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
            # A dropped connection often comes after the worker already wrote its output: the checker decides.
            try:
                saved = not flow.check(job, job_dir)
            except Exception:  # noqa: BLE001 - no usable output: an ordinary failure
                saved = False
            if not saved:
                q.finish(job["id"], "failed", f"fleet: {r.get('failure') or r.get('error') or r.get('status')}"[:500])
                return "failed"
            r["status"] = "SUCCESS"
        errors = flow.check(job, job_dir)
        if errors:
            q.finish(job["id"], "failed", "; ".join(errors)[:500])
            return "failed"
        q.finish(job["id"], "passed")
        for flow_name, jobs in (flow.then(job, job_dir) if hasattr(flow, "then") else []):
            q.add_jobs(flow_name, jobs)  # the next step of a chain (transcribe, then clean and link)
        return "passed"

    def work_group(self, q, jobs, account):
        """Several jobs of one flow in one fleet run: an orchestrator starts one subagent per job folder (the flow's
        `orchestrate(dirs)` writes its prompt). Each job is then checked on its own, as in `work`."""
        flow = self.flows[jobs[0]["flow"]]
        dirs = []
        for job in jobs:
            d = self.jobs_root / job["flow"] / job["key"]
            d.mkdir(parents=True, exist_ok=True)
            flow.prepare(job, d)
            dirs.append(d)
        od = self.jobs_root / jobs[0]["flow"] / "_orchestrator" / f"{account}-{jobs[0]['key']}"
        od.mkdir(parents=True, exist_ok=True)
        prompt = od / "prompt.md"
        prompt.write_text(flow.orchestrate(dirs), encoding="utf-8")
        result = od / "result.json"
        result.unlink(missing_ok=True)
        cmd = self.fleet_cmd + ["run", "-a", account, "--cwd", str(od), "-f", str(prompt), "--out", str(result),
                                "--timeout", str(getattr(flow, "timeout", 30))]
        for d in dirs:
            cmd += ["--add-dir", str(d)]
        if getattr(flow, "model", None):
            cmd += ["--model", flow.model]
        run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        (od / "fleet.log").write_text(run.stdout[-4000:] + run.stderr[-4000:], encoding="utf-8")
        try:
            r = json.loads(result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            r = {"status": "ERROR", "error": (run.stderr or run.stdout).strip()[-300:]}
        quota = r.get("status") != "SUCCESS" and (r.get("failure") == "quota" or cooling(self.fleet_state, account))
        outcomes = []
        for job, d in zip(jobs, dirs):
            try:
                errors = flow.check(job, d)  # a worker's PASS is never trusted; a dropped run may still have written
            except Exception as e:  # noqa: BLE001 - no usable output
                errors = [f"{type(e).__name__}: {e}"]
            if errors and quota:
                q.release(job["id"])
                outcomes.append("released")
            elif errors:
                why = "" if r.get("status") == "SUCCESS" else f"fleet: {r.get('failure') or r.get('error') or r.get('status')}; "
                q.finish(job["id"], "failed", (why + "; ".join(errors))[:500])
                outcomes.append("failed")
            else:
                q.finish(job["id"], "passed")
                for flow_name, nxt in (flow.then(job, d) if hasattr(flow, "then") else []):
                    q.add_jobs(flow_name, nxt)
                outcomes.append("passed")
        return outcomes

    def slot(self, account, once):
        lane = self.lanes.get(account)
        q = queue_db.Queue(self.qpath)
        try:
            while not self.stopping():
                if cooling(self.fleet_state, account):
                    # Code-only steps (flows with `expand`) need no account: run them while the account rests.
                    code = [name for name, f in self.flows.items() if hasattr(f, "expand")]
                    job = next((j for j in (q.claim(name, account, only=True) for name in code) if j), None)
                    if job:
                        with self._lock:
                            self.stats[self.work(q, job, account)] += 1
                        continue
                    if once:
                        return
                    self.stop.wait(60)
                    continue
                # a lane is one flow or a list (owner 2026-11-14: one account per kind of work); its own flows first,
                # then any queued flow, so no account sits idle
                lanes = lane if isinstance(lane, list) else [lane]
                job = next((j for j in (q.claim(name, account, only=True) for name in lanes) if j), None)                     or q.claim(lanes[0], account)
                flow = self.flows.get(job["flow"]) if job else None
                if job and getattr(flow, "group", 0) > 1:  # one orchestrator, one subagent per job folder
                    group = [job] + [j for j in (q.claim(job["flow"], account, only=True)
                                                 for _ in range(flow.group - 1)) if j]
                    try:
                        outcomes = self.work_group(q, group, account)
                    except Exception as e:  # noqa: BLE001 - a broken group never kills its slot
                        for j in group:
                            q.finish(j["id"], "failed", f"dispatcher: {type(e).__name__}: {e}"[:500])
                        outcomes = ["failed"] * len(group)
                    with self._lock:
                        self.stats.update(outcomes)
                    continue
                if job is None:
                    busy = sum(c.get("running", 0) for c in q.progress().values())
                    if once and not busy:
                        return
                    self.stop.wait(0.2 if once else 30)
                    continue
                try:
                    outcome = self.work(q, job, account)
                except Exception as e:  # noqa: BLE001 - a broken job never kills its slot (2026-11-08)
                    q.finish(job["id"], "failed", f"dispatcher: {type(e).__name__}: {e}"[:500])
                    outcome = "failed"
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

"""The job queue: one SQLite file, one owner per job.

Lanes are flows (config.json `lanes` maps each fleet account to its flow). An account claims from its own
lane first, then from the longest lane. A failed job goes back to the queue twice, then it is held.
Named queue_db.py because queue.py would shadow the stdlib `queue` module.
"""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

DB = Path(__file__).resolve().parent / "queue.db"
MAX_RETRIES = 2
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, flow TEXT, key TEXT, payload TEXT, status TEXT DEFAULT 'queued',
  account TEXT, pid INTEGER, tries INTEGER DEFAULT 0, note TEXT DEFAULT '', added REAL, started REAL, finished REAL);
CREATE INDEX IF NOT EXISTS jobs_lane ON jobs(status, flow, added);
"""


def pid_alive(pid):
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)  # never on Windows: there it terminates the process
        return True
    except OSError:
        return False


class Queue:
    def __init__(self, path=DB):
        self.path = Path(path)
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def add_jobs(self, flow, jobs):
        """jobs: [{"key", "payload"}]. A key already queued for this flow adds nothing."""
        now = time.time()
        cur = self.db.executemany(
            "INSERT OR IGNORE INTO jobs(id, flow, key, payload, added) VALUES(?,?,?,?,?)",
            [(f"{flow}:{j['key']}", flow, j["key"], json.dumps(j.get("payload")), now) for j in jobs])
        return cur.rowcount

    def claim(self, lane, account, only=False):
        """The oldest queued job of the lane's flow, else of the flow with most queued jobs (not with only=True)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT id FROM jobs WHERE status='queued' AND flow=? ORDER BY added, id LIMIT 1",
                                  (lane,)).fetchone()
            if row is None and not only:
                row = self.db.execute(
                    "SELECT id FROM jobs WHERE status='queued' AND flow=(SELECT flow FROM jobs WHERE status='queued' "
                    "GROUP BY flow ORDER BY COUNT(*) DESC, flow LIMIT 1) ORDER BY added, id LIMIT 1").fetchone()
            if row is None:
                self.db.execute("COMMIT")
                return None
            self.db.execute("UPDATE jobs SET status='running', account=?, pid=?, started=? WHERE id=?",
                            (account, os.getpid(), time.time(), row["id"]))
            job = self.db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        out = dict(job)
        out["payload"] = json.loads(out["payload"]) if out["payload"] else None
        return out

    def finish(self, job_id, status, note=""):
        """passed | held end the job; failed requeues it until MAX_RETRIES, then holds it."""
        if status not in ("passed", "failed", "held"):
            raise ValueError(status)
        if status == "failed":
            tries = self.db.execute("SELECT tries FROM jobs WHERE id=?", (job_id,)).fetchone()["tries"] + 1
            status = "queued" if tries <= MAX_RETRIES else "held"
            self.db.execute("UPDATE jobs SET status=?, tries=?, note=?, pid=NULL, finished=? WHERE id=?",
                            (status, tries, note, time.time(), job_id))
        else:
            self.db.execute("UPDATE jobs SET status=?, note=?, pid=NULL, finished=? WHERE id=?",
                            (status, note, time.time(), job_id))

    def release(self, job_id):
        """Back to the queue with no try counted (the account hit its quota, not the job)."""
        self.db.execute("UPDATE jobs SET status='queued', account=NULL, pid=NULL WHERE id=? AND status='running'", (job_id,))

    def recover(self):
        """Jobs left running by a process that died go back to the queue. Run when the dispatcher starts."""
        dead = [r["id"] for r in self.db.execute("SELECT id, pid FROM jobs WHERE status='running'")
                if not r["pid"] or not pid_alive(r["pid"])]
        for job_id in dead:
            self.release(job_id)
        return len(dead)

    def progress(self):
        out = {}
        for r in self.db.execute("SELECT flow, status, COUNT(*) n FROM jobs GROUP BY flow, status"):
            out.setdefault(r["flow"], {})[r["status"]] = r["n"]
        return out

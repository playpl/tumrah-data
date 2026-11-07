import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dispatch  # noqa: E402
import queue_db  # noqa: E402

# A stand-in for `fleet.py run`: reads behaviour from the job folder, writes out.txt and --out like the real CLI.
FAKE_FLEET = r'''
import json, sys
from datetime import datetime, timedelta
from pathlib import Path
a = sys.argv[1:]
arg = lambda k: a[a.index(k) + 1]
account, cwd, out, state = arg("-a"), Path(arg("--cwd")), arg("--out"), Path(arg("--state"))
plan = json.loads((cwd / "plan.json").read_text())
runs = cwd / "runs.txt"
n = len(runs.read_text().splitlines()) if runs.exists() else 0
runs.write_text((runs.read_text() if runs.exists() else "") + account + "\n")
step = plan[min(n, len(plan) - 1)]
if step == "quota" or (isinstance(step, dict) and account in step.get("quota_on", [])):
    s = json.loads(state.read_text()) if state.exists() else {"cooldown": {}}
    s["cooldown"][account] = (datetime.now() + timedelta(minutes=60)).isoformat(timespec="seconds")
    state.write_text(json.dumps(s))
    sys.exit("no account available (all tried or cooling down)")
text = step if isinstance(step, str) else step["text"]
(cwd / "out.txt").write_text(text)
Path(out).write_text(json.dumps({"status": "SUCCESS", "response": "PASS"}))
'''


class EchoFlow:
    """Prompt asks for out.txt; the checker (not the worker's PASS) decides: out.txt must say "good"."""
    lane = "pointers"

    def prepare(self, job, job_dir):
        (job_dir / "plan.json").write_text(json.dumps(job["payload"]["plan"]))
        (job_dir / "prompt.md").write_text("write out.txt")
        return job_dir / "prompt.md"

    def check(self, job, job_dir):
        text = (job_dir / "out.txt").read_text() if (job_dir / "out.txt").exists() else ""
        return [] if text == "good" else [f"out.txt says {text!r}"]


class TestDispatcher(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        self.fake = root / "fake_fleet.py"
        self.fake.write_text(FAKE_FLEET)
        self.state = root / "state.json"
        self.q = queue_db.Queue(root / "queue.db")
        self.d = dispatch.Dispatcher(
            self.q, slots={"work": 2, "personal": 1}, lanes={"work": "pointers", "personal": "books"},
            flows={"pointers": EchoFlow(), "books": EchoFlow()}, jobs_root=root / "jobs",
            fleet_cmd=[sys.executable, str(self.fake), "--state", str(self.state)], fleet_state=self.state)

    def tearDown(self):
        self.q.close()
        self.dir.cleanup()

    def add(self, flow, n, plan):
        self.q.add_jobs(flow, [{"key": f"j{i}", "payload": {"plan": plan}} for i in range(n)])

    def runs(self, flow, key):
        return (Path(self.dir.name) / "jobs" / flow / key / "runs.txt").read_text().split()

    def test_jobs_spread_over_every_slot_and_pass(self):
        self.add("pointers", 6, ["good"])
        self.add("books", 2, ["good"])
        self.assertEqual(self.d.run(once=True), {"passed": 8})
        self.assertEqual(self.q.progress(), {"pointers": {"passed": 6}, "books": {"passed": 2}})
        accounts = {self.runs(f, f"j{i}")[0] for f, n in (("pointers", 6), ("books", 2)) for i in range(n)}
        self.assertEqual(accounts, {"work", "personal"})

    def test_checker_failure_retries_and_then_passes(self):
        self.add("pointers", 1, ["bad", "good"])
        self.d.run(once=True)
        self.assertEqual(self.q.progress(), {"pointers": {"passed": 1}})
        self.assertEqual(len(self.runs("pointers", "j0")), 2)

    def test_worker_pass_is_never_trusted(self):
        self.add("pointers", 1, ["bad"])
        self.d.run(once=True)
        self.assertEqual(self.q.progress(), {"pointers": {"held": 1}})
        self.assertEqual(len(self.runs("pointers", "j0")), 3)
        note = self.q.db.execute("SELECT note FROM jobs").fetchone()["note"]
        self.assertIn("out.txt says 'bad'", note)

    def test_quota_frees_the_job_and_rests_the_account(self):
        self.add("pointers", 2, ["good"])  # keeps work's two slots on their own lane, so personal claims the book
        self.add("books", 1, [{"text": "good", "quota_on": ["personal"]}])
        self.d.run(once=True)
        self.assertEqual(self.q.progress(), {"pointers": {"passed": 2}, "books": {"passed": 1}})
        self.assertEqual(self.runs("books", "j0"), ["personal", "work"])
        job = self.q.db.execute("SELECT tries, account FROM jobs WHERE flow='books'").fetchone()
        self.assertEqual((job["tries"], job["account"]), (0, "work"))
        self.assertTrue(dispatch.cooling(self.state, "personal"))
        self.assertFalse(dispatch.cooling(self.state, "work"))

    def test_a_passed_job_queues_its_next_step(self):
        class Chain(EchoFlow):
            def then(self, job, job_dir):
                return [("books", [{"key": "next-" + job["key"], "payload": job["payload"]}])]
        self.d.flows["pointers"] = Chain()
        self.add("pointers", 1, ["good"])
        self.d.run(once=True)
        self.assertEqual(self.q.progress(), {"pointers": {"passed": 1}, "books": {"passed": 1}})

    def test_unknown_flow_is_held_not_run(self):
        self.q.add_jobs("nope", [{"key": "x", "payload": {}}])
        self.d.run(once=True)
        self.assertEqual(self.q.progress(), {"nope": {"held": 1}})


if __name__ == "__main__":
    unittest.main()

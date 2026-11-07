import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import queue_db as q  # noqa: E402

DEAD_PID = 2 ** 22 + 7  # no such process


class TestQueue(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "queue.db"
        self.q = q.Queue(self.path)

    def tearDown(self):
        self.q.close()
        self.dir.cleanup()

    def jobs(self, flow, n, start=0):
        return [{"key": f"k{i}", "payload": {"i": i}} for i in range(start, start + n)]

    def test_repeat_add_adds_nothing(self):
        self.assertEqual(self.q.add_jobs("pointers", self.jobs("pointers", 3)), 3)
        self.assertEqual(self.q.add_jobs("pointers", self.jobs("pointers", 3)), 0)
        self.assertEqual(self.q.add_jobs("pointers", self.jobs("pointers", 4)), 1)
        self.assertEqual(self.q.progress(), {"pointers": {"queued": 4}})

    def test_own_lane_first_then_longest_lane(self):
        self.q.add_jobs("pointers", self.jobs("pointers", 1))
        self.q.add_jobs("books", self.jobs("books", 3))
        self.q.add_jobs("links", self.jobs("links", 2))
        self.assertEqual(self.q.claim("pointers", "work")["flow"], "pointers")
        self.assertEqual(self.q.claim("pointers", "work")["flow"], "books")
        self.assertEqual(self.q.claim("transcribe", "zero")["flow"], "books")
        job = self.q.claim("links", "other")
        self.assertEqual((job["flow"], job["key"], job["payload"]), ("links", "k0", {"i": 0}))

    def test_empty_queue_gives_none(self):
        self.assertIsNone(self.q.claim("pointers", "work"))

    def test_two_threads_never_claim_the_same_job(self):
        self.q.add_jobs("pointers", self.jobs("pointers", 200))
        got, lock = [], threading.Lock()

        def worker():
            mine = q.Queue(self.path)
            while (job := mine.claim("pointers", "work")) is not None:
                with lock:
                    got.append(job["id"])
            mine.close()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(got), 200)
        self.assertEqual(len(set(got)), 200)

    def test_failure_retries_twice_then_holds(self):
        self.q.add_jobs("books", self.jobs("books", 1))
        for _ in range(2):
            job = self.q.claim("books", "personal")
            self.q.finish(job["id"], "failed", "bad span")
        job = self.q.claim("books", "personal")
        self.assertEqual(job["tries"], 2)
        self.q.finish(job["id"], "failed", "bad span")
        self.assertIsNone(self.q.claim("books", "personal"))
        self.assertEqual(self.q.progress(), {"books": {"held": 1}})

    def test_release_frees_a_job_without_a_try(self):
        self.q.add_jobs("books", self.jobs("books", 1))
        job = self.q.claim("books", "personal")
        self.q.release(job["id"])
        self.assertEqual(self.q.claim("books", "work")["tries"], 0)

    def test_job_of_a_dead_process_returns_on_start(self):
        self.q.add_jobs("links", self.jobs("links", 2))
        self.q.claim("links", "other")
        alive = self.q.claim("links", "other")
        self.q.db.execute("UPDATE jobs SET pid=? WHERE id!=?", (DEAD_PID, alive["id"]))
        self.assertEqual(self.q.recover(), 1)
        self.assertEqual(self.q.progress(), {"links": {"queued": 1, "running": 1}})
        self.assertEqual(alive["pid"], os.getpid())


if __name__ == "__main__":
    unittest.main()

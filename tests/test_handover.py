import json
import sys
import tempfile
import unittest
from pathlib import Path

from bson import ObjectId

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import intake  # noqa: E402
import queue_db  # noqa: E402
from test_page import FakeReader  # noqa: E402


class TestIntake(unittest.TestCase):
    def test_each_file_becomes_pointer_jobs_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "handover"
            folder.mkdir()
            docs = [{"_id": ObjectId(), "question_text": f"Q{i}", "test_type": "doctor", "correct_option": "B",
                     "options": {"A": {"text": "a"}, "B": {"text": "b"}}} for i in range(30)]
            docs.append({"_id": ObjectId(), "question_text": "has pointer", "book_found": True, "options": {}})
            (folder / "2026-11-07-year2-cns-1.json").write_text(json.dumps({"module": "year2-cns", "questions": [str(d["_id"]) for d in docs]}))
            q = queue_db.Queue(Path(tmp) / "queue.db")
            got = intake.intake(FakeReader({"questions": docs}), q, ["doctor"], folder)
            self.assertEqual(got, {"2026-11-07-year2-cns-1.json": 2})
            self.assertEqual(intake.intake(FakeReader({"questions": docs}), q, ["doctor"], folder), {})
            job = q.claim("pointers", "work")
            row = job["payload"]["batch"][0]
            self.assertEqual((row["options"], row["correct_index"], row["set"]), (["a", "b"], 1, "doctor"))
            self.assertEqual(sum(len(j["payload"]["batch"]) for j in [job, q.claim("pointers", "work")]), 30)
            q.close()


if __name__ == "__main__":
    unittest.main()

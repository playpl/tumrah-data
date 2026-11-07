import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bson import ObjectId

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import lectures  # noqa: E402
import page  # noqa: E402
import queue_db  # noqa: E402
from flows.common import write_jsonl  # noqa: E402
from test_lecture_checks import RAW, TestClean  # noqa: E402


class FakeReader:
    def __init__(self, docs):
        self.docs = docs

    def find(self, coll, flt=None, projection=None, limit=50, sort=None, skip=0):
        rows = self.docs.get(coll, [])
        ids = (flt or {}).get("_id", {}).get("$in") if isinstance((flt or {}).get("_id"), dict) else None
        if ids is not None:
            rows = [d for d in rows if d["_id"] in ids]
        return rows[:limit]


class TestPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [mock.patch.object(page, "HANDOVER", root / "handover"),
                        mock.patch.object(lectures, "LECTURES", root / "lectures")]
        for p in self.patches:
            p.start()
        self.q = queue_db.Queue(root / "queue.db")

    def tearDown(self):
        self.q.close()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_hand_over_skips_questions_that_have_pointers(self):
        a, b = ObjectId(), ObjectId()
        reader = FakeReader({"questions": [{"_id": a}, {"_id": b, "book_found": True}]})
        out = page.handover(reader, "year2-cns", [str(a), str(b), "not-an-id"])
        self.assertEqual((out["handed_over"], out["skipped_with_pointers"]), (1, 1))
        saved = json.loads((page.HANDOVER / out["file"]).read_text())
        self.assertEqual(saved, {"module": "year2-cns", "questions": [str(a)]})

    def test_questions_are_paged_with_a_cursor(self):
        docs = [{"_id": ObjectId(), "question_text": "q" * 300} for _ in range(page.PAGE_SIZE)]
        out = page.questions(FakeReader({"questions": docs}))
        self.assertEqual(len(out["rows"]), page.PAGE_SIZE)
        self.assertEqual(out["next"], str(docs[-1]["_id"]))
        self.assertEqual(len(out["rows"][0]["text"]), 220)
        self.assertIsNone(page.questions(FakeReader({"questions": docs[:3]}))["next"])

    def test_book_percent_aligned(self):
        pages = lambda a, b: [{"book_id": "b1", "page": n, "text": "x"} for n in range(a, b)]
        self.q.add_jobs("books", [{"key": "1", "payload": {"module": "m", "book_id": "b1", "pages": pages(1, 6)}},
                                  {"key": "2", "payload": {"module": "m", "book_id": "b1", "pages": pages(6, 8)}}])
        job = self.q.claim("books", "personal")
        self.q.finish(job["id"], "passed")
        self.assertEqual(page.books(self.q), [{"module": "m", "book": "b1", "pages": 7, "aligned": 5, "held": 0, "percent": 71.4}])

    def lecture(self, raw, clean, fixes):
        lectures.save({"id": "l1", "module": "m", "title": "T", "transcribe": False, "duration_s": 120})
        d = lectures.folder("l1")
        (d / "raw.txt").write_text(raw, encoding="utf-8")
        (d / "clean.txt").write_text(clean, encoding="utf-8")
        write_jsonl(d / "fixes.jsonl", fixes)
        (d / "audio.ogg").write_bytes(b"OggS")
        return d

    def test_the_owner_takes_or_keeps_an_unsure_fix(self):
        raw = RAW.replace("raphe", "rafi")
        fix = {"at": "00:40", "heard": "rafi", "meant": "raphe", "confidence": 0.6, "reason": "nucleus name"}
        d = self.lecture(raw, TestClean.CLEAN.replace("raphe", "rafi"), [fix])
        self.assertEqual([f["index"] for f in page.pending_fixes("l1")], [0])
        self.assertEqual(page.decide_fix("l1", 0, take=True), {"saved": True})
        self.assertIn("raphe", (d / "clean.txt").read_text(encoding="utf-8"))
        self.assertEqual(page.pending_fixes("l1")[0]["decision"], "take")
        self.assertEqual(page.decide_fix("l1", 0, take=False), {"saved": True})
        self.assertNotIn("raphe", (d / "clean.txt").read_text(encoding="utf-8"))

    def test_turning_transcribe_on_queues_the_lecture(self):
        self.lecture(RAW, RAW, [])
        (lectures.folder("l1") / "raw.txt").unlink()
        self.assertEqual(page.set_transcribe("l1", True, self.q), {"transcribe": True})
        self.assertEqual(self.q.progress(), {"transcribe": {"queued": 1}})
        self.assertEqual(page.lecture_list()[0]["stage"], "waiting")


if __name__ == "__main__":
    unittest.main()

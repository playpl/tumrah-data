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
        self.assertEqual(page.books(self.q), [{"module": "m", "book": "b1", "pages": 7, "aligned": 5, "held": 0, "percent": 71.4,
                                               "title": None, "doctor": None}])

    def test_an_upload_must_be_a_whole_pdf(self):
        import io
        dest = Path(self.tmp.name) / "m" / "handout.pdf"
        with self.assertRaises(ValueError):
            page.save_upload(io.BytesIO(b"<html>"), 6, dest)
        with self.assertRaises(ValueError):
            page.save_upload(io.BytesIO(b"%PDF-1"), 60, dest)  # the upload broke off
        self.assertFalse(dest.exists())
        self.assertFalse(dest.with_name("handout.pdf.part").exists())
        page.save_upload(io.BytesIO(b"%PDF-1.7 x"), 10, dest)
        self.assertEqual(dest.read_bytes(), b"%PDF-1.7 x")

    def test_a_replaced_handout_and_its_lines_are_kept(self):
        import io
        root = Path(self.tmp.name)
        d = root / "modules" / "year2-cns"
        d.mkdir(parents=True)
        (d / "handout.pdf").write_bytes(b"%PDF old")
        (d / "lines.jsonl").write_text("{}\n", encoding="utf-8")
        with mock.patch.object(page, "ROOT", root), mock.patch.object(page, "module_codes", return_value=["year2-cns"]), \
                mock.patch.object(page, "background", return_value={"started": True}) as bg:
            out = page.put_handout("year2-cns", io.BytesIO(b"%PDF new"), 8)
            self.assertEqual(page.put_handout("year9-x", io.BytesIO(b"%PDF"), 4), {"error": "unknown module year9-x"})
        self.assertEqual(out, {"started": True, "replaced": True})
        self.assertEqual((d / "handout.pdf").read_bytes(), b"%PDF new")
        old = next((d / "old").iterdir())
        self.assertEqual(((old / "handout.pdf").read_bytes(), (old / "lines.jsonl").exists()), (b"%PDF old", True))
        self.assertEqual(bg.call_args.args[1:], (page.run_dm, "lines", "year2-cns"))

    def test_a_book_is_queued_with_its_doctor(self):
        import io
        root = Path(self.tmp.name)
        (root / "modules" / "year2-cns").mkdir(parents=True)
        with mock.patch.object(page, "ROOT", root), mock.patch.object(page, "module_codes", return_value=["year2-cns"]), \
                mock.patch.object(page, "background", return_value={"started": True}) as bg:
            a = {"module": "year2-cns", "book": "B101", "doctor": "dr-x", "title": "Neuro", "pages": "1-20"}
            self.assertIn("handout first", page.put_book(a, io.BytesIO(b"%PDF"), 4)["error"])
            (root / "modules" / "year2-cns" / "lines.jsonl").write_text("{}\n", encoding="utf-8")
            self.assertIn("book id", page.put_book({**a, "book": "../x"}, io.BytesIO(b"%PDF"), 4)["error"])
            self.assertEqual(page.put_book(a, io.BytesIO(b"%PDF"), 4), {"started": True})
        pdf = root / "modules" / "year2-cns" / "books" / "b101.pdf"
        self.assertTrue(pdf.exists())
        self.assertEqual(bg.call_args.args[2:], ("add", "books", "year2-cns", "--book", "b101", "--file", str(pdf),
                                                 "--pages", "1-20", "--doctor", "dr-x", "--title", "Neuro"))

    def test_the_owner_settles_a_key_conflict(self):
        bank = Path(self.tmp.name) / "bank"
        bank.mkdir()
        rows = [{"word_key": "k1", "question": "Q", "options": ["a", "b"], "votes": [3, 4], "total": 7, "key": 0,
                 "key_conflict": True, "sightings": [{"link": "https://t.me/c/1/2"}]},
                {"word_key": "k2", "question": "Q2", "options": ["a", "b"], "votes": [1, 0], "total": 1, "key": 0,
                 "key_conflict": False, "sightings": []}]
        (bank / "questions.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        with mock.patch.object(page, "BANK", bank), mock.patch.object(page, "DECISIONS", bank / "key_decisions.json"):
            self.assertEqual([c["id"] for c in page.conflicts()], ["k1"])
            self.assertEqual(page.decide_key("k1", 1), {"saved": True, "decided": 1})
            self.assertEqual(page.conflicts()[0]["decision"], 1)
            self.assertEqual(page.decide_key("k1", None), {"saved": True, "decided": 0})
            self.assertIsNone(page.conflicts()[0]["decision"])

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

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import checks  # noqa: E402
import highlights  # noqa: E402
import lectures  # noqa: E402
from flows import common  # noqa: E402
from flows import highlights as flow  # noqa: E402

M = "year2-cns"
TEXTS = ["Pain control", "The raphe magnus releases serotonin", "onto the dorsal horn cells", "FIGURE"]
LINES = [{"id": f"{M}:h:p12:l{n}", "module": M, "hash": "h", "page": 12, "printed": 4, "n": n, "text": t,
          "figure": "fig" if t == "FIGURE" else None} for n, t in enumerate(TEXTS, 1)]
LINES.append({"id": f"{M}:h:p30:l1", "module": M, "hash": "h", "page": 30, "printed": 22, "n": 1, "text": "far away",
              "figure": None})
ID = [ln["id"] for ln in LINES]
CLEAN = "[00:10] Today pain control.\n[01:00] Write MCQ on this: the raphe magnus, serotonin!\n[02:30] Again raphe magnus.\n"
PARTS = [{"part": 1, "sub": 0, "title": "Pain control", "start": 0, "end": 200, "line_ids": ID[:3]}]
QS = [{"qid": "q1", "kind": "doctor", "doctors": ["Dr A"], "stem": "s", "options": {"A": "x"}, "keyed": "x",
       "repeats": 1, "line_ids": [ID[1]]},
      {"qid": "q2", "kind": "other", "doctors": [], "stem": "s", "options": {"A": "x"}, "keyed": "x", "repeats": 3,
       "line_ids": [ID[2]]}]
LECS = {"pain1": {"norm": checks.norm(CLEAN), "duration_s": 300, "doctor": "Dr B", "pages": {12}}}


def mark(text="raphe magnus", ids=(1,), kind="word", evidence=None):
    return {"line_ids": [ID[i] for i in ids], "text": text, "kind": kind, "why": "doctor asks it",
            "evidence": evidence or [{"type": "doctor_mcq", "qid": "q1"}]}


SAID = {"type": "said_mcq", "lecture": "pain1", "at": "01:00", "quote": "write MCQ on this the raphe magnus"}


class TestCheckMarks(unittest.TestCase):
    def errors(self, *rows):
        return checks.check_marks(list(rows), QS, LINES, LECS, [10, 14])

    def test_good_marks_pass(self):
        self.assertEqual(self.errors(
            mark(evidence=[SAID, {"type": "doctor_mcq", "qid": "q1"}]),
            mark("dorsal horn", (2,), evidence=[{"type": "other_mcq", "qid": "q2"}]),
            mark("releases serotonin onto the dorsal", (1, 2), "sentence",
                 [{"type": "stressed", "lecture": "pain1", "at": ["01:00", "02:30"]}])), [])

    def test_bad_marks_fail(self):
        cases = {
            "not word for word": mark("raphe magnum"),
            "1 to 3 words": mark("The raphe magnus releases"),
            "4 to 40 words": mark("raphe magnus", kind="sentence"),
            "a figure": mark("FIGURE", (3,)),
            "outside this lesson": mark("far away", (4,), evidence=[{"type": "other_mcq", "qid": "q2"}]),
            "is not word for word in lectures": mark(evidence=[dict(SAID, quote="this is never said")]),
            "its evidence type is other_mcq": mark("dorsal horn", (2,), evidence=[{"type": "doctor_mcq", "qid": "q2"}]),
            "not pointed at these lines": mark("dorsal horn", (2,)),
            "2 or more different times": mark(evidence=[{"type": "stressed", "lecture": "pain1", "at": ["01:00"]}]),
            "more lines than the text needs": mark("raphe magnus", (1, 2)),
            "not in batch": mark(evidence=[{"type": "other_mcq", "qid": "zz"}]),
        }
        for want, row in cases.items():
            with self.subTest(want):
                self.assertTrue(any(want in e for e in self.errors(row)), self.errors(row))

    def test_duplicate_mark_fails(self):
        self.assertTrue(any("twice" in e for e in self.errors(mark(), mark())))

    def test_audit_rows(self):
        batch = [{"n": 1}, {"n": 2}]
        self.assertEqual(checks.check_audit([{"n": 1, "keep": True, "reason": "ok"},
                                             {"n": 2, "keep": False, "reason": "wrong word"}], batch), [])
        self.assertTrue(checks.check_audit([{"n": 1, "keep": "yes", "reason": "ok"}], batch))


class TestLevel(unittest.TestCase):
    def lv(self, *evidence):
        return highlights.level(highlights.enrich(mark(evidence=list(evidence)), QS, {"pain1": "Dr B"}, LINES))

    def test_levels(self):
        self.assertEqual((self.lv(SAID)["level"], self.lv(SAID)["mcq"]), (1, True))
        self.assertEqual(self.lv({"type": "doctor_mcq", "qid": "q1"})["level"], 2)
        self.assertEqual(self.lv({"type": "stressed", "lecture": "pain1", "at": ["01:00", "02:30"]})["level"], 3)
        both = self.lv({"type": "doctor_mcq", "qid": "q1"},
                       {"type": "said_important", "lecture": "pain1", "at": "01:00", "quote": "raphe magnus"})
        self.assertEqual((both["level"], both["doctors"]), (1, ["Dr A", "Dr B"]))

    def test_same_evidence_counts_once(self):
        self.assertEqual(self.lv({"type": "doctor_mcq", "qid": "q1"}, {"type": "doctor_mcq", "qid": "q1"})["score"], 3)

    def test_cap_keeps_mcq_and_strongest(self):
        ms = [{"page": 12, "kind": "word", "mcq": False, "level": 3, "score": 1, "n": i} for i in range(25)]
        ms[20].update(level=1, score=9)
        ms[24].update(mcq=True)
        with mock.patch.dict(highlights.CONFIG["highlights"], max_words_per_page=3):
            kept = highlights.cap(ms)
        self.assertEqual([m["n"] for m in kept], [0, 20, 24])  # the MCQ mark counts toward the limit


class TestFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "modules" / M).mkdir(parents=True)
        common.write_jsonl(root / "modules" / M / "lines.jsonl", LINES)
        book = root / "book" / "modules" / M / "Physiology" / "2 - Functional" / "_work"
        book.mkdir(parents=True)
        (book / "chapter.json").write_text(json.dumps({"lessons": [
            {"dir": "Pain", "name": "Pain control", "first": 10, "last": 14}]}), encoding="utf-8")
        self.patches = [mock.patch.object(common, "MODULES", root / "modules"),
                        mock.patch.object(highlights, "ROOT", root),
                        mock.patch.object(highlights, "OUT", root / "highlights"),
                        mock.patch.object(highlights, "EXPORTS", root / "exports"),
                        mock.patch.dict(highlights.CONFIG, book_root=str(root / "book")),
                        mock.patch.object(lectures, "LECTURES", root / "lectures")]
        for p in self.patches:
            p.start()
        lectures.save({"id": "pain1", "module": M, "title": "Pain", "doctor": "Dr B", "duration_s": 300})
        (lectures.folder("pain1") / "clean.txt").write_text(CLEAN, encoding="utf-8")
        common.write_jsonl(lectures.folder("pain1") / "parts.jsonl", PARTS)
        self.jobs = root / "jobs"

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_lesson_to_export(self):
        lesson = highlights.lessons(M)[0]
        self.assertEqual((lesson["key"], lesson["pages"]), (f"{M}__Physiology-2-Pain", [10, 14]))
        self.assertEqual(highlights.lessons_for_lecture("pain1"), [lesson])
        payload = highlights.job_payload(None, lesson)
        self.assertEqual(payload["lectures"], ["pain1"])
        payload["questions"] = QS
        job = {"key": lesson["key"] + ".1", "payload": payload}
        d = self.jobs / "highlights" / job["key"]
        f = flow.HighlightFlow()
        f.prepare(job, d)
        self.assertTrue((d / "lectures" / "pain1" / "clean.txt").exists())
        tool = subprocess.run([sys.executable, "-I", str(d / "tools" / "lecture.py"), "12"], capture_output=True,
                              text=True, encoding="utf-8")
        self.assertIn("Write MCQ on this", tool.stdout)
        common.write_jsonl(d / "marks.jsonl", [mark(evidence=[SAID]), mark("dorsal horn", (2,),
                                                                          evidence=[{"type": "other_mcq", "qid": "q2"}])])
        kit = subprocess.run([sys.executable, "-I", str(d / "tools" / "check.py")], capture_output=True, text=True)
        self.assertIn("PASS", kit.stdout, kit.stdout + kit.stderr)
        self.assertEqual(f.check(job, d), [])
        nxt = f.then(job, d)
        self.assertEqual(nxt[0][0], "hl_audit")
        audit = {"key": job["key"], "payload": nxt[0][1][0]["payload"]}
        a = flow.AuditFlow()
        ad = self.jobs / "hl_audit" / job["key"]
        a.prepare(audit, ad)
        batch = common.read_jsonl(ad / "batch.jsonl")
        self.assertEqual(len(batch), 2)  # the MCQ mark, and the only other mark (every 10th of the rest)
        self.assertIn("Write MCQ on this", batch[0]["evidence"][0]["transcript"])
        common.write_jsonl(ad / "audit.jsonl", [{"n": 1, "keep": True, "reason": "doctor says MCQ"},
                                                {"n": 2, "keep": False, "reason": "wrong words"}])
        self.assertEqual(a.check(audit, ad), [])
        rows = common.read_jsonl(highlights.EXPORTS / M / "highlights.jsonl")
        self.assertEqual([(r["text"], r["level"], r["mcq"]) for r in rows], [("raphe magnus", 1, True)])
        self.assertEqual(highlights.summary(M, lesson["key"])["mcq"], 1)

    def test_export_merges_doctors(self):
        base = highlights.level(highlights.enrich(mark(), QS, {}, LINES))
        other = highlights.level(highlights.enrich(
            mark(evidence=[{"type": "said_important", "lecture": "pain1", "at": "01:00", "quote": "raphe magnus"}]),
            QS, {"pain1": "Dr B"}, LINES))
        self.assertEqual((base["level"], other["level"]), (2, 2))
        highlights.finish(M, "a", [base])
        highlights.finish(M, "b", [other])
        rows = common.read_jsonl(highlights.EXPORTS / M / "highlights.jsonl")
        self.assertEqual([(r["level"], r["doctors"]) for r in rows], [(1, ["Dr A", "Dr B"])])


if __name__ == "__main__":
    unittest.main()

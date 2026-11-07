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
import labels  # noqa: E402
from flows import common, labels as label_flow, reference as reference_flow  # noqa: E402

M = "year2-cns"


def line(page, n, text="a teaching line"):
    return {"id": f"{M}:h:p{page}:l{n}", "module": M, "hash": "h", "page": page, "printed": page, "n": n,
            "text": text, "figure": None}


LINES = [line(p, 1) for p in range(1, 21)]
REF = {"lectures": [{"lecture_id": f"{M}:L01", "title": "Pain", "subject": "Physiology", "pdf_pages": [2, 10]},
                    {"lecture_id": f"{M}:L02", "title": "Cerebellum", "subject": "Anatomy", "pdf_pages": [10, 20]}]}
LISTS = {"modules": {M: "CNS & Special Senses", "year1-musculoskeletal": "Musculoskeletal"},
         "lectures": {M: REF["lectures"]}, "doctors": ["Ahmed Ammar", "Komsan"]}


class TestReference(unittest.TestCase):
    def test_good_list_passes(self):
        self.assertEqual(checks.check_reference(REF, M, LINES), [])

    def test_bad_lists(self):
        def err(lecs):
            return checks.check_reference({"lectures": lecs}, M, LINES)
        a, b = REF["lectures"]
        self.assertIn("non-empty", checks.check_reference({}, M, LINES)[0])
        self.assertIn(f"must be {M}:L02", err([a, dict(b, lecture_id=f"{M}:L07")])[0])
        self.assertIn("before lecture 1 ends", err([a, dict(b, pdf_pages=[5, 20])])[0])
        self.assertIn("inside 1-20", err([a, dict(b, pdf_pages=[10, 99])])[0])
        self.assertIn("title is empty", err([dict(a, title=" "), b])[0])
        gap = err([dict(a, pdf_pages=[2, 5]), dict(b, pdf_pages=[12, 20])])
        self.assertIn("6 text pages sit in no lecture", gap[0])


class TestLabels(unittest.TestCase):
    HEADERS = [{"hid": "h1"}, {"hid": "h2"}]

    def test_header_rows(self):
        rows = [{"hid": "h1", "module": M, "lecture_id": f"{M}:L02", "doctor": "Komsan", "kind": "doctor"},
                {"hid": "h2", "module": "mixed", "lecture_id": None, "doctor": None, "kind": "past_exam"}]
        self.assertEqual(checks.check_labels(rows, self.HEADERS, [], LISTS), [])
        bad = [dict(rows[0], lecture_id="year1-musculoskeletal:L01"), dict(rows[1], doctor="Dr Nobody", kind="x")]
        errors = checks.check_labels(bad, self.HEADERS, [], LISTS)
        self.assertEqual(len(errors), 3)
        self.assertIn("1 items have no row", checks.check_labels(rows[:1], self.HEADERS, [], LISTS)[0])
        self.assertIn("exactly the fields", checks.check_labels([dict(rows[0], note="x"), rows[1]], self.HEADERS, [], LISTS)[0])

    def test_question_rows_never_mixed(self):
        batch = [{"wid": "w1"}]
        ok = [{"wid": "w1", "module": "year1-musculoskeletal", "lecture_id": None}]
        self.assertEqual(checks.check_labels(ok, batch, [], LISTS), [])
        self.assertIn("module must be", checks.check_labels([dict(ok[0], module="mixed")], batch, [], LISTS)[0])


def bank_row(wk, question, chat, header, date, msg_id=1):
    return {"word_key": wk, "question": question, "options": ["a", "b"], "key": 0,
            "sightings": [{"source": "poll", "chat": chat, "msg_id": msg_id, "date": date, "header": header}]}


CONFIG = {"label_modules": LISTS["modules"], "poll_channels": {"1": ["ZAG_59_Polls"], "2": ["Batch58ATM"]},
          "module_windows": {M: [{"batch": 58, "from": "2026-11-04"}]}}
BANK = [bank_row("k1", "q1", "Batch58ATM", "Pain lec", "2026-09-01T10:00:00"),
        bank_row("k2", "q2", "Batch58ATM", "Pain lec", "2026-09-01T10:00:00"),
        bank_row("k3", "q3", "Batch58ATM", "Final revision", "2026-09-02T10:00:00"),
        bank_row("k4", "q4", "Batch58ATM", "New lec", "2026-11-05T10:00:00")]


class TestStepper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        common.write_jsonl(self.root / "bank.jsonl", BANK)
        self.out = self.root / "labels"

    def tearDown(self):
        self.tmp.cleanup()

    def test_headers_then_questions_then_labels(self):
        items = labels.header_items(BANK)
        self.assertEqual(sorted(i["count"] for i in items), [1, 1, 2])
        self.assertEqual(len(items[0]["samples"]), min(3, items[0]["count"]))
        h = {i["header"]: i["hid"] for i in items}
        header_rows = {h["Pain lec"]: {"module": M, "lecture_id": f"{M}:L01", "doctor": "Komsan", "kind": "doctor"},
                       h["Final revision"]: {"module": "mixed", "lecture_id": None, "doctor": None, "kind": "past_exam"},
                       h["New lec"]: {"module": "year1-musculoskeletal", "lecture_id": None, "doctor": None, "kind": "other"}}
        todo = labels.question_items(BANK, header_rows, CONFIG, LISTS["lectures"])
        # k3 sits under a mixed header; k4's window says CNS, so it needs its lecture; k1/k2 are done by the header
        self.assertEqual(sorted(t["question"] for t in todo), ["q3", "q4"])
        self.assertEqual(todo[0]["wid"], labels.wid("k3"))
        final = labels.final_labels(BANK, header_rows, {"k3": {"module": M, "lecture_id": f"{M}:L02"},
                                                         "k4": {"module": M, "lecture_id": None}}, CONFIG)
        by = {r["word_key"]: r for r in final}
        self.assertEqual((by["k1"]["module"], by["k1"]["lecture_id"], by["k1"]["doctors"]), (M, f"{M}:L01", ["Komsan"]))
        self.assertEqual((by["k3"]["module"], by["k3"]["lecture_id"]), (M, f"{M}:L02"))
        self.assertEqual((by["k4"]["module"], by["k4"]["by"]), (M, "window"))
        self.assertTrue(by["k4"]["window_disagrees"])  # the header said MSK; the window wins and the row is counted

    def test_doctor_map_for_the_bank(self):
        items = labels.header_items(BANK)
        rows = {i["hid"]: {"module": M, "lecture_id": None, "doctor": "Komsan" if i["header"] == "Pain lec" else None,
                           "kind": "doctor"} for i in items}
        doctors = labels.header_doctors(BANK, rows)
        self.assertEqual(doctors, {("Batch58ATM", "Pain lec"): "Komsan"})


class TestFlows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "modules" / M).mkdir(parents=True)
        common.write_jsonl(root / "modules" / M / "lines.jsonl", LINES)
        self.p = mock.patch.object(common, "MODULES", root / "modules")
        self.p.start()
        self.root = root

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def kit_check(self, d):
        return subprocess.run([sys.executable, "-I", str(d / "tools" / "check.py")], capture_output=True, text=True)

    def test_reference_lands_in_the_module(self):
        flow, d, job = reference_flow.ReferenceFlow(), self.root / "job", {"payload": {"module": M}}
        flow.prepare(job, d)
        self.assertIn("lecture_id", (d / "BRIEF.md").read_text(encoding="utf-8"))
        self.assertEqual(flow.check(job, d), ["reference.json is missing"])
        (d / "reference.json").write_text(json.dumps(REF), encoding="utf-8")
        self.assertIn("PASS", self.kit_check(d).stdout)
        self.assertEqual(flow.check(job, d), [])
        self.assertEqual(json.loads((self.root / "modules" / M / "reference.json").read_text(encoding="utf-8")), REF)

    def test_label_job_checks_and_saves(self):
        flow, d = label_flow.LabelFlow(), self.root / "lab"
        job = {"key": "headers-1", "payload": {"stage": "headers", "lists": LISTS,
                                               "batch": [{"hid": "h1", "chat": "c", "header": "x", "count": 1, "samples": []}]}}
        with mock.patch.object(label_flow, "OUT", self.root / "labels"):
            flow.prepare(job, d)
            self.assertIn("mixed", (d / "BRIEF.md").read_text(encoding="utf-8"))
            common.write_jsonl(d / "out.jsonl", [{"hid": "h1", "module": M, "lecture_id": None, "doctor": None,
                                                  "kind": "student"}])
            self.assertIn("PASS", self.kit_check(d).stdout)
            self.assertEqual(flow.check(job, d), [])
            self.assertTrue((self.root / "labels" / "headers" / "headers-1.jsonl").exists())


if __name__ == "__main__":
    unittest.main()

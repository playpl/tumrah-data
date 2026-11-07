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
from flows import common, pointers  # noqa: E402

M = "year2-cns:d30dcde2"
LINES = [
    {"id": f"{M}:p12:l1", "module": "year2-cns", "hash": "d30dcde2", "page": 12, "printed": 4, "n": 1, "text": "The analgesia system has three parts:", "figure": None},
    {"id": f"{M}:p12:l2", "module": "year2-cns", "hash": "d30dcde2", "page": 12, "printed": 4, "n": 2, "text": "periaqueductal gray and the raphe", "figure": None},
    {"id": f"{M}:p12:l3", "module": "year2-cns", "hash": "d30dcde2", "page": 12, "printed": 4, "n": 3, "text": "magnus nucleus in the medulla.", "figure": None},
    {"id": f"{M}:p12:f1", "module": "year2-cns", "hash": "d30dcde2", "page": 12, "printed": 4, "n": 1, "text": "", "figure": "Descending pain pathway"},
]
REF = {"lectures": [{"lecture_id": "cns-pain-control", "title": "Pain control", "pdf_pages": [10, 14]}]}
BATCH = [{"qid": "65f0c0ffee0000000000000a", "stem": "Q1", "options": ["a", "b", "c"]},
         {"qid": "65f0c0ffee0000000000000b", "stem": "Q2", "options": ["a", "b"]}]


def row(qid, **kw):
    r = {"qid": qid, "found": True, "lecture_id": "cns-pain-control",
         "spans": [{"pdf_page": 12, "printed_page": 4, "text": "the raphe  magnus nucleus", "figure": None, "for_option": 1}],
         "partial": False, "tested_fact": "raphe magnus is part of analgesia", "reason": None, "other_module": None}
    r.update(kw)
    return r


GOOD = [row(BATCH[0]["qid"]),
        row(BATCH[1]["qid"], found=False, lecture_id=None, spans=[], tested_fact="x", reason="not_in_book")]


class TestPointerChecks(unittest.TestCase):
    def test_good_rows_pass_and_resolve_line_ids(self):
        self.assertEqual(checks.check_pointers(GOOD, BATCH, LINES, REF), [])
        out = checks.pointer_import_rows(GOOD, LINES)
        self.assertEqual(out[0]["spans"][0]["line_ids"], [f"{M}:p12:l2", f"{M}:p12:l3"])
        self.assertEqual(out[0]["spans"][0]["for_option"], "B")
        self.assertEqual(out[0]["question_id"], BATCH[0]["qid"])
        self.assertEqual(out[1]["spans"], [])

    def test_bad_rows_fail(self):
        cases = {
            "not verbatim": [row(BATCH[0]["qid"], spans=[{**GOOD[0]["spans"][0], "text": "invented sentence"}]), GOOD[1]],
            "printed_page": [row(BATCH[0]["qid"], spans=[{**GOOD[0]["spans"][0], "printed_page": 9}]), GOOD[1]],
            "unknown lecture_id": [row(BATCH[0]["qid"], lecture_id="cns-nope"), GOOD[1]],
            "banned word": [row(BATCH[0]["qid"], tested_fact="the correct one"), GOOD[1]],
            "missing 1 qids": [GOOD[0]],
            "for_option": [row(BATCH[0]["qid"], spans=[{**GOOD[0]["spans"][0], "for_option": 5}]), GOOD[1]],
            "outside lecture": [row(BATCH[0]["qid"]), GOOD[1]],
            "keys must be exactly": [{**GOOD[0], "correct": 1}, GOOD[1]],
        }
        ref_far = {"lectures": [{"lecture_id": "cns-pain-control", "pdf_pages": [40, 44]}]}
        for want, rows in cases.items():
            errors = checks.check_pointers(rows, BATCH, LINES, ref_far if want == "outside lecture" else REF)
            self.assertTrue(any(want in e for e in errors), (want, errors))

    def test_figure_span_resolves_by_nearby_text(self):
        fig = row(BATCH[0]["qid"], spans=[{"pdf_page": 12, "printed_page": 4, "text": "FIGURE", "figure": "Descending pain pathway", "for_option": None}])
        self.assertEqual(checks.check_pointers([fig, GOOD[1]], BATCH, LINES, REF), [])
        self.assertEqual(checks.pointer_import_rows([fig], LINES)[0]["spans"][0]["line_ids"], [f"{M}:p12:f1"])


class TestPointerJob(unittest.TestCase):
    def test_job_folder_self_check_matches_dispatcher_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            mods = Path(tmp) / "modules" / "year2-cns"
            mods.mkdir(parents=True)
            common.write_jsonl(mods / "lines.jsonl", LINES)
            (mods / "reference.json").write_text(json.dumps(REF))
            job_dir = Path(tmp) / "job"
            job = {"payload": {"module": "year2-cns", "batch": BATCH}}
            flow = pointers.PointerFlow()
            with mock.patch.object(common, "MODULES", Path(tmp) / "modules"):
                prompt = flow.prepare(job, job_dir)
            self.assertIn("BRIEF.md", prompt.read_text())
            self.assertIn("subagents", prompt.read_text())
            tool = [sys.executable, "-I", str(job_dir / "tools" / "check.py")]
            self.assertIn("FAIL: out.jsonl does not exist", subprocess.run(tool, capture_output=True, text=True).stderr)
            common.write_jsonl(job_dir / "out.jsonl", GOOD)
            self.assertIn("PASS: 2 rows", subprocess.run(tool, capture_output=True, text=True).stdout)
            self.assertEqual(flow.check(job, job_dir), [])
            self.assertTrue((job_dir / "pointers.jsonl").exists())
            page = subprocess.run([sys.executable, "-I", str(job_dir / "tools" / "page.py"), "12"], capture_output=True, text=True).stdout
            self.assertIn("[FIGURE: Descending pain pathway]", page)
            self.assertIn("(printed page 4)", page)


if __name__ == "__main__":
    unittest.main()

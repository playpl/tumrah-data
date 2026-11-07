import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import checks  # noqa: E402
from flows import books, common  # noqa: E402
from test_pointers import LINES, M, REF  # noqa: E402

PAGE = {"book_id": "b001", "page": 3, "text": "Pain control\nThe raphe magnus nucleus lies in the medulla.\nTip: remember RM"}
IMAGE = {"book_id": "b001", "page": 4, "text": " "}
SPAN = {"pdf_page": 12, "printed_page": 4, "text": "the raphe magnus nucleus", "figure": None}


def good():
    return [
        {"book_id": "b001", "page": 3, "page_kind": "content", "lecture_id": "cns-pain-control", "note": None, "blocks": [
            {"n": 1, "text": "Pain control", "figure": None, "match": "not_content", "handout": []},
            {"n": 2, "text": "The raphe magnus nucleus lies in the medulla.", "figure": None, "match": "reworded", "handout": [dict(SPAN)]},
            {"n": 3, "text": "Tip: remember RM", "figure": None, "match": "extra", "handout": []}]},
        {"book_id": "b001", "page": 4, "page_kind": "not_content", "lecture_id": None, "note": None, "blocks": []},
    ]


class TestAlignmentChecks(unittest.TestCase):
    def test_good_rows_pass_and_carry_line_ids(self):
        self.assertEqual(checks.check_alignment(good(), [PAGE, IMAGE], LINES, REF), [])
        out = checks.alignment_import_rows(good(), LINES)
        self.assertEqual(out[0]["blocks"][1]["line_ids"], [f"{M}:p12:l2", f"{M}:p12:l3"])
        self.assertEqual(out[0]["blocks"][0]["line_ids"], [])

    def test_bad_rows_fail(self):
        def bad(change):
            rows = good()
            change(rows)
            return checks.check_alignment(rows, [PAGE, IMAGE], LINES, REF)

        cases = {
            "not verbatim on the book page": lambda r: r[0]["blocks"][1].update(text="An invented line"),
            "cover": lambda r: r[0]["blocks"].pop(),
            "needs handout spans": lambda r: r[0]["blocks"][1].update(handout=[]),
            "needs no spans": lambda r: r[0]["blocks"][2].update(handout=[dict(SPAN)]),
            "numbered": lambda r: r[0]["blocks"][2].update(n=7),
            "not verbatim on handout": lambda r: r[0]["blocks"][1]["handout"][0].update(text="the red nucleus"),
            "printed_page": lambda r: r[0]["blocks"][1]["handout"][0].update(printed_page=99),
            "missing 1 pages": lambda r: r.pop(),
            "unknown lecture_id": lambda r: r[0].update(lecture_id="cns-x"),
            "match must be": lambda r: r[0]["blocks"][2].update(match="maybe"),
        }
        for want, change in cases.items():
            errors = bad(change)
            self.assertTrue(any(want in e for e in errors), (want, errors))

    def test_job_folder_self_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            mods = Path(tmp) / "modules" / "year2-cns"
            mods.mkdir(parents=True)
            common.write_jsonl(mods / "lines.jsonl", LINES)
            job_dir = Path(tmp) / "job"
            job = {"payload": {"module": "year2-cns", "book_id": "b001", "pages": [PAGE, IMAGE]}}
            flow = books.BookFlow()
            with mock.patch.object(common, "MODULES", Path(tmp) / "modules"):
                flow.prepare(job, job_dir)
            common.write_jsonl(job_dir / "out.jsonl", good())
            run = subprocess.run([sys.executable, "-I", str(job_dir / "tools" / "check.py")], capture_output=True, text=True)
            self.assertIn("PASS: 2 checked", run.stdout)
            self.assertEqual(flow.check(job, job_dir), [])
            self.assertTrue((job_dir / "aligned.jsonl").exists())
            shown = subprocess.run([sys.executable, "-I", str(job_dir / "tools" / "book.py"), "4"], capture_output=True, text=True).stdout
            self.assertIn("image page", shown)


if __name__ == "__main__":
    unittest.main()

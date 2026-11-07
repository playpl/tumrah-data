import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cover  # noqa: E402
from merge import word_key  # noqa: E402


class TestCover(unittest.TestCase):
    def test_zero_lossy_script_match(self):
        index = {word_key("Which nerve supplies the deltoid?", ["Axillary", "Radial"]): "site1"}
        rows = [{"question": "which nerve supplies the DELTOID", "options": ["radial", "axillary"]},
                {"question": "Which nerve supplies the biceps?", "options": ["Axillary", "Radial"]}]
        self.assertEqual(cover.script_match(rows, index), ["site1", None])

    def test_candidates_are_an_index_by_rare_words(self):
        pool, df = cover.pool_of([{"id": "a", "text": "deltoid muscle axillary nerve"},
                                  {"id": "b", "text": "biceps muscle musculocutaneous nerve"},
                                  {"id": "c", "text": "heart muscle"}])
        got = cover.candidates({"question": "Axillary nerve injury weakens deltoid", "options": []}, pool, df)
        self.assertEqual(got[0], "a")
        self.assertNotIn("c", got)

    def test_worker_may_only_pick_a_listed_candidate(self):
        batch = [{"i": 0, "candidates": ["a", "b"]}, {"i": 1, "candidates": ["c"]}]
        self.assertEqual(cover.check_cover([{"i": 0, "match": "a"}, {"i": 1, "match": None}], batch), [])
        self.assertIn("listed candidates", cover.check_cover([{"i": 0, "match": "z"}, {"i": 1, "match": None}], batch)[0])
        self.assertIn("no row", cover.check_cover([{"i": 0, "match": "a"}], batch)[0])

    def test_a_covered_file_is_recorded_once_by_content(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(cover, "BANK", Path(tmp)):
            f = Path(tmp) / "sheet.jsonl"
            rows = [{"question": "Q1", "options": ["a"]}, {"question": "Q2", "options": ["b"]}]
            f.write_text("".join(json.dumps(r) + "\n" for r in rows))
            self.assertIsNone(cover.covered(f))
            entry = cover.record(f, rows, ["site1", None])
            self.assertEqual((entry["matched"], entry["percent"]), (1, 50.0))
            self.assertEqual(cover.covered(f)["sha"], entry["sha"])


if __name__ == "__main__":
    unittest.main()

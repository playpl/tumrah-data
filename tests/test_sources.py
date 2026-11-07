import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sources  # noqa: E402

WINDOWS = {"year1-musculoskeletal": [{"batch": 58, "from": "2025-11-01", "to": "2026-01-31"}, {"batch": 59, "from": "2026-11-04"}],
           "year2-cns": [{"batch": 58, "from": "2026-11-04"}]}


def item(param, *sightings):
    return {"param": param, "sightings": [{"chat_batch": b, "date": d} for b, d in sightings]}


class TestPlan(unittest.TestCase):
    def test_windows_pick_the_module_by_batch_and_date(self):
        got = sources.plan([item("a", (58, "2025-12-03T10:00")), item("b", ("59", "2026-11-05")),
                            item("c", (58, "2026-11-10")), item("d", (59, "2025-12-03")), item("e", (None, "2025-12-03"))],
                           WINDOWS)
        self.assertEqual([i["param"] for i in got["year1-musculoskeletal"]], ["a", "b"])
        self.assertEqual([i["param"] for i in got["year2-cns"]], ["c"])

    def test_an_earlier_reading_wins_over_the_window(self):
        got = sources.plan([item("sf", (58, "2025-12-03")), item("msk", (58, "2026-03-01")), item("chk", (58, "2025-12-01"))],
                           WINDOWS, {"sf": "Structure & Function", "msk": "Musculoskeletal", "chk": "check"})
        self.assertEqual([i["param"] for i in got["year1-musculoskeletal"]], ["msk", "chk"])
        self.assertIn("read on 2026-10-14", got["year1-musculoskeletal"][0]["reason"])

    def test_a_sighting_in_two_modules_windows_is_left_out(self):
        both = {"m1": [{"batch": 58, "from": "2026-01-01"}], "m2": [{"batch": 58, "from": "2026-01-01"}]}
        self.assertEqual(sources.plan([item("x", (58, "2026-02-01"))], both), {"m1": [], "m2": []})


if __name__ == "__main__":
    unittest.main()

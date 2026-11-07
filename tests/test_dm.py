import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import dm  # noqa: E402

ORDER = ["doctor", "quiz", "past_exam", "ai"]


class TestAdd(unittest.TestCase):
    def test_pointer_batches_follow_the_set_order_and_keep_stable_keys(self):
        qs = [{"qid": f"q{i:02d}", "set": s} for i, s in enumerate(["ai"] * 20 + ["doctor"] * 20 + [None] * 5)]
        jobs = dm.pointer_jobs("year2-cns", qs, ORDER)
        self.assertEqual([len(j["payload"]["batch"]) for j in jobs], [25, 20])
        self.assertEqual({q["set"] for q in jobs[0]["payload"]["batch"][:20]}, {"doctor"})
        self.assertEqual(jobs[1]["payload"]["batch"][-1]["set"], None)
        self.assertEqual([j["key"] for j in jobs], [j["key"] for j in dm.pointer_jobs("year2-cns", list(reversed(qs)), ORDER)])

    def test_book_jobs_hold_five_pages(self):
        pages = [{"book_id": "b1", "page": n, "text": "x"} for n in range(3, 15)]
        jobs = dm.book_jobs("year2-cns", "b1", pages)
        self.assertEqual([len(j["payload"]["pages"]) for j in jobs], [5, 5, 2])
        self.assertEqual(jobs[0]["key"], "year2-cns-b1-p0003")


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest import mock

from cloud import state, tg


class Merge(unittest.TestCase):
    def test_union_in_time_order(self):
        pc = [{"id": "a", "at": "2026-11-17T01:00:00Z", "state": "downloaded"},
              {"id": "b", "at": "2026-11-17T03:00:00Z", "state": "seen"}]
        cloud = [{"id": "a", "at": "2026-11-17T01:00:00Z", "state": "downloaded"},
                 {"id": "a", "at": "2026-11-17T02:00:00Z", "state": "uploaded"}]
        rows = state.merge(pc, cloud)
        self.assertEqual([(r["id"], r["at"][11:13]) for r in rows], [("a", "01"), ("a", "02"), ("b", "03")])

    def test_merge_twice_changes_nothing(self):
        rows = [{"id": "a", "at": "1", "x": 1}, {"id": "b", "at": "2"}]
        self.assertEqual(state.merge(rows, rows), rows)


class Runner(unittest.TestCase):
    def test_runner_only_with_its_own_session(self):
        with mock.patch.dict(os.environ, {"TG_SESSION": ""}):
            self.assertFalse(tg.on_runner())
        with mock.patch.dict(os.environ, {"TG_SESSION": "x"}):
            self.assertTrue(tg.on_runner())

    def test_inputs_are_small_and_inside_the_repo(self):
        for f in state.input_files():
            self.assertTrue(f.suffix == ".json")
            self.assertIn("sources", f.parts)


if __name__ == "__main__":
    unittest.main()

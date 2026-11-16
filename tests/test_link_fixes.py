"""Hand fixes for a doctor's wrong list links (owner, 2026-11-15: the site must be exact to the mother message)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tg_lists


def lst():
    return {"sections": {"lectures": [{"title": "Medulla", "parts": [
        {"label": "part1", "url": "u1707", "post": 1707},
        {"label": "Part 2", "url": "u1708", "post": 1708},
        {"label": "Part 3", "url": "u1708", "post": 1708}]}]}}


class LinkFixes(unittest.TestCase):
    def fixes(self, data):
        f = Path(tempfile.mkdtemp()) / "link_fixes.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        return mock.patch.object(tg_lists, "LINK_FIXES", f)

    def test_twice_linked_is_found(self):
        self.assertEqual(tg_lists.twice_linked(lst()), ["Medulla: post 1708 linked twice"])

    def test_fix_replaces_the_wrong_link_only(self):
        with self.fixes({"1630": [{"item": "Medulla", "label": "Part 3", "linked": 1708, "post": 1709}]}):
            d = tg_lists.apply_link_fixes(1630, lst())
        parts = d["sections"]["lectures"][0]["parts"]
        self.assertEqual([p["post"] for p in parts], [1707, 1708, 1709])
        self.assertEqual(d["fixed"], ["Medulla Part 3: post 1708 -> 1709"])
        self.assertEqual(tg_lists.twice_linked(d), [])

    def test_fix_stops_once_the_channel_fixed_its_link(self):
        d = lst()
        d["sections"]["lectures"][0]["parts"][2]["post"] = 1709
        with self.fixes({"1630": [{"item": "Medulla", "label": "Part 3", "linked": 1708, "post": 1709}]}):
            d = tg_lists.apply_link_fixes(1630, d)
        self.assertEqual(d["fixed"], [])

    def test_other_list_untouched(self):
        with self.fixes({"1630": [{"item": "Medulla", "label": "Part 3", "linked": 1708, "post": 1709}]}):
            d = tg_lists.apply_link_fixes(1631, lst())
        self.assertEqual(d["fixed"], [])


if __name__ == "__main__":
    unittest.main()

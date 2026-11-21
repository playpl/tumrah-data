"""The primary switch: a lesson's site ranges come from its accepted segments unless the owner placed it."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lectures

OLD = [{"from": "m:h:p198:f1", "to": "m:h:p200:l22", "pages": [198, 200]}]
SEG = {"ranges": [{"from": "m:h:p192:s3", "to": "m:h:p192:s9", "pages": [192, 192]}], "placed_by": "spine"}


class SiteRanges(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(lectures, "LECTURES", Path(self.tmp.name))
        self.p.start()
        d = Path(self.tmp.name) / "x-1"
        (d / "spine").mkdir(parents=True)
        (d / "spine" / "ranges.json").write_text(json.dumps(SEG))

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_no_accepted_segments_keeps_the_old_placement(self):
        self.assertEqual(lectures.site_ranges({"id": "x-1", "ranges": OLD, "placed_by": "claude-coarse"}),
                         [{"from": "m:h:p198:f1", "to": "m:h:p200:l22"}])

    def test_accepted_segments_replace_a_coarse_placement(self):
        (Path(self.tmp.name) / "x-1" / "segments.jsonl").write_text("{}")
        self.assertEqual(lectures.site_ranges({"id": "x-1", "ranges": OLD, "placed_by": "claude-coarse"}),
                         [{"from": "m:h:p192:s3", "to": "m:h:p192:s9"}])

    def test_the_owners_placement_wins(self):
        (Path(self.tmp.name) / "x-1" / "segments.jsonl").write_text("{}")
        self.assertEqual(lectures.site_ranges({"id": "x-1", "ranges": OLD, "placed_by": "owner"}),
                         [{"from": "m:h:p198:f1", "to": "m:h:p200:l22"}])


if __name__ == "__main__":
    unittest.main()

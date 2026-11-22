import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cloud import youtube
from spine.records import lectures_hear as H


class RehearYoutube(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "L1").mkdir()
        (root / "L1" / "lecture.json").write_text(json.dumps(
            {"id": "L1", "module": "year2-cns", "source": {"youtube": "u", "transcript": "youtube"}}), encoding="utf-8")
        (root / "L1" / "raw.txt").write_text("captions", encoding="utf-8")
        rehear = root / "rehear.json"
        rehear.write_text(json.dumps([{"lecture": "L1", "url": "u"}]), encoding="utf-8")
        self.p = [mock.patch.object(H, "LECTURES", root), mock.patch.object(youtube, "REHEAR", rehear)]
        for x in self.p:
            x.start()
        self.root = root

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def test_no_runner_copy_waits_and_keeps_the_captions(self):
        self.assertEqual(H.rehear_youtube(say=lambda *a: None, size=lambda k: None, get=lambda k, p: False), 0)
        self.assertTrue((self.root / "L1" / "raw.txt").exists())

    def test_a_runner_copy_moves_the_captions_aside_and_hear2_sees_it(self):
        def get(key, path):
            Path(path).write_bytes(b"ogg")
            return True
        self.assertEqual(H.rehear_youtube(say=lambda *a: None, size=lambda k: 10, get=get), 1)
        self.assertFalse((self.root / "L1" / "raw.txt").exists())
        self.assertEqual((self.root / "L1" / "raw_youtube.txt").read_text(encoding="utf-8"), "captions")
        self.assertEqual(H.todo(), ["L1"])
        self.assertEqual(H.rehear_youtube(say=lambda *a: None, size=lambda k: 10, get=get), 0)   # once


if __name__ == "__main__":
    unittest.main()

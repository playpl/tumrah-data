"""Year 2 transcripts on Gemini web: which lectures, which audio, when raw.txt is written."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from spine.records import lectures_hear as lh


class LecturesHear(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(lh, "LECTURES", self.tmp)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lecture(self, lid, files=(), **meta):
        d = self.tmp / lid
        d.mkdir(parents=True)
        (d / "lecture.json").write_text(json.dumps({"id": lid, "module": "year2-cns", **meta}), encoding="utf-8")
        for f in files:
            (d / f).write_text("x", encoding="utf-8")
        return d

    def test_todo_takes_lectures_with_audio_and_no_transcript(self):
        self.lecture("a", ["audio.ogg"])
        self.lecture("b", ["audio.ogg", "raw.txt"])                    # already heard
        self.lecture("c", source={"cloud": {"hear_key": "ops/hear/c.16k.ogg"}})
        self.lecture("d")                                              # no audio anywhere
        self.lecture("e", ["audio.ogg"], hold=True)                    # held duplicate
        self.lecture("f", ["audio.ogg"], module="year1-musculoskeletal")
        self.assertEqual(lh.todo(), ["a", "c"])

    def test_audio_prefers_the_local_file_and_fetches_the_small_copy(self):
        self.lecture("a", ["audio.ogg"])
        self.assertEqual(lh.audio("a", get=lambda k, p: self.fail("fetched")).name, "audio.ogg")
        self.lecture("c", source={"cloud": {"hear_key": "ops/hear/c.16k.ogg"}})
        got = []

        def get(key, path):
            got.append(key)
            Path(path).write_text("ogg", encoding="utf-8")
            return True
        self.assertEqual(lh.audio("c", get=get).name, "hear.16k.ogg")
        self.assertEqual(got, ["ops/hear/c.16k.ogg"])
        self.lecture("g", source={"cloud": {"hear_key": "k"}})
        self.assertIsNone(lh.audio("g", get=lambda k, p: False))       # not in the bucket

    def test_finish_writes_raw_once_and_only_when_whole(self):
        d = self.lecture("a", ["audio.ogg"])
        with mock.patch("flows.lecture.merge_pieces", lambda lid: (None, ["pieces not done yet: [1]"])):
            self.assertEqual(lh.finish("a"), (False, ["pieces not done yet: [1]"]))
        self.assertFalse((d / "raw.txt").exists())
        with mock.patch("flows.lecture.merge_pieces", lambda lid: ("[00:00] text\n", [])):
            self.assertEqual(lh.finish("a"), (True, []))
            self.assertEqual((d / "raw.txt").read_text(encoding="utf-8"), "[00:00] text\n")
            self.assertEqual(lh.finish("a"), (False, []))              # never rewritten


if __name__ == "__main__":
    unittest.main()

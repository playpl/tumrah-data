import json
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
import lectures  # noqa: E402
from flows import common, lecture  # noqa: E402
from test_lecture_checks import RAW, TestClean  # noqa: E402

LINES = [{"id": f"year2-cns:h:p12:l{n}", "module": "year2-cns", "hash": "h", "page": 12, "printed": 4, "n": n,
          "text": t, "figure": None} for n, t in enumerate(["Pain control", "raphe magnus", "dorsal horn"], 1)]
VTT = """WEBVTT

00:00:01.000 --> 00:00:03.000
<c>today we talk</c>

00:00:03.000 --> 00:00:05.000
today we talk
about pain

00:00:40.000 --> 00:00:42.000
the raphe magnus
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "modules" / "year2-cns").mkdir(parents=True)
        common.write_jsonl(root / "modules" / "year2-cns" / "lines.jsonl", LINES)
        self.patches = [mock.patch.object(common, "MODULES", root / "modules"),
                        mock.patch.object(lectures, "LECTURES", root / "lectures")]
        for p in self.patches:
            p.start()
        lectures.save({"id": "pain1", "module": "year2-cns", "title": "Pain control", "lesson": None,
                       "pdf_pages": [10, 14], "transcribe": True, "source": {"file": "x"}, "duration_s": 120})
        (lectures.folder("pain1") / "audio.ogg").write_bytes(b"OggS")
        self.job = {"payload": {"lecture": "pain1"}}
        self.dir = root / "job"

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def kit_check(self):
        return subprocess.run([sys.executable, "-I", str(self.dir / "tools" / "check.py")], capture_output=True, text=True)


class TestChunks(unittest.TestCase):
    def test_pieces_have_exact_lengths(self):
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / "a.ogg"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=7", "-c:a", "libopus",
                            "-b:a", "16k", str(src)], check=True)
            self.assertEqual(lectures.chunks(src, Path(t) / "chunks", 3), 3)
            lengths = [lectures.duration(p) for p in sorted((Path(t) / "chunks").glob("c*.ogg"))]
            self.assertAlmostEqual(lengths[0], 3, delta=0.05)
            self.assertAlmostEqual(sum(lengths), 7, delta=0.1)
            self.assertEqual(lectures.chunks(src, Path(t) / "chunks", 3), 3)  # already cut: counted, not cut again


class TestTranscribe(Base):
    def test_raw_is_written_once_and_the_links_job_follows(self):
        flow = lecture.TranscribeFlow()
        with mock.patch.object(lectures, "chunks", return_value=1):
            prompt = flow.prepare(self.job, self.dir)
        self.assertIn("WHOLE recording", prompt.read_text())
        self.assertIn("cut into 1 pieces", prompt.read_text())
        self.assertTrue((self.dir / "audio.ogg").exists())
        self.assertEqual(flow.check(self.job, self.dir), ["transcript.txt and timing.jsonl missing"])
        (self.dir / "transcript.txt").write_text(RAW, encoding="utf-8")
        common.write_jsonl(self.dir / "timing.jsonl", [{"chunk": 0, "paragraph": 1, "first_words": "today we talk about"}])
        self.assertIn("PASS", self.kit_check().stdout)
        self.assertIn("1 | today we talk", subprocess.run([sys.executable, "-I", str(self.dir / "tools" / "paras.py")],
                                                          capture_output=True, text=True).stdout)
        self.assertEqual(flow.check(self.job, self.dir), [])
        raw = lectures.folder("pain1") / "raw.txt"
        first = raw.read_text(encoding="utf-8")
        self.assertEqual(checks.paragraphs(first), [(0, RAW.splitlines()[0][8:]), (41, RAW.splitlines()[1][8:]),
                                                    (73, RAW.splitlines()[2][8:])])  # times by word position
        (self.dir / "transcript.txt").write_text(RAW + "\n[01:50] more", encoding="utf-8")
        flow.check(self.job, self.dir)
        self.assertEqual(raw.read_text(encoding="utf-8"), first)  # never edited after
        self.assertEqual(flow.then(self.job, self.dir), [("lecture_links", [{"key": "pain1", "payload": {"lecture": "pain1"}}])])


class TestLectureLinks(Base):
    def test_clean_fixes_parts_pass_and_land_in_the_lecture_folder(self):
        (lectures.folder("pain1") / "raw.txt").write_text(RAW, encoding="utf-8")
        flow = lecture.LectureLinkFlow()
        flow.prepare(self.job, self.dir)
        self.assertIn("Never change, add, drop or reorder a word", (self.dir / "BRIEF.md").read_text(encoding="utf-8"))
        ids = subprocess.run([sys.executable, "-I", str(self.dir / "tools" / "lineids.py"), "12"], capture_output=True, text=True).stdout
        self.assertIn("year2-cns:h:p12:l2", ids)
        (self.dir / "clean.txt").write_text(TestClean.CLEAN, encoding="utf-8")
        (self.dir / "fixes.jsonl").write_text(json.dumps({"at": "00:40", "heard": "fibers", "meant": "fibres", "confidence": 0.5, "reason": "spelling"}) + "\n", encoding="utf-8")
        common.write_jsonl(self.dir / "parts.jsonl", [
            {"part": 1, "sub": 0, "title": "Analgesia", "start": 0, "end": 120, "line_ids": ["year2-cns:h:p12:l1", "year2-cns:h:p12:l2"]}])
        self.assertIn("PASS", self.kit_check().stdout)
        self.assertEqual(flow.check(self.job, self.dir), [])
        meta = lectures.load("pain1")
        self.assertEqual(meta["fixes"], {"applied": 0, "for_owner": 1})
        self.assertEqual(meta["report"]["recording_linked"], 1.0)
        self.assertTrue((lectures.folder("pain1") / "links.jsonl").exists())

    def test_a_changed_word_fails(self):
        (lectures.folder("pain1") / "raw.txt").write_text(RAW, encoding="utf-8")
        flow = lecture.LectureLinkFlow()
        flow.prepare(self.job, self.dir)
        (self.dir / "clean.txt").write_text(TestClean.CLEAN.replace("pain", "ache"), encoding="utf-8")
        (self.dir / "fixes.jsonl").write_text("", encoding="utf-8")
        common.write_jsonl(self.dir / "parts.jsonl", [{"part": 1, "sub": 0, "title": "A", "start": 0, "end": 120, "line_ids": []}])
        self.assertIn("differs from the raw transcript", flow.check(self.job, self.dir)[0])


class TestYoutube(unittest.TestCase):
    def test_vtt_rolling_captions_become_timed_paragraphs(self):
        self.assertEqual(lectures.vtt_to_raw(VTT), "[00:01] today we talk about pain\n[00:40] the raphe magnus\n")


if __name__ == "__main__":
    unittest.main()

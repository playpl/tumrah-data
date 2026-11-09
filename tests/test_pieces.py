"""Transcription by pieces (owner, 2026-11-09): transcribe fans out by code, one worker per 5-minute piece, code joins."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import checks  # noqa: E402
import lectures  # noqa: E402
from flows import lecture  # noqa: E402

WORDS = " ".join(f"word{i}" for i in range(500))


def tone(path, seconds):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-ac", "1", "-c:a", "libopus", "-b:a", "16k", str(path)], check=True)


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class TestPieces(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = mock.patch.object(lectures, "LECTURES", self.root / "lectures")
        self.p.start()
        lectures.save({"id": "l1", "module": "m", "title": "T", "ranges": [{"from": "a", "to": "b", "pages": [1, 2]}],
                       "duration_s": 400})
        tone(lectures.folder("l1") / "audio.ogg", 400)

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def run_piece(self, c, text):
        job = {"id": f"piece:l1-c{c:02d}", "key": f"l1-c{c:02d}", "payload": {"lecture": "l1", "chunk": c}}
        d = self.root / "jobs" / job["key"]
        flow = lecture.PieceFlow()
        prompt = flow.prepare(job, d)
        self.assertIn("Do not start subagents", prompt.read_text(encoding="utf-8"))
        (d / "piece.txt").write_text(text, encoding="utf-8")
        self.assertEqual(flow.check(job, d), [])
        return flow.then(job, d)

    def test_fan_out_then_join_with_exact_offsets(self):
        nxt = lecture.TranscribeFlow().expand({"payload": {"lecture": "l1"}})
        self.assertEqual(nxt[0][0], "piece")
        self.assertEqual([j["key"] for j in nxt[0][1]], ["l1-c00", "l1-c01"])
        self.assertEqual(self.run_piece(0, f"[00:00] {WORDS}\n[03:00] {WORDS}\n[04:30] {WORDS}\n"), [])  # not all pieces yet
        self.assertFalse((lectures.folder("l1") / "raw.txt").exists())
        then = self.run_piece(1, f"[00:00] {WORDS}\n[01:30] {WORDS}\n")
        self.assertEqual(then, [("lecture_links", [{"key": "l1", "payload": {"lecture": "l1"}}])])
        raw = (lectures.folder("l1") / "raw.txt").read_text(encoding="utf-8")
        self.assertEqual([s for s, _ in checks.paragraphs(raw)], [0, 180, 270, 300, 390])

    def test_a_piece_with_times_past_its_end_is_refused(self):
        lecture.TranscribeFlow().expand({"payload": {"lecture": "l1"}})
        job = {"key": "l1-c01", "payload": {"lecture": "l1", "chunk": 1}}
        d = self.root / "jobs" / "x"
        lecture.PieceFlow().prepare(job, d)
        (d / "piece.txt").write_text(f"[00:00] {WORDS}\n[04:00] {WORDS}\n", encoding="utf-8")  # piece is 100 s long
        self.assertTrue(lecture.PieceFlow().check(job, d))


if __name__ == "__main__":
    unittest.main()

"""Whiteboard PDFs in a folder inside a chapter folder attach to the lecture with the same number (owner, 2026-11-13)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import doctors_folder
import lesson_files


class LessonFiles(unittest.TestCase):
    def test_attaches_by_number_and_reports_unknown(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            chap = root / "cns" / "physiology" / "doc" / "1- sensations"
            (chap / "board").mkdir(parents=True)
            (chap / "6- Tracts.mp3").write_bytes(b"a")
            (chap / "board" / "6- Tracts.pdf").write_bytes(b"pdf")
            (chap / "board" / "9- Other.pdf").write_bytes(b"pdf")
            metas = [{"id": "cns-076", "module": "m", "kind": "lecture", "title": "Tracts", "doctor": "dr-x",
                      "source": {"file": str(chap / "6- Tracts.mp3")}}]
            with mock.patch.object(doctors_folder, "DOCTORS", root), mock.patch.object(lesson_files.lectures, "all_lectures", return_value=metas):
                out, report = lesson_files.rows("m")
        self.assertEqual([r["lesson"] for r in out], ["lecture:cns-076"])
        self.assertEqual(out[0]["kind"], "whiteboard")
        self.assertTrue(any("no lecture 9" in r for r in report))


if __name__ == "__main__":
    unittest.main()

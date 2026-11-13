"""The doctors folder: lessons as .txt link files, or as a recording plus a quiz shortcut (owner, 2026-11-09)."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import doctors_folder  # noqa: E402
import doctors_watch  # noqa: E402

FORM = "[InternetShortcut]\nURL=https://docs.google.com/forms/d/e/x{}/viewform\n"


def build(root):
    chap = root / "cns" / "histology" / "zahran" / "1- nervous tissue"
    chap.mkdir(parents=True)
    (chap / "1- neuron 1.txt").write_text("https://youtu.be/abc\nquiz: https://forms.gle/q1\n", encoding="utf-8")
    (chap / "2- Nerve fiber.mp3").write_bytes(b"x")
    (chap / "2- Nerve Fiber test.url").write_text(FORM.format(2), encoding="utf-8")
    (chap / "3- Ganglia.m4a").write_bytes(b"x")
    (chap / "1- neuron 1 extra test.url").write_text(FORM.format(1), encoding="utf-8")
    anat = root / "cns" / "anatomy" / "amr mossafer" / "chapter 1"
    anat.mkdir(parents=True)
    (anat / "1- spinal cord 1.txt").write_text("https://youtu.be/def\n", encoding="utf-8")
    (anat / "3- mcq.url").write_text(FORM.format(3), encoding="utf-8")
    (root / "cns" / "physiology" / "nageb").mkdir(parents=True)
    (root / "cns" / "physiology" / "nageb" / "Pain quiz.url").write_text(FORM.format(9), encoding="utf-8")


class TestScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        build(Path(self.tmp.name))
        self.patch = mock.patch.object(doctors_folder, "DOCTORS", Path(self.tmp.name))
        self.patch.start()
        lessons, _ = doctors_folder.scan()
        self.by = {(x["doctor_folder"], x["n"]): x for x in lessons}

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_a_recording_and_its_test_make_one_lesson(self):
        x = self.by[("zahran", 2)]
        self.assertEqual(x["title"], "Nerve fiber")
        self.assertEqual([k["kind"] for k in x["links"]], ["recording", "quiz"])
        self.assertTrue(x["links"][0]["file"].endswith("2- Nerve fiber.mp3"))
        self.assertEqual(x["chapter"], "nervous tissue")
        self.assertEqual([k["kind"] for k in self.by[("zahran", 3)]["links"]], ["recording"])

    def test_a_shortcut_with_a_txt_lesson_of_its_number_joins_that_lesson(self):
        x = self.by[("zahran", 1)]
        self.assertEqual([k["kind"] for k in x["links"]], ["recording", "quiz", "quiz"])
        self.assertEqual(sum(1 for k in self.by if k[0] == "zahran"), 3)

    def test_a_lone_numbered_shortcut_is_the_chapters_quiz(self):
        x = self.by[("amr mossafer", 3)]
        self.assertTrue(x.get("chapter_quiz"))
        self.assertEqual(x["links"][0]["kind"], "quiz")

    def test_top_level_forms_are_left_to_their_own_script(self):
        self.assertFalse(any(k[0] == "nageb" for k in self.by))


class TestWatch(unittest.TestCase):
    def test_new_and_changed_files_are_reported_once(self):
        with tempfile.TemporaryDirectory() as t:
            root, state = Path(t) / "doctors", Path(t) / "seen.json"
            build(root)
            self.assertEqual(doctors_watch.changes(root, state, save=True)["new"], [])  # first run: baseline only
            (root / "cns" / "histology" / "zahran" / "1- nervous tissue" / "4- Trunk.m4a").write_bytes(b"y")
            (root / "cns" / "anatomy" / "amr mossafer" / "chapter 1" / "1- spinal cord 1.txt").write_text("changed")
            got = doctors_watch.changes(root, state, save=True)
            self.assertEqual(got["new"], ["cns/histology/zahran/1- nervous tissue/4- Trunk.m4a"])
            self.assertEqual(got["changed"], ["cns/anatomy/amr mossafer/chapter 1/1- spinal cord 1.txt"])
            self.assertEqual(doctors_watch.changes(root, state, save=True), {"new": [], "changed": [], "gone": []})


class NotesInBrackets(unittest.TestCase):
    """A bracket that starts with "for " is the owner's note to Claude (2026-11-12), not part of the title."""

    def test_note_is_split_from_the_title(self):
        self.assertEqual(doctors_folder.split_note("pain Revision (for 1 and 2)"), ("pain Revision", "for 1 and 2"))
        self.assertEqual(doctors_folder.split_note("Pain 1 (1)"), ("Pain 1 (1)", None))  # a download copy mark stays

    def test_revision_note_with_numbers_covers_only_those_lessons(self):
        import lectures
        metas = [{"id": "a", "title": "Pain 1"}, {"id": "b", "title": "Pain 2"}, {"id": "c", "title": "Pain analgesia system pain control"}]
        orig = lectures.all_lectures
        lectures.all_lectures = lambda *a, **k: [{**m, "kind": "lecture", "doctor": "d", "chapter": "c"} for m in metas]
        try:
            x = {"doctor_id": "d", "doctor_folder": "d", "chapter": "c", "module": "m", "title": "pain Revision", "note": "for 1 and 2"}
            self.assertEqual(doctors_folder.revision_covers(x), ["a", "b"])
        finally:
            lectures.all_lectures = orig

    def test_note_naming_one_lecture_makes_a_mini_lecture(self):
        metas = [{"id": "c", "kind": "lecture", "title": "Pain analgesia system pain control", "module": "m", "chapter": "ch"}]
        x = {"kind": "revision", "module": "m", "chapter": "ch", "note": "for Pain analgesia system pain control"}
        self.assertEqual(doctors_folder.mini_target(x, metas)["id"], "c")
        self.assertIsNone(doctors_folder.mini_target({**x, "note": "for 1 and 2"}, metas))


if __name__ == "__main__":
    unittest.main()

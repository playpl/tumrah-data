"""A doctor's lectures are filed in the handout chapter their pages fall in, never all in the subject's first chapter
(owner, 2026-11-13: every Azony lecture showed under Spinal cord)."""
import unittest

import dm

CH = {"anatomy": [
    {"id": "L03", "title": "Spinal cord", "handout_title": "Anatomy of the spinal cord", "order": 1, "pages": [49, 57]},
    {"id": "L05", "title": "Anatomy of the brain stem nuclei", "handout_title": "Anatomy of the brain stem nuclei", "order": 2, "pages": [71, 76]},
    {"id": "L08", "title": "Anatomy of the 4th ventricle", "handout_title": "Anatomy of the 4th ventricle", "order": 3, "pages": [99, 101]},
]}


class ChapterOf(unittest.TestCase):
    def test_pages_decide(self):
        row, how = dm.chapter_of({"title": "Medulla part 1", "ranges": [{"pages": [71, 73]}]}, "anatomy", CH)
        self.assertEqual((row["id"], how), ("L05", "pages"))

    def test_most_pages_win(self):
        row, _ = dm.chapter_of({"title": "x", "ranges": [{"pages": [49, 50]}, {"pages": [71, 76]}]}, "anatomy", CH)
        self.assertEqual(row["id"], "L05")

    def test_unplaced_lesson_matches_title(self):
        row, how = dm.chapter_of({"title": "4th ventricle part 2", "ranges": []}, "anatomy", CH)
        self.assertEqual((row["id"], how), ("L08", "title"))

    def test_unknown_is_a_flagged_guess(self):
        row, how = dm.chapter_of({"title": "Something else", "ranges": []}, "anatomy", CH)
        self.assertEqual((row["id"], how), ("L03", "guess"))


if __name__ == "__main__":
    unittest.main()

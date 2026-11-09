"""A doctor's MCQ book, copied out by the fleet (owner, 2026-11-08)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import checks  # noqa: E402
import doctors_folder  # noqa: E402

PAGE = """1. Which tract carries pain and temperature?
a) Lateral spinothalamic
b) Dorsal column
c) Corticospinal
d) Rubrospinal
2. The conus medullaris ends at which vertebra?
a) L1
b) S2
"""
BATCH = [{"page": 3, "text": PAGE}, {"page": 4, "text": "Answers: 1-a 2-a"}]


def row(**kw):
    return {"page": 3, "n": 1, "question": "Which tract carries pain and temperature?",
            "options": ["Lateral spinothalamic", "Dorsal column", "Corticospinal", "Rubrospinal"],
            "key": None, "key_from": None, **kw}


class TestCheckMCQ(unittest.TestCase):
    def test_copied_questions_pass_with_or_without_the_books_key(self):
        rows = [row(), row(n=2, question="The conus medullaris ends at which vertebra?", options=["L1", "S2"],
                           key=0, key_from="answer_list")]
        self.assertEqual(checks.check_mcq(rows, BATCH), [])

    def test_a_key_needs_its_source_and_an_invented_question_is_refused(self):
        self.assertTrue(checks.check_mcq([row(key=0)], BATCH))                         # key with no source
        self.assertTrue(checks.check_mcq([row(key_from="marked")], BATCH))              # source with no key
        self.assertTrue(checks.check_mcq([row(key=7, key_from="marked")], BATCH))       # not an option
        bad = checks.check_mcq([row(question="Explain hormonal regulation of thyroid glands")], BATCH)
        self.assertTrue(any("not on its page" in e for e in bad))

    def test_a_page_of_options_cannot_be_skipped(self):
        self.assertTrue(any("shows options but has no questions" in e for e in checks.check_mcq([], BATCH)))
        self.assertTrue(checks.check_mcq([row(), row()], BATCH))  # the same n twice


class TestBookKinds(unittest.TestCase):
    def test_mcq_partial_and_full_books_get_their_own_ids(self):
        b = {"doctor_folder": "amr mossafer", "subject": "anatomy"}
        self.assertEqual(doctors_folder.book_id({**b, "kind": "partial"}), "mossafer-anat-1")
        self.assertEqual(doctors_folder.book_id({**b, "kind": "full"}), "mossafer-anat-full")
        self.assertEqual(doctors_folder.book_id({**b, "kind": "mcq"}), "mossafer-anat-mcq")


if __name__ == "__main__":
    unittest.main()

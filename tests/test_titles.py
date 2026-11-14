"""Poll titles -> handout lectures (owner, 2026-11-14: non-poll messages are the titles that organize the polls)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fast_lessons  # noqa: E402
import index_map  # noqa: E402
import titles  # noqa: E402


class Topics(unittest.TestCase):
    def test_the_subtitle_line_names_the_lecture(self):
        self.assertEqual(titles.topics("physiology", "👇🏻 Dr.Khaled Abualfadle \n     Sensory receptors"), {"year2-cns:L19"})

    def test_whole_words_only(self):
        self.assertEqual(index_map.lecture_of("physiology", "hypothalamus"), "year2-cns:L29")
        self.assertEqual(index_map.lecture_of("physiology", "muscle reflex"), "year2-cns:L23")

    def test_a_title_keeps_every_lecture_it_names(self):
        self.assertEqual(titles.topics("anatomy", "👇🏻Face & Blood supply \n Easy"), {"year2-cns:L38", "year2-cns:L16"})

    def test_a_topic_with_no_subject_names_each_subjects_lecture(self):
        got, how = titles.scope("👇🏻Eye \n Hard", set(), {})
        self.assertEqual((got, how), (["year2-cns:L54", "year2-cns:L55", "year2-cns:L56"], "title"))

    def test_the_index_subject_narrows_it(self):
        self.assertEqual(titles.scope("👇🏻Eye \n Hard", {"histology"}, {}), (["year2-cns:L55"], "title+index"))

    def test_a_doctor_title_with_no_topic_falls_back_to_his_lectures(self):
        docs = {"Amr Mosafer": ("anatomy", ["year2-cns:L03", "year2-cns:L10"])}
        self.assertEqual(titles.scope("👇🏻Dr.Amr Mosafer Notebook \n Final Zatoona", set(), docs),
                         (["year2-cns:L03", "year2-cns:L10"], "doctor"))

    def test_an_exam_title_is_an_orphan(self):
        self.assertEqual(titles.scope("👇🏻Zag Final 26", set(), {}), ([], None))


class Ranges(unittest.TestCase):
    def test_touching_ranges_join(self):
        self.assertEqual(fast_lessons.merge_ranges([(99, 101), (102, 110), (50, 57)]), [(50, 57), (99, 110)])


if __name__ == "__main__":
    unittest.main()

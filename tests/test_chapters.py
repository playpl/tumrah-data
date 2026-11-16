"""A lesson's chapter is the item of the doctor's Telegram list it is posted under (owner, 2026-11-14: "chapters should be
imported from the mother message"), never the handout lecture its pages fall in and never our own guess."""
import unittest

import dm


class ListChapters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = {r["key"]: r for r in dm.lesson_rows("year2-cns")}

    def test_azony_parts_sit_in_their_list_item(self):
        by = {}
        for r in self.rows.values():
            if r["doctorId"] == "dr-ibrahim-el-azouni-anat":
                by.setdefault(r["chapter"]["title"], []).append(r["name"])
        for title in ("Medulla", "Nuclei of medulla & Features of pons", "Nuclei of pons & midbrain & cerebellum", "4th ventricle"):
            self.assertIn(title, by)
            self.assertTrue(all(n.startswith(title) for n in by[title]), by[title])

    def test_one_order_per_chapter_title_and_no_two_titles_share_an_order(self):
        seen = {}
        for r in self.rows.values():
            key = (r["subject"], r["chapter"]["order"])
            self.assertEqual(seen.setdefault(key, r["chapter"]["title"]), r["chapter"]["title"], key)

    def test_a_revision_or_mini_lecture_sits_with_what_it_covers(self):
        for r in self.rows.values():
            if r["covers"]:
                self.assertEqual(r["chapter"], self.rows[r["covers"][0]]["chapter"], r["key"])


if __name__ == "__main__":
    unittest.main()

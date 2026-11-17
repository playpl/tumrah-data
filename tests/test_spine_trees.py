"""The first-year lists (ZAG59_* channels, owner 2026-11-17): Arabic headers, other bullets, chapters inside a section."""
import json
import unittest

import tg_lists
from spine.tg import mother

TEXT = "\n".join([
    "🔹 Dr. X", "🔗Channel link:", "https://t.me/x",
    "📚المذكرات:", ". Book",
    "🎥 الشرح:", "🔻CELL🔻", ". Cell 2", ".Transport", "Chapter 1 (CHO)", "-Lect1 -> mini",
    "📝Mini Lectures:", ". Cell 2",
    "🔄 المراجعات:", "• All cell",
    "❓الأسئلة:", ". Cell MCQ"])
LINKS = [("Book", 5, 0), ("Cell 2", 6, 0), ("Transport", 7, 0), ("Lect1", 8, 0), ("mini", 9, 0), ("Cell 2", 10, 1),
         ("All cell", 11, 0), ("Cell MCQ", 12, 0)]


class Ent:
    def __init__(self, offset, url):
        self.offset, self.url = offset, url


class Msg:
    id, date, edit_date, media = 40, None, None, None

    def __init__(self, text, links, channel):
        self.message = text
        self.ents = []
        for label, post, nth in links:
            at = -1
            for _ in range(nth + 1):
                at = text.index(label, at + 1)
            self.ents.append((Ent(tg_lists.utf16_len(text[:at]), f"https://t.me/{channel}/{post}"), label))

    def get_entities_text(self):
        return self.ents


def parsed():
    d = tg_lists.parse(Msg(TEXT, LINKS, "ZAG59_Histo"), "ZAG59_Histo")
    d["channel"] = "ZAG59_Histo"
    d["posts"] = {str(p): {"kind": "pdf" if p in (5, 12) else "audio", "size": p, "caption": ""} for _, p, _ in LINKS}
    return d


class YearOneList(unittest.TestCase):
    def test_arabic_headers_make_the_sections(self):
        s = parsed()["sections"]
        self.assertEqual({k: [it["title"] for it in v] for k, v in s.items()},
                         {"pdfs": ["Book"], "lectures": ["Cell 2", "Transport", "Lect1 -> mini"], "minis": ["Cell 2"],
                          "revisions": ["All cell"], "other": ["Cell MCQ"]})

    def test_a_sub_heading_is_the_group_of_the_items_under_it(self):
        lec = parsed()["sections"]["lectures"]
        self.assertEqual([it.get("group") for it in lec], ["CELL", "CELL", "Chapter 1 (CHO)"])
        self.assertEqual([p["label"] for p in lec[2]["parts"]], ["Lect1", "mini"])
        self.assertNotIn("group", parsed()["sections"]["minis"][0])

    def test_only_links_of_the_list_own_channel_are_posts(self):
        d = tg_lists.parse(Msg(TEXT, LINKS, "ZAG59_Histo"), "ZAG59_bio")
        self.assertEqual({p["post"] for s in d["sections"].values() for it in s for p in it["parts"]}, {None})

    def test_the_year_two_channel_reads_as_before(self):
        text = "DR\n\nPDFs\n\n- A\n\nLectures\n\n- Neuron 1\n. not an item\n\nRevisions\n"
        d = tg_lists.parse(Msg(text, [("A", 1, 0), ("Neuron 1", 2, 0)], tg_lists.CHANNEL))
        self.assertEqual([it["title"] for it in d["sections"]["lectures"]], ["Neuron 1"])
        self.assertNotIn("group", d["sections"]["lectures"][0])


class YearOneMother(unittest.TestCase):
    def test_references(self):
        self.assertEqual(mother.ref_of("ZAG59_bio/29"), ("ZAG59_bio", 29))
        self.assertEqual(mother.ref_of(1632), (mother.CHANNEL, 1632))
        self.assertEqual(mother.ref({"id": 29, "channel": "ZAG59_bio"}), "ZAG59_bio/29")
        self.assertEqual(mother.ref({"id": 1632}), "1632")
        self.assertEqual(mother.cache_dir("ZAG59_bio/29"), mother.CACHE / "ZAG59_bio" / "29")

    def test_the_trees_never_give_a_year_two_fallback_list(self):
        two = mother.tree_lists(2)
        self.assertIn(1639, two)                      # Dr. Khaled Aboelfadl, new
        self.assertIn(1562, two)                      # Dr. Basel: his only list
        for old in (1205, 1267, 1335, 1598, 1538, 1373, 1457):
            self.assertNotIn(old, two)
        one = mother.tree_lists(1)
        self.assertEqual(len(one), 20)
        self.assertIn("ZAG59_Anatomy/39", one)

    def test_chapter_is_the_group_and_a_bare_lecture_number_gets_its_chapter(self):
        lst = parsed()
        rows = [(1, "ignore", []), (2, "lecture", []), (3, "lecture", []), (4, "lecture", []), (5, "mini", [4]),
                (6, "mini", [2]), (7, "revision", [2, 3]), (8, "ignore", [])]
        m, errors = mother.parse("\n".join(json.dumps({"link": k, "role": r, "covers": c}) for k, r, c in rows), lst)
        self.assertEqual(errors, [])
        self.assertEqual((m[2]["chapter"], m[2]["name"]), ("CELL", "Cell 2"))
        self.assertEqual((m[4]["chapter"], m[4]["name"]), ("Chapter 1 (CHO)", "CHO Lect1"))
        self.assertEqual((m[5]["chapter"], m[5]["name"]), ("Chapter 1 (CHO)", "CHO Lect1 mini"))
        self.assertEqual((m[6]["chapter"], m[6]["name"]), ("CELL", "Cell 2 (mini lecture)"))
        self.assertEqual(m[7]["chapter"], "CELL")
        self.assertIn("Lectures / CELL: under \"Cell 2\"", mother.render(lst))


if __name__ == "__main__":
    unittest.main()

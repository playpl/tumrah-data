import json
import tempfile
import unittest
from pathlib import Path

from spine.parity import mother as parity
from spine.tg import cli, mother


def part(label, post):
    return {"label": label, "post": post}


def make_list(extra_lecture=None, revisions=True):
    """A doctor's list: 1 PDF, Spinal cord (2 parts), CSF, Pons (not posted yet), 1 mini, 2 revisions.
    The Pons revision links post 13, the CSF lecture: the doctor's wrong link."""
    lectures = [{"title": "Spinal cord", "parts": [part("Part 1", 11), part("Part2", 12)]},
                {"title": "CSF ", "parts": [part("CSF", 13)]},
                {"title": "Pons", "parts": []}]
    if extra_lecture:
        lectures.append({"title": extra_lecture, "parts": [part(extra_lecture, 16)]})
    return {"id": 99, "edit_date": None, "text": "Dr X\n- Spinal cord\n- CSF\n- Pons\nRevisions\n- CSF\n- Pons",
            "sections": {"pdfs": [{"title": "CNS", "parts": [part("CNS", 10)]}],
                         "lectures": lectures,
                         "minis": [{"title": "Spinal part 1", "parts": [part("Spinal part 1", 14)]}],
                         "revisions": [{"title": "CSF", "parts": [part("CSF", 15)]},
                                       {"title": "Pons", "parts": [part("Pons", 13)]}] if revisions else [],
                         "other": []},
            "posts": {"10": {"kind": "pdf", "size": 5, "caption": "Dr X CNS"},
                      "11": {"kind": "youtube", "caption": "https://youtu.be/abcdef1 part 1", "youtube": ["https://youtu.be/abcdef1"]},
                      "12": {"kind": "audio", "size": 7, "caption": "Spinal 2"},
                      "13": {"kind": "audio", "size": 8, "caption": "Dr X CSF 2X"},
                      "14": {"kind": "audio", "size": 2, "caption": "Spinal 1 (mini)"},
                      "15": {"kind": "audio", "size": 3, "caption": "CSF (revision)"},
                      "16": {"kind": "audio", "size": 9, "caption": "new"}}}


def answer(rows):
    return "\n".join(json.dumps({"link": k, "role": role, "covers": covers}) for k, role, covers in rows)


GOOD = [(1, "ignore", []), (2, "lecture", []), (3, "lecture", []), (4, "lecture", []), (5, "lecture", []),
        (6, "mini", [2]), (7, "revision", [4]), (8, "revision", [5])]


class Links(unittest.TestCase):
    def test_links_follow_the_sections_and_keep_an_item_with_no_post(self):
        ls = mother.links(make_list())
        self.assertEqual([(l["k"], l["section"], l["item"], l["post"]) for l in ls][3:6],
                         [(4, "lectures", "CSF", 13), (5, "lectures", "Pons", None), (6, "minis", "Spinal part 1", 14)])

    def test_a_post_linked_twice_belongs_to_the_section_its_caption_fits(self):
        ls = mother.links(make_list())
        self.assertIsNone(ls[3]["wrong"])                     # the CSF lecture owns post 13
        self.assertEqual(ls[7]["wrong"], 4)                   # the Pons revision that links it is the wrong link
        self.assertIn("WRONG LINK (this post belongs to link 4)", mother.render(make_list()))

    def test_the_key_changes_with_the_message_only(self):
        self.assertEqual(mother.cache_key(make_list()), mother.cache_key(make_list()))
        self.assertNotEqual(mother.cache_key(make_list()), mother.cache_key(make_list("Midbrain")))


class Finish(unittest.TestCase):
    def setUp(self):
        self.lst = make_list()
        self.m, self.errors = mother.parse(answer(GOOD), self.lst)

    def test_a_good_answer_is_valid(self):
        self.assertEqual(self.errors, [])

    def test_chapter_and_name_are_the_message_words(self):
        self.assertEqual((self.m[3]["chapter"], self.m[3]["name"]), ("Spinal cord", "Spinal cord part 2"))
        self.assertEqual((self.m[5]["chapter"], self.m[5]["name"]), ("Pons", "Pons"))

    def test_a_part_label_with_more_words_keeps_the_item(self):
        lst = make_list()
        lst["sections"]["lectures"][1]["parts"] = [part("Part 2 + lat. Ventricle", 13)]
        m, _ = mother.parse(answer(GOOD), lst)
        self.assertEqual(m[4]["name"], "CSF part 2 + lat. Ventricle")

    def test_a_mini_or_revision_that_reads_like_a_lecture_gets_its_kind(self):
        self.assertEqual((self.m[6]["chapter"], self.m[6]["name"]), ("Spinal cord", "Spinal part 1 (mini lecture)"))
        self.assertEqual((self.m[7]["chapter"], self.m[7]["name"]), ("CSF", "CSF revision"))

    def test_a_wrong_link_is_ignored_whatever_the_reader_says(self):
        self.assertEqual((self.m[8]["role"], self.m[8]["covers"]), ("ignore", []))

    def test_readers_agree_on_role_and_covers(self):
        other, _ = mother.parse(answer(GOOD[:6] + [(7, "revision", [4, 5]), (8, "ignore", [])]), self.lst)
        self.assertEqual(mother.agree(self.m, other), [7])


class PdfNeverLecture(unittest.TestCase):
    def test_a_pdf_post_cannot_be_a_lecture(self):
        _, errors = mother.parse(answer([(1, "lecture", [])] + GOOD[1:]), make_list())
        self.assertEqual(errors, ["link 1: a pdf post cannot be a lecture"])

    def test_missing_links_and_bad_covers_are_errors(self):
        _, errors = mother.parse(answer(GOOD[:5] + [(6, "mini", [2, 3]), (7, "revision", [1])]), make_list())
        self.assertEqual(errors, ["link 8 has no answer", "link 6: a mini covers 2 lectures",
                                  "link 7: covers a link that is not a lecture of this message"])


class Fixes(unittest.TestCase):
    def test_a_hand_fix_names_posts_or_an_item_with_no_post(self):
        with tempfile.TemporaryDirectory() as tmp:
            old, mother.FIXES = mother.FIXES, Path(tmp) / "fixes.json"
            try:
                mother.FIXES.write_text(json.dumps({"99": [{"post": 15, "role": "revision", "covers": [13, "Pons"]}]}))
                lst = make_list()
                m, _ = mother.parse(answer(GOOD), lst)
                self.assertEqual(mother.apply_fixes(m, lst), [7])
                self.assertEqual((m[7]["covers"], m[7]["chapter"]), ([4, 5], "Pons"))
                self.assertEqual(mother.validate(m, lst), [])
            finally:
                mother.FIXES = old


class Settle(unittest.TestCase):
    def test_two_equal_answers_give_the_map_and_two_different_ones_do_not(self):
        lst = make_list()
        m, _, line = cli.settle(lst, {"A": answer(GOOD), "B": answer(GOOD)})
        self.assertEqual(m[2]["role"], "lecture")
        self.assertIn("two readers agree on all 8 links", line)
        m, _, line = cli.settle(lst, {"A": answer(GOOD), "B": answer(GOOD[:5] + [(6, "mini", [3])] + GOOD[6:])})
        self.assertIsNone(m)
        self.assertIn("they differ on links [6]", line)
        self.assertIsNone(cli.settle(lst, {"A": answer(GOOD), "B": None})[0])


class ToDoctor(unittest.TestCase):
    INDEX = {("yt", "abcdef1"): "x-001", ("post", 12): "x-002", ("post", 13): "x-003", ("title", "dr-x", "pons"): "x-004",
             ("post", 14): "x-005", ("post", 15): "x-006"}

    def block(self):
        lst = make_list()
        m, _ = mother.parse(answer(GOOD), lst)
        return mother.to_doctor(lst, m, "dr-x", "anatomy", self.INDEX)

    def test_the_block_has_the_shape_of_the_hand_file(self):
        doc = self.block()
        self.assertEqual([c["title"] for c in doc["chapters"]], ["Spinal cord", "CSF", "Pons"])
        self.assertEqual(doc["chapters"][0]["items"], [
            {"id": "x-001", "name": "Spinal cord part 1", "post": 11},
            {"id": "x-002", "name": "Spinal cord part 2", "post": 12},
            {"id": "x-005", "name": "Spinal part 1 (mini lecture)", "kind": "summary", "covers": ["x-001"], "post": 14}])
        self.assertEqual(doc["chapters"][2]["items"], [{"id": "x-004", "name": "Pons", "post": None}])

    def test_two_list_items_with_the_same_words_are_two_chapters(self):
        lst = make_list(extra_lecture="Spinal cord")        # Nagib 1638: "Internal capsule" twice, far apart
        rows = [(1, "ignore", [])] + [(k, "lecture", []) for k in range(2, 7)] + \
            [(7, "mini", [2]), (8, "revision", [4]), (9, "revision", [5])]
        m, _ = mother.parse(answer(rows), lst)
        doc = mother.to_doctor(lst, m, "dr-x", "anatomy", {**self.INDEX, ("post", 16): "x-007"})
        self.assertEqual([c["title"] for c in doc["chapters"]], ["Spinal cord", "CSF", "Pons", "Spinal cord"])
        self.assertEqual([i["id"] for i in doc["chapters"][3]["items"]], ["x-007"])

    def test_parity_is_exact_against_itself_and_sees_a_moved_lesson(self):
        hand = self.block()
        self.assertEqual(parity.compare(hand, self.block()), [])
        hand["chapters"][1]["items"][1]["covers"] = ["x-001"]
        hand["chapters"][0]["items"][0]["name"] = "spinal  cord PART 1"        # case and spacing are not a difference
        self.assertEqual(parity.compare(hand, self.block()), ["x-006 covers: hand ['x-001'] / agent ['x-003']"])

    def test_a_held_duplicate_answers_with_its_twin(self):
        with tempfile.TemporaryDirectory() as tmp:
            for lid, extra in (("x-074", {"source": {"file": "a.mp4"}}),
                               ("x-086", {"source": {"telegram": "https://t.me/ch/1732"},
                                          "hold": "duplicate: same lecture as x-074 (Telegram post 1732)"})):
                (Path(tmp) / lid).mkdir()
                (Path(tmp) / lid / "lecture.json").write_text(json.dumps({"id": lid, "doctor": "dr-x", "title": "Spinal revision", **extra}))
            index = mother.lecture_index(Path(tmp))
            self.assertEqual(index[("post", 1732)], "x-074")


def row(lst, rows):
    m, errors = mother.parse(answer(rows), lst)
    assert not errors, errors
    return {"map": {str(k): v for k, v in m.items()}, "posts": {str(l["k"]): l["post"] for l in mother.links(lst)}}


class DiffAddEditDelete(unittest.TestCase):
    def test_add_edit_delete_by_post(self):
        prev = row(make_list(), GOOD)
        new_list = make_list("Midbrain", revisions=False)      # a new lecture; both revisions are gone
        new = row(new_list, [(1, "ignore", []), (2, "lecture", []), (3, "lecture", []), (4, "lecture", []),
                             (5, "lecture", []), (6, "lecture", []), (7, "mini", [3])])
        changes = mother.diff(prev, new)
        self.assertEqual([(c["change"], c["post"]) for c in changes], [("add", 16), ("delete", 15), ("edit", 14)])
        self.assertEqual(changes[2]["fields"], ["covers"])
        self.assertEqual(changes[0]["chapter"], "Midbrain")

    def test_the_first_map_is_all_additions(self):
        self.assertEqual({c["change"] for c in mother.diff(None, row(make_list(), GOOD))}, {"add"})


class MassDeleteHeld(unittest.TestCase):
    def test_a_deletion_waits_for_a_second_fetch(self):
        self.assertIn("two fetches", mother.held([{"change": "delete"}], 30, minutes_between_fetches=0))
        self.assertEqual(mother.held([{"change": "delete"}], 30, minutes_between_fetches=20), "")

    def test_many_deletions_wait_for_the_owner(self):
        self.assertIn("4 of 30", mother.held([{"change": "delete"}] * 4, 30, minutes_between_fetches=20))
        self.assertIn("3 of 10", mother.held([{"change": "delete"}] * 3, 10, minutes_between_fetches=20))
        self.assertEqual(mother.held([{"change": "add"}] * 9, 10), "")


if __name__ == "__main__":
    unittest.main()

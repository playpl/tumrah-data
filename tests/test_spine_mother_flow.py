import copy
import unittest

from spine.tg import flow


def doc(name, chapters):
    return {"doctor": name, "list": 1, "subject": "x",
            "chapters": [{"title": t, "items": [{"id": i, "name": i} for i in ids]} for t, ids in chapters]}


class AddOnly(unittest.TestCase):
    def test_new_items_land_under_their_chapter_and_nothing_else_moves(self):
        hand = {"doctors": [doc("d1", [("Spinal cord", ["c1", "c2"]), ("Medulla", ["c5"])])]}
        agent = {"doctors": [doc("d1", [("Spinal cord", ["c1", "c2", "c3"]), ("Pons", ["c4"]), ("Medulla", ["c5"])])]}
        before = copy.deepcopy(hand)
        lines = flow.add_only(hand, agent)
        chapters = [(c["title"], [i["id"] for i in c["items"]]) for c in hand["doctors"][0]["chapters"]]
        self.assertEqual(chapters, [("Spinal cord", ["c1", "c2", "c3"]), ("Pons", ["c4"]), ("Medulla", ["c5"])])
        self.assertEqual(len(lines), 2)
        self.assertEqual(before["doctors"][0]["chapters"][1]["items"], [{"id": "c5", "name": "c5"}])

    def test_a_removed_item_stays_in_the_hand_file(self):
        hand = {"doctors": [doc("d1", [("A", ["c1", "c2"])])]}
        flow.add_only(hand, {"doctors": [doc("d1", [("A", ["c1"])])]})
        self.assertEqual([i["id"] for i in hand["doctors"][0]["chapters"][0]["items"]], ["c1", "c2"])

    def test_new_doctor_is_added_whole(self):
        hand = {"doctors": []}
        lines = flow.add_only(hand, {"doctors": [doc("d2", [("A", ["c9"])])]})
        self.assertEqual(hand["doctors"][0]["doctor"], "d2")
        self.assertIn("new doctor", lines[0])


if __name__ == "__main__":
    unittest.main()

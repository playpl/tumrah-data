import unittest

from spine.align import bm25, prefilter, windows

TEXTS = ["The spinal cord ends at the lower border of the first lumbar vertebra.",
         "It is surrounded by three meninges.",
         "Pyramidal cells",
         "The pyramidal cells are multipolar nerve cells of the cerebral cortex.",
         "Stellate cells",
         "The cerebellum has three peduncles that connect it to the brain stem.",
         "Pyramidal cells",
         "The red nucleus is an oval mass of grey matter in the tegmentum of the midbrain."]
LESSON = ["m:L1", "m:L1", "m:L2", "m:L2", "m:L2", "m:L3", "m:L3", "m:L3"]


def handout():
    sents = [{"id": f"m:h:p{n + 1}:s1", "i": n, "kind": "fact", "text": t, "lesson": LESSON[n], "ctx": []}
             for n, t in enumerate(TEXTS)]
    lessons = {l: {"subject": "anatomy"} for l in set(LESSON)}
    return prefilter.Handout("m", sents, lessons)


def item(text, scope=("m:L1", "m:L2", "m:L3")):
    return {"text": text, "scope": list(scope)}


class BM25(unittest.TestCase):
    def test_ranks_exact_first(self):
        idx = bm25.Index([t.lower().split() for t in TEXTS])
        self.assertEqual(idx.top("the cerebellum has three peduncles".split(), 1)[0][0], 5)

    def test_allowed_limits_the_search(self):
        idx = bm25.Index([t.lower().split() for t in TEXTS])
        self.assertEqual(idx.top(["pyramidal", "cells"], 3, allowed={6, 7})[0][0], 6)
        self.assertEqual(idx.top(["nothing"], 3), [])


class Tiers(unittest.TestCase):
    def setUp(self):
        self.H = handout()

    def test_exact_unique_accepted(self):
        res = prefilter.code_tiers([item("It is surrounded by three meninges")], self.H)
        self.assertEqual(res[0], ("A1", (1,)))

    def test_exact_across_two_sentences(self):
        res = prefilter.code_tiers([item(TEXTS[0] + " " + TEXTS[1])], self.H)
        self.assertEqual(res[0], ("A1", (0, 1)))

    def test_fuzzy_needs_anchors_on_both_sides(self):
        reworded = "Pyramidal cells are multipolar nerve cell of cerebral cortex"
        alone = prefilter.code_tiers([item(reworded)], self.H)
        self.assertIsNone(alone[0])
        between = prefilter.code_tiers([item(TEXTS[1]), item(reworded), item(TEXTS[5])], self.H)
        self.assertEqual(between[1], ("A3", (3,)))

    def test_short_needs_neighbours(self):
        alone = prefilter.code_tiers([item("Pyramidal cells")], self.H)
        self.assertIsNone(alone[0])
        pinned = prefilter.code_tiers([item(TEXTS[1]), item("Pyramidal cells"), item(TEXTS[3])], self.H)
        self.assertEqual(pinned[1], ("A4", (2,)))

    def test_candidates_hold_the_corridor_and_the_hits(self):
        items = [item(TEXTS[0]), item("three peduncles join the cerebellum and brain stem"), item(TEXTS[7])]
        res = prefilter.code_tiers(items, self.H)
        cands = prefilter.candidates(items, res, [0, 1, 2], self.H)
        self.assertIn(5, cands)
        self.assertEqual(cands, sorted(cands))
        self.assertEqual(prefilter.windows(3, res), [[0, 1, 2]])
        self.assertEqual(prefilter.windows(2, [("A1", (0,)), ("A1", (1,))]), [])

    def test_page_scope_follows_the_words(self):
        scopes = self.H.page_lessons(["spinal cord lumbar vertebra meninges", "cerebellum peduncles brain stem"])
        self.assertEqual(scopes[0][0], "m:L1")
        self.assertEqual(scopes[1][0], "m:L3")


class Windows(unittest.TestCase):
    def setUp(self):
        self.H = handout()
        self.items = [item(TEXTS[0]), item("three peduncles join the cerebellum to the brain stem"),
                      item("Page 4"), item(TEXTS[7])]
        self.res = prefilter.code_tiers(self.items, self.H)
        self.cands = prefilter.candidates(self.items, self.res, [0, 1, 2, 3], self.H)
        self.text, self.key = windows.render(self.items, self.res, [0, 1, 2, 3], self.cands, self.H, label="W1")

    def h(self, pos):
        return next(n for n, p in self.key["h"].items() if p == pos)

    def answer(self, probe_pos=None):
        probe = next(iter(self.key["probe"]))
        want = self.key["h"][str(self.key["probe"][probe][0])] if probe_pos is None else probe_pos
        return "\n".join([f"W1 B{probe} = H{self.h(want)} S", f"W1 B2 = H{self.h(5)} R", "W1 B3 = X"])

    def test_render_hides_one_known_sentence(self):
        self.assertEqual(len(self.key["probe"]), 1)
        self.assertIn("[done=", self.text)
        self.assertEqual(sorted(self.key["open"]), sorted({2, 3} | {int(b) for b in self.key["probe"]}))

    def test_good_answer_parses(self):
        verdicts, errors = windows.parse(self.answer(), self.key, self.H, self.items)
        self.assertEqual(errors, [])
        self.assertEqual(verdicts[1][:3], ("link", [5], "R"))
        self.assertEqual(verdicts[2], "X")

    def test_grammar_rejects_bad_line(self):
        _, errors = windows.parse("\n".join([self.answer(), "W1 B2 is H3 maybe"]), self.key, self.H, self.items)
        self.assertTrue(any("grammar" in e for e in errors))
        _, errors = windows.parse(self.answer().replace("W1 B3 = X", "W1 B3 = H99 S"), self.key, self.H, self.items)
        self.assertTrue(any("no H99" in e for e in errors))
        _, errors = windows.parse("W1 B2 = 0", self.key, self.H, self.items)
        self.assertTrue(any("no answer" in e for e in errors))

    def test_probe_fail_rejects(self):
        wrong = next(p for p in self.cands if p not in (0, 7))
        _, errors = windows.parse(self.answer(probe_pos=wrong), self.key, self.H, self.items)
        self.assertTrue(any(e.startswith("probe") for e in errors))

    def test_same_with_few_shared_words_becomes_reworded_and_flagged(self):
        ans = self.answer().replace(f"W1 B2 = H{self.h(5)} R", f"W1 B2 = H{self.h(1)} S")
        verdicts, _ = windows.parse(ans, self.key, self.H, self.items)
        self.assertEqual((verdicts[1][2], verdicts[1][3]), ("R", True))


class Cells(unittest.TestCase):
    """A table row of several cells links each cell that the handout says word for word near the row's own link."""
    def setUp(self):
        self.H = handout()

    def test_each_cell_found_near_the_row_link(self):
        from spine.align import engine
        row = {"text": "Pyramidal: |  The pyramidal cells are multipolar nerve cells of the cerebral cortex. "
                       "2. Stellate cells are small", "kind": "table_row"}
        self.assertEqual(engine.cell_links(row, {"m:h:p3:s1"}, self.H), ["m:h:p4:s1"])

    def test_a_cell_in_another_lesson_or_a_one_cell_row_adds_nothing(self):
        from spine.align import engine
        row = {"text": "Meninges | The red nucleus is an oval mass of grey matter in the tegmentum of the midbrain."}
        self.assertEqual(engine.cell_links(row, {"m:h:p2:s1"}, self.H), [])        # p8 is lesson L3, the link L1
        self.assertEqual(engine.cell_links({"text": TEXTS[3]}, {"m:h:p3:s1"}, self.H), [])


if __name__ == "__main__":
    unittest.main()

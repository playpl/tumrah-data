import unittest

from spine.graph import twin


def sent(m, i, text, lesson="L1"):
    return {"id": f"{m}:s{i}", "i": i, "kind": "fact", "text": text, "rows": [f"{m}:l{i}"], "lesson": f"{m}:{lesson}"}


A_TEXT = ["The deltoid muscle covers the shoulder joint laterally",
          "Axillary nerve supplies the deltoid and teres minor",
          "Site: chondrocyte lies inside a lacuna within the matrix",
          "Nothing like this sentence exists on the other handout at all",
          "Radial nerve winds around the spiral groove of humerus"]
B_TEXT = ["Front matter of the other university",
          "The deltoid muscle covers the shoulder joint laterally",
          "Axillary nerve supplies the deltoid and teres minor",
          "Chondrocyte lies inside a lacuna within the matrix",
          "Radial nerve winds around the spiral groove of humerus"]


class Twin(unittest.TestCase):
    def setUp(self):
        self.a = [sent("a", i, t) for i, t in enumerate(A_TEXT)]
        self.b = [sent("b", i, t) for i, t in enumerate(B_TEXT)]
        self.m = twin.match(self.a, self.b)

    def test_same_words_and_near_words_map_one_to_one(self):
        self.assertEqual(self.m["a:s0"][:2], ("b:s1", "T1"))
        self.assertEqual(self.m["a:s2"][:2], ("b:s3", "T2"))
        self.assertNotIn("a:s3", self.m)
        self.assertEqual(len({v[0] for v in self.m.values()}), len(self.m))

    def test_a_range_is_carried_as_dst_rows(self):
        self.assertEqual(twin.carry_range("a:l0", "a:l4", self.a, self.b, self.m), [{"from": "b:l1", "to": "b:l4"}])

    def test_an_unmapped_pointer_line_takes_its_neighbour(self):
        lines, lesson = twin.carry_lines(["a:l3"], self.a, self.b, self.m)
        self.assertEqual(lesson, "b:L1")
        self.assertTrue(set(lines) <= {"b:l3", "b:l4"} and lines)

    def test_a_far_match_against_the_order_is_dropped(self):
        b = self.b + [sent("b", 5 + k, f"filler sentence number {k} about nothing") for k in range(60)]
        b.append(sent("b", 65, "Site: a lone sentence that reappears far away in the handout"))
        a = self.a
        m = twin.in_order({"a:s0": ("b:s1", "T1", 1), "a:s4": ("b:s4", "T1", 1), "a:s2": ("b:s65", "T1", 1)}, a, b)
        self.assertNotIn("a:s2", m)
        self.assertIn("a:s4", m)


if __name__ == "__main__":
    unittest.main()

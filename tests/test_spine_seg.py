import unittest

import numpy as np

from spine.seg import prior, scope, segment


def segs(*rows):
    return [{"p": [a, b], "b": None if c is None else [c, d]} for a, b, c, d in rows]


class Paragraphs(unittest.TestCase):
    def test_stamps_and_joined_lines(self):
        p = prior.paragraphs("[00:00] one\nmore\n[01:05] two\n[1:02:03] three\n")
        self.assertEqual([(x["n"], x["start"], x["text"]) for x in p],
                         [(1, 0, "one more"), (2, 65, "two"), (3, 3723, "three")])
        self.assertEqual(prior.stamp(3723), "1:02:03")


class PriorPath(unittest.TestCase):
    def test_monotone_and_none(self):
        m = np.array([[1, 0, 0, 0], [0, 0, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0], [0, 0, 0, 1]], dtype=float)
        pts = prior.path(m)
        self.assertEqual(pts[1], None)                       # matches nothing
        hits = [p for p in pts if p is not None]
        self.assertEqual(hits, sorted(hits))                 # never goes back
        self.assertEqual(pts[0], 0)
        self.assertEqual(pts[4], 3)

    def test_trimmed_window(self):
        self.assertEqual(scope.trimmed([50, 51, 52, 53, 54, 55, 56, 57, 58, 900], 1000, margin=10, trim=0.1),
                         (41, 68))
        self.assertIsNone(scope.trimmed([], 10))


class MonotonicEnforced(unittest.TestCase):
    def test_clean_answer(self):
        s = segs((1, 3, 1, 5), (4, 4, None, None), (5, 9, 5, 12))
        self.assertEqual(segment.check(s, 9, 20), [])

    def test_going_back_is_found(self):
        s = segs((1, 3, 10, 15), (4, 6, 2, 4), (7, 9, 15, 18))
        self.assertTrue(any("goes back" in p for p in segment.check(s, 9, 20)))

    def test_coverage_problems(self):
        probs = segment.check(segs((2, 3, 1, 2), (5, 8, 3, 4)), 9, 20)
        self.assertTrue(any("not P1" in p for p in probs))
        self.assertTrue(any("right after" in p for p in probs))
        self.assertTrue(any("not P9" in p for p in probs))

    def test_parse_grammar(self):
        got, bad = segment.parse("P1-P4 = B1-B9\n```\np5 - p6 = none\nP7-P8 = B10\nchatter")
        self.assertEqual(got, segs((1, 4, 1, 9), (5, 6, None, None)))
        self.assertEqual(bad, ["P7-P8 = B10", "chatter"])


class RepairBoundedReask(unittest.TestCase):
    def test_offender_bounds_from_the_chain(self):
        s = segs((1, 5, 1, 10), (6, 6, 40, 45), (7, 12, 11, 20), (13, 20, 21, 30))
        fixed, asks, share = segment.repair(s, 50)
        self.assertEqual(asks, [{"seg": 1, "p": [6, 6], "lo": 10, "hi": 11, "was": [40, 45]}])
        self.assertIsNone(fixed[1]["b"])
        self.assertEqual(fixed[1]["flag"], "reask")
        self.assertAlmostEqual(share, 1 / 20)


class CoverageAllParagraphs(unittest.TestCase):
    def test_agreement_per_paragraph(self):
        a = segs((1, 5, 1, 10), (6, 10, None, None))
        b = segs((1, 5, 3, 12), (6, 8, None, None), (9, 10, 30, 40))
        self.assertAlmostEqual(segment.agree(a, b, 10), 0.8)
        self.assertEqual(segment.disputed(a, b, 10), [[9, 10]])

    def test_record_times_and_handout(self):
        paras = [{"n": 1, "start": 0, "text": ""}, {"n": 2, "start": 30, "text": ""}, {"n": 3, "start": 60, "text": ""}]
        sents = [{"id": "b1"}, {"id": "b2"}, {"id": "b3"}]
        rows = segment.record(segs((1, 2, 1, 2), (3, 3, None, None)), paras, sents, {"b2": ["h9"]}, "x")
        self.assertEqual((rows[0]["start"], rows[0]["end"], rows[0]["book"], rows[0]["handout"]), (0, 60, ["b1", "b2"], ["h9"]))
        self.assertEqual((rows[1]["end"], rows[1]["book"]), (None, None))


class TranslitAnchors(unittest.TestCase):
    def test_arabic_script_term_reaches_the_book_word(self):
        sents = [{"text": "The thalamus relays sensation", "ctx": []}, {"text": "Cerebellum controls balance", "ctx": []}]
        m = prior.scores([{"n": 1, "start": 0, "text": "الثالاموس ده مهم"}], sents)
        self.assertEqual(int(np.argmax(m[0])), 0)



class CodeRepairs(unittest.TestCase):
    def test_small_holes_become_none(self):
        s, holes = segment.fill(segs((2, 5, 1, 3), (7, 8, 4, 6)), 10)
        self.assertEqual([x["p"] for x in s], [[1, 1], [2, 5], [6, 6], [7, 8], [9, 10]])
        self.assertEqual(holes, 3)
        self.assertEqual(segment.check(s, 10, 20), [])

    def test_big_hole_is_refused(self):
        self.assertIsNone(segment.fill(segs((1, 2, 1, 3), (9, 10, 4, 6)), 10)[0])

    def test_overlap_is_clipped_not_dropped(self):
        s = segment.clip(segs((1, 5, 26, 36), (6, 9, 29, 40), (10, 12, 41, 44)))
        self.assertEqual([x["b"] for x in s], [[26, 36], [36, 40], [41, 44]])
        self.assertEqual(segment.check(s, 12, 50), [])


if __name__ == "__main__":
    unittest.main()

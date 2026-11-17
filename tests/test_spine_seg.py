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
        self.assertEqual(got, segs((1, 4, 1, 9), (5, 6, None, None), (7, 8, 10, 10)))
        self.assertEqual(bad, ["chatter"])


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


def collapsed_answer(n_paras=173):
    """The cns-036 failure: a real opening, then every later paragraph sent to one 6-line table (B293-B298)."""
    rows = [(1, 9, 285, 286), (10, 20, 287, 291), (21, 22, None, None), (23, 34, 293, 298)]
    p = 35
    while p <= n_paras:
        q = min(p + 11, n_paras)
        rows.append((p, q, 293, 298))
        p = q + 1
    return segs(*rows)


class RestatementIsCountedNotHidden(unittest.TestCase):
    def test_restating_the_last_line_is_clipped_and_flagged(self):
        s = segment.clip(segs((1, 5, 1, 10), (6, 17, 9, 10)))
        self.assertEqual((s[1]["b"], s[1]["flag"]), ([10, 10], "clipped"))

    def test_same_line_again_is_flagged(self):
        s = segment.clip(segs((1, 5, 1, 10), (6, 17, 10, 10)))
        self.assertEqual((s[1]["b"], s[1]["flag"]), ([10, 10], "clipped"))

    def test_a_short_restatement_is_fine(self):
        s = segment.clip(segs((1, 5, 1, 10), (6, 7, 10, 10)))
        self.assertEqual(segment.check(s, 7, 50), [])

    def test_too_much_restating_is_rejected(self):
        rows = [(1, 10, 1, 10), (11, 22, 10, 10), (23, 34, 10, 10), (35, 44, 11, 20), (45, 54, 21, 30),
                (55, 64, 31, 40), (65, 74, 41, 50), (75, 84, 51, 60), (85, 94, 61, 70), (95, 100, 71, 80)]
        fixed, problems, share = segment.judge_segs(segs(*rows), 100, 100)
        self.assertIsNone(fixed)
        self.assertTrue(any("re-states" in p for p in problems))

    def test_restating_within_the_limit_is_accepted(self):
        rows = [(1, 10, 1, 10), (11, 20, 10, 10), (21, 30, 11, 20), (31, 40, 21, 30), (41, 50, 31, 40),
                (51, 60, 41, 50), (61, 70, 51, 60), (71, 80, 61, 70), (81, 90, 71, 80), (91, 100, 81, 90)]
        fixed, problems, share = segment.judge_segs(segs(*rows), 100, 100)
        self.assertIsNotNone(fixed)

    def test_new_content_overlap_is_clipped(self):
        s = segment.clip(segs((1, 5, 26, 36), (6, 9, 29, 40)))
        self.assertEqual(s[1]["b"], [36, 40])


class SegmentRangeGuard(unittest.TestCase):
    def test_reversed_range_is_a_problem(self):
        self.assertTrue(any("not a range" in p for p in segment.check(segs((1, 4, 9, 3)), 4, 20)))

    def test_range_past_the_slice_is_a_problem(self):
        self.assertTrue(any("not a range" in p for p in segment.check(segs((1, 4, 3, 25)), 4, 20)))

    def test_over_twelve_paragraphs_is_a_problem(self):
        self.assertTrue(any("over 12 paragraphs" in p for p in segment.check(segs((1, 13, 1, 5)), 13, 20)))

    def test_over_120_book_lines_is_a_problem(self):
        self.assertTrue(any("over 120 book lines" in p for p in segment.check(segs((1, 2, 1, 200)), 2, 300)))


class DominantRangeGuard(unittest.TestCase):
    def test_one_range_over_thirty_percent_is_found(self):
        s = segs((1, 12, 1, 5), (13, 24, 1, 5), (25, 36, 1, 5), (37, 48, 6, 9), (49, 60, 10, 12), (61, 72, 13, 15),
                 (73, 84, 16, 18), (85, 96, 19, 20), (97, 100, 21, 22))
        self.assertEqual(segment.dominant(s, 100), ([1, 5], 0.36))

    def test_a_spread_talk_is_fine(self):
        s = segs((1, 12, 1, 5), (13, 24, 6, 9), (25, 36, 10, 13), (37, 48, 14, 17), (49, 60, 18, 21),
                 (61, 72, 22, 25), (73, 84, 26, 29), (85, 96, 30, 33), (97, 100, 34, 35))
        self.assertIsNone(segment.dominant(s, 100))

    def test_tiny_answers_are_not_judged_by_share(self):
        self.assertIsNone(segment.dominant(segs((1, 5, 1, 5)), 5))


class JudgeWholeAnswer(unittest.TestCase):
    def test_collapsed_answer_is_rejected(self):
        fixed, problems, share = segment.judge_segs(collapsed_answer(), 173, 324)
        self.assertIsNone(fixed)

    def test_clean_long_answer_is_accepted(self):
        rows = [(1, 12, 1, 10), (13, 24, 11, 20), (25, 36, 21, 30), (37, 48, 31, 40), (49, 60, 41, 50),
                (61, 72, 51, 60), (73, 84, 61, 70), (85, 96, None, None), (97, 108, 71, 80), (109, 120, 81, 90)]
        fixed, problems, share = segment.judge_segs(segs(*rows), 120, 100)
        self.assertIsNotNone(fixed)
        self.assertEqual(share, 0.0)

    def test_twenty_percent_offenders_are_the_limit(self):
        ok = segs((1, 12, 1, 10), (13, 24, 11, 20), (25, 36, 21, 30), (37, 48, 2, 3), (49, 60, 41, 50),
                  (61, 72, 51, 60), (73, 84, 61, 70), (85, 96, 71, 80), (97, 100, 81, 90))
        fixed, problems, share = segment.judge_segs(ok, 100, 100)
        self.assertAlmostEqual(share, 0.12)
        self.assertIsNotNone(fixed)

    def test_bad_lines_alone_do_not_break_a_clean_answer(self):
        fixed, problems, share = segment.judge_segs(segs((1, 5, 1, 10), (6, 10, 11, 20)), 10, 50, bad=["chatter"])
        self.assertIsNotNone(fixed)


class NoneIsNotAnAnswer(unittest.TestCase):
    def test_all_none_is_rejected(self):
        # cns-011: both readers said NONE for all 117 paragraphs; they agreed, so agreement alone accepted it
        rows = [(p, min(p + 11, 117), None, None) for p in range(1, 118, 12)]
        fixed, problems, share = segment.judge_segs(segs(*rows), 117, 1177)
        self.assertIsNone(fixed)
        self.assertTrue(any("NONE for" in p for p in problems))

    def test_a_quarter_none_is_fine(self):
        rows = [(1, 12, 1, 10), (13, 24, 11, 20), (25, 36, None, None), (37, 48, 21, 30), (49, 60, 31, 40),
                (61, 72, 41, 50), (73, 84, 51, 60), (85, 96, 61, 70), (97, 100, 71, 80)]
        fixed, problems, share = segment.judge_segs(segs(*rows), 100, 100)
        self.assertIsNotNone(fixed)


class ParserRaw(unittest.TestCase):
    def test_spaces_and_case_and_backticks(self):
        got, bad = segment.parse("  `P1 - P3 = b1 - b9`  \np4-p4 = none\n")
        self.assertEqual(got, segs((1, 3, 1, 9), (4, 4, None, None)))
        self.assertEqual(bad, [])

    def test_single_paragraph_and_single_line_forms(self):
        got, bad = segment.parse("P1 = NONE\nP120 = B28-B34\nP82-P84 = B40\nP5-P6 = B7-B9")
        self.assertEqual(got, segs((1, 1, None, None), (120, 120, 28, 34), (82, 84, 40, 40), (5, 6, 7, 9)))
        self.assertEqual(bad, [])

    def test_en_dash_is_reported_not_silently_read(self):
        got, bad = segment.parse("P1\u2013P3 = B1\u2013B9")
        self.assertEqual(got, [])
        self.assertEqual(bad, ["P1\u2013P3 = B1\u2013B9"])

    def test_prose_is_reported(self):
        got, bad = segment.parse("Here are the segments:\n---\nP1-P2 = B1-B2")
        self.assertEqual(got, segs((1, 2, 1, 2)))
        self.assertEqual(bad, ["Here are the segments:", "---"])


if __name__ == "__main__":
    unittest.main()

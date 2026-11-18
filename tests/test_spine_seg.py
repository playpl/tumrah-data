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

    def test_typographic_dash_is_the_same_range(self):
        got, bad = segment.parse("P1\u2013P3 = B1\u2013B9")
        self.assertEqual(got, segs((1, 3, 1, 9)))
        self.assertEqual(bad, [])

    def test_prose_is_reported(self):
        got, bad = segment.parse("Here are the segments:\n---\nP1-P2 = B1-B2")
        self.assertEqual(got, segs((1, 2, 1, 2)))
        self.assertEqual(bad, ["Here are the segments:", "---"])


class ParserFormatting(unittest.TestCase):
    """Formatting variants a reader may add. Each must read as the same segment; none may change its meaning."""

    def test_bom_nbsp_zero_width_and_arabic_digits(self):
        got, bad = segment.parse("﻿P1 - P3 = B1-B9\nP4 = B10​\nP٥٠ = NONE")
        self.assertEqual(got, segs((1, 3, 1, 9), (4, 4, 10, 10), (50, 50, None, None)))
        self.assertEqual(bad, [])

    def test_bullets_numbers_bold_and_trailing_period(self):
        got, bad = segment.parse("- P1-P3 = B1-B9.\n* P4 = NONE\n2. **P5-P6 = B10-B12**\n`P7-P8 = B13`;")
        self.assertEqual(got, segs((1, 3, 1, 9), (4, 4, None, None), (5, 6, 10, 12), (7, 8, 13, 13)))
        self.assertEqual(bad, [])

    def test_colon_and_arrow_for_equals(self):
        got, bad = segment.parse("P1-P3: B1-B9\nP4 → NONE")
        self.assertEqual(got, segs((1, 3, 1, 9), (4, 4, None, None)))
        self.assertEqual(bad, [])

    def test_notes_with_paragraph_numbers_are_prose(self):
        # cns-018 reader A: explanatory bullets that mention P-numbers and B-numbers but are not segments
        got, bad = segment.parse("- P2�P9 covers adaptation (see B26)\n- P22 opens the topic\nP1-P3 = B1-B9")
        self.assertEqual(got, segs((1, 3, 1, 9)))
        self.assertEqual(len(bad), 2)

    def test_crlf_and_blank_lines(self):
        got, bad = segment.parse("P1-P3 = B1-B9\r\n\r\n\r\nP4-P4 = NONE\r\n")
        self.assertEqual(got, segs((1, 3, 1, 9), (4, 4, None, None)))
        self.assertEqual(bad, [])


class MalformedSegmentIsNotGuessed(unittest.TestCase):
    def test_a_segment_line_that_does_not_parse_rejects_the_answer(self):
        rows = [(1, 5, 1, 10), (6, 10, 11, 20)]
        fixed, problems, share = segment.judge_segs(segs(*rows), 10, 50, bad=["P6-P10 = B11 to B20 approx"])
        self.assertIsNone(fixed)
        self.assertTrue(any("did not parse" in p for p in problems))

    def test_prose_next_to_good_segments_is_fine(self):
        rows = [(1, 5, 1, 10), (6, 10, 11, 20)]
        fixed, problems, share = segment.judge_segs(segs(*rows), 10, 50, bad=["Notes: the doctor is clear."])
        self.assertIsNotNone(fixed)


class RepairCannotBreakTheShareRules(unittest.TestCase):
    """The fuzz found this: NONE was counted before repair, so repair could push an answer over 50% NONE."""

    def test_none_created_by_repair_is_counted(self):
        # 5 NONE paragraphs plus one out-of-order paragraph repaired to NONE = 6 of 10 (60%)
        rows = [(1, 5, None, None), (6, 6, 857, 897), (7, 10, 317, 327)]
        fixed, problems, share = segment.judge_segs(segs(*rows), 10, 1000)
        self.assertIsNone(fixed)
        self.assertTrue(any("NONE for" in p for p in problems))

    def test_a_repaired_answer_under_the_limit_is_still_accepted(self):
        rows = [(1, 3, None, None), (4, 4, 857, 897), (5, 10, 317, 327), (11, 15, 330, 340), (16, 20, 345, 355)]
        fixed, problems, share = segment.judge_segs(segs(*rows), 20, 1000)
        self.assertIsNotNone(fixed)
        self.assertEqual(sum(s["p"][1] - s["p"][0] + 1 for s in fixed if s["b"] is None), 4)  # 3 NONE + 1 repaired


class ShapeOnlyJudgementIsStable(unittest.TestCase):
    def test_judging_twice_gives_the_same_result(self):
        rows = [(1, 5, 1, 10), (6, 6, 40, 45), (7, 12, 11, 20), (13, 20, 21, 30)]
        a = segment.judge_segs(segs(*rows), 20, 50)
        b = segment.judge_segs(segs(*rows), 20, 50)
        self.assertEqual(a, b)

    def test_zero_paragraphs_is_refused_not_divided(self):
        self.assertIsNone(segment.judge_segs(segs((1, 1, 1, 1)), 0, 10)[0])


class CollectIsSafe(unittest.TestCase):
    """collect() end to end in a temp folder: the job, the slice it was written for, and what is written."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from spine.seg import flow, scope
        from spine import compat
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "root"
        self.jobs = self.tmp / "jobs"
        self.root.mkdir()
        self.real_compat = (compat.lecture_files, compat._handout)     # the handout-target test uses the real ones
        self.patches = [
            mock.patch.object(flow, "ROOT", self.root), mock.patch.object(flow, "JOBS", self.jobs),
            mock.patch.object(scope, "edges", lambda module, book: {}),
            mock.patch.object(compat, "lecture_files", lambda *a, **k: None),
            mock.patch.object(compat, "_handout", lambda module: ({}, {})),
        ]
        for p in self.patches:
            p.start()
        self.book = [{"id": f"s{j}", "text": f"book line {j}", "kind": "sentence", "page": 1} for j in range(1, 61)]
        self.paras = [{"n": i, "start": 30 * (i - 1), "text": f"talk {i}"} for i in range(1, 21)]
        self.slice = self.book[:]
        self.fake = mock.patch.object(flow, "prepare", self._prepare)
        self.fake.start()

    def tearDown(self):
        for p in self.patches + [self.fake]:
            p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prepare(self, lid, module="year2-cns", cache=None):
        return {"paras": self.paras, "scope": {"book": "bk", "how": "test", "lo": 0, "hi": len(self.slice) - 1},
                "slice": self.slice, "prior": []}

    GOOD = "P1-P5 = B1-B3\nP6-P10 = B4-B6\nP11-P15 = B7-B9\nP16-P20 = B10-B12\n"

    def _answer(self, lid, reader, text):
        d = self.jobs / lid / reader
        d.mkdir(parents=True, exist_ok=True)
        (d / "answer.txt").write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))

    def _lecture_file(self, lid):
        return self.root / "lectures" / lid / "segments.jsonl"

    def _state(self, lid):
        from spine import read_json
        return read_json(self.jobs / lid / "state.json")

    def test_two_agreeing_readers_are_accepted_and_written(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        self._answer("L1", "B", self.GOOD)
        stats = flow.collect(["L1"], say=lambda *a: None)
        self.assertEqual(stats, {"accepted": 1})
        self.assertTrue(self._lecture_file("L1").exists())

    def test_a_moved_slice_makes_the_job_stale_and_drops_old_output(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        self._answer("L1", "B", self.GOOD)
        flow.collect(["L1"], say=lambda *a: None)
        self.assertTrue(self._lecture_file("L1").exists())
        self.slice = self.book[10:]                      # the owner moved the placement; B numbers now mean other lines
        stats = flow.collect(["L1"], say=lambda *a: None)
        self.assertEqual(stats, {"stale": 1})
        self.assertFalse(self._lecture_file("L1").exists())
        self.assertEqual(self._state("L1")["stale_readers"], ["A", "B"])

    def test_remaking_jobs_for_the_new_slice_clears_the_old_answers(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        self.slice = self.book[10:]
        self.assertEqual(flow.make_jobs(["L1"], say=lambda *a: None), 2)
        self.assertFalse((self.jobs / "L1" / "A" / "answer.txt").exists())
        self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"waiting": 1})

    def test_same_task_keeps_its_answer(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        self.assertEqual(flow.make_jobs(["L1"], say=lambda *a: None), 0)
        self.assertTrue((self.jobs / "L1" / "A" / "answer.txt").exists())

    def test_a_job_from_before_fingerprints_is_adopted_when_its_task_matches(self):
        from spine.seg import flow, segment
        from spine import write_json
        task = segment.render(self.paras, self.slice)
        for r in ("A", "B"):
            d = self.jobs / "L1" / r
            d.mkdir(parents=True)
            (d / "task.txt").write_text(task, encoding="utf-8")
            write_json(d / "meta.json", {"lecture": "L1", "lo": 0, "hi": 59, "version": segment.VERSION})
            (d / "answer.txt").write_text(self.GOOD, encoding="utf-8")
        self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"accepted": 1})

    def test_a_job_from_before_fingerprints_with_another_task_is_stale(self):
        from spine.seg import flow, segment
        from spine import write_json
        for r in ("A", "B"):
            d = self.jobs / "L1" / r
            d.mkdir(parents=True)
            (d / "task.txt").write_text("an old task", encoding="utf-8")
            write_json(d / "meta.json", {"lecture": "L1", "version": segment.VERSION})
            (d / "answer.txt").write_text(self.GOOD, encoding="utf-8")
        self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"stale": 1})

    def test_a_disputed_lecture_loses_its_old_accepted_output(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        self._answer("L1", "B", self.GOOD)
        flow.collect(["L1"], say=lambda *a: None)
        self.assertTrue(self._lecture_file("L1").exists())
        self._answer("L1", "B", "P1-P20 = B30-B40\n")     # one range over all: rejected, so not accepted now
        stats = flow.collect(["L1"], say=lambda *a: None)
        self.assertEqual(stats, {"rejected": 1})
        self.assertFalse(self._lecture_file("L1").exists())

    def test_one_broken_lecture_does_not_stop_the_batch(self):
        from unittest import mock
        from spine.seg import flow
        for lid in ("L1", "L2"):
            flow.make_jobs([lid], say=lambda *a: None)
            self._answer(lid, "A", self.GOOD)
            self._answer(lid, "B", self.GOOD)
        real = flow._judge_lecture

        def boom(lid, module, cache):
            if lid == "L1":
                raise KeyError("broken transcript")
            return real(lid, module, cache)
        with mock.patch.object(flow, "_judge_lecture", boom):
            stats = flow.collect(["L1", "L2"], say=lambda *a: None)
        self.assertEqual(stats, {"error": 1, "accepted": 1})
        self.assertIn("broken transcript", self._state("L1")["why"])

    def test_no_source_is_reported_not_crashed(self):
        from unittest import mock
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        self._answer("L1", "B", self.GOOD)
        with mock.patch.object(flow, "prepare", lambda *a, **k: None):
            self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"no source": 1})

    def test_non_utf8_bytes_and_bom_do_not_crash_or_drop_a_line(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", b"\xef\xbb\xbf" + self.GOOD.encode("utf-8") + b"\xff\xfe junk\n")
        self._answer("L1", "B", self.GOOD)
        self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"accepted": 1})

    def test_empty_answer_is_rejected_not_accepted(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", "")
        self._answer("L1", "B", self.GOOD)
        self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"rejected": 1})

    def test_an_accepted_handout_target_lecture_writes_its_shadow_files(self):
        """Handout-target segments point at handout sentence ids, not book ids: the real compat writer and audit
        must take them (the first version raised KeyError 'book' and would have stopped the whole collect)."""
        from unittest import mock
        from spine import graph_dir, read_jsonl, compat
        from spine.seg import flow
        handout = [x for x in read_jsonl(graph_dir("year2-cns") / "sentences.jsonl")
                   if x.get("kind") != "figure" and (x.get("text") or "").strip() and x.get("rows")][:30]
        self.slice = handout
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        self._answer("L1", "B", self.GOOD)
        real_lf, real_h = self.real_compat
        with mock.patch.object(compat, "lecture_files", real_lf), mock.patch.object(compat, "_handout", real_h),                 mock.patch("spine.ROOT", self.root),                 mock.patch.object(flow, "prepare", lambda lid, module="year2-cns", cache=None: {
                    "paras": self.paras, "slice": handout, "prior": [],
                    "scope": {"book": None, "target": "handout", "how": "test", "lo": 0, "hi": 29}}):
            self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"accepted": 1})
            self.assertTrue((self.root / "lectures" / "L1" / "spine" / "links.jsonl").exists())
            out = []
            flow.audit("L1", out=out.append)
        self.assertTrue(any("segments" in line for line in out))

    def test_a_disagreeing_pair_is_disputed_and_writes_nothing(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        self._answer("L1", "B", "P1-P5 = B20-B22\nP6-P10 = B30-B32\nP11-P15 = B40-B42\nP16-P20 = B50-B52\n")
        stats = flow.collect(["L1"], say=lambda *a: None)
        self.assertEqual(stats, {"disputed": 1})
        self.assertFalse(self._lecture_file("L1").exists())
        self.assertTrue(self._state("L1")["runs"])

    def test_three_quarters_agreement_is_disputed_not_accepted(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        # B agrees with A on P1-P15 (75% of paragraphs) and disagrees on P16-P20
        self._answer("L1", "B", "P1-P5 = B1-B3\nP6-P10 = B4-B6\nP11-P15 = B7-B9\nP16-P20 = B40-B42\n")
        self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"disputed": 1})

    def test_the_agreement_line_is_ninety_percent(self):
        a = segs((1, 10, 1, 10))
        b = segs((1, 1, 1, 1), (2, 10, 30, 30))            # agree on 1 of 10 paragraphs
        self.assertLess(segment.agree(a, b, 10), segment.AGREE_SHARE)
        c = segs((1, 9, 1, 1), (10, 10, 1, 1))              # same book line everywhere: agrees
        self.assertGreaterEqual(segment.agree(a, c, 10), segment.AGREE_SHARE)

    def test_same_text_but_other_sentence_ids_is_stale(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        self._answer("L1", "B", self.GOOD)
        self.slice = [dict(x, id="other-" + x["id"]) for x in self.book]     # the same numbered text, new ids
        self.assertEqual(flow.make_jobs(["L1"], say=lambda *a: None), 2)
        self.assertFalse((self.jobs / "L1" / "A" / "answer.txt").exists())

    def test_paragraph_numbers_outside_the_transcript_are_refused(self):
        for text in ("P0-P5 = B1-B3\nP6-P10 = B4-B6", "P10-P1 = B1-B3", "P1-P5 = B1-B3\nP6-P12 = B4-B6"):
            segs_, bad = segment.parse(text)
            fixed, problems, share = segment.judge_segs(segs_, 10, 50, bad)
            self.assertIsNone(fixed, text)
            self.assertTrue(any("outside" in p or "over" in p or "last segment" in p for p in problems), text)

    def test_run_limit_zero_asks_nothing_and_one_asks_one(self):
        from unittest import mock
        from spine.seg import flow
        flow.make_jobs(["L1", "L2"], say=lambda *a: None)
        calls = []

        def fake(d):                              # one Gemini chat per job
            calls.append((d.parent.name, d.name))
            return "answered"
        with mock.patch.object(flow, "ask_gemini", fake):
            flow.run(["L1", "L2"], limit=0, say=lambda *a: None)
            self.assertEqual(calls, [])
            flow.run(["L1", "L2"], limit=1, say=lambda *a: None)
        self.assertEqual(len(calls), 1)

    def test_dry_decides_like_collect_and_writes_nothing(self):
        from spine.seg import flow
        flow.make_jobs(["L1", "L2"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        self._answer("L1", "B", self.GOOD)
        self._answer("L2", "A", "P1-P20 = B30-B40")
        self._answer("L2", "B", "P1-P20 = B30-B40")
        self.assertEqual(flow.dry(["L1", "L2"], say=lambda *a: None), {"accepted": 1, "rejected": 1})
        self.assertFalse(self._lecture_file("L1").exists())
        self.assertFalse((self.jobs / "L1" / "state.json").exists())
        self.assertEqual(flow.collect(["L1", "L2"], say=lambda *a: None), {"accepted": 1, "rejected": 1})

    def test_fingerprint_changes_with_text_or_ids(self):
        from spine.seg import flow
        base = flow.fingerprint("t", self.book[:3])
        self.assertNotEqual(base, flow.fingerprint("t2", self.book[:3]))
        self.assertNotEqual(base, flow.fingerprint("t", self.book[:2]))
        self.assertEqual(base, flow.fingerprint("t", self.book[:3]))

    def test_segments_name_the_readers_that_answered(self):
        # Opus audit 2026-11-18: `by` was hard-coded "fleetA+fleetB", so a browser or Haiku answer was written as fleet
        from spine import read_jsonl, write_json
        from spine.seg import flow
        flow.make_jobs(["L1", "L2"], say=lambda *a: None)
        for lid in ("L1", "L2"):
            self._answer(lid, "A", self.GOOD)
            self._answer(lid, "B", self.GOOD)
        write_json(self.jobs / "L2" / "B" / "reader.json", {"by": "haiku"})
        flow.collect(["L1", "L2"], say=lambda *a: None)
        self.assertEqual({r["by"] for r in read_jsonl(self._lecture_file("L1"))}, {"fleetA+fleetB"})   # unchanged
        self.assertEqual({r["by"] for r in read_jsonl(self._lecture_file("L2"))}, {"fleetA+haikuB"})

    def test_remaking_a_job_forgets_who_answered_it(self):
        from spine import write_json
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self._answer("L1", "A", self.GOOD)
        write_json(self.jobs / "L1" / "A" / "reader.json", {"by": "haiku"})
        self.slice = self.book[10:]
        flow.make_jobs(["L1"], say=lambda *a: None)
        self.assertFalse((self.jobs / "L1" / "A" / "reader.json").exists())


class OpusAuditJudgeFixes(unittest.TestCase):
    """Bugs found in the Opus audit 2026-11-18: answers the judge read silently instead of refusing."""

    ROWS = [(1, 5, 1, 10), (9, 12, 21, 30)]             # P6-P8 missing: a 3-paragraph hole fill() turns into NONE

    def test_a_labelled_segment_line_is_not_prose(self):
        # "Segment 2: P6-P8 = B11-B20 (approx)" did not parse; SEG_LIKE was matched at the line start only, so the
        # line counted as prose and P6-P8 became NONE without a word
        fixed, problems, share = segment.judge_segs(segs(*self.ROWS), 12, 50,
                                                    bad=["Segment 2: P6-P8 = B11-B20 (approx)"])
        self.assertIsNone(fixed)
        self.assertTrue(any("did not parse" in p for p in problems))

    def test_real_prose_is_still_prose(self):
        # the unparsed lines seen in the 91 real answers (cns-018 A, cns-037 A) must stay prose
        bad = ["The segment lines mapping the lecture transcript onto the book:", "*Assumptions and notes:*",
               "- P22 opens the topic of Pain Sensation ([B26](file:///C:/Users/x/task.txt#L30))",
               "- P2\u2013P9 covers adaptation vs. fatigue", "Notes: the doctor is clear."]
        fixed, problems, share = segment.judge_segs(segs((1, 5, 1, 10), (6, 12, 11, 30)), 12, 50, bad=bad)
        self.assertIsNotNone(fixed)

    def test_a_stretch_answered_twice_differently_is_refused(self):
        # a draft then a correction: fill() kept the first answer for P1-P12 and dropped the second silently
        draft = [(1, 12, 1, 10), (13, 24, 11, 20)]
        fix = [(1, 12, 30, 40), (13, 24, 41, 50)]
        fixed, problems, share = segment.judge_segs(segs(*draft, *fix), 24, 60)
        self.assertIsNone(fixed)
        self.assertTrue(any("answered twice" in p for p in problems))

    def test_an_exact_repeat_is_not_a_conflict(self):
        rows = [(1, 9, 1, 10), (10, 18, 11, 20)]          # 18 paragraphs: under the dominant rule's minimum
        fixed, problems, share = segment.judge_segs(segs(*rows, *rows), 18, 60)
        self.assertIsNotNone(fixed)
        self.assertEqual([s["p"] for s in fixed], [[1, 9], [10, 18]])

    def test_a_one_paragraph_boundary_slip_is_still_repaired(self):
        fixed, problems, share = segment.judge_segs(segs((1, 9, 1, 10), (9, 18, 11, 20)), 18, 60)
        self.assertIsNotNone(fixed)
        self.assertEqual([s["p"] for s in fixed], [[1, 9], [10, 18]])

    def test_conflict_counts_only_different_answers(self):
        self.assertEqual(segment.conflict(segs((1, 10, 1, 5), (1, 10, 1, 5))), (0, None))
        self.assertEqual(segment.conflict(segs((1, 10, 1, 5), (6, 12, None, None))), (5, [6, 12]))


class ScopeAndPrepareSafety(unittest.TestCase):
    def test_a_missing_lecture_record_is_empty_not_a_crash(self):
        self.assertEqual(scope.lecture("no-such-lecture-xyz"), {})

    def test_a_covers_id_with_no_record_does_not_stop_the_slice(self):
        from unittest import mock
        lec = {"doctor": "nobody", "covers": ["ghost-1"], "ranges": []}
        with mock.patch.object(scope, "lecture", lambda lid: lec if lid == "L1" else {}):
            self.assertIsNone(scope.pick("L1", "year2-cns", [], {}))

    def test_prepare_refuses_an_empty_slice(self):
        from unittest import mock
        from spine.seg import flow
        with mock.patch.object(flow, "raw_of", lambda lid: "[00:00] talk\n[00:30] more\n"), \
                mock.patch.object(scope, "pick", lambda *a, **k: {"book": "b", "sents": [], "lo": 0, "hi": -1,
                                                                  "how": "x"}):
            self.assertIsNone(flow.prepare("L1", "year2-cns", {}))

    def test_render_numbers_the_slice_from_b1(self):
        sl = [{"id": "a", "text": "first", "kind": "sentence"}, {"id": "b", "text": "Second", "kind": "heading"}]
        paras = [{"n": 1, "start": 0, "text": "x"}, {"n": 2, "start": 65, "text": "y"}]
        task = segment.render(paras, sl)
        self.assertIn("\nB1 first\nB2 ## Second\n", task)
        self.assertIn("P1 [00:00] x\nP2 [01:05] y\n", task)
        self.assertIn("the last ends at P2", task)  # the prompt names the last paragraph


class PropertyFuzz(unittest.TestCase):
    """Seeded random answers: whatever the reader sends, judge never raises, and an accepted answer always meets
    every rule on the form it is written in. The fuzz found the NONE-after-repair hole (now fixed)."""

    def _random_answer(self, rng, n, nb):
        segs, p = [], 1
        while p <= n:
            q = min(n, p + rng.choice([0, 1, 2, 4, 7, 11, 12, 12, 13]))
            r = rng.random()
            if r < 0.15:
                b = None
            elif r < 0.2:
                b = [rng.randint(0, nb + 3), rng.randint(0, nb + 3)]
            else:
                c = rng.randint(1, max(1, nb))
                b = [c, min(nb + 1, c + rng.choice([0, 1, 3, 10, 40, 130]))]
            segs.append({"p": [p, q], "b": b})
            p = q + 1
        for _ in range(rng.choice([0, 0, 1, 2])):
            if segs:
                k = rng.randrange(len(segs))
                if rng.random() < 0.5:
                    segs[k]["p"][0] = max(0, segs[k]["p"][0] - rng.randint(1, 3))
                else:
                    segs[k]["p"] = [segs[k]["p"][1], segs[k]["p"][0]]
        return segs

    def test_accepted_answers_always_meet_the_rules(self):
        import random as _r
        rnd = _r.Random(20261118)
        acc = 0
        for _ in range(2500):
            n = rnd.choice([1, 2, 3, 5, 10, 12, 13, 30, 50, 100, 173, 400])
            nb = rnd.choice([0, 1, 2, 5, 20, 100, 300, 1000])
            segs = self._random_answer(rnd, n, nb)
            fixed, probs, share = segment.judge_segs(segs, n, nb, bad=rnd.choice([[], ["x y"]]))
            if fixed is None:
                continue
            acc += 1
            self.assertEqual(fixed[0]["p"][0], 1)
            self.assertEqual(fixed[-1]["p"][1], n)
            for k, s in enumerate(fixed):
                a, b = s["p"]
                self.assertLessEqual(a, b)
                self.assertLessEqual(b - a + 1, segment.MAX_PARAS)
                if k:
                    self.assertEqual(a, fixed[k - 1]["p"][1] + 1)
                if s["b"]:
                    c, d = s["b"]
                    self.assertTrue(1 <= c <= d <= nb)
                    self.assertLessEqual(d - c + 1, segment.MAX_RANGE)
            mapped = [s["b"] for s in fixed if s["b"]]
            for x, y in zip(mapped, mapped[1:]):
                self.assertGreaterEqual(y[0], x[1])
            none = sum(s["p"][1] - s["p"][0] + 1 for s in fixed if not s["b"]) / n
            self.assertLessEqual(none, segment.MAX_NONE + 1e-9)
            self.assertLessEqual(share, segment.MAX_OFFEND + 1e-9)
            self.assertEqual(segment.shares(fixed, n), [])
        self.assertGreater(acc, 100)                 # the generator must reach the accept path often enough

    def test_formatting_noise_never_changes_the_judgement(self):
        import random as _r
        rnd = _r.Random(7)
        for _ in range(1500):
            n = rnd.choice([5, 12, 20, 40, 97])
            nb = max(3, int(n * rnd.choice([1.5, 2, 3])))
            lines = []
            p = 1
            while p <= n:
                q = min(n, p + rnd.choice([0, 1, 3, 4, 7, 11]))
                c = rnd.randint(1, nb)
                lines.append((p, q, None if rnd.random() < 0.15 else c, min(nb, c + rnd.choice([0, 2, 6]))))
                p = q + 1

            def render(noisy):
                out = []
                for a, b, c, d in lines:
                    body = f"P{a}-P{b} = " + ("NONE" if c is None else f"B{c}-B{d}")
                    if noisy:
                        body = rnd.choice(["", "- ", "* ", "1. ", "**", "`", "2) "]) + body \
                            + rnd.choice(["", ".", ";", "**", "`"])
                        if rnd.random() < 0.3:
                            body = body.replace(" = ", ": ")
                        if rnd.random() < 0.3:
                            body = body.replace("-", "–", 1)
                        if rnd.random() < 0.2:
                            out.append("Here are the segments:")
                    out.append(body)
                text = "\n".join(out)
                return ("﻿" + text.replace("\n", "\r\n")) if noisy and rnd.random() < 0.5 else text

            clean_segs, clean_bad = segment.parse(render(False))
            clean = segment.judge_segs(clean_segs, n, nb, clean_bad)
            noisy_text = render(True)
            segs, bad = segment.parse(noisy_text)
            got = segment.judge_segs(segs, n, nb, bad)
            self.assertEqual(segs, clean_segs, noisy_text[:200])
            self.assertEqual(got[0] is None, clean[0] is None, noisy_text[:200])
            if clean[0] is not None:
                self.assertEqual(got[0], clean[0])


class GeminiReader(unittest.TestCase):
    """The reader (owner 2026-11-18): Gemini web, model 4 Hydrogen; the fleet is retired and Haiku reads no Arabic."""

    GOOD = "P1-P5 = B1-B3\nP6-P10 = B4-B6\n"

    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from spine.seg import flow
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(flow, "JOBS", self.tmp / "jobs")
        self.patch.start()
        for lid in ("L1", "L2"):
            for r in ("A", "B"):
                d = self.tmp / "jobs" / lid / r
                d.mkdir(parents=True)
                (d / "task.txt").write_text("the prompt\nBOOK\nB1 x\n\nTRANSCRIPT\nP1 [0:00] y\n", encoding="utf-8")

    def tearDown(self):
        self.patch.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake(self, text):
        self.seen = []

        def ask(prompt, model=None, attach=(), wait=None):
            self.seen.append({"prompt": prompt, "model": model, "attach": list(attach)})
            return text, {"account": "acct1", "model": "Hydrogen", "secs": 5} if text else {"error": "no account"}
        return ask

    def test_an_answer_is_written_with_its_reader(self):
        from spine import read_json
        from spine.seg import flow
        d = self.tmp / "jobs" / "L1" / "A"
        self.assertEqual(flow.ask_gemini(d, ask=self.fake(self.GOOD)), "answered")
        self.assertEqual((d / "answer.txt").read_text(encoding="utf-8"), self.GOOD)
        self.assertEqual(flow.answered_by(d), "gemini")
        self.assertEqual(read_json(d / "browser.json")["account"], "acct1")
        call = self.seen[0]
        self.assertEqual(call["model"], "hydrogen")
        self.assertEqual(call["attach"], [str(d / "task.txt")])
        self.assertTrue(call["prompt"].startswith("the prompt"))
        self.assertNotIn("P1 [0:00]", call["prompt"])             # the blocks come in the attached file

    def test_a_reply_without_segments_is_not_an_answer(self):
        from spine.seg import flow
        d = self.tmp / "jobs" / "L1" / "A"
        for text in ("I cannot read this.", None):
            self.assertEqual(flow.ask_gemini(d, ask=self.fake(text)), "failed")
        self.assertFalse((d / "answer.txt").exists())
        self.assertTrue((d / "reply_failed.txt").exists())
        self.assertEqual(len(flow.todo(["L1"])), 2)

    def test_run_asks_each_unanswered_job_once(self):
        from unittest import mock
        from spine.seg import flow
        asked = []
        with mock.patch.object(flow, "ask_gemini", lambda d: asked.append(d) or "answered"):
            self.assertEqual(flow.run(["L1"], say=lambda *a: None), {"answered": 2})
        self.assertEqual(len(asked), 2)


class PromptV3(unittest.TestCase):
    """Prompt v3 (2026-11-18) answers what made readers fail in the Opus audit."""

    def test_the_rules_are_in_the_prompt(self):
        self.assertEqual(segment.VERSION, 3)
        for words in ("Never write a range you already wrote", "Still on the same line", "Tables and figures",
                      "Going back", "no second version"):
            self.assertIn(words, segment.PROMPT)

    def test_the_prompt_examples_pass_the_judge(self):
        """The 'Right' and 'same line' examples of the prompt are a clean answer to the judge (going forward)."""
        text = "P1-P10 = B37-B43\nP11-P20 = B43-B49\nP21-P30 = B51\nP31-P40 = B51-B53"
        fixed, problems, share = segment.judge_segs(*segment.parse(text)[:1], 40, 60)
        self.assertIsNotNone(fixed, problems)
        self.assertEqual(share, 0)


if __name__ == "__main__":
    unittest.main()

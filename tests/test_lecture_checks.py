import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import checks  # noqa: E402

RAW = "[00:00] today we talk about the pain control system\n[00:40] the raphe magnus nucleus sends fibers\n[01:30] down to the dorsal horn of the spinal cord"
LINES = [{"id": f"m:h:p12:l{n}", "page": 12} for n in range(1, 4)] + [{"id": "m:h:p30:l1", "page": 30}]


class TestTranscript(unittest.TestCase):
    def test_good_transcript(self):
        self.assertEqual(checks.check_transcript(RAW, 120), [])

    def test_time_goes_back_or_end_missing(self):
        self.assertIn("goes back", checks.check_transcript("[01:00] a\n[00:30] b", 70)[0])
        self.assertIn("the end is missing", checks.check_transcript(RAW, 600)[0])
        self.assertIn("after the end", checks.check_transcript(RAW, 30)[0])
        self.assertIn("no [mm:ss]", checks.check_transcript("just words", 60)[0])

    def test_density_band(self):
        self.assertIn("characters per minute", checks.check_transcript(RAW, 120, chars_per_min=(400, 2000))[0])

    def test_hour_stamps(self):
        self.assertEqual(checks.stamp_seconds("[1:02:03] x"), 3723)
        self.assertEqual(checks.stamp_seconds("[75:10] x"), 4510)


class TestTiming(unittest.TestCase):
    # worker stamps are wrong on purpose: the chunk offsets must replace them
    HEARD = "[00:00] today we talk about the pain control system\n[09:00] the raphe magnus nucleus sends fibers\n" \
            "[20:00] down to the dorsal horn of the spinal cord"
    ROWS = [{"chunk": 0, "paragraph": 1, "first_words": "today we talk about"},
            {"chunk": 1, "paragraph": 2, "first_words": "the raphe magnus nucleus"}]

    def test_times_come_from_the_chunks(self):
        errors, timed = checks.check_timed_transcript(self.HEARD, self.ROWS, 100, chunks=2, chunk_s=60)
        self.assertEqual(errors, [])
        # 3rd paragraph: word 14 lies between (word 8, 60 s) and (word 23, 100 s) -> 76 s
        self.assertEqual([s for s, _ in checks.paragraphs(timed)], [0, 60, 76])
        self.assertEqual([t for _, t in checks.paragraphs(timed)], [t for _, t in checks.paragraphs(self.HEARD)])

    def test_silent_chunk_and_words_found_across_a_paragraph_end(self):
        rows = [self.ROWS[0], {"chunk": 1, "silent": True},
                {"chunk": 2, "paragraph": 2, "first_words": "sends fibers down to"}]
        errors, timed = checks.check_timed_transcript(self.HEARD, rows, 150, chunks=3, chunk_s=60)
        self.assertEqual(errors, [])
        self.assertEqual(checks.stamp_seconds(timed.splitlines()[1]), 80)  # word 8 between (0, 0 s) and (12, 120 s)

    def test_bad_rows_fail_without_showing_words(self):
        def err(rows, chunks=2):
            return checks.check_timed_transcript(self.HEARD, rows, 100, chunks=chunks, chunk_s=60)[0]
        self.assertIn("one row per chunk", err(self.ROWS[:1])[0])
        self.assertIn("paragraph must be 1 to 3", err([self.ROWS[0], dict(self.ROWS[1], paragraph=9)])[0])
        self.assertIn("at least 4 words", err([self.ROWS[0], dict(self.ROWS[1], first_words="the raphe")])[0])
        wrong = err([self.ROWS[0], dict(self.ROWS[1], paragraph=3)])[0]
        self.assertIn("not in paragraph 3", wrong)
        self.assertNotIn("raphe", wrong)
        self.assertIn("follow each other", err([dict(self.ROWS[1], chunk=0), dict(self.ROWS[0], chunk=1)])[0])
        self.assertIn("unknown fields", err([self.ROWS[0], dict(self.ROWS[1], at=5)])[0])
        self.assertIn("every chunk is silent", err([{"chunk": 0, "silent": True}, {"chunk": 1, "silent": True}])[0])

    def test_retimed_text_still_meets_the_transcript_check(self):
        errors, _ = checks.check_timed_transcript(self.HEARD, self.ROWS, 600, chunks=2, chunk_s=60)
        self.assertIn("the end is missing", errors[0])


class TestClean(unittest.TestCase):
    CLEAN = ("[00:00] Today we talk about the pain control system.\n\n"
             "[00:40] The raphe magnus nucleus sends fibers down to the dorsal horn of the spinal cord.")

    def test_layout_and_punctuation_only_pass(self):
        self.assertEqual(checks.check_clean(RAW, self.CLEAN, []), [])

    def test_changed_dropped_or_added_word_fails_without_showing_words(self):
        changed = self.CLEAN.replace("fibers", "axons")
        errors = checks.check_clean(RAW, changed, [])
        self.assertIn("word 14", errors[0])
        self.assertIn("[00:40]", errors[0])
        self.assertNotIn("axons", errors[0])
        self.assertIn("words", checks.check_clean(RAW, self.CLEAN.replace(" spinal", ""), [])[0])
        self.assertIn("has 24 words", checks.check_clean(RAW, self.CLEAN + " extra", [])[0])

    def test_sure_fix_replaces_unsure_fix_waits(self):
        raw = RAW.replace("raphe", "rafi")
        sure = {"at": "00:40", "heard": "rafi", "meant": "raphe", "confidence": 0.95, "reason": "nucleus name"}
        self.assertEqual(checks.check_clean(raw, self.CLEAN, [sure]), [])
        unsure = dict(sure, confidence=0.6)
        self.assertTrue(checks.check_clean(raw, self.CLEAN, [unsure]))
        self.assertEqual(checks.check_clean(raw, self.CLEAN.replace("raphe", "rafi"), [unsure]), [])

    def test_fix_shape(self):
        bad = {"at": "00:40", "heard": "x", "meant": "x", "confidence": 0.95, "reason": "r"}
        self.assertIn("different words", checks.check_clean(RAW, self.CLEAN, [bad])[0])
        self.assertIn("not in the raw", checks.check_clean(RAW, self.CLEAN, [dict(bad, heard="zzz", meant="y")])[0])


class TestLinks(unittest.TestCase):
    PARTS = [{"part": 1, "sub": 0, "title": "Analgesia", "start": 0, "end": 80, "line_ids": ["m:h:p12:l1"]},
             {"part": 1, "sub": 1, "title": "Raphe", "start": 40, "end": 80, "line_ids": ["m:h:p12:l2"]},
             {"part": 2, "sub": 0, "title": "Dorsal horn", "start": 80, "end": 120, "line_ids": []}]

    def test_good_parts_and_report(self):
        self.assertEqual(checks.check_links(self.PARTS, 120, LINES, (10, 14)), [])
        self.assertEqual(checks.link_report(self.PARTS, 120, LINES, (10, 14)), {"lines_covered": 0.667, "recording_linked": 0.667})

    def test_bad_parts(self):
        overlap = [dict(self.PARTS[0]), dict(self.PARTS[2], start=70)]
        self.assertIn("overlap", checks.check_links(overlap, 120, LINES)[0])
        outside = [dict(self.PARTS[0]), dict(self.PARTS[1], end=100)]
        self.assertIn("inside its times", checks.check_links(outside, 120, LINES)[0])
        self.assertIn("not a handout line", checks.check_links([dict(self.PARTS[0], line_ids=["x"])], 120, LINES)[0])
        self.assertIn("outside the lecture", checks.check_links([dict(self.PARTS[0], line_ids=["m:h:p30:l1"])], 120, LINES, (10, 14))[0])
        self.assertIn("start < end", checks.check_links([dict(self.PARTS[0], end=500)], 120, LINES)[0])


if __name__ == "__main__":
    unittest.main()

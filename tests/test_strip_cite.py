import unittest

import gemini_run


class StripCite(unittest.TestCase):
    def test_tags_removed_inside_a_line(self):
        self.assertEqual(gemini_run.strip_cite("dorsal root [cite: 1] fibers [cite: 1, 2].\nnext"),
                         "dorsal root fibers.\nnext")

    def test_piece_text_has_no_tags(self):
        text = gemini_run.piece_text("first part [cite: 1]\n\nsecond part [cite: 2]", 60)
        self.assertNotIn("cite", text)
        self.assertIn("first part", text)
        self.assertIn("second part", text)


if __name__ == "__main__":
    unittest.main()


class Loop(unittest.TestCase):
    def test_a_repeated_passage_fails_the_piece_check(self):
        from spine.records import transcribe
        part = " ".join(f"word{i}" for i in range(50))
        filler = " ".join(f"other{i}" for i in range(80))
        self.assertGreaterEqual(transcribe.looped(f"[00:00] {part} {filler} {part}"), 40)
        self.assertEqual(transcribe.looped(f"[00:00] {part} {filler}"), 0)

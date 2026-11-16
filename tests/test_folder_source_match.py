"""A folder lesson finds its lecture by recording, not title (titles follow mother_lists.json since 2026-11-14)."""
import unittest

import doctors_folder as d


class SourceKeys(unittest.TestCase):
    def test_youtube_forms_match(self):
        a = d.source_keys("m", [{"url": "https://youtube.com/watch?v=GABrSUDznYE"}])
        b = d.source_keys("m", [{"youtube": "https://www.youtube.com/watch?v=GABrSUDznYE", "transcript": "youtube"}])
        c = d.source_keys("m", [{"url": "https://youtu.be/GABrSUDznYE?si=x"}])
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_file_case_and_slashes(self):
        a = d.source_keys("m", [{"file": r"C:\Docs\Chapter 1\3- Spinal cord 3.mp3"}])
        b = d.source_keys("m", [{"file": "c:/docs/chapter 1/3- spinal cord 3.mp3"}])
        self.assertEqual(a, b)

    def test_module_kept_apart(self):
        self.assertNotEqual(d.source_keys("a", [{"url": "https://youtu.be/GABrSUDznYE"}]),
                            d.source_keys("b", [{"url": "https://youtu.be/GABrSUDznYE"}]))


if __name__ == "__main__":
    unittest.main()

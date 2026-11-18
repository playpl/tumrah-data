"""Phase 1 job folders answered on Gemini web (fleet retired 2026-11-18)."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from spine import read_json
from spine.align import engine


class AskGemini(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "prompt.md").write_text("the windows", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_an_answer_with_lines_is_a_success_result(self):
        seen = []

        def ask(prompt, model=None, wait=None):
            seen.append((prompt, model))
            return "W1 B1 = H3 S\nW1 B2 = 0", {"account": "acct2"}
        self.assertEqual(engine.ask_gemini(self.d, ask), "answered")
        r = read_json(self.d / "result.json")
        self.assertEqual((r["status"], r["by"], r["response"]), ("SUCCESS", "gemini", "W1 B1 = H3 S\nW1 B2 = 0"))
        self.assertEqual(seen, [("the windows", "hydrogen")])

    def test_prose_fails_and_a_cap_writes_nothing(self):
        self.assertEqual(engine.ask_gemini(self.d, lambda p, model=None, wait=None: ("I cannot", {})), "failed")
        self.assertFalse((self.d / "result.json").exists())
        capped = lambda p, model=None, wait=None: (None, {"error": "capped", "until": 99.0})
        self.assertEqual(engine.ask_gemini(self.d, capped), "capped")
        self.assertEqual(engine.CAPPED["until"], 99.0)
        self.assertFalse((self.d / "result.json").exists())

    def test_the_fleet_runner_refuses_while_the_fleet_is_down(self):
        with mock.patch("spine.config", lambda: {"fleet": {"down": True}}):
            with self.assertRaises(SystemExit):
                engine.run_jobs("year2-cns")


if __name__ == "__main__":
    unittest.main()

"""Owner 2026-11-18: the Antigravity fleet is retired. `mother run` reads changed lists on Gemini web, never the
fleet; mother_check reports a list link to a post the channel does not have as a note, not a difference."""
import unittest
from unittest import mock

import mother_check
from spine.tg import cli


class MotherReadersAreGemini(unittest.TestCase):
    def test_a_changed_list_is_read_on_gemini_web_never_the_fleet(self):
        import shutil
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp())
        seen = []

        def ask(prompt, model=None, wait=None):
            seen.append(model)
            return "1 = lecture", {"account": "acct1"}
        try:
            with mock.patch.object(cli, "job_dir", lambda lst, r: tmp / r),                  mock.patch.object(cli.mother, "render", return_value="the list"),                  mock.patch.object(cli.mother, "ref", return_value=1631):
                got = cli.read_one((0, {"ref": 1631}, "A"), ask=ask)
            self.assertEqual(got, (1631, "A", "1 = lecture", ""))
            self.assertEqual(seen, ["hydrogen"])
            self.assertEqual(cli.read_json(tmp / "A" / "result.json")["by"], "gemini")
            self.assertFalse(hasattr(cli, "FLEET"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class MotherCheckDeadLink(unittest.TestCase):
    def test_a_deleted_post_is_a_note_not_a_difference(self):
        lst = {"sections": {"lectures": [{"title": "A", "parts": [{"label": "A", "post": 10}]}],
                            "revisions": [{"title": "A", "parts": [{"label": "A", "post": 11}]}]},
               "posts": {"10": {"kind": "audio"}}}
        doc = {"doctor": "d", "chapters": [{"title": "Lectures", "items": [{"id": "c1", "name": "A", "post": 10}]}]}  # no chapters: one (11-21)
        mother_check.DEAD.clear()
        self.assertEqual(mother_check.check_doctor(doc, lst), [])
        self.assertEqual(len(mother_check.DEAD), 1)
        self.assertIn("post 11", mother_check.DEAD[0])


if __name__ == "__main__":
    unittest.main()

"""Owner 2026-11-18: the Antigravity fleet is retired. `mother run` must not start fleet readers when config.json says
fleet.down; mother_check reports a list link to a post the channel does not have as a note, not a difference."""
import argparse
import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

import mother_check
from spine.tg import cli


class MotherRunFleetDown(unittest.TestCase):
    def test_changed_list_is_not_read_when_the_fleet_is_down(self):
        lst = {"ref": 1631}
        with mock.patch.object(cli, "wanted", return_value=[1631]), \
             mock.patch.object(cli.mother, "load", return_value=lst), \
             mock.patch.object(cli.mother, "links", return_value=[{"post": 1}]), \
             mock.patch.object(cli.mother, "cache_key", return_value="k"), \
             mock.patch.object(cli.mother, "cached", return_value=None), \
             mock.patch.object(cli.mother, "ref", return_value=1631), \
             mock.patch.object(cli, "fleet_down", return_value=True), \
             mock.patch.object(cli, "read_one", side_effect=AssertionError("fleet reader started")):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli._run(argparse.Namespace(lists=[], year=2, again=False))
        self.assertEqual(code, 0)
        self.assertIn("NOT read (fleet retired", buf.getvalue())


class MotherCheckDeadLink(unittest.TestCase):
    def test_a_deleted_post_is_a_note_not_a_difference(self):
        lst = {"sections": {"lectures": [{"title": "A", "parts": [{"label": "A", "post": 10}]}],
                            "revisions": [{"title": "A", "parts": [{"label": "A", "post": 11}]}]},
               "posts": {"10": {"kind": "audio"}}}
        doc = {"doctor": "d", "chapters": [{"title": "A", "items": [{"id": "c1", "name": "A", "post": 10}]}]}
        mother_check.DEAD.clear()
        self.assertEqual(mother_check.check_doctor(doc, lst), [])
        self.assertEqual(len(mother_check.DEAD), 1)
        self.assertIn("post 11", mother_check.DEAD[0])


if __name__ == "__main__":
    unittest.main()

"""A list's "Mini Lectures" section is its own section, and a mini lecture covers the lecture it shortens (owner, 2026-11-13)."""
import unittest
from unittest import mock

import auto_doctors
import tg_lists


class FakeMsg:
    id = 1
    date = None
    edit_date = None
    media = None

    def __init__(self, text):
        self.message = text

    def get_entities_text(self):
        return []


class Parse(unittest.TestCase):
    def test_mini_header_is_not_lectures(self):
        text = "DR\n\nPDFs\n\n- A\n\nLectures\n\n- Neuron 1\n\nMini Lectures\n\n- Perikaryon\n\nRevisions\n"
        d = tg_lists.parse(FakeMsg(text))
        self.assertIn("minis", d["sections"])
        self.assertEqual(d["sections"]["lectures"], [])


class Parent(unittest.TestCase):
    LECS = [{"id": "a", "title": "Ganglia & Nerve Trunk", "doctor": "d", "kind": "lecture", "ranges": [{"pages": [23, 27]}]},
            {"id": "b", "title": "Neuron 1", "doctor": "d", "kind": "lecture", "ranges": [{"pages": [11, 13]}]}]

    def test_title_words(self):
        with mock.patch.object(auto_doctors.lectures, "all_lectures", return_value=self.LECS):
            self.assertEqual(auto_doctors.mini_parent("m", "d", "histology", "Ganglia")["id"], "a")

    def test_no_match_is_none(self):
        with mock.patch.object(auto_doctors.lectures, "all_lectures", return_value=self.LECS):
            self.assertIsNone(auto_doctors.mini_parent("nomodule", "d", "histology", "Zebra"))

    def test_title(self):
        self.assertEqual(auto_doctors.mini_title("Ganglia"), "Ganglia (mini lecture)")
        self.assertEqual(auto_doctors.mini_title("Mini lecture 1 (Neuron)"), "Mini lecture 1 (Neuron)")


if __name__ == "__main__":
    unittest.main()

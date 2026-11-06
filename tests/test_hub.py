import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import hub  # noqa: E402

BULLET = "*"  # the base-14 font in the fixture cannot draw U+2022


def make_pdf(path):
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    p.insert_text((72, 80), "Pain Control System", fontsize=16)
    p.insert_text((90, 120), BULLET, fontsize=11)            # bullet glyph on its own, same row as its text
    p.insert_text((108, 120), "The analgesia system has three parts:", fontsize=11)
    p.insert_text((108, 140), "periaqueductal gray and the raphe", fontsize=11)
    p.insert_text((108, 160), "magnus nucleus in the medulla.", fontsize=11)
    p.insert_text((72, 200), "Opioid", fontsize=11)        # a table row: two cells, one line
    p.insert_text((300, 200), "Enkephalin", fontsize=11)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 40), 0)
    pix.clear_with(200)
    p.insert_image(fitz.Rect(150, 260, 450, 460), pixmap=pix)
    p.insert_text((200, 480), "Descending pain pathway", fontsize=10)
    p.insert_text((300, 770), "154", fontsize=10)           # printed page number
    p2 = doc.new_page(width=612, height=792)
    p2.insert_text((72, 80), "Touch", fontsize=16)
    p2.insert_text((300, 770), "155", fontsize=10)
    doc.new_page(width=612, height=792)                       # empty page
    doc.save(path)


class TestHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.pdf = cls.tmp / "handout.pdf"
        make_pdf(cls.pdf)
        cls.lines = hub.split_handout(cls.pdf, "year2-cns")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def page(self, n):
        return [ln for ln in self.lines if ln.page == n]

    def test_word_key(self):
        self.assertEqual(hub.word_key("A-1, b!"), "a1b")

    def test_line_id_format(self):
        self.assertEqual(hub.line_id("year2-cns", "3fa9c1d2", 12, 7), "year2-cns:3fa9c1d2:p12:l7")
        self.assertEqual(hub.line_id("year2-cns", "3fa9c1d2", 12, 1, figure=True), "year2-cns:3fa9c1d2:p12:f1")

    def test_ids_stable_across_runs(self):
        again = hub.split_handout(self.pdf, "year2-cns")
        self.assertEqual([(ln.id, ln.text) for ln in again], [(ln.id, ln.text) for ln in self.lines])
        self.assertEqual(len({ln.id for ln in self.lines}), len(self.lines))

    def test_rows_reading_order_and_printed_page(self):
        texts = [ln.text for ln in self.page(1) if ln.figure is None]
        self.assertEqual(texts[0], "Pain Control System")
        self.assertIn("The analgesia system has three parts:", texts[1])
        self.assertTrue(texts[1].startswith(BULLET))
        self.assertIn("Opioid Enkephalin", texts)
        self.assertNotIn("154", texts)
        self.assertEqual({ln.printed for ln in self.page(1)}, {154})

    def test_figure_line_with_nearby_text(self):
        figs = [ln for ln in self.page(1) if ln.figure is not None]
        self.assertEqual(len(figs), 1)
        self.assertTrue(figs[0].id.endswith(":p1:f1"))
        self.assertEqual(figs[0].figure, "Descending pain pathway")

    def test_empty_page_is_one_page_figure(self):
        empty = self.page(3)
        self.assertEqual(len(empty), 1)
        self.assertEqual(empty[0].figure, "page")

    def test_resolve_span_across_line_break(self):
        ids = hub.resolve_span(self.lines, 1, "the raphe magnus nucleus")
        self.assertEqual(len(ids), 2)
        self.assertTrue(ids[0].endswith(":p1:l3") and ids[1].endswith(":p1:l4"))

    def test_resolve_span_missing(self):
        self.assertEqual(hub.resolve_span(self.lines, 1, "not in the handout"), [])
        self.assertEqual(hub.resolve_span(self.lines, 2, "the raphe magnus"), [])
        self.assertEqual(hub.resolve_span(self.lines, 1, "  "), [])

    def test_resolve_figure_by_caption(self):
        ids = hub.resolve_span(self.lines, 1, "FIGURE", figure="Descending pain pathway diagram")
        self.assertEqual(len(ids), 1)
        self.assertTrue(ids[0].endswith(":p1:f1"))
        self.assertEqual(hub.resolve_span(self.lines, 2, "FIGURE", figure="anything"), [])


if __name__ == "__main__":
    unittest.main()

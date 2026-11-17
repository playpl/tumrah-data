import unittest

from spine import ids, rows as R
from spine.graph import handout

M, H = "m", "abcd1234"


def row(page, n, text, x0=72, x1=None, y=None, figure=None):
    """A text row on a page whose full lines end at x=540. 6 pt per letter unless x1 is given."""
    y = 100 + n * 18 if y is None else y
    x1 = x0 + 6 * len(text) if x1 is None else x1
    return {"id": f"{M}:{H}:p{page}:{'f' if figure is not None else 'l'}{n}", "module": M, "hash": H, "page": page,
            "printed": None, "n": n, "text": text, "figure": figure, "bbox": [x0, y, x1, y + 15]}


def page_filler(page, start=40):
    """Eight full-width rows, far down the page, so the page's right margin is 540."""
    return [row(page, start + i, "Filler line that reaches the right margin of the page.", x1=540, y=600 + i * 18)
            for i in range(8)]


def texts(rows, **kw):
    return [(u["kind"], u["marker"], u["text"]) for u in R.build(rows, **kw) if "Filler" not in u["text"]]


class Joins(unittest.TestCase):
    def test_wrap_joined(self):
        rows = [row(1, 1, "• Its cells form the second order neurons in the pain and", x1=540),
                row(1, 2, "temperature pathway from the body.", x0=90),
                row(1, 3, "• It is present in all segments.")] + page_filler(1)
        self.assertEqual(texts(rows), [
            ("fact", "•", "Its cells form the second order neurons in the pain and temperature pathway from the body."),
            ("fact", "•", "It is present in all segments.")])

    def test_short_line_not_joined(self):
        rows = [row(1, 1, "Pyramidal cells"), row(1, 2, "Stellate cells")] + page_filler(1)
        self.assertEqual([t for _, _, t in texts(rows)], ["Pyramidal cells", "Stellate cells"])

    def test_narrow_column_joined_by_small_letter(self):
        rows = [row(1, 1, "It pierces the dura, passes through the sacral canal", x1=380),
                row(1, 2, "and hiatus.", x1=150)] + page_filler(1)
        self.assertEqual([t for _, _, t in texts(rows)],
                         ["It pierces the dura, passes through the sacral canal and hiatus."])

    def test_lead_in_never_joined(self):
        rows = [row(1, 1, "The motor nuclei of the anterior horn of the spinal cord in all segments are:", x1=540),
                row(1, 2, "medial group")] + page_filler(1)
        self.assertEqual(len(texts(rows)), 2)

    def test_marker_and_heading_start_units(self):
        rows = [row(1, 1, "Some text that reaches the right margin of this page and", x1=540),
                row(1, 2, "o Severe distension of hollow organs."), row(1, 3, "NEURON")] + page_filler(1)
        got = texts(rows, headings={rows[2]["id"]})
        self.assertEqual([(k, m) for k, m, _ in got], [("fact", ""), ("fact", "o"), ("heading", "")])

    def test_hyphen_rejoined_only_when_the_word_exists(self):
        rows = [row(1, 1, "The impulse reaches the area of trans-", x1=540), row(1, 2, "mission and the second-", x1=540),
                row(1, 3, "order neuron; transmission is fast.")] + page_filler(1)
        self.assertEqual(texts(rows)[0][2],
                         "The impulse reaches the area of transmission and the second- order neuron; transmission is fast.")

    def test_cross_page(self):
        rows = page_filler(1, start=1) + [row(1, 20, "It ends at the lower border of the first lumbar vertebra and",
                                              x1=540, y=800)]
        rows += [row(2, 1, "continues as the filum terminale.")] + page_filler(2)
        self.assertEqual(texts(rows)[0][2].split()[-4:], ["as", "the", "filum", "terminale."])


class Splits(unittest.TestCase):
    def test_inner_split(self):
        cuts = R.cut_sentences("Their sizes range from 10-50 um. Betz cells are larger cells found in the motor cortex.")
        self.assertEqual(len(cuts), 2)

    def test_no_split_on_abbreviation_or_short_side(self):
        self.assertEqual(len(R.cut_sentences("It is seen e.g. In the motor cortex of man.")), 1)
        self.assertEqual(len(R.cut_sentences("See Fig. A for the pathway of pain.")), 1)
        self.assertEqual(len(R.cut_sentences("It is large. Very large.")), 1)
        self.assertEqual(len(R.cut_sentences("It has two parts (i.e. Lt. Temporal and Rt. Nasal retina) in man.")), 1)

    def test_split_rows_and_ids(self):
        lines = [row(1, 1, "• Their sizes range from 10-50 um. Betz cells are larger cells", x1=540),
                 row(1, 2, "found in the motor cortex.", x0=90)] + page_filler(1)
        sents = handout.sentences(lines, [], [{"lecture_id": "m:L01", "subject": "Anatomy", "pdf_pages": [1, 1]}])
        a, b = sents[0], sents[1]
        self.assertEqual((a["id"], b["id"]), (f"{M}:{H}:p1:s1a", f"{M}:{H}:p1:s1b"))
        self.assertEqual(a["rows"], [lines[0]["id"]])
        self.assertEqual(b["rows"], [lines[0]["id"], lines[1]["id"]])
        self.assertEqual(b["text"], "Betz cells are larger cells found in the motor cortex.")
        self.assertEqual(a["lesson"], "m:L01")


class Context(unittest.TestCase):
    def test_list_item_keeps_ctx(self):
        rows = [row(1, 1, "NUCLEI OF THE ANTERIOR HORN"), row(1, 2, "• The motor nuclei are:", x0=90),
                row(1, 3, "1. Medial group: present in all segments.", x0=108),
                row(1, 4, "2. Lateral group", x0=108), row(1, 5, "Function:"),
                row(1, 6, "It moves the limb.")] + page_filler(1)
        got = {u["text"]: u["ctx"] for u in R.build(rows, headings={rows[0]["id"]})}
        self.assertEqual(got["Medial group: present in all segments."],
                         ["NUCLEI OF THE ANTERIOR HORN", "The motor nuclei are:"])
        self.assertEqual(got["Lateral group"], ["NUCLEI OF THE ANTERIOR HORN", "The motor nuclei are:"])
        self.assertEqual(got["It moves the limb."], ["NUCLEI OF THE ANTERIOR HORN", "Function:"])

    def test_table_row_is_one_unit(self):
        rows = [row(1, 1, "Theory Statement", y=100), row(1, 2, "Passive theory The system becomes fatigued", y=120),
                row(1, 3, "(old) and stops working", y=138)] + page_filler(1)
        tables = {1: [{"bbox": [60, 95, 560, 160], "rows": [
            {"bbox": [60, 95, 560, 117], "cells": ["Theory", "Statement"]},
            {"bbox": [60, 117, 560, 160], "cells": ["Passive theory\n(old)", "The system becomes fatigued\nand stops working"]}]}]}
        got = [u for u in R.build(rows, tables=tables) if u["kind"] == "table_row"]
        self.assertEqual(got[1]["text"], "Passive theory (old) | The system becomes fatigued and stops working")
        self.assertEqual(len(got[1]["rows"]), 2)
        self.assertEqual(got[1]["ctx"], ["Theory | Statement"])


class Invariants(unittest.TestCase):
    def setUp(self):
        self.lines = [row(1, 1, "", figure="A figure"), row(1, 1, "SPINAL CORD"),
                      row(1, 2, "• It ends at L1. It begins at the foramen magnum of the skull", x1=540),
                      row(1, 3, "in the adult.", x0=90), row(1, 4, "a. Cervical"), row(1, 5, "b. Thoracic")] + page_filler(1)
        self.lessons = [{"lecture_id": "m:L01", "subject": "Anatomy", "pdf_pages": [1, 1]}]

    def test_every_row_covered_and_order_kept(self):
        sents = handout.sentences(self.lines, [], self.lessons)
        covered = {r for s in sents for r in s["rows"]}
        self.assertEqual(covered, {ln["id"] for ln in self.lines})
        self.assertEqual([s["i"] for s in sents], list(range(len(sents))))
        for s in sents:
            self.assertEqual(ids.first_row(s["id"]), s["rows"][0])

    def test_ids_stable_and_unique(self):
        a = handout.sentences(self.lines, [], self.lessons)
        b = handout.sentences(self.lines, [], self.lessons)
        self.assertEqual(a, b)
        self.assertEqual(len({s["id"] for s in a}), len(a))
        self.assertEqual(a[0]["id"], f"{M}:{H}:p1:f1")
        self.assertEqual(a[0]["kind"], "figure")


if __name__ == "__main__":
    unittest.main()

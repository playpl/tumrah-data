import tempfile
import unittest
from pathlib import Path

from spine import ids, store, text


class RoundTrip(unittest.TestCase):
    def test_handout_sentence(self):
        sid = ids.sent_id("year2-cns", "d30dcde2", 60, 5, "a")
        self.assertEqual(sid, "year2-cns:d30dcde2:p60:s5a")
        p = ids.parse(sid)
        self.assertEqual((p["space"], p["module"], p["page"], p["kind"], p["n"], p["sub"]),
                         ("handout", "year2-cns", 60, "s", 5, "a"))
        self.assertEqual(ids.first_row(sid), "year2-cns:d30dcde2:p60:l5")

    def test_figure_and_row(self):
        self.assertEqual(ids.parse("year2-cns:d30dcde2:p60:f1")["kind"], "f")
        self.assertEqual(ids.first_row("year2-cns:d30dcde2:p60:f1"), "year2-cns:d30dcde2:p60:f1")
        self.assertFalse(ids.is_sentence("year2-cns:d30dcde2:p60:l5"))
        self.assertTrue(ids.is_sentence("year2-cns:d30dcde2:p60:s5"))

    def test_book_and_tumrah(self):
        b = ids.book_sent_id("mossafer-anat-full", "6f2a91c0", 12, 3)
        self.assertEqual(ids.parse(b)["book"], "mossafer-anat-full")
        t1 = ids.tumrah_sent_id("year2-cns/anatomy/c1/spinal-cord", "The spinal cord ends at L1.")
        t2 = ids.tumrah_sent_id("year2-cns/anatomy/c1/spinal-cord", "the  spinal cord ends at L1")
        self.assertEqual(t1, t2)
        self.assertEqual(ids.parse(t1)["space"], "tumrah")

    def test_bad_ids_raise(self):
        for bad in ("x", "year2-cns:d30dcde2:p60", "year2-cns:d30dcde2:p60:l5a", "bk:b:h:p1:q2"):
            with self.assertRaises(ValueError):
                ids.parse(bad)

    def test_order(self):
        a, b, c = (ids.sent_id("m", "h", 2, 10), ids.sent_id("m", "h", 10, 1), ids.sent_id("m", "h", 2, 9, "b"))
        self.assertEqual(sorted([a, b, c], key=ids.order_key), [c, a, b])


class Text(unittest.TestCase):
    def test_tokens_and_arabic(self):
        self.assertEqual(text.tokens("The Thalamus (VPL) is 2nd."), ["the", "thalamus", "vpl", "is", "2nd"])
        self.assertEqual(text.ar_norm("الْمُخَيخ"), "المخيخ")
        self.assertEqual(text.tokens("إلى الأعصَاب"), text.tokens("الي الاعصاب"))
        self.assertEqual(text.content("It is in the thalamus"), ["thalamus"])

    def test_overlap(self):
        self.assertEqual(text.overlap("spinal cord ends", "The spinal cord ends at L1"), 1.0)
        self.assertEqual(text.overlap("", "x"), 0.0)

    def test_ends_sentence(self):
        self.assertTrue(text.ends_sentence("It ends at L1."))
        self.assertTrue(text.ends_sentence("The nuclei are:"))
        self.assertFalse(text.ends_sentence("as seen in Fig."))
        self.assertFalse(text.ends_sentence("e.g."))
        self.assertFalse(text.ends_sentence("the cord and"))

    def test_restore_terms(self):
        lex = text.Lexicon(["thalamus", "cerebellum", "neuron", "the", "cord"])
        self.assertIn("thalamus", text.restore_terms("ده الثالاموس يا جماعة", lex))
        self.assertIn("cerebellum", text.restore_terms("السيريبيلم", lex))
        self.assertEqual(text.restore_terms("ده كلام عادي", lex), set())


class Store(unittest.TestCase):
    def test_edges_rows_cross(self):
        with tempfile.TemporaryDirectory() as d:
            con = store.connect(Path(d) / "g.db")
            store.put_sentences(con, "m", [{"id": "m:h:p1:s1", "i": 0, "text": "A b.", "rows": ["m:h:p1:l1", "m:h:p1:l2"],
                                            "lesson": "m:L01"}])
            store.put_edge(con, "bk:a:x:p1:s1", "m:h:p1:s1", "S", 0.99, "spine-code:A1")
            store.put_edge(con, "bk:b:y:p4:s2", "m:h:p1:s1", "R", 0.9, "spine-fleet")
            store.put_vote(con, "bk:a:x:p1:s1", "code", {"dst": ["m:h:p1:s1"], "rel": "S"})
            self.assertEqual(store.line_ids(con, ["m:h:p1:s1"]), ["m:h:p1:l1", "m:h:p1:l2"])
            self.assertEqual(store.sentences_of_line(con, "m:h:p1:l2"), ["m:h:p1:s1"])
            self.assertEqual(store.cross(con, "bk:a:x:p1:s1"), ["bk:b:y:p4:s2"])
            self.assertEqual(store.votes(con, "bk:a:x:p1:s1")["code"]["rel"], "S")
            self.assertEqual(len(store.edges(con, dst="m:h:p1:s1")), 2)
            con.close()


if __name__ == "__main__":
    unittest.main()

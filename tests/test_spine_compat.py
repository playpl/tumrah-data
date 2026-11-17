import unittest

from spine import compat, graph_dir


class LegacyBlockShape(unittest.TestCase):
    def test_rows_have_the_old_keys(self):
        if not (graph_dir("year2-cns") / "edges" / "ammar-hist-1.jsonl").exists():
            self.skipTest("no edges for ammar-hist-1 on this machine")
        rows = compat.aligned_blocks("year2-cns", "ammar-hist-1")
        self.assertEqual(rows[0]["book_id"], "ammar-hist-1")
        page = rows[1]
        self.assertTrue({"book_id", "page", "page_kind", "lecture_id", "blocks"} <= set(page))
        b = page["blocks"][0]
        self.assertTrue({"n", "text", "figure", "match", "handout", "line_ids"} <= set(b))
        matches = {b["match"] for r in rows[1:] for b in r["blocks"]}
        self.assertTrue(matches <= {"same", "reworded", "partial", "extra", "not_content", "open"})
        linked = [b for r in rows[1:] for b in r["blocks"] if b["match"] in ("same", "reworded", "partial")]
        self.assertTrue(all(b["line_ids"] and b["handout"] for b in linked))



class LectureFiles(unittest.TestCase):
    def test_links_shape(self):
        from spine import ROOT
        if not (ROOT / "lectures" / "cns-002" / "segments.jsonl").exists():
            self.skipTest("cns-002 has no segments on this machine")
        links, ranges = compat.lecture_files("cns-002", write=False)
        self.assertTrue(all({"part", "sub", "title", "start", "end", "line_ids"} <= set(x) for x in links))
        starts = [x["start"] for x in links]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(r["from"] <= r["to"] or r["pages"][0] == r["pages"][1] for r in ranges))


if __name__ == "__main__":
    unittest.main()

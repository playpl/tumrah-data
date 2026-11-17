import unittest

from spine.linktree import crawl

TREE = {"channel": "ch", "root": 1, "nodes": [
    {"id": 1, "kind": "list", "depth": 0, "text": "MSK", "links": [{"anchor": "Dr. A", "id": 2}], "outer": [], "file": None},
    {"id": 2, "kind": "list", "depth": 1, "text": "Dr. A quizzes",
     "links": [{"anchor": "Axilla", "id": 3}, {"anchor": "Book", "id": 4}, {"anchor": "Axilla again", "id": 3}],
     "outer": [], "file": None},
    {"id": 3, "kind": "form", "depth": 2, "text": "Axilla quiz", "links": [],
     "outer": [{"anchor": "", "url": "https://forms.gle/x", "kind": "form"}], "file": None},
    {"id": 4, "kind": "file", "depth": 2, "text": "", "links": [], "outer": [],
     "file": {"name": "mcq.pdf", "mime": "application/pdf", "size": 10}}],
    "unreached": [{"id": 9, "kind": "quizbot"}]}


class LinkTree(unittest.TestCase):
    def test_url_kinds(self):
        self.assertEqual(crawl.url_kind("http://t.me/QuizBot?start=NoEDFK1o"), "quizbot")
        self.assertEqual(crawl.url_kind("https://forms.gle/KrxbNtq8renQw7iQ7"), "form")
        self.assertEqual(crawl.url_kind("https://docs.google.com/forms/d/18dw/edit"), "form")
        self.assertEqual(crawl.url_kind("https://t.me/other/5"), "telegram")
        self.assertEqual(crawl.url_kind("https://example.com"), "web")

    def test_summary_counts_unreached_posts(self):
        text = crawl.summary(TREE)
        self.assertIn("4 posts in the link tree", text)
        self.assertIn("no list links to: 1 (quizbot 1)", text)

    def test_outline_follows_links_once(self):
        lines = crawl.outline(TREE).splitlines()
        self.assertEqual(len(lines), 5)
        self.assertTrue(lines[2].startswith("    3 form"))
        self.assertIn("<mcq.pdf>", lines[3])
        self.assertIn("(seen above)", lines[4])


if __name__ == "__main__":
    unittest.main()

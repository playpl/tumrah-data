import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import db  # noqa: E402


class FakeCursor(list):
    def sort(self, _):
        return self

    def skip(self, n):
        return FakeCursor(self[n:])

    def limit(self, n):
        return FakeCursor(self[:n])


class FakeCollection:
    def __init__(self):
        self.pipeline = None

    def find(self, flt, projection):
        return FakeCursor(range(2000))

    def aggregate(self, pipeline):
        self.pipeline = pipeline
        return []


class FakeDb(dict):
    def __missing__(self, key):
        self[key] = FakeCollection()
        return self[key]


class TestDb(unittest.TestCase):
    def test_source_has_no_write_method(self):
        src = (ROOT / "db.py").read_text(encoding="utf-8")
        for word in ("insert", "update", "delete", "replace", "drop", "bulk_write"):
            self.assertIsNone(re.search(word, src, re.I), word)

    def test_aggregate_refuses_writing_stages(self):
        reader = db.Reader(FakeDb())
        for stage in ({"$out": "x"}, {"$merge": {"into": "x"}}):
            with self.assertRaises(ValueError):
                reader.aggregate("questions", [{"$match": {}}, stage])

    def test_reads_are_capped(self):
        fake = FakeDb()
        reader = db.Reader(fake)
        self.assertEqual(len(reader.find("questions", limit=10**6)), db.MAX_ROWS)
        reader.aggregate("questions", [{"$match": {}}])
        self.assertEqual(fake["questions"].pipeline[-1], {"$limit": db.MAX_ROWS})

    def test_uri_read_from_env_file(self):
        tmp = ROOT / "tests" / "_env_fixture"
        tmp.write_text("A=1\nMONGODB_URI=\"mongodb://x/y\"\n", encoding="utf-8")
        try:
            self.assertEqual(db._uri(tmp), "mongodb://x/y")
        finally:
            tmp.unlink()


if __name__ == "__main__":
    unittest.main()

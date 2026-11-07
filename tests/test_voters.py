import json
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import voters  # noqa: E402
from voters import engine  # noqa: E402


class TestVoters(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.c = engine.db(Path(self.dir.name) / "t.db")
        self.c.execute("INSERT INTO polls(chat,msg_id,word_key,status,key,votes,total,seen) VALUES(?,?,?,?,?,?,?,?)",
                       ("Batch58ATM", 7, "k", "keyed", 1, json.dumps([2, 5]), 7, 100.0))
        engine.add_own(self.c, "Batch58ATM", 7, "voter3", 0, 50.0)
        self.c.execute("INSERT INTO polls(chat,msg_id,word_key,status) VALUES('Batch58ATM', 8, 'k2', 'need')")

    def tearDown(self):
        self.c.close()
        self.dir.cleanup()

    def test_each_keyed_poll_is_read_by_an_account_that_voted(self):
        todo = voters.plan(self.c)
        self.assertEqual({a: dict(v) for a, v in todo.items()}, {"voter3": {"Batch58ATM": [7]}})

    def test_new_counts_are_stored_net_of_our_vote_and_the_key_never_changes(self):
        report = defaultdict(int)
        voters.apply_read(self.c, "Batch58ATM", 7, {"key": 0, "votes": [4, 9], "total": 13, "chosen": 0}, report)
        row = self.c.execute("SELECT key, votes, total FROM polls WHERE msg_id=7").fetchone()
        self.assertEqual((row["key"], json.loads(row["votes"]), row["total"]), (1, [4, 9], 13))
        self.assertEqual(dict(report), {"read": 1, "key_reads_differently": 1, "polls_changed": 1, "new_voters": 6})

    def test_site_rows_only_for_keyed_questions_on_the_site(self):
        bank = [{"word_key": "a", "key": 1, "total": 10, "votes": [3, 7], "key_conflict": False},
                {"word_key": "b", "key": None, "total": 5, "votes": [5], "key_conflict": False},
                {"word_key": "c", "key": 0, "total": 5, "votes": [5], "key_conflict": True},
                {"word_key": "d", "key": 0, "total": 5, "votes": [5], "key_conflict": False}]
        self.assertEqual(voters.site_stats(bank, {"a": "s1", "b": "s2", "c": "s3"}),
                         [{"question_id": "s1", "attempts": 10, "correct": 7}])


if __name__ == "__main__":
    unittest.main()

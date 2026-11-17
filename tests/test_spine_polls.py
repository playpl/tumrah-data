import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from spine.polls import registry

REG = [{"chat": "A59", "university": "ZU", "batch": 59, "year": 1, "role": "backbone", "grade": 4, "harvest": True},
       {"chat": "B58", "university": "ZU", "batch": 58, "year": 2, "role": "backbone", "grade": 4, "harvest": True,
        "drop_modules": ["year2-endo"]},
       {"chat": "old58", "university": "ZU", "batch": 58, "year": 1, "role": "archive", "grade": 5, "harvest": False}]


def q(wk, *sightings):
    return {"word_key": wk, "question": wk, "options": ["a", "b"], "sightings": [
        {"source": "poll", "chat": s} if s != "form" else {"source": "form", "chat": "someone"} for s in sightings]}


class Plan(unittest.TestCase):
    def verdict(self, module, *sightings):
        return registry.plan(q("x", *sightings), module, REG)[0]

    def test_drop_only_the_named_modules_of_that_channel(self):
        self.assertEqual(self.verdict("year2-endo", "B58"), "delete")
        self.assertEqual(self.verdict("year2-cns", "B58"), "keep")
        self.assertEqual(self.verdict(registry.UNLABELLED, "B58"), "keep")
        self.assertEqual(self.verdict("year1-msk", "B58"), "keep")
        self.assertEqual(self.verdict("year2-endo", "A59"), "keep")

    def test_archive_goes_to_grade5_unless_repeated(self):
        self.assertEqual(self.verdict("year1-msk", "old58"), "grade5")
        self.assertEqual(self.verdict("year1-msk", "old58", "A59"), "trim")     # the repeated one stays with the backbone
        self.assertEqual(self.verdict("year1-msk", "old58", "form"), "trim")    # a doctor's quiz keeps it

    def test_a_dropped_question_seen_elsewhere_stays(self):
        self.assertEqual(self.verdict("year2-endo", "B58", "form"), "trim")
        self.assertEqual(self.verdict("year2-endo", "B58", "old58"), "grade5")


class InventoryCounts(unittest.TestCase):
    def test_counts_and_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            polls, bank = Path(d) / "polls", Path(d) / "bank"
            (polls / "raw" / "B58").mkdir(parents=True)
            bank.mkdir()
            rows = [q("k1", "B58"), q("k2", "B58"), q("k3", "old58"), q("k4", "old58", "A59")]
            (bank / "questions.jsonl").write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
            labels = [{"word_key": "k1", "module": "year2-endo"}, {"word_key": "k2", "module": "year2-cns"},
                      {"word_key": "k3", "module": "year1-msk"}, {"word_key": "k4", "module": "year1-msk"}]
            (bank / "labels.jsonl").write_text("\n".join(map(json.dumps, labels)), encoding="utf-8")
            (polls / "raw" / "B58" / "messages.jsonl").write_text("{}\n{}\n", encoding="utf-8")
            con = sqlite3.connect(polls / "polls.db")
            con.execute("CREATE TABLE polls(chat, msg_id, word_key, status)")
            con.execute("CREATE TABLE own(chat, msg_id, account)")
            con.executemany("INSERT INTO polls VALUES (?,?,?,?)", [("B58", 1, "k1", "keyed"), ("B58", 2, "k2", "keyed"),
                                                                 ("old58", 1, "k3", "keyed"), ("A59", 1, "k4", "keyed")])
            con.executemany("INSERT INTO own VALUES (?,?,?)", [("B58", 1, "v1"), ("B58", 2, "v1")])
            con.commit()
            con.close()
            before = (polls / "polls.db").read_bytes()
            inv = registry.inventory(polls, bank, REG)
            self.assertEqual((polls / "polls.db").read_bytes(), before)
            self.assertEqual(inv["bank_total"], 4)
            self.assertEqual(inv["db_plan"][("delete", "B58", "year2-endo")], 1)
            self.assertEqual(inv["db_plan"][("grade5", "old58", "year1-msk")], 1)
            self.assertEqual(inv["own_plan"]["B58"], 1)
            self.assertEqual(inv["raw"]["B58"], 2)
            verdicts = {k[0]: n for k, n in inv["bank_plan"].items()}
            self.assertEqual(verdicts, {"delete": 1, "keep": 1, "grade5": 1, "trim": 1})
            self.assertIn("CHANGE A", registry.report(inv, REG))


if __name__ == "__main__":
    unittest.main()

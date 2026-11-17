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


class Apply(unittest.TestCase):
    """spine/polls/apply.py on a copy: dry run writes nothing; --go moves, deletes and trims as planned."""

    def make(self, d):
        import shutil
        from spine.polls import apply
        polls, bank = Path(d) / "polls", Path(d) / "bank"
        (polls / "raw" / "old58").mkdir(parents=True)
        (polls / "ready").mkdir()
        bank.mkdir()
        shutil.copy(apply.POLLS / "engine.py", polls / "engine.py")
        shutil.copy(apply.POLLS / "channels.json", polls / "channels.json")
        rows = [dict(q(*r), key=0, key_conflict=False, repetition_count=1)
                for r in (("k1", "B58"), ("k2", "B58"), ("k3", "old58"), ("k4", "old58", "A59"), ("k5", "B58", "form"))]
        (bank / "questions.jsonl").write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
        labels = [{"word_key": "k1", "module": "year2-endo"}, {"word_key": "k2", "module": "year2-cns"},
                  {"word_key": "k3", "module": "year1-msk"}, {"word_key": "k4", "module": "year1-msk"},
                  {"word_key": "k5", "module": "year2-endo"}]
        (bank / "labels.jsonl").write_text("\n".join(map(json.dumps, labels)), encoding="utf-8")
        (polls / "raw" / "old58" / "messages.jsonl").write_text("{}\n", encoding="utf-8")
        engine = apply._engine(polls)
        ready = []
        for wk, chats in (("k1", ["B58"]), ("k2", ["B58"]), ("k3", ["old58"]), ("k4", ["old58", "A59"])):
            ready.append({"question": wk, "options": ["a", "b"], "key": 0,
                          "sightings": [{"chat": c, "msg_id": 1} for c in chats]})
        (polls / "ready" / "questions.jsonl").write_text("\n".join(map(json.dumps, ready)), encoding="utf-8")
        labels_wk = {engine.word_key(r["question"], r["options"]): l["module"] for r, l in zip(ready, labels)}
        (bank / "labels.jsonl").write_text("\n".join(map(json.dumps, labels + [
            {"word_key": k, "module": m} for k, m in labels_wk.items()])), encoding="utf-8")
        c = engine.db(polls / "polls.db")
        c.executemany("INSERT INTO polls(chat, msg_id, word_key, status) VALUES(?,?,?,?)",
                      [("B58", 1, "k1", "keyed"), ("B58", 2, "k2", "dupe"), ("old58", 1, "k2", "keyed"),
                       ("old58", 2, "k3", "keyed"), ("A59", 1, "k4", "keyed")])
        c.executemany("INSERT INTO own VALUES(?,?,?,?,?)", [("B58", 1, "v", 0, 0.0), ("B58", 2, "v", 0, 0.0),
                                                            ("old58", 1, "v", 0, 0.0)])
        c.execute("INSERT INTO channels VALUES('old58', 9, 9)")
        c.close()
        cfg = Path(d) / "config.json"
        cfg.write_text(json.dumps({"poll_channels": {"2": ["old58", "B58"]}}), encoding="utf-8")
        return apply, polls, bank, cfg

    def test_dry_then_go(self):
        with tempfile.TemporaryDirectory() as d:
            apply, polls, bank, cfg = self.make(d)
            before = (bank / "questions.jsonl").read_bytes()
            self.assertEqual(apply.apply(False, polls, bank, REG, cfg, out=lambda *_: None), 0)
            self.assertEqual((bank / "questions.jsonl").read_bytes(), before)
            self.assertFalse((polls / "grade5").exists())
            self.assertEqual(apply.apply(True, polls, bank, REG, cfg, out=lambda *_: None), 0)
            left = [json.loads(x) for x in (bank / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([r["word_key"] for r in left], ["k2", "k4", "k5"])
            self.assertEqual([s["chat"] for s in left[1]["sightings"]], ["A59"])     # trimmed
            self.assertEqual([s["chat"] for s in left[2]["sightings"]], ["someone"])  # A sighting gone, form stays
            g5 = [json.loads(x) for x in (polls / "grade5" / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([(r["word_key"], r["module"]) for r in g5], [("k3", "year1-msk")])
            con = sqlite3.connect(polls / "polls.db")
            self.assertEqual(sorted(con.execute("SELECT chat, msg_id, status FROM polls")),
                             [("A59", 1, "keyed"), ("B58", 2, "need")])    # the dupe's keyed twin left: vote again
            self.assertEqual(list(con.execute("SELECT chat, msg_id FROM own")), [("B58", 2)])
            self.assertEqual(list(con.execute("SELECT * FROM channels")), [])
            con.close()
            con = sqlite3.connect(polls / "grade5" / "polls.db")
            self.assertEqual(sorted(con.execute("SELECT chat, msg_id FROM polls")), [("old58", 1), ("old58", 2)])
            self.assertEqual(list(con.execute("SELECT chat, msg_id FROM own")), [("old58", 1)])
            con.close()
            ready = [json.loads(x) for x in (polls / "ready" / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([[s["chat"] for s in r["sightings"]] for r in ready], [["B58"], ["A59"]])
            self.assertEqual((polls / "tombstones.jsonl").read_text(encoding="utf-8").count("\n"), 1)
            self.assertTrue((polls / "grade5" / "raw" / "old58" / "messages.jsonl").exists())
            self.assertFalse((polls / "raw" / "old58").exists())
            self.assertEqual(json.loads(cfg.read_text(encoding="utf-8"))["poll_channels"], {"2": ["B58"]})

    def test_refuses_while_the_job_runs(self):
        import time
        with tempfile.TemporaryDirectory() as d:
            apply, polls, bank, cfg = self.make(d)
            con = sqlite3.connect(polls / "polls.db")
            con.execute("INSERT INTO state VALUES('beat', ?)", (str(time.time()),))
            con.commit()
            con.close()
            self.assertEqual(apply.apply(True, polls, bank, REG, cfg, out=lambda *_: None), 2)
            self.assertFalse((polls / "grade5").exists())


class EngineRegistry(unittest.TestCase):
    def test_channels_follow_the_registry(self):
        import sys
        sys.path.insert(0, str(registry.POLLS))
        import engine
        chans, seed = engine.load_channels()
        self.assertEqual(list(chans), ["Batch58ATM", "ZAG_59_Polls"])
        self.assertNotIn("zagpolls58", chans)
        self.assertEqual(seed, {"Batch58ATM", "ZAG_59_Polls"})
        with tempfile.TemporaryDirectory() as d:
            t = Path(d) / "t.jsonl"
            t.write_text('{"chat": "B", "msg_id": 3}\n', encoding="utf-8")
            self.assertEqual(engine.tombstones(t), {("B", 3)})
            self.assertEqual(engine.tombstones(Path(d) / "none.jsonl"), set())


if __name__ == "__main__":
    unittest.main()

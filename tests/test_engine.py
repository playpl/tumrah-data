import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "polls"))
import engine  # noqa: E402


def poll(*opts):
    return NS(answers=[NS(option=o) for o in opts])


def results(*rows, solution=None):
    """rows: (option, voters, correct, chosen)"""
    return NS(results=[NS(option=o, voters=v, correct=c, chosen=ch) for o, v, c, ch in rows],
              total_voters=sum(r[1] for r in rows), solution=solution)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.c = engine.db(Path(self.dir.name) / "t.db")
        engine.STOP = Path(self.dir.name) / "stop.flag"

    def tearDown(self):
        self.c.close()
        self.dir.cleanup()

    def add(self, chat, msg_id, key_text, status="need"):
        self.c.execute("INSERT INTO polls(chat,msg_id,word_key,status) VALUES(?,?,?,?)", (chat, msg_id, key_text, status))


class Keys(unittest.TestCase):
    def test_word_key_ignores_numbering_labels_order_and_case(self):
        self.assertEqual(engine.word_key("Q12: What is, this?", ["A) One", "B) Two"]),
                         engine.word_key("what is this", ["two", "ONE"]))

    def test_one_different_word_is_a_different_question(self):
        self.assertNotEqual(engine.word_key("a b", ["x", "y"]), engine.word_key("a c", ["x", "y"]))

    def test_read_results_maps_by_option_not_by_result_order(self):
        got = engine.read_results(poll(b"0", b"1", b"2"),
                                  results((b"2", 5, True, False), (b"0", 1, False, True), (b"1", 0, False, False)))
        self.assertEqual((got["key"], got["votes"], got["chosen"]), (2, [1, 0, 5], 0))

    def test_no_results_means_no_key(self):
        self.assertIsNone(engine.read_results(poll(b"0"), None)["key"])


class OwnVotes(unittest.TestCase):
    def test_own_votes_never_count(self):
        self.assertEqual(engine.net([5, 1, 0], 6, [(0, 10.0), (1, 10.0)], seen=20.0), ([4, 0, 0], 4))

    def test_vote_after_the_snapshot_is_not_subtracted(self):
        self.assertEqual(engine.net([5, 1], 6, [(0, 30.0)], seen=20.0), ([5, 1], 6))

    def test_counts_never_go_below_zero(self):
        self.assertEqual(engine.net([0, 0], 0, [(1, 1.0)], seen=2.0), ([0, 0], 0))


class Queue(Base):
    def test_claims_never_overlap_and_follow_channel_order(self):
        self.add("zagpolls58", 1, "a")
        self.add("Batch58ATM", 5, "b")
        self.add("Batch58ATM", 9, "c")
        chats = ["Batch58ATM", "zagpolls58"]
        self.assertEqual(engine.claim(self.c, "v1", chats, 2), [("Batch58ATM", 9), ("Batch58ATM", 5)])
        self.assertEqual(engine.claim(self.c, "v2", chats, 2), [("zagpolls58", 1)])

    def test_account_gets_only_its_channels(self):
        self.add("zagpolls58", 1, "a")
        self.assertEqual(engine.claim(self.c, "v1", ["Batch58ATM"], 5), [])

    def test_release_returns_claims(self):
        self.add("zagpolls58", 1, "a")
        engine.claim(self.c, "v1", ["zagpolls58"], 5)
        engine.release(self.c, "v1")
        self.assertEqual(engine.claim(self.c, "v2", ["zagpolls58"], 5), [("zagpolls58", 1)])

    def test_one_vote_per_distinct_question(self):
        self.add("zagpolls58", 1, "same")
        self.add("Batch58ATM", 2, "same")
        self.add("Batch58ATM", 3, "keyed", "keyed")
        self.add("zagpolls58", 4, "keyed")
        engine.mark_dupes(self.c)
        rows = {(r["chat"], r["msg_id"]): r["status"] for r in self.c.execute("SELECT * FROM polls")}
        self.assertEqual(rows[("Batch58ATM", 2)], "need")
        self.assertEqual(rows[("zagpolls58", 1)], "dupe")
        self.assertEqual(rows[("zagpolls58", 4)], "dupe")


class FakeFlood(Exception):
    seconds = 0


class FakeStop(Exception):
    pass


class FakeClient:
    """Answers like Telegram: option b"1" is correct, each poll had 3 voters on it before our vote."""

    def __init__(self, fail=None):
        self.votes, self.fail = [], fail

    async def get_messages(self, ent, ids):
        return [NS(id=i, media=NS(poll=poll(b"0", b"1"), results=None)) for i in ids]

    async def __call__(self, request):
        if self.fail:
            error, self.fail = self.fail, None
            raise error
        self.votes.append(request.msg_id)
        mine = request.options[0]
        res = results((b"0", int(mine == b"0"), False, mine == b"0"), (b"1", 3 + int(mine == b"1"), True, mine == b"1"))
        return NS(updates=[NS(results=res)])


def fake_tg(fatal=False):
    def check_fatal(error, label):
        if fatal:
            raise FakeStop(f"[{label}] account limited: {error}")
    return NS(FloodWaitError=FakeFlood, Stop=FakeStop, check_fatal=check_fatal,
              SendVoteRequest=lambda peer, msg_id, options: NS(msg_id=msg_id, options=options))


class Voting(Base):
    def run_voter(self, client, tg=None, label="v1", shared=None):
        self.c.execute("INSERT OR IGNORE INTO accounts(label) VALUES(?)", (label,))
        engine.put(self.c, "interval", 0)
        shared = {"halt": None} if shared is None else shared
        asyncio.run(engine.voter(label, client, {"Batch58ATM": "ent"}, self.c, tg or fake_tg(), shared))
        return shared

    def test_votes_every_poll_once_and_ledgers_it(self):
        self.add("Batch58ATM", 1, "a")
        self.add("Batch58ATM", 2, "b")
        client = FakeClient()
        self.run_voter(client)
        self.assertEqual(sorted(client.votes), [1, 2])
        rows = self.c.execute("SELECT * FROM polls").fetchall()
        self.assertEqual({r["status"] for r in rows}, {"keyed"})
        self.assertEqual({r["key"] for r in rows}, {1})
        self.assertEqual(self.c.execute("SELECT COUNT(*) n FROM own").fetchone()["n"], 2)

    def test_own_vote_leaves_the_real_count(self):
        self.add("Batch58ATM", 1, "a")
        self.run_voter(FakeClient())
        row = self.c.execute("SELECT * FROM polls").fetchone()
        own = [(r["option"], r["ts"]) for r in self.c.execute("SELECT * FROM own")]
        self.assertEqual(engine.net(json.loads(row["votes"]), row["total"], own, row["seen"]), ([0, 3], 3))

    def test_stop_flag_leaves_nothing_claimed(self):
        self.add("Batch58ATM", 1, "a")
        engine.STOP.write_text("")
        client = FakeClient()
        self.run_voter(client)
        self.assertEqual(client.votes, [])
        self.assertEqual(self.c.execute("SELECT status FROM polls").fetchone()["status"], "need")

    def test_flood_returns_the_poll_and_retries(self):
        self.add("Batch58ATM", 1, "a")
        client = FakeClient(fail=FakeFlood())
        self.run_voter(client)
        self.assertEqual(client.votes, [1])
        self.assertEqual(self.c.execute("SELECT floods FROM accounts").fetchone()["floods"], 1)

    def test_restriction_stops_every_account(self):
        self.add("Batch58ATM", 1, "a")
        shared = self.run_voter(FakeClient(fail=FakeFlood("USER_RESTRICTED")), fake_tg(fatal=True))
        self.assertIn("USER_RESTRICTED", shared["halt"])
        self.assertEqual(self.c.execute("SELECT status FROM polls").fetchone()["status"], "need")

    def test_signed_out_account_stops_alone(self):
        self.add("Batch58ATM", 1, "a")
        shared = self.run_voter(FakeClient(fail=FakeFlood("AUTH_KEY_UNREGISTERED")), fake_tg(fatal=True))
        self.assertIsNone(shared["halt"])
        self.assertEqual(self.c.execute("SELECT state FROM accounts").fetchone()["state"], "needs login")


class Joining(unittest.TestCase):
    class Client:
        def __init__(self, ids=None, fail=None):
            self.ids, self.fail, self.joined = ids or engine.CHANNELS, fail, []

        async def get_entity(self, name):
            return NS(id=self.ids[name], name=name)

        async def __call__(self, request):
            if self.fail:
                raise self.fail
            self.joined.append(request)

    def run_join(self, client, have):
        return asyncio.run(engine.join_missing(client, have, NS(JoinChannelRequest=lambda ent: ent.name)))

    def test_joins_only_what_is_missing(self):
        client, have = self.Client(), {"Batch58ATM": "ent"}
        self.assertEqual(self.run_join(client, have), "")
        self.assertEqual(sorted(client.joined), ["ZAG_59_Polls", "zagpolls58"])
        self.assertEqual(len(have), 3)

    def test_failed_join_is_reported_and_keeps_the_rest(self):
        have = {"Batch58ATM": "ent"}
        problem = self.run_join(self.Client(fail=Exception("CHANNELS_TOO_MUCH")), have)
        self.assertIn("CHANNELS_TOO_MUCH", problem)
        self.assertEqual(list(have), ["Batch58ATM"])

    def test_never_joins_a_username_that_moved_to_another_chat(self):
        client = self.Client(ids=dict(engine.CHANNELS, zagpolls58=1))
        problem = self.run_join(client, {"Batch58ATM": "e", "ZAG_59_Polls": "e"})
        self.assertIn("another chat", problem)
        self.assertEqual(client.joined, [])


class LateLogin(unittest.TestCase):
    def test_account_that_logs_in_joins_the_running_job(self):
        ran = []

        async def work(name, seconds):
            await asyncio.sleep(seconds)
            ran.append(name)

        async def go():
            async def retry():
                return [asyncio.create_task(work("late", 0))] if "late" not in ran else []
            await engine.run_voters(lambda: [asyncio.create_task(work("first", 2.2))], retry, every=1)

        asyncio.run(go())
        self.assertIn("late", ran)
        self.assertIn("first", ran)


class Ready(Base):
    def raw(self, chat, rows):
        d = Path(self.dir.name) / "raw" / chat
        d.mkdir(parents=True, exist_ok=True)
        (d / "messages.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def msg(self, mid, q, options):
        return {"msg_id": mid, "type": "poll", "date": "2026-10-01", "text": "",
                "poll": {"question": q, "options": options, "quiz": True}}

    def save(self, chat, mid, wk, key, votes, status="keyed"):
        self.c.execute("INSERT INTO polls(chat,msg_id,word_key,status,key,votes,total,seen) VALUES(?,?,?,?,?,?,?,?)",
                       (chat, mid, wk, status, key, json.dumps(votes) if votes else None, sum(votes or []), 20.0))

    def build(self):
        return engine.build_ready(self.c, Path(self.dir.name) / "raw", Path(self.dir.name) / "ready")

    def rows(self):
        f = Path(self.dir.name) / "ready" / "questions.jsonl"
        return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()]

    def test_own_vote_removed_and_reposts_add_up_by_option_text(self):
        wk = engine.word_key("Q", ["Yes", "No"])
        self.raw("Batch58ATM", [{"msg_id": 1, "type": "text", "text": "Header\nmore", "date": "x"},
                                self.msg(2, "Q", ["Yes", "No"])])
        self.raw("zagpolls58", [self.msg(7, "Q", ["No", "Yes"])])
        self.save("Batch58ATM", 2, wk, 0, [4, 2])
        self.save("zagpolls58", 7, wk, 1, [1, 3])
        engine.add_own(self.c, "Batch58ATM", 2, "v1", 1, 10.0)
        self.assertEqual(self.build()["questions"], 1)
        row = self.rows()[0]
        self.assertEqual((row["votes"], row["total"], row["key"]), ([7, 2], 9, 0))
        self.assertEqual(row["sightings"][0]["header"], "Header")
        self.assertFalse(row["key_conflict"])

    def test_postings_that_disagree_are_flagged(self):
        wk = engine.word_key("Q", ["Yes", "No"])
        self.raw("Batch58ATM", [self.msg(2, "Q", ["Yes", "No"])])
        self.raw("zagpolls58", [self.msg(7, "Q", ["Yes", "No"])])
        self.save("Batch58ATM", 2, wk, 0, [1, 0])
        self.save("zagpolls58", 7, wk, 1, [0, 1])
        self.build()
        self.assertTrue(self.rows()[0]["key_conflict"])

    def test_no_key_goes_to_held_never_to_questions(self):
        wk = engine.word_key("Q", ["Yes", "No"])
        self.raw("Batch58ATM", [self.msg(2, "Q", ["Yes", "No"])])
        self.save("Batch58ATM", 2, wk, None, None, "held")
        counts = self.build()
        self.assertEqual((counts["questions"], counts["held"]), (0, 1))


if __name__ == "__main__":
    unittest.main()

"""The ledger, the checked placement, the owner's cards and the Gemini answer readers (2026-11-10).
Every test uses a temp ledger file and made-up ids: the real ledger.db and lectures/ are never opened for writing."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import decisions  # noqa: E402
import doctors_folder  # noqa: E402
import gemini_run  # noqa: E402
import lectures  # noqa: E402
import ledger  # noqa: E402
import placement  # noqa: E402
import runners  # noqa: E402

M = "mod"
RULE = {"max_error": 0.05, "min_checked": 30}


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = ledger.connect(Path(self.tmp.name) / "ledger.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def state(self, src, runner, kind="question"):
        r = self.db.execute("SELECT state FROM links WHERE kind=? AND src=? AND runner=?", (kind, src, runner)).fetchone()
        return r["state"] if r else None

    def set_state(self, src, runner, state):
        self.db.execute("UPDATE links SET state=? WHERE src=? AND runner=?", (state, src, runner))


class TestPut(LedgerCase):
    def test_same_lines_keep_the_state_and_new_lines_start_again(self):
        ledger.put(self.db, M, "question", "q1", "web", ["a", "b"])
        self.assertEqual(self.state("q1", "web"), "proposed")
        self.set_state("q1", "web", "agreed")
        ledger.put(self.db, M, "question", "q1", "web", ["a", "b"], scope="again")
        self.assertEqual(self.state("q1", "web"), "agreed")
        ledger.put(self.db, M, "question", "q1", "web", ["a", "c"])
        self.assertEqual(self.state("q1", "web"), "proposed")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM links").fetchone()[0], 1)

    def test_a_rejected_row_stays_rejected_when_the_reader_repeats_itself(self):
        ledger.put(self.db, M, "question", "q1", "script", ["a"])
        ledger.mark(self.db, "question", "q1", "script", False)
        ledger.put(self.db, M, "question", "q1", "script", ["a"])
        self.assertEqual(self.state("q1", "script"), "rejected")

    def test_the_owner_runner_and_a_given_state_are_written_as_said(self):
        ledger.put(self.db, M, "question", "q1", "owner", ["a"])
        self.assertEqual(self.state("q1", "owner"), "owner")
        ledger.put(self.db, M, "lesson", "l1", "agent", [["a", "b"]])
        ledger.put(self.db, M, "lesson", "l1", "agent", [["a", "b"]], state="owner")
        self.assertEqual(self.state("l1", "agent", "lesson"), "owner")

    def test_each_reader_has_its_own_row(self):
        ledger.put(self.db, M, "question", "q1", "script", ["a"])
        ledger.put(self.db, M, "question", "q1", "web", ["b"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM links WHERE src='q1'").fetchone()[0], 2)


class TestAgree(LedgerCase):
    def test_a_shared_line_is_agreed_and_no_shared_line_is_a_conflict(self):
        ledger.put(self.db, M, "question", "same", "script", ["a", "b"])
        ledger.put(self.db, M, "question", "same", "web", ["b", "c"])
        ledger.put(self.db, M, "question", "apart", "script", ["a"])
        ledger.put(self.db, M, "question", "apart", "web", ["z"])
        ledger.put(self.db, M, "question", "alone", "script", ["a"])
        n = ledger.agree(self.db, M)
        self.assertEqual(dict(n), {"agreed": 1, "conflict": 1})
        self.assertEqual([self.state("same", r) for r in ("script", "web")], ["agreed", "agreed"])
        self.assertEqual([self.state("apart", r) for r in ("script", "web")], ["conflict", "conflict"])
        self.assertEqual(self.state("alone", "script"), "proposed")

    def test_a_thing_the_owner_settled_is_left_alone(self):
        ledger.put(self.db, M, "question", "q1", "script", ["a"])
        ledger.put(self.db, M, "question", "q1", "web", ["z"])
        ledger.put(self.db, M, "question", "q1", "owner", ["a"])
        self.assertEqual(dict(ledger.agree(self.db, M)), {})
        self.assertEqual([self.state("q1", r) for r in ("script", "web", "owner")], ["proposed", "proposed", "owner"])

    def test_not_found_and_rejected_rows_do_not_vote(self):
        ledger.put(self.db, M, "question", "q1", "script", ["a"])
        ledger.put(self.db, M, "question", "q1", "web", [], found=False, reason="other_lecture")
        ledger.put(self.db, M, "question", "q2", "script", ["a"])
        ledger.put(self.db, M, "question", "q2", "web", ["z"])
        ledger.mark(self.db, "question", "q2", "web", False)
        self.assertEqual(dict(ledger.agree(self.db, M)), {})
        self.assertEqual(self.state("q1", "script"), "proposed")
        self.assertEqual(self.state("q2", "web"), "rejected")

    def test_a_conflict_becomes_agreed_when_a_reader_moves_to_the_same_line(self):
        ledger.put(self.db, M, "question", "q1", "script", ["a"])
        ledger.put(self.db, M, "question", "q1", "web", ["z"])
        ledger.agree(self.db, M)
        ledger.put(self.db, M, "question", "q1", "web", ["a"])
        ledger.agree(self.db, M)
        self.assertEqual([self.state("q1", r) for r in ("script", "web")], ["agreed", "agreed"])


class TestRanges(unittest.TestCase):
    # page 1: a b c, page 2: d e f; the figure of page 1 comes last in the file
    IDS = ["a", "b", "c", "d", "e", "f", "fig1"]
    PAGE = {"a": 1, "b": 1, "c": 1, "d": 2, "e": 2, "f": 2, "fig1": 1}
    IDX = {i: n for n, i in enumerate(IDS)}

    def ids(self, ranges):
        return ledger.range_ids(ranges, self.IDX, self.IDS, self.PAGE)

    def test_a_cut_range_runs_line_by_line(self):
        self.assertEqual(self.ids([{"from": "b", "to": "d", "pages": [1, 2], "cut": True}]), {"b", "c", "d"})

    def test_a_whole_page_range_takes_every_line_of_its_pages(self):
        self.assertEqual(self.ids([{"from": "a", "to": "c", "pages": [1, 1]}]), {"a", "b", "c", "fig1"})

    def test_ranges_join_and_an_unknown_line_gives_nothing(self):
        self.assertEqual(self.ids([{"from": "a", "to": "a", "pages": [1, 1], "cut": True},
                                   {"from": "d", "to": "f", "pages": [2, 2]}]), {"a", "d", "e", "f"})
        self.assertEqual(self.ids([{"from": "a", "to": "gone", "pages": [1, 1], "cut": True}]), set())
        self.assertEqual(self.ids(None), set())


class TestWilson(unittest.TestCase):
    def test_nothing_checked_says_nothing(self):
        self.assertEqual(ledger.wilson(0, 0), (None, 0.0, 1.0))

    def test_the_interval_holds_the_rate(self):
        rate, low, high = ledger.wilson(0, 30)
        self.assertEqual((rate, low), (0.0, 0.0))
        self.assertAlmostEqual(high, 0.1135, places=3)
        rate, low, high = ledger.wilson(5, 100)
        self.assertEqual(rate, 0.05)
        self.assertAlmostEqual(low, 0.0215, places=3)
        self.assertAlmostEqual(high, 0.1118, places=3)
        self.assertEqual(ledger.wilson(10, 10)[2], 1.0)


class TestReady(LedgerCase):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(ledger, "ready_rule", return_value=dict(RULE))
        p.start()
        self.addCleanup(p.stop)

    def checks(self, runner, right, wrong=0, kind="question"):
        have = self.db.execute("SELECT COUNT(*) FROM gold").fetchone()[0]
        for i in range(right + wrong):
            self.db.execute("INSERT INTO gold(kind, src, runner, verdict, at) VALUES(?,?,?,?,0)",
                            (kind, f"g{have + i}", runner, "right" if i < right else "wrong"))

    def ready(self):
        return {src: r["runner"] for src, r in ledger.ready(self.db, M, "question").items()}

    def test_a_lone_proposal_is_not_ready_until_its_reader_passes(self):
        ledger.put(self.db, M, "question", "q1", "web", ["a"])
        self.assertEqual(self.ready(), {})
        self.checks("web", 29)
        self.assertEqual(self.ready(), {})          # too few checks
        self.checks("web", 1)
        self.assertEqual(self.ready(), {"q1": "web"})

    def test_a_reader_over_the_error_limit_does_not_pass(self):
        ledger.put(self.db, M, "question", "q1", "web", ["a"])
        self.checks("web", 28, wrong=2)             # 6.7% wrong
        self.assertEqual(ledger.passing(self.db), set())
        self.assertEqual(self.ready(), {})

    def test_owner_first_then_agreed_then_a_passing_proposal_and_ai_before_script(self):
        self.checks("web", 30)
        self.checks("script", 30)
        ledger.put(self.db, M, "question", "own", "script", ["a"])
        ledger.put(self.db, M, "question", "own", "web", ["a"])
        ledger.agree(self.db, M)
        ledger.put(self.db, M, "question", "own", "owner", ["b"])
        ledger.put(self.db, M, "question", "both", "script", ["a"])
        ledger.put(self.db, M, "question", "both", "web", ["a", "b"])
        ledger.agree(self.db, M)
        ledger.put(self.db, M, "question", "mixed", "script", ["a"])
        ledger.put(self.db, M, "question", "mixed", "web", ["b"])
        self.set_state("mixed", "script", "agreed")  # agreed beats proposed even when the proposal is an AI's
        self.assertEqual(self.ready(), {"own": "owner", "both": "web", "mixed": "script"})

    def test_conflict_rejected_and_not_found_rows_are_never_ready(self):
        self.checks("web", 30)
        self.checks("script", 30)
        ledger.put(self.db, M, "question", "apart", "script", ["a"])
        ledger.put(self.db, M, "question", "apart", "web", ["z"])
        ledger.agree(self.db, M)
        ledger.put(self.db, M, "question", "bad", "web", ["a"])
        ledger.mark(self.db, "question", "bad", "web", False)
        ledger.put(self.db, M, "question", "none", "web", [], found=False, reason="other_lecture")
        self.assertEqual(self.ready(), {})

    def test_mark_scores_the_reader_and_never_touches_an_owner_row(self):
        ledger.put(self.db, M, "question", "q1", "web", ["a"])
        ledger.put(self.db, M, "question", "q1", "owner", ["a"])
        ledger.mark(self.db, "question", "q1", "web", True)
        ledger.mark(self.db, "question", "q1", "owner", False)
        self.assertEqual([self.state("q1", r) for r in ("web", "owner")], ["agreed", "owner"])
        e = ledger.errors(self.db)
        self.assertEqual((e[("question", "web")]["checked"], e[("question", "web")]["wrong"]), (1, 0))
        self.assertEqual(e[("question", "owner")]["wrong"], 1)


class TestMembers(LedgerCase):
    def test_a_question_follows_the_lesson_that_holds_its_lines(self):
        ledger.put(self.db, M, "question", "q1", "owner", ["b"])
        ledger.put(self.db, M, "question", "q2", "owner", ["c", "d"])
        with mock.patch.object(ledger, "ready_rule", return_value=dict(RULE)):
            with mock.patch.object(ledger, "lesson_ids", return_value={"l1": {"a", "b", "c"}, "l2": {"d"}}):
                self.assertEqual(ledger.members(self.db, M), {"l1": ["q1", "q2"], "l2": ["q2"]})
            with mock.patch.object(ledger, "lesson_ids", return_value={"l1": {"a"}, "l2": {"b", "c", "d"}}):
                self.assertEqual(ledger.members(self.db, M), {"l1": [], "l2": ["q1", "q2"]})  # a moved boundary moves them


class TestPointerAnswers(unittest.TestCase):
    LABELS = {f"48.{n}": {"id": f"id{n}", "page": 48} for n in range(1, 21)}

    def read(self, lines, n):
        return gemini_run.pointer_answers("\n".join(json.dumps(x) if isinstance(x, dict) else x for x in lines), n, self.LABELS)

    def test_lines_none_and_partial_are_read(self):
        got, errors = self.read([{"q": 1, "lines": ["48.1", "48.2", "48.1"], "partial": True},
                                 {"q": 2, "none": "other_lecture"}, {"q": 3, "lines": ["48.5"]}], 3)
        self.assertEqual(errors, [])
        self.assertEqual(got, {1: {"ids": ["id1", "id2"], "partial": True}, 2: {"none": "other_lecture"},
                               3: {"ids": ["id5"], "partial": False}})

    def test_a_fenced_answer_with_trailing_commas_and_chatter_is_read(self):
        text = 'Here you go:\n```json\n{"q": 1, "lines": ["48.1"]},\n{"q": 2, "none": "question_unclear"}\n```\nDone.'
        got, errors = gemini_run.pointer_answers(text, 2, self.LABELS)
        self.assertEqual((sorted(got), errors), ([1, 2], []))

    def test_a_missing_question_is_an_error_and_the_rest_is_kept(self):
        got, errors = self.read([{"q": 1, "lines": ["48.1"]}, {"q": 3, "lines": ["48.3"]}], 3)
        self.assertEqual(sorted(got), [1, 3])
        self.assertEqual(len(errors), 1)
        self.assertIn("1 questions unanswered", errors[0])
        self.assertIn("[2]", errors[0])

    def test_an_unknown_label_refuses_that_question_only(self):
        got, errors = self.read([{"q": 1, "lines": ["48.1", "99.4"]}, {"q": 2, "lines": ["48.2"]}], 2)
        self.assertEqual(sorted(got), [2])
        self.assertTrue(any("Q1" in e and "99.4" in e for e in errors))

    def test_more_than_twelve_lines_no_lines_and_a_made_up_reason_are_refused(self):
        got, errors = self.read([{"q": 1, "lines": [f"48.{n}" for n in range(1, 14)]}, {"q": 2, "lines": []},
                                 {"q": 3, "none": "not_sure"}, {"q": 4, "lines": [f"48.{n}" for n in range(1, 13)]}], 4)
        self.assertEqual(sorted(got), [4])
        self.assertEqual(len(got[4]["ids"]), 12)
        self.assertTrue(any("Q1: more than 12 lines" in e for e in errors))
        self.assertTrue(any("Q2: no lines" in e for e in errors))
        self.assertTrue(any("Q3: none must be one of" in e for e in errors))

    def test_a_question_number_outside_the_call_and_broken_lines_are_dropped(self):
        got, errors = self.read([{"q": 1, "lines": ["48.1"]}, {"q": 7, "lines": ["48.2"]}, '{"q": "x", "lines": []}',
                                 "{not json", {"lines": ["48.3"]}], 1)
        self.assertEqual((sorted(got), errors), ([1], []))


class TestBoundsSpans(unittest.TestCase):
    SECS = [{"i0": n * 10, "i1": n * 10 + 9} for n in range(10)]
    SCOPE = [2, 3, 4, 5, 6, 7]

    def read(self, answer):
        return gemini_run.bounds_spans(answer if isinstance(answer, str) else json.dumps(answer), self.SCOPE, self.SECS)

    def test_sections_that_follow_each_other_make_one_run(self):
        self.assertEqual(self.read({"sections": [4, 3, 5, 3], "note": "x"}), ([(30, 59)], []))

    def test_a_skip_makes_two_runs(self):
        self.assertEqual(self.read('```json\n{"sections": ["3", 4, 7]}\n```'), ([(30, 49), (70, 79)], []))

    def test_a_section_outside_the_ones_shown_refuses_the_answer(self):
        spans, errors = self.read({"sections": [3, 8]})
        self.assertEqual(spans, [])
        self.assertIn("[8]", errors[0])

    def test_no_sections_and_a_broken_answer_are_refused(self):
        self.assertEqual(self.read({"sections": []}), ([], ["no sections named"]))
        for bad in ("he starts at pain", '{"note": "x"}', '{"sections": ["two"]}', '{"sections": 4}', "[3, 4]"):
            spans, errors = self.read(bad)
            self.assertEqual(spans, [], bad)
            self.assertIn("not the JSON asked for", errors[0], bad)


class TestRuns(unittest.TestCase):
    def test_gaps_of_up_to_two_sections_are_bridged(self):
        self.assertEqual(placement._runs([10, 3, 1, 2, 6]), [(1, 6), (10, 10)])
        self.assertEqual(placement._runs([1, 4, 8]), [(1, 4), (8, 8)])
        self.assertEqual(placement._runs([5]), [(5, 5)])
        self.assertEqual(placement._runs([]), [])


class TestRefresh(LedgerCase):
    def card(self, cid="bound:l1", payload=None, title="t"):
        return {"id": cid, "kind": "bound", "title": title, "detail": "d", "options": ["Use", "Keep"],
                "payload": payload or {"lecture": "l1", "pages": [[1, 2]]}}

    def refresh(self, *cards):
        with mock.patch.object(decisions, "cards", return_value=list(cards)):
            return decisions.refresh(M, self.db)

    def row(self, cid="bound:l1"):
        return self.db.execute("SELECT * FROM decisions WHERE id=?", (cid,)).fetchone()

    def answer(self, cid="bound:l1"):
        self.db.execute("UPDATE decisions SET state='done', answer='[0, null]' WHERE id=?", (cid,))

    def test_a_new_card_is_open_with_its_payload_read_back(self):
        got = self.refresh(self.card())
        self.assertEqual([(c["id"], c["options"], c["payload"]["lecture"]) for c in got], [("bound:l1", ["Use", "Keep"], "l1")])

    def test_an_answered_card_stays_answered_while_its_facts_hold(self):
        self.refresh(self.card())
        self.answer()
        self.assertEqual(self.refresh(self.card(title="new words, same facts")), [])
        self.assertEqual((self.row()["state"], self.row()["answer"], self.row()["title"]), ("done", "[0, null]", "new words, same facts"))

    def test_an_answered_card_returns_when_its_payload_changes(self):
        self.refresh(self.card())
        self.answer()
        got = self.refresh(self.card(payload={"lecture": "l1", "pages": [[1, 3]]}))
        self.assertEqual([c["id"] for c in got], ["bound:l1"])
        self.assertEqual((self.row()["state"], self.row()["answer"]), ("open", None))

    def test_an_open_card_whose_reason_is_gone_closes_and_reopens_if_it_comes_back(self):
        self.refresh(self.card(), self.card("bound:l2"))
        self.assertEqual([c["id"] for c in self.refresh(self.card())], ["bound:l1"])
        self.assertEqual(self.row("bound:l2")["state"], "gone")
        self.assertEqual(sorted(c["id"] for c in self.refresh(self.card(), self.card("bound:l2"))), ["bound:l1", "bound:l2"])

    def test_an_answered_card_whose_reason_is_gone_keeps_its_answer(self):
        self.refresh(self.card())
        self.answer()
        self.refresh()
        self.assertEqual(self.row()["state"], "done")

    def test_cards_come_in_the_screen_order(self):
        cards = [{**self.card("keys"), "kind": "open"}, {**self.card("spot:x"), "kind": "review"}, self.card(),
                 {**self.card("bounds_bulk"), "kind": "bounds_bulk"}, {**self.card("runner"), "kind": "runner"}]
        self.assertEqual([c["kind"] for c in self.refresh(*cards)], ["runner", "bounds_bulk", "bound", "review", "open"])


class TestRunnerHealth(unittest.TestCase):
    def web(self, rows):
        run = mock.Mock(stdout=json.dumps(rows))
        with mock.patch.object(runners.subprocess, "run", return_value=run), \
                mock.patch.dict(runners._CACHE, {"at": 0, "web": None}):
            return runners.web()

    def test_a_dead_login_is_not_up_even_when_gweb_calls_it_usable(self):
        w = self.web([{"slot": s, "usable": True, "state": "READY", "cause": "cookie_dead", "used_5h": 10} for s in "ab"])
        self.assertEqual((w["up"], w["usable"], w["thinking"]), (False, [], []))
        self.assertIn("export the cookies again", w["note"])

    def test_live_accounts_are_up_and_a_full_one_does_no_thinking(self):
        w = self.web([{"slot": "a", "usable": True, "used_5h": 10}, {"slot": "b", "usable": True, "used_5h": 95},
                      {"slot": "c", "usable": True, "cause": "cookie_dead"}, {"slot": "d", "usable": False}])
        self.assertEqual((w["up"], w["usable"], w["thinking"], w["note"]), (True, ["a", "b"], ["a"], "2 of 4 accounts usable"))

    def test_a_failed_status_call_is_down(self):
        with mock.patch.object(runners.subprocess, "run", side_effect=OSError), \
                mock.patch.dict(runners._CACHE, {"at": 0, "web": None}):
            w = runners.web()
        self.assertEqual((w["up"], w["note"]), (False, "gweb status failed: OSError"))


class TestOwnerAliases(unittest.TestCase):
    """The "Set site doctor" card: the answer is a rule in the ledger, and doctors_folder.ALIASES takes it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "ledger.db"
        for p in (mock.patch.object(ledger, "DB", self.path), mock.patch.dict(doctors_folder.ALIASES)):
            p.start()
            self.addCleanup(p.stop)
        db = ledger.connect()
        db.execute("INSERT INTO decisions(id, kind, title, detail, options, payload, state) VALUES"
                   "('doctor:newdoc', 'doctor', 't', 'd', '[]', '{\"key\": \"newdoc\"}', 'open')")
        db.commit()
        db.close()

    def card(self):
        db = ledger.connect()
        r = db.execute("SELECT state FROM decisions WHERE id='doctor:newdoc'").fetchone()
        db.close()
        return r["state"]

    def test_the_answer_becomes_a_rule_for_this_process_and_the_next(self):
        self.assertEqual(doctors_folder.owner_aliases(self.path), {})
        got = decisions.answer("doctor:newdoc", 0, "  dr-new-doc-anat ")
        self.assertTrue(got.get("done"))
        self.assertEqual(self.card(), "done")
        self.assertEqual(doctors_folder.ALIASES["newdoc"], "dr-new-doc-anat")            # the running page
        self.assertEqual(doctors_folder.owner_aliases(self.path), {"newdoc": "dr-new-doc-anat"})  # a new process
        self.assertEqual(doctors_folder.match_doctor("Newdoc (auto)", []), "dr-new-doc-anat")

    def test_an_empty_answer_changes_nothing(self):
        self.assertIn("error", decisions.answer("doctor:newdoc", 0, "  "))
        self.assertEqual(self.card(), "open")
        self.assertNotIn("newdoc", doctors_folder.ALIASES)
        self.assertEqual(doctors_folder.owner_aliases(self.path), {})

    def test_keep_held_writes_no_rule(self):
        self.assertTrue(decisions.answer("doctor:newdoc", 1).get("done"))
        self.assertEqual((self.card(), doctors_folder.owner_aliases(self.path)), ("skipped", {}))

    def test_no_ledger_file_or_an_old_one_without_rules_gives_nothing(self):
        import sqlite3
        self.assertEqual(doctors_folder.owner_aliases(Path(self.tmp.name) / "none.db"), {})
        self.assertFalse((Path(self.tmp.name) / "none.db").exists())
        old = Path(self.tmp.name) / "old.db"
        con = sqlite3.connect(old)
        con.execute("CREATE TABLE links(x)")
        con.commit()
        con.close()
        self.assertEqual(doctors_folder.owner_aliases(old), {})


class TestApply(unittest.TestCase):
    """placement.apply on a made-up module: the place is cut at exact lines, and a revision follows what it covers."""
    LINES = [{"id": f"L{i}", "page": 1 + i // 4, "n": i % 4} for i in range(12)]   # 3 pages of 4 lines

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        (t / "modules" / M).mkdir(parents=True)
        (t / "modules" / M / "lines.jsonl").write_text("\n".join(json.dumps(x) for x in self.LINES) + "\n", encoding="utf-8")
        for p in (mock.patch.object(lectures, "LECTURES", t / "lectures"), mock.patch.object(ledger, "ROOT", t)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        lectures.save({"id": "l1", "module": M, "title": "one", "kind": "lecture", "placed_by": "agent",
                       "ranges": [{"from": "L0", "to": "L7", "pages": [1, 2]}]})
        lectures.save({"id": "l2", "module": M, "title": "two", "kind": "lecture", "placed_by": "agent",
                       "ranges": [{"from": "L4", "to": "L11", "pages": [2, 3]}]})
        lectures.save({"id": "r1", "module": M, "title": "rev", "kind": "revision", "covers": ["l1"]})

    def test_the_place_is_cut_at_the_lines_and_marked_owner(self):
        self.assertEqual(placement.apply("l1", [[0, 5]]), [[1, 2]])
        meta = lectures.load("l1")
        self.assertEqual(meta["ranges"], [{"from": "L0", "to": "L5", "pages": [1, 2], "cut": True}])
        self.assertEqual((meta["placed_by"], meta["pdf_pages"]), ("owner", [1, 2]))

    def test_two_lessons_split_one_page_after_the_cut(self):
        both = ledger.lesson_ids(M)
        self.assertEqual(both["l1"] & both["l2"], {"L4", "L5", "L6", "L7"})    # whole pages: page 2 is in both
        placement.apply("l1", [[0, 5]])
        placement.apply("l2", [[6, 11]])
        both = ledger.lesson_ids(M)
        self.assertEqual(both["l1"] & both["l2"], set())
        self.assertEqual(both["l1"] | both["l2"], {x["id"] for x in self.LINES})

    def test_a_revision_follows_the_lecture_it_covers(self):
        placement.apply("l1", [[0, 2], [8, 9]])
        rev = lectures.load("r1")
        self.assertEqual(rev["ranges"], lectures.load("l1")["ranges"])
        self.assertEqual((rev["placed_by"], rev["pdf_pages"]), ("covers", [1, 3]))
        self.assertEqual(ledger.lesson_ids(M, kinds=("revision",))["r1"], {"L0", "L1", "L2", "L8", "L9"})

    def test_no_place_is_refused(self):
        with self.assertRaises(ValueError):
            placement.apply("l1", [])
        self.assertEqual(lectures.load("l1")["placed_by"], "agent")


if __name__ == "__main__":
    unittest.main()

"""Phase 2 segmentation (rebuilt 2026-11-18): per-paragraph answers from two Gemini web readers."""
import unittest
from unittest import mock

import numpy as np

from spine.seg import prior, scope, segment


class Paragraphs(unittest.TestCase):
    def test_stamps_and_joined_lines(self):
        p = prior.paragraphs("[00:00] one\nmore\n[01:05] two\n[1:02:03] three\n")
        self.assertEqual([(x["n"], x["start"], x["text"]) for x in p],
                         [(1, 0, "one more"), (2, 65, "two"), (3, 3723, "three")])
        self.assertEqual(prior.stamp(3723), "1:02:03")


class PriorAndScope(unittest.TestCase):
    def test_monotone_and_none(self):
        m = np.array([[1, 0, 0, 0], [0, 0, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0], [0, 0, 0, 1]], dtype=float)
        pts = prior.path(m)
        self.assertEqual(pts[1], None)
        hits = [p for p in pts if p is not None]
        self.assertEqual(hits, sorted(hits))
        self.assertEqual((pts[0], pts[4]), (0, 3))

    def test_trimmed_window(self):
        self.assertEqual(scope.trimmed([50, 51, 52, 53, 54, 55, 56, 57, 58, 900], 1000, margin=10, trim=0.1),
                         (41, 68))
        self.assertIsNone(scope.trimmed([], 10))

    def test_arabic_script_term_reaches_the_book_word(self):
        sents = [{"text": "The thalamus relays sensation", "ctx": []}, {"text": "Cerebellum controls balance", "ctx": []}]
        m = prior.scores([{"n": 1, "start": 0, "text": "الثالاموس ده مهم"}], sents)
        self.assertEqual(int(np.argmax(m[0])), 0)

    def test_a_missing_lecture_record_is_empty_not_a_crash(self):
        self.assertEqual(scope.lecture("no-such-lecture-xyz"), {})

    def test_a_covers_id_with_no_record_does_not_stop_the_slice(self):
        from unittest import mock
        lec = {"doctor": "nobody", "covers": ["ghost-1"], "ranges": []}
        with mock.patch.object(scope, "lecture", lambda lid: lec if lid == "L1" else {}):
            self.assertIsNone(scope.pick("L1", "year2-cns", [], {}))

    def test_prepare_refuses_an_empty_slice(self):
        from unittest import mock
        from spine.seg import flow
        with mock.patch.object(flow, "raw_of", lambda lid: "[00:00] talk\n[00:30] more\n"), \
                mock.patch.object(scope, "pick", lambda *a, **k: {"book": "b", "sents": [], "lo": 0, "hi": -1,
                                                                  "how": "x"}):
            self.assertIsNone(flow.prepare("L1", "year2-cns", {}))


class Task(unittest.TestCase):
    def test_render_numbers_the_slice_from_b1_and_names_the_last_paragraph(self):
        sl = [{"id": "a", "text": "first", "kind": "sentence"}, {"id": "b", "text": "Second", "kind": "heading"}]
        paras = [{"n": 1, "start": 0, "text": "x"}, {"n": 2, "start": 65, "text": "y"}]
        task = segment.render(paras, sl)
        self.assertIn("\nB1 first\nB2 ## Second\n", task)
        self.assertIn("P1 [00:00] x\nP2 [01:05] y\n", task)
        self.assertIn("from P1 to P2", task)

    def test_the_prompt_sets_no_length_or_order_rule(self):
        # owner 2026-11-18: an AI cannot keep to a length rule; a doctor who goes back gets the earlier lines
        self.assertNotIn("12 paragraphs", segment.PROMPT)
        self.assertNotIn("never smaller", segment.PROMPT)
        self.assertIn("goes back", segment.PROMPT)


class Parse(unittest.TestCase):
    def test_single_ranges_runs_and_none(self):
        per, notes = segment.parse("P1 = B3\nP2-P3 = B4-B6\nP4 = NONE\nP5 = B2-B2", 5, 10)
        self.assertEqual(per, [[[3, 3]], [[4, 6]], [[4, 6]], None, [[2, 2]]])     # going back (B2 after B6) is kept
        self.assertEqual(notes["missing"], 0)

    def test_formatting_is_folded_never_meaning(self):
        text = "Here are the lines:\n**P1 = B3**\n- P2 – P3 = B4 – B6.\n3) P4: NONE\n`P5 → B7`\nP٦ = B٨"
        per, notes = segment.parse(text, 6, 10)
        self.assertEqual(per, [[[3, 3]], [[4, 6]], [[4, 6]], None, [[7, 7]], [[8, 8]]])

    def test_a_paragraph_answered_twice_keeps_its_first_answer(self):
        per, notes = segment.parse("P1-P3 = B1-B2\nP3 = B9", 3, 10)
        self.assertEqual(per[2], [[1, 2]])
        self.assertEqual(notes["twice"], 1)

    def test_several_places_for_one_paragraph_are_kept(self):
        # v4 pilot (cns-013 B, cns-021 B, cns-038 B): Gemini names several places; these were "not answered" before
        text = ("P6-P7 = B25, B34\nP8-P14 = B24-B25, B33-B34\nP3 = B26-B29, B37, B44\nP1 = B3 ، B5\n"
                "P2 = B9, B9")
        per, notes = segment.parse(text, 14, 50)
        self.assertEqual(per[5], [[25, 25], [34, 34]])
        self.assertEqual(per[7], [[24, 25], [33, 34]])
        self.assertEqual(per[2], [[26, 29], [37, 37], [44, 44]])
        self.assertEqual(per[0], [[3, 3], [5, 5]])              # Arabic comma
        self.assertEqual(per[1], [[9, 9]])                      # a line named twice counts once
        self.assertEqual(notes["missing"], 2)                   # only P4 and P5 not given
        self.assertEqual(segment.problems(*segment.parse(text + "\nP4-P5 = NONE", 14, 50)), [])

    def test_numbers_outside_are_counted_and_clipped(self):
        per, notes = segment.parse("P1 = B8-B14\nP2 = B1\nP3 = B1", 2, 10)
        self.assertEqual(per, [[[8, 10]], [[1, 1]]])
        self.assertEqual((notes["outside_book"], notes["outside_talk"]), (1, 1))


class Problems(unittest.TestCase):
    def check(self, text, n=20, nb=50):
        return segment.problems(*segment.parse(text, n, nb))

    def test_a_whole_answer_is_usable(self):
        self.assertEqual(self.check("P1-P10 = B1-B5\nP11-P20 = B6-B9"), [])

    def test_missing_paragraphs_make_it_unusable(self):
        self.assertTrue(any("not answered" in p for p in self.check("P1-P10 = B1-B5")))
        self.assertEqual(self.check("P1-P19 = B1-B5"), [])                     # one missing of 20 is fine

    def test_mostly_none_is_unusable(self):
        self.assertTrue(any("NONE" in p for p in self.check("P1-P15 = NONE\nP16-P20 = B1")))

    def test_prose_only_is_unusable(self):
        self.assertIn("no answer line", self.check("I could not find the attachment."))

    def test_a_line_outside_the_book_is_unusable(self):
        self.assertTrue(any("outside" in p for p in self.check("P1-P20 = B40-B60")))


class Agreement(unittest.TestCase):
    def test_overlap_near_and_none(self):
        self.assertTrue(segment.same([[58, 64]], [[58, 77]]))       # nested ranges agree (cns-015)
        self.assertTrue(segment.same([[10, 10]], [[14, 14]]))
        self.assertFalse(segment.same([[10, 10]], [[30, 30]]))
        self.assertTrue(segment.same(None, None))
        self.assertFalse(segment.same(None, [[1, 1]]))

    def test_one_shared_place_of_several_agrees(self):
        self.assertTrue(segment.same([[25, 25], [34, 34]], [[33, 34]]))
        self.assertFalse(segment.same([[2, 3], [60, 61]], [[30, 31]]))

    def test_agreed_keeps_a_and_marks_the_rest(self):
        per, share = segment.agreed([[[1, 2]], [[3, 3]], None, [[40, 40]]], [[[2, 2]], [[3, 4]], None, [[3, 3]]])
        self.assertEqual(per, [[[1, 2]], [[3, 3]], None, "disputed"])
        self.assertEqual(share, 0.75)

    def test_segments_merge_runs(self):
        segs = segment.segments([[[1, 2]], [[1, 2]], None, "disputed", "disputed", [[5, 5]]])
        self.assertEqual(segs, [{"p": [1, 2], "b": [[1, 2]]}, {"p": [3, 3], "b": None},
                                {"p": [4, 5], "b": None, "flag": "disputed"}, {"p": [6, 6], "b": [[5, 5]]}])

    def test_record_times_and_handout(self):
        paras = [{"n": i, "start": 30 * (i - 1), "text": ""} for i in range(1, 5)]
        sents = [{"id": f"s{j}"} for j in range(1, 6)]
        rows = segment.record([{"p": [1, 2], "b": [[2, 3]]}, {"p": [3, 4], "b": None}], paras, sents,
                              {"s2": ["h1"], "s3": ["h1", "h2"]}, "geminiA+geminiB", 0.9)
        self.assertEqual(rows[0], {"n": 1, "p": [1, 2], "start": 0, "end": 60, "by": "geminiA+geminiB",
                                   "book": ["s2", "s3"], "handout": ["h1", "h2"], "conf": 0.9})
        self.assertEqual((rows[1]["book"], rows[1]["end"]), (None, None))

    def test_record_several_places_reach_only_their_lines(self):
        paras = [{"n": 1, "start": 0, "text": ""}]
        sents = [{"id": f"s{j}"} for j in range(1, 11)]
        rows = segment.record([{"p": [1, 1], "b": [[2, 2], [8, 9]]}], paras, sents,
                              {"s2": ["h1"], "s5": ["h5"], "s9": ["h9"]}, "x")
        self.assertEqual(rows[0]["book"], ["s2", "s9"])
        self.assertEqual(rows[0]["parts"], [["s2", "s2"], ["s8", "s9"]])
        self.assertEqual(rows[0]["handout"], ["h1", "h9"])           # s5 sits in the gap: not reached


class Flow(unittest.TestCase):
    """make_jobs -> answers -> dry/collect in a temp folder."""

    GOOD = "P1-P10 = B1-B5\nP11-P20 = B6-B12\n"

    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from spine import compat
        from spine.seg import flow
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "root"
        self.root.mkdir()
        self.book = [{"id": f"s{j}", "text": f"book line {j}", "kind": "sentence", "page": 1} for j in range(1, 61)]
        self.paras = [{"n": i, "start": 30 * (i - 1), "text": f"talk {i}"} for i in range(1, 21)]
        self.slice = self.book[:]
        self.patches = [
            mock.patch.object(flow, "ROOT", self.root), mock.patch.object(flow, "JOBS", self.tmp / "jobs"),
            mock.patch.object(scope, "home", lambda lid: self.root / "lectures" / lid),
            mock.patch.object(scope, "edges", lambda module, book: {}),
            mock.patch.object(compat, "lecture_files", lambda *a, **k: None),
            mock.patch.object(compat, "_handout", lambda module: ({}, {})),
            mock.patch.object(flow, "prepare", lambda lid, module="year2-cns", cache=None: {
                "paras": self.paras, "slice": self.slice,
                "scope": {"book": "bk", "how": "test", "lo": 0, "hi": len(self.slice) - 1}}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def answer(self, lid, r, text):
        from spine.seg import flow
        (flow.job_dir(lid, r) / "answer.txt").write_text(text, encoding="utf-8")

    def out(self, lid):
        return self.root / "lectures" / lid / "segments.jsonl"

    def test_two_agreeing_readers_are_accepted_and_written(self):
        from spine import read_jsonl
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self.answer("L1", "A", self.GOOD)
        self.answer("L1", "B", "P1-P10 = B2-B5\nP11-P20 = B7-B12\n")
        self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"accepted": 1})
        rows = read_jsonl(self.out("L1"))
        self.assertEqual([(r["p"], r["book"]) for r in rows], [([1, 10], ["s1", "s5"]), ([11, 20], ["s6", "s12"])])
        self.assertEqual(rows[0]["by"], "fleetA+fleetB")         # no reader.json in this test

    def test_partial_disagreement_is_written_as_disputed(self):
        from spine import read_jsonl
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self.answer("L1", "A", self.GOOD)
        self.answer("L1", "B", "P1-P10 = B1-B5\nP11-P16 = B6-B12\nP17-P20 = B50\n")
        self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"accepted": 1})
        rows = read_jsonl(self.out("L1"))
        self.assertEqual(rows[-1]["p"], [17, 20])
        self.assertEqual((rows[-1]["book"], rows[-1]["flag"]), (None, "disputed"))

    def test_disagreement_is_disputed_and_drops_old_output(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self.answer("L1", "A", self.GOOD)
        self.answer("L1", "B", self.GOOD)
        flow.collect(["L1"], say=lambda *a: None)
        self.answer("L1", "B", "P1-P20 = B40-B50\n")
        self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"disputed": 1})
        self.assertFalse(self.out("L1").exists())

    def test_one_unusable_answer_is_rejected_and_none_is_waiting(self):
        from spine.seg import flow
        flow.make_jobs(["L1", "L2"], say=lambda *a: None)
        self.answer("L1", "A", self.GOOD)
        self.answer("L1", "B", "sorry")
        self.answer("L2", "A", self.GOOD)
        self.assertEqual(flow.dry(["L1", "L2"], say=lambda *a: None), {"rejected": 1, "waiting": 1})
        self.assertFalse((flow.JOBS / "L1" / "state.json").exists())     # dry writes nothing

    def test_a_changed_slice_makes_the_job_stale_and_remaking_clears_it(self):
        from spine.seg import flow
        flow.make_jobs(["L1"], say=lambda *a: None)
        self.answer("L1", "A", self.GOOD)
        self.answer("L1", "B", self.GOOD)
        self.assertEqual(flow.make_jobs(["L1"], say=lambda *a: None), 0)   # same task keeps its answers
        self.slice = self.book[10:]
        self.assertEqual(flow.collect(["L1"], say=lambda *a: None), {"stale": 1})
        self.assertEqual(flow.make_jobs(["L1"], say=lambda *a: None), 2)
        self.assertFalse(flow.answered(flow.job_dir("L1", "A")))

    def test_one_broken_lecture_does_not_stop_the_batch(self):
        from unittest import mock
        from spine.seg import flow
        flow.make_jobs(["L1", "L2"], say=lambda *a: None)
        for lid in ("L1", "L2"):
            self.answer(lid, "A", self.GOOD)
            self.answer(lid, "B", self.GOOD)
        real = flow._judge_lecture

        def judge(lid, module, cache):
            if lid == "L1":
                raise RuntimeError("boom")
            return real(lid, module, cache)
        with mock.patch.object(flow, "_judge_lecture", judge):
            self.assertEqual(flow.collect(["L1", "L2"], say=lambda *a: None), {"error": 1, "accepted": 1})


class GeminiReader(unittest.TestCase):
    """The reader (owner 2026-11-18): Gemini web, model 4 Hydrogen, two separate chats per lecture."""

    GOOD = "P1-P5 = B1-B3\n"

    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from spine.seg import flow
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(flow, "JOBS", self.tmp / "jobs")
        self.patch.start()
        for lid in ("L1", "L2"):
            for r in ("A", "B"):
                d = self.tmp / "jobs" / lid / r
                d.mkdir(parents=True)
                (d / "task.txt").write_text("the prompt\nBOOK\nB1 x\n\nTRANSCRIPT\nP1 [00:00] y\n", encoding="utf-8")

    def tearDown(self):
        self.patch.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake(self, *replies):
        self.seen, replies = [], list(replies)

        def ask(prompt, model=None, attach=(), wait=None):
            self.seen.append({"prompt": prompt, "model": model, "attach": list(attach)})
            text = replies.pop(0)
            return text, ({"account": "acct1"} if text else {"error": "no account ready"})
        return ask

    def test_an_answer_is_written_with_its_reader(self):
        from spine import read_json
        from spine.seg import flow
        d = self.tmp / "jobs" / "L1" / "A"
        self.assertEqual(flow.ask_gemini(d, ask=self.fake(self.GOOD)), "answered")
        self.assertEqual((d / "answer.txt").read_text(encoding="utf-8"), self.GOOD)
        self.assertEqual(flow.answered_by(d), "gemini")
        self.assertEqual(read_json(d / "browser.json")["account"], "acct1")
        call = self.seen[0]
        self.assertEqual((call["model"], call["attach"]), ("hydrogen", [str(d / "task.txt")]))
        self.assertTrue(call["prompt"].startswith("the prompt"))
        self.assertNotIn("P1 [00:00]", call["prompt"])            # the blocks come in the attached file

    def test_a_reply_without_answer_lines_is_asked_once_more(self):
        from spine.seg import flow
        d = self.tmp / "jobs" / "L1" / "A"
        self.assertEqual(flow.ask_gemini(d, ask=self.fake("the file was not attached", self.GOOD)), "answered")
        self.assertEqual(len(self.seen), 2)
        self.assertEqual(flow.ask_gemini(self.tmp / "jobs" / "L1" / "B", ask=self.fake("no", None)), "failed")
        self.assertTrue((self.tmp / "jobs" / "L1" / "B" / "reply_failed.txt").exists())

    def test_run_asks_each_unanswered_job_once_and_limit_zero_asks_nothing(self):
        from unittest import mock
        from spine.seg import flow
        asked = []
        with mock.patch.object(flow, "ask_gemini", lambda d: asked.append(d) or "answered"):
            self.assertEqual(flow.run(["L1"], say=lambda *a: None, limit=0), {})
            self.assertEqual(flow.run(["L1"], say=lambda *a: None), {"answered": 2})
        self.assertEqual(len(asked), 2)

    def test_every_account_capped_writes_nothing_and_run_can_wait(self):
        from unittest import mock
        from spine.seg import flow
        d = self.tmp / "jobs" / "L1" / "A"
        capped = lambda prompt, model=None, attach=(), wait=None: (None, {"error": "capped", "until": 123.0})
        self.assertEqual(flow.ask_gemini(d, ask=capped), "capped")
        self.assertFalse((d / "reply_failed.txt").exists())
        self.assertEqual(flow.CAPPED["until"], 123.0)
        mixed = lambda prompt, model=None, attach=(), wait=None: (None, {"error": "no account ready. acct3: capped; "
                                                                       "acct1: Locator.click: Timeout 10000ms exceeded."})
        self.assertEqual(flow.ask_gemini(d, ask=mixed), "capped")       # waits too, instead of failing the job
        self.assertFalse((d / "reply_failed.txt").exists())
        replies, slept = ["capped", "answered", "answered"], []
        with mock.patch.object(flow, "ask_gemini", lambda d: replies.pop(0)):
            self.assertEqual(flow.run(["L1"], say=lambda *a: None, wait_caps=True, sleep=slept.append),
                             {"answered": 2})
        self.assertEqual(len(slept), 1)
        with mock.patch.object(flow, "ask_gemini", lambda d: "capped"):
            self.assertEqual(flow.run(["L1"], say=lambda *a: None), {"capped": 2})


class Renewal(unittest.TestCase):
    def test_capped_option_text_gives_the_renewal(self):
        from datetime import datetime
        import gemini_browser as g
        now = datetime(2026, 11, 18, 4, 31)
        at = lambda t: datetime.fromtimestamp(g.renews_at(t, now))
        self.assertEqual(at("يتم تجديد سقف ‎١٨ "
                            "نوفمبر، ٤:٥٣ ص"),
                         datetime(2026, 11, 18, 4, 53))
        self.assertEqual(at("Usage limit resets Nov 18, 7:12 PM"), datetime(2026, 11, 18, 19, 12))
        self.assertIsNone(g.renews_at("‎3.5 Flash-Lite", now))


class CapFallback(unittest.TestCase):
    """Owner 2026-11-20: a capped account answers with its free model (Flash-Lite) until the renewal."""

    def test_known_cap_uses_flash_lite(self):
        import gemini_browser as g
        calls = []
        with mock.patch.object(g, "capped_until", lambda n, m: 9e12 if m == "hydrogen" else None), \
                mock.patch.object(g, "ask_on", lambda pw, n, p, a, w, m: calls.append(m) or "ok"):
            self.assertEqual(g.ask_on_fallback(None, 1, "p", model="hydrogen"), ("ok", "Flash-Lite"))
        self.assertEqual(calls, ["flash-lite"])

    def test_cap_found_now_retries_with_flash_lite(self):
        import gemini_browser as g
        calls = []

        def ask_on(pw, n, p, a, w, m):
            calls.append(m)
            if m == "hydrogen":
                raise g.Capped(n, "Hydrogen", 9e9)
            return "ok"
        with mock.patch.object(g, "capped_until", lambda n, m: None), mock.patch.object(g, "ask_on", ask_on):
            self.assertEqual(g.ask_on_fallback(None, 2, "p", model="hydrogen"), ("ok", "Flash-Lite"))
        self.assertEqual(calls, ["hydrogen", "flash-lite"])

    def test_ready_account_keeps_hydrogen(self):
        import gemini_browser as g
        with mock.patch.object(g, "capped_until", lambda n, m: None), \
                mock.patch.object(g, "ask_on", lambda pw, n, p, a, w, m: m):
            self.assertEqual(g.ask_on_fallback(None, 3, "p", model="hydrogen"), ("hydrogen", "Hydrogen"))


class Widen(unittest.TestCase):
    """A rejection for a missed slice steps the lecture up the ladder: whole book, then the handout, then the owner."""
    def setUp(self):
        import tempfile
        from pathlib import Path
        from spine.seg import flow
        self.tmp = tempfile.TemporaryDirectory()
        self.flow = flow
        self.patches = [mock.patch.object(flow, "JOBS", Path(self.tmp.name)),
                        mock.patch.object(scope, "WIDEN", Path(self.tmp.name)),
                        mock.patch.object(scope, "lecture", lambda lid: {"doctor": "dr-x", "ranges": [{"from": "a", "to": "b"}]}),
                        mock.patch.object(scope, "doctor_books", lambda module: {"dr-x": "x-book"})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def missed(self, fp):
        return {"state": "rejected", "fp": fp, "readers": {"A": ["NONE for 90% of paragraphs"], "B": ["NONE for 85% of paragraphs"]}}

    def test_the_ladder_steps_once_per_answer_pair_and_ends_with_the_owner(self):
        f = self.flow
        self.assertEqual(f.widen("L1", self.missed("fp1")), 1)
        self.assertIsNone(f.widen("L1", self.missed("fp1")))            # the same answers never step twice
        self.assertEqual(scope.widen_step("L1"), 1)
        self.assertEqual(f.widen("L1", self.missed("fp2")), 2)
        self.assertEqual(f.widen("L1", self.missed("fp3")), 3)          # the handout prior
        self.assertIsNone(f.widen("L1", self.missed("fp4")))            # top of the ladder: the owner's card
        from pathlib import Path
        (Path(self.tmp.name) / "L1" / "A").mkdir(parents=True)
        (Path(self.tmp.name) / "L1" / "A" / "meta.json").write_text('{"lecture": "L1"}')
        self.assertEqual(f.for_owner(), ["L1"])

    def test_one_reader_with_answers_is_not_a_missed_slice(self):
        st = {"state": "rejected", "fp": "x", "readers": {"A": ["NONE for 90% of paragraphs"], "B": []}}
        self.assertIsNone(self.flow.widen("L2", st))

    def test_step_one_reads_the_whole_book_and_step_two_the_handout(self):
        sents = [{"id": f"s{i}", "text": "t", "kind": "sentence"} for i in range(100)]
        cache = {"x-book": {"sents": sents, "links": {}, "index": []}}
        self.flow.widen("L3", self.missed("a"))
        got = scope.pick("L3", "year2-cns", None, cache)
        self.assertEqual((got["book"], got["lo"], got["hi"]), ("x-book", 0, 99))
        self.flow.widen("L3", self.missed("b"))
        with mock.patch.object(scope, "handout_target", lambda lec, module, cache, margin: {"book": None, "margin": margin}):
            self.assertEqual(scope.pick("L3", "year2-cns", None, cache), {"book": None, "margin": scope.WIDE})

    def test_the_top_step_reads_the_handout_window_the_lectures_words_point_at(self):
        for fp in "abc":
            self.flow.widen("L4", self.missed(fp))
        sents = ([{"id": f"h{i}", "text": "Medial lemniscus of the midbrain", "kind": "fact", "rows": ["r"]} for i in range(40)]
                 + [{"id": f"h{40 + i}", "text": "The frontal lobe and parietal lobe of the cerebrum", "kind": "fact", "rows": ["r"]}
                    for i in range(10)])
        paras = [{"text": "frontal lobe parietal lobe cerebrum"}] * 3
        with mock.patch.object(scope, "HANDOUT_DENSE", 10), mock.patch.object(scope, "MARGIN", 0):
            got = scope.pick("L4", "year2-cns", paras, {"handout_sents": sents, "index": []})
        self.assertEqual((got["target"], got["lo"], got["hi"]), ("handout", 40, 49))

    def test_no_book_and_no_placement_starts_at_the_handout_prior(self):
        with mock.patch.object(scope, "lecture", lambda lid: {"doctor": "dr-none"}),                 mock.patch.object(scope, "handout_prior", lambda paras, module, cache: {"how": "prior"}):
            self.assertEqual(scope.pick("L5", "year2-cns", [{"text": "x"}], {}), {"how": "prior"})
            self.assertEqual(scope.last_step("L5"), 2)


class TalkyAndRetry(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from spine.seg import flow
        self.tmp, self.flow = tempfile.TemporaryDirectory(), flow
        self.p = mock.patch.object(flow, "JOBS", Path(self.tmp.name))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_a_talky_lecture_both_readers_agree_on_is_usable(self):
        a = [None] * 6 + [[(1, 2)]] * 3 + [[(5, 6)]] * 3
        b = [None] * 6 + [[(1, 2)]] * 3 + [[(5, 5)]] * 3
        none = ["NONE for 50% of paragraphs"]
        self.assertTrue(self.flow.talky(a, b, none, []))
        self.assertFalse(self.flow.talky(a, b, none + ["3 answers outside the BOOK lines"], []))
        mostly = [None] * 10 + [[(1, 2)]] * 2
        self.assertFalse(self.flow.talky(mostly, mostly, none, none))          # too much NONE, too few links
        self.assertFalse(self.flow.talky(a, [None] * 6 + [[(90, 95)]] * 6, none, none))   # they link elsewhere

    def test_one_unusable_reader_is_asked_once_more(self):
        d = self.flow.job_dir("L1", "B")
        d.mkdir(parents=True)
        (d / "answer.txt").write_text("P1 = NONE")
        st = {"state": "rejected", "fp": "f1", "readers": {"A": [], "B": ["NONE for 92% of paragraphs"]}}
        self.assertEqual(self.flow.retry("L1", st), "B")
        self.assertFalse((d / "answer.txt").exists())
        self.assertEqual((d / "answer_rejected.txt").read_text(), "P1 = NONE")
        (d / "answer.txt").write_text("P1 = NONE")
        self.assertIsNone(self.flow.retry("L1", st))                           # once per answer pair
        both = {"state": "rejected", "fp": "f2", "readers": {"A": ["x"], "B": ["y"]}}
        self.assertIsNone(self.flow.retry("L1", both))

    def test_two_of_three_readers_decide_a_disputed_paragraph(self):
        from spine.seg import segment
        a = [None, [(1, 2)], [(10, 11)], [(30, 31)]]
        b = [[(5, 6)], None, [(10, 10)], [(60, 61)]]
        c = [[(5, 6)], [(1, 1)], None, [(90, 91)]]
        per, share = segment.agreed3(a, b, c)
        self.assertEqual(per, [[(5, 6)], [(1, 2)], [(10, 11)], "disputed"])
        self.assertEqual(share, 0.75)

    def test_a_disputed_pair_writes_the_third_job_once(self):
        a = self.flow.job_dir("L2", "A")
        a.mkdir(parents=True)
        (a / "task.txt").write_text("task")
        (a / "meta.json").write_text('{"fp": "f1"}')
        self.assertTrue(self.flow.ask_third("L2", {"state": "disputed"}))
        self.assertEqual((self.flow.job_dir("L2", "C") / "task.txt").read_text(), "task")
        self.assertFalse(self.flow.ask_third("L2", {"state": "disputed", "third": "waiting"}))
        self.assertIn(("L2", "C"), [(lid, r) for lid, r, _ in self.flow.todo(["L2"])])


if __name__ == "__main__":
    unittest.main()

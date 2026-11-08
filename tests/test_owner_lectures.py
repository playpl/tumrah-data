"""Owner-named lectures (2026-11-08): naming, placing, the shortlist, lecture-scoped pointers, the owner's picks."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import checks  # noqa: E402
import lectures  # noqa: E402
import page  # noqa: E402
import queue_db  # noqa: E402
import shortlist  # noqa: E402
from flows.common import read_jsonl, write_jsonl  # noqa: E402
from flows.place import PlaceFlow  # noqa: E402


def handout(pages):
    """lines.jsonl rows: {page: [text, ...]}."""
    rows = []
    for p, texts in pages.items():
        for n, t in enumerate(texts, 1):
            rows.append({"id": f"m:h:p{p}:l{n}", "module": "year2-cns", "hash": "h", "page": p, "printed": p,
                         "n": n, "text": t, "figure": None, "bbox": [0, 0, 1, 1]})
    return rows


COMMON = "the nerve cell is part of the system"
LINES = handout({1: [COMMON], 2: [COMMON, "corticospinal tract decussation pyramids"], 3: ["lateral corticospinal tract"],
                 4: [COMMON, "cerebellum vermis flocculus"], 5: [COMMON, "hypothalamus releasing hormones"]})


def bank_q(text, options=("one", "two"), key=0, **kw):
    import merge
    return {"word_key": merge.word_key(text, list(options)), "question": text, "options": list(options), "key": key,
            "sightings": [], "repetition_count": 1, **kw}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.p = mock.patch.object(lectures, "LECTURES", self.root / "lectures")
        self.p.start()
        self.q = queue_db.Queue(self.root / "queue.db")

    def tearDown(self):
        self.q.close()
        self.p.stop()
        self.tmp.cleanup()


class TestNaming(Base):
    def test_ids_count_up_per_module_and_need_title_and_doctor(self):
        self.assertEqual(lectures.create("year2-cns", "Spinal cord", "dr-a")["id"], "cns-001")
        self.assertEqual(lectures.create("year2-cns", "Brain stem", "dr-a")["id"], "cns-002")
        self.assertEqual(lectures.create("year1-musculoskeletal", "Bones", "dr-b")["id"], "musculoskeletal-001")
        with self.assertRaises(ValueError):
            lectures.create("year2-cns", "", "dr-a")
        with self.assertRaises(ValueError):
            lectures.create("year2-cns", "X", " ")

    def test_pages_become_line_id_ranges(self):
        m = lectures.set_ranges(lectures.create("year2-cns", "T", "d"), LINES, [[4, 5], [2, 3]], "owner")
        self.assertEqual(m["ranges"], [{"from": "m:h:p2:l1", "to": "m:h:p3:l1", "pages": [2, 3]},
                                       {"from": "m:h:p4:l1", "to": "m:h:p5:l2", "pages": [4, 5]}])
        self.assertEqual(m["pdf_pages"], [2, 5])
        self.assertEqual(len(lectures.lecture_lines(m, LINES)), 7)

    def test_a_recording_keeps_the_owners_fields(self):
        m = lectures.create("year2-cns", "T", "dr-a")
        m["required"] = [{"word_key": "k"}]
        lectures.save(m)
        with mock.patch.object(lectures, "compress"), mock.patch.object(lectures, "duration", return_value=60.0):
            lectures.add(m["id"], "year2-cns", "T", 16, file=str(self.root / "a.mp3"))
        m = lectures.load(m["id"])
        self.assertEqual((m["required"], m["doctor"], m["duration_s"]), ([{"word_key": "k"}], "dr-a", 60.0))


class TestPlace(Base):
    def test_place_checker(self):
        ok = {"ranges": [{"first_page": 2, "last_page": 3}], "note": "contents page"}
        self.assertEqual(checks.check_place(ok, LINES), [])
        self.assertTrue(checks.check_place({"ranges": []}, LINES))
        self.assertTrue(checks.check_place({**ok, "ranges": [{"first_page": 3, "last_page": 9}]}, LINES))
        self.assertTrue(checks.check_place({**ok, "ranges": [{"first_page": 2, "last_page": 3}, {"first_page": 3, "last_page": 4}]}, LINES))
        self.assertTrue(checks.check_place({**ok, "note": ""}, LINES))

    def test_the_agent_places_but_never_over_the_owner(self):
        m = lectures.create("year2-cns", "T", "d")
        job_dir = self.root / "job"
        (job_dir / "inputs").mkdir(parents=True)
        write_jsonl(job_dir / "inputs" / "lines.jsonl", LINES)
        (job_dir / "place.json").write_text(json.dumps({"ranges": [{"first_page": 2, "last_page": 3}], "note": "n"}))
        job = {"payload": {"lecture": m["id"]}}
        self.assertEqual(PlaceFlow().check(job, job_dir), [])
        self.assertEqual((lectures.load(m["id"])["placed_by"], lectures.page_ranges(lectures.load(m["id"]))), ("agent", [[2, 3]]))
        lectures.set_ranges(lectures.load(m["id"]), LINES, [[4, 5]], "owner")
        PlaceFlow().check(job, job_dir)
        self.assertEqual(lectures.page_ranges(lectures.load(m["id"])), [[4, 5]])


class TestShortlist(Base):
    def test_the_lectures_rare_words_rank_its_questions_first(self):
        terms = shortlist.lecture_terms(LINES, [[2, 3]], {**shortlist.DEFAULTS, "max_df": 0.5})
        self.assertIn("corticospinal", terms)
        self.assertNotIn("nerve", terms)  # on most pages: no weight
        bank = [bank_q("Which nerve cell is in the system?"), bank_q("The corticospinal tract crosses at the pyramids?"),
                bank_q("Vermis of the cerebellum?")]
        ranked = shortlist.rank(bank, terms, "year2-cns")
        self.assertEqual([k for _, k in ranked], [bank[1]["word_key"]])

    def test_the_cap_grows_to_cover_the_owners_questions(self):
        ranked = [(100 - i, f"k{i}") for i in range(50)]
        c = {**shortlist.DEFAULTS, "cap": 10, "max": 100, "floor": 0}
        kept, s = shortlist.cut(ranked, ["k3"], c)
        self.assertEqual((s["cap"], s["grew"], len(kept)), (10, False, 9))  # the owner's own question is not in the 10
        kept, s = shortlist.cut(ranked, ["k3", "k30"], c)
        self.assertEqual((s["cap"], s["grew"], s["owner_within_default_cap"]), (39, True, 1))

    def test_send_puts_the_owners_questions_first_and_never_twice(self):
        bank = [bank_q(f"q{i} corticospinal") for i in range(30)]
        m = lectures.create("year2-cns", "T", "d")
        m["required"] = [{"word_key": bank[29]["word_key"]}]
        lectures.save(m)
        write_jsonl(lectures.folder(m["id"]) / "shortlist.jsonl", [{"word_key": q["word_key"]} for q in bank[:29]])
        out = shortlist.send(m["id"], self.q, bank)
        self.assertEqual((out["questions"], out["jobs"], out["owner_first"]), (30, 2, 1))
        job = self.q.claim("pointers", "work")
        self.assertEqual((job["payload"]["lecture"], job["payload"]["batch"][0]["word_key"]), (m["id"], bank[29]["word_key"]))
        self.assertEqual(shortlist.send(m["id"], self.q, bank)["questions"], 0)


class TestScopedPointers(unittest.TestCase):
    def row(self, **kw):
        return {"qid": "q1", "found": False, "lecture_id": None, "spans": [], "partial": False, "tested_fact": None,
                "reason": "other_lecture", "other_module": None, **kw}

    def test_other_lecture_only_in_a_lecture_job_and_pages_may_be_several_ranges(self):
        batch = [{"qid": "q1", "options": ["a", "b"]}]
        self.assertTrue(checks.check_pointers([self.row()], batch, LINES, {}))
        ref = {"lecture_scope": True, "lectures": [{"lecture_id": "cns-001", "title": "T", "pdf_pages": [[2, 2], [4, 5]]}]}
        self.assertEqual(checks.check_pointers([self.row()], batch, LINES, ref), [])
        span = {"pdf_page": 3, "printed_page": 3, "text": "lateral corticospinal tract", "figure": None, "for_option": None}
        found = self.row(found=True, lecture_id="cns-001", spans=[span], reason=None, tested_fact="tract")
        self.assertTrue(any("outside lecture" in e for e in checks.check_pointers([found], batch, LINES, ref)))
        span4 = {**span, "pdf_page": 4, "printed_page": 4, "text": "cerebellum vermis flocculus"}
        self.assertEqual(checks.check_pointers([{**found, "spans": [span4]}], batch, LINES, ref), [])


class TestOwnerPicks(Base):
    def test_pick_moves_a_question_between_the_two_lists(self):
        m = lectures.create("year2-cns", "T", "d")
        self.assertEqual(page.pick(m["id"], "k1", "required"), {"required": 1, "doctor_questions": 0})
        self.assertEqual(page.pick(m["id"], "k1", "doctor_questions"), {"required": 0, "doctor_questions": 1})
        self.assertEqual(page.pick(m["id"], "k1", None), {"required": 0, "doctor_questions": 0})

    def test_the_owner_sets_pages(self):
        m = lectures.create("year2-cns", "T", "d")
        with mock.patch.object(page, "ROOT", self.root):
            (self.root / "modules" / "year2-cns").mkdir(parents=True)
            write_jsonl(self.root / "modules" / "year2-cns" / "lines.jsonl", LINES)
            self.assertEqual(page.set_pages(m["id"], "4-5, 2"), {"pages": [[2, 2], [4, 5]]})
            self.assertIn("error", page.set_pages(m["id"], "2-9"))
        self.assertEqual(lectures.load(m["id"])["placed_by"], "owner")

    def test_naming_queues_the_place_agent(self):
        with mock.patch.object(page, "ROOT", self.root), mock.patch.object(page, "module_codes", return_value=["year2-cns"]):
            self.assertIn("handout first", page.new_lecture({"module": "year2-cns", "title": "T", "doctor": "d"}, self.q)["error"])
            (self.root / "modules" / "year2-cns").mkdir(parents=True)
            write_jsonl(self.root / "modules" / "year2-cns" / "lines.jsonl", LINES)
            self.assertEqual(page.new_lecture({"module": "year2-cns", "title": "T", "doctor": "d"}, self.q),
                             {"id": "cns-001", "queued": "place"})
        self.assertEqual(self.q.progress(), {"place": {"queued": 1}})


if __name__ == "__main__":
    unittest.main()

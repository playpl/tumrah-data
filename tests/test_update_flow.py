"""The 2026-11-10 update flow: folder names, unnumbered recordings, Telegram lists, partial books folded into full ones,
the backup rule."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backup  # noqa: E402
import books_merge  # noqa: E402
import doctors_folder  # noqa: E402
import lectures  # noqa: E402
import mcq  # noqa: E402
import queue_db  # noqa: E402
import tg_lists  # noqa: E402


class TestFolderNames(unittest.TestCase):
    def test_fancy_letters_and_auto_notes_are_flattened(self):
        self.assertEqual(doctors_folder.key_of("𝚆𝚊𝚐𝚒𝚑 𝙴𝚕𝚑𝚞𝚜𝚜𝚎𝚒𝚗𝚢 (auto)"), "wagih elhusseiny")
        self.assertEqual(doctors_folder.key_of("azony (auto)"), "azony")
        self.assertEqual(doctors_folder.match_doctor("𝙼𝚊𝚑𝚖𝚘𝚞𝚍 𝙴𝚕𝚑𝚞𝚜𝚜𝚎𝚒𝚗𝚢", []), "dr-mahmoud-el-husseiny-hist")
        with mock.patch.dict(doctors_folder.ALIASES):
            doctors_folder.ALIASES.pop("cocci", None)  # the owner may have set it since (ledger.db rules)
            self.assertIsNone(doctors_folder.match_doctor("𝙲𝚘𝚌𝚌𝚒", []))  # no site doctor: never guessed

    def test_book_ids_ignore_the_auto_note(self):
        b = {"doctor_folder": "azony (auto)", "subject": "anatomy", "kind": "full"}
        self.assertEqual(doctors_folder.book_id(b), "azony-anat-full")
        self.assertEqual(doctors_folder.book_id({**b, "kind": "mcq_partial"}), "azony-anat-mcq")

    def test_list_files_read_the_message_id(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / "all here updates (auto).txt").write_text("https://t.me/RecordsBatch58ATM/1630", encoding="utf-8")
            (d / "old data.txt").write_text("https://t.me/RecordsBatch58ATM/1205\n", encoding="utf-8")
            (d / "notes.txt").write_text("https://t.me/RecordsBatch58ATM/9", encoding="utf-8")
            self.assertEqual(doctors_folder.list_files(d), {"auto": 1630, "old": 1205})


class TestChapterFiles(unittest.TestCase):
    def test_unnumbered_recordings_follow_the_chapter_and_a_revision_is_kind_revision(self):
        with tempfile.TemporaryDirectory() as t:
            doc = Path(t) / "cns" / "physiology" / "elsamahy"
            chap = doc / "1- sensations"
            chap.mkdir(parents=True)
            (chap / "3- pain 1.txt").write_text("https://youtu.be/abc", encoding="utf-8")
            for name in ("Pain 2 .mp3", "Pain analgesia system pain control.mp3", "pain Revision.mp3"):
                (chap / name).write_bytes(b"x")
                os.utime(chap / name, (time.time() - 3600,) * 2)
            with mock.patch.object(doctors_folder, "DOCTORS", Path(t)):
                lessons, _ = doctors_folder.scan()
            by = {x["title"]: x for x in lessons if x["n"]}
            self.assertEqual(by["Pain 2"]["n"], 4)
            self.assertEqual(by["Pain analgesia system pain control"]["n"], 5)
            self.assertEqual(by["pain Revision"]["kind"], "revision")
            self.assertFalse(by["Pain 2"]["waiting"])

    def test_a_file_changed_a_moment_ago_waits(self):
        with tempfile.TemporaryDirectory() as t:
            chap = Path(t) / "cns" / "anatomy" / "amr mossafer" / "chapter 2"
            chap.mkdir(parents=True)
            (chap / "4- csf .mp3").write_bytes(b"x")
            with mock.patch.object(doctors_folder, "DOCTORS", Path(t)):
                lessons, _ = doctors_folder.scan()
            x = next(x for x in lessons if x["n"] == 4)
            self.assertEqual(x["title"], "csf")
            self.assertTrue(x["waiting"])
            self.assertEqual(doctors_folder.nice("csf"), "CSF")

    def test_a_bare_youtube_address_in_a_lesson_file_is_a_link(self):
        self.assertEqual(doctors_folder.links(" lec youtube.com/watch?v=GABrSUDznYE\n"),
                         [{"kind": "recording", "url": "https://youtube.com/watch?v=GABrSUDznYE"}])


class FakeEnt:
    def __init__(self, offset, url):
        self.offset, self.url = offset, url


class FakeMsg:
    """What parse() reads of a Telethon message: text and the link entities with their labels."""
    id, date, edit_date, media, entities = 1630, None, None, None, []

    def __init__(self, text, links):
        self.message = text
        self._links = links

    def get_entities_text(self):
        out = []
        for label, url in self._links:
            off = len(self.message[:self.message.index(label)].encode("utf-16-le")) // 2
            out.append((FakeEnt(off, url), label))
        return out


class TestListParse(unittest.TestCase):
    def test_sections_items_and_parts(self):
        text = ("DR.X\n\n📚 PDFs\n\n- Part 1\n- Part 2\n\n💻 Lectures\n\n- Spinal cord\n ➥ part 1  ➥ Part 2\n- Pain\n ➥ P1\n\n📝 Revisions\n")
        base = "https://t.me/RecordsBatch58ATM/"
        msg = FakeMsg(text, [("Part 1", base + "1"), ("Part 2", base + "2?single"), ("part 1", base + "3"),
                             ("Part 2 ", base + "4") if False else ("➥ Part 2", base + "4"), ("P1", base + "5")])
        d = tg_lists.parse(msg)
        self.assertEqual([i["title"] for i in d["sections"]["pdfs"]], ["Part 1", "Part 2"])
        self.assertEqual(d["sections"]["pdfs"][1]["parts"][0]["post"], 2)  # ?single is dropped
        lec = d["sections"]["lectures"]
        self.assertEqual([(i["title"], len(i["parts"])) for i in lec], [("Spinal cord", 2), ("Pain", 1)])
        self.assertEqual(d["sections"]["revisions"], [])

    def test_an_older_list_takes_numbered_blocks_as_lectures_then_revisions(self):
        text = "Dr x\n\nالكتب\n\nPart 1\n\nالمحاضرات\n\n1. Intro\n2. Spinal cord\n\nالمراجعات\n\n1. Final\n"
        base = "https://t.me/RecordsBatch58ATM/"
        msg = FakeMsg(text, [("Part 1", base + "1"), ("Intro", base + "2"), ("Spinal cord", base + "3"), ("Final", base + "4")])
        d = tg_lists.parse(msg)
        self.assertEqual([i["title"] for i in d["sections"]["lectures"]], ["Intro", "Spinal cord"])
        self.assertEqual([i["title"] for i in d["sections"]["revisions"]], ["Final"])
        self.assertEqual(len(d["sections"]["pdfs"]), 1)


def make_pdf(path, pages):
    import fitz
    doc = fitz.open()
    for text in pages:
        p = doc.new_page()
        if text:
            p.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


LONG = "The spinal cord ends at the lower border of the first lumbar vertebra in adults. "


class TestBooksMerge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def pdfs(self):
        pages = [LONG + f"Page {i} " * 6 for i in range(1, 7)]
        make_pdf(self.t / "partial.pdf", pages[:3])
        make_pdf(self.t / "full.pdf", pages)
        make_pdf(self.t / "other.pdf", ["Something else entirely about the heart valves and the cardiac cycle " * 3] * 3 + pages[3:])

    def test_the_partial_is_the_first_pages_of_the_full_book(self):
        self.pdfs()
        self.assertEqual(books_merge.page_offset(self.t / "partial.pdf", self.t / "full.pdf")[0], 0)
        self.assertTrue(books_merge.same_prefix(self.t / "partial.pdf", self.t / "full.pdf"))
        self.assertIsNone(books_merge.page_offset(self.t / "partial.pdf", self.t / "other.pdf")[0])

    def test_an_mcq_book_grows_without_requeuing_pages_already_copied(self):
        self.pdfs()
        q = queue_db.Queue(self.t / "q.db")
        with mock.patch.object(mcq, "ROOT", self.t):
            first = mcq.queue_book(q, "year2-cns", "x-mcq", self.t / "partial.pdf", "dr-x", "anatomy")
            second = mcq.queue_book(q, "year2-cns", "x-mcq", self.t / "full.pdf", "dr-x", "anatomy")
            third = mcq.queue_book(q, "year2-cns", "x-mcq", self.t / "full.pdf", "dr-x", "anatomy")
        self.assertIn("1 new jobs", first)
        self.assertIn("3 already in jobs, 1 new jobs", second)
        self.assertIn("0 new jobs", third)
        keys = sorted(r["key"] for r in q.db.execute("SELECT key FROM jobs WHERE flow='mcq'"))
        q.close()
        self.assertEqual(keys, ["year2-cns-x-mcq-p0001", "year2-cns-x-mcq-p0004"])


class TestBackupWords(unittest.TestCase):
    def test_numbers_must_agree_so_spinal_cord_2_is_not_3(self):
        meta = {"title": "Spinal cord 2 (Dr. Wagih)"}
        items = [("lectures", {"title": "Spinal cord 3", "parts": []}), ("lectures", {"title": "Spinal cord 2", "parts": []}),
                 ("revisions", {"title": "Spinal cord", "parts": []})]
        ranked = backup.candidates(meta, items)
        self.assertEqual(ranked[0][2]["title"], "Spinal cord 2")
        self.assertNotIn("Spinal cord 3", [r[2]["title"] for r in ranked])

    def test_find_lectures_by_id_or_by_words(self):
        metas = [{"id": "cns-001", "title": "Spinal cord 1", "doctor": "dr-a"}, {"id": "cns-002", "title": "Spinal cord 2 (Dr. B)", "doctor": "dr-b"}]
        with mock.patch.object(lectures, "all_lectures", return_value=metas):
            self.assertEqual([m["id"] for m in backup.find_lectures("cns-002")], ["cns-002"])
            self.assertEqual([m["id"] for m in backup.find_lectures("spinal cord 2")], ["cns-002"])
            self.assertEqual([m["id"] for m in backup.find_lectures("spinal cord", "dr-a")], ["cns-001"])


class TestBackupFlag(unittest.TestCase):
    def test_a_real_recording_replaces_the_backup_and_moves_its_transcript_aside(self):
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(lectures, "LECTURES", Path(t)), mock.patch.object(lectures, "compress"), \
                    mock.patch.object(lectures, "duration", return_value=60.0):
                d = Path(t) / "cns-001"
                d.mkdir()
                lectures.save({"id": "cns-001", "module": "m", "title": "T", "doctor": "dr-a", "kind": "lecture", "source": {},
                               "ranges": [], "required": [], "doctor_questions": []})
                f = Path(t) / "old.mp3"
                f.write_bytes(b"x")
                lectures.add("cns-001", "m", "T", 16, file=f, backup={"item": "T", "since": "2026-11-10"})
                (d / "raw.txt").write_text("[00:00] the old batch's words", encoding="utf-8")
                self.assertTrue(lectures.load("cns-001")["backup"])
                lectures.add("cns-001", "m", "T", 16, file=f)
                self.assertNotIn("backup", lectures.load("cns-001"))
                self.assertTrue((d / "old_backup_recording" / "raw.txt").exists())
                self.assertFalse((d / "raw.txt").exists())


class TestOwnSourceRows(unittest.TestCase):
    def test_a_keyed_row_from_the_owners_own_source_becomes_a_site_question_and_an_unkeyed_one_does_not(self):
        import site_questions
        meta = {"id": "cns-005", "lesson": "L1", "kind": "lecture", "subject": "Physiology", "title": "Receptors 1",
                "doctor": "dr-abdullah-el-samahi-phys", "required": [
                    {"file": "abc", "n": 0, "row": {"question": "Q?", "options": ["a", "b", "c"], "key": 1}},
                    {"file": "abc", "n": 1, "row": {"question": "Q2?", "options": ["a", "b"], "key": None}}],
                "doctor_questions": []}
        with mock.patch.object(lectures, "all_lectures", return_value=[meta]):
            data, skipped = site_questions.build("year2-cns", [])
        self.assertEqual(len(data["questions"]), 1)
        q = data["questions"][0]
        self.assertTrue(q["source_id"].startswith("own:"))
        self.assertEqual((q["correct_index"], q["_list"], q["doctorId"]), (1, "required", "dr-abdullah-el-samahi-phys"))
        self.assertEqual(skipped["not_in_bank_no_key"], 1)


class TestRenumbered(unittest.TestCase):
    def test_a_recording_the_owner_renumbered_is_found_again(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t) / "cns" / "physiology" / "elsamahy" / "1- sensations"
            root.mkdir(parents=True)
            (root / "4- Pain 2 .mp3").write_bytes(b"x")
            meta = {"id": "cns-023", "module": "year2-cns", "title": "Pain 2", "source": {"file": str(root / "Pain 2 .mp3")}}
            saved = []
            with mock.patch.object(doctors_folder, "DOCTORS", Path(t)), mock.patch.object(lectures, "all_lectures", return_value=[meta]),                     mock.patch.object(lectures, "save", side_effect=saved.append):
                lines = doctors_folder.repair_paths()
            self.assertTrue(saved and saved[0]["source"]["file"].endswith("4- Pain 2 .mp3"), lines)


class TestLessonOrder(unittest.TestCase):
    def test_a_doctors_lessons_follow_the_order_they_were_named_whatever_their_titles_say(self):
        import dm
        metas = [{"id": "cns-018", "doctor": "d1", "title": "Pain 1", "chapter_lessons": ["Receptors 1"]},
                 {"id": "cns-005", "doctor": "d1", "title": "Receptors 1"},
                 {"id": "cns-023", "doctor": "d1", "title": "Pain 2", "chapter_lessons": ["Pain 2", "Pain 1"]},
                 {"id": "cns-024", "doctor": "d1", "title": "Analgesia"},
                 {"id": "cns-030", "doctor": "d2", "title": "Pain 1"},
                 {"id": "cns-025", "doctor": "d1", "title": "Pain revision", "kind": "revision", "covers": ["cns-018", "cns-023"]},
                 {"id": "cns-026", "doctor": "d1", "title": "Pain revision 2", "kind": "revision", "covers": ["cns-018", "cns-023"]}]
        o = dm.lesson_order(metas)
        self.assertEqual([o[i] for i in ("cns-005", "cns-018", "cns-023", "cns-024")], [1, 2, 3, 4])
        self.assertEqual(o["cns-030"], 1)                       # another doctor counts on its own
        self.assertEqual((o["cns-025"], o["cns-026"]), (3.5, 3.51))  # after the last lesson covered; never equal

    def test_the_owners_file_numbers_win(self):
        import dm
        metas = [{"id": "cns-023", "doctor": "d1", "title": "Pain 2", "order_key": [0, 5]},
                 {"id": "cns-024", "doctor": "d1", "title": "Analgesia", "order_key": [0, 4]},
                 {"id": "cns-018", "doctor": "d1", "title": "Pain 1", "order_key": [0, 3]},
                 {"id": "cns-040", "doctor": "d1", "title": "From an auto list"}]
        o = dm.lesson_order(metas)
        self.assertEqual([o[i] for i in ("cns-018", "cns-024", "cns-023", "cns-040")], [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()

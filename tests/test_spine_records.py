import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from spine.records import machine
from spine.tg import mother

CH = "ZAG59_bio"


def make_list():
    """Two lectures (YouTube, Telegram audio), a revision of both (Telegram video), a PDF."""
    return {"id": 29, "channel": CH, "text": "Dr. X\nLectures\nRevisions", "edit_date": None,
            "sections": {"pdfs": [{"title": "Book", "parts": [{"label": "Book", "post": 75}]}],
                         "lectures": [{"title": "CHO Lect1", "group": "Chapter 1 (CHO)", "parts": [{"label": "CHO Lect1", "post": 38}]},
                                      {"title": "CHO Lect2", "group": "Chapter 1 (CHO)", "parts": [{"label": "CHO Lect2", "post": 40}]}],
                         "revisions": [{"title": "CHO revision", "parts": [{"label": "CHO revision", "post": 41}]}]},
            "posts": {"38": {"kind": "youtube", "youtube": ["https://youtu.be/AbCdEfGhIjK?si=x"], "size": None, "caption": ""},
                      "40": {"kind": "audio", "size": 5_000_000, "file_name": "lect2.mp3", "mime": "audio/mpeg", "caption": ""},
                      "41": {"kind": "video", "size": 9_000_000, "file_name": "rev.mp4", "mime": "video/mp4", "caption": ""},
                      "75": {"kind": "pdf", "size": 1_000_000, "caption": ""}}}


MAP = {1: {"role": "ignore", "covers": [], "name": "Book", "chapter": ""},
       2: {"role": "lecture", "covers": [], "name": "CHO Lect1", "chapter": "Chapter 1 (CHO)"},
       3: {"role": "lecture", "covers": [], "name": "CHO Lect2", "chapter": "Chapter 1 (CHO)"},
       4: {"role": "revision", "covers": [2, 3], "name": "CHO revision", "chapter": "Chapter 1 (CHO)"}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        lists, cache = self.tmp / "lists", self.tmp / "mother"
        (lists / CH).mkdir(parents=True)
        lst = make_list()
        (lists / CH / "29.json").write_text(json.dumps(lst), encoding="utf-8")
        trees = self.tmp / "trees.json"
        trees.write_text(json.dumps({"year1": {"module": "year1-test", "doctors": [
            {"subject": "biochemistry", "name": "Dr. X", "site": None, "channel": CH, "list": 29}]}}), encoding="utf-8")
        self.patches = [mock.patch.object(mother, "LISTS", lists), mock.patch.object(mother, "CACHE", cache),
                        mock.patch.object(mother, "TREES", trees),
                        mock.patch.object(machine, "SOURCES", self.tmp / "records"),
                        mock.patch.object(machine, "graph_dir", lambda m: self.tmp / "modules" / m / "graph"),
                        mock.patch.object(machine, "module_dir", lambda m: self.tmp / "modules" / m)]
        for p in self.patches:
            p.start()
        mother.save(lst, MAP, "test")
        self.recs = machine.plan(1)

    def tearDown(self):
        for p in self.patches:
            p.stop()


class Plan(Base):
    def test_only_lectures_minis_and_revisions_are_records(self):
        self.assertEqual([r["id"] for r in self.recs], ["y1-bio-38", "y1-bio-40", "y1-bio-41"])

    def test_source_kind_and_covers(self):
        yt, aud, rev = self.recs
        self.assertEqual((yt["source"], yt["youtube"]), ("youtube", "https://youtu.be/AbCdEfGhIjK?si=x"))
        self.assertEqual((aud["source"], aud["size"]), ("telegram", 5_000_000))
        self.assertEqual((rev["role"], rev["covers"]), ("revision", ["y1-bio-38", "y1-bio-40"]))
        self.assertEqual(rev["chapter"], "Chapter 1 (CHO)")

    def test_a_changed_list_is_skipped_and_reported(self):
        lst = make_list()
        lst["text"] += "\nnew line"
        (mother.LISTS / CH / "29.json").write_text(json.dumps(lst), encoding="utf-8")
        problems = []
        self.assertEqual(machine.plan(1, problems=problems), [])
        self.assertIn("changed", problems[0])

    def test_doctor_filter(self):
        self.assertEqual(len(machine.plan(1, "dr. x")), 3)
        self.assertEqual(machine.plan(1, "nobody"), [])
        self.assertEqual(len(machine.plan(1, "ZAG59_bio/29")), 3)

    def test_ids_never_look_like_year_2(self):
        self.assertEqual(machine.record_id(1, "ZAG59_Anatomy", 112), "y1-anat-112")
        self.assertEqual(machine.record_id(1, "ZAG59_Histo", None, "https://youtu.be/DUuSlklkU70?si=2"), "y1-hist-ytDUuSlklkU70")

    def test_plan_lines_total(self):
        self.assertIn("  3   2     14    1", machine.plan_lines(self.recs)[-1])


class State(Base):
    def test_last_row_wins_and_fields_merge(self):
        machine.mark("year1-test", "y1-bio-40", "downloaded", size=5)
        machine.mark("year1-test", "y1-bio-40", "compressed", duration_s=60)
        st = machine.states("year1-test")
        self.assertEqual((st["y1-bio-40"]["state"], st["y1-bio-40"]["size"]), ("compressed", 5))
        self.assertTrue(machine.reached(st, "y1-bio-40", "downloaded"))
        self.assertFalse(machine.reached(st, "y1-bio-40", "uploaded"))
        self.assertFalse(machine.reached(st, "y1-bio-41", "downloaded"))

    def test_status_counts_what_is_left(self):
        machine.mark("year1-test", "y1-bio-40", "uploaded")
        lines = machine.status_lines(self.recs)
        self.assertIn("left: 2 records, 9 MB", lines[-1])


async def _pieces(data, off, size):
    for i in range(off, len(data), size):
        yield data[i:i + size]


class Download(Base):
    def test_resume_offset_is_a_whole_piece(self):
        self.assertEqual(machine.resume_offset(0), 0)
        self.assertEqual(machine.resume_offset(machine.CHUNK * 3 + 17), machine.CHUNK * 3)

    def test_a_stopped_download_goes_on_from_its_partial(self):
        data = bytes(range(256)) * 40          # 10,240 bytes, pieces of 1,024
        part = self.tmp / "f.partial"
        with mock.patch.object(machine, "CHUNK", 1024):
            budget = machine.Budget(2500 / 1e6)
            whole = asyncio.run(machine.fetch_into(part, len(data), lambda off: _pieces(data, off, 1024), budget))
            self.assertFalse(whole)
            self.assertEqual(part.stat().st_size, 3072)
            with open(part, "ab") as f:        # a torn last piece is cut back to a whole one
                f.write(b"xx")
            whole = asyncio.run(machine.fetch_into(part, len(data), lambda off: _pieces(data, off, 1024), machine.Budget(None)))
        self.assertTrue(whole)
        self.assertEqual(part.read_bytes(), data)


class Upload(Base):
    def test_an_original_is_never_uploaded(self):
        with self.assertRaises(ValueError):
            machine.check_uploadable(self.tmp / "records" / CH / "40" / "lect2.mp3")
        machine.check_uploadable(self.tmp / "modules" / "m" / "records" / "y1-bio-40" / "recording.48k.m4a")

    def test_upload_sends_the_compressed_file_under_its_key(self):
        aud = self.recs[1]
        f = machine.compressed_path(aud)
        f.parent.mkdir(parents=True)
        f.write_bytes(b"m4a")
        machine.mark("year1-test", aud["id"], "compressed")
        sent = []
        machine.upload(self.recs, say=lambda s: None, sender=lambda file, key: (sent.append((file, key)) or (True, "ok")))
        self.assertEqual(sent, [(f, "lectures/year1-test/y1-bio-40/recording.48k.m4a")])
        st = machine.states("year1-test")
        self.assertEqual(st[aud["id"]]["state"], "uploaded")
        machine.upload(self.recs, say=lambda s: None, sender=lambda file, key: self.fail("sent twice"))

    def test_a_failed_upload_stays_compressed(self):
        aud = self.recs[1]
        f = machine.compressed_path(aud)
        f.parent.mkdir(parents=True)
        f.write_bytes(b"m4a")
        machine.mark("year1-test", aud["id"], "compressed")
        machine.upload(self.recs, say=lambda s: None, sender=lambda file, key: (False, "boom"))
        self.assertEqual(machine.states("year1-test")[aud["id"]]["state"], "compressed")


if __name__ == "__main__":
    unittest.main()

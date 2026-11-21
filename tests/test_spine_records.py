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
            {"subject": "histology", "name": "Dr. X", "site": None, "channel": CH, "list": 29}]}}), encoding="utf-8")
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

    def test_biochemistry_is_never_planned(self):
        trees = json.loads(mother.TREES.read_text(encoding="utf-8"))
        trees["year1"]["doctors"][0]["subject"] = "biochemistry"
        mother.TREES.write_text(json.dumps(trees), encoding="utf-8")
        problems = []
        self.assertEqual(machine.plan(1, problems=problems), [])
        self.assertIn("biochemistry", problems[0])

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

    def test_a_silent_stream_stops_instead_of_hanging(self):
        async def stuck(off):
            yield b"x" * 10
            await asyncio.sleep(3600)
            yield b"never"
        part = self.tmp / "s.partial"
        with self.assertRaises(TimeoutError):
            asyncio.run(machine.fetch_into(part, 100, stuck, machine.Budget(None), stall=0.05))
        self.assertEqual(part.stat().st_size, 10)            # what came is kept for the next run

    def test_progress_beat(self):
        data = b"y" * 4096
        t = [0.0]

        def clock():
            t[0] += machine.BEAT_S
            return t[0]
        beats = []
        asyncio.run(machine.fetch_into(self.tmp / "b.partial", len(data), lambda off: _pieces(data, off, 1024),
                                       machine.Budget(None), beat=beats.append, clock=clock))
        self.assertEqual(beats, [1024, 2048, 3072, 4096])


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


class Priority(unittest.TestCase):
    def test_first_lessons_of_every_subject_come_first(self):
        recs = [{"id": f"{s}{i}", "subject": s, "rank": i, "doctor_order": d}
                for d, s in enumerate(("histology", "anatomy", "biochemistry")) for i in range(3)]
        order = [r["id"] for r in machine.priority(recs)]
        self.assertEqual(order[:3], ["anatomy0", "histology0", "biochemistry0"])
        self.assertEqual(order[3:6], ["anatomy1", "histology1", "biochemistry1"])


class Site(Base):
    def rows(self, site="dr-x-hist", subject="histology"):
        from spine.records import flow
        for r in self.recs:
            r.update(site=site, subject=subject)
        return flow.site_rows(self.recs, machine.states("year1-test"))

    def test_no_site_doctor_means_no_lesson(self):
        rows, out = self.rows(site=None)
        self.assertEqual(rows, [])
        self.assertIn("no site doctor id", out[0])

    def test_a_subject_the_module_lacks_is_left_out(self):
        rows, out = self.rows(subject="biochemistry")
        self.assertEqual(rows, [])
        self.assertIn("biochemistry", out[0])

    def test_old_data_lessons_with_their_recordings(self):
        machine.mark("year1-test", "y1-bio-40", "uploaded", key="lectures/year1-test/y1-bio-40/recording.48k.m4a")
        rows, out = self.rows()
        by = {r["key"]: r for r in rows}
        self.assertEqual(set(by), {"lecture:y1-bio-38", "lecture:y1-bio-40"})          # the revision is not uploaded
        self.assertEqual(by["lecture:y1-bio-38"]["videoUrl"], "https://youtu.be/AbCdEfGhIjK")
        self.assertEqual(by["lecture:y1-bio-40"]["audioUrl"], "r2:lectures/year1-test/y1-bio-40/recording.48k.m4a")
        self.assertTrue(all(r["oldData"] and r["kind"] == "lesson" and r["ranges"] == [] for r in rows))
        self.assertEqual([r["order"] for r in rows], [1, 2])
        self.assertIn("not uploaded", out[0])

    def test_a_revision_covers_only_lessons_in_the_file(self):
        machine.mark("year1-test", "y1-bio-41", "uploaded")
        rows, _ = self.rows()
        rev = next(r for r in rows if r["kind"] == "revision")
        self.assertEqual(rev["covers"], ["lecture:y1-bio-38"])

    def test_a_revision_with_a_lectures_video_is_left_out(self):
        rev = self.recs[2]
        rev.update(source="youtube", youtube="https://youtu.be/AbCdEfGhIjK?si=other")
        rows, out = self.rows()
        self.assertNotIn("lecture:y1-bio-41", {r["key"] for r in rows})
        self.assertTrue(any("same video" in x and "y1-bio-41" in x for x in out))

    def test_accepted_segments_give_the_ranges_and_the_placement_stays_for_the_slice(self):
        from spine.records import flow
        placed = [{"from": "m:h:p6:l1", "to": "m:h:p10:l1"}]
        seg = [{"from": "m:h:p7:l2", "to": "m:h:p7:l9"}]
        machine.mark("year1-test", "y1-bio-40", "uploaded", key="lectures/year1-test/y1-bio-40/recording.48k.m4a")
        with mock.patch.object(flow, "placed_ranges", lambda *a, **k: placed),                 mock.patch.object(flow, "segment_ranges", lambda rid, module: seg if rid == "y1-bio-38" else []):
            rows, _ = self.rows()
        by = {r["key"]: r for r in rows}
        self.assertEqual((by["lecture:y1-bio-38"]["ranges"], by["lecture:y1-bio-38"]["placedRanges"]), (seg, placed))
        self.assertEqual(by["lecture:y1-bio-40"]["ranges"], placed)

    def test_segment_ranges_need_accepted_segments(self):
        from spine.records import flow
        d = self.tmp / "modules" / "year1-test" / "records" / "y1-bio-38"
        (d / "spine").mkdir(parents=True)
        (d / "spine" / "ranges.json").write_text(json.dumps({"ranges": [{"from": "a", "to": "b", "pages": [1, 1]}]}))
        with mock.patch.object(flow, "module_dir", lambda m: self.tmp / "modules" / m):
            self.assertEqual(flow.segment_ranges("y1-bio-38", "year1-test"), [])        # no segments.jsonl: not accepted
            (d / "segments.jsonl").write_text("{}")
            self.assertEqual(flow.segment_ranges("y1-bio-38", "year1-test"), [{"from": "a", "to": "b"}])

    def test_update_dry_only_reports(self):
        from spine.records import flow
        with mock.patch.object(machine, "download", side_effect=AssertionError("downloaded in a dry run")), \
                mock.patch.object(flow, "start_finish", side_effect=AssertionError("started in a dry run")):
            out = flow.update(dry=True)
        self.assertTrue(out[-2].startswith("year 1: 3 records"))


class Transcribe(Base):
    def test_shift_and_join(self):
        from spine.records import transcribe
        self.assertEqual(transcribe.shift("[04:50] a\n", 3600), "[64:50] a\n")
        raw = transcribe.join(["[00:00] one\n[02:30] two\n", "", "[00:10] three\n"])
        self.assertEqual(raw, "[00:00] one\n[02:30] two\n[10:10] three\n")

    def test_pieces_are_heard_once_and_joined(self):
        from spine.records import transcribe
        aud = self.recs[1]
        f = machine.compressed_path(aud)
        f.parent.mkdir(parents=True)
        f.write_bytes(b"m4a")
        machine.mark("year1-test", aud["id"], "compressed")
        pdir = machine.record_dir(aud) / "pieces"
        pdir.mkdir()
        pieces = [pdir / "c00.ogg", pdir / "c01.ogg"]
        for p in pieces:
            p.write_bytes(b"ogg")
        (pdir / "c00.txt").write_text("[00:00] heard before\n", encoding="utf-8")   # a stopped run's piece
        asked = []

        def ask(prompt, model, attach, timeout):
            asked.append(attach[0].name)
            return "word " * 3000, {"account": "x"}
        import lectures
        with mock.patch.object(transcribe, "cut", lambda r, a: pieces), mock.patch.object(lectures, "duration", lambda p: 300.0):
            n = transcribe.run(self.recs, say=lambda s: None, ask=ask, via="direct", workers=1)
        self.assertEqual((n, asked), (1, ["c01.ogg"]))
        raw = (machine.record_dir(aud) / "raw.txt").read_text(encoding="utf-8")
        self.assertTrue(raw.startswith("[00:00] heard before\n[05:00] word"))
        self.assertEqual(machine.states("year1-test")[aud["id"]]["transcript"], "gemini")

    def test_the_fleet_writes_piece_txt_and_it_is_checked(self):
        from spine.records import transcribe
        p = self.tmp / "pieces" / "c00.ogg"
        p.parent.mkdir()
        p.write_bytes(b"ogg")
        body = "\n".join(f"[{m:02d}:00] " + " ".join(f"kalam{m}x{i}" for i in range(120)) for m in range(5)) + "\n"

        def runner(cmd):
            self.assertIn("flash", cmd)
            (Path(cmd[cmd.index("--cwd") + 1]) / "piece.txt").write_text(body, encoding="utf-8")

        def short(cmd):
            (Path(cmd[cmd.index("--cwd") + 1]) / "piece.txt").write_text("[00:00] hi\n", encoding="utf-8")
        import lectures
        with mock.patch.object(lectures, "duration", lambda p: 300.0):
            self.assertEqual(transcribe.hear_fleet(p, "zero", runner=runner, say=lambda s: None), body)
            self.assertEqual(p.with_suffix(".txt").read_text(encoding="utf-8"), body)
            p.with_suffix(".txt").unlink()
            self.assertIsNone(transcribe.hear_fleet(p, "zero", runner=short, say=lambda s: None))
        self.assertFalse(p.with_suffix(".txt").exists())

    def test_a_condensed_answer_is_not_kept(self):
        from spine.records import transcribe
        p = self.tmp / "c00.ogg"
        p.write_bytes(b"ogg")
        import lectures
        with mock.patch.object(lectures, "duration", lambda p: 300.0):
            got = transcribe.hear(p, ask=lambda *a, **k: ("short summary", {}), say=lambda s: None)
        self.assertIsNone(got)
        self.assertFalse(p.with_suffix(".txt").exists())



class Year2Tree(Base):
    """Year 2 rows carry `new` (and `old`, fallback) and the channel once per year (the plan(2) KeyError 'channel')."""

    def setUp(self):
        super().setUp()
        lst = make_list()
        lst["id"], lst["channel"] = 1630, "RecordsBatch58ATM"
        (mother.LISTS / "1630.json").write_text(json.dumps(lst), encoding="utf-8")
        trees = json.loads(mother.TREES.read_text(encoding="utf-8"))
        trees["year2"] = {"module": "year2-test", "channel": "RecordsBatch58ATM", "doctors": [
            {"subject": "anatomy", "name": "Dr. A", "site": "a", "new": 1630, "old": 1205},
            {"subject": "anatomy", "name": "Dr. K", "site": None, "new": None, "old": None, "skip": True, "note": "playlist"},
            {"subject": "histology", "name": "Dr. B", "site": "b", "new": None, "old": 1562}]}
        mother.TREES.write_text(json.dumps(trees), encoding="utf-8")

    def test_new_list_and_year_channel(self):
        module, docs = machine.year_doctors(2)
        self.assertEqual((module, docs[0]["channel"], docs[0]["list"]), ("year2-test", "RecordsBatch58ATM", 1630))

    def test_plan_2_reports_instead_of_crashing(self):
        problems = []
        recs = machine.plan(2, problems=problems)
        self.assertEqual(recs, [])                       # no agreed map for 1630 in this test
        text = " | ".join(problems)
        self.assertIn("Dr. K (anatomy): playlist", text)
        self.assertIn("Dr. B (histology): no new list", text)
        self.assertNotIn("1205", text)                   # the old list is never planned
        self.assertNotIn("1562", text)


class TimeBudget(unittest.TestCase):
    def test_out_of_time_is_spent(self):
        t = [0.0]
        b = machine.Budget(None, 60, clock=lambda: t[0])
        self.assertFalse(b.spent)
        t[0] = 61
        self.assertTrue(b.spent)

    def test_bytes_still_count(self):
        b = machine.Budget(1, 3600)
        b.take(1_000_001)
        self.assertTrue(b.spent)


class _File:
    def __init__(self, name, size):
        self.name, self.ext, self.size = name, ".mp3", size


class _Msg:
    def __init__(self, size):
        self.media, self.file = object(), _File("lect.mp3", size)


class _Client:
    def __init__(self, data):
        self.data = data

    async def get_entity(self, ch):
        return ch

    async def get_messages(self, ent, ids):
        return _Msg(len(self.data))

    def iter_download(self, media, offset, request_size, file_size):
        return _pieces(self.data, offset, request_size)

    async def disconnect(self):
        pass


class RunnerDownload(Base):
    def test_each_record_is_finished_before_the_next(self):
        from cloud import tg as cloud_tg
        data = b"x" * 3000
        seen = []

        def on_done(rec):
            seen.append((rec["id"], machine.reached(machine.states(rec["module"]), rec["id"], "downloaded")))
            raise RuntimeError("upload down")             # one failure never stops the next record

        async def connect():
            return _Client(data)
        tg = [r for r in self.recs if r["source"] == "telegram"]
        with mock.patch.object(cloud_tg, "on_runner", lambda: True), mock.patch.object(cloud_tg, "connect", connect), \
                mock.patch.object(machine, "ROOT", self.tmp):
            got = asyncio.run(machine._download_telegram(tg, machine.Budget(None), lambda s: None, on_done=on_done))
        self.assertEqual(got, ["y1-bio-40", "y1-bio-41"])
        self.assertEqual(seen, [("y1-bio-40", True), ("y1-bio-41", True)])
        self.assertEqual(machine.states("year1-test")["y1-bio-40"]["where"], "runner")

    def test_runner_todo(self):
        from cloud import records
        machine.mark("year1-test", "y1-bio-40", "downloaded")                    # the PC has it: the PC uploads it
        machine.mark("year1-test", "y1-bio-41", "compressed", where="runner")    # a stopped run: fetch again
        st = machine.states("year1-test")
        self.assertEqual([r["id"] for r in records.todo(self.recs, st)], ["y1-bio-41"])
        machine.mark("year1-test", "y1-bio-41", "uploaded")
        self.assertEqual(records.todo(self.recs, machine.states("year1-test")), [])


class SiteKey(unittest.TestCase):
    def test_keys_fit_the_site_pattern(self):
        import re
        from spine.records import flow
        self.assertEqual(flow.site_key("y1-hist-93"), "lecture:y1-hist-93")
        a, b = flow.site_key("y1-hist-ytDUuSlklkU70"), flow.site_key("y1-hist-ytduuslklku70")
        self.assertRegex(a, r"^lecture:[a-z0-9-]+$")
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()

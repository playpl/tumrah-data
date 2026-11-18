"""Year 2 records through the GitHub runner (cloud/year2.py, cloud/records.py --year 2, update_data pc_transfers)."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import doctors_folder
import lectures
import upload_media
from cloud import records, state, year2
from spine.records import machine

M = "year2-cns"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(lectures, "LECTURES", self.tmp / "lectures"),
                        mock.patch.object(upload_media, "ROOT", self.tmp),
                        mock.patch.object(doctors_folder, "ROOT", self.tmp),
                        mock.patch.object(machine, "SOURCES", self.tmp / "records"),
                        mock.patch.object(machine, "graph_dir", lambda m: self.tmp / "modules" / m / "graph"),
                        mock.patch.object(machine, "module_dir", lambda m: self.tmp / "modules" / m)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def lecture(self, lid, **source):
        lectures.save({"id": lid, "module": M, "title": f"T {lid}", "doctor": "doc", "subject": "anatomy",
                       "source": source})

    def media(self, rows):
        f = self.tmp / "modules" / M / "site" / "media.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(rows), encoding="utf-8")

    def media_rows(self):
        return json.loads((self.tmp / "modules" / M / "site" / "media.json").read_text(encoding="utf-8"))


class Todo(Base):
    def test_selection(self):
        audio = self.tmp / "a.mp3"
        audio.write_bytes(b"x" * 10)
        self.lecture("cns-001", telegram="https://t.me/RecordsBatch58ATM/1870")                       # no file: in
        self.lecture("cns-002", telegram="https://t.me/RecordsBatch58ATM/1871", file=str(audio))      # pending: in
        self.lecture("cns-003", telegram="https://t.me/RecordsBatch58ATM/1872", file=str(audio))      # uploaded: out
        self.lecture("cns-004", telegram="https://t.me/RecordsBatch58ATM/1873", youtube="https://youtu.be/x")
        self.lecture("cns-005", telegram="https://t.me/RecordsBatch58ATM/1874", cloud={"key": "k"})
        self.lecture("cns-006", telegram="https://t.me/c/123/45")                                     # private chat
        self.lecture("cns-007")                                                                       # no source
        self.media([{"lecture": "cns-002", "file": str(audio), "key": "k2", "field": "audioUrl"},
                    {"lecture": "cns-003", "file": str(audio), "key": "k3", "field": "audioUrl", "uploaded_size": 10}])
        rows = year2.todo()
        self.assertEqual([(r["lecture"], r["post"]) for r in rows], [("cns-001", 1870), ("cns-002", 1871)])
        self.assertEqual(rows[1]["size"], 10)
        self.assertEqual(rows[0]["channel"], "RecordsBatch58ATM")

    def test_pending_skips_cloud_rows(self):
        self.media([{"lecture": "cns-010", "file": "", "key": year2.key("cns-010"), "field": "audioUrl", "cloud": True,
                     "uploaded_size": 5}])
        self.assertEqual(upload_media.pending(M), [])


class Pull(Base):
    def test_uploaded_rows_go_into_the_lecture_and_media(self):
        self.lecture("cns-164", telegram="https://t.me/RecordsBatch58ATM/1870")
        self.lecture("cns-165", telegram="https://t.me/RecordsBatch58ATM/1871")
        machine.mark(M, "cns-164", "compressed", duration_s=3079.0)
        machine.mark(M, "cns-164", "uploaded", key=year2.key("cns-164"), uploaded_size=18_000_000)
        machine.mark(M, "cns-164", hear_key="ops/tumrah-data/hear/year2-cns/cns-164.16k.ogg")
        machine.mark(M, "cns-165", "downloaded", where="runner")                       # not uploaded yet: untouched
        with mock.patch.object(state, "pull_log", lambda m: (0, 4)):
            out = year2.pull()
            again = year2.pull()
        meta = lectures.load("cns-164")
        self.assertEqual(meta["source"]["cloud"]["key"], "lectures/year2-cns/cns-164/recording.48k.m4a")
        self.assertEqual(meta["source"]["cloud"]["hear_key"], "ops/tumrah-data/hear/year2-cns/cns-164.16k.ogg")
        self.assertEqual(meta["duration_s"], 3079.0)
        self.assertEqual(meta["source"]["telegram"], "https://t.me/RecordsBatch58ATM/1870")
        self.assertNotIn("cloud", lectures.load("cns-165")["source"])
        rows = self.media_rows()
        self.assertEqual(rows, [{"lecture": "cns-164", "file": "", "key": year2.key("cns-164"), "field": "audioUrl",
                                 "cloud": True, "uploaded_size": 18_000_000}])
        self.assertEqual(len(out), 2)
        self.assertEqual(len(again), 1)                                                # nothing new the second time
        self.assertEqual(year2.todo(), [{"lecture": "cns-165", "module": M, "channel": "RecordsBatch58ATM",
                                         "post": 1871, "title": "T cns-165", "doctor": "doc", "subject": "anatomy",
                                         "size": None}])


class RunnerRecords(Base):
    def test_records_from_todo_and_skip_uploaded(self):
        rows = [{"lecture": "cns-164", "module": M, "channel": "RecordsBatch58ATM", "post": 1870, "title": "A",
                 "doctor": "d", "subject": "anatomy", "size": 3},
                {"lecture": "cns-165", "module": M, "channel": "RecordsBatch58ATM", "post": 1871, "title": "B",
                 "doctor": "d", "subject": "anatomy", "size": None}]
        recs = year2.records(rows)
        self.assertEqual([(r["id"], r["post"], r["source"], r["module"]) for r in recs],
                         [("cns-164", 1870, "telegram", M), ("cns-165", 1871, "telegram", M)])
        self.assertEqual(machine.upload_key(recs[0]), "lectures/year2-cns/cns-164/recording.48k.m4a")
        self.assertEqual(records.hear_key(recs[0]), "ops/tumrah-data/hear/year2-cns/cns-164.16k.ogg")
        machine.mark(M, "cns-164", "uploaded")
        self.assertEqual([r["id"] for r in records.todo(recs, machine.states(M))], ["cns-165"])
        with mock.patch.object(state, "pull_year2_todo", lambda: rows):
            self.assertEqual([r["id"] for r in records.plan(2, True, lambda s: None)], ["cns-164", "cns-165"])


class _BlockClient:
    """iter_download with offset/limit, as Telethon: `limit` pieces of `request_size` from `offset`."""

    def __init__(self, data):
        self.data, self.calls = data, []

    async def iter_download(self, media, offset, limit, request_size, file_size):
        self.calls.append(offset)
        for i in range(limit):
            o = offset + i * request_size
            if o >= len(self.data):
                return
            await asyncio.sleep(0.001 * ((offset // request_size) % 3))     # blocks finish out of order
            yield self.data[o:o + request_size]


class Parallel(unittest.TestCase):
    def test_pieces_come_in_order_from_the_resume_offset(self):
        data = bytes(range(256)) * 41                                       # 10496 bytes
        c = _BlockClient(data)

        async def go(off):
            return b"".join([p async for p in machine.parallel_stream(c, None, off, len(data), 3, chunk=512, block=2)])
        self.assertEqual(asyncio.run(go(0)), data)
        self.assertEqual(asyncio.run(go(2048)), data[2048:])

    def test_fetch_into_with_parallel_blocks(self):
        data = b"abcdefgh" * 2000
        c = _BlockClient(data)
        part = Path(tempfile.mkdtemp()) / "f.partial"
        whole = asyncio.run(machine.fetch_into(part, len(data), lambda off: machine.parallel_stream(
            c, None, off, len(data), 4, chunk=1024, block=3), machine.Budget(None)))
        self.assertTrue(whole)
        self.assertEqual(part.read_bytes(), data)

    def test_stop_mid_way_cancels_blocks_in_flight(self):
        data = b"z" * 20_000
        c = _BlockClient(data)
        part = Path(tempfile.mkdtemp()) / "f.partial"
        with mock.patch.object(machine, "CHUNK", 1024):
            whole = asyncio.run(machine.fetch_into(part, len(data), lambda off: machine.parallel_stream(
                c, None, off, len(data), 4, chunk=1024, block=2), machine.Budget(0.004)))
        self.assertFalse(whole)
        self.assertEqual(part.read_bytes(), data[:part.stat().st_size])


class _FakePool:
    """fast.Pool's `get` over bytes; pieces come back out of order; `cdn_at` raises CdnRedirect from that offset."""

    def __init__(self, data, n=3, cdn_at=None):
        self.data, self.n, self.cdn_at, self.asked = data, n, cdn_at, []

    async def get(self, dc_id, location, offset, limit):
        from spine.records import fast
        self.asked.append(offset)
        await asyncio.sleep(0.001 * ((offset // limit) % 3))
        if self.cdn_at is not None and offset >= self.cdn_at:
            raise fast.CdnRedirect()
        return self.data[offset:offset + limit]


def _doc(size):
    from telethon.tl import types
    return types.MessageMediaDocument(document=types.Document(
        id=1, access_hash=2, file_reference=b"r", date=None, mime_type="audio/mpeg", size=size, dc_id=4, attributes=[]))


class Connections(unittest.TestCase):
    def test_pieces_in_order_from_the_resume_offset(self):
        from spine.records import fast
        data = bytes(range(256)) * 40
        pool = _FakePool(data)

        async def go(off):
            return b"".join([p async for p in fast.stream(pool, _doc(len(data)), off, len(data), 512)])
        self.assertEqual(asyncio.run(go(0)), data)
        self.assertEqual(asyncio.run(go(1024)), data[1024:])

    def test_cdn_file_goes_on_over_the_client(self):
        from spine.records import fast
        data = b"q" * 5000 + b"w" * 5000
        pool = _FakePool(data, cdn_at=4096)
        asked = []

        async def fallback(off):
            asked.append(off)
            for o in range(off, len(data), 512):
                yield data[o:o + 512]

        async def go():
            return b"".join([p async for p in fast.stream(pool, _doc(len(data)), 0, len(data), 512, fallback=fallback)])
        self.assertEqual(asyncio.run(go()), data)
        self.assertEqual(asked, [4096])

    def test_fetch_into_stops_mid_way_and_resumes(self):
        from spine.records import fast
        data = b"abcdefgh" * 4000
        part = Path(tempfile.mkdtemp()) / "f.partial"
        with mock.patch.object(machine, "CHUNK", 1024):
            stream = lambda off: fast.stream(_FakePool(data), _doc(len(data)), off, len(data), 1024)  # noqa: E731
            self.assertFalse(asyncio.run(machine.fetch_into(part, len(data), stream, machine.Budget(0.01))))
            self.assertTrue(asyncio.run(machine.fetch_into(part, len(data), stream, machine.Budget(None))))
        self.assertEqual(part.read_bytes(), data)

    def test_runner_downloads_over_the_pool(self):
        from cloud import tg as cloud_tg
        from spine.records import fast
        data = b"m" * 3000

        class Msg:
            media, file = _doc(3000), type("F", (), {"name": "a.mp3", "ext": ".mp3", "size": 3000})()

        class Client:
            async def get_entity(self, ch):
                return ch

            async def get_messages(self, ent, ids):
                return Msg()

            async def disconnect(self):
                pass

        async def connect():
            return Client()

        made = []

        class Pool(_FakePool):
            def __init__(self, client, n, say):
                super().__init__(data, n)
                made.append(n)

            async def close(self):
                made.append("closed")

        tmp = Path(tempfile.mkdtemp())
        rec = {"id": "cns-200", "module": M, "channel": "RecordsBatch58ATM", "post": 1900, "source": "telegram"}
        with mock.patch.object(cloud_tg, "on_runner", lambda: True), mock.patch.object(cloud_tg, "connect", connect),                 mock.patch.object(fast, "Pool", Pool), mock.patch.object(machine, "SOURCES", tmp / "records"),                 mock.patch.object(machine, "ROOT", tmp), mock.patch.object(machine, "CHUNK", 1024),                 mock.patch.object(machine, "graph_dir", lambda m: tmp / "modules" / m / "graph"):
            got = asyncio.run(machine._download_telegram([rec], machine.Budget(None), lambda s: None, connections=5))
        self.assertEqual(got, ["cns-200"])
        self.assertEqual(made, [5, "closed"])
        self.assertEqual((tmp / "records" / "RecordsBatch58ATM" / "1900" / "a.mp3").read_bytes(), data)

    def test_requests_at_once_open_the_connections_once(self):
        from spine.records import fast
        pool = fast.Pool(object(), n=8)
        opened = []

        async def sender(dc_id):
            opened.append(dc_id)
            await asyncio.sleep(0.01)
            return object()

        async def go():
            pool._sender = sender
            await asyncio.gather(*(pool.senders_for(4) for _ in range(16)))
        asyncio.run(go())
        self.assertEqual(opened, [4] * 8)                    # run #4 opened 16 x 8
        self.assertEqual(len(pool.senders[4]), 8)


class UpdateDataNoTransfers(unittest.TestCase):
    def test_no_download_when_pc_transfers_is_false(self):
        import auto_doctors
        import tg_lists
        meta = {"id": "cns-900", "module": M, "title": "X", "source": {}}
        x = {"title": "X", "post": 1877, "url": "https://t.me/RecordsBatch58ATM/1877", "youtube": None, "size": None,
             "kind": "audio"}
        with mock.patch.object(lectures, "load", lambda lid: dict(meta)), mock.patch.object(lectures, "save"), \
                mock.patch.object(tg_lists, "download", side_effect=AssertionError("downloaded on the PC")):
            out = auto_doctors.add_recording(None, {"module": M}, x, "cns-900", "doc", "cns-900: 'X'", 0)
        self.assertIn("waits for the GitHub runner", out[0])

    def test_waiting_telegram_does_not_download(self):
        import tg_lists
        import update_data
        metas = [{"id": "cns-901", "module": M, "title": "Y", "source": {"telegram": "https://t.me/RecordsBatch58ATM/1878"}}]
        with mock.patch.object(lectures, "all_lectures", lambda *a: metas), \
                mock.patch.object(tg_lists, "info", lambda posts: {1878: {"kind": "audio", "size": 5_000_000}}), \
                mock.patch.object(tg_lists, "download", side_effect=AssertionError("downloaded on the PC")):
            out = update_data.waiting_telegram(None, False, transfers=False)
        self.assertEqual(out, ["cns-901: post 1878 (5 MB) waits for the GitHub runner"])

    def test_fleet_is_down(self):
        import update_data
        self.assertTrue(update_data.fleet_down())             # the mother step must not start fleet readers

    def test_config_says_no_transfers(self):
        import update_data
        self.assertFalse(update_data.pc_transfers())


if __name__ == "__main__":
    unittest.main()

"""Telegram downloads over several connections at once (the GitHub runner; owner 2026-11-18 "make it faster").

Telegram limits the speed of one connection: one Telethon client, even with several requests in flight, stayed at
about 1.2-1.7 MB/s on the runner. Like mautrix-telegram's parallel_file_transfer.py (MIT) and FastTelethon, `Pool`
opens `n` connections (MTProto senders) to the data center that holds the file and spreads the file's pieces over
them. The home data center reuses the session's key; another data center gets one exported authorization whose key
the other connections share.

`stream(...)` has the contract of `client.iter_download(...)`: an async iterator of the file's pieces in order from
`off`, so `machine.fetch_into` (resume from a .partial, budget, stall check) works unchanged. A file Telegram serves
from its CDN (`FileCdnRedirect`) goes on over the client's own `iter_download` from the byte reached.

Uses Telethon internals (`_get_dc`, `_connection`, `_init_request`, `_call`): checked against telethon 1.43.2, the
version pinned in cloud/requirements.txt.
"""
import asyncio

TRIES = 4


class CdnRedirect(Exception):
    """Telegram serves this file from its CDN: the client's own iter_download handles that."""


class Pool:
    """`n` connected senders per data center, made when first needed and kept for the whole run."""

    def __init__(self, client, n=8, say=None):
        self.client, self.n, self.say = client, n, say
        self.senders, self.keys, self.next = {}, {}, {}

    async def _sender(self, dc_id):
        from telethon.network import MTProtoSender
        from telethon.tl import functions
        from telethon.tl.alltlobjects import LAYER
        c = self.client
        dc = await c._get_dc(dc_id)
        key = c.session.auth_key if dc_id == c.session.dc_id else self.keys.get(dc_id)
        sender = MTProtoSender(key, loggers=c._log)
        await sender.connect(c._connection(dc.ip_address, dc.port, dc.id, loggers=c._log, proxy=c._proxy))
        if key is None:                              # another data center: export the authorization once
            auth = await c(functions.auth.ExportAuthorizationRequest(dc_id))
            c._init_request.query = functions.auth.ImportAuthorizationRequest(id=auth.id, bytes=auth.bytes)
            await sender.send(functions.InvokeWithLayerRequest(LAYER, c._init_request))
            self.keys[dc_id] = sender.auth_key
        return sender

    async def senders_for(self, dc_id):
        if dc_id not in self.senders:
            first = [await self._sender(dc_id)]                       # the first one exports the key if needed
            rest = await asyncio.gather(*(self._sender(dc_id) for _ in range(self.n - 1)), return_exceptions=True)
            bad = [r for r in rest if isinstance(r, BaseException)]
            self.senders[dc_id] = first + [r for r in rest if not isinstance(r, BaseException)]
            self.next[dc_id] = 0
            if self.say:
                self.say(f"  data center {dc_id}: {len(self.senders[dc_id])} connections"
                         + (f" ({len(bad)} failed: {type(bad[0]).__name__})" if bad else ""))
        return self.senders[dc_id]

    async def get(self, dc_id, location, offset, limit):
        """One piece; FloodWait is slept by Telethon's _call (up to the client's flood_sleep_threshold)."""
        from telethon.tl import functions, types
        senders = await self.senders_for(dc_id)
        err = None
        for attempt in range(TRIES):
            i = self.next[dc_id] = (self.next[dc_id] + 1) % len(senders)
            try:
                res = await self.client._call(senders[i], functions.upload.GetFileRequest(location, offset, limit))
            except Exception as e:  # noqa: BLE001 - a dropped connection: the next sender tries again
                err = e
                await asyncio.sleep(1 + attempt)
                continue
            if isinstance(res, types.upload.FileCdnRedirect):
                raise CdnRedirect()
            return res.bytes
        raise err

    async def close(self):
        for ss in self.senders.values():
            for s in ss:
                try:
                    await s.disconnect()
                except Exception:  # noqa: BLE001 - closing a dead connection
                    pass
        self.senders.clear()


async def stream(pool, media, off, total, chunk, fallback=None, window=None):
    """The pieces of `media` from `off`, in order, `window` requests in flight over the pool's connections.
    `fallback(offset)` (the client's iter_download) takes over from the byte reached when the file is on the CDN."""
    from telethon import utils
    dc_id, location = utils.get_input_location(media)
    window = window or pool.n * 2
    offsets = list(range(off, total, chunk))
    flight, nxt, pos = [], 0, off
    try:
        while nxt < len(offsets) or flight:
            while nxt < len(offsets) and len(flight) < window:
                flight.append(asyncio.ensure_future(pool.get(dc_id, location, offsets[nxt], chunk)))
                nxt += 1
            try:
                piece = await flight.pop(0)
            except CdnRedirect:
                if fallback is None:
                    raise
                for t in flight:
                    t.cancel()
                await asyncio.gather(*flight, return_exceptions=True)
                flight = []
                async for p in fallback(pos):
                    yield p
                return
            if not piece:
                return
            pos += len(piece)
            yield piece
    finally:
        for t in flight:
            t.cancel()
        await asyncio.gather(*flight, return_exceptions=True)

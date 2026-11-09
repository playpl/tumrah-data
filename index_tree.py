"""A channel's index message and its link tree (owner, 2026-11-09: https://t.me/Batch58ATM/51245).

The index links to sub-indexes and lesson posts in the same channel. Following every link (read only, never joins,
never votes) gives each lesson's first message; the channel's polls between one lesson's first message and the next
lesson's belong to that lesson. Writes sources/index/<channel>_<id>.json: the nodes (message id, link anchor text,
the links it holds, poll or not). Prints counts only.

    py index_tree.py fetch Batch58ATM 51245 [--account voter2] [--depth 4]
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\quizbot")
OUT = ROOT / "sources" / "index"
MAX_NODES = 2500


def links_of(msg, channel, channel_id):
    """(anchor text, message id) for every link in the message to another message of the same channel. Anchor text
    comes from Telethon (entity offsets count UTF-16 units). Links to other chats are counted, not followed."""
    from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
    pat = re.compile(rf"(?:https?://)?t\.me/(?:({re.escape(channel)})|c/(\d+))/(\d+)", re.I)

    def same(m):
        return m and (m.group(1) or m.group(2) == str(channel_id))

    found, other = [], 0
    for e, txt in msg.get_entities_text():
        url = e.url if isinstance(e, MessageEntityTextUrl) else txt if isinstance(e, MessageEntityUrl) else None
        if url is None:
            continue
        m = pat.search(url)
        if same(m):
            found.append((txt if isinstance(e, MessageEntityTextUrl) else "", int(m.group(3))))
        elif "t.me/" in url:
            other += 1
    for row in (getattr(msg.reply_markup, "rows", None) or []):
        for b in row.buttons:
            m = pat.search(getattr(b, "url", "") or "")
            if same(m):
                found.append((b.text, int(m.group(3))))
    return found, other


async def fetch(channel, root, account, depth):
    from tg import connect
    client = await connect(account)
    try:
        ent = await client.get_entity(channel)
        nodes, todo, seen = {}, [(root, 0, None)], set()
        while todo and len(nodes) < MAX_NODES:
            batch = [t for t in todo if t[0] not in seen][:100]
            todo = [t for t in todo if t[0] not in {b[0] for b in batch}]
            if not batch:
                break
            msgs = await client.get_messages(ent, ids=[b[0] for b in batch])
            for (mid, d, anchor), msg in zip(batch, msgs):
                seen.add(mid)
                if msg is None:
                    nodes[mid] = {"id": mid, "missing": True, "anchor": anchor, "depth": d}
                    continue
                kids, other = links_of(msg, channel, ent.id)
                nodes[mid] = {"id": mid, "depth": d, "anchor": anchor, "date": msg.date.isoformat(),
                              "poll": bool(getattr(msg, "poll", None)), "media": type(msg.media).__name__ if msg.media else None,
                              "other_chat_links": other, "links": [{"anchor": a, "id": i} for a, i in kids]}
                if d < depth:
                    todo += [(i, d + 1, a) for a, i in kids if i not in seen]
            await asyncio.sleep(1)
    finally:
        await client.disconnect()
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{channel}_{root}.json"
    f.write_text(json.dumps({"channel": channel, "root": root, "nodes": list(nodes.values())}, ensure_ascii=False), encoding="utf-8")
    by_depth = {}
    for n in nodes.values():
        by_depth.setdefault(n["depth"], [0, 0, 0])
        by_depth[n["depth"]][0] += 1
        by_depth[n["depth"]][1] += len(n.get("links") or [])
        by_depth[n["depth"]][2] += bool(n.get("poll"))
    print(json.dumps({"file": str(f), "nodes": len(nodes), "by_depth [messages, links, polls]": by_depth}))


async def scan(channel, since, account):
    """Index-like messages (5+ links to the same channel) posted after message `since`: id, date, link count, and the
    English (non-Arabic) link anchors. Read only."""
    from tg import connect
    ar = re.compile("[؀-ۿﭐ-﻿]")
    client = await connect(account)
    try:
        ent = await client.get_entity(channel)
        out = []
        async for msg in client.iter_messages(ent, min_id=since, reverse=True):
            kids, _ = links_of(msg, channel, ent.id)
            if len(kids) >= 5:
                out.append({"id": msg.id, "date": msg.date.isoformat()[:16], "links": len(kids),
                            "anchors": [" ".join(a.split())[:30] for a, _ in kids if a.strip() and not ar.search(a)][:12]})
    finally:
        await client.disconnect()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{channel}_scan_{since}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for r in out:
        print(r["id"], r["date"], r["links"], "|", ", ".join(r["anchors"]))


async def kinds(channel, lo, hi, account):
    """id -> p (poll) | t (anything else) for every message in [lo, hi]. Read only; no text kept."""
    from tg import connect
    client = await connect(account)
    out = {}
    try:
        ent = await client.get_entity(channel)
        async for msg in client.iter_messages(ent, min_id=lo - 1, max_id=hi + 1, reverse=True):
            out[msg.id] = "p" if getattr(msg, "poll", None) else "t"
    finally:
        await client.disconnect()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{channel}_kinds_{lo}_{hi}.json").write_text(json.dumps(out), encoding="utf-8")
    print(json.dumps({"messages": len(out), "polls": sum(v == "p" for v in out.values())}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["fetch", "scan", "kinds"])
    p.add_argument("channel")
    p.add_argument("root", type=int)
    p.add_argument("hi", type=int, nargs="?")
    p.add_argument("--account", default="voter2")
    p.add_argument("--depth", type=int, default=4)
    a = p.parse_args()
    if a.cmd == "kinds":
        asyncio.run(kinds(a.channel, a.root, a.hi, a.account))
    elif a.cmd == "scan":
        asyncio.run(scan(a.channel, a.root, a.account))
    else:
        asyncio.run(fetch(a.channel, a.root, a.account, a.depth))

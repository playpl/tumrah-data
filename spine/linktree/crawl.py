"""The quiz and file channels as a link tree: links only, no file is downloaded.

    py -m spine tree fetch zagexam59 503       Year 1 quizzes and files (owner, 2026-11-16)
    py -m spine tree fetch ZMSUMcqs58 2098     Year 2
    py -m spine tree show zagexam59 503        the saved tree as an indented outline

A channel's root message links to list messages, which link to posts: a QuizBot quiz, a Google Form, a file, a
poll. Every link is followed inside the channel (read only: never joins, never votes, never downloads) and one
JSON file is written: sources/tree/<channel>_<root>.json. Each node keeps its text, the links it holds and what
it is (list, quizbot, form, file, poll, media, text). "From this message onward" (owner): every post after the
root is also listed, so a quiz that no list links to is seen as `unreached` instead of being missed.
"""
import asyncio
import re
import sys

from index_tree import links_of
from spine import ROOT, now, read_json, write_json

OUT = ROOT / "sources" / "tree"
MAX_NODES, MAX_ONWARD, TEXT_KEPT = 4000, 20000, 600
_URL_KIND = [("quizbot", re.compile(r"t\.me/(quizbot|quizbot\?|QuizBot)", re.I)),
             ("form", re.compile(r"(docs\.google\.com/forms|forms\.gle)", re.I)),
             ("drive", re.compile(r"(drive\.google\.com|docs\.google\.com/(document|spreadsheets|presentation))", re.I)),
             ("youtube", re.compile(r"(youtu\.be|youtube\.com)", re.I)),
             ("telegram", re.compile(r"t\.me/", re.I))]


def url_kind(url):
    return next((k for k, pat in _URL_KIND if pat.search(url or "")), "web")


def describe(msg, channel, channel_id):
    """One message as a node (no parent, no depth yet)."""
    from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
    inner, _ = links_of(msg, channel, channel_id)
    inner_ids = {i for _, i in inner}
    outer = []
    for e, txt in msg.get_entities_text():
        url = e.url if isinstance(e, MessageEntityTextUrl) else txt if isinstance(e, MessageEntityUrl) else None
        if url and not re.search(rf"t\.me/(?:{re.escape(channel)}|c/{channel_id})/\d+", url, re.I):
            outer.append({"anchor": txt if isinstance(e, MessageEntityTextUrl) else "", "url": url, "kind": url_kind(url)})
    for row in (getattr(msg.reply_markup, "rows", None) or []):
        for b in row.buttons:
            url = getattr(b, "url", "") or ""
            if url and not any(i == int(m.group(1)) for m in [re.search(r"/(\d+)$", url)] if m for i in inner_ids):
                outer.append({"anchor": b.text, "url": url, "kind": url_kind(url)})
    file = None
    if msg.file is not None and not msg.photo:
        file = {"name": msg.file.name, "mime": msg.file.mime_type, "size": msg.file.size}
    via = getattr(getattr(msg, "via_bot", None), "username", None) or ""
    kinds = {o["kind"] for o in outer}
    kind = ("list" if inner else "poll" if msg.poll else "quizbot" if "quizbot" in kinds or "quiz" in via.lower()
            else "form" if "form" in kinds else "file" if file and (file["mime"] or "").startswith(("application", "text"))
            else "media" if msg.media else "text")
    return {"id": msg.id, "date": msg.date.isoformat(), "edit_date": msg.edit_date.isoformat() if msg.edit_date else None,
            "kind": kind, "text": (msg.message or "")[:TEXT_KEPT], "links": [{"anchor": a, "id": i} for a, i in inner],
            "outer": outer, "file": file, "poll": bool(msg.poll), "grouped_id": msg.grouped_id}


async def _fetch(channel, root, account, depth, onward):
    sys.path.insert(0, r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\quizbot")
    from tg import connect
    client = await connect(account)
    try:
        ent = await client.get_entity(channel)
        nodes, todo, seen = {}, [(root, 0, None, "")], set()
        while todo and len(nodes) < MAX_NODES:
            batch = [t for t in todo if t[0] not in seen][:100]
            done = {b[0] for b in batch}
            todo = [t for t in todo if t[0] not in done and t[0] not in seen]
            if not batch:
                break
            msgs = await client.get_messages(ent, ids=[b[0] for b in batch])
            for (mid, d, parent, anchor), msg in zip(batch, msgs):
                seen.add(mid)
                if msg is None:
                    nodes[mid] = {"id": mid, "missing": True, "kind": "missing", "parent": parent, "anchor": anchor,
                                  "depth": d, "links": [], "outer": []}
                    continue
                nodes[mid] = {**describe(msg, channel, ent.id), "parent": parent, "anchor": anchor, "depth": d}
                if d < depth:
                    todo += [(l["id"], d + 1, mid, l["anchor"]) for l in nodes[mid]["links"] if l["id"] not in seen]
            await asyncio.sleep(1)
        after = []
        if onward:
            async for msg in client.iter_messages(ent, min_id=root, reverse=True, limit=MAX_ONWARD):
                if msg.id not in nodes:
                    n = describe(msg, channel, ent.id)
                    after.append({k: n[k] for k in ("id", "date", "kind", "file", "outer", "grouped_id")}
                                 | {"text": n["text"][:160], "links": len(n["links"])})
        return {"channel": channel, "channel_id": ent.id, "root": root, "fetched": now(), "depth": depth,
                "nodes": [nodes[k] for k in sorted(nodes)], "unreached": after}
    finally:
        await client.disconnect()


def fetch(channel, root, account="voter2", depth=8, onward=True):
    """Crawl and save. The copy before it goes to <name>.prev.json when the tree changed."""
    tree = asyncio.run(_fetch(channel, root, account, depth, onward))
    path = OUT / f"{channel}_{root}.json"
    old = read_json(path)
    if old and old.get("nodes") != tree["nodes"]:
        write_json(OUT / f"{channel}_{root}.prev.json", old)
    write_json(path, tree)
    return tree


def load(channel, root):
    return read_json(OUT / f"{channel}_{root}.json")


def summary(tree):
    from collections import Counter
    kinds = Counter(n["kind"] for n in tree["nodes"])
    after = Counter(n["kind"] for n in tree["unreached"])
    outer = Counter(o["kind"] for n in tree["nodes"] for o in n["outer"])
    lines = [f"{tree['channel']} from message {tree['root']}: {len(tree['nodes'])} posts in the link tree, "
             f"deepest level {max((n['depth'] for n in tree['nodes']), default=0)}",
             "  in the tree: " + ", ".join(f"{k} {n}" for k, n in kinds.most_common()),
             "  links out of the channel: " + (", ".join(f"{k} {n}" for k, n in outer.most_common()) or "none"),
             f"  posts after the root that no list links to: {len(tree['unreached'])}"
             + (" (" + ", ".join(f"{k} {n}" for k, n in after.most_common()) + ")" if after else "")]
    return "\n".join(lines)


def outline(tree, max_text=70):
    """The tree as indented lines: id, kind, anchor or first line of text."""
    by_id = {n["id"]: n for n in tree["nodes"]}
    out, seen = [], set()

    def walk(mid, depth, anchor):
        n = by_id.get(mid)
        if n is None:
            return
        first = " ".join((n.get("text") or "").split())[:max_text]
        extra = "".join(f" [{o['kind']}]" for o in n["outer"][:3]) + (f" <{n['file']['name']}>" if n.get("file") else "")
        out.append(f"{'  ' * depth}{mid} {n['kind']:<7} {(anchor or '').strip()[:40]!r} {first}{extra}"
                   + (" (seen above)" if mid in seen else ""))
        if mid in seen:
            return
        seen.add(mid)
        for l in n["links"]:
            walk(l["id"], depth + 1, l["anchor"])

    walk(tree["root"], 0, "")
    return "\n".join(out)

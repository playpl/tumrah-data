"""Reads the owner's Telegram list messages (RecordsBatch58ATM): read only, never joins, never writes.

A doctor's folder holds `all here updates (auto).txt` / `old data.txt` with one link, https://t.me/RecordsBatch58ATM/<id>.
That message is a list the channel keeps editing: three sections (PDFs, Lectures, Revisions); each item links the
channel posts that hold the files (a video, an audio file, a PDF, or a YouTube link in the post's text).

    py tg_lists.py fetch <id> [<id> ...]     save sources/lists/<id>.json: the list and every post it links
    py tg_lists.py show <id> [...]           print a saved list; Arabic text is never printed, only its length

`fetch_many(ids)` and `download(post ids)` are what the update flow calls. Account `voter2`, one connection per call.
"""
import asyncio
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "sources" / "lists"
CHANNEL = "RecordsBatch58ATM"
LINK = re.compile(r"https?://t\.me/(?:c/(\d+)|([A-Za-z0-9_]+))/(\d+)")
ARABIC = re.compile(r"[\u0600-\u06FF]")
SECTIONS = (("mini", "minis"), ("pdf", "pdfs"), ("lecture", "lectures"), ("revision", "revisions"))  # "Mini Lectures" before "lecture"
# The first-year lists (ZAG59_*, owner 2026-11-17): Arabic headers, "Books" / "Recs", bullets ". • ● _".
# Questions, practical, notes and the doctor's channel link are "other": never a lecture.
SECTIONS_Y1 = (("المذكرات", "pdfs"), ("books", "pdfs"),
               ("الشرح", "lectures"), ("recs", "lectures"),
               ("مراجع", "revisions"),
               ("الأسئلة", "other"), ("العملي", "other"),
               ("ملاحظات", "other"), ("channel link", "other"),
               ("قهوة", "other"), ("الجمعة", "other"),
               ("إسعاف", "other"))
BULLETS = ("-", ".", "•", "●", "_")
SUBHEAD = re.compile(r"(?i)chapter\b.*|\[.*\]|\U0001F53B.*\U0001F53B")


def message_id(url):
    """The message number in a t.me link (https://t.me/RecordsBatch58ATM/1630 -> 1630); None when it is not one."""
    m = LINK.search(url or "")
    return int(m.group(3)) if m else None


def utf16_len(text):
    return len(text.encode("utf-16-le")) // 2


def parse(msg, channel=None):
    """{id, date, edit_date, title, text, sections: {pdfs|lectures|revisions: [item]}, media}: one list message.

    An item is {title, parts: [{label, url, post}]}. A line "- Spinal cord" starts an item and the lines under it
    ("part 1  part 2") are its parts; in the PDFs section a line that is itself a link ("- Part 2") is an item of one
    part. Links come from the message's link entities (the url is hidden behind the label), `?single` stripped."""
    text = msg.message or ""
    lines, pos = [], 0
    for ln in text.split("\n"):
        lines.append((pos, ln))
        pos += utf16_len(ln) + 1
    y1 = channel is not None and channel != CHANNEL
    bullets = BULLETS if y1 else ("-",)
    is_title = [l.strip().startswith(bullets) or bool(re.match(r"^\d+[.)]", l.strip())) for _, l in lines]
    plain = [i for i, (_, l) in enumerate(lines) if i > 0 and l.strip() and not is_title[i] and not l.strip().startswith(("➠", "➥"))]
    sec_at = []
    for i in plain:
        low = unicodedata.normalize("NFKC", lines[i][1]).lower()
        for name, key in SECTIONS + (SECTIONS_Y1 if y1 else ()) + (("notebook", "pdfs"),):
            if name in low and len(low) < 30:
                sec_at.append((lines[i][0], key))
                break  # one header, one section ("Mini Lectures" is not also "Lectures")
    if len(sec_at) < 2:
        # An older list (Mossafer's, Wagih's old data): the headers are not in plain English. A header with no numbered
        # line under it is the PDFs; the first numbered block is the lectures, the next the revisions, any more "other".
        sec_at, seen = [], []
        for n, i in enumerate(plain):
            end = plain[n + 1] if n + 1 < len(plain) else len(lines)
            numbered_under = any(re.match(r"^\d+[.)]", lines[j][1].strip()) for j in range(i + 1, end))
            key = "pdfs" if not numbered_under and not seen else ("lectures", "revisions", "other")[min(len(seen), 2)] if numbered_under else None
            if key:
                if numbered_under:
                    seen.append(key)
                sec_at.append((lines[i][0], key))
    sections = {k: [] for k in ("pdfs", "lectures", "minis", "revisions", "other")}
    items = {}
    for ent, label in msg.get_entities_text():
        url = getattr(ent, "url", None) or (label if type(ent).__name__ == "MessageEntityUrl" else None)
        if not url:
            continue
        section = next((k for o, k in reversed(sec_at) if o <= ent.offset), None)
        if section is None:
            continue
        li = max(i for i, (o, _) in enumerate(lines) if o <= ent.offset)
        owner = li
        while not is_title[owner] and owner > 0 and lines[owner - 1][1].strip() and not any(o == lines[owner][0] for o, _ in sec_at):
            owner -= 1  # a "part 1  part 2" line belongs to the "- title" line above it
        if not is_title[owner]:
            owner = li
        url = re.sub(r"\?single$", "", url.strip())
        part = {"label": label.strip(), "url": url, "post": message_id(url) if f"/{(channel or CHANNEL).lower()}/" in url.lower() + "/" else None}
        if owner not in items:
            line = lines[owner][1].strip()
            title = re.sub(r"^(?:-\s*|\d+[.)]\s*)", "", line).strip() if is_title[owner] else label.strip()
            if y1:
                title = line.lstrip("".join(BULLETS) + " ").strip() or label.strip()
            items[owner] = {"title": title, "parts": []}
            sections[section].append(items[owner])
        items[owner]["parts"].append(part)
    if y1:  # a sub-heading inside a section ("Chapter 1 (CHO)", a line between two red triangles) names its items' group
        heads = {o for o, _ in sec_at}
        for owner, it in items.items():
            for j in range(owner - 1, -1, -1):
                if lines[j][0] in heads:
                    break
                bare = lines[j][1].strip().lstrip("".join(BULLETS) + "# ").strip()
                if j not in items and SUBHEAD.fullmatch(bare):
                    it["group"] = bare.strip("🔻[] ").strip()
                    break
    title = next((ln.strip() for _, ln in lines if ln.strip()), "")
    return {"id": msg.id, "date": msg.date.isoformat() if msg.date else None,
            "edit_date": msg.edit_date.isoformat() if msg.edit_date else None,
            "title": unicodedata.normalize("NFKC", title), "text": text, "sections": sections,
            "media": type(msg.media).__name__ if msg.media else None}


def parse_post(msg):
    """What a linked post is: {id, date, kind, file_name, mime, size, duration, caption, youtube: [urls], album}."""
    d = getattr(msg.media, "document", None) if msg.media else None
    attrs = {type(a).__name__: a for a in (d.attributes if d else [])}
    name = attrs.get("DocumentAttributeFilename")
    av = attrs.get("DocumentAttributeAudio") or attrs.get("DocumentAttributeVideo")
    mime = d.mime_type if d else None
    text = msg.message or ""
    yt = re.findall(r"(?:https?://)?(?:www\.)?(?:youtu\.be/|youtube\.com/watch\?v=)[\w-]+(?:\?si=[\w-]+)?", text)
    for ent in msg.entities or []:
        u = getattr(ent, "url", None)
        if u and "youtu" in u:
            yt.append(u)
    kind = ("pdf" if mime == "application/pdf" else "video" if (mime or "").startswith("video") else
            "audio" if (mime or "").startswith("audio") else "file" if d else "youtube" if yt else "text" if text else "none")
    return {"id": msg.id, "date": msg.date.isoformat() if msg.date else None, "kind": kind,
            "file_name": name.file_name if name else None, "mime": mime, "size": getattr(d, "size", None),
            "duration": getattr(av, "duration", None), "caption": text,
            "youtube": sorted({u if u.startswith("http") else "https://" + u for u in yt}), "album": msg.grouped_id}


LINK_FIXES = OUT / "link_fixes.json"


def apply_link_fixes(list_id, d, channel=None):
    """The doctor's own wrong links, fixed by hand in sources/lists/link_fixes.json (owner, 2026-11-15: the site must be
    exact to the mother message). A fix is {"item", "label", "linked", "post", "why"}: the part `label` of `item` links
    post `linked`, but its post is `post` (read from the channel's captions). Applied only while the list still links the
    wrong post; once the channel fixes its link the fix stops matching. Each applied fix is noted in d["fixed"]."""
    key = str(list_id) if (channel or CHANNEL) == CHANNEL else f"{channel}/{list_id}"
    fixes = json.loads(LINK_FIXES.read_text(encoding="utf-8")).get(key, []) if LINK_FIXES.exists() else []
    d["fixed"] = []
    for fx in fixes:
        for sec in d["sections"].values():
            for it in sec:
                if it["title"].strip().lower() != fx["item"].strip().lower():
                    continue
                for part in it["parts"]:
                    if part["label"].strip().lower() == fx["label"].strip().lower() and part["post"] == fx["linked"]:
                        part.update(post=fx["post"], url=f"https://t.me/{channel or CHANNEL}/{fx['post']}", fixed_from=fx["linked"])
                        d["fixed"].append(f"{fx['item']} {fx['label']}: post {fx['linked']} -> {fx['post']}")
    return d


def twice_linked(d):
    """["item: post N linked twice"] for every item that links one post under two labels (a broken link in the list)."""
    out = []
    for sec in d["sections"].values():
        for it in sec:
            posts = [p["post"] for p in it["parts"] if p["post"]]
            out += [f"{it['title']}: post {x} linked twice" for x in sorted(set(posts)) if posts.count(x) > 1]
    return out


async def _fetch(ids, account="voter2", channel=None):
    sys.path.insert(0, r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\quizbot")
    from tg import connect
    client = await connect(account)
    out = {}
    try:
        ent = await client.get_entity(channel or CHANNEL)
        lists = {m.id: m for m in await client.get_messages(ent, ids=list(ids)) if m is not None}
        for i, m in lists.items():
            d = apply_link_fixes(i, parse(m, channel), channel)
            d["channel"] = channel or CHANNEL
            posts = {p["post"] for sec in d["sections"].values() for it in sec for p in it["parts"] if p["post"]}
            d["posts"] = {str(pm.id): parse_post(pm) for pm in await client.get_messages(ent, ids=sorted(posts)) if pm is not None}
            out[i] = d
    finally:
        await client.disconnect()
    return out


def list_dir(channel=None):
    """Where a channel's lists are saved: sources/lists/ for RecordsBatch58ATM (year 2), sources/lists/<channel>/ for
    any other channel (year 1: ZAG59_Anatomy, ZAG59_physio, ZAG59_Histo, ZAG59_bio; their list numbers repeat)."""
    return OUT if (channel or CHANNEL) == CHANNEL else OUT / channel


def fetch_many(ids, save=True, channel=None):
    """{id: list}: each list message with the posts it links, saved under sources/lists/<id>.json. The previous copy goes
    to <id>.prev.json when the list's links changed."""
    got = asyncio.run(_fetch(sorted(set(ids)), channel=channel))
    out = list_dir(channel)
    out.mkdir(parents=True, exist_ok=True)
    if save:
        for i, d in got.items():
            f = out / f"{i}.json"
            if f.exists():
                old = json.loads(f.read_text(encoding="utf-8"))
                if old.get("sections") != d["sections"]:
                    (out / f"{i}.prev.json").write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return got


async def _download(ids, out_dir, account="voter2", channel=None):
    sys.path.insert(0, r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\quizbot")
    from tg import connect
    client = await connect(account)
    got = {}
    try:
        ent = await client.get_entity(channel or CHANNEL)
        for m in await client.get_messages(ent, ids=list(ids)):
            if m is None or not m.media:
                continue
            d = Path(out_dir) / str(m.id)
            d.mkdir(parents=True, exist_ok=True)
            have = [f for f in d.glob("*.*") if not f.name.endswith(".partial")]
            got[m.id] = have[0] if have else Path(await client.download_media(m, file=str(d)))
    finally:
        await client.disconnect()
    return got


def download(ids, out_dir=ROOT / "sources" / "records", channel=None):
    """{post id: local file}: the posts' media (audio, video, pdf), read only. Already downloaded: kept. Another
    channel's posts (year 1 books, `-c ZAG59_Histo`) go to sources/lists_pdf/<channel>/<post>/."""
    if channel and channel != CHANNEL and out_dir == ROOT / "sources" / "records":
        out_dir = ROOT / "sources" / "lists_pdf" / channel
    return asyncio.run(_download(sorted(set(ids)), out_dir, channel=channel)) if ids else {}


def load(i, channel=None):
    f = list_dir(channel) / f"{i}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def ascii_label(s):
    """A label for printing. Arabic is shown as it is (owner, 2026-11-13: Claude reads Arabic; it used to be hidden)."""
    return s or ""


def show(i, channel=None):
    d = load(i, channel)
    if not d:
        print(f"{i}: not fetched")
        return
    print(f"{i}: {ascii_label(d['title'])}, edited {d['edit_date']}")
    for sec, items in d["sections"].items():
        print(f"  {sec}: {len(items)} items")
        for it in items:
            for p in it["parts"]:
                post = d["posts"].get(str(p["post"])) or {}
                print(f"    {ascii_label(it['title'])[:40]:<40} {ascii_label(p['label'])[:12]:<12} {p['post']} {post.get('kind')} "
                      f"{post.get('size') or ''} {post.get('duration') or ''} {(post.get('youtube') or [''])[0]}")


async def _info(ids, account="voter2"):
    sys.path.insert(0, r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\quizbot")
    from tg import connect
    client = await connect(account)
    try:
        ent = await client.get_entity(CHANNEL)
        return {m.id: parse_post(m) for m in await client.get_messages(ent, ids=list(ids)) if m is not None}
    finally:
        await client.disconnect()


def info(ids):
    """{post id: what the post is} (kind, size, duration, YouTube links) without downloading it."""
    return asyncio.run(_info(sorted(set(ids)))) if ids else {}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd, args = sys.argv[1], sys.argv[2:]
    channel = None                      # py tg_lists.py fetch -c ZAG59_Anatomy 39 40 41: another channel's lists
    if args[:1] == ["-c"]:
        channel, args = args[1], args[2:]
    ids = [int(x) for x in args]
    if cmd == "fetch":
        for i, d in fetch_many(ids, channel=channel).items():
            print(f"saved {i}: {sum(len(it['parts']) for s in d['sections'].values() for it in s)} links, {len(d['posts'])} posts")
    elif cmd == "text":  # the list message exactly as the doctor's channel shows it, then each linked post's caption
        for i in ids:
            d = load(i, channel)
            print(f"== {i} edited {d['edit_date']}\n{d['text']}\n-- posts")
            for k, p in d["posts"].items():
                print(f"{k} {p['kind']} {p.get('size') or ''} {p.get('file_name') or ''} | {(p.get('caption') or '').strip()[:120]}".replace("\n", " "))
    elif cmd == "download":  # post ids: the posts' files into sources/records/<post>/ (a list PDF the agent inspects by hand)
        for k, v in download(ids, channel=channel).items():
            print(k, v)
    elif cmd == "show":
        for i in ids:
            show(i, channel)

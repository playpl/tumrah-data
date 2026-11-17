"""The mother-message agent, code side: show a doctor's Telegram list to a reader, check the answer, keep the map.

    py -m spine mother render 1632        what a reader is shown (about 1 to 2K tokens)
    py -m spine mother job 1632 -r A      a ready fleet job folder (nothing is run)
    py -m spine mother run [list ids]     run the readers on the fleet, validate, cache the agreed map
    py -m spine mother diff               what changed since the map before (add, edit, delete); writes nothing
    py -m spine parity mother             the agent's map against the hand-written mother_lists.json

The reader decides only what needs reading: each link's role (lecture, mini, revision, ignore) and what a mini
lecture or revision covers. Code does the rest: a PDF or picture is never a lecture, a post the doctor linked
twice has one owner, chapter and name are the message's own words, lecture ids come from the existing lectures,
the output keeps today's mother_lists.json shape.
Shadow mode: nothing here writes modules/<m>/site/mother_lists.json; the agreed map goes to sources/mother/.
"""
import hashlib
import json
import re

from spine import ROOT, now, read_json, write_json

CHANNEL = "RecordsBatch58ATM"
LISTS = ROOT / "sources" / "lists"
CACHE = ROOT / "sources" / "mother" / CHANNEL
FIXES = ROOT / "sources" / "mother" / "fixes.json"
ROLES = ("lecture", "mini", "revision", "ignore")
NOT_A_RECORD = ("pdf", "file", "photo", "image", "text", None)
MAX_DRAFTS, MAX_SHARE = 3, 0.2
VERSION = 3                               # of links() and PROMPT: a new number makes every cached map stale
SECTION = {"pdfs": "PDFs", "lectures": "Lectures", "minis": "Mini lectures", "revisions": "Revisions", "other": "Other"}

PROMPT = """You read one Telegram message in which a doctor lists his lectures, and you fill a small table.
Do not open any file. Do not use tools. Do not start subagents. Reply with the answer lines only.

{rendered}

Write exactly one line per link, in link order, as JSON:
{{"link": <number>, "role": "lecture" | "mini" | "revision" | "ignore", "covers": [<link numbers>]}}

Rules:
- "lecture": a full lecture record (video, audio or YouTube). "mini": a short summary of ONE lecture.
  "revision": a revision of one or more lectures. "ignore": everything else (PDF, book, MCQ, picture, notes).
- A link whose post is a pdf, file or photo is always "ignore". A link marked WRONG LINK or MISSING POST is always "ignore".
- An item of the Lectures section that has no post yet is still a "lecture".
- Trust the caption over the section: a caption that says "revision" is a revision, one that says "mini" is a mini.
- covers: for a mini, the one lecture link it summarises. For a revision, every lecture link it revises: a
  revision named after one topic covers the lectures of that topic; a revision of the whole course (final,
  written) covers every lecture; a numbered revision ("Spinal cord 2 revision") covers only the lecture part
  with that number ("Spinal cord" Part 2). For a lecture or ignore: [].
Example: {{"link": 5, "role": "lecture", "covers": []}}
Example: {{"link": 12, "role": "revision", "covers": [5, 6, 7]}}
"""


def load(list_id):
    return read_json(LISTS / f"{list_id}.json")


def links(lst):
    """Every link of the message, section by section in the order tg_lists.parse kept:
    [{k, section, item, label, post, kind, size, caption, wrong, missing}].

    A list item with no link at all (the doctor has not posted it yet) is kept with post None.
    `missing` = the link names a post the channel does not have (the doctor's link to nothing).
    `wrong` = the k of the link that really owns the post, when the doctor linked one post twice: the owner is
    the link whose section fits the caption (a "revision" caption -> Revisions, "mini" -> Mini lectures, else
    Lectures); with no such link, the first one."""
    out = []
    for section, items in lst["sections"].items():
        for it in items:
            for p in (it.get("parts") or [{"label": it["title"], "post": None}]):
                post = lst["posts"].get(str(p.get("post"))) or {}
                out.append({"k": len(out) + 1, "section": section, "item": " ".join(it["title"].split()),
                            "label": " ".join((p.get("label") or "").split()).lstrip("-•–— "), "post": p.get("post"),
                            "kind": post.get("kind"), "size": post.get("size"),
                            "caption": " ".join((post.get("caption") or "").split())[:160], "wrong": None,
                            "missing": bool(p.get("post")) and str(p.get("post")) not in lst["posts"]})
    by_post = {}
    for l in out:
        if l["post"]:
            by_post.setdefault(l["post"], []).append(l)
    for same in by_post.values():
        if len(same) > 1:
            cap = same[0]["caption"].lower()
            fits = "revisions" if "revis" in cap else "minis" if "mini" in cap else "lectures"
            owner = next((l for l in same if l["section"] == fits), same[0])
            for l in same:
                if l is not owner:
                    l["wrong"] = owner["k"]
    return out


def render(lst):
    lines = [f"MESSAGE {lst['id']} (numbered lines)"]
    lines += [f"L{n} {line}" for n, line in enumerate(lst["text"].splitlines(), start=1) if line.strip()]
    lines.append("")
    lines.append("LINKS (in message order; `under` is the list item the link stands under)")
    for l in links(lst):
        size = f" {l['size'] / 1e6:.1f}MB" if l["size"] else ""
        what = f"post {l['post']} {l['kind'] or 'unknown'}{size}" if l["post"] else "no post yet"
        if l["missing"]:
            what = f"post {l['post']} MISSING POST (the channel has no such post)"
        lines.append(f"[{l['k']}] {SECTION.get(l['section'], l['section'])}: under \"{l['item']}\" label \"{l['label']}\" -> {what}"
                     + (f" caption \"{l['caption']}\"" if l["caption"] else "")
                     + (f" WRONG LINK (this post belongs to link {l['wrong']})" if l["wrong"] else ""))
    return "\n".join(lines)


def cache_key(lst):
    """sha12 of what a reader is shown and what code checks. The same key = no new read."""
    body = json.dumps([VERSION, lst["text"], lst["sections"],
                       {k: [p.get("kind"), p.get("size"), p.get("caption")] for k, p in sorted(lst["posts"].items())}],
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def parse(answer, lst):
    """({link number: {role, chapter, name, covers}}, [errors]) from a reader's JSON lines.

    The reader gives role and covers; chapter and name are the message's own words, set by `finish`."""
    out, errors = {}, []
    for raw in answer.splitlines():
        line = raw.strip().strip("`").rstrip(",")
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
            out[int(row["link"])] = {"role": row["role"], "covers": sorted({int(c) for c in row.get("covers") or []})}
        except (ValueError, KeyError, TypeError):
            errors.append(f"not a valid line: {line[:60]!r}")
    finish(out, lst)
    return out, errors + validate(out, lst)


def _key(s):
    return re.sub(r"\W+", " ", s or "").strip().lower()


def finish(m, lst):
    """Fill what code decides, in place: a wrong link or a link to a missing post is ignored; chapter = the list item a lecture stands under,
    or the chapter of the last lecture a mini or revision covers; name = the item's words, with the part number
    for an item that has several parts. A mini or revision that carries a lecture's own name (or a part number,
    for a mini) gets " (mini lecture)" / " revision", so that no two lessons of a doctor read the same."""
    ls = {l["k"]: l for l in links(lst)}
    for k, v in m.items():
        if k in ls and (ls[k]["wrong"] or ls[k]["missing"]):
            v["role"], v["covers"] = "ignore", []
    for k, v in m.items():
        l = ls.get(k) or {"item": "", "label": ""}
        part = re.fullmatch(r"(?i)part\s*(\d+)", l["label"])
        name = f"{l['item']} part {part.group(1)}" if part else (l["label"] or l["item"])
        v["name"] = name[:1].upper() + name[1:]
        v["chapter"] = l["item"] if v["role"] == "lecture" else ""
    lectures = {_key(v["name"]) for v in m.values() if v["role"] == "lecture"}
    for k, v in m.items():
        if v["role"] not in ("mini", "revision"):
            continue
        covered = [c for c in v["covers"] if c in m and m[c]["role"] == "lecture"]
        if covered:
            v["chapter"] = m[max(covered) if v["role"] == "revision" else covered[0]]["chapter"]
        if v["role"] == "mini" and "mini" not in v["name"].lower() \
                and (_key(v["name"]) in lectures or re.search(r"(?i)\bpart\s*\d", v["name"])):
            v["name"] += " (mini lecture)"
        if v["role"] == "revision" and _key(v["name"]) in lectures:
            v["name"] += " revision"
    return m


def validate(m, lst):
    """Every rule code can check. [] = the map is usable."""
    ls = {l["k"]: l for l in links(lst)}
    errors = [f"link {k} has no answer" for k in ls if k not in m] + [f"no link {k} in the message" for k in m if k not in ls]
    lectures = {k for k, v in m.items() if v["role"] == "lecture"}
    names = {}
    for k, v in sorted(m.items()):
        if k not in ls:
            continue
        if v["role"] not in ROLES:
            errors.append(f"link {k}: role {v['role']!r}")
        if v["role"] != "ignore" and ls[k]["post"] and ls[k]["kind"] in NOT_A_RECORD:
            errors.append(f"link {k}: a {ls[k]['kind'] or 'missing'} post cannot be a {v['role']}")
        if v["role"] != "ignore" and names.setdefault(_key(v["name"]), k) != k:
            errors.append(f"link {k}: the name {v['name']!r} is used twice")
        want = {"lecture": (0, 0), "ignore": (0, 0), "mini": (1, 1), "revision": (1, 99)}.get(v["role"], (0, 99))
        if not want[0] <= len(v["covers"]) <= want[1]:
            errors.append(f"link {k}: a {v['role']} covers {len(v['covers'])} lectures")
        if any(c not in lectures for c in v["covers"]):
            errors.append(f"link {k}: covers a link that is not a lecture of this message")
    return errors


def agree(a, b):
    """Link numbers on which two readers differ (role and covers; chapter and name come from code)."""
    def norm(v):
        return v["role"], tuple(sorted(v["covers"]))
    return sorted(k for k in set(a) | set(b) if k not in a or k not in b or norm(a[k]) != norm(b[k]))


def fixes(lst):
    """The hand fixes of this list (sources/mother/fixes.json), as {link number: {role, covers}}.

    A fix names its link by `post`, and what it covers by post number or, for a lecture with no post yet, by
    the list item's words. It is for what the message does not say (which lectures a mid-term revision
    revises), the same way sources/lists/link_fixes.json is for a doctor's wrong link."""
    ls = links(lst)
    out = {}
    for f in (read_json(FIXES) or {}).get(str(lst["id"])) or []:
        k = next((l["k"] for l in ls if l["post"] == f["post"] and not l["wrong"]), None)
        if k is None:
            continue
        covers = [next((l["k"] for l in ls if not l["wrong"] and (
            l["post"] == c if isinstance(c, int) else l["section"] == "lectures" and _key(l["item"]) == _key(c))), None)
            for c in f.get("covers") or []]
        out[k] = {"role": f["role"], "covers": sorted(c for c in covers if c)}
    return out


def apply_fixes(m, lst):
    """Lay the hand fixes over a reader's map and finish it again. Returns the link numbers that were fixed."""
    fx = fixes(lst)
    for k, f in fx.items():
        m[k] = {**m.get(k, {}), **f}
    finish(m, lst)
    return sorted(fx)


# --- lecture ids and the mother_lists.json shape ---------------------------------------------------------------
def lecture_index(lectures_dir=None):
    """Keys that find an existing lecture: ("post", n), ("yt", video id), ("title", doctor, lowered title).

    A held duplicate (lecture.json "hold": "duplicate: same lecture as cns-074 ...") answers with its twin's id."""
    out = {}
    for f in sorted((lectures_dir or ROOT / "lectures").glob("*/lecture.json")):
        d = read_json(f)
        twin = re.search(r"\b(?:as|to) ([a-z0-9]+-\d+)\b", d.get("hold") or "")
        lid = twin.group(1) if twin else d["id"]
        src = d.get("source") or {}
        m = re.search(r"/(\d+)$", src.get("telegram") or "")
        if m:
            out.setdefault(("post", int(m.group(1))), lid)
        y = re.search(r"(?:youtu\.be/|v=)([\w-]{6,})", src.get("youtube") or "")
        if y:
            out.setdefault(("yt", y.group(1)), lid)
        out.setdefault(("title", d.get("doctor"), (d.get("title") or "").strip().lower()), lid)
    return out


def lecture_id(link, name, doctor, lst, index):
    post = lst["posts"].get(str(link["post"])) or {}
    for url in post.get("youtube") or []:
        y = re.search(r"(?:youtu\.be/|v=)([\w-]{6,})", url)
        if y and ("yt", y.group(1)) in index:
            return index[("yt", y.group(1))]
    return index.get(("post", link["post"])) or index.get(("title", doctor, name.strip().lower()))


def to_doctor(lst, m, doctor, subject, index):
    """One doctor's block in the shape of mother_lists.json: chapters in message order; under each its
    lectures, then its mini lectures, then the revisions that end there."""
    ls = {l["k"]: l for l in links(lst)}
    ids = {k: lecture_id(ls[k], v["name"], doctor, lst, index) for k, v in m.items() if v["role"] != "ignore"}
    chapters, order = {}, []
    for k in sorted(m):
        if m[k]["role"] == "lecture":
            if m[k]["chapter"] not in chapters:
                order.append(m[k]["chapter"])
            chapters.setdefault(m[k]["chapter"], {"lecture": [], "mini": [], "revision": []})["lecture"].append(k)
    for k in sorted(m):
        v = m[k]
        if v["role"] in ("mini", "revision") and v["chapter"] in chapters:
            chapters[v["chapter"]][v["role"]].append(k)
    out = []
    for title in order:
        items = []
        for role in ("lecture", "mini", "revision"):
            for k in chapters[title][role]:
                row = {"id": ids[k], "name": m[k]["name"]}
                if role != "lecture":
                    row["kind"] = "summary" if role == "mini" else "revision"
                    row["covers"] = [ids[c] for c in sorted(m[k]["covers"])]
                row["post"] = ls[k]["post"]
                items.append(row)
        out.append({"title": title, "items": items})
    return {"doctor": doctor, "list": lst["id"], "subject": subject, "chapters": out}


# --- cache and diff ---------------------------------------------------------------------------------------------
def history(list_id):
    """Every cached map of a list, oldest first."""
    rows = [read_json(f) for f in (CACHE / str(list_id)).glob("*.json")]
    return sorted(rows, key=lambda r: r["at"])


def cached(list_id, sha=None):
    """The newest agreed map of a list (or the one with this sha): {sha, at, edit_date, map, posts, by} or None."""
    rows = [r for r in history(list_id) if not sha or r["sha"] == sha]
    return rows[-1] if rows else None


def save(lst, m, by, fixed=()):
    row = {"list": lst["id"], "sha": cache_key(lst), "version": VERSION, "at": now(), "edit_date": lst.get("edit_date"),
           "map": {str(k): v for k, v in sorted(m.items())}, "posts": {str(l["k"]): l["post"] for l in links(lst)},
           "by": by, "fixed": list(fixed)}
    write_json(CACHE / str(lst["id"]) / f"{row['sha']}.json", row)
    return row


def records(row):
    """{post: {role, chapter, name, covers (posts)}} of a cached map: what the site mirrors."""
    post = {int(k): p for k, p in row["posts"].items()}
    return {post[int(k)]: {"role": v["role"], "chapter": v["chapter"], "name": v["name"],
                           "covers": sorted(post[c] for c in v["covers"] if post.get(c))}
            for k, v in row["map"].items() if v["role"] != "ignore" and post.get(int(k))}


def diff(prev, new, prev_sizes=None, new_sizes=None):
    """[{"change": add|edit|media_changed|delete, "post", ...}] between two cached maps, keyed by post."""
    a, b = records(prev) if prev else {}, records(new)
    out = [{"change": "add", "post": p, **b[p]} for p in sorted(set(b) - set(a))]
    out += [{"change": "delete", "post": p, **a[p]} for p in sorted(set(a) - set(b))]
    for p in sorted(set(a) & set(b)):
        fields = [f for f in ("role", "chapter", "name", "covers") if a[p][f] != b[p][f]]
        if fields:
            out.append({"change": "edit", "post": p, "fields": fields, **b[p]})
        if prev_sizes and new_sizes and prev_sizes.get(p) != new_sizes.get(p):
            out.append({"change": "media_changed", "post": p, **b[p]})
    return out


def held(changes, lessons_before, minutes_between_fetches=0):
    """Why a diff may not be applied by itself ("" = it may). Deletions draft lessons on the live site, so a
    big one, or one seen by a single fetch, waits for the owner (a Today card)."""
    drafts = sum(1 for c in changes if c["change"] == "delete")
    if drafts and minutes_between_fetches < 10:
        return "a deletion needs two fetches at least 10 minutes apart that both show it"
    if drafts > MAX_DRAFTS or (lessons_before and drafts / lessons_before > MAX_SHARE):
        return f"{drafts} of {lessons_before} lessons would be drafted: held for the owner"
    return ""

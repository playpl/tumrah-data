"""The mother-message agent, code side: show a doctor's Telegram list to a reader, check the answer, keep the map.

    py -m spine mother render 1632        what a reader is shown (about 1 to 2K tokens)
    py -m spine mother job 1632 -r A      a ready fleet job folder (nothing is run)
    py -m spine mother run [list ids]     run the readers on the fleet, validate, cache the agreed map
    py -m spine mother diff --dry         what changed since the cached map (add, edit, delete)
    py -m spine parity mother             the agent's map against the hand-written mother_lists.json

The reader decides only what needs reading: each link's role (lecture, mini, revision, ignore), its chapter, its
name and what a mini lecture or revision covers. Code does the rest: a PDF or picture is never a lecture, links
are counted, lecture ids come from the existing lectures, the output keeps today's mother_lists.json shape.
Shadow mode: nothing here writes modules/<m>/site/mother_lists.json; the agreed map goes to sources/mother/.
"""
import hashlib
import json
import re

from spine import ROOT, now, read_json, write_json

CHANNEL = "RecordsBatch58ATM"
LISTS = ROOT / "sources" / "lists"
CACHE = ROOT / "sources" / "mother" / CHANNEL
ROLES = ("lecture", "mini", "revision", "ignore")
NOT_A_RECORD = ("pdf", "file", "photo", "image", "text", None)
MAX_DRAFTS, MAX_SHARE = 3, 0.2

PROMPT = """You read one Telegram message in which a doctor lists his lectures, and you fill a small table.
Do not open any file. Do not use tools. Do not start subagents. Reply with the answer lines only.

{rendered}

Write exactly one line per link, in link order, as JSON:
{{"link": <number>, "role": "lecture" | "mini" | "revision" | "ignore", "chapter": "<text>", "name": "<text>", "covers": [<link numbers>]}}

Rules:
- "lecture": a full lecture record (video, audio or YouTube). "mini": a short summary of ONE lecture.
  "revision": a revision of one or more lectures. "ignore": everything else (PDF, book, MCQ, picture, notes).
- A link whose post is a pdf, file or photo is always "ignore".
- chapter: for a lecture, the list item it stands under, in the message's own words (the item "- Spinal cord"
  with Part 1, Part 2 gives chapter "Spinal cord" for each part). For a mini or a revision, the chapter of
  the lecture it covers. For ignore: "".
- name: the item's words; add the part when an item has several parts ("Spinal cord part 1").
- covers: for a mini, the one lecture link it summarises; for a revision, every lecture link it revises;
  for a lecture or ignore: [].
Example: {{"link": 5, "role": "lecture", "chapter": "Spinal cord", "name": "Spinal cord part 1", "covers": []}}
Example: {{"link": 12, "role": "revision", "chapter": "Spinal cord", "name": "Spinal revision", "covers": [5, 6, 7]}}
"""


def load(list_id):
    return read_json(LISTS / f"{list_id}.json")


def links(lst):
    """Every link of the message in message order: [{k, section, item, label, post, kind, size, caption}].

    A list item with no link at all (the doctor has not posted it yet) is kept with post None."""
    out = []
    for section, items in lst["sections"].items():
        for it in items:
            for p in (it.get("parts") or [{"label": it["title"], "post": None}]):
                post = lst["posts"].get(str(p.get("post"))) or {}
                out.append({"section": section, "item": it["title"].strip(), "label": (p.get("label") or "").strip(),
                            "post": p.get("post"), "kind": post.get("kind"), "size": post.get("size"),
                            "caption": " ".join((post.get("caption") or "").split())[:90]})
    at = {}                                   # message order: by where the item's words stand in the text
    for l in out:
        at[id(l)] = lst["text"].find(l["item"])
    out.sort(key=lambda l: (at[id(l)] if at[id(l)] >= 0 else 10 ** 9))
    for k, l in enumerate(out, start=1):
        l["k"] = k
    return out


def render(lst):
    lines = [f"MESSAGE {lst['id']} (numbered lines)"]
    lines += [f"L{n} {line}" for n, line in enumerate(lst["text"].splitlines(), start=1) if line.strip()]
    lines.append("")
    lines.append("LINKS (in message order; `under` is the list item the link stands under)")
    for l in links(lst):
        size = f" {l['size'] / 1e6:.1f}MB" if l["size"] else ""
        what = f"post {l['post']} {l['kind'] or 'unknown'}{size}" if l["post"] else "no post yet"
        lines.append(f"[{l['k']}] under \"{l['item']}\" label \"{l['label']}\" -> {what}"
                     + (f" caption \"{l['caption']}\"" if l["caption"] else ""))
    return "\n".join(lines)


def cache_key(lst):
    """sha12 of what a reader is shown and what code checks. The same key = no new read."""
    body = json.dumps([lst["text"], lst["sections"], {k: [p.get("kind"), p.get("size"), p.get("caption")]
                                                      for k, p in sorted(lst["posts"].items())}],
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def parse(answer, lst):
    """({link number: {role, chapter, name, covers}}, [errors]) from a reader's JSON lines."""
    out, errors = {}, []
    for raw in answer.splitlines():
        line = raw.strip().strip("`").rstrip(",")
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
            k = int(row["link"])
            out[k] = {"role": row["role"], "chapter": str(row.get("chapter") or "").strip(),
                      "name": str(row.get("name") or "").strip(), "covers": [int(c) for c in row.get("covers") or []]}
        except (ValueError, KeyError, TypeError):
            errors.append(f"not a valid line: {line[:60]!r}")
    return out, errors + validate(out, lst)


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
            errors.append(f"link {k}: a {ls[k]['kind']} post cannot be a {v['role']}")
        if v["role"] != "ignore":
            if not v["name"] or not v["chapter"]:
                errors.append(f"link {k}: a {v['role']} needs a chapter and a name")
            if names.setdefault(v["name"].lower(), k) != k:
                errors.append(f"link {k}: the name {v['name']!r} is used twice")
        want = {"lecture": (0, 0), "ignore": (0, 0), "mini": (1, 1), "revision": (1, 99)}.get(v["role"], (0, 99))
        if not want[0] <= len(v["covers"]) <= want[1]:
            errors.append(f"link {k}: a {v['role']} covers {len(v['covers'])} lectures")
        if any(c not in lectures for c in v["covers"]):
            errors.append(f"link {k}: covers a link that is not a lecture of this message")
        if v["role"] in ("mini", "revision") and v["covers"] and all(c in m for c in v["covers"]) \
                and v["chapter"] not in {m[c]["chapter"] for c in v["covers"]}:
            errors.append(f"link {k}: its chapter is not the chapter of a lecture it covers")
    order = [m[k]["chapter"] for k in sorted(lectures) if k in ls]
    firsts = list(dict.fromkeys(order))
    if any(order[i] != order[i - 1] and order[i] in order[:i] for i in range(1, len(order))):
        errors.append(f"chapters are not in one piece each: {firsts}")
    return errors


def agree(a, b):
    """Link numbers on which two readers differ (role, chapter, covers; names may differ in spelling)."""
    def norm(v):
        return (v["role"], re.sub(r"\W+", "", v["chapter"]).lower(), tuple(sorted(v["covers"])))
    return sorted(k for k in set(a) | set(b) if k not in a or k not in b or norm(a[k]) != norm(b[k]))


# --- lecture ids and the mother_lists.json shape ---------------------------------------------------------------
def lecture_index(lectures_dir=None):
    """Keys that find an existing lecture: ("post", n), ("yt", video id), ("title", doctor, lowered title)."""
    out = {}
    for f in sorted((lectures_dir or ROOT / "lectures").glob("*/lecture.json")):
        d = read_json(f)
        src = d.get("source") or {}
        m = re.search(r"/(\d+)$", src.get("telegram") or "")
        if m:
            out.setdefault(("post", int(m.group(1))), d["id"])
        y = re.search(r"(?:youtu\.be/|v=)([\w-]{6,})", src.get("youtube") or "")
        if y:
            out.setdefault(("yt", y.group(1)), d["id"])
        out.setdefault(("title", d.get("doctor"), (d.get("title") or "").strip().lower()), d["id"])
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
        if v["role"] in ("mini", "revision") and v["covers"]:
            home = m[max(v["covers"])]["chapter"] if v["role"] == "revision" else m[v["covers"][0]]["chapter"]
            chapters[home][v["role"]].append(k)
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
def cached(list_id, sha=None):
    """The newest agreed map of a list (or the one with this sha): {sha, at, edit_date, map, by} or None."""
    files = sorted((CACHE / str(list_id)).glob("*.json"), key=lambda f: f.stat().st_mtime)
    if sha:
        files = [f for f in files if f.stem == sha]
    return read_json(files[-1]) if files else None


def save(lst, m, by):
    row = {"list": lst["id"], "sha": cache_key(lst), "at": now(), "edit_date": lst.get("edit_date"),
           "map": {str(k): v for k, v in m.items()}, "posts": {str(l["k"]): l["post"] for l in links(lst)}, "by": by}
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

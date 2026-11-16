"""Checks the hand-written mother_lists.json against each doctor's saved Telegram list message (owner, 2026-11-15:
"make it exact to the mother message"). Reads only; the hand file is still written by hand.

    py mother_check.py [module]      every difference, one line each; "exact" when there is none

Checked per doctor: the chapters are the list's lecture items, in list order and with the list's words; every post the
list links (lecture parts, mini lectures, revisions; PDFs never) is an item of the hand file; every hand item's post is
linked by the list. Hand link fixes (sources/lists/link_fixes.json) are already applied in the saved list.
"""
import json
import re
import sys
from pathlib import Path

import tg_lists

ROOT = Path(__file__).resolve().parent


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("-", " ")).strip().lower()


def check_doctor(doc, lst):
    out = []
    who = doc["doctor"]
    want = [it["title"].strip() for it in lst["sections"].get("lectures", [])]
    have = [ch["title"] for ch in doc["chapters"]]
    lecture_ch = [t for t in have if norm(t) in {norm(w) for w in want}]
    for w in want:
        if norm(w) not in {norm(h) for h in have}:
            out.append(f"{who}: list item '{w}' has no chapter")
        elif w not in have:
            out.append(f"{who}: chapter '{next(h for h in have if norm(h) == norm(w))}' is '{w}' in the list")
    if [norm(t) for t in lecture_ch] != [norm(w) for w in want if norm(w) in {norm(h) for h in have}]:
        out.append(f"{who}: chapter order {lecture_ch} is not the list's order {want}")
    items = {it.get("post"): (ch["title"], it) for ch in doc["chapters"] for it in ch["items"]}
    linked = set()
    for sec in ("lectures", "minis", "revisions"):
        for it in lst["sections"].get(sec, []):
            for p in it["parts"]:
                post = lst["posts"].get(str(p["post"])) or {}
                if not p["post"] or post.get("kind") in ("pdf", "file"):
                    continue
                linked.add(p["post"])
                if p["post"] not in items:
                    out.append(f"{who}: {sec[:-1]} '{it['title']}' {p['label']} (post {p['post']}) is not in the hand file")
                elif sec == "lectures" and norm(items[p["post"]][0]) != norm(it["title"]):
                    out.append(f"{who}: post {p['post']} sits under '{items[p['post']][0]}', the list puts it under '{it['title']}'")
    for post, (ch, it) in items.items():
        if post is not None and post not in linked:  # null: the list item has no link (noted in the hand file)
            out.append(f"{who}: {it['id']} '{it['name']}' (post {post}) is not linked by the list")
    return out


def check(module="year2-cns"):
    hand = json.loads((ROOT / "modules" / module / "site" / "mother_lists.json").read_text(encoding="utf-8"))
    out = []
    for doc in hand["doctors"]:
        lst = tg_lists.load(doc["list"])
        if not lst:
            out.append(f"{doc['doctor']}: list {doc['list']} not fetched")
            continue
        out += check_doctor(doc, lst)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    lines = check(*sys.argv[1:])
    print("\n".join(lines) if lines else "exact")

"""The mother-message flow inside Update data (year 2), still in shadow: the hand file stays what site_lessons reads.

    py -m spine mother flow [--dry]

1. Two Gemini web readers (4 Hydrogen) re-read only the lists whose message changed (`mother run --year 2`; the cache key is the
   message's sha, so an unchanged list costs nothing).
2. The agent's whole file in the hand file's shape: `modules/year2-cns/site/mother_lists.agent.json`.
3. ADD ONLY: a lecture, mini lecture or revision in the agent's map that the hand file lacks is added under its
   chapter (a new chapter goes where the list has it). Nothing in the hand file is changed or removed here.
4. Edits and deletions between the last two cached maps of a list are REPORTED with the hold rule
   (`mother.held`: a deletion needs two fetches 10 minutes apart; a big one waits for the owner). Applying them to
   the site needs the website's draft + undo (W1, W2): not built.
5. `parity mother` must stay exact; any difference is printed.
When `spine.config()["mother"] == "primary"`, step 3 becomes "the agent's file replaces the hand file" (old file
kept in modules/year2-cns/old/). Default: shadow.
"""
import argparse
import json
import shutil
import time

from spine import ROOT, config, read_json, write_json
from spine.tg import mother

HAND = ROOT / "modules" / "year2-cns" / "site" / "mother_lists.json"
AGENT = HAND.with_name("mother_lists.agent.json")


def save_hand(data):
    """The hand file in its own layout (indent 1, real letters, a newline at the end)."""
    HAND.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def year2_doctors():
    t = read_json(mother.TREES)["year2"]
    out = []
    for d in t["doctors"]:
        if d.get("skip") or not d.get("site"):
            continue
        lst = d.get("new") or d.get("old")
        if lst:
            out.append((d["site"], d["subject"], lst))
    return out


def agent_file(index=None):
    """{"_about", "doctors": [...]} from the cached maps; doctors in the hand file's order, new ones after."""
    index = index or mother.lecture_index()
    hand = read_json(HAND, {"doctors": []})
    order = [d["doctor"] for d in hand["doctors"]]
    blocks, missing = {}, []
    for site, subject, lst_id in year2_doctors():
        lst = mother.load(lst_id)
        row = mother.cached(lst_id, mother.cache_key(lst)) if lst else None
        if not row:
            missing.append(f"{site} (list {lst_id}): no agreed map for the current message")
            continue
        m = {int(k): v for k, v in row["map"].items()}
        blocks[site] = mother.to_doctor(lst, m, site, subject, index)
    doctors = [blocks[d] for d in order if d in blocks] + [b for d, b in blocks.items() if d not in order]
    return {"_about": "Made by the mother agent (spine/tg/flow.py) from the cached maps; shadow copy, not read by "
                      "site_lessons.py.", "doctors": doctors}, missing


def add_only(hand, agent):
    """Items of the agent's file the hand file lacks, added in place (hand is changed). Returns report lines."""
    out = []
    have = {it["id"] for d in hand["doctors"] for c in d["chapters"] for it in c["items"]}
    by_doc = {d["doctor"]: d for d in hand["doctors"]}
    for a in agent["doctors"]:
        h = by_doc.get(a["doctor"])
        if h is None:
            hand["doctors"].append(json.loads(json.dumps(a)))
            out.append(f"{a['doctor']}: new doctor, {sum(len(c['items']) for c in a['chapters'])} items added")
            continue
        for ci, c in enumerate(a["chapters"]):
            new = [it for it in c["items"] if it["id"] and it["id"] not in have]
            if not new:
                continue
            hc = next((x for x in h["chapters"] if x["title"].strip().lower() == c["title"].strip().lower()), None)
            if hc is None:                                  # a new chapter: after the chapter that precedes it
                prev = {x["title"].strip().lower() for x in a["chapters"][:ci]}
                at = max([i + 1 for i, x in enumerate(h["chapters"]) if x["title"].strip().lower() in prev] or [len(h["chapters"])])
                hc = {"title": c["title"], "items": []}
                h["chapters"].insert(at, hc)
            for it in new:
                hc["items"].append(dict(it))
                have.add(it["id"])
                out.append(f"{a['doctor']}: added {it['id']} '{it['name']}' under '{c['title']}'")
    return out


def changes(year=2):
    """Report lines: edits and deletions between the last two cached maps of every list, with the hold rule."""
    out = []
    for site, subject, lst_id in year2_doctors():
        rows = mother.history(lst_id)
        if len(rows) < 2:
            continue
        ch = [c for c in mother.diff(rows[-2], rows[-1]) if c["change"] != "add"]
        if not ch:
            continue
        before = len(mother.records(rows[-2]))
        why = mother.held(ch, before)
        out.append(f"{site} (list {lst_id}): {len(ch)} edit/delete since the map of {rows[-2]['at']}"
                   + (f"; HELD: {why}" if why else "; not applied (site draft + undo not built)"))
        out += [f"    {c['change']} post {c['post']} {c['name']!r}" for c in ch[:6]]
    return out


def run(dry=False, read=True, say=print):
    lines = []
    if read and not dry:
        from spine.tg import cli
        a = argparse.Namespace(lists=[], year=2, again=False)
        cli._run(a)
    agent, missing = agent_file()
    lines += [f"no map: {m}" for m in missing]
    if not dry:
        write_json(AGENT, agent)
    hand = read_json(HAND)
    if config().get("mother") == "primary":
        if not dry and not missing:
            old = ROOT / "modules" / "year2-cns" / "old" / f"mother_lists_before_agent_{time.strftime('%Y-%m-%d_%H%M')}.json"
            old.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HAND, old)
            save_hand({**agent, "_about": hand.get("_about")})
            lines.append("primary: the agent's file replaced the hand file")
    else:
        added = add_only(hand, agent)
        if added and not dry:
            save_hand(hand)
        lines += added or ["hand file: nothing to add"]
    lines += changes()
    import contextlib
    import io
    from spine.parity import mother as parity
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        parity.run(argparse.Namespace(module="year2-cns", show=3))
    got = buf.getvalue().splitlines()
    return lines + [ln for ln in got if not ln.endswith(": exact")]


def cli_run(a):
    for line in run(dry=a.dry, read=not a.no_read):
        print(line)
    return 0


def add(sub):
    p = sub.add_parser("flow", help="re-read changed lists, add new items to the hand file, report the rest")
    p.add_argument("--dry", action="store_true")
    p.add_argument("--no-read", action="store_true", help="use the cached maps only (no Gemini read)")
    p.set_defaults(run=cli_run)

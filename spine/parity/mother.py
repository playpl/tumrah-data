"""py -m spine parity mother: the agent's cached maps against the hand-written mother_lists.json.

The mother agent goes from shadow to primary only when this prints "exact" for every doctor.
"""
import re

from spine import ROOT, read_json
from spine.tg import mother


def _norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def compare(hand, agent):
    """Differences between one doctor's hand block and the agent's block, as lines."""
    out = []
    ht, at = [c["title"] for c in hand["chapters"]], [c["title"] for c in agent["chapters"]]
    if [_norm(t) for t in ht] != [_norm(t) for t in at]:
        out.append(f"chapters: hand {ht} / agent {at}")
    hi = {it["id"]: (c["title"], it) for c in hand["chapters"] for it in c["items"]}
    ai = {it["id"]: (c["title"], it) for c in agent["chapters"] for it in c["items"]}
    for lid in sorted(set(hi) | set(ai), key=str):
        if lid not in ai:
            out.append(f"{lid} '{hi[lid][1]['name']}' is missing from the agent's map")
        elif lid not in hi:
            out.append(f"{lid} '{ai[lid][1]['name']}' (post {ai[lid][1].get('post')}) is not in the hand file")
        else:
            (hc, h), (ac, a) = hi[lid], ai[lid]
            for what, x, y in (("chapter", _norm(hc), _norm(ac)), ("name", _norm(h["name"]), _norm(a["name"])),
                               ("kind", h.get("kind", "lesson"), a.get("kind", "lesson")),
                               ("covers", sorted(h.get("covers") or []), sorted(a.get("covers") or [])),
                               ("post", h.get("post"), a.get("post"))):
                if x != y:
                    out.append(f"{lid} {what}: hand {x!r} / agent {y!r}")
    order = [[it["id"] for it in c["items"]] for c in hand["chapters"]]
    if not out and order != [[it["id"] for it in c["items"]] for c in agent["chapters"]]:
        out.append("same items, another order inside a chapter")
    return out


def run(a):
    hand = read_json(ROOT / "modules" / a.module / "site" / "mother_lists.json")
    index, exact = mother.lecture_index(), 0
    for doc in hand["doctors"]:
        lst = mother.load(doc["list"])
        row = mother.cached(doc["list"], mother.cache_key(lst)) if lst else None
        if not row:
            print(f"{doc['doctor']} (list {doc['list']}): no agent map yet")
            continue
        m = {int(k): v for k, v in row["map"].items()}
        diffs = compare(doc, mother.to_doctor(lst, m, doc["doctor"], doc["subject"], index))
        exact += not diffs
        print(f"{doc['doctor']} (list {doc['list']}): " + ("exact" if not diffs else f"{len(diffs)} differences"))
        for d in diffs[:a.show]:
            print(f"    {d}")
    print(f"parity mother: {exact} of {len(hand['doctors'])} doctors exact")
    return 0 if exact == len(hand["doctors"]) else 1


def add(sub):
    p = sub.add_parser("mother", help="agent maps against the hand-written mother_lists.json")
    p.add_argument("module", nargs="?", default="year2-cns")
    p.add_argument("--show", type=int, default=6, help="differences printed per doctor")
    p.set_defaults(run=run)

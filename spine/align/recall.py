"""`py -m spine p1 recall <module>`: how much code proves, and whether a reader's short list holds the answer.

Run before any fleet job is queued. The old links (lifted to sentences) are the gold; they are noisy for
`reworded`, so the numbers are a floor. Gate (PLAN.md decision 8): the gold sentence must be inside the window's
candidate list for at least 95% of the `reworded` sentences, else an embedding stage is needed.
"""
import bisect
from collections import Counter

from spine import text as T
from spine.align import old, prefilter
from spine.books import split

GATE = 0.95
WORST = {"same": 0, "partial": 1, "reworded": 2}


def canonical(old_id, names, aliases):
    """The split book an old book id belongs to (an alias, or an earlier partial of the same doctor's book)."""
    if old_id in aliases:
        return aliases[old_id][0]
    if old_id in names:
        return old_id
    doctor, subject = old_id.split("-")[0], old.subject_of(old_id)
    return next((n for n in names if n.split("-")[0] == doctor and old.subject_of(n) == subject), None)


def book_items(module, book, H):
    """The book's content sentences as tier items, with their page's lesson scope."""
    sents = [s for s in split.load(module, book) if s["kind"] != "not_content"]
    pages = {}
    for s in sents:
        pages.setdefault(s["page"], []).append(s["text"])
    order = sorted(pages)
    scopes = dict(zip(order, H.page_lessons([" ".join(pages[p]) for p in order], old.subject_of(book))))
    return sents, [{"text": s["text"], "scope": scopes[s["page"]]} for s in sents]


def gold_of(module, book, sents, H, names, aliases, old_books, rows):
    """{sentence number: (handout positions, match type)} from the old blocks that sit inside each sentence."""
    keys = [T.word_key(s["text"]) for s in sents]
    starts, joined = [], ""
    for k in keys:
        starts.append(len(joined))
        joined += k
    by_page = {}
    for n, s in enumerate(sents):
        by_page.setdefault(s["page"], []).append(n)
    gold = {}
    for name, pages in old_books.items():
        if canonical(name, names, aliases) != book:
            continue
        offset = 0 if name == book else aliases[name][1] if name in aliases else None
        for page, blocks in pages:
            for b in blocks:
                if b["match"] not in WORST or not b.get("line_ids"):
                    continue
                key, where = T.word_key(b["text"]), None
                if len(key) >= 12:
                    at = joined.find(key)
                    if at >= 0 and joined.find(key, at + 1) < 0:
                        where = bisect.bisect_right(starts, at) - 1
                if where is None and offset is not None and key:
                    on_page = [n for n in by_page.get(page + offset, []) if key in keys[n]]
                    where = on_page[0] if len(on_page) == 1 else None
                target = old.lift(b["line_ids"], rows, H)
                if where is not None and target:
                    had = gold.get(where, (set(), "same"))
                    gold[where] = (had[0] | target, max(had[1], b["match"], key=WORST.get))
    return gold


def measure(module, only=None):
    H = prefilter.Handout(module)
    aliases, rows, old_books = split.dedupe(module), old.row_map(module), old.old_books(module)
    names = [b for b in split.books(module) if b not in aliases]
    out = {"books": {}, "tier": Counter(), "tier_ok": Counter(), "open": Counter(), "hit": Counter(),
           "scope": Counter(), "scope_ok": Counter(), "windows": 0, "cands": 0, "chars": 0, "items": 0, "coded": 0}
    for book in names:
        if only and book != only:
            continue
        sents, items = book_items(module, book, H)
        res = prefilter.code_tiers(items, H)
        gold = gold_of(module, book, sents, H, names, aliases, old_books, rows)
        wins = prefilter.windows(len(items), res)
        seen = {}
        for w in wins:
            cands = prefilter.candidates(items, res, w, H)
            out["windows"] += 1
            out["cands"] += len(cands)
            out["chars"] += (900 + sum(len(H.sents[n]["text"]) + 6 for n in cands)
                             + sum(len(items[i]["text"]) + 6 for i in w))
            for i in w:
                if not res[i] and i in gold:
                    seen[i] = seen.get(i, False) or bool(gold[i][0] & set(cands))
        for i, (pos, kind) in gold.items():
            out["scope"][kind] += 1
            out["scope_ok"][kind] += any(H.lesson[n] in items[i]["scope"] for n in pos)
            if res[i]:
                out["tier"][res[i][0]] += 1
                out["tier_ok"][res[i][0]] += bool(set(res[i][1]) & pos)
            else:
                out["open"][kind] += 1
                out["hit"][kind] += seen.get(i, False)
        coded = sum(1 for r in res if r)
        out["items"] += len(items)
        out["coded"] += coded
        out["books"][book] = {"sentences": len(items), "code": coded, "windows": len(wins), "gold": len(gold)}
    return out


def report(m):
    lines = ["PHASE 1 RECALL (no fleet job is queued by this command)"]
    for book, b in m["books"].items():
        lines.append(f"  {book:<22} {b['sentences']:>5} content sentences, code accepts {b['code']:>5} "
                     f"({b['code'] / max(b['sentences'], 1):.0%}), {b['windows']:>4} fleet windows, "
                     f"{b['gold']:>5} with an old link to compare")
    lines.append(f"  all books: {m['items']:,} sentences, code accepts {m['coded']:,} ({m['coded'] / max(m['items'], 1):.0%}), "
                 f"{m['windows']:,} windows for the rest")
    lines.append("code tiers against the old links:")
    for tier in ("A1", "A2", "A3", "A4"):
        if m["tier"][tier]:
            lines.append(f"  {tier}: {m['tier'][tier]:>5,} with an old link, {m['tier_ok'][tier]:>5,} agree "
                         f"({m['tier_ok'][tier] / m['tier'][tier]:.1%})")
    lines.append("page scope (old link's lesson is in the page's lesson scope):")
    for kind in WORST:
        if m["scope"][kind]:
            lines.append(f"  {kind:<9} {m['scope_ok'][kind]:>5,} of {m['scope'][kind]:>5,} "
                         f"({m['scope_ok'][kind] / m['scope'][kind]:.1%})")
    lines.append("open sentences: the old link's sentence is in the window's candidate list:")
    for kind in WORST:
        if m["open"][kind]:
            lines.append(f"  {kind:<9} {m['hit'][kind]:>5,} of {m['open'][kind]:>5,} ({m['hit'][kind] / m['open'][kind]:.1%})")
    if m["windows"]:
        lines.append(f"windows: {m['cands'] / m['windows']:.0f} candidates and about {m['chars'] / m['windows'] / 4:,.0f} "
                     f"tokens each; one reader over everything is about {m['chars'] / 4 / 1e6:.2f}M tokens")
    rew = m["hit"]["reworded"] / m["open"]["reworded"] if m["open"]["reworded"] else 1.0
    lines.append(f"GATE (reworded >= {GATE:.0%}): {rew:.1%} -> " + ("passes" if rew >= GATE else "FAILS"))
    return "\n".join(lines), rew >= GATE

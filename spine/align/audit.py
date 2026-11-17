"""py -m spine p1 audit <module>: what a person (or Claude) reads before a book is marked ready.

    p1 audit year2-cns                         the counts per book and per audit list
    p1 audit year2-cns --sample 40 --book X    40 random accepted links of a book, each with both sentences
    p1 audit year2-cns --list split-vote       the sentences of one list, with every reader's answer

Lists (read from votes/ and edges/; nothing is written):
    split-vote     two readers gave links that share no handout sentence
    one-reader     one reader linked it, nobody else read it or agreed
    one-no         one reader said "not in the handout", no other answer
    no-reader      nobody answered
    jump           accepted by the votes, but far from where its neighbours point (state "flagged")
    orphan-handout handout facts of a lesson the book covers that no accepted link reaches
"""
import random
from collections import Counter

from spine import graph_dir, read_jsonl
from spine.align import engine, prefilter
from spine.books import split

LISTS = ("split-vote", "one-reader", "one-no", "no-reader", "jump", "orphan-handout")


def book_state(module, book, H):
    """{list name: [book sentence or handout sentence]}, plus "accepted": [(book sentence, [edge])]."""
    sents = [s for s in split.load(module, book) if s["kind"] != "not_content"]
    votes = {}
    for f in sorted((graph_dir(module) / "votes").glob(f"{book}.*.jsonl")):
        for v in read_jsonl(f):
            votes.setdefault(v["src"], {})[v["reader"]] = v
    edges = {}
    for e in read_jsonl(graph_dir(module) / "edges" / f"{book}.jsonl"):
        edges.setdefault(e["src"], []).append(e)
    out = {k: [] for k in LISTS + ("accepted", "no")}
    for s in sents:
        mine = votes.get(s["id"], {})
        links = [r for r, v in mine.items() if isinstance(v["answer"], dict)]
        nos = [r for r, v in mine.items() if isinstance(v["answer"], str)]
        if s["id"] in edges:
            out["jump" if edges[s["id"]][0]["state"] == "flagged" else "accepted"].append((s, edges[s["id"]]))
        elif len(nos) >= 2:
            out["no"].append(s)
        elif nos and not links:
            out["one-no"].append(s)
        elif len(links) >= 2:
            out["split-vote"].append(s)
        elif links:
            out["one-reader"].append(s)
        else:
            out["no-reader"].append(s)
    reached = {e["dst"] for s, es in out["accepted"] for e in es}
    lessons = Counter(H.lesson[H.pos[d]] for d in reached if d in H.pos)
    covered = {l for l, n in lessons.items() if n >= 10}          # a lesson the book really teaches
    out["orphan-handout"] = [h for n, h in enumerate(H.sents)
                             if h["kind"] == "fact" and H.lesson[n] in covered and h["id"] not in reached]
    out["votes"] = votes
    return out


def summary(module, books=None):
    H = prefilter.Handout(module)
    lines = ["audit lists per book (accepted / lists)"]
    for book in books or engine.canonical_books(module)[0]:
        st = book_state(module, book, H)
        lines.append(f"  {book:<22} accepted {len(st['accepted']):>5}, not in the handout {len(st['no']):>4}, "
                     + ", ".join(f"{k} {len(st[k])}" for k in LISTS))
    return "\n".join(lines)


def sample(module, book, n, seed=1):
    """n random accepted links of a book as text blocks: the book sentence, then every handout sentence it links."""
    H = prefilter.Handout(module)
    st = book_state(module, book, H)
    pick = random.Random(seed).sample(st["accepted"], min(n, len(st["accepted"])))
    lines = [f"{book}: {len(pick)} of {len(st['accepted'])} accepted links (seed {seed})"]
    for k, (s, es) in enumerate(pick, start=1):
        lines.append(f"{k:>3}. [{es[0]['rel']} {es[0]['by']}] BOOK p{s.get('page')}: {s['text'][:300]}")
        for e in es:
            h = H.sents[H.pos[e["dst"]]]
            lines.append(f"        HANDOUT {e['dst'].split(':', 2)[-1]}: {h['text'][:300]}")
    return "\n".join(lines)


def listing(module, name, book=None, limit=40):
    H = prefilter.Handout(module)
    lines = []
    for b in [book] if book else engine.canonical_books(module)[0]:
        st = book_state(module, b, H)
        lines.append(f"{b}: {name} {len(st[name])}")
        for item in st[name][:limit]:
            s = item[0] if isinstance(item, tuple) else item
            lines.append(f"  {s['id'].split(':', 2)[-1]}: {s['text'][:220]}")
            for r, v in sorted(st["votes"].get(s["id"], {}).items()):
                a = v["answer"]
                if isinstance(a, dict):
                    lines.append(f"      {r} {a.get('rel', '')}: " + " | ".join(
                        f"{d.split(':', 2)[-1]} {H.sents[H.pos[d]]['text'][:110]}" for d in a["dst"] if d in H.pos))
                else:
                    lines.append(f"      {r}: {a}")
    return "\n".join(lines)


def run(a):
    if a.sample:
        for b in [a.book] if a.book else engine.canonical_books(a.module)[0]:
            print(sample(a.module, b, a.sample, a.seed))
    elif a.list:
        print(listing(a.module, a.list, a.book, a.limit))
    else:
        print(summary(a.module, [a.book] if a.book else None))
    return 0


def add(p):
    u = p.add_parser("audit", help="audit lists and a random sample of accepted links (read only)")
    u.add_argument("module")
    u.add_argument("--book")
    u.add_argument("--sample", type=int, help="print this many random accepted links per book")
    u.add_argument("--seed", type=int, default=1)
    u.add_argument("--list", choices=LISTS)
    u.add_argument("--limit", type=int, default=40)
    u.set_defaults(run=run)

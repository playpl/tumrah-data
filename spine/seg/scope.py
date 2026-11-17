"""Which doctor's book a lecture is read against, and which slice of it the reader gets.

The slice comes, in this order, from:
1. the lecture's handout placement (`lecture.json` ranges) carried back to the book through the Phase 1 edges
   (accepted book -> handout links), and the lectures it covers when it is a revision or mini lecture;
2. else the densest run of book sentences the prior's scores point at (a window of `DENSE` sentences).
The slice is widened by `MARGIN` sentences each side, so a doctor who strays a little stays inside it.
"""
from spine import ROOT, graph_dir, read_json, read_jsonl
from spine import ids
from spine.books import split

MARGIN, DENSE, TRIM = 30, 160, 0.1


def doctor_books(module):
    """{doctor id: canonical book id}: an alias (a partial copy of a full book) is never the reader's book. Only
    canonical books are split (`books split`), so a book with a sentences file is canonical."""
    out = {}
    for book, card in split.books(module).items():
        if not card.get("doctor") or not split.path(module, book).exists():
            continue
        out.setdefault(card["doctor"], book)
    return out


def lecture(lid):
    return read_json(ROOT / "lectures" / lid / "lecture.json")


def book_sentences(module, book):
    """The book's content sentences (page furniture out), in book order, as the reader numbers them."""
    return [s for s in split.load(module, book) if s["kind"] != "not_content"]


def _handout_index(module):
    """[(order key of the first row, sentence id)] in handout order."""
    rows = []
    for s in read_jsonl(graph_dir(module) / "sentences.jsonl"):
        if s.get("rows"):
            rows.append((ids.order_key(s["rows"][0]), s["id"]))
    return sorted(rows)


def handout_in_ranges(module, ranges, index=None):
    """Handout sentence ids whose first row lies inside one of the ranges ({from, to} line ids)."""
    index = index or _handout_index(module)
    out = set()
    for r in ranges or []:
        try:
            lo, hi = ids.order_key(r["from"]), ids.order_key(r["to"])
        except (KeyError, ValueError):
            continue
        out |= {sid for key, sid in index if lo <= key <= hi}
    return out


def edges(module, book):
    """{book sentence id: [handout sentence ids]} of the accepted Phase 1 links."""
    out = {}
    for e in read_jsonl(graph_dir(module) / "edges" / f"{book}.jsonl"):
        if e.get("state") == "accepted" and e.get("dst"):
            out.setdefault(e["src"], []).append(e["dst"])
    return out


def from_placement(lec, sents, module, book, index=None, links=None):
    """Book indexes whose accepted edges land inside the lecture's handout ranges (and its covered lectures')."""
    ranges = list(lec.get("ranges") or [])
    for other in lec.get("covers") or []:
        try:
            ranges += lecture(other).get("ranges") or []
        except (OSError, ValueError):
            pass
    want = handout_in_ranges(module, ranges, index)
    if not want:
        return []
    links = links if links is not None else edges(module, book)
    return [i for i, s in enumerate(sents) if any(d in want for d in links.get(s["id"], ()))]


def trimmed(points, n, margin=MARGIN, trim=TRIM):
    hits = sorted(points)
    if not hits:
        return None
    k = int(len(hits) * trim)
    core = hits[k:len(hits) - k] or hits
    return max(0, core[0] - margin), min(n - 1, core[-1] + margin)


def densest(m, width=DENSE, margin=MARGIN):
    """(lo, hi) of the run of `width` book sentences with the most prior score mass."""
    import numpy as np
    mass = m.sum(axis=0)
    n = len(mass)
    if n <= width:
        return 0, n - 1
    run = np.convolve(mass, np.ones(width), mode="valid")
    lo = int(np.argmax(run))
    return max(0, lo - margin), min(n - 1, lo + width - 1 + margin)


def pick(lid, module="year2-cns", paras=None, cache=None):
    """{book, sents (whole book), lo, hi, how} for a lecture, or None when its doctor has no book."""
    from spine.seg import prior
    cache = cache if cache is not None else {}
    lec = lecture(lid)
    book = doctor_books(module).get(lec.get("doctor"))
    if not book:
        return None
    if book not in cache:
        cache[book] = {"sents": book_sentences(module, book), "links": edges(module, book),
                       "index": _handout_index(module)}
    c = cache[book]
    sents = c["sents"]
    pts = from_placement(lec, sents, module, book, c["index"], c["links"])
    span = trimmed(pts, len(sents))
    if span:
        return {"book": book, "sents": sents, "lo": span[0], "hi": span[1], "how": f"placement ({len(pts)} linked)"}
    if paras is None:
        return {"book": book, "sents": sents, "lo": 0, "hi": len(sents) - 1, "how": "whole book"}
    if "lex" not in c:
        c["lex"] = prior.lexicon(sents)
    lo, hi = densest(prior.scores(paras, sents, c["lex"]))
    return {"book": book, "sents": sents, "lo": lo, "hi": hi, "how": "prior density"}

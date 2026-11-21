"""Which doctor's book a lecture is read against, and which slice of it the reader gets.

The slice comes, in this order, from:
1. the lecture's handout placement (`lecture.json` ranges) carried back to the book through the Phase 1 edges
   (accepted book -> handout links), and the lectures it covers when it is a revision or mini lecture;
2. else the densest run of book sentences the prior's scores point at (a window of `DENSE` sentences).
The slice is widened by `MARGIN` sentences each side, so a doctor who strays a little stays inside it.

When both readers find (almost) nothing of the lecture in its slice (`flow.collect`: both answers rejected for
NONE), the slice missed: the doctor's book has no such chapter (a partial book), the prior pointed elsewhere, or the
placement is off. `jobs/sp_seg/<lecture>/widen.json` then steps the lecture up the ladder, one step per rejection:
    step 1  the whole book (a book over WHOLE_MAX lines: the slice +- WIDE); no book: the handout +- WIDE
    step 2  a lecture with a book and a placement: the handout +- WIDE (the book does not have it)
    top     the handout window the lecture's own words point at (`handout_prior`: the prior's densest run of
            HANDOUT_DENSE handout sentences), for an old placement on the wrong pages (Azouny's Cerebrum part 1
            was placed on the midbrain and receptor pages: every slice built from it missed)
A lecture with no placement and no book starts at the top. A lecture still rejected at its last step goes to the
owner (a Today card, `decisions.py`).
"""
from spine import ROOT, graph_dir, read_json, read_jsonl
from spine import ids
from spine.books import split

MARGIN, DENSE, TRIM = 30, 160, 0.1
WIDE, WHOLE_MAX = 300, 1500
WIDEN = ROOT / "jobs" / "sp_seg"


def widen_step(lid):
    """0 = the normal slice; 1, 2 = the ladder steps above (written by `flow.collect`)."""
    return (read_json(WIDEN / lid / "widen.json") or {}).get("step", 0)


def last_step(lid, module="year2-cns"):
    """The top of the ladder for this lecture (the handout prior): 3 with a book and a placement, else 2."""
    lec = lecture(lid)
    has_book = lec.get("doctor") in doctor_books(module)
    return 3 if has_book and (lec.get("ranges") or lec.get("covers")) else 2


def doctor_books(module):
    """{doctor id: canonical book id}: an alias (a partial copy of a full book) is never the reader's book. Only
    canonical books are split (`books split`), so a book with a sentences file is canonical."""
    out = {}
    for book, card in split.books(module).items():
        if not card.get("doctor") or not split.path(module, book).exists():
            continue
        out.setdefault(card["doctor"], book)
    return out


RECORD_MODULES = ("year1-musculoskeletal",)       # their lessons are records, not lectures/<id> folders


_RECORDS = {}


def _record_lessons():
    """{record id: lecture-shaped dict} from the site lessons of the record modules (year 1: no lecture.json).
    Read again only when a lessons file changes."""
    files = [ROOT / "modules" / m / "site" / "lessons.jsonl" for m in RECORD_MODULES]
    stamp = tuple(f.stat().st_mtime if f.exists() else 0 for f in files)
    if _RECORDS.get("stamp") != stamp:
        _RECORDS.update(stamp=stamp, rows=_read_record_lessons())
    return _RECORDS["rows"]


def _read_record_lessons():
    out = {}
    for m in RECORD_MODULES:
        for r in read_jsonl(ROOT / "modules" / m / "site" / "lessons.jsonl"):
            lid = r["key"].split(":", 1)[-1]
            out[lid] = {"id": lid, "module": m, "doctor": r.get("doctorId"), "title": r.get("name"),
                        "ranges": r.get("placedRanges", r.get("ranges")) or [], "covers": [c.split(":", 1)[-1] for c in r.get("covers") or []]}
    return out


def home(lid):
    """The folder that holds a lecture's raw.txt and segments: lectures/<id>, or a year 1 record's folder."""
    d = ROOT / "lectures" / lid
    if (d / "lecture.json").exists():
        return d
    rec = _record_lessons().get(lid)
    return ROOT / "modules" / rec["module"] / "records" / lid if rec else d


def lecture(lid):
    """The lecture record, or {} when there is none (a `covers` id with no record must not stop the batch). A year 1
    record has no lecture.json: its site lesson stands in (doctor, ranges, covers)."""
    return read_json(ROOT / "lectures" / lid / "lecture.json") or _record_lessons().get(lid) or {}


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


def edges(module, book, cells=True):
    """{book sentence id: [handout sentence ids]} of the accepted Phase 1 links. `cells=False` (the slice) leaves
    out the per-cell links of table rows and the jumps kept because their text is found only there (2026-11-21):
    they add handout facts to rows already placed, and a slice that moved with them would make answered seg jobs
    stale."""
    out = {}
    for e in read_jsonl(graph_dir(module) / "edges" / f"{book}.jsonl"):
        if not cells and (e.get("by") == "spine-code:cell" or e.get("kept")):
            continue
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


HANDOUT_MARGIN = 15
HANDOUT_DENSE = 500


def handout_target(lec, module="year2-cns", cache=None, margin=HANDOUT_MARGIN):
    """No split book (Azouny, Khaled, Mahmoud Elhusseiny): the reader maps the transcript straight onto the handout
    sentences of the lecture's placement (and its covered lectures'), +- HANDOUT_MARGIN sentences, in handout order.
    `book` is None and `target` is "handout"; the B numbers then stand for handout sentences. None without ranges."""
    sents = _handout_sents(module, cache)
    ranges = list(lec.get("ranges") or [])
    for other in lec.get("covers") or []:
        try:
            ranges += lecture(other).get("ranges") or []
        except (OSError, ValueError):
            pass
    want = handout_in_ranges(module, ranges, cache["index"])
    pts = [i for i, s in enumerate(sents) if s["id"] in want]
    if not pts:
        return None
    lo, hi = max(0, min(pts) - margin), min(len(sents) - 1, max(pts) + margin)
    return {"book": None, "target": "handout", "sents": sents, "lo": lo, "hi": hi,
            "how": f"handout placement ({len(pts)} sentences)" + (f", widened +-{margin}" if margin != HANDOUT_MARGIN else "")}


def _handout_sents(module, cache):
    if "handout_sents" not in cache:
        cache["handout_sents"] = [s for s in read_jsonl(graph_dir(module) / "sentences.jsonl")
                                  if s["kind"] != "figure" and (s.get("text") or "").strip() and s.get("rows")]
        cache["index"] = cache.get("index") or _handout_index(module)
    return cache["handout_sents"]


def handout_prior(paras, module="year2-cns", cache=None, width=None):
    """The top of the ladder: the handout window of `width` sentences the lecture's own words point at (the prior's
    densest run over the whole handout), placement-free. None without paragraphs or a word in common."""
    from spine.seg import prior
    cache = cache if cache is not None else {}
    sents = _handout_sents(module, cache)
    if not paras or not sents:
        return None
    if "handout_lex" not in cache:
        cache["handout_lex"] = prior.lexicon(sents)
    m = prior.scores(paras, sents, cache["handout_lex"])
    if not m.any():
        return None
    width = width or HANDOUT_DENSE
    lo, hi = densest(m, width=width, margin=MARGIN)
    return {"book": None, "target": "handout", "sents": sents, "lo": lo, "hi": hi,
            "how": f"handout prior (densest {width} sentences, placement-free)"}


def pick(lid, module="year2-cns", paras=None, cache=None):
    """{book, sents (whole book), lo, hi, how} for a lecture, or None when its doctor has no book."""
    from spine.seg import prior
    cache = cache if cache is not None else {}
    lec = lecture(lid)
    step = widen_step(lid)
    book = doctor_books(module).get(lec.get("doctor"))
    if step and step >= last_step(lid, module):
        return handout_prior(paras, module, cache)
    if not book or step >= 2:
        hand = handout_target(lec, module, cache, WIDE if step else HANDOUT_MARGIN)
        if hand:
            return hand
        if not book:                                   # no placement to start from: the lecture's own words
            return handout_prior(paras, module, cache)
    if book not in cache:
        cache[book] = {"sents": book_sentences(module, book), "links": edges(module, book, cells=False),
                       "index": _handout_index(module)}
    c = cache[book]
    sents = c["sents"]
    pts = from_placement(lec, sents, module, book, c["index"], c["links"])
    span = trimmed(pts, len(sents))
    if step >= 1:
        if len(sents) <= WHOLE_MAX or not span:
            return {"book": book, "sents": sents, "lo": 0, "hi": len(sents) - 1, "how": "whole book (the slice missed)"}
        return {"book": book, "sents": sents, "lo": max(0, span[0] - WIDE), "hi": min(len(sents) - 1, span[1] + WIDE),
                "how": f"placement ({len(pts)} linked), widened +-{WIDE}"}
    if span:
        return {"book": book, "sents": sents, "lo": span[0], "hi": span[1], "how": f"placement ({len(pts)} linked)"}
    if paras is None:
        return {"book": book, "sents": sents, "lo": 0, "hi": len(sents) - 1, "how": "whole book"}
    if "lex" not in c:
        c["lex"] = prior.lexicon(sents)
    lo, hi = densest(prior.scores(paras, sents, c["lex"]))
    return {"book": book, "sents": sents, "lo": lo, "hi": hi, "how": "prior density"}

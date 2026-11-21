"""Writers of the legacy file shapes from the spine's links, so the old readers (book_export, ledger.sync, the site's
BookAlignmentPage) can switch over without changing.

    aligned_blocks(module, book)  -> [triage row, page rows]: the shape of
                                     modules/<m>/site/alignment/out/aligned/<book>.jsonl
                                     page row {book_id, page, page_kind, lecture_id, blocks: [{n, text, figure, match,
                                     handout: [{pdf_page, printed_page, text, figure}], line_ids}]}
    write_aligned(module, book)   -> writes it to modules/<m>/graph/compat/aligned/<book>.jsonl (shadow: the site's
                                     alignment folder is written only when Phase 1 goes primary)

match: S -> same, R -> reworded, P -> partial; a content sentence two readers called "not in the handout" -> extra;
page furniture -> not_content; a content sentence with no settled link -> open (new: the old shape had no such word,
it marks what the audit still has to settle).
"""
from spine import graph_dir, read_jsonl, write_jsonl
from spine.books import split

MATCH = {"S": "same", "R": "reworded", "P": "partial"}


def _handout(module):
    sents = {s["id"]: s for s in read_jsonl(graph_dir(module) / "sentences.jsonl")}
    printed = {}
    from spine import module_dir
    for ln in read_jsonl(module_dir(module) / "lines.jsonl"):
        if ln.get("printed") is not None:
            printed.setdefault(ln["page"], ln["printed"])
    return sents, printed


def _votes(module, book):
    out = {}
    for f in sorted((graph_dir(module) / "votes").glob(f"{book}.*.jsonl")):
        for v in read_jsonl(f):
            out.setdefault(v["src"], {})[v["reader"]] = v
    return out


def aligned_blocks(module, book, handout=None):
    sents, printed = handout or _handout(module)
    edges = {}
    for e in read_jsonl(graph_dir(module) / "edges" / f"{book}.jsonl"):
        if e.get("state") == "accepted":
            edges.setdefault(e["src"], []).append(e)
    votes = _votes(module, book)
    card = split.books(module).get(book) or {}
    pages = {}
    for s in split.load(module, book):
        es = edges.get(s["id"], [])
        if s["kind"] == "not_content":
            match = "not_content"
        elif es:
            match = MATCH.get(es[0]["rel"], "same")
        elif sum(isinstance(v["answer"], str) for v in votes.get(s["id"], {}).values()) >= 2:
            match = "extra"
        else:
            match = "open"
        hand, line_ids = [], []
        for e in es:
            h = sents.get(e["dst"])
            if not h:
                continue
            hand.append({"pdf_page": h["page"], "printed_page": printed.get(h["page"]), "text": h["text"],
                         "figure": None})
            line_ids += [r for r in h.get("rows") or [] if r not in line_ids]
        blocks = pages.setdefault(s["page"], [])
        blocks.append({"n": len(blocks) + 1, "text": s["text"], "figure": None, "match": match, "handout": hand,
                       "line_ids": line_ids, "sentence": s["id"]})
    triage = {"book_id": book, "kind": "lecture_notes", "page_count": max(pages, default=0), "align": True,
              "doctor": card.get("doctor"), "by": "spine"}
    rows = [{"book_id": book, "page": p, "page_kind": "content", "lecture_id": None, "blocks": pages[p]}
            for p in sorted(pages)]
    return [triage] + rows


def lecture_files(lid, module="year2-cns", handout=None, write=True):
    """A segmented lecture (lectures/<id>/segments.jsonl) in the legacy shapes, written in shadow beside the live
    files: lectures/<id>/spine/links.jsonl ({part, sub: 0, title, start, end, line_ids}; title = the book heading
    the segment starts under) and lectures/<id>/spine/ranges.json (the handout rows the segments reach, merged per
    page into {from, to, pages}). Returns (links, ranges) or None when the lecture has no segments."""
    from spine import ROOT, ids, write_json
    from spine.seg import scope
    segs = read_jsonl(scope.home(lid) / "segments.jsonl")
    if not segs:
        return None
    sents, _ = handout or _handout(module)

    def book_of(bid):           # a handout-target lecture points at handout sentences: no book, no headings
        p = ids.parse(bid)
        return p.get("book") if p.get("space") == "book" else None

    book = next((b for b in (book_of(s["book"][0]) for s in segs if s.get("book")) if b), None)
    bsents = split.load(module, book) if book else []
    at = {s["id"]: i for i, s in enumerate(bsents)}

    from collections import Counter
    pages = {}
    for s in bsents:                                   # a heading on many pages is a running header, not a title
        for t in ([s["text"]] if s["kind"] == "heading" else []) + list(s.get("ctx") or []):
            pages.setdefault(t.strip().lower(), set()).add(s["page"])

    def title_ok(t):
        return t.strip() and len(pages.get(t.strip().lower(), ())) <= 6

    def heading(bid):
        """The sentence's innermost heading (ctx), else the nearest heading above; never a running header."""
        i = at.get(bid)
        while i is not None and i >= 0:
            s = bsents[i]
            if s["kind"] != "not_content":
                for t in reversed(s.get("ctx") or []):
                    if title_ok(t):
                        return t
                if s["kind"] == "heading" and title_ok(s["text"]):
                    return s["text"]
            i -= 1
        return ""

    links, rows = [], []
    for s in segs:
        line_ids = []
        for h in s.get("handout") or []:
            line_ids += [r for r in (sents.get(h) or {}).get("rows") or [] if r not in line_ids]
        rows += line_ids
        links.append({"part": s["n"], "sub": 0, "title": heading(s["book"][0]) if s.get("book") else "",
                      "start": s["start"], "end": s["end"], "line_ids": line_ids})
    by_page = {}
    for r in sorted(set(rows), key=ids.order_key):
        by_page.setdefault(ids.parse(r)["page"], []).append(r)
    ranges = [{"from": v[0], "to": v[-1], "pages": [p, p]} for p, v in sorted(by_page.items())]
    if write:
        from spine.seg import scope
        d = scope.home(lid) / "spine"
        write_jsonl(d / "links.jsonl", links)
        write_json(d / "ranges.json", {"ranges": ranges, "placed_by": "spine"})
    return links, ranges


def path(module, book):
    return graph_dir(module) / "compat" / "aligned" / f"{book}.jsonl"


def write_aligned(module, book):
    rows = aligned_blocks(module, book)
    write_jsonl(path(module, book), rows)
    return rows

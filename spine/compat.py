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


def path(module, book):
    return graph_dir(module) / "compat" / "aligned" / f"{book}.jsonl"


def write_aligned(module, book):
    rows = aligned_blocks(module, book)
    write_jsonl(path(module, book), rows)
    return rows

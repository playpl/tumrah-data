"""A doctor's book PDF as sentences: `modules/<m>/graph/books/<book>.sentences.jsonl`.

    py -m spine books split year2-cns [book]     every book (or one) -> sentences
    py -m spine books dedupe year2-cns           which books are page-for-page copies of a bigger one

Same join rules as the handout (spine/rows.py). A partial book that is page for page inside a full one is an
alias: it is split and aligned once, as the full book. Lines that are not teaching text are marked by code
(`kind: "not_content"`): page numbers, a line repeated on a third of the pages, pages with almost no words.
"""
from collections import Counter

import hub
import outline
from books_merge import page_offset
from spine import SPLITTER, graph_dir, ids, module_dir, read_json, read_jsonl, rows as R, text as T, write_json, write_jsonl

MIN_PAGE_WORDS = 15         # a page with fewer words is a cover, a divider or a picture
REPEAT_SHARE = 0.3          # a line on this share of the pages is a running header or footer


def books(module):
    """{book id: card} for every book PDF of the module."""
    out = {}
    for card in sorted((module_dir(module) / "books").glob("*.json")):
        if card.with_suffix(".pdf").exists():
            out[card.stem] = read_json(card)
    return out


def dedupe(module):
    """{alias: (canonical book, page offset)}: alias page i is canonical page i + offset.

    The alias is the smaller book; of two copies of one file, the one named "partial". Cached in
    graph/work/dedupe.json, keyed by the PDFs' names and sizes (comparing pages opens every PDF)."""
    d = module_dir(module) / "books"
    key = {name: (d / f"{name}.pdf").stat().st_size for name in books(module)}
    cache = graph_dir(module) / "work" / "dedupe.json"
    hit = read_json(cache) if cache.exists() else None
    if hit and hit.get("key") == key:
        return {a: tuple(v) for a, v in hit["aliases"].items()}
    out = _dedupe(module, d)
    write_json(cache, {"key": key, "aliases": out})
    return out


def _dedupe(module, d):
    import fitz
    size = {}
    for name in books(module):
        with fitz.open(d / f"{name}.pdf") as doc:
            size[name] = (len(doc), "partial" not in name, name)
    out = {}
    for a in sorted(size, key=size.get):
        for b in sorted(size, key=size.get, reverse=True):
            if size[b] > size[a] and b not in out:
                offset = page_offset(d / f"{a}.pdf", d / f"{b}.pdf")[0]
                if offset is not None:
                    out[a] = (b, offset)
                    break
    return out


def pdf_rows(pdf, book):
    """The book's visual rows in the shape spine/rows.py takes, and its ruled tables."""
    import fitz
    rows, tables = [], {}
    with fitz.open(pdf) as doc:
        for p, page in enumerate(doc, start=1):
            for n, (box, txt) in enumerate(hub._rows(page), start=1):
                rows.append({"id": f"{book}:p{p}:l{n}", "page": p, "n": n, "text": txt, "figure": None,
                             "bbox": [round(v, 1) for v in box]})
            found = []
            for t in page.find_tables().tables:
                cells = t.extract()
                trs = [{"bbox": list(row.bbox), "cells": cells[i]} for i, row in enumerate(t.rows)]
                if sum(1 for r in trs if sum(1 for c in r["cells"] if (c or "").strip()) >= 2) >= 2:
                    found.append({"bbox": list(t.bbox), "rows": trs})
            if found:
                tables[p] = found
    return rows, tables


def not_content(rows):
    """IDs of rows that are not teaching text, by code (tier N1)."""
    pages = {r["page"] for r in rows}
    words = Counter()
    seen = Counter()
    for r in rows:
        words[r["page"]] += len(r["text"].split())
    for key, page in {(T.word_key(r["text"]).rstrip("0123456789"), r["page"]) for r in rows}:
        seen[key] += 1
    out = set()
    for r in rows:
        key = T.word_key(r["text"]).rstrip("0123456789")
        if (not key or words[r["page"]] < MIN_PAGE_WORDS
                or (len(pages) >= 10 and seen[key] >= REPEAT_SHARE * len(pages))):
            out.add(r["id"])
    return out


def sentences(rows, tables, book, sha8):
    left = {}
    for r in rows:
        left[r["page"]] = min(left.get(r["page"], 1e9), r["bbox"][0])
    skip = not_content(rows)
    heads = {r["id"] for r in rows if r["id"] not in skip and outline.is_heading(r, left[r["page"]])
             and not r["text"].rstrip().endswith(":")}
    out, starts, used = [], Counter(), Counter()
    built = R.build(rows, heads, tables, breaks=skip | {r["id"] for i, r in enumerate(rows)
                                                         if i and rows[i - 1]["id"] in skip})
    for u in built:
        starts[u["first"]["id"]] += 1
    for u in built:
        first = u["first"]
        sub = ""
        if starts[first["id"]] > 1:
            sub = "abcdefghijklmnopqrstuvwxyz"[used[first["id"]] % 26]
            used[first["id"]] += 1
        kind = "not_content" if all(r["id"] in skip for r in u["rows"]) else u["kind"]
        out.append({"id": ids.book_sent_id(book, sha8, first["page"], first["n"], sub), "i": len(out), "kind": kind,
                    "marker": u["marker"], "text": u["text"], "rows": [r["id"] for r in u["rows"]],
                    "page": first["page"], "book": book, "ctx": u["ctx"], "splitter": SPLITTER})
    return out


def path(module, book):
    return graph_dir(module) / "books" / f"{book}.sentences.jsonl"


def split(module, book):
    """Split one book and write its sentences. An alias is not split: its canonical book is."""
    pdf = module_dir(module) / "books" / f"{book}.pdf"
    rows, tables = pdf_rows(pdf, book)
    sents = sentences(rows, tables, book, hub.file_hash(pdf))
    write_jsonl(path(module, book), sents)
    return sents


def load(module, book):
    return read_jsonl(path(module, book))

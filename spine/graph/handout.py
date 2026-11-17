"""The handout as atomic sentences: `modules/<m>/graph/sentences.jsonl`.

    py -m spine graph build year2-cns      rows (lines.jsonl) -> sentences, tree files
    py -m spine graph check year2-cns      the invariants; exit code 0 only when all hold
    py -m spine graph sample year2-cns     100 sentences with their raw rows, for a person to judge the joins

The handout itself is never changed. A sentence keeps its `rows` (line IDs), so the site's line-ID contract is
served by conversion. The join rules live in spine/rows.py (shared with the doctors' books).
"""
import json

import outline
from spine import SPLITTER, graph_dir, ids, module_dir, read_json, read_jsonl, rows as R, write_json, write_jsonl

MIN_TABLE_ROWS = 2      # a "table" with one real row is a frame around a title or a figure


def find_tables(module):
    """{page: [{bbox, rows: [{bbox, cells}]}]} of the handout's ruled tables, read from the PDF (cached by hash)."""
    lines_hash = next(iter(read_jsonl(module_dir(module) / "lines.jsonl")), {}).get("hash")
    cache = graph_dir(module) / "work" / "tables.json"
    saved = read_json(cache)
    if saved and saved.get("hash") == lines_hash:
        return {int(p): t for p, t in saved["pages"].items()}
    import fitz
    pages = {}
    with fitz.open(module_dir(module) / "handout.pdf") as doc:
        for n, page in enumerate(doc, start=1):
            found = []
            for t in page.find_tables().tables:
                cells = t.extract()
                trs = [{"bbox": [round(v, 1) for v in row.bbox], "cells": cells[i]} for i, row in enumerate(t.rows)]
                real = [r for r in trs if sum(1 for c in r["cells"] if (c or "").strip()) >= 2]
                if len(real) >= MIN_TABLE_ROWS:
                    found.append({"bbox": [round(v, 1) for v in t.bbox], "rows": trs})
            if found:
                pages[n] = found
    write_json(cache, {"hash": lines_hash, "pages": pages})
    return pages


def headings_and_breaks(lines, sections, lessons):
    """Rows that are headings, and rows that must start a unit (a section or a lesson begins there)."""
    left = {}
    for ln in lines:
        if ln.get("text"):
            left[ln["page"]] = min(left.get(ln["page"], 1e9), ln["bbox"][0])
    starts = {s["from"] for s in sections}
    first_pages, seen = {l["pdf_pages"][0] for l in lessons}, set()
    for ln in lines:
        if ln["page"] in first_pages and ln["page"] not in seen and ln.get("figure") is None:
            seen.add(ln["page"])
            starts.add(ln["id"])
    heads = set()
    for ln in lines:
        if ln.get("figure") is None and outline.is_heading(ln, left.get(ln["page"], 0)):
            t = ln["text"].strip()
            tall = ln["bbox"][3] - ln["bbox"][1] >= outline.TITLE_HEIGHT
            caps = t.upper() == t and len(outline.LETTERS.findall(t)) >= 6
            # A short "Definition:" line is a lead-in for what is under it, not a heading, unless a section starts there.
            if tall or caps or ln["id"] in starts:
                heads.add(ln["id"])
    return heads, starts


def sentences(lines, sections, lessons, tables=None):
    """Handout rows -> sentence rows (the shape in spine/__init__.py), in handout order."""
    heads, breaks = headings_and_breaks(lines, sections, lessons)
    index = {ln["id"]: i for i, ln in enumerate(lines)}
    section_of = {}
    for s in sections:
        for i in range(s["i0"], s["i1"] + 1):
            section_of.setdefault(i, s)
    lesson_of_page = {}
    for l in lessons:
        for p in range(l["pdf_pages"][0], l["pdf_pages"][1] + 1):
            lesson_of_page.setdefault(p, l["lecture_id"])
    built = R.build(lines, heads, tables, breaks)
    starts = {}
    for u in built:
        if u["kind"] != "figure":
            starts[u["first"]["id"]] = starts.get(u["first"]["id"], 0) + 1
    out, used = [], {}
    for u in built:
        first = u["first"]
        if u["kind"] == "figure":
            sid = first["id"]
        else:
            sub = ""
            if starts[first["id"]] > 1:
                sub = "abcdefghijklmnopqrstuvwxyz"[used.get(first["id"], 0) % 26]
                used[first["id"]] = used.get(first["id"], 0) + 1
            sid = ids.sent_id(first["module"], first["hash"], first["page"], first["n"], sub)
        sec = section_of.get(index[first["id"]])
        out.append({"id": sid, "i": len(out), "kind": u["kind"], "marker": u["marker"], "text": u["text"],
                    "rows": [r["id"] for r in u["rows"]], "page": first["page"],
                    "lesson": sec["lecture"] if sec else lesson_of_page.get(first["page"]),
                    "section": sec["id"] if sec else None, "ctx": u["ctx"], "splitter": SPLITTER})
    return out


def make(module):
    lines = read_jsonl(module_dir(module) / "lines.jsonl")
    return lines, sentences(lines, outline.load(module), outline.reference(module), find_tables(module))


def build(module, dry=False):
    lines, sents = make(module)
    if not dry:
        write_jsonl(graph_dir(module) / "sentences.jsonl", sents)
    return lines, sents


def load(module):
    return read_jsonl(graph_dir(module) / "sentences.jsonl")


def check(module):
    """[(name, ok, detail)] for every invariant."""
    lines = read_jsonl(module_dir(module) / "lines.jsonl")
    path = graph_dir(module) / "sentences.jsonl"
    sents = read_jsonl(path)
    out = []
    covered = {r for s in sents for r in s["rows"]}
    missing = [ln["id"] for ln in lines if ln["id"] not in covered]
    out.append(("every row is in a sentence", not missing, f"{len(missing)} rows missing {missing[:3]}"))
    order = {ln["id"]: i for i, ln in enumerate(lines)}
    firsts = [order[s["rows"][0]] for s in sents if s["kind"] != "figure"]
    out.append(("row order is kept", firsts == sorted(firsts), f"{len(firsts)} sentences"))
    idset = {s["id"] for s in sents}
    out.append(("ids are unique", len(idset) == len(sents), f"{len(sents) - len(idset)} repeats"))
    bad = []
    for s in sents:
        try:
            if ids.first_row(s["id"]) != s["rows"][0]:
                bad.append(s["id"])
        except ValueError:
            bad.append(s["id"])
    out.append(("every id parses and names its first row", not bad, f"{len(bad)} bad {bad[:3]}"))
    again = "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in make(module)[1])
    out.append(("a rebuild gives the same file", path.exists() and again == path.read_text(encoding="utf-8"), ""))
    lessons = {l["lecture_id"] for l in outline.reference(module)}
    have = {s["lesson"] for s in sents}
    out.append(("every lesson has sentences", lessons <= have, f"missing {sorted(lessons - have)}"))
    mixed = [s["id"] for s in sents if len({ids.parse(r)["page"] for r in s["rows"]}) > 2]
    out.append(("no sentence spans more than two pages", not mixed, f"{mixed[:3]}"))
    too_long = sorted((s for s in sents if len(s["text"].split()) > 90 and s["kind"] == "fact"),
                      key=lambda s: -len(s["text"]))
    out.append(("no fact sentence over 90 words", not too_long,
                f"{len(too_long)} over: " + ", ".join(f"{ids.short(s['id'])}={len(s['text'].split())}w"
                                                      for s in too_long[:8])))
    empty = [s["id"] for s in sents if not s["text"].strip() and s["kind"] != "figure"]
    out.append(("no empty sentence", not empty, f"{len(empty)} empty {empty[:3]}"))
    return out

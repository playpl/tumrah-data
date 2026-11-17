"""The old book alignment (jobs/books/*/aligned.jsonl, 7,173 linked blocks) read as one more reader.

    py -m spine p1 grade-old year2-cns

Each old link is lifted from handout rows to handout sentences and graded by code (owner, 2026-11-16: "Check
their quality. See if they need any redo."):
    keep      a code tier (A1 to A4) finds the same handout sentence: reused with no new read
    conflict  a code tier finds another sentence: redo
    one-read  code cannot judge it, the old link looks sound: one new fleet read confirms it
    redo      a reworded link that shares under 30% of its words with its target; an old "not in the handout"
              block that is in the handout word for word
Nothing is changed in jobs/ or ledger.db. The verdicts go to modules/<m>/graph/work/old_grade.jsonl.
"""
from collections import Counter

from spine import ROOT, graph_dir, read_jsonl, text as T, write_jsonl
from spine.align import prefilter
from spine.graph import handout as handout_graph

SUBJECTS = {"anat": "anatomy", "hist": "histology", "phys": "physiology"}
LOW_OVERLAP = 0.3


def subject_of(book):
    return next((v for k, v in SUBJECTS.items() if k in book.split("-")), None)


def old_books(module):
    """{old book id: [(page, blocks)]} in page order, from every old job that has an aligned.jsonl."""
    out = {}
    for f in sorted((ROOT / "jobs" / "books").glob(f"{module}-*/aligned.jsonl")):
        for row in read_jsonl(f):
            out.setdefault(row["book_id"], {})[row["page"]] = row["blocks"]
    return {b: sorted(pages.items()) for b, pages in out.items()}


def row_map(module):
    """{handout row id: [sentence ids]}"""
    out = {}
    for s in handout_graph.load(module):
        for r in s["rows"]:
            out.setdefault(r, []).append(s["id"])
    return out


def lift(line_ids, rows, H):
    """Positions in H.sents of the sentences these handout rows belong to."""
    return {H.pos[sid] for lid in line_ids for sid in rows.get(lid, []) if sid in H.pos}


def grade(module, H=None):
    """[{book, page, n, match, verdict, tier, old: [sentence ids], code: [sentence ids]}] for every old block."""
    H = H or prefilter.Handout(module)
    rows = row_map(module)
    out = []
    for book, pages in old_books(module).items():
        scopes = H.page_lessons([" ".join(b["text"] or "" for b in blocks) for _, blocks in pages], subject_of(book))
        items, meta = [], []
        for (page, blocks), scope in zip(pages, scopes):
            for b in blocks:
                items.append({"text": b.get("text") or "", "scope": scope})
                meta.append((page, b))
        res = prefilter.code_tiers(items, H)
        for it, (page, b), r in zip(items, meta, res):
            linked = b["match"] in ("same", "partial", "reworded") and b.get("line_ids")
            old = lift(b.get("line_ids") or [], rows, H) if linked else set()
            code = set(r[1]) if r else set()
            if linked and r:
                verdict = "keep" if old & code else "conflict"
            elif linked:
                target = " ".join(H.sents[n]["text"] for n in sorted(old))
                weak = b["match"] == "reworded" and T.overlap(it["text"], target) < LOW_OVERLAP
                verdict = "redo" if weak or not old else "one-read"
            elif r and r[0] in ("A1", "A2") and b["match"] in ("extra", "not_content"):
                verdict = "redo"            # called "not in the handout", yet it is there word for word
            else:
                verdict = "negative"
            out.append({"book": book, "page": page, "n": b["n"], "match": b["match"], "verdict": verdict,
                        "tier": r[0] if r else None, "old": [H.sents[n]["id"] for n in sorted(old)],
                        "code": [H.sents[n]["id"] for n in sorted(code)]})
    return out


def report(graded):
    linked = [g for g in graded if g["match"] in ("same", "partial", "reworded") and g["old"]]
    lines = [f"old book links graded by code: {len(linked):,} linked blocks of {len(graded):,} blocks"]
    by = Counter((g["match"], g["verdict"]) for g in linked)
    for match in ("same", "partial", "reworded"):
        total = sum(n for (m, _), n in by.items() if m == match)
        lines.append(f"  {match:<9} {total:>5,}: " + ", ".join(
            f"{v} {by[(match, v)]:,}" for v in ("keep", "one-read", "conflict", "redo") if by[(match, v)]))
    tiers = Counter((g["tier"], g["verdict"]) for g in linked if g["tier"])
    for tier in ("A1", "A2", "A3", "A4"):
        yes, no = tiers[(tier, "keep")], tiers[(tier, "conflict")]
        if yes + no:
            lines.append(f"  tier {tier}: {yes + no:,} judged, {yes:,} agree with the old link ({yes / (yes + no):.1%})")
    v = Counter(g["verdict"] for g in linked)
    lines.append(f"  kept with no new read: {v['keep']:,}; one fleet read: {v['one-read']:,}; "
                 f"redo: {v['conflict'] + v['redo']:,} (code disagrees {v['conflict']:,}, weak reworded {v['redo']:,})")
    neg = sum(1 for g in graded if g["verdict"] == "redo" and not g["old"] and g["match"] in ("extra", "not_content"))
    lost = sum(1 for g in graded if g["match"] in ("same", "partial", "reworded") and not g["old"])
    lines.append(f"  old 'extra / not content' blocks found word for word in the handout (redo): {neg:,}")
    lines.append(f"  old links whose rows are outside every lesson or empty: {lost:,}")
    return "\n".join(lines)


def write(module, graded):
    write_jsonl(graph_dir(module) / "work" / "old_grade.jsonl", graded)

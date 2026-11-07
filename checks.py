"""Checkers: each returns a list of errors; empty means pass. Standard library only, so fleet workers run the
same checks in their job folders (tools/check.py) that the dispatcher trusts.
"""
import re

from hub import resolve_span, word_key

POINTER_KEYS = {"qid", "found", "lecture_id", "spans", "partial", "tested_fact", "reason", "other_module"}
SPAN_KEYS = {"pdf_page", "printed_page", "text", "figure", "for_option"}
REASONS = {"not_in_book", "other_module", "question_unclear"}
BANNED = re.compile(r"\b(answer|correct|incorrect|keyed)\b", re.I)
LETTERS = "ABCDE"


class L:
    """A handout line read from lines.jsonl (dicts), with the attributes hub.resolve_span reads."""
    __slots__ = ("id", "page", "printed", "n", "text", "figure")

    def __init__(self, d):
        self.id, self.page, self.printed, self.n = d["id"], d["page"], d.get("printed"), d["n"]
        self.text, self.figure = d.get("text") or "", d.get("figure")


def as_lines(rows):
    return [r if isinstance(r, L) else L(r) for r in rows]


def check_pointers(rows, batch, lines, reference=None):
    """rows: the worker's output; batch: the questions it was given (qid, options); lines: the module's lines."""
    lines = as_lines(lines)
    printed = {ln.page: ln.printed for ln in lines}
    lectures = {lec["lecture_id"]: lec for lec in (reference or {}).get("lectures", [])}
    options = {q["qid"]: len(q.get("options") or []) for q in batch}
    errors, seen = [], []
    for n, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            errors.append(f"row {n}: not an object")
            continue
        q = r.get("qid", f"row {n}")
        seen.append(q)
        if set(r) != POINTER_KEYS:
            errors.append(f"{q}: keys must be exactly {sorted(POINTER_KEYS)}")
            continue
        for field in ("tested_fact", "reason"):
            if r[field] and BANNED.search(str(r[field])):
                errors.append(f"{q}: {field} uses a banned word")
        if not r["found"]:
            if r["reason"] not in REASONS:
                errors.append(f"{q}: found=false needs reason in {sorted(REASONS)}")
            if r["spans"]:
                errors.append(f"{q}: found=false must have no spans")
            continue
        if not r["spans"]:
            errors.append(f"{q}: found=true needs spans")
            continue
        lec = lectures.get(r["lecture_id"])
        if lectures and lec is None:
            errors.append(f"{q}: unknown lecture_id {r['lecture_id']}")
        for i, s in enumerate(r["spans"]):
            if not isinstance(s, dict) or set(s) != SPAN_KEYS:
                errors.append(f"{q} span {i}: keys must be exactly {sorted(SPAN_KEYS)}")
                continue
            p = s["pdf_page"]
            if p not in printed:
                errors.append(f"{q} span {i}: pdf_page {p} does not exist")
                continue
            if s["printed_page"] != printed[p]:
                errors.append(f"{q} span {i}: printed_page for pdf {p} must be {printed[p]}")
            fo = s["for_option"]
            if fo is not None and not (isinstance(fo, int) and 0 <= fo < options.get(q, 0)):
                errors.append(f"{q} span {i}: for_option must be null or an option index")
            if s["text"] == "FIGURE" and not s["figure"]:
                errors.append(f"{q} span {i}: FIGURE needs the figure's nearby text in figure")
            elif not resolve_span(lines, p, s["text"], s["figure"]):
                errors.append(f"{q} span {i}: not verbatim on pdf page {p}: {str(s['text'])[:60]!r}")
        if lec and lec.get("pdf_pages") and r["spans"] and isinstance(r["spans"][0], dict):
            a, b = lec["pdf_pages"]
            if not a <= r["spans"][0].get("pdf_page", 0) <= b:
                errors.append(f"{q}: the first span lies outside lecture {lec['lecture_id']} (pdf {a}-{b})")
    want = [q["qid"] for q in batch]
    missing = [q for q in want if q not in seen]
    extra = [q for q in seen if q not in want]
    if missing:
        errors.append(f"missing {len(missing)} qids: {missing[:3]}")
    if extra:
        errors.append(f"{len(extra)} qids not in the batch: {extra[:3]}")
    if len(seen) != len(set(seen)):
        errors.append("duplicate qids")
    return errors


def pointer_import_rows(rows, lines):
    """Checked worker rows as importHubData pointer rows: line IDs resolved, option index as the site letter."""
    lines = as_lines(lines)
    out = []
    for r in rows:
        spans = [{"pdf_page": s["pdf_page"], "printed_page": s["printed_page"], "text": s["text"], "figure": s["figure"],
                  "for_option": None if s["for_option"] is None else LETTERS[s["for_option"]],
                  "line_ids": resolve_span(lines, s["pdf_page"], s["text"], s["figure"])} for s in r["spans"]]
        out.append({"question_id": r["qid"], "found": r["found"], "partial": bool(r["partial"]),
                    "lecture_id": r["lecture_id"], "reason": r["reason"], "other_module": r["other_module"],
                    "spans": spans})
    return out

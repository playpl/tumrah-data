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


ALIGN_KEYS = {"book_id", "page", "page_kind", "lecture_id", "blocks", "note"}
BLOCK_KEYS = {"n", "text", "figure", "match", "handout"}
ALIGN_SPAN_KEYS = {"pdf_page", "printed_page", "text", "figure"}
MATCHES = {"same", "reworded", "partial", "extra", "not_content"}
LINKED = {"same", "reworded", "partial"}
MIN_COVERAGE = 0.9        # share of a text page's characters its blocks must cover (old alignment rule)
IMAGE_PAGE_CHARS = 20     # less text than this: an image-only page, blocks are not checked against it
MAX_BLOCK_WORDS, MAX_SPAN_WORDS = 60, 80


def squash(text):
    return " ".join(str(text or "").split())


def coverage(page_text, blocks):
    """Share of the page's non-space characters covered by the blocks' texts (first free occurrence of each)."""
    covered = [False] * len(page_text)
    for text in blocks:
        start, i = 0, -1
        while True:
            i = page_text.find(text, start)
            if i < 0 or not any(covered[i:i + len(text)]):
                break
            start = i + 1
        if i >= 0 and text:
            covered[i:i + len(text)] = [True] * len(text)
    chars = [k for k, c in enumerate(page_text) if not c.isspace()]
    return sum(covered[k] for k in chars) / len(chars) if chars else 1.0


def check_alignment(rows, batch, lines, reference=None):
    """rows: align rows; batch: the book pages {"book_id", "page", "text"}; lines: the module's handout lines."""
    lines = as_lines(lines)
    printed = {ln.page: ln.printed for ln in lines}
    lectures = {lec["lecture_id"] for lec in (reference or {}).get("lectures", [])}
    pages = {(b["book_id"], b["page"]): squash(b["text"]) for b in batch}
    errors, seen = [], []
    for r in rows:
        where = f"{r.get('book_id')} p{r.get('page')}" if isinstance(r, dict) else "row"
        if not isinstance(r, dict) or set(r) != ALIGN_KEYS:
            errors.append(f"{where}: keys must be exactly {sorted(ALIGN_KEYS)}")
            continue
        seen.append((r["book_id"], r["page"]))
        text = pages.get((r["book_id"], r["page"]))
        if text is None:
            errors.append(f"{where}: not a page of this batch")
            continue
        if r["page_kind"] not in ("content", "not_content"):
            errors.append(f"{where}: page_kind must be content or not_content")
        if r["lecture_id"] is not None and lectures and r["lecture_id"] not in lectures:
            errors.append(f"{where}: unknown lecture_id {r['lecture_id']}")
        blocks = r["blocks"] if isinstance(r["blocks"], list) else []
        ns = [b.get("n") for b in blocks if isinstance(b, dict)]
        if ns != list(range(1, len(blocks) + 1)):
            errors.append(f"{where}: blocks must be numbered 1, 2, 3... with no gap or repeat")
        for b in blocks:
            if not isinstance(b, dict) or set(b) != BLOCK_KEYS:
                errors.append(f"{where}: block keys must be exactly {sorted(BLOCK_KEYS)}")
                continue
            at = f"{where} block {b['n']}"
            if b["match"] not in MATCHES:
                errors.append(f"{at}: match must be one of {sorted(MATCHES)}")
            if r["page_kind"] == "not_content" and b["match"] != "not_content":
                errors.append(f"{at}: a not_content page has only not_content blocks")
            if len(squash(b["text"]).split()) > MAX_BLOCK_WORDS:
                errors.append(f"{at}: over {MAX_BLOCK_WORDS} words; split it")
            if len(text) >= IMAGE_PAGE_CHARS and squash(b["text"]) not in text:
                errors.append(f"{at}: not verbatim on the book page: {squash(b['text'])[:60]!r}")
            spans = b["handout"] if isinstance(b["handout"], list) else []
            if (b["match"] in LINKED) != bool(spans):
                errors.append(f"{at}: {b['match']} needs {'handout spans' if b['match'] in LINKED else 'no spans'}")
            for i, s in enumerate(spans):
                if not isinstance(s, dict) or set(s) != ALIGN_SPAN_KEYS:
                    errors.append(f"{at} span {i}: keys must be exactly {sorted(ALIGN_SPAN_KEYS)}")
                    continue
                if s["pdf_page"] not in printed:
                    errors.append(f"{at} span {i}: handout pdf_page {s['pdf_page']} does not exist")
                    continue
                if s["printed_page"] != printed[s["pdf_page"]]:
                    errors.append(f"{at} span {i}: printed_page for pdf {s['pdf_page']} must be {printed[s['pdf_page']]}")
                if len(squash(s["text"]).split()) > MAX_SPAN_WORDS:
                    errors.append(f"{at} span {i}: over {MAX_SPAN_WORDS} words")
                if not resolve_span(lines, s["pdf_page"], s["text"], s["figure"]):
                    errors.append(f"{at} span {i}: not verbatim on handout pdf page {s['pdf_page']}: {squash(s['text'])[:60]!r}")
        if len(text) >= IMAGE_PAGE_CHARS and r["page_kind"] == "content":
            cov = coverage(text, [squash(b.get("text")) for b in blocks if isinstance(b, dict)])
            if cov < MIN_COVERAGE:
                errors.append(f"{where}: blocks cover {cov:.0%} of the page; at least {MIN_COVERAGE:.0%}")
    missing = [p for p in pages if p not in seen]
    if missing:
        errors.append(f"missing {len(missing)} pages: {missing[:3]}")
    if len(seen) != len(set(seen)):
        errors.append("a page appears twice")
    return errors


def alignment_import_rows(rows, lines):
    """Checked align rows as importSiteBook page rows, with each block's handout line IDs."""
    lines = as_lines(lines)
    out = []
    for r in rows:
        blocks = []
        for b in r["blocks"]:
            ids = [i for s in b["handout"] for i in resolve_span(lines, s["pdf_page"], s["text"], s["figure"])]
            blocks.append({**b, "line_ids": list(dict.fromkeys(ids))})
        out.append({"book_id": r["book_id"], "page": r["page"], "page_kind": r["page_kind"],
                    "lecture_id": r["lecture_id"], "blocks": blocks})
    return out

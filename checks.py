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


# ---- lectures -------------------------------------------------------------------------------------------------
STAMP = re.compile(r"^\s*\[(\d{1,3}):(\d{2})(?::(\d{2}))?\]")
TOKEN = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
FIX_KEYS = {"at", "heard", "meant", "confidence", "reason"}
APPLY_AT = 0.9            # owner 2026-11-07: a fix this sure replaces the word; lower ones wait for the owner


def stamp_seconds(line):
    m = STAMP.match(line)
    if not m:
        return None
    a, b, c = (int(x) if x else None for x in m.groups())
    return a * 3600 + b * 60 + c if c is not None else a * 60 + b


def paragraphs(text):
    """[(seconds, text)] for every timestamped paragraph; untimed lines join the paragraph before them."""
    out = []
    for line in text.splitlines():
        s = stamp_seconds(line)
        if s is not None:
            out.append([s, STAMP.sub("", line, count=1).strip()])
        elif line.strip() and out:
            out[-1][1] += " " + line.strip()
    return [tuple(p) for p in out]


def check_transcript(text, duration_s, end_slack=90, chars_per_min=None):
    """Counts only: timestamps rise, the last sits near the end, the text is dense enough for speech."""
    paras = paragraphs(text)
    if not paras:
        return ["no [mm:ss] timestamps"]
    errors = []
    for i in range(1, len(paras)):
        if paras[i][0] < paras[i - 1][0]:
            errors.append(f"timestamp {i + 1} goes back in time ({paras[i][0]} s after {paras[i - 1][0]} s)")
    last = paras[-1][0]
    if last > duration_s + 5:
        errors.append(f"last timestamp {last} s is after the end of the recording ({duration_s:.0f} s)")
    elif last < duration_s - end_slack:
        errors.append(f"last timestamp {last} s is {duration_s - last:.0f} s before the end: the end is missing")
    if chars_per_min:
        rate = sum(len(p[1]) for p in paras) / max(duration_s / 60, 1)
        low, high = chars_per_min
        if not low <= rate <= high:
            errors.append(f"{rate:.0f} characters per minute is outside {low}-{high}: words missing or repeated")
    return errors


# Timing pass (spike 2026-11-07: a worker's own [mm:ss] overshoot or fall short by minutes). The audio is cut into
# CHUNK_SECONDS pieces with known offsets; the worker names where each piece's first words sit in its transcript,
# and every paragraph's time is set between those anchors by word position.
CHUNK_SECONDS = 300
TIMING_KEYS = {"chunk", "paragraph", "first_words", "silent"}
TIMING_MIN_WORDS = 4


def timing_anchors(text, rows, chunks, chunk_s=CHUNK_SECONDS):
    """(errors, [(word index, seconds)]). Errors give chunk and paragraph numbers, never words."""
    paras = paragraphs(text)
    if not paras:
        return ["no [mm:ss] paragraphs"], []
    words, starts = [], []
    for _, body in paras:
        starts.append(len(words))
        words += [t.lower() for t in TOKEN.findall(body)]
    starts.append(len(words))
    if [r.get("chunk") if isinstance(r, dict) else None for r in rows] != list(range(chunks)):
        return [f"timing.jsonl needs one row per chunk, chunk 0 to {chunks - 1} in order; it has {len(rows)} rows"], []
    errors, anchors = [], []
    for r in rows:
        c = r["chunk"]
        if set(r) - TIMING_KEYS:
            errors.append(f"chunk {c}: unknown fields {sorted(set(r) - TIMING_KEYS)}")
            continue
        if r.get("silent") is True:
            continue
        p = r.get("paragraph")
        if not isinstance(p, int) or isinstance(p, bool) or not 1 <= p <= len(paras):
            errors.append(f"chunk {c}: paragraph must be 1 to {len(paras)}")
            continue
        want = [t.lower() for t in TOKEN.findall(str(r.get("first_words") or ""))]
        if len(want) < TIMING_MIN_WORDS:
            errors.append(f"chunk {c}: first_words needs at least {TIMING_MIN_WORDS} words copied from the transcript")
            continue
        hits = [i for i in range(starts[p - 1], starts[p]) if words[i:i + len(want)] == want]
        later = [i for i in hits if not anchors or i > anchors[-1][0]]
        if not hits:
            errors.append(f"chunk {c}: first_words are not in paragraph {p} word for word")
        elif not later:
            errors.append(f"chunk {c}: its words come before the previous chunk's; chunks follow each other")
        else:
            anchors.append((later[0], c * chunk_s))
    if not errors and not anchors:
        errors.append("every chunk is silent")
    return errors, anchors


def retime(text, anchors, duration_s):
    """text with each paragraph's [mm:ss] set by word position between the anchors (start 0 s, end duration_s)."""
    total = sum(len(TOKEN.findall(body)) for _, body in paragraphs(text))
    pts = sorted(anchors)
    if pts[0][0] > 0:
        pts.insert(0, (0, 0))
    if pts[-1][0] < total:
        pts.append((total, max(duration_s, pts[-1][1])))

    def at(w):
        for (w0, t0), (w1, t1) in zip(pts, pts[1:]):
            if w0 <= w <= w1:
                return t0 if w1 == w0 else t0 + (t1 - t0) * (w - w0) / (w1 - w0)
        return pts[-1][1]

    out, seen, started = [], 0, False  # words before the first stamp are not in paragraphs(), so not counted
    for line in text.splitlines():
        m = STAMP.match(line)
        if m:
            started, t = True, int(at(seen))
            line = f"[{t // 60:02d}:{t % 60:02d}]" + line[m.end():]
        if started:
            seen += len(TOKEN.findall(STAMP.sub("", line, count=1)))
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def check_timed_transcript(text, rows, duration_s, chunks, chunk_s=CHUNK_SECONDS):
    """(errors, retimed text): the timing rows, then the usual transcript check on the retimed text."""
    errors, anchors = timing_anchors(text, rows, chunks, chunk_s)
    if errors:
        return errors, None
    timed = retime(text, anchors, duration_s)
    return check_transcript(timed, duration_s), timed


def check_job_transcript(job_dir):
    """(errors, retimed text) for a transcribe job folder: transcript.txt, timing.jsonl and job.json."""
    from pathlib import Path
    import json
    d = Path(job_dir)
    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    need = [n for n in ("transcript.txt", "timing.jsonl") if not (d / n).exists()]
    if need:
        return [f"{' and '.join(need)} missing"], None
    try:
        rows = [json.loads(x) for x in (d / "timing.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    except ValueError as e:
        return [f"a line of timing.jsonl is not JSON ({e})"], None
    return check_timed_transcript((d / "transcript.txt").read_text(encoding="utf-8"), rows, job["duration_s"],
                                  job["chunks"], job.get("chunk_s", CHUNK_SECONDS))


def tokens(text):
    """Words, lowercased, with each line's leading [mm:ss] left out."""
    return [t.lower() for line in str(text).splitlines() for t in TOKEN.findall(STAMP.sub("", line, count=1))]


def word_time(text, index):
    """The [mm:ss] of the paragraph holding word `index` (0-based) of text."""
    seen, stamp = 0, "start"
    for line in str(text).splitlines():
        if STAMP.match(line):
            stamp = STAMP.match(line).group(0).strip()
        seen += len(TOKEN.findall(STAMP.sub("", line, count=1)))
        if seen > index:
            break
    return stamp


def applied(fixes, decisions=None):
    """Fixes in clean.txt: 0.9 or more, unless the owner kept the heard word; under 0.9 only when the owner took it.
    decisions: {"<fix index>": "take" | "keep"} from the admin page."""
    decisions = decisions or {}

    def on(i, f):
        d = decisions.get(str(i))
        return d == "take" or (d != "keep" and f.get("confidence", 0) >= APPLY_AT)
    return [f for i, f in enumerate(fixes) if isinstance(f, dict) and on(i, f)]


def check_fixes(fixes):
    errors = []
    for i, f in enumerate(fixes):
        if not isinstance(f, dict) or set(f) != FIX_KEYS:
            errors.append(f"fix {i + 1}: keys must be exactly {sorted(FIX_KEYS)}")
        elif not (isinstance(f["confidence"], (int, float)) and 0 <= f["confidence"] <= 1):
            errors.append(f"fix {i + 1}: confidence must be a number from 0 to 1")
        elif not tokens(f["heard"]) or not tokens(f["meant"]) or tokens(f["heard"]) == tokens(f["meant"]):
            errors.append(f"fix {i + 1}: heard and meant must be different words")
        elif stamp_seconds(f"[{f['at']}]") is None:
            errors.append(f"fix {i + 1}: at must be mm:ss")
    return errors


def expected_tokens(raw, fixes, decisions=None):
    """The raw words with every applied fix put in, each at its next occurrence after the previous fix."""
    words, pos = tokens(raw), 0
    for f in applied(fixes, decisions):
        heard, meant = tokens(f["heard"]), tokens(f["meant"])
        for i in range(pos, len(words) - len(heard) + 1):
            if words[i:i + len(heard)] == heard:
                words[i:i + len(heard)] = meant
                pos = i + len(meant)
                break
        else:
            return None, f"an applied fix at [{f['at']}] is not in the raw transcript after the previous fix"
    return words, None


def check_clean(raw, clean, fixes, decisions=None):
    """clean.txt is raw.txt laid out again: the same words in the same order, except the applied fixes.
    Errors give positions, never the words, so a reader of the log never needs the transcript."""
    errors = check_fixes(fixes)
    if errors:
        return errors
    want, problem = expected_tokens(raw, fixes, decisions)
    if problem:
        return [problem]
    got = tokens(clean)
    for i, (a, b) in enumerate(zip(want, got)):
        if a != b:
            return [f"word {i + 1} of clean.txt (paragraph {word_time(clean, i)}) differs from the raw transcript; "
                    f"the first {i} words match. Never change, add or drop a word; only lay out and punctuate"]
    if len(want) != len(got):
        return [f"clean.txt has {len(got)} words, the raw transcript (with applied fixes) has {len(want)}"]
    return []


PART_KEYS = {"part", "sub", "title", "start", "end", "line_ids"}


def check_links(parts, duration_s, lines, lecture_pages=None):
    """Parts in order, inside the recording, not overlapping; every line real and inside the lecture's pages."""
    pages = {ln["id"]: ln["page"] for ln in lines}
    errors, prev_top = [], None
    tops = {}
    for i, p in enumerate(parts, 1):
        if not isinstance(p, dict) or set(p) != PART_KEYS:
            errors.append(f"part row {i}: keys must be exactly {sorted(PART_KEYS)}")
            continue
        at = f"part {p['part']}.{p['sub']}"
        if not (0 <= p["start"] < p["end"] <= duration_s + 5):
            errors.append(f"{at}: start and end must satisfy 0 <= start < end <= {duration_s:.0f}")
        if p["sub"] == 0:
            if prev_top and (p["part"] != prev_top["part"] + 1 or p["start"] < prev_top["end"]):
                errors.append(f"{at}: parts must be numbered 1, 2, 3... and must not overlap")
            prev_top = tops[p["part"]] = p
        else:
            top = tops.get(p["part"])
            if not top or not (top["start"] <= p["start"] and p["end"] <= top["end"]):
                errors.append(f"{at}: a sub-part must follow its part and sit inside its times")
        for lid in p["line_ids"]:
            if lid not in pages:
                errors.append(f"{at}: {lid} is not a handout line")
            elif lecture_pages and not lecture_pages[0] <= pages[lid] <= lecture_pages[1]:
                errors.append(f"{at}: {lid} is outside the lecture's pages {lecture_pages[0]}-{lecture_pages[1]}")
    if not tops:
        errors.append("no parts")
    return errors


def link_report(parts, duration_s, lines, lecture_pages=None):
    """Share of the lecture's handout lines the parts cover, and share of the recording linked to a line."""
    pool = [ln["id"] for ln in lines if not lecture_pages or lecture_pages[0] <= ln["page"] <= lecture_pages[1]]
    used = {lid for p in parts for lid in p["line_ids"]}
    linked = sum(p["end"] - p["start"] for p in parts if p["sub"] == 0 and p["line_ids"])
    return {"lines_covered": round(len(used & set(pool)) / len(pool), 3) if pool else 0.0,
            "recording_linked": round(linked / duration_s, 3) if duration_s else 0.0}


def check_lecture_dir(job_dir, lines, duration_s, lecture_pages=None):
    """The clean, align and link job: clean.txt word for word, fixes well formed, parts valid."""
    from pathlib import Path
    import json
    d = Path(job_dir)
    need = [n for n in ("clean.txt", "fixes.jsonl", "parts.jsonl") if not (d / n).exists()]
    if need:
        return [f"missing {', '.join(need)}"]
    try:
        fixes = [json.loads(x) for x in (d / "fixes.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        parts = [json.loads(x) for x in (d / "parts.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    except ValueError as e:
        return [f"a line of fixes.jsonl or parts.jsonl is not JSON ({e})"]
    raw = (d / "raw.txt").read_text(encoding="utf-8")
    return check_clean(raw, (d / "clean.txt").read_text(encoding="utf-8"), fixes) + \
        check_links(parts, duration_s, lines, lecture_pages)


def check_cover(rows, batch, lines=None, reference=None):
    """Worker rows {i, match}: every item answered once, each match null or one of its listed candidates."""
    allowed = {b["i"]: set(b["candidates"]) for b in batch}
    errors, seen = [], set()
    for r in rows:
        if not isinstance(r, dict) or set(r) != {"i", "match"}:
            errors.append("each row must be exactly {i, match}")
            continue
        if r["i"] not in allowed:
            errors.append(f"item {r['i']} is not in the batch")
        elif r["match"] is not None and r["match"] not in allowed[r["i"]]:
            errors.append(f"item {r['i']}: match must be null or one of its listed candidates")
        seen.add(r["i"])
    missing = set(allowed) - seen
    if missing:
        errors.append(f"{len(missing)} items have no row")
    return errors


# ---- module lecture list and labels (plan task 13) ------------------------------------------------------------
LECTURE_KEYS = {"lecture_id", "title", "subject", "pdf_pages"}
REFERENCE_GAP = 0.05      # share of the handout's text pages (inside the lectures' span) that may sit in no lecture


def check_reference(ref, module, lines):
    """reference.json: lectures in handout order, ids <module>:L01.., ascending pdf ranges that may share an edge page."""
    lecs = ref.get("lectures") if isinstance(ref, dict) else None
    if not isinstance(lecs, list) or not lecs:
        return ['reference.json needs a non-empty "lectures" list']
    top = max((ln["page"] for ln in lines), default=0)
    text_pages = {ln["page"] for ln in lines if ln.get("figure") is None and len((ln.get("text") or "").strip()) > 3}
    errors, covered, prev_end = [], set(), 0
    for i, lec in enumerate(lecs, 1):
        if not isinstance(lec, dict):
            errors.append(f"lecture {i}: not an object")
            continue
        if set(lec) - LECTURE_KEYS:
            errors.append(f"lecture {i}: unknown fields {sorted(set(lec) - LECTURE_KEYS)}")
        if lec.get("lecture_id") != f"{module}:L{i:02d}":
            errors.append(f"lecture {i}: lecture_id must be {module}:L{i:02d}")
        for k in ("title", "subject"):
            if not isinstance(lec.get(k), str) or not lec[k].strip():
                errors.append(f"lecture {i}: {k} is empty")
        pp = lec.get("pdf_pages")
        if not (isinstance(pp, list) and len(pp) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in pp)
                and 1 <= pp[0] <= pp[1] <= top):
            errors.append(f"lecture {i}: pdf_pages must be [first, last] inside 1-{top}")
        elif pp[0] < prev_end:
            errors.append(f"lecture {i}: starts on pdf page {pp[0]}, before lecture {i - 1} ends ({prev_end})")
        else:
            prev_end = pp[1]
            covered |= set(range(pp[0], pp[1] + 1))
    if not errors:
        span = {p for p in text_pages if lecs[0]["pdf_pages"][0] <= p <= prev_end}
        gap = sorted(span - covered)
        if len(gap) > REFERENCE_GAP * max(len(span), 1):
            errors.append(f"{len(gap)} text pages sit in no lecture (pdf pages {gap[:15]}): every teaching page "
                          "belongs to its lecture")
    return errors


LABEL_KINDS = {"doctor", "past_exam", "ai", "student", "other"}
HEADER_LABEL_KEYS = {"hid", "module", "lecture_id", "doctor", "kind"}
POLL_LABEL_KEYS = {"wid", "module", "lecture_id"}


def check_labels(rows, batch, lines=None, reference=None):
    """Header rows {hid, module, lecture_id, doctor, kind} or question rows {wid, module, lecture_id}; every label
    from the closed lists in reference.json (modules, lectures per module, doctors). "mixed" only for a header."""
    ref = reference or {}
    modules, lectures = set(ref.get("modules") or {}), ref.get("lectures") or {}
    doctors = set(ref.get("doctors") or [])
    idf = "hid" if batch and "hid" in batch[0] else "wid"
    keys = HEADER_LABEL_KEYS if idf == "hid" else POLL_LABEL_KEYS
    allowed = modules | {"none"} | ({"mixed"} if idf == "hid" else set())
    want = [b[idf] for b in batch]
    errors, seen = [], []
    for n, r in enumerate(rows, 1):
        if not isinstance(r, dict) or set(r) != keys:
            errors.append(f"row {n}: must have exactly the fields {sorted(keys)}")
            continue
        rid = r[idf]
        seen.append(rid)
        if rid not in want:
            errors.append(f"row {n}: {idf} {rid} is not in the batch")
            continue
        if r["module"] not in allowed:
            errors.append(f"{idf} {rid}: module must be one of {sorted(allowed)}")
        elif r["lecture_id"] is not None and r["lecture_id"] not in {x["lecture_id"] for x in lectures.get(r["module"], [])}:
            errors.append(f"{idf} {rid}: lecture_id must be null or a lecture of {r['module']} in reference.json")
        if idf == "hid":
            if r["doctor"] is not None and r["doctor"] not in doctors:
                errors.append(f"hid {rid}: doctor must be null or a name from the doctors list")
            if r["kind"] not in LABEL_KINDS:
                errors.append(f"hid {rid}: kind must be one of {sorted(LABEL_KINDS)}")
    if len(seen) != len(set(seen)):
        errors.append("an id has more than one row")
    missing = set(want) - set(seen)
    if missing:
        errors.append(f"{len(missing)} items have no row")
    return errors


# ---- importance highlights (owner 2026-11-08) ----------------------------------------------------------------------
MARK_KEYS = {"line_ids", "text", "kind", "evidence", "why"}
MARK_WORDS = {"word": (1, 3), "sentence": (4, 40)}   # owner: a highlight is 1-3 words; a stressed sentence is underlined
LECTURE_EVIDENCE = {"said_mcq", "said_important", "stressed"}
MCQ_EVIDENCE = {"doctor_mcq", "other_mcq"}
MAX_QUOTE_WORDS, MAX_WHY_WORDS = 30, 15
AUDIT_KEYS = {"n", "keep", "reason"}


def words(text):
    return TOKEN.findall(str(text or ""))


def norm(text):
    """Words only, lower case: a quote matches the transcript whatever its punctuation or spacing."""
    return " ".join(words(text)).lower()


def on_lines(text, joined):
    """text sits on the lines as whole words (spacing may differ)."""
    return bool(text) and re.search(r"(?<!\w)" + re.escape(text) + r"(?!\w)", joined) is not None


def check_evidence(e, ids, lns, qs, lectures):
    t = e.get("type") if isinstance(e, dict) else None
    if t in MCQ_EVIDENCE:
        if set(e) != {"type", "qid"}:
            return [f"{t} evidence is exactly {{type, qid}}"]
        q = qs.get(e["qid"])
        if q is None:
            return [f"question {e['qid']} is not in batch.jsonl"]
        if (t == "doctor_mcq") != (q["kind"] == "doctor"):
            right = "doctor_mcq" if q["kind"] == "doctor" else "other_mcq"
            return [f"question {e['qid']} is a {q['kind']} MCQ: its evidence type is {right}"]
        if not set(q.get("line_ids") or []) & set(ids):
            return [f"question {e['qid']} is not pointed at these lines"]
        return []
    if t not in LECTURE_EVIDENCE:
        return [f"evidence type must be one of {sorted(LECTURE_EVIDENCE | MCQ_EVIDENCE)}"]
    need = {"type", "lecture", "at"} | ({"quote"} if t != "stressed" else set())
    if set(e) != need:
        return [f"{t} evidence is exactly {{{', '.join(sorted(need))}}}"]
    lec = lectures.get(e["lecture"])
    if lec is None:
        return [f"lecture {e['lecture']} is not in lectures/"]
    stamps = e["at"] if t == "stressed" else [e["at"]]
    if t == "stressed" and (not isinstance(stamps, list) or len({str(s) for s in stamps}) < 2):
        return ["stressed needs 2 or more different times in at (a list of mm:ss)"]
    errors = []
    for s in stamps:
        sec = stamp_seconds(f"[{s}]") if isinstance(s, str) else None
        if sec is None or sec > (lec["duration_s"] or 0) + 5:
            errors.append(f"at {s!r} is not a mm:ss time inside lecture {e['lecture']}")
    if not {ln["page"] for ln in lns} & lec["pages"]:
        errors.append(f"lecture {e['lecture']} has no part on pdf page {lns[0]['page']}")
    if t != "stressed":
        quote = norm(e["quote"])
        if not quote or len(quote.split()) > MAX_QUOTE_WORDS:
            errors.append(f"quote has 1 to {MAX_QUOTE_WORDS} words")
        elif f" {quote} " not in f" {lec['norm']} ":
            errors.append(f"quote is not word for word in lectures/{e['lecture']}/clean.txt")
    return errors


def check_marks(rows, batch, lines, lectures, pages):
    """rows: marks.jsonl; batch: the lesson's MCQs; lectures: {id: {norm, duration_s, pages}}; pages: [first, last]."""
    idx = {ln["id"]: i for i, ln in enumerate(lines)}
    qs = {q["qid"]: q for q in batch}
    first, last = pages
    errors, seen = [], set()
    for n, r in enumerate(rows, 1):
        at = f"row {n}"
        if not isinstance(r, dict) or set(r) != MARK_KEYS:
            errors.append(f"{at}: keys must be exactly {sorted(MARK_KEYS)}")
            continue
        ids = r["line_ids"]
        if not isinstance(ids, list) or not ids or any(i not in idx for i in ids):
            errors.append(f"{at}: line_ids must be a list of IDs from inputs/lines.jsonl")
            continue
        pos = [idx[i] for i in ids]
        if pos != list(range(pos[0], pos[0] + len(pos))):
            errors.append(f"{at}: line_ids must be neighbouring lines in reading order")
            continue
        lns = [lines[p] for p in pos]
        if any(ln.get("figure") is not None for ln in lns):
            errors.append(f"{at}: a figure cannot be highlighted")
            continue
        if any(not first <= ln["page"] <= last for ln in lns):
            errors.append(f"{at}: a line is outside this lesson's pdf pages {first}-{last}")
        if r["kind"] not in MARK_WORDS:
            errors.append(f"{at}: kind is word or sentence")
            continue
        text = squash(r["text"])
        if not on_lines(text, squash(" ".join(ln["text"] for ln in lns))):
            errors.append(f"{at}: text is not word for word on its lines")
        elif len(lns) > 1 and (on_lines(text, squash(" ".join(ln["text"] for ln in lns[1:])))
                               or on_lines(text, squash(" ".join(ln["text"] for ln in lns[:-1])))):
            errors.append(f"{at}: line_ids hold more lines than the text needs")
        low, high = MARK_WORDS[r["kind"]]
        if not low <= len(words(text)) <= high:
            errors.append(f"{at}: a {r['kind']} mark has {low} to {high} words, this one has {len(words(text))}")
        key = (tuple(ids), text, r["kind"])
        if key in seen:
            errors.append(f"{at}: the same mark twice (put all its evidence in one row)")
        seen.add(key)
        if not isinstance(r["why"], str) or not r["why"].strip() or len(words(r["why"])) > MAX_WHY_WORDS:
            errors.append(f"{at}: why is a reason of 1 to {MAX_WHY_WORDS} words")
        if not isinstance(r["evidence"], list) or not r["evidence"]:
            errors.append(f"{at}: evidence must list at least one item")
            continue
        for e in r["evidence"]:
            errors += [f"{at}: {m}" for m in check_evidence(e, ids, lns, qs, lectures)]
    return errors


def _jsonl(path):
    import json
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def job_lectures(job_dir, lines):
    """{id: {norm, duration_s, doctor, pages}} from the lectures/ folder of a highlights job."""
    from pathlib import Path
    import json
    page_of = {ln["id"]: ln["page"] for ln in lines}
    out = {}
    for d in sorted(p for p in (Path(job_dir) / "lectures").glob("*") if p.is_dir()):
        meta = json.loads((d / "lecture.json").read_text(encoding="utf-8"))
        out[d.name] = {"norm": norm((d / "clean.txt").read_text(encoding="utf-8")),
                       "duration_s": meta.get("duration_s"), "doctor": meta.get("doctor"),
                       "pages": {page_of[i] for p in _jsonl(d / "parts.jsonl") for i in p["line_ids"] if i in page_of}}
    return out


def check_job_marks(job_dir):
    """The highlights job: marks.jsonl against its lines, MCQs and lectures (same code on the worker and here)."""
    from pathlib import Path
    import json
    d = Path(job_dir)
    if not (d / "marks.jsonl").exists():
        return ["marks.jsonl does not exist"]
    try:
        rows = _jsonl(d / "marks.jsonl")
    except ValueError as e:
        return [f"a line of marks.jsonl is not JSON ({e})"]
    lines = _jsonl(d / "inputs" / "lines.jsonl")
    job = json.loads((d / "job.json").read_text(encoding="utf-8"))
    return check_marks(rows, _jsonl(d / "batch.jsonl"), lines, job_lectures(d, lines), job["pages"])


def check_audit(rows, batch, lines=None, reference=None):
    """Audit rows {n, keep, reason}: every item answered once."""
    want = {b["n"] for b in batch}
    errors, seen = [], set()
    for r in rows:
        if not isinstance(r, dict) or set(r) != AUDIT_KEYS:
            errors.append(f"each row must be exactly {sorted(AUDIT_KEYS)}")
            continue
        if r["n"] not in want:
            errors.append(f"n {r['n']!r} is not an item of batch.jsonl")
        if r["n"] in seen:
            errors.append(f"n {r['n']} has more than one row")
        seen.add(r["n"])
        if not isinstance(r["keep"], bool):
            errors.append(f"n {r['n']}: keep is true or false")
        if not isinstance(r["reason"], str) or not r["reason"].strip() or len(words(r["reason"])) > MAX_WHY_WORDS:
            errors.append(f"n {r['n']}: reason is 1 to {MAX_WHY_WORDS} words")
    if want - seen:
        errors.append(f"{len(want - seen)} items have no row")
    return errors

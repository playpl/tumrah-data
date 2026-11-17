"""Visual PDF rows -> atomic sentences. Shared by the handout and the doctors' books; knows neither.

A row is a dict {id, page, n, text, bbox, figure} (the shape of `lines.jsonl`). `build(rows, ...)` returns
sentences in order: {kind, marker, text, rows: [row dicts], ctx: [str], first: row dict}.

Rules, in this order:
 1. A figure row is its own unit. A heading row (the caller says which) is its own unit.
 2. Rows inside one row of a ruled table are one unit; its text is the cells joined with " | ".
 3. A row that starts with a bullet or a list label starts a unit; the marker is kept apart from the text.
 4. A row continues the unit when the row before it is a wrapped line: the first word of this row would not
    have fitted in the space left before the page's right margin; or (text in a narrow column beside a figure)
    the row before it does not end a sentence and this row starts with a small letter. Not after a lead-in
    ending in ":", not after a jump down the page, not when this row is further left than the unit's first row.
 5. A unit is cut into sentences at `. ? !` followed by a capital letter, unless the dot belongs to an
    abbreviation or either side would have fewer than three words.
 6. Every sentence carries `ctx`: the last heading plus the short lines it is nested under ("The motor nuclei are:").
"""
import re
from collections import Counter

from spine import text as T

WRAP_SLACK = 3.0        # pt of tolerance in the "next word would not fit" test
LEAD_WORDS = 12         # a line ending in ":" with at most this many words is a lead-in
LABEL_WORDS = 8         # a short line with no sentence end can be the parent of the lines nested under it
CTX_DEPTH = 4
MIN_SIDE_WORDS = 3

_BULLET = r"[-•▪■□●○◦➢➤❖✓✔◆◇*#►▶→·\-–—−]"
MARKER = re.compile(rf"^\s*(?:({_BULLET}+)\s*(?=\S)|(\(?(?:\d{{1,2}}|[A-Za-z]|[ivxIVX]{{2,4}})[.)\-])\s+(?=\S)"
                    r"|(o)\s+(?=[A-Z]))")        # a small "o" before a capital is a hollow bullet
_SPLIT = re.compile(r"(?<=[.?!])[\"')\]]?\s+(?=[A-Z(ء-ي])")
_WORD = re.compile(r"\S+")


def split_marker(s):
    """("•", "text") or ("2.", "text"); ("", text) when the row starts with no marker."""
    m = MARKER.match(s)
    if not m:
        return "", s.strip()
    marker = (m.group(1) or m.group(2) or m.group(3)).strip()
    if marker in ("-", "–", "—", "−") and re.match(r"\s*\d", s[m.end():]):   # "-5 mV", "– 70": a number, not a bullet
        return "", s.strip()
    return marker, s[m.end():].strip()


def page_geometry(rows):
    """{page: (left, right)}: where text starts and where a full line ends on that page."""
    by_page = {}
    for r in rows:
        if r.get("figure") is None and r.get("text"):
            by_page.setdefault(r["page"], []).append(r["bbox"])
    rights = sorted(max(b[2] for b in boxes) for boxes in by_page.values() if len(boxes) >= 8)
    usual = rights[len(rights) // 2] if rights else 0
    geo = {}
    for page, boxes in by_page.items():
        x1 = sorted(b[2] for b in boxes)
        right = x1[min(len(x1) - 1, int(len(x1) * 0.95))] if len(boxes) >= 8 else max(usual, x1[-1])
        geo[page] = (min(b[0] for b in boxes), right)
    return geo


def wraps(prev, nxt_text, right):
    """True when `prev` is a wrapped line: the first word of the next row did not fit after it."""
    txt = prev["text"].strip()
    words = _WORD.findall(nxt_text)
    if not txt or not words:
        return False
    x0, _, x1, _ = prev["bbox"]
    char = (x1 - x0) / max(len(txt), 1)
    return right - x1 <= (len(words[0]) + 1) * char + WRAP_SLACK


def _table_rows(tables, row):
    """Index (table number, row number) of the table row this visual row sits in, or None."""
    x0, y0, x1, y1 = row["bbox"]
    mid = (y0 + y1) / 2
    for ti, table in enumerate(tables or []):
        for ri, tr in enumerate(table["rows"]):
            b = tr["bbox"]
            if b[1] - 1 <= mid <= b[3] + 1 and x0 >= b[0] - 5 and x1 <= b[2] + 5:
                return ti, ri
    return None


def _join(parts, vocab):
    """Rows of one unit as one text, with the character span of each row. A word hyphenated over the line
    break is rejoined only when the joined word is used somewhere else in the document."""
    out, spans = "", []
    for row, s in parts:
        if out:
            m, first = re.search(r"([A-Za-z]{2,})-$", out), re.match(r"[a-z]{2,}", s)
            if m and first and vocab.get((m.group(1) + first.group(0)).lower(), 0) > 0:
                out = out[:-1]
            else:
                out += " "
        spans.append((len(out), len(out) + len(s), row))
        out += s
    return out, spans


def cut_sentences(s):
    """[(start, end)] of the sentences inside one unit's text."""
    cuts, start, depth_at = [], 0, 0
    for m in _SPLIT.finditer(s):
        left, right = s[start:m.start()], s[m.end():]
        depth_at = s[:m.start()].count("(") - s[:m.start()].count(")")
        if (depth_at <= 0 and T.ends_sentence(left) and len(_WORD.findall(left)) >= MIN_SIDE_WORDS
                and len(_WORD.findall(right)) >= MIN_SIDE_WORDS):
            cuts.append((start, m.start()))
            start = m.end()
    cuts.append((start, len(s)))
    return cuts


def units(rows, headings=(), tables=None, breaks=()):
    """Rules 1 to 4: rows grouped into units {kind, marker, parts: [(row, text)], indent, page}."""
    headings, breaks = set(headings), set(breaks)
    geo = page_geometry(rows)
    out, cur, last_text = [], None, None       # last_text: the text row before this one, across figures
    for row in rows:
        if row.get("figure") is not None:
            out.append({"kind": "figure", "marker": "", "parts": [(row, row.get("figure") or "")],
                        "indent": 0, "page": row["page"]})
            continue
        raw = (row.get("text") or "").strip()
        left, right = geo.get(row["page"], (0, 0))
        cell = _table_rows((tables or {}).get(row["page"]), row)
        prev, last_text = last_text, row
        if cell is not None:
            if cur and cur.get("cell") == (row["page"], *cell):
                cur["parts"].append((row, raw))
            else:
                cur = {"kind": "table_row", "marker": "", "parts": [(row, raw)], "indent": 0, "page": row["page"],
                       "cell": (row["page"], *cell)}
                out.append(cur)
            continue
        marker, body = split_marker(raw)
        heading = row["id"] in headings
        joins = False
        if (cur and cur["kind"] == "fact" and prev is not None and prev is cur["parts"][-1][0] and not marker
                and not heading and row["id"] not in breaks and not prev["text"].rstrip().endswith((":", "?"))):
            if prev["page"] == row["page"]:
                gap = row["bbox"][1] - prev["bbox"][3]
                open_end = ((raw[:1].islower() or raw[:1] in "(&→,;")
                            and not prev["text"].rstrip().endswith(T.SENTENCE_END))
                joins = ((wraps(prev, raw, right) or open_end) and gap <= prev["bbox"][3] - prev["bbox"][1]
                         and row["bbox"][0] >= cur["x0"] - 3)
            elif prev["page"] + 1 == row["page"]:
                joins = raw[:1].islower() and not prev["text"].rstrip().endswith(T.SENTENCE_END)
        if joins:
            cur["parts"].append((row, raw))
            continue
        cur = {"kind": "heading" if heading else "fact", "marker": marker, "parts": [(row, body)], "indent": row["bbox"][0] - left, "x0": row["bbox"][0],
               "page": row["page"]}
        out.append(cur)
    return out


def build(rows, headings=(), tables=None, breaks=()):
    """Rows -> sentences, with context. See the module docstring for the rules."""
    vocab = Counter(t for r in rows for t in T.tokens(r.get("text") or ""))
    out, stack, heading, header = [], [], None, {}
    for u in units(rows, headings, tables, breaks):
        first = u["parts"][0][0]
        if u["kind"] == "figure":
            out.append({"kind": "figure", "marker": "", "text": u["parts"][0][1], "rows": [first],
                        "ctx": [heading] if heading else [], "first": first})
            continue
        if u["kind"] == "table_row":
            page, ti, ri = u["cell"]
            cells = [" ".join((c or "").split()) for c in tables[page][ti]["rows"][ri]["cells"]]
            text = " | ".join(c for c in cells if c) or " ".join(s for _, s in u["parts"])
            ctx = [heading] if heading else []
            if header.get((page, ti)) is None:
                header[(page, ti)] = text
            else:
                ctx = ctx + [header[(page, ti)][:120]]
            out.append({"kind": "table_row", "marker": "", "text": text, "rows": [r for r, _ in u["parts"]],
                        "ctx": ctx, "first": first})
            continue
        text, spans = _join(u["parts"], vocab)
        if u["kind"] == "heading":
            heading, stack = text[:120], []
            out.append({"kind": "heading", "marker": u["marker"], "text": text, "rows": [first], "ctx": [], "first": first})
            continue
        cuts = cut_sentences(text)
        last = text[cuts[-1][0]:cuts[-1][1]].strip()        # "…oblongata. Termination:" leads in with its last sentence
        n_words = len(_WORD.findall(last))
        lead = last.endswith(":") and n_words <= LEAD_WORDS
        label = lead or (len(cuts) == 1 and n_words <= LABEL_WORDS and not T.ends_sentence(text))
        # Leave what this unit is not nested under: deeper lines, and lines at its own level unless one of them
        # is a lead-in ("Definition:") that this plain line answers.
        while stack and (stack[-1][0] > u["indent"] + 1
                         or (abs(stack[-1][0] - u["indent"]) <= 1 and (label or not stack[-1][2]))):
            stack.pop()
        ctx = ([heading] if heading else []) + [s for _, s, _ in stack][-(CTX_DEPTH - 1):]
        for a, b in cuts:
            piece = text[a:b].strip()
            mine = [row for s, e, row in spans if s < b and e > a] or [first]
            if piece:
                out.append({"kind": "fact", "marker": u["marker"] if a == 0 else "", "text": piece, "rows": mine,
                            "ctx": ctx, "first": mine[0]})
        if label:
            stack.append((u["indent"], last[:100], lead))
    return out

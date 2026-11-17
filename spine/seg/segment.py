"""Phase 2 reader task: a lecture's transcript paragraphs -> ranges of its doctor's book, strictly forward.

The reader gets a BOOK block (the slice, numbered B1..Bk, headings as `## ...`) and a TRANSCRIPT block
(P1..Pn with their time stamps), and answers one line per segment:

    P<a>-P<b> = B<c>-B<d>
    P<a>-P<b> = NONE

Code checks (`check`): the first segment starts at P1, each next one at the previous end + 1, the last ends at Pn;
c <= d; c of a segment >= d of the segment before it (NONE segments do not count); a segment holds at most
`MAX_PARAS` paragraphs and `MAX_RANGE` book sentences. `repair` keeps the longest forward chain (weighted by
paragraphs) and turns the rest into bounded re-asks: "choose a range inside B<lo>-B<hi>, or NONE".
"""
import re

LINE = re.compile(r"^\s*P(\d+)(?:\s*-\s*P(\d+))?\s*=\s*(?:B(\d+)(?:\s*-\s*B(\d+))?|(NONE))\s*$", re.I)
# Formatting only, never meaning: byte-order mark, no-break and zero-width spaces, typographic dashes, Arabic-Indic
# digits, a colon or arrow for "=". A line that still looks like a segment after this is an error, not prose.
_FOLD = {**{c: None for c in (0xFEFF, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060)}, 0xA0: " ",
         **{c: "-" for c in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2212, 0xFE58, 0xFE63, 0xFF0D)},
         **{c: "=" for c in (0x3A, 0x2192)},
         **{0x660 + i: str(i) for i in range(10)}, **{0x6F0 + i: str(i) for i in range(10)}}
BULLET = re.compile(r"^(?:[-*" + chr(0x2022) + r"]+|\d{1,2}[.)])\s+")
SEG_LIKE = re.compile(r"P\s*\d+\s*(?:-\s*P?\s*\d+\s*)?=", re.I)     # a range then "=" anywhere in the line, read
# after norm(): "Segment 3: P5-P9 = B7-B9" is a segment we could not read, not prose (searched, not matched at the start)
MAX_PARAS, MAX_RANGE = 12, 120
MAX_HOLE = 3                      # paragraphs a hole (filled as NONE) or a conflicting overlap may span
# One identical book range may not hold more than this share of the paragraphs (min paragraphs for the rule).
DOMINANT_SHARE, DOMINANT_MIN = 0.3, 20
MAX_NONE = 0.5                    # share of paragraphs a reader may call NONE (talk with no book line)
MAX_CLIPPED = 0.2                 # share of paragraphs that may only restate the book lines already explained
MAX_OFFEND = 0.2                  # share of paragraphs a reader may get wrong and still be used after repair
AGREE_WITHIN, AGREE_SHARE = 5, 0.9
VERSION = 2          # 2: segments of at most 12 paragraphs, NONE only for talk with no book line

PROMPT = """You map a recorded medical lecture onto the doctor's own book.

BOOK lines are numbered B1, B2, ... in book order. Lines that start with ## are headings.
TRANSCRIPT paragraphs are numbered P1, P2, ... in time order; each starts with its time stamp. The doctor speaks
Egyptian Arabic and says the English terms in Arabic letters (for example "سبينال كورد" = spinal cord).

Cut the transcript into consecutive segments. A segment is a run of 1 to 12 paragraphs (about 6 minutes at most)
where the doctor explains one stretch of the book. For each segment write the first and last BOOK line it explains.
Read every paragraph: the doctor's Arabic explanation of an English heading or fact belongs to that book line.

Rules:
- Cover every paragraph exactly once, in order: the first segment starts at P1, the last ends at P{last}.
- The doctor moves down the book: a segment's first B is never smaller than the previous segment's last B.
- Use NONE only for talk that explains no book line at all (greetings, jokes, exam advice, a part the book does
  not have). The opening of a topic belongs to that topic's first book lines, not NONE. In a normal lecture NONE
  is under a quarter of the paragraphs.
- A segment is at most 12 paragraphs and at most 120 B lines. A long explanation of one stretch is several
  segments in a row.

Answer with these lines only, nothing else:
P<a>-P<b> = B<c>-B<d>
P<a>-P<b> = NONE
"""


def render(paras, sents):
    """The task text: prompt, BOOK block, TRANSCRIPT block. `sents` is the slice (B1 = sents[0])."""
    from spine.seg.prior import stamp
    book = []
    for i, s in enumerate(sents, 1):
        t = " ".join((s.get("text") or "").split())
        book.append(f"B{i} " + (f"## {t}" if s.get("kind") == "heading" else t))
    talk = [f"P{p['n']} [{stamp(p['start'])}] {' '.join(p['text'].split())}" for p in paras]
    return (PROMPT.replace("{last}", str(len(paras))) + "\nBOOK\n" + "\n".join(book)
            + "\n\nTRANSCRIPT\n" + "\n".join(talk) + "\n")


def norm(line):
    """A line with formatting removed: fold characters, markdown bold/code marks, a bullet or number, a final period."""
    line = (line or "").translate(_FOLD).strip()
    for _ in range(6):                             # wrappers nest ("**1. P8-P12 = NONE**"): peel until stable
        before = line
        line = BULLET.sub("", line).strip("`*_ \t").rstrip(".;").rstrip()
        if line == before:
            break
    return line


def parse(answer):
    """[{"p": [a, b], "b": [c, d] or None}] in answer order, and the lines that did not parse."""
    segs, bad = [], []
    for raw in (answer or "").splitlines():
        line = norm(raw)
        if not line:
            continue
        m = LINE.match(line)
        if not m:
            bad.append(raw.strip())
            continue
        a, b, c, d, none = m.groups()
        b = a if b is None else b                         # "P120 = B28-B34": one paragraph
        d = c if d is None else d                         # "P82-P84 = B40": one book line
        segs.append({"p": [int(a), int(b)], "b": None if none else [int(c), int(d)]})
    return segs, bad


def check(segs, n_paras, n_book):
    """Problems as text lines; an empty list means the answer is clean."""
    out = []
    if not segs:
        return ["no segment"]
    if segs[0]["p"][0] != 1:
        out.append(f"first segment starts at P{segs[0]['p'][0]}, not P1")
    if segs[-1]["p"][1] != n_paras:
        out.append(f"last segment ends at P{segs[-1]['p'][1]}, not P{n_paras}")
    last_d = 0
    for k, s in enumerate(segs):
        a, b = s["p"]
        if a > b:
            out.append(f"P{a}-P{b}: backwards")
        if k and a != segs[k - 1]["p"][1] + 1:
            out.append(f"P{a}-P{b}: does not start right after P{segs[k - 1]['p'][1]}")
        if b - a + 1 > MAX_PARAS:
            out.append(f"P{a}-P{b}: over {MAX_PARAS} paragraphs")
        if s["b"]:
            c, d = s["b"]
            if not (1 <= c <= d <= n_book):
                out.append(f"P{a}-P{b} = B{c}-B{d}: not a range of B1-B{n_book}")
            elif d - c + 1 > MAX_RANGE:
                out.append(f"P{a}-P{b} = B{c}-B{d}: over {MAX_RANGE} book lines")
            if c < last_d:
                out.append(f"P{a}-P{b} = B{c}-B{d}: goes back above B{last_d}")
            last_d = max(last_d, d)
    return out


def fill(segs, n_paras, max_hole=MAX_HOLE):
    """Holes of at most `max_hole` paragraphs (before the first, between two, after the last segment) become NONE
    segments. Returns (segments, holes filled) or (None, holes) when a hole is bigger."""
    out, want, holes = [], 1, 0
    for s in sorted(segs, key=lambda s: s["p"][0]):
        a, b = s["p"]
        if a > want:
            if a - want > max_hole:
                return None, a - want
            out.append({"p": [want, a - 1], "b": None, "flag": "filled"})
            holes += 1
        if a < want:                    # overlaps the one before: start after it
            if b < want:
                continue
            s = dict(s, p=[want, b])
        out.append(s)
        want = s["p"][1] + 1
    if want <= n_paras:
        if n_paras - want + 1 > max_hole:
            return None, n_paras - want + 1
        out.append({"p": [want, n_paras], "b": None, "flag": "filled"})
        holes += 1
    return out, holes


def conflict(segs):
    """(paragraphs, [a, b]): the most paragraphs one segment answers again with a different answer than an earlier
    segment, and that segment's paragraphs. fill() keeps the first answer and drops the rest, so a reader that
    answers a stretch twice (a draft, then a correction) would be read by its draft without a word. An exact
    repeat (same answer) is not a conflict; a one-paragraph boundary slip (P1-P12, P12-P20) is under MAX_HOLE."""
    seen, worst, where = {}, 0, None
    for s in sorted(segs, key=lambda s: s["p"][0]):
        a, b = s["p"]
        k = sum(1 for p in range(a, b + 1) if p in seen and seen[p] != s["b"])
        if k > worst:
            worst, where = k, s["p"]
        for p in range(a, b + 1):
            seen.setdefault(p, s["b"])
    return worst, where


def clip(segs):
    """A range that starts above the previous range's end but ends at or below it is the reader re-stating the
    stretch just explained: it starts at the previous end instead (flag "clipped"). A range wholly above stays
    (repair makes it a re-ask)."""
    out, last_d = [], 0
    for s in segs:
        if s["b"]:
            c, d = s["b"]
            if c < last_d <= d:                            # overlaps: start at the previous end
                s = dict(s, b=[last_d, d], flag="clipped")
            elif c == d == last_d:                         # re-states the last line only
                s = dict(s, flag="clipped")
            last_d = max(last_d, s["b"][1]) if s["b"][0] >= last_d else last_d
        out.append(s)
    return out


def dominant(segs, n_paras, share=DOMINANT_SHARE, min_paras=DOMINANT_MIN):
    """([B_c, B_d], share) of the one identical book range that holds more than `share` of the paragraphs, else None.
    A long talk sent to one place is a collapse, not an explanation (the cns-036 table)."""
    count = {}
    for s in segs:
        if s["b"]:
            key = tuple(s["b"])
            count[key] = count.get(key, 0) + (s["p"][1] - s["p"][0] + 1)
    if not count or n_paras < min_paras:
        return None
    key, n = max(count.items(), key=lambda kv: kv[1])
    if n / n_paras > share:
        return list(key), round(n / n_paras, 3)
    return None


def shares(segs, n_paras):
    """Problems of an answer's shape as the rules count them: NONE share, restated share, one dominant range.
    Run on the reader's answer AND on its repaired form, because repair can create a NONE-heavy or a
    restated answer that the first pass never saw (the fuzz found 6 of 10 NONE accepted that way)."""
    out = []
    none = sum(s["p"][1] - s["p"][0] + 1 for s in segs if not s["b"]) / n_paras
    if none > MAX_NONE:
        out.append(f"NONE for {none:.0%} of paragraphs (a lecture maps to its book)")
    restated = sum(s["p"][1] - s["p"][0] + 1 for s in segs if s.get("flag") == "clipped") / n_paras
    if restated > MAX_CLIPPED:
        out.append(f"re-states earlier book lines for {restated:.0%} of paragraphs")
    dom = dominant(segs, n_paras)
    if dom:
        out.append(f"one range B{dom[0][0]}-B{dom[0][1]} covers {dom[1]:.0%} of paragraphs")
    return out


def judge_segs(segs, n_paras, n_book, bad=()):
    """(repaired segments or None, problems, offending share) of one reader's parsed answer. `bad` are the lines
    that did not parse. Every acceptance rule lives here, so tests run the same code the collect step runs."""
    if n_paras <= 0:
        return None, ["no paragraphs"], 1.0
    if not segs:
        return None, ["no segment"], 1.0
    malformed = [b for b in bad if SEG_LIKE.search(norm(b))]
    if malformed:                                             # a segment line we could not read: never guess it
        return None, [f"{len(malformed)} segment line(s) did not parse, e.g. {malformed[0][:60]!r}"], 1.0
    outside = [s["p"] for s in segs if s["p"][0] < 1 or s["p"][1] > n_paras or s["p"][0] > s["p"][1]]
    if outside:                                               # P0, past the last paragraph, or reversed: a numbering slip
        a, b = outside[0]
        return None, [f"P{a}-P{b}: paragraph numbers outside P1-P{n_paras}"], 1.0
    twice, where = conflict(segs)
    if twice > MAX_HOLE:                                      # two different answers for one stretch: never pick one
        return None, [f"P{where[0]}-P{where[1]}: {twice} paragraphs answered twice, differently"], 1.0
    first = check(segs, n_paras, n_book)
    filled, holes = fill(segs, n_paras)
    if filled is None:
        return None, first + [f"a hole of {holes} paragraphs"], 1.0
    segs = clip(filled)                                       # code repairs: small holes -> NONE, overlaps clipped
    problems = check(segs, n_paras, n_book)
    why = shares(segs, n_paras)
    if why:
        return None, problems + why, 1.0
    order = [p for p in problems if "goes back" not in p]     # only order (monotone) problems can be repaired
    if order:
        return None, problems + ([f"{len(bad)} lines did not parse"] if bad else []), 1.0
    notes = [f"repaired: {p}" for p in first if p not in problems]
    fixed, asks, share = repair(segs, n_book)
    if share > MAX_OFFEND:
        return None, problems + [f"{share:.0%} of paragraphs out of order"], share
    why = shares(fixed, n_paras)                              # the repaired answer is what gets written
    if why:
        return None, problems + why, share
    return fixed, problems + notes[:3], share


def chain(segs):
    """Indexes of the longest forward chain of mapped segments (weight = paragraphs): each next c >= previous d."""
    mapped = [k for k, s in enumerate(segs) if s["b"]]
    best, prev = {}, {}
    for i, k in enumerate(mapped):
        w = segs[k]["p"][1] - segs[k]["p"][0] + 1
        best[k], prev[k] = w, None
        for j in mapped[:i]:
            if segs[j]["b"][1] <= segs[k]["b"][0] and best[j] + w > best[k]:
                best[k], prev[k] = best[j] + w, j
    if not best:
        return []
    k = max(best, key=best.get)
    out = []
    while k is not None:
        out.append(k)
        k = prev[k]
    return out[::-1]


def repair(segs, n_book):
    """(segments with offenders set to None and flagged, re-asks [{seg, lo, hi}], share of paragraphs offending).

    An offender is a mapped segment outside the longest forward chain; its re-ask bounds are the chain's
    neighbours: lo = the previous kept segment's d, hi = the next kept segment's c."""
    keep = set(chain(segs))
    total = sum(s["p"][1] - s["p"][0] + 1 for s in segs) or 1
    out, asks, bad = [], [], 0
    for k, s in enumerate(segs):
        if s["b"] and k not in keep:
            lo = max([segs[j]["b"][1] for j in keep if j < k] or [1])
            hi = min([segs[j]["b"][0] for j in keep if j > k] or [n_book])
            asks.append({"seg": k, "p": s["p"], "lo": lo, "hi": hi, "was": s["b"]})
            bad += s["p"][1] - s["p"][0] + 1
            out.append(dict(s, b=None, flag="reask"))
        else:
            out.append(dict(s))
    return out, asks, bad / total


def per_paragraph(segs, n_paras):
    """[book line (the middle of its segment's range) or None] per paragraph."""
    out = [None] * n_paras
    for s in segs:
        for p in range(s["p"][0], min(s["p"][1], n_paras) + 1):
            out[p - 1] = None if not s["b"] else (s["b"][0] + s["b"][1]) / 2
    return out


def agree(a, b, n_paras, within=AGREE_WITHIN):
    """Share of paragraphs where two readers agree: both NONE, or middles within `within` book lines."""
    pa, pb = per_paragraph(a, n_paras), per_paragraph(b, n_paras)
    same = sum((x is None and y is None) or (x is not None and y is not None and abs(x - y) <= within)
               for x, y in zip(pa, pb))
    return same / n_paras if n_paras else 1.0


def disputed(a, b, n_paras, within=AGREE_WITHIN):
    """Runs [p_from, p_to] of paragraphs where two readers disagree."""
    pa, pb = per_paragraph(a, n_paras), per_paragraph(b, n_paras)
    runs, start = [], None
    for i, (x, y) in enumerate(zip(pa, pb), 1):
        ok = (x is None and y is None) or (x is not None and y is not None and abs(x - y) <= within)
        if not ok and start is None:
            start = i
        if ok and start is not None:
            runs.append([start, i - 1])
            start = None
    if start is not None:
        runs.append([start, n_paras])
    return runs


def record(segs, paras, sents, edges, by, conf=None):
    """Rows of `lectures/<id>/segments.jsonl`: times from paragraph stamps, book sentence ids, and the handout
    sentences the book range reaches through the Phase 1 edges."""
    rows = []
    for n, s in enumerate(segs, 1):
        a, b = s["p"]
        start = paras[a - 1]["start"]
        end = paras[b]["start"] if b < len(paras) else None
        row = {"n": n, "p": [a, b], "start": start, "end": end, "by": by}
        if s["b"]:
            c, d = s["b"]
            book = [x["id"] for x in sents[c - 1:d]]
            row["book"] = [book[0], book[-1]]
            hand = []
            for bid in book:
                for h in edges.get(bid, ()):
                    if h not in hand:
                        hand.append(h)
            row["handout"] = hand
        else:
            row["book"] = None
        if s.get("flag"):
            row["flag"] = s["flag"]
        if conf is not None:
            row["conf"] = conf
        rows.append(row)
    return rows

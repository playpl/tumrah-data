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

LINE = re.compile(r"^\s*P(\d+)\s*-\s*P(\d+)\s*=\s*(?:B(\d+)\s*-\s*B(\d+)|(NONE))\s*$", re.I)
MAX_PARAS, MAX_RANGE = 12, 120
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


def parse(answer):
    """[{"p": [a, b], "b": [c, d] or None}] in answer order, and the lines that did not parse."""
    segs, bad = [], []
    for line in (answer or "").splitlines():
        line = line.strip().strip("`").strip()
        if not line:
            continue
        m = LINE.match(line)
        if not m:
            bad.append(line)
            continue
        a, b, c, d, none = m.groups()
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

"""Phase 2 reader task and its answer: which lines of the doctor's book each transcript paragraph explains.

Rebuilt 2026-11-18 (owner: the earlier flow was over-engineered, and an AI cannot keep to a length rule). The reader
answers per paragraph; a run of paragraphs with the same answer may share one line:

    P12 = B40            P12 = B40-B42            P12-P15 = B40-B42            P16 = NONE

There is no segment length rule and no forward-only rule: a doctor who goes back gets the earlier lines. Readers
also name several places for one paragraph (`P6-P7 = B25, B34`); that is kept as a list of ranges. Code turns
the answer into a list of book ranges (or None) per paragraph (`parse`), checks it is a whole answer (`problems`),
compares two readers paragraph by paragraph (`same`), and merges runs of paragraphs into segments (`segments`).
"""
import re

VERSION = 4          # 4 (2026-11-18): per-paragraph answers, no length or order rule
NONE_MAX = 0.5       # a reader that calls more than half the lecture NONE did not read it
MISSING_MAX = 0.05   # paragraphs a reader may leave out (read as NONE)
NEAR = 5             # two ranges that do not overlap still agree when their middles are this close (book lines)

PROMPT = """You link a recorded medical lecture to the doctor's own book.

BOOK lines are numbered B1, B2, ... in book order. Lines that start with ## are headings.
TRANSCRIPT paragraphs are numbered P1, P2, ... in time order (about 30 seconds each); each starts with its time
stamp. The doctor speaks Egyptian Arabic and says the English terms in Arabic letters (for example "سبينال كورد" =
spinal cord).

For every paragraph, write which BOOK lines the doctor is explaining in it.
- Go by meaning, not only by the English words: his Arabic explanation of a fact belongs to that fact's line.
- Give the line, or the few lines, he is on: P12 = B40, or P12 = B40-B42.
- Paragraphs in a row with the same answer may share one line: P12-P15 = B40-B42.
- If he goes back to earlier lines (a recap, a student's question), give those earlier lines.
- NONE only for a paragraph that explains no book line: greetings, jokes, exam advice, or something the book does
  not have.
- Every paragraph from P1 to P{last} gets exactly one answer.

Answer with these lines only, nothing else:
P<a> = B<c>-B<d>
P<a>-P<b> = B<c>-B<d>
P<a> = NONE
"""

_RNG = r"B\d+(?:\s*-\s*B?\d+)?"
LINE = re.compile(r"^P(\d+)(?:\s*-\s*P?(\d+))?\s*=\s*(?:(" + _RNG + r"(?:\s*,\s*" + _RNG + r")*)|(NONE))$", re.I)
ONE = re.compile(r"B(\d+)(?:\s*-\s*B?(\d+))?", re.I)
# Formatting only, never meaning: zero-width and no-break spaces, typographic dashes, Arabic-Indic digits, ":" or an
# arrow for "=", markdown marks, a bullet or number in front, a final period.
_FOLD = {**{c: None for c in (0xFEFF, 0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060)}, 0xA0: " ",
         **{c: "-" for c in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2212)},
         **{c: "=" for c in (0x3A, 0x2192)}, 0x60C: ",",
         **{0x660 + i: str(i) for i in range(10)}, **{0x6F0 + i: str(i) for i in range(10)}}
_WRAP = re.compile(r"^(?:[-*•]+\s*|\d{1,3}[.)]\s+)")


def render(paras, sents):
    """The task text: prompt, BOOK block, TRANSCRIPT block. `sents` is the slice (B1 = sents[0])."""
    from spine.seg.prior import stamp
    book = [f"B{i} " + ("## " if s.get("kind") == "heading" else "") + " ".join((s.get("text") or "").split())
            for i, s in enumerate(sents, 1)]
    talk = [f"P{p['n']} [{stamp(p['start'])}] {' '.join(p['text'].split())}" for p in paras]
    return (PROMPT.replace("{last}", str(len(paras))) + "\nBOOK\n" + "\n".join(book)
            + "\n\nTRANSCRIPT\n" + "\n".join(talk) + "\n")


def norm(line):
    line = (line or "").translate(_FOLD).strip()
    for _ in range(4):
        before = line
        line = _WRAP.sub("", line.strip("`*_ \t")).rstrip(".;, ").strip()
        if line == before:
            break
    return line


def parse(answer, n_paras, n_book):
    """(per, notes): per = [list of book ranges [[c, d], ...] or None] for P1..Pn (a paragraph answered twice keeps its first
    answer); notes = counts of what was wrong: missing paragraphs, B outside the slice, paragraphs outside the
    transcript, paragraphs answered twice."""
    per = [False] * n_paras                       # False = not answered yet
    notes = {"missing": 0, "outside_book": 0, "outside_talk": 0, "twice": 0, "lines": 0}
    for raw in (answer or "").splitlines():
        m = LINE.match(norm(raw))
        if not m:
            continue
        notes["lines"] += 1
        a, b, books, none = m.groups()
        a, b = int(a), int(b or a)
        rng = None
        if not none:
            rng = []
            for c, d in ONE.findall(books):
                c, d = int(c), int(d or c)
                c, d = min(c, d), max(c, d)
                if not (1 <= c and d <= n_book):
                    notes["outside_book"] += 1
                    c, d = max(1, c), min(n_book, d)
                if c <= d and [c, d] not in rng:
                    rng.append([c, d])
            rng = sorted(rng) or None
        for p in range(min(a, b), max(a, b) + 1):
            if not 1 <= p <= n_paras:
                notes["outside_talk"] += 1
            elif per[p - 1] is False:
                per[p - 1] = rng
            else:
                notes["twice"] += 1
    notes["missing"] = sum(x is False for x in per)
    return [None if x is False else x for x in per], notes


def problems(per, notes):
    """Why an answer is not usable (empty list = usable)."""
    n = len(per) or 1
    out = []
    if not notes["lines"]:
        out.append("no answer line")
    if notes["missing"] / n > MISSING_MAX:
        out.append(f"{notes['missing']} of {len(per)} paragraphs not answered")
    if sum(x is None for x in per) / n > NONE_MAX:
        out.append(f"NONE for {sum(x is None for x in per) / n:.0%} of paragraphs")
    if notes["outside_book"]:
        out.append(f"{notes['outside_book']} answers outside the BOOK lines")
    return out


def same(x, y, near=NEAR):
    """Two readers' answers for one paragraph agree: both NONE, or a range of one overlaps a range of the other or
    their middles are within `near` book lines."""
    if x is None or y is None:
        return x is None and y is None
    return any(p[0] <= q[1] and q[0] <= p[1] or abs((p[0] + p[1]) - (q[0] + q[1])) / 2 <= near for p in x for q in y)


def agreed(a, b):
    """(per paragraph: A's answer where the readers agree, else "disputed"; share agreed)."""
    out = [x if same(x, y) else "disputed" for x, y in zip(a, b)]
    return out, (sum(v != "disputed" for v in out) / len(out) if out else 1.0)


def segments(per):
    """Runs of paragraphs with the same answer: [{"p": [a, b], "b": [[c, d], ...] or None, "flag"?}]."""
    out = []
    for i, x in enumerate(per, 1):
        if out and out[-1]["_x"] == x:
            out[-1]["p"][1] = i
            continue
        out.append({"p": [i, i], "_x": x})
    for s in out:
        x = s.pop("_x")
        s["b"] = None if x in (None, "disputed") else x
        if x == "disputed":
            s["flag"] = "disputed"
    return out


def record(segs, paras, sents, edges, by, conf=None):
    """Rows of `lectures/<id>/segments.jsonl`: times from paragraph stamps, book sentence ids ("book" = first to last
    named line; "parts" = each named range when there are several), and the handout sentences the named lines reach
    through the Phase 1 edges."""
    rows = []
    for n, s in enumerate(segs, 1):
        a, b = s["p"]
        row = {"n": n, "p": [a, b], "start": paras[a - 1]["start"],
               "end": paras[b]["start"] if b < len(paras) else None, "by": by}
        if s["b"]:
            parts = [[x["id"] for x in sents[c - 1:d]] for c, d in s["b"]]
            row["book"] = [parts[0][0], parts[-1][-1]]          # first to last named line
            if len(parts) > 1:                                  # several places: only these lines, not the gap
                row["parts"] = [[p[0], p[-1]] for p in parts]
            row["handout"] = list(dict.fromkeys(h for p in parts for bid in p for h in edges.get(bid, ())))
        else:
            row["book"] = None
        if s.get("flag"):
            row["flag"] = s["flag"]
        if conf is not None:
            row["conf"] = conf
        rows.append(row)
    return rows

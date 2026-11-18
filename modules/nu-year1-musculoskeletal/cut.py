"""ZNU year 1 musculoskeletal: the sentence cut follows the book's lesson starts (owner, 2026-11-18).

Why: reference.json (the Tumrah book's lesson cuts) gives each lesson whole pages, and two neighbouring lessons share
their boundary page. outline.py cut the sections by page only, so every shared page went to both lessons: 38 overlaps,
13 to 40 sentences each. Here lesson k runs from its `start` line up to the line before lesson k+1's `start` line.
The heading rules (what a section starts at) are still outline.py's, so only the cut changes.

    py -X utf8 cut.py build                 write outline.json (the old one is kept in old/), then check it
    py -X utf8 cut.py check [outline.json]  the invariants; exit 0 only when all of them hold

Run from this folder or from the tumrah-data root. Nothing outside modules/nu-year1-musculoskeletal/ is written. (Copied from year1-musculoskeletal 2026-11-18; the
lesson starts come from the handout's own index, reference.json.)
"""
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))   # tumrah-data root: outline.py and its heading rules
import outline  # noqa: E402

MODULE = "nu-year1-musculoskeletal"
LINES = HERE / "lines.jsonl"
OUTLINE = HERE / "outline.json"
OLD = HERE / "old" / "outline_pages_only_2026-11-18.json"


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def read_lines(path=LINES):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def anchors(lines, lectures):
    """Line index where each lecture starts: the first line on its first page that reads as its `start`.
    Searched after the previous lecture's start, so the starts come out in book order."""
    found, prev = [], -1
    for lec in lectures:
        a = lec["pdf_pages"][0]
        want = norm(lec["start"])
        at = next((i for i in range(prev + 1, len(lines))
                   if lines[i]["page"] == a and norm(lines[i]["text"]) == want), None)
        if at is None:
            raise ValueError(f"{lec['lecture_id']}: no line {lec['start']!r} after line {prev} on page {a}")
        found.append(at)
        prev = at
    return found


def spans(lines, lectures):
    """[(first, last)] line index per lecture, consecutive, no gap. The first lecture also takes the lines of its
    first page that come before its start (the lesson's own lead-in); lines outside all lectures are returned
    separately with a reason."""
    starts = anchors(lines, lectures)
    first_page = lectures[0]["pdf_pages"][0]
    last_page = lectures[-1]["pdf_pages"][1]
    lo = min(i for i, ln in enumerate(lines) if ln["page"] == first_page)
    hi = max(i for i, ln in enumerate(lines) if ln["page"] <= last_page)
    bounds = [lo] + starts[1:]
    out = []
    for k, begin in enumerate(bounds):
        end = bounds[k + 1] - 1 if k + 1 < len(bounds) else hi
        out.append((begin, end))
    unassigned = {}
    for i in range(len(lines)):
        if i < lo:
            unassigned[i] = "front matter: the book's cover, objectives and contents, before the first lesson's pages"
        elif i > hi:
            unassigned[i] = "after the last lesson's pages"
    return out, starts, unassigned


def sections(lines, lectures, span_list):
    """Sections in book order, the same rules as outline.build, but only inside each lecture's own span."""
    left = {}
    for ln in lines:
        if ln.get("text"):
            left[ln["page"]] = min(left.get(ln["page"], 1e9), ln["bbox"][0])
    out = []
    for lec, (lo, hi) in zip(lectures, span_list):
        cur = None
        count = 0
        for i in range(lo, hi + 1):
            ln = lines[i]
            if cur is None or (outline.is_heading(ln, left.get(ln["page"], 0))
                               and i - cur["i0"] >= outline.MIN_SECTION_LINES):
                count += 1
                cur = {"id": f"{lec['lecture_id']}/s{count}", "lecture": lec["lecture_id"],
                       "subject": (lec.get("subject") or "").lower(),
                       "title": (ln.get("text") or lec["title"]).strip()[:80],
                       "from": ln["id"], "page": ln["page"], "i0": i}
                out.append(cur)
            cur["to"], cur["i1"] = ln["id"], i
    return out


def build():
    lines, lectures = read_lines(), outline.reference(MODULE)
    span_list, _, _ = spans(lines, lectures)
    secs = sections(lines, lectures, span_list)
    text = json.dumps(secs, ensure_ascii=False)
    if OUTLINE.exists() and not OLD.exists():
        OLD.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OUTLINE, OLD)          # nothing is deleted: the page-only outline is kept
    tmp = OUTLINE.with_name(OUTLINE.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(OUTLINE)
    print(f"wrote {OUTLINE.name}: {len(secs)} sentences; old kept at {OLD.relative_to(HERE)}")
    return check(OUTLINE)


def check(path=OUTLINE):
    """Print every invariant. Returns 0 when all hold, 1 otherwise."""
    lines, lectures = read_lines(), outline.reference(MODULE)
    secs = json.loads(Path(path).read_text(encoding="utf-8"))
    span_list, starts, unassigned = spans(lines, lectures)
    results = []

    def add(name, bad, detail=""):
        results.append((name, not bad, detail))

    # who covers each line
    cover = [0] * len(lines)
    for s in secs:
        for i in range(s["i0"], s["i1"] + 1):
            cover[i] += 1
    twice = [i for i, c in enumerate(cover) if c > 1]
    none = [i for i, c in enumerate(cover) if c == 0]
    add("no line belongs to two sentences", twice, f"{len(twice)} lines, first {twice[:5]}")
    add("i0 is monotone across the whole outline",
        [j for j in range(1, len(secs)) if secs[j]["i0"] <= secs[j - 1]["i0"]],
        f"{sum(1 for j in range(1, len(secs)) if secs[j]['i0'] <= secs[j - 1]['i0'])} breaks")
    add("sentence ids are unique", len({s["id"] for s in secs}) != len(secs), "")
    gaps = []
    for p, q in zip(secs, secs[1:]):
        if p["lecture"] == q["lecture"] and q["i0"] != p["i1"] + 1:
            gaps.append(p["id"])
    add("sentences inside a lecture are contiguous", gaps, f"{len(gaps)} gaps/overlaps, first {gaps[:3]}")

    by_lec = {}
    for s in secs:
        by_lec.setdefault(s["lecture"], []).append(s)
    lec_bad, page_bad, anchor_bad, empty = [], [], [], []
    for k, lec in enumerate(lectures):
        lid = lec["lecture_id"]
        mine = by_lec.get(lid, [])
        lo, hi = span_list[k]
        if not mine:
            empty.append(lid)
            continue
        if mine[0]["i0"] != lo or mine[-1]["i1"] != hi:
            lec_bad.append(lid)
        a, b = lec["pdf_pages"]
        if not (lines[lo]["page"] == a and lines[hi]["page"] == b
                and all(a <= lines[i]["page"] <= b for i in range(lo, hi + 1))):
            page_bad.append(lid)
        if k > 0 and (norm(lines[starts[k]]["text"]) != norm(lec["start"]) or lo != starts[k]):
            anchor_bad.append(lid)
    add("every lecture has sentences", empty, f"{len(empty)} empty")
    add("each lecture's sentences fill its span exactly", lec_bad, f"{lec_bad[:3]}")
    add("each lecture's span lines up with its pdf_pages", page_bad, f"{page_bad[:3]}")
    add("each lecture (after the first) starts on its book start line", anchor_bad, f"{anchor_bad[:3]}")
    spans_ok = all(span_list[k + 1][0] == span_list[k][1] + 1 for k in range(len(span_list) - 1))
    add("lecture spans follow each other with no gap", not spans_ok, "")

    # every line: assigned once, or unassigned with a reason
    reasons_missing = [i for i in none if i not in unassigned]
    add("every line is assigned once or unassigned with a reason", twice or reasons_missing,
        f"{len(none)} unassigned, {len(reasons_missing)} without reason")

    # the sentences must not cross a lecture boundary: rows of a lecture stay inside its span
    lec_of = {}
    for k, (lo, hi) in enumerate(span_list):
        for i in range(lo, hi + 1):
            lec_of[i] = lectures[k]["lecture_id"]
    cross = [s["id"] for s in secs if any(lec_of.get(i) != s["lecture"] for i in range(s["i0"], s["i1"] + 1))]
    add("no sentence crosses a lecture boundary", cross, f"{len(cross)} crossing, first {cross[:3]}")

    boundaries = len(lectures) - 1
    overlap_boundaries = [k for k in range(boundaries)
                          if max((s["i1"] for s in by_lec.get(lectures[k]["lecture_id"], [])), default=-1)
                          >= span_list[k + 1][0]]
    add(f"lecture boundaries with an overlap ({boundaries} boundaries)", overlap_boundaries,
        f"{len(overlap_boundaries)} overlapping")

    for name, ok, detail in results:
        print(("ok    " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail and not ok else ""))
    print(f"lines {len(lines)}: assigned once {sum(1 for c in cover if c == 1)}, "
          f"unassigned {len(none)} ({len(unassigned)} by reason), in two sentences {len(twice)}")
    print(f"sentences {len(secs)}, lectures {len(lectures)}, boundaries checked {boundaries}, "
          f"overlapping boundaries {len(overlap_boundaries)}")
    print("check:", "passes" if all(ok for _, ok, _ in results) else "FAILS")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "build":
        sys.exit(build())
    if cmd == "check":
        sys.exit(check(Path(sys.argv[2]) if len(sys.argv) > 2 else OUTLINE))
    print(__doc__)
    sys.exit(2)

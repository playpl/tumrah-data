"""Lesson placement, checked (owner, 2026-11-10: one wrong lesson range spreads to every question in it).

Every other link is judged against a lesson's place in the handout, so this is the one link the owner confirms. Code
does the looking first, per lesson:
  current   lecture.json ranges (whoever placed it)
  reading   what a reader of the recording says the doctor covers, as outline sections: the web `bounds` reading
            (gemini_run.py bounds, ledger row lesson/web) or, without it, the sections the lecture links point at
  gates     off-subject pages, pages shared with another lesson of the same doctor, a coarse or very wide range
A lesson whose reading matches its current place and passes the gates is "agree": the owner accepts those in one click.
The rest get one card each with the reading as the suggestion. A lesson with no reading yet waits for one.
An accepted place is cut at section starts (ranges marked `cut`), so two lessons no longer share a whole page.

    py placement.py [module]     the verdicts, counts and ids only (changes nothing)
"""
import bisect
import json
import sys
from collections import Counter

import ledger
import lectures
import outline
from flows.common import read_jsonl

MIN_LINKED = 3      # linked lines that make a section "covered" by the recording
BRIDGE = 2          # uncovered sections between two covered ones that still belong to the lesson
AGREE_COVER = 0.8   # share of the current lines the reading must also hold
AGREE_EXTRA = 0.1   # share of the reading that may lie outside the current place
MAX_PAGES = 25
HARD = ("coarse", "off-subject pages", "overlaps", "very wide")


def _runs(covered):
    """Sorted section numbers -> [(first, last)] runs, bridging gaps of up to BRIDGE sections."""
    out = []
    for n in sorted(covered):
        if out and n - out[-1][1] <= BRIDGE + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return [tuple(r) for r in out]


def look(module):
    """One verdict per lecture (kind lecture): {id, title, doctor, subject, by, pages, flags, verdict, reader, cover,
    spans [(i0, i1)], suggest_pages, from_title, to_title}. verdict: owner | agree | differs | waits."""
    lines = read_jsonl(ledger.ROOT / "modules" / module / "lines.jsonl")
    ids = [ln["id"] for ln in lines]
    idx, page_of = {i: n for n, i in enumerate(ids)}, [ln["page"] for ln in lines]
    secs = outline.load(module)
    starts = [s["i0"] for s in secs]
    sec_of = lambda i: bisect.bisect_right(starts, i) - 1  # noqa: E731
    subject_of = {}
    for s in secs:
        for i in range(s["i0"], s["i1"] + 1):
            subject_of[page_of[i]] = s["subject"]
    metas = [m for m in lectures.all_lectures(module) if m.get("kind", "lecture") == "lecture"]
    pid = {i: page_of[n] for i, n in idx.items()}
    cur = {m["id"]: {idx[i] for i in ledger.range_ids(m.get("ranges"), idx, ids, pid)} for m in metas}
    db = ledger.connect()
    web = {r["src"]: json.loads(r["lines"]) for r in db.execute(
        "SELECT src, lines FROM links WHERE module=? AND kind='lesson' AND runner='web' AND found=1", (module,))}
    db.close()
    out = []
    for m in metas:
        a = cur[m["id"]]
        pages = sorted({page_of[i] for i in a})
        sub = (m.get("subject") or "").lower()
        flags = []
        if m.get("placed_by") == "claude-coarse":
            flags.append("coarse")
        off = [p for p in pages if subject_of.get(p) and subject_of[p] != sub]
        if off:
            flags.append("off-subject pages")
        shared = Counter()
        for o in metas:
            if o["id"] != m["id"] and o.get("doctor") == m.get("doctor"):
                n = len({page_of[i] for i in a & cur[o["id"]]})
                if n:
                    shared[o["id"]] = n
        if any(n > 1 for n in shared.values()):
            flags.append("overlaps")
        elif shared:
            flags.append("shares a page")
        if len(pages) > MAX_PAGES or len(m.get("ranges") or []) > 3:
            flags.append("very wide")
        # the reading: web bounds first, else the sections the lecture links cover
        spans, reader = [], None
        if m["id"] in web:
            spans = [(idx[f], idx[t]) for f, t in web[m["id"]] if f in idx and t in idx]
            reader = "web reading of the recording"
        else:
            f = lectures.folder(m["id"]) / "links.jsonl"
            hit = Counter(sec_of(idx[i]) for r in (read_jsonl(f) if f.exists() else []) for i in r.get("line_ids") or [] if i in idx)
            covered = [n for n, c in hit.items() if c >= MIN_LINKED]
            if covered:
                spans = [(secs[x]["i0"], secs[y]["i1"]) for x, y in _runs(covered)]
                reader = "lecture links"
        e = {i for x, y in spans for i in range(x, y + 1)}
        cover = len(a & e) / len(a) if a and e else 0.0
        extra = len(e - a) / len(e) if e else 0.0
        if m.get("placed_by") == "owner":
            verdict = "owner"
        elif not e:
            verdict = "waits"
        elif cover >= AGREE_COVER and extra <= AGREE_EXTRA and not any(f in HARD for f in flags):
            verdict = "agree"
            # keep the current ends, except on a page shared with the doctor's next or previous lesson: cut there
            first_shared = any(page_of[min(a)] in {page_of[i] for i in cur[o]} for o in shared)
            last_shared = any(page_of[max(a)] in {page_of[i] for i in cur[o]} for o in shared)
            lo = min(e) if first_shared else min(a)  # min(e) is a section start
            hi = max(e) if last_shared else max(a)
            spans = [(lo, hi)]
        else:
            verdict = "differs"
            if cover < AGREE_COVER:
                flags.append(f"the recording covers {round(100 * cover)}% of it")
            if extra > AGREE_EXTRA:
                flags.append(f"{round(100 * extra)}% of the recording lies outside it")
        out.append({"id": m["id"], "title": m["title"], "doctor": m.get("doctor"), "subject": sub, "by": m.get("placed_by"),
                    "pages": lectures.page_ranges(m), "flags": flags, "verdict": verdict, "reader": reader,
                    "cover": round(cover, 2), "spans": spans,
                    "suggest_pages": [[page_of[x], page_of[y]] for x, y in spans],
                    "from_title": secs[sec_of(spans[0][0])]["title"] if spans else None,
                    "to_title": secs[sec_of(spans[-1][1])]["title"] if spans else None,
                    "has_recording": (lectures.folder(m["id"]) / "raw.txt").exists()})
    return out


def apply(lecture_id, spans, by="owner"):
    """Sets a lesson's place to these (first line index, last line index) spans, cut exactly there."""
    meta = lectures.load(lecture_id)
    if not spans:
        raise ValueError(f"{lecture_id}: no place to set")
    lines = read_jsonl(ledger.ROOT / "modules" / meta["module"] / "lines.jsonl")
    lectures.set_line_ranges(meta, lines, [tuple(s) for s in spans], by)
    return lectures.page_ranges(meta)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    rows = look(sys.argv[1] if len(sys.argv) > 1 else ledger.MODULE)
    print(json.dumps({"verdicts": Counter(r["verdict"] for r in rows),
                      "flags": Counter(f.split(" covers ")[0].split("% of")[0] if "%" in f else f for r in rows for f in r["flags"])}))
    for r in rows:
        print(r["id"], r["verdict"], "by", r["by"], "pages", r["pages"], "->", r["suggest_pages"], "cover", r["cover"], r["flags"])

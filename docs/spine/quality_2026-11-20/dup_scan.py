"""Repeated passages inside one transcript (a reader looping, or a piece heard twice). A 12-word run that occurs again
more than 60 words later is a repeat; consecutive repeats join into one passage. Short passages can be the doctor
saying it twice; passages of 40+ words are counted as transcript defects.

    py docs/spine/quality_2026-11-20/dup_scan.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
N, GAP, LONG = 12, 60, 40


def words(t):
    t = re.sub(r"\[\d+:\d+(?::\d+)?\]|\[cite[^\]]*\]", " ", t)
    t = re.sub(r"[ًٌٍَُِّْـ]", "", t).replace("أ", "ا").replace("إ", "ا").replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"[^\w\s]", " ", t.lower()).split()


def passages(w):
    """Lengths (words) of the repeated passages."""
    seen, runs = {}, []
    for i in range(len(w) - N + 1):
        k = tuple(w[i:i + N])
        j = seen.get(k)
        if j is not None and i - j > GAP:
            runs.append(i)
        else:
            seen.setdefault(k, i)
    out = []
    for i in runs:
        if out and i - out[-1][1] <= 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return [b - a + N for a, b in out]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    for f in sorted((ROOT / "lectures").glob("*/raw.txt")):
        m = json.loads((f.parent / "lecture.json").read_text(encoding="utf-8"))
        src = "youtube" if (m.get("source") or {}).get("transcript") == "youtube" else "heard"
        w = words(f.read_text(encoding="utf-8"))
        long = [n for n in passages(w) if n >= LONG]
        rows.append((sum(long) / max(1, len(w)), f.parent.name, src, long))
    rows.sort(reverse=True)
    for src in ("heard", "youtube"):
        r = [x for x in rows if x[2] == src]
        bad = [x for x in r if x[3]]
        print(f"{src}: {len(r)} transcripts; with a repeated passage of {LONG}+ words: {len(bad)}")
    for s, lid, src, long in rows:
        if long:
            print(f"  {lid} ({src}): {s:.1%} of its words; passages {long[:6]}")


if __name__ == "__main__":
    main()

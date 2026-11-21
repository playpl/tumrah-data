"""Remove Gemini web's "[cite: N]" tags from transcripts (quality report 2026-11-20, fix 2).

Cleans lectures/*/raw.txt, their pieces/cNN.txt and modules/*/records/*/raw.txt (+ pieces). The tags sit inside a
line, so paragraph numbers do not change: a segmentation job whose task.txt was built from the tagged transcript keeps
its answer (task.txt is cleaned and meta.json gets the new fingerprint) instead of being asked again.

    py strip_cite.py [--dry]
"""
import argparse
import json
import sys
from pathlib import Path

from gemini_run import CITE, strip_cite

ROOT = Path(__file__).resolve().parent


def transcript_files():
    for pat in ("lectures/*/raw.txt", "lectures/*/pieces/c[0-9][0-9].txt",
                "modules/*/records/*/raw.txt", "modules/*/records/*/pieces/c[0-9][0-9].txt"):
        yield from ROOT.glob(pat)


def clean_files(dry=False):
    n = 0
    for f in transcript_files():
        t = f.read_text(encoding="utf-8")
        if CITE.search(t):
            n += 1
            if not dry:
                f.write_text(strip_cite(t), encoding="utf-8")
    return n


def clean_seg_jobs(dry=False):
    """Seg jobs: clean task.txt and re-fingerprint, keeping answers. Only when the cleaned task is what make_jobs
    would write now (same text), so nothing stale is kept."""
    from spine.seg import flow, segment
    kept = 0
    for meta_f in flow.JOBS.glob("*/*/meta.json"):
        d = meta_f.parent
        task_f = d / "task.txt"
        if not task_f.exists():
            continue
        task = task_f.read_text(encoding="utf-8")
        if not CITE.search(task):
            continue
        meta = json.loads(meta_f.read_text(encoding="utf-8"))
        p = flow.prepare(meta["lecture"])
        if not p:
            continue
        new = segment.render(p["paras"], p["slice"])
        new = strip_cite(new)
        if new != strip_cite(task):
            print(f"  {meta['lecture']}/{d.name}: task differs beyond the tags; left for make_jobs")
            continue
        kept += 1
        if not dry:
            task_f.write_text(new, encoding="utf-8")
            meta["fp"] = flow.fingerprint(new, p["slice"])
            meta_f.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return kept


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    n = clean_files(a.dry)
    print(f"transcript files with cite tags: {n}" + (" (dry)" if a.dry else " cleaned"))
    k = clean_seg_jobs(a.dry)
    print(f"seg jobs re-fingerprinted (answers kept): {k}")


if __name__ == "__main__":
    main()

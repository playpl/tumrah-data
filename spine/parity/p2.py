"""py -m spine parity p2: every segmented lecture (lectures/<id>/segments.jsonl) against its old placement.

Per lecture: the share of the handout pages its segments reach (through the book's Phase 1 edges) that lie inside
the lecture's old `lecture.json` ranges. A lecture passes at >= 80% (the doctor strays a little; the old ranges were
cut to page level). Prints one line per lecture and the total.
"""
import contextlib
import io

from spine import ROOT
from spine.seg import flow

PASS = 0.8


def run(a):
    lids = a.lectures or sorted(p.parent.name for p in (ROOT / "lectures").glob("*/segments.jsonl"))
    ok = 0
    for lid in lids:
        with contextlib.redirect_stdout(io.StringIO()):
            share = flow.audit(lid, out=lambda *_: None)
        good = share is not None and share >= PASS
        ok += good
        print(f"{lid}: " + ("no segments" if share is None else f"{share:.0%} of reached handout pages inside the old "
                            f"placement {'PASS' if good else 'fail'}"))
    print(f"parity p2: {ok} of {len(lids)} lectures pass (>= {PASS:.0%})")
    return 0 if lids and ok == len(lids) else 1


def add(sub):
    p = sub.add_parser("p2", help="segments against the old lecture placement")
    p.add_argument("lectures", nargs="*")
    p.set_defaults(run=run)

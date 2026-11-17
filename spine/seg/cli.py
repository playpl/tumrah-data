"""py -m spine seg prior | jobs | run | collect | audit (Phase 2 segmentation, shadow)."""
from spine.seg import flow, prior


def _prior(a):
    p = flow.prepare(a.lecture, a.module)
    if not p:
        print(f"{a.lecture}: no transcript or no book")
        return 1
    sc, sl, pts = p["scope"], p["slice"], p["prior"]
    print(f"{a.lecture}: {len(p['paras'])} paragraphs; book {sc['book']} B{sc['lo']}-B{sc['hi']} ({sc['how']}), "
          f"pages {sl[0]['page']}-{sl[-1]['page']}; prior matched {sum(x is not None for x in pts)}")
    for i in range(0, len(pts), a.every):
        j = pts[i]
        print(f"  P{i + 1} [{prior.stamp(p['paras'][i]['start'])}] "
              + (f"B{j + 1} p{sl[j]['page']} {sl[j]['text'][:70]}" if j is not None else "NONE"))
    return 0


def _lids(a):
    return a.lectures or flow.lectures_with_books(a.module, handout=getattr(a, "handout", False))


def _jobs(a):
    n = flow.make_jobs(_lids(a), a.module)
    print(f"seg jobs: {n} job folders written")
    return 0


def _run(a):
    print(f"seg run: {flow.run(a.lectures or None, via=a.via, limit=a.limit)}")
    return 0


def _collect(a):
    print(f"seg collect: {flow.collect(a.lectures or None, a.module)}")
    return 0


def _dry(a):
    print(f"seg dry: {flow.dry(a.lectures or None, a.module)}")
    return 0


def _audit(a):
    flow.audit(a.lecture)
    return 0


def register(sub):
    p = sub.add_parser("seg", help="Phase 2: transcript -> doctor's book, strictly forward").add_subparsers(dest="seg_cmd")
    x = p.add_parser("prior", help="the zero-token prior and book slice of one lecture")
    x.add_argument("lecture")
    x.add_argument("--module", default="year2-cns")
    x.add_argument("--every", type=int, default=10)
    x.set_defaults(run=_prior)
    for name, fn, hlp in (("jobs", _jobs, "write job folders"), ("run", _run, "readers answer the job folders"),
                          ("collect", _collect, "judge answers, write segments.jsonl"),
                          ("dry", _dry, "what collect would decide, writing nothing")):
        x = p.add_parser(name, help=hlp)
        x.add_argument("lectures", nargs="*")
        x.add_argument("--module", default="year2-cns")
        if name == "jobs":
            x.add_argument("--handout", action="store_true",
                           help="also lectures whose doctor has no split book (read against the handout)")
        if name == "run":
            x.add_argument("--via", choices=["fleet", "browser"], default="fleet")
            x.add_argument("--limit", type=int)
        x.set_defaults(run=fn)
    x = p.add_parser("audit", help="one lecture's segments against its old placement")
    x.add_argument("lecture")
    x.set_defaults(run=_audit)

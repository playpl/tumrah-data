"""py -m spine p1 recall | grade-old | code | jobs | run | accept <module>"""
from spine.align import engine, old, recall


def _recall(a):
    text, ok = recall.report(recall.measure(a.module, a.book))
    print(text)
    return 0 if ok else 1


def _grade_old(a):
    graded = old.grade(a.module)
    print(old.report(graded))
    if not a.dry:
        old.write(a.module, graded)
        print(f"saved: modules/{a.module}/graph/work/old_grade.jsonl")
    return 0


def register(sub):
    p = sub.add_parser("p1", help="Phase 1: book sentences to handout sentences").add_subparsers(dest="p1_cmd")
    r = p.add_parser("recall", help="what code proves and whether the short lists hold the answer")
    r.add_argument("module")
    r.add_argument("--book")
    r.set_defaults(run=_recall)
    g = p.add_parser("grade-old", help="grade the old book links by code")
    g.add_argument("module")
    g.add_argument("--dry", action="store_true")
    g.set_defaults(run=_grade_old)
    c = p.add_parser("code", help="write the code and old-link votes (no LLM)")
    c.add_argument("module")
    c.set_defaults(run=lambda a: print(engine.report(engine.run_code(a.module), "votes written (code tiers, old links)")))
    j = p.add_parser("jobs", help="fleet job folders for what a reader has not read (nothing is run)")
    j.add_argument("module")
    j.add_argument("--reader", default="A", choices=["A", "B"])
    j.set_defaults(run=lambda a: print(f"{len(engine.make_jobs(a.module, a.reader))} job folders under jobs/sp_align/"))
    n = p.add_parser("run", help="run the waiting job folders on the fleet accounts, then collect the votes")
    n.add_argument("module")
    n.add_argument("--reader", default="A", choices=["A", "B"])
    n.add_argument("--limit", type=int)
    n.add_argument("--accounts", nargs="*")
    n.set_defaults(run=lambda a: print("fleet run:", dict(engine.run_jobs(a.module, a.reader, a.accounts, a.limit))))
    t = p.add_parser("accept", help="votes -> edges, with the order check")
    t.add_argument("module")
    t.set_defaults(run=lambda a: print(engine.report(engine.accept(a.module), "links after every reader so far")))
    try:
        from spine.align import pilot
        pilot.add(p)
    except ImportError:
        pass

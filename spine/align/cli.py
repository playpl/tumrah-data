"""py -m spine p1 recall | grade-old <module>"""
from spine.align import old, recall


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
    try:
        from spine.align import pilot
        pilot.add(p)
    except ImportError:
        pass

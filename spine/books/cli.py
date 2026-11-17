"""py -m spine books split | dedupe <module> [book]"""
from collections import Counter

from spine.books import split


def _split(a):
    aliases = split.dedupe(a.module)
    for book in ([a.book] if a.book else sorted(split.books(a.module))):
        if book in aliases:
            print(f"{book}: a copy of {aliases[book][0]} (page offset {aliases[book][1]}); not split on its own")
            continue
        sents = split.split(a.module, book)
        kinds = Counter(s["kind"] for s in sents)
        print(f"{book}: {max(s['page'] for s in sents)} pages -> {len(sents)} sentences ("
              + ", ".join(f"{k} {n}" for k, n in kinds.most_common()) + ")")
    return 0


def _dedupe(a):
    aliases = split.dedupe(a.module)
    for alias, (canonical, offset) in sorted(aliases.items()):
        print(f"{alias} = {canonical}, page offset {offset}")
    print(f"{len(aliases)} of {len(split.books(a.module))} books are copies")
    return 0


def register(sub):
    p = sub.add_parser("books", help="doctors' books as sentences").add_subparsers(dest="books_cmd")
    s = p.add_parser("split", help="book PDF -> sentences")
    s.add_argument("module")
    s.add_argument("book", nargs="?")
    s.set_defaults(run=_split)
    d = p.add_parser("dedupe", help="books that are page-for-page copies of a bigger one")
    d.add_argument("module")
    d.set_defaults(run=_dedupe)

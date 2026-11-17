"""py -m spine tree fetch | show <channel> <root message id>"""
from spine.linktree import crawl


def _fetch(a):
    tree = crawl.fetch(a.channel, a.root, a.account, a.depth, onward=not a.no_onward)
    print(crawl.summary(tree))
    print(f"saved: sources/tree/{a.channel}_{a.root}.json (links only; no file was downloaded)")
    return 0


def _show(a):
    tree = crawl.load(a.channel, a.root)
    if not tree:
        print(f"not fetched yet: py -m spine tree fetch {a.channel} {a.root}")
        return 1
    print(crawl.summary(tree))
    print(crawl.outline(tree))
    return 0


def register(sub):
    p = sub.add_parser("tree", help="quiz and file channels as a link tree").add_subparsers(dest="tree_cmd")
    f = p.add_parser("fetch", help="crawl the links from a root message (read only, no downloads)")
    f.add_argument("channel")
    f.add_argument("root", type=int)
    f.add_argument("--account", default="voter2")
    f.add_argument("--depth", type=int, default=8)
    f.add_argument("--no-onward", action="store_true", help="skip listing the posts after the root")
    f.set_defaults(run=_fetch)
    s = p.add_parser("show", help="the saved tree as an outline")
    s.add_argument("channel")
    s.add_argument("root", type=int)
    s.set_defaults(run=_show)

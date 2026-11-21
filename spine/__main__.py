"""py -m spine <command> ...

Every subpackage owns its commands in a `register(subparsers)` function; this file only lists them.
A handler is set with `parser.set_defaults(run=function)` and gets the parsed args.
"""
import argparse
import importlib
import sys

# module that holds register(subparsers) -> the commands it adds
COMMANDS = [
    "spine.store",          # store rebuild | status
    "spine.graph.cli",      # graph build | check | sample
    "spine.polls.cli",      # polls inventory
    "spine.linktree.cli",   # tree fetch | show
    "spine.tg.cli",         # mother render | job | validate | diff
    "spine.records.cli",    # records plan | watch
    "spine.books.cli",      # books split | dedupe
    "spine.align.cli",      # p1 recall | grade-old | windows | audit
    "spine.seg.cli",        # seg prior | audit
    "spine.site.cli",       # site export
    "spine.parity",         # parity mother | p1 | p2
    "spine.questions.grades",  # questions grades
]


def build_parser():
    parser = argparse.ArgumentParser(prog="py -m spine", description="The handout spine: graph, books, records.")
    sub = parser.add_subparsers(dest="command")
    for name in COMMANDS:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name and name.startswith(e.name):   # this part is not built yet
                continue
            raise
        mod.register(sub)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    run = getattr(args, "run", None)
    if run is None:
        parser.print_help()
        return 2
    return run(args) or 0


if __name__ == "__main__":
    sys.exit(main())

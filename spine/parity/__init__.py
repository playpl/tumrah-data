"""py -m spine parity <phase>: does the new engine reproduce what the old scripts (or the owner's hand) made?

A phase goes from shadow to primary only when its parity report passes. Each phase has its own file here with
`add(subparsers)`: mother.py, p1.py, p2.py.
"""
import importlib

PHASES = ["mother", "p1", "p2"]


def register(sub):
    p = sub.add_parser("parity", help="new engine against the old results").add_subparsers(dest="phase")
    for name in PHASES:
        try:
            importlib.import_module(f"spine.parity.{name}").add(p)
        except ModuleNotFoundError as e:
            if e.name != f"spine.parity.{name}":
                raise

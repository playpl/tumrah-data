"""py -m spine polls inventory"""
from spine import ROOT
from spine.polls import registry


def _inventory(a):
    text = registry.report(registry.inventory())
    print(text)
    if a.save:
        out = ROOT / "docs" / "spine" / "POLLS_INVENTORY.md"
        out.write_text("```\n" + text + "\n```\n", encoding="utf-8")
        print(f"\nsaved to {out.relative_to(ROOT)}")
    return 0


def register(sub):
    p = sub.add_parser("polls", help="polls channel registry and inventory").add_subparsers(dest="polls_cmd")
    i = p.add_parser("inventory", help="read-only counts, and what the two ordered changes would touch")
    i.add_argument("--save", action="store_true", help="also write docs/spine/POLLS_INVENTORY.md")
    i.set_defaults(run=_inventory)

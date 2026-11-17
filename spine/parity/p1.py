"""py -m spine parity p1: the spine's book links (through compat.aligned_blocks) against the old aligned blocks
(modules/<m>/site/alignment/out/aligned/<book>.jsonl, what the site shows today).

Per book, over the handout rows (line ids):
  old rows reached   share of the handout rows the old blocks linked that the new links also reach
  new rows reached   handout rows only the new links reach (the old flow missed them, or the new one is wrong)
  open               content sentences the new engine has not settled yet (`p1 audit` lists them)
A book passes when old rows reached >= 95% and open <= 2% of its content sentences. Writes the compat files
(shadow) as it goes.
"""
from spine import module_dir, read_jsonl
from spine import compat
from spine.align import engine

PASS_OLD, PASS_OPEN = 0.95, 0.02


def old_rows(module, book):
    f = module_dir(module) / "site" / "alignment" / "out" / "aligned" / f"{book}.jsonl"
    if not f.exists():
        return None
    out = set()
    for r in read_jsonl(f):
        for b in r.get("blocks", []):
            if b.get("match") in ("same", "partial", "reworded"):
                out |= set(b.get("line_ids") or [])
    return out


def check(module, book, handout=None):
    rows = compat.aligned_blocks(module, book, handout)
    from spine import write_jsonl
    write_jsonl(compat.path(module, book), rows)
    blocks = [b for r in rows[1:] for b in r["blocks"]]
    new = {l for b in blocks for l in b["line_ids"]}
    content = [b for b in blocks if b["match"] != "not_content"]
    opened = sum(b["match"] == "open" for b in content)
    old = old_rows(module, book)
    res = {"book": book, "content": len(content), "open": opened, "new_rows": len(new),
           "open_share": opened / len(content) if content else 0.0}
    if old:
        res.update(old_rows=len(old), old_reached=len(old & new) / len(old), only_new=len(new - old))
    res["pass"] = res["open_share"] <= PASS_OPEN and res.get("old_reached", 1.0) >= PASS_OLD
    return res


def run(a):
    handout = compat._handout(a.module)
    books = [a.book] if a.book else engine.canonical_books(a.module)[0]
    ok = 0
    for book in books:
        r = check(a.module, book, handout)
        ok += r["pass"]
        old = (f"old rows {r['old_rows']:,}, reached {r['old_reached']:.1%}, only new {r['only_new']:,}"
               if "old_rows" in r else "no old alignment")
        print(f"{book:<22} {'PASS' if r['pass'] else 'fail'}  content {r['content']:,}, open {r['open']:,} "
              f"({r['open_share']:.1%}); new rows {r['new_rows']:,}; {old}")
    print(f"parity p1: {ok} of {len(books)} books pass (old rows reached >= {PASS_OLD:.0%}, open <= {PASS_OPEN:.0%})")
    return 0 if ok == len(books) else 1


def add(sub):
    p = sub.add_parser("p1", help="book links against the old aligned blocks")
    p.add_argument("module", nargs="?", default="year2-cns")
    p.add_argument("--book")
    p.set_defaults(run=run)

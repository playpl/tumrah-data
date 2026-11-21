"""py -m spine graph build | check | sample <module>"""
import random
from collections import Counter

import outline
from spine import ROOT, graph_dir, module_dir, read_jsonl
from spine.graph import handout


def _line(name, ok, detail):
    return ("ok    " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail and not ok else "")


def _tree():
    try:
        from spine.graph import tree
        return tree
    except ImportError:
        return None


def _build(a):
    lines, sents = handout.build(a.module, dry=a.dry)
    text_rows = sum(1 for ln in lines if ln.get("figure") is None)
    kinds = Counter(s["kind"] for s in sents)
    joined = sum(1 for s in sents if len(s["rows"]) > 1 and s["kind"] == "fact")
    split = sum(1 for s in sents if s["id"][-1].isalpha())
    print(f"{a.module}: {len(lines)} rows ({text_rows} text) -> {len(sents)} sentences"
          + (" (dry run, nothing written)" if a.dry else ""))
    print("  by kind:", ", ".join(f"{k} {n}" for k, n in kinds.most_common()))
    print(f"  facts made of several rows: {joined}; sentences cut out of a shared row: {split}")
    print(f"  in a lesson: {sum(1 for s in sents if s['lesson'])}; front matter: {sum(1 for s in sents if not s['lesson'])}")
    if not a.dry and _tree():
        print("  tree:", _tree().build(a.module))
    return 0


def _check(a):
    results = handout.check(a.module) + (_tree().check(a.module) if _tree() else [])
    for r in results:
        print(_line(*r))
    bad = sum(1 for _, ok, _ in results if not ok)
    print("graph check:", "passes" if not bad else f"{bad} invariants fail")
    return 1 if bad else 0


def _sample(a):
    sents = read_jsonl(graph_dir(a.module) / "sentences.jsonl")
    rows = {ln["id"]: ln for ln in read_jsonl(module_dir(a.module) / "lines.jsonl")}
    subject = {l["lecture_id"]: l["subject"].lower() for l in outline.reference(a.module)}
    rng = random.Random(a.seed)
    pool = [s for s in sents if s["lesson"] and s["kind"] in ("fact", "table_row")
            and (not a.subject or subject[s["lesson"]] == a.subject)
            and (not a.joined or len(s["rows"]) > 1 or s["id"][-1].isalpha())]
    by_subject = {}
    for s in pool:
        by_subject.setdefault(subject[s["lesson"]], []).append(s)
    picked = []
    for name in sorted(by_subject):
        picked += rng.sample(by_subject[name], min(len(by_subject[name]), a.n // len(by_subject)))
    out = []
    for s in sorted(picked, key=lambda s: s["i"]):
        out.append(f"### {s['id']}  ({s['kind']}, {subject[s['lesson']]}, marker {s['marker'] or '-'})")
        out.append("ctx: " + " > ".join(s["ctx"]))
        out.append("TEXT: " + s["text"])
        for r in s["rows"]:
            out.append(f"   row {rows[r]['n']:>3} x0={rows[r]['bbox'][0]:5.0f} x1={rows[r]['bbox'][2]:5.0f} | {rows[r]['text']}")
        if s["i"] + 1 < len(sents):
            nxt = sents[s["i"] + 1]
            out.append(f"   next -> [{nxt['kind']}] {nxt['text'][:90]}")
        out.append("")
    text = "\n".join(out)
    (ROOT / "docs" / "spine" / "sample_sentences.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


def register(sub):
    p = sub.add_parser("graph", help="handout sentences and the tree").add_subparsers(dest="graph_cmd")
    b = p.add_parser("build", help="rows -> sentences.jsonl, graph.json")
    b.add_argument("module")
    b.add_argument("--dry", action="store_true")
    b.set_defaults(run=_build)
    c = p.add_parser("check", help="the invariants")
    c.add_argument("module")
    c.set_defaults(run=_check)
    s = p.add_parser("sample", help="sentences with their raw rows, to judge the joins")
    s.add_argument("module")
    s.add_argument("--n", type=int, default=100)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--subject")
    s.add_argument("--joined", action="store_true", help="only sentences made by a join or a split")
    s.set_defaults(run=_sample)
    from spine.graph import twin
    twin.add(p)

"""The fleet pilot: 20 real windows before any bulk run, to measure how the free readers do on the closed task.

    py -m spine p1 pilot make year2-cns [--n 20] [--per-job 5] [--seed 7]    job folders, nothing is run
    py -m spine p1 pilot check year2-cns                                    read the answers, print the numbers

`make` writes jobs/sp_align/pilot/job<k>/prompt.md and key.json. Each job is then run by hand on one fleet
account (the answer comes back as the reply; no tools, no files):
    py C:/Users/Ahmed/agy-fleet/fleet.py run -a <account> --cwd <job dir> -f prompt.md --out result.json
`check` grades each window: grammar, the hidden probe, and agreement with the old links where one exists.
"""
import random
from collections import Counter

from spine import ROOT, read_json, write_json
from spine.align import old, prefilter, recall, windows
from spine.books import split

HOME = ROOT / "jobs" / "sp_align" / "pilot"


def make(module, n=20, per_job=5, seed=7):
    H = prefilter.Handout(module)
    aliases, rows, old_books = split.dedupe(module), old.row_map(module), old.old_books(module)
    names = [b for b in split.books(module) if b not in aliases]
    pool = []
    for book in names:
        sents, items = recall.book_items(module, book, H)
        res = prefilter.code_tiers(items, H)
        gold = recall.gold_of(module, book, sents, H, names, aliases, old_books, rows)
        for w in prefilter.windows(len(items), res):
            if any(res[i] for i in w):                       # a window needs a known sentence for its probe
                pool.append((book, sents, items, res, gold, w))
    picked = random.Random(seed).sample(pool, min(n, len(pool)))
    jobs = []
    for k in range(0, len(picked), per_job):
        rendered, keys = [], []
        for j, (book, sents, items, res, gold, w) in enumerate(picked[k:k + per_job], start=1):
            cands = prefilter.candidates(items, res, w, H)
            text, key = windows.render(items, res, w, cands, H, label=f"W{j}")
            key.update(book=book, ids={str(b): sents[i]["id"] for b, i in key["b"].items()},
                       texts={str(b): items[i]["text"] for b, i in key["b"].items()},
                       gold={str(b): [sorted(gold[i][0]), gold[i][1]] for b, i in key["b"].items() if i in gold})
            rendered.append(text)
            keys.append(key)
        d = HOME / f"job{k // per_job + 1}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "prompt.md").write_text(windows.prompt(rendered), encoding="utf-8")
        write_json(d / "key.json", keys)
        (d / "result.json").unlink(missing_ok=True)
        jobs.append(d)
    return jobs


def check(module):
    H = prefilter.Handout(module)
    out = Counter()
    lines, usage = [], Counter()
    for d in sorted(HOME.glob("job*")):
        keys, result = read_json(d / "key.json"), read_json(d / "result.json")
        if not result or result.get("status") != "SUCCESS":
            out["jobs failed"] += 1
            lines.append(f"{d.name}: no answer ({(result or {}).get('status') or 'not run'})")
            continue
        out["jobs answered"] += 1
        for k, v in (result.get("usage") or {}).items():
            if isinstance(v, (int, float)):
                usage[k] += v
        for key in keys:
            items = {i: {"text": key["texts"][b]} for b, i in key["b"].items()}
            verdicts, errors = windows.parse(result.get("response") or "", key, H, items)
            out["windows"] += 1
            out["open lines"] += len(key["open"])
            out["probes"] += len(key["probe"])
            out["probes wrong"] += sum(1 for e in errors if e.startswith("probe"))
            out["windows clean"] += not errors
            if errors:
                lines.append(f"{d.name} {key['label']} ({key['book']}): " + "; ".join(errors[:3]))
            for b, i in key["b"].items():
                v = verdicts.get(i)
                if int(b) not in key["open"] or b in key["probe"] or v is None:
                    continue
                out["answers " + (v if isinstance(v, str) else v[2])] += 1
                if b in key["gold"]:
                    kind = key["gold"][b][1]
                    out[f"old link {kind}"] += 1
                    out[f"old link {kind} agrees"] += isinstance(v, tuple) and bool(set(v[1]) & set(key["gold"][b][0]))
    return out, lines, usage


def report(out, lines, usage):
    text = ["FLEET PILOT", f"  jobs answered {out['jobs answered']}, failed {out['jobs failed']}",
            f"  windows {out['windows']}: clean {out['windows clean']} (grammar, every line answered, probe right)",
            f"  probes {out['probes']}: wrong {out['probes wrong']}",
            f"  open lines {out['open lines']}: " + ", ".join(
                f"{k[8:]} {n}" for k, n in sorted(out.items()) if k.startswith("answers "))]
    for kind in ("same", "partial", "reworded"):
        if out[f"old link {kind}"]:
            text.append(f"  against the old link ({kind}): {out[f'old link {kind} agrees']} of {out[f'old link {kind}']} agree")
    if usage:
        text.append("  tokens: " + ", ".join(f"{k} {int(v):,}" for k, v in sorted(usage.items())))
    return "\n".join(text + ["  problems:"] + [f"    {l}" for l in lines] if lines else text)


def add(sub):
    p = sub.add_parser("pilot", help="20 fleet windows before any bulk run").add_subparsers(dest="pilot_cmd")
    m = p.add_parser("make", help="write the pilot job folders (nothing is run)")
    m.add_argument("module")
    m.add_argument("--n", type=int, default=20)
    m.add_argument("--per-job", type=int, default=5)
    m.add_argument("--seed", type=int, default=7)
    m.set_defaults(run=lambda a: print("\n".join(f"{d}  ({(d / 'prompt.md').stat().st_size:,} bytes)"
                                                  for d in make(a.module, a.n, a.per_job, a.seed))))
    c = p.add_parser("check", help="grade the answers")
    c.add_argument("module")
    c.set_defaults(run=lambda a: print(report(*check(a.module))))

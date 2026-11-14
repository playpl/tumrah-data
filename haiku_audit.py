"""Haiku audit of a reader's pointer answers (owner 2026-11-14: "get Haiku to test what they did, make sure there is no
conflicts; random questions, 50-question batches").

A random sample of one runner's answers (default fleet-A) goes into batches of 50. For each question the auditor sees the
question, the keyed option, and the lines the reader chose (with their page neighbours); for a "none" answer, the
script's best line in the same scope. The auditor judges; code counts. Audit verdicts are not the owner's gold rows.

    py haiku_audit.py build [--runner fleet-A] [--n 200] [--seed 1114]   -> jobs/audit/<runner>-<seed>/bNN/audit.txt
    py haiku_audit.py check <batch dir>                                    -> PASS or the errors
    py haiku_audit.py report [--runner fleet-A] [--seed 1114]              -> counts, error rate, every bad verdict
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULE = "year2-cns"
SIZE = 50
VERDICTS = {"correct", "partial", "wrong", "missed", "ok_none"}

TASK = """# Audit: do these handout lines teach the keyed answer?

Each item below is a multiple-choice question with its keyed option marked `*`, and what a reader chose:
- `CHOSE` = handout lines the reader says teach the keyed answer (each line: `ID text`; `ctx` lines are neighbours,
  shown only so you can read the chosen line in context; they were not chosen).
- `NONE` = the reader said no line teaches it; `CANDIDATE` is the best line a word-matching script found nearby.

Judge each item on the text alone (the key is given: never question it):
- `correct`: the chosen lines state what a student needs for the keyed option.
- `partial`: on topic, but the fact that makes the keyed option right is missing from the chosen lines.
- `wrong`: the chosen lines do not teach the keyed answer (other topic, only a shared word, a heading alone).
- for a NONE item: `missed` when the CANDIDATE line does teach the keyed answer, else `ok_none`.

Write `verdicts.jsonl` in this folder, one line per item, in item order:
{{"n": 1, "verdict": "correct", "why": "<12 words or fewer>"}}

Then run `python check.py` and fix what it prints until it prints PASS. {n} items.

"""


def read_jsonl(p):
    return [json.loads(x) for x in open(p, encoding="utf-8") if x.strip()]


def lines_by_id():
    rows = read_jsonl(ROOT / "modules" / MODULE / "lines.jsonl")
    by_id = {r["id"]: r for r in rows}
    by_page = {}
    for r in rows:
        by_page.setdefault(r["page"], []).append(r)
    return by_id, by_page


def text(ln):
    return ln.get("text") or (f"[FIGURE] {ln.get('figure') or ''}" if ln.get("figure") is not None else "")


def short(i):
    return i.split(":", 2)[2]


def questions(runner):
    """{word_key: (question row, scope ranges)} from the passed jobs of that reader's flow."""
    import queue_db
    q = queue_db.Queue()
    reader = runner.split("-")[-1]
    fleet = runner.startswith("fleet")
    out = {}
    for payload, account in q.db.execute("SELECT payload, account FROM jobs WHERE flow='pointers_one' AND status='passed'"):
        p = json.loads(payload)
        if p.get("reader") != reader or bool(account) != fleet:
            continue
        for b in p["batch"]:
            out[b["word_key"]] = (b, p["scope"]["ranges"])
    q.close()
    return out


def build(args):
    import ledger
    db = ledger.connect()
    mine = {r["src"]: r for r in db.execute("SELECT * FROM links WHERE module=? AND kind='question' AND runner=?",
                                            (MODULE, args.runner))}
    script = {r["src"]: json.loads(r["lines"] or "[]") for r in db.execute(
        "SELECT src, lines FROM links WHERE module=? AND kind='question' AND runner='script'", (MODULE,))}
    db.close()
    qs = questions(args.runner)
    pool = sorted(k for k in mine if k in qs)
    found = [k for k in pool if mine[k]["found"]]
    none = [k for k in pool if not mine[k]["found"] and script.get(k)]
    rnd = random.Random(args.seed)
    n_none = min(len(none), round(args.n * len(none) / max(1, len(none) + len(found))))
    pick = rnd.sample(found, min(len(found), args.n - n_none)) + rnd.sample(none, n_none)
    rnd.shuffle(pick)
    by_id, by_page = lines_by_id()
    base = ROOT / "jobs" / "audit" / f"{args.runner}-{args.seed}"
    for bi in range(0, len(pick), SIZE):
        d = base / f"b{bi // SIZE + 1:02d}"
        d.mkdir(parents=True, exist_ok=True)
        part = pick[bi:bi + SIZE]
        out, items = [TASK.format(n=len(part))], []
        for n, wk in enumerate(part, 1):
            b, _ = qs[wk]
            opts = json.loads(b["options"]) if isinstance(b["options"], str) else b["options"]
            key = int(b["correct_index"])
            out.append(f"## Item {n}\n{b['stem']}" + (f"\n{b['case_text']}" if b.get("case_text") not in (None, "None") else ""))
            out += [f"{'*' if j == key else ' '} {'ABCDE'[j]}. {o}" for j, o in enumerate(opts)]
            ids = json.loads(mine[wk]["lines"] or "[]")
            if ids:
                out.append("CHOSE:")
                shown = set()
                for i in ids:
                    ln = by_id.get(i)
                    if not ln:
                        continue
                    page = by_page[ln["page"]]
                    k = page.index(ln)
                    for c in page[max(0, k - 1):k + 2]:
                        if c["id"] in shown:
                            continue
                        shown.add(c["id"])
                        out.append(f"  {'>>' if c['id'] in ids else 'ctx'} {short(c['id'])} {text(c)}")
            else:
                out.append(f"NONE ({mine[wk]['reason'] or 'not found'})")
                for i in script.get(wk, [])[:2]:
                    if i in by_id:
                        out.append(f"  CANDIDATE {short(i)} {text(by_id[i])}")
            out.append("")
            items.append({"n": n, "word_key": wk, "found": bool(ids)})
        (d / "audit.txt").write_text("\n".join(out), encoding="utf-8")
        (d / "items.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        (d / "check.py").write_text(
            "import subprocess, sys\n"
            f"sys.exit(subprocess.run([{sys.executable!r}, {str(ROOT / 'haiku_audit.py')!r}, 'check', "
            f"{str(d)!r}]).returncode)\n", encoding="utf-8")
    print(f"{args.runner}: pool {len(pool)} ({len(found)} found, {len(none)} none with a candidate); sampled {len(pick)} "
          f"({len(pick) - n_none} found, {n_none} none) in {-(-len(pick) // SIZE)} batches under {base}")


def check_dir(d):
    d = Path(d)
    items = json.loads((d / "items.json").read_text(encoding="utf-8"))
    f = d / "verdicts.jsonl"
    if not f.exists():
        return ["verdicts.jsonl is missing"]
    errors, seen = [], set()
    for k, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            n = int(r["n"])
        except (ValueError, KeyError, TypeError):
            errors.append(f"line {k}: not a JSON object with n")
            continue
        if not 1 <= n <= len(items):
            errors.append(f"line {k}: n {n} is not an item")
            continue
        allowed = {"correct", "partial", "wrong"} if items[n - 1]["found"] else {"missed", "ok_none"}
        if r.get("verdict") not in allowed:
            errors.append(f"item {n}: verdict must be one of {sorted(allowed)}")
        if n in seen:
            errors.append(f"item {n}: judged twice")
        seen.add(n)
    missing = [i["n"] for i in items if i["n"] not in seen]
    if missing:
        errors.append(f"items not judged: {missing[:20]}")
    return errors


def report(args):
    base = ROOT / "jobs" / "audit" / f"{args.runner}-{args.seed}"
    c, bad = Counter(), []
    for d in sorted(base.glob("b*")):
        if check_dir(d):
            print(d.name, "not complete")
            continue
        items = json.loads((d / "items.json").read_text(encoding="utf-8"))
        for r in read_jsonl(d / "verdicts.jsonl"):
            it = items[int(r["n"]) - 1]
            c[r["verdict"]] += 1
            if r["verdict"] in ("wrong", "partial", "missed"):
                bad.append((d.name, r["n"], r["verdict"], it["word_key"][:60], r.get("why", "")))
    found = c["correct"] + c["partial"] + c["wrong"]
    none = c["missed"] + c["ok_none"]
    print(dict(c))
    if found:
        print(f"found answers: {found}; wrong {c['wrong']} ({100 * c['wrong'] / found:.1f}%), partial {c['partial']} "
              f"({100 * c['partial'] / found:.1f}%)")
    if none:
        print(f"none answers: {none}; missed {c['missed']} ({100 * c['missed'] / none:.1f}%)")
    for b in bad:
        print(*b, sep=" | ")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("--runner", default="fleet-A")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=1114)
    p = sub.add_parser("check")
    p.add_argument("dir")
    p = sub.add_parser("report")
    p.add_argument("--runner", default="fleet-A")
    p.add_argument("--seed", type=int, default=1114)
    a = ap.parse_args()
    if a.cmd == "build":
        build(a)
    elif a.cmd == "check":
        errs = check_dir(a.dir)
        print("\n".join(errs) if errs else "PASS")
        sys.exit(1 if errs else 0)
    else:
        report(a)

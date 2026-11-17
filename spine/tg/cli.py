"""py -m spine mother render | job | run | show | diff <list id ...>"""
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from spine import ROOT, read_json
from spine.tg import mother

FLEET = Path(r"C:\Users\Ahmed\agy-fleet\fleet.py")
ACCOUNT = {"A": ["zero", "work"], "B": ["personal", "other"]}       # two readers never share an account


def job_dir(lst, reader):
    return ROOT / "jobs" / "sp_mother" / f"{mother.ref(lst).replace('/', '-')}-{mother.cache_key(lst)}-{reader}"


def wanted(a):
    """The list references of a command: the ones typed, else the mother trees (--year 1 or 2 for one of them)."""
    return a.lists or mother.tree_lists(getattr(a, "year", None))


def make_job(lst, reader):
    d = job_dir(lst, reader)
    d.mkdir(parents=True, exist_ok=True)
    (d / "prompt.md").write_text(mother.PROMPT.format(rendered=mother.render(lst)), encoding="utf-8")
    return d


def read_one(arg):
    """Run one reader on one list (skipped when its answer is already there). Returns (list id, reader, answer or None, why)."""
    n, lst, reader = arg
    d = make_job(lst, reader)
    result = read_json(d / "result.json") or {}
    for attempt in range(2):
        if result.get("status") == "SUCCESS":
            break
        account = ACCOUNT[reader][(n + attempt) % 2]
        subprocess.run(["py", str(FLEET), "run", "-a", account, "--cwd", str(d), "-f", "prompt.md",
                        "--out", "result.json", "--timeout", "10"], capture_output=True, text=True, cwd=d)
        result = read_json(d / "result.json") or {}
    if result.get("status") != "SUCCESS":
        return mother.ref(lst), reader, None, f"no answer from the fleet ({result.get('failure') or result.get('status')})"
    return mother.ref(lst), reader, result.get("response") or "", ""


def settle(lst, answers):
    """(map or None, fixed link numbers, report line) from the two readers' answers {reader: text or None}.

    The map is usable when both readers answered, both maps pass `validate` after the hand fixes, and they agree."""
    maps, errors, fixed = {}, {}, []
    for r, text in answers.items():
        if text is None:
            maps[r], errors[r] = None, ["no answer"]
            continue
        m, e = mother.parse(text, lst)
        fixed = mother.apply_fixes(m, lst)
        maps[r], errors[r] = m, [x for x in e if x.startswith("not a valid line")] + mother.validate(m, lst)
    (ra, rb) = sorted(answers)
    differ = mother.agree(maps[ra], maps[rb]) if maps[ra] is not None and maps[rb] is not None else []
    if not errors[ra] and not errors[rb] and not differ:
        note = f" ({len(fixed)} by a hand fix)" if fixed else ""
        return maps[ra], fixed, f"two readers agree on all {len(maps[ra])} links{note}"
    return None, fixed, (f"reader {ra}: {errors[ra][:3] or 'valid'}; reader {rb}: {errors[rb][:3] or 'valid'}; "
                         f"they differ on links {differ}")


def _render(a):
    for i in a.lists:
        print(mother.render(mother.load(i)), "\n")
    return 0


def _job(a):
    for i in a.lists:
        print(make_job(mother.load(i), a.reader))
    return 0


def _run(a):
    lists = [mother.load(i) for i in wanted(a)]
    for i, l in zip(wanted(a), lists):
        if not l:
            print(f"{i}: not fetched (py tg_lists.py fetch)")
        elif not mother.links(l):
            print(f"{i}: the list has no link yet")
    lists = [l for l in lists if l and mother.links(l)]
    todo = [l for l in lists if a.again or not mother.cached(l, mother.cache_key(l))]
    for l in lists:
        if l not in todo:
            print(f"{mother.ref(l)}: unchanged since the cached map, no read")
    with ThreadPoolExecutor(max_workers=12) as pool:
        got = list(pool.map(read_one, [(n, l, r) for n, l in enumerate(todo) for r in ("A", "B")]))
    bad = 0
    for lst in todo:
        m, fixed, line = settle(lst, {r: text for i, r, text, why in got if i == mother.ref(lst)})
        if m is not None:
            mother.save(lst, m, "fleetA+fleetB" + ("+fix" if fixed else ""), [mother.links(lst)[k - 1]["post"] for k in fixed])
            print(f"{mother.ref(lst)}: {line}; map cached")
        else:
            bad += 1
            print(f"{mother.ref(lst)}: NOT cached. {line}")
    return 1 if bad else 0


def _show(a):
    for i in a.lists:
        row = mother.cached(i)
        if not row:
            print(f"{i}: no cached map")
            continue
        print(f"{i}: cached {row['at']} by {row['by']}")
        for k, v in sorted(row["map"].items(), key=lambda kv: int(kv[0])):
            if v["role"] != "ignore":
                print(f"  [{k}] {v['role']:<8} {v['chapter']!r} / {v['name']!r} covers {v['covers']}")
    return 0


def _diff(a):
    """What the newest cached map changes against the one before it. Prints only; nothing is applied."""
    for i in wanted(a):
        rows = mother.history(i)
        if not rows:
            print(f"{i}: no cached map")
            continue
        prev = rows[-2] if len(rows) > 1 else None
        changes = mother.diff(prev, rows[-1])
        before = len(mother.records(prev)) if prev else 0
        why = mother.held(changes, before)
        print(f"{i}: {len(changes)} changes against " + (f"the map of {prev['at']}" if prev else "nothing (first map)")
              + (f"; HELD: {why}" if why else ""))
        for c in changes[:a.show]:
            what = ", ".join(c["fields"]) if c["change"] == "edit" else c["role"]
            print(f"    {c['change']:<6} post {c['post']} {c['name']!r} in {c['chapter']!r} ({what})")
    return 0


def register(sub):
    p = sub.add_parser("mother", help="the mother-message agent (shadow mode)").add_subparsers(dest="mother_cmd")
    r = p.add_parser("render", help="what a reader is shown")
    r.add_argument("lists", nargs="+")
    r.set_defaults(run=_render)
    j = p.add_parser("job", help="write a reader's fleet job folder; nothing is run")
    j.add_argument("lists", nargs="+")
    j.add_argument("-r", "--reader", default="A", choices=("A", "B"))
    j.set_defaults(run=_job)
    n = p.add_parser("run", help="two fleet readers per changed list; cache the map they agree on")
    n.add_argument("lists", nargs="*")
    n.add_argument("--again", action="store_true", help="read even when the message is unchanged")
    n.add_argument("--year", type=int, choices=(1, 2), help="only this year's lists of the mother trees")
    n.set_defaults(run=_run)
    s = p.add_parser("show", help="the cached map")
    s.add_argument("lists", nargs="+")
    s.set_defaults(run=_show)
    d = p.add_parser("diff", help="what the newest map changes against the one before; prints only")
    d.add_argument("lists", nargs="*")
    d.add_argument("--dry", action="store_true", help="the default: nothing is ever applied here")
    d.add_argument("--year", type=int, choices=(1, 2))
    d.add_argument("--show", type=int, default=12, help="changes printed per list")
    d.set_defaults(run=_diff)

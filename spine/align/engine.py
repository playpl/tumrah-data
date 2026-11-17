"""Phase 1 end to end for one module: votes from every reader, then the links that two readers agree on.

    py -m spine p1 code year2-cns              code tiers + the old links as votes (no LLM)
    py -m spine p1 jobs year2-cns --reader A   fleet job folders for the sentences reader A has not read
    py -m spine p1 run year2-cns --reader A    run those jobs on the fleet accounts (resumable), collect votes
    py -m spine p1 accept year2-cns            votes -> edges/<book>.jsonl, with the order check
    py -m spine p1 status year2-cns

Readers: `code` (tiers A1 to A4), `old` (the old fleet link sitting inside the sentence), `fleetA`, `fleetB`
(B reads windows shifted by 5, so its neighbours differ). A link is accepted when code proves it (A1 to A3) or
when two readers name the same handout sentence. Everything lives in modules/<m>/graph/votes and /edges; the
old scripts, ledger.db and the site are not touched (shadow mode).
"""
import json
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from spine import ROOT, graph_dir, now, read_json, read_jsonl, write_json, write_jsonl
from spine.align import old, prefilter, recall, windows
from spine.books import split

CONF = {"A1": 0.99, "A2": 0.98, "A3": 0.95, "A4": 0.93}
PROVEN = ("A1", "A2", "A3")             # accepted on code alone; A4 needs one more reader
REL_OF_OLD = {"same": "S", "partial": "P", "reworded": "R"}
WINDOWS_PER_JOB = 5
FLEET = Path(r"C:\Users\Ahmed\agy-fleet\fleet.py")
ACCOUNTS = ["zero", "work", "personal", "other"]
PER_ACCOUNT = 6                         # fleet sessions at once on one account (owner, 2026-11-17: use the limits)
JUMP = 40                               # sentences away from its neighbours' targets = a jump


def jobs_home(book):
    return ROOT / "jobs" / "sp_align" / book


def votes_path(module, book, reader):
    return graph_dir(module) / "votes" / f"{book}.{reader}.jsonl"


def state(module, book, H):
    """A book's sentences, tier items and code results (the same every run)."""
    sents, items = recall.book_items(module, book, H)
    return sents, items, prefilter.code_tiers(items, H)


def canonical_books(module):
    aliases = split.dedupe(module)
    return [b for b in split.books(module) if b not in aliases], aliases


def run_code(module):
    """Write the `code` and `old` votes of every book. Returns {book: counts}."""
    H = prefilter.Handout(module)
    names, aliases = canonical_books(module)
    rows, old_books = old.row_map(module), old.old_books(module)
    out = {}
    for book in names:
        sents, items, res = state(module, book, H)
        code = [{"src": sents[i]["id"], "reader": "code", "tier": r[0], "at": now(),
                 "answer": {"dst": [H.sents[n]["id"] for n in r[1]], "rel": "S" if r[0] != "A3" else "R"}}
                for i, r in enumerate(res) if r]
        gold = recall.gold_of(module, book, sents, H, names, aliases, old_books, rows)
        olds = [{"src": sents[i]["id"], "reader": "old", "at": now(),
                 "answer": {"dst": [H.sents[n]["id"] for n in sorted(pos)], "rel": REL_OF_OLD[kind]}}
                for i, (pos, kind) in sorted(gold.items())]
        write_jsonl(votes_path(module, book, "code"), code)
        write_jsonl(votes_path(module, book, "old"), olds)
        out[book] = {"sentences": len(items), "code": len(code), "old": len(olds)}
    return out


SHIFT = {"A": 0, "B": 5, "C": 3}         # C is the third reader: only the windows that hold an open sentence


def open_sentences(module, book, H):
    """Ids of the book sentences the votes have not settled: split vote, one reader, one no, no reader."""
    from spine.align import audit
    st = audit.book_state(module, book, H)
    return {s["id"] for k in ("split-vote", "one-reader", "one-no", "no-reader") for s in st[k]}


def make_jobs(module, reader="A"):
    """Job folders for the windows this reader still has to read. Returns the folders written.

    Reader C (third reader) only reads windows that hold a sentence still open after A and B."""
    H = prefilter.Handout(module)
    shift = SHIFT[reader]
    made = []
    for book in canonical_books(module)[0]:
        sents, items, res = state(module, book, H)
        shown = [r if r and r[0] in PROVEN else None for r in res]
        read = {v["src"] for v in read_jsonl(votes_path(module, book, f"fleet{reader}"))}
        want = open_sentences(module, book, H) if reader == "C" else None
        wins = [w for w in prefilter.windows(len(items), shown, shift=shift)
                if any(not shown[i] and sents[i]["id"] not in read and (want is None or sents[i]["id"] in want)
                       for i in w)]
        home = jobs_home(book)
        for d in home.glob(f"{reader}-*"):                 # unfinished folders of an earlier plan are rebuilt
            if not (d / "done").exists() and not (d / "result.json").exists():
                for f in d.iterdir():
                    f.unlink()
                d.rmdir()
        taken = {int(d.name.split("-")[1]) for d in home.glob(f"{reader}-*")} if home.exists() else set()
        n = max(taken, default=0)
        for k in range(0, len(wins), WINDOWS_PER_JOB):
            n += 1
            rendered, keys = [], []
            for j, w in enumerate(wins[k:k + WINDOWS_PER_JOB], start=1):
                text, key = windows.render(items, shown, w, prefilter.candidates(items, shown, w, H), H, f"W{j}")
                key.update(ids={b: sents[i]["id"] for b, i in key["b"].items()},
                           texts={b: items[i]["text"] for b, i in key["b"].items()})
                rendered.append(text)
                keys.append(key)
            d = home / f"{reader}-{n:03d}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "prompt.md").write_text(windows.prompt(rendered), encoding="utf-8")
            write_json(d / "key.json", keys)
            made.append(d)
    return made


def collect(module, book, reader, H):
    """Parse every answered job of this reader into votes. A window with any error is left unread."""
    path = votes_path(module, book, f"fleet{reader}")
    votes = {v["src"]: v for v in read_jsonl(path)}
    stats = Counter()
    for d in sorted(jobs_home(book).glob(f"{reader}-*")):
        result = read_json(d / "result.json")
        if (d / "done").exists() or not result or result.get("status") != "SUCCESS":
            continue
        for key in read_json(d / "key.json"):
            items = {i: {"text": key["texts"][b]} for b, i in key["b"].items()}
            verdicts, errors = windows.parse(result.get("response") or "", key, H, items)
            stats["windows"] += 1
            if errors:
                stats["rejected"] += 1
                continue
            for b, i in key["b"].items():
                v = verdicts.get(i)
                if v is None or b in key["probe"]:
                    continue
                answer = v if isinstance(v, str) else {"dst": [H.sents[p]["id"] for p in v[1]], "rel": v[2]}
                votes[key["ids"][b]] = {"src": key["ids"][b], "reader": f"fleet{reader}", "answer": answer,
                                        "flag": bool(not isinstance(v, str) and v[3]), "job": d.name, "at": now()}
        (d / "done").write_text(now(), encoding="utf-8")
    write_jsonl(path, votes.values())
    return stats


def run_jobs(module, reader="A", accounts=None, limit=None, per_account=PER_ACCOUNT):
    """Run the unanswered job folders, `per_account` at a time on each fleet account, then collect.

    Safe to run again: answered folders are skipped. One runner at a time (two would run a job twice)."""
    H = prefilter.Handout(module)
    todo = [d for book in canonical_books(module)[0] for d in sorted(jobs_home(book).glob(f"{reader}-*"))
            if not (d / "done").exists() and (read_json(d / "result.json") or {}).get("status") != "SUCCESS"]
    todo = todo[:limit] if limit else todo
    accounts = list(accounts or ACCOUNTS)
    stats, resting = Counter(), set()

    def work(arg):
        n, d = arg
        for attempt in range(len(accounts)):
            account = accounts[(n + attempt) % len(accounts)]
            if account in resting:
                continue
            subprocess.run(["py", str(FLEET), "run", "-a", account, "--cwd", str(d), "-f", "prompt.md",
                            "--out", "result.json", "--timeout", "20"], capture_output=True, text=True, cwd=d)
            r = read_json(d / "result.json") or {}
            if r.get("status") == "SUCCESS":
                return "answered"
            if r.get("failure") == "quota":
                resting.add(account)
        return "failed"

    with ThreadPoolExecutor(max_workers=len(accounts) * per_account) as pool:
        for verdict in pool.map(work, enumerate(todo)):
            stats[verdict] += 1
    for book in canonical_books(module)[0]:
        stats.update(collect(module, book, reader, H))
    stats["accounts out of quota"] = len(resting)
    return stats


def jumps(targets):
    """Numbers of the entries whose handout position is far from the median of their neighbours' positions."""
    out = []
    for k, (_, pos) in enumerate(targets):
        near = sorted(p for _, p in targets[max(0, k - 5):k] + targets[k + 1:k + 6])
        if len(near) >= 4 and abs(pos - near[len(near) // 2]) > JUMP:
            out.append(k)
    return out


def accept(module):
    """Votes -> edges/<book>.jsonl. Returns {book: counts}."""
    H = prefilter.Handout(module)
    out = {}
    for book in canonical_books(module)[0]:
        sents = [s for s in split.load(module, book) if s["kind"] != "not_content"]
        votes = {}
        for f in sorted((graph_dir(module) / "votes").glob(f"{book}.*.jsonl")):
            for v in read_jsonl(f):
                votes.setdefault(v["src"], {})[v["reader"]] = v
        edges, counts, chain = [], Counter(), []
        for s in sents:
            mine = votes.get(s["id"], {})
            code = mine.get("code")
            links = {r: set(v["answer"]["dst"]) for r, v in mine.items() if isinstance(v["answer"], dict)}
            nos = [r for r, v in mine.items() if isinstance(v["answer"], str)]
            verdict = None
            if code and code["tier"] in PROVEN:
                verdict = (links["code"], code["answer"]["rel"], CONF[code["tier"]], f"spine-code:{code['tier']}")
            else:
                pairs = [(a, b) for a in links for b in links if a < b and links[a] & links[b]]
                if pairs:
                    a, b = pairs[0]
                    fleet = next((r for r in (a, b) if r.startswith("fleet")), None)
                    rel = mine[fleet or b]["answer"]["rel"]
                    verdict = (links[a] & links[b], rel, 0.9, "spine-fleet" if fleet else "spine-code:old")
            if verdict:
                dst, rel, conf, by = verdict
                for d in sorted(dst, key=H.pos.get):
                    edges.append({"src": s["id"], "dst": d, "rel": rel, "grp": s["i"], "conf": conf, "by": by,
                                  "state": "accepted", "at": now()})
                chain.append((s["id"], min(H.pos[d] for d in dst)))
                counts["accepted"] += 1
            elif len(nos) >= 2 or (nos and not links):
                counts["not in the handout or not content" if len(nos) >= 2 else "one reader says no"] += 1
            elif len(links) >= 2:
                counts["readers disagree"] += 1
            elif links:
                counts["one reader only"] += 1
            else:
                counts["no reader yet"] += 1
        odd = {chain[k][0] for k in jumps(chain)}
        for e in edges:
            if e["src"] in odd:
                e["state"] = "flagged"
        counts["accepted"] -= len(odd)
        counts["jump (flagged)"] = len(odd)
        write_jsonl(graph_dir(module) / "edges" / f"{book}.jsonl", edges)
        counts["sentences"] = len(sents)
        out[book] = counts
    return out


def report(per_book, title):
    keys = sorted({k for c in per_book.values() for k in c if k != "sentences"})
    total = Counter()
    lines = [title]
    for book, c in per_book.items():
        total.update(c)
        lines.append(f"  {book:<22} {c.get('sentences', 0):>5} sentences: "
                     + ", ".join(f"{k} {c[k]:,}" for k in keys if c.get(k)))
    lines.append(f"  all: {total.get('sentences', 0):,} sentences: " + ", ".join(f"{k} {total[k]:,}" for k in keys if total.get(k)))
    return "\n".join(lines)

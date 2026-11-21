"""Phase 1 end to end for one module: votes from every reader, then the links that two readers agree on.

    py -m spine p1 code year2-cns              code tiers + the old links as votes (no LLM)
    py -m spine p1 jobs year2-cns --reader A   job folders for the sentences reader A has not read
    py -m spine p1 run year2-cns --reader A    Gemini web (4 Hydrogen) answers those jobs (resumable), collect votes
    py -m spine p1 accept year2-cns            votes -> edges/<book>.jsonl, with the order check
    py -m spine p1 status year2-cns

Readers: `code` (tiers A1 to A4), `old` (the old fleet link sitting inside the sentence), `fleetA`, `fleetB`
(B reads windows shifted by 5, so its neighbours differ). The names stay `fleet<R>` for the votes files; since the fleet
was retired (owner 2026-11-18) the answers come from Gemini web, 4 Hydrogen (result.json "by": "gemini"). A link is accepted when code proves it (A1 to A3) or
when two readers name the same handout sentence. Everything lives in modules/<m>/graph/votes and /edges; the
old scripts, ledger.db and the site are not touched (shadow mode).
"""
import json
import re
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from spine import ROOT, graph_dir, now, read_json, read_jsonl, write_json, write_jsonl
from spine.align import old, prefilter, recall, windows
from spine.books import split
from spine import text as T

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
    """Ids of the book sentences the votes have not settled: split vote, one reader, one no, no reader, jump."""
    from spine.align import audit
    st = audit.book_state(module, book, H)
    return {s["id"] for k in ("split-vote", "one-reader", "one-no", "no-reader") for s in st[k]} |         {s["id"] for s, _ in st["jump"]}            # a jump is checked by the third reader too


def make_jobs(module, reader="A", per_job=WINDOWS_PER_JOB):
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
        for k in range(0, len(wins), per_job):
            n += 1
            rendered, keys = [], []
            for j, w in enumerate(wins[k:k + per_job], start=1):
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


MODEL = "hydrogen"                      # Gemini web (owner 2026-11-18)
WAIT = 900


def ask_gemini(d, ask=None):
    """One job folder answered on Gemini web: result.json {"status": "SUCCESS", "response", "by": "gemini"}.
    "answered", "capped" (every account at its usage cap; meta "until" kept in CAPPED) or "failed"."""
    if ask is None:
        import functools
        import gemini_browser
        # Linking never runs on the free model (owner 2026-11-21: "We won't link with the light model"): a capped
        # account is skipped and the job waits for a renewal instead of answering with Flash-Lite.
        ask = functools.partial(gemini_browser.ask, fallback=False)
    text, meta = ask((d / "prompt.md").read_text(encoding="utf-8"), model=MODEL, wait=WAIT)
    if text is None and meta.get("until"):
        CAPPED["until"] = max(CAPPED["until"], float(meta["until"]))
        return "capped"
    if not text or not any(windows.LINE.match(x.strip()) for x in text.splitlines()):
        write_json(d / "reply_failed.json", {"text": text, **meta, "at": now()})
        return "failed"
    write_json(d / "result.json", {"status": "SUCCESS", "response": text, "by": "gemini", "model": MODEL, **meta,
                                   "at": now()})
    return "answered"


CAPPED = {"until": 0.0}


def run_gemini(module, reader="A", limit=None, workers=4, wait_caps=True, ask=None, sleep=time.sleep, say=print):
    """Gemini web answers the unanswered job folders, `workers` chats at a time (one per account), then collect.
    With `wait_caps`, a job that finds every account capped waits for the first renewal."""
    H = prefilter.Handout(module)
    todo = [d for book in canonical_books(module)[0] for d in sorted(jobs_home(book).glob(f"{reader}-*"))
            if not (d / "done").exists() and (read_json(d / "result.json") or {}).get("status") != "SUCCESS"]
    todo = todo[:limit] if limit is not None else todo
    stats = Counter()

    def work(d):
        while True:
            v = ask_gemini(d, ask)
            if v != "capped" or not wait_caps:
                break
            secs = max(60, CAPPED["until"] - time.time() + 60)
            say(f"  {d.parent.name}/{d.name}: every account capped; waiting {secs / 60:.0f} min")
            sleep(secs)
        say(f"  {d.parent.name}/{d.name}: {v}")
        return v

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 4))) as pool:
        for verdict in pool.map(work, todo):
            stats[verdict] += 1
    for book in canonical_books(module)[0]:
        stats.update(collect(module, book, reader, H))
    return stats


def run_jobs(module, reader="A", accounts=None, limit=None, per_account=PER_ACCOUNT):
    """RETIRED (fleet down 2026-11-18; `run_gemini` replaces it). Run the unanswered job folders, `per_account` at
    a time on each fleet account, then collect. Refuses while config fleet.down is true."""
    from spine import config
    if (config().get("fleet") or {}).get("down"):
        raise SystemExit("the fleet is retired (config fleet.down): py -m spine p1 run uses Gemini web")
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


def jumps(targets, order=True):
    """Numbers of the entries whose handout position is far from the median of their neighbours' positions. An entry
    in order between its two direct neighbours is never a jump: at a section boundary the median sits on one side
    (Zahran's receptor table, p36 -> table p37 -> meninges p42, was flagged)."""
    out = []
    for k, (_, pos) in enumerate(targets):
        if order and 0 < k < len(targets) - 1 and targets[k - 1][1] <= pos <= targets[k + 1][1]:
            continue
        near = sorted(p for _, p in targets[max(0, k - 5):k] + targets[k + 1:k + 6])
        if len(near) >= 4 and abs(pos - near[len(near) // 2]) > JUMP:
            out.append(k)
    return out


def three_agree(mine):
    """True when three different readers (code, old, fleet A/B/C) link this sentence to a common handout sentence."""
    links = [set(v["answer"]["dst"]) for v in mine.values() if isinstance(v["answer"], dict)]
    for i, a in enumerate(links):
        for j in range(i + 1, len(links)):
            for k in range(j + 1, len(links)):
                if a & links[j] & links[k]:
                    return True
    return False


CELL_SPLIT = re.compile(r"\s*(?:\||[\uf000-\uf0ff\u2022\u25aa\u25fe\u25cf\u27a2]|(?<![\d.])\d{1,2}[.)-]\s|^[a-zA-Z][.)-]\s)\s*")
CELL_NEAR = 40                          # handout sentences around the row's own link


def cell_links(s, dsts, H):
    """Handout sentences that one cell of a table row (or one bullet of a list line) says word for word, close to the
    row's accepted link, in the same lesson: a row of three cells is three handout facts, but the readers' agreed set
    often holds one (Zahran's tables, parity p1 2026-11-21). Code-proven: the cell's letters (>= LONG) occur exactly
    once inside that window."""
    parts = [x for x in CELL_SPLIT.split(s["text"]) if x and x.strip()]
    anchor = [H.pos[d] for d in dsts if d in H.pos]
    if len(parts) < 2 or not anchor:
        return []
    lo, hi = min(anchor) - CELL_NEAR, max(anchor) + CELL_NEAR
    lessons = {H.lesson[a] for a in anchor}
    out = []
    for part in parts:
        k = T.word_key(part)
        if len(k) < prefilter.LONG:
            continue
        hits = [h for h in H.exact(k) if lo <= h[0] <= hi and H.lesson[h[0]] in lessons]
        if len(hits) == 1:
            out += [H.sents[n]["id"] for n in hits[0]]
    return [d for d in dict.fromkeys(out) if d not in dsts]


ROW_NEAR = 3                            # book sentences to look back and ahead for an open row's neighbours


def open_row_cells(sents, linked, H):
    """[(sentence, handout ids)]: a table row no reader settled (a row of three columns read as one sentence:
    "Pear-shaped structure  Spherical body  It is a fusiform structure") borrows the links of its nearest linked
    book sentences before and after (within ROW_NEAR, landing within 2 * CELL_NEAR of each other) as the anchor for
    `cell_links`."""
    out = []
    for k, s in enumerate(sents):
        if s["id"] in linked:
            continue
        before = next((linked[x["id"]] for x in reversed(sents[max(0, k - ROW_NEAR):k]) if x["id"] in linked), None)
        after = next((linked[x["id"]] for x in sents[k + 1:k + 1 + ROW_NEAR] if x["id"] in linked), None)
        if not before or not after:
            continue
        pos = [H.pos[d] for d in before | after if d in H.pos]
        if not pos or max(pos) - min(pos) > 2 * CELL_NEAR:
            continue
        more = cell_links(s, before | after, H)
        if more:
            out.append((s, more))
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
        edges, counts, chain, linked = [], Counter(), [], {}
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
                linked[s["id"]] = set(dst)
                counts["accepted"] += 1
                more = cell_links(s, dst, H)
                for d in sorted(more, key=H.pos.get):
                    edges.append({"src": s["id"], "dst": d, "rel": "P", "grp": s["i"], "conf": 0.95,
                                  "by": "spine-code:cell", "state": "accepted", "at": now()})
                counts["cell links added"] += len(more)
            elif len(nos) >= 2 or (nos and not links):
                counts["not in the handout or not content" if len(nos) >= 2 else "one reader says no"] += 1
            elif len(links) >= 2:
                counts["readers disagree"] += 1
            elif links:
                counts["one reader only"] += 1
            else:
                counts["no reader yet"] += 1
        for s, more in open_row_cells(sents, linked, H):
            for d in sorted(more, key=H.pos.get):
                edges.append({"src": s["id"], "dst": d, "rel": "P", "grp": s["i"], "conf": 0.95,
                              "by": "spine-code:cell", "state": "accepted", "at": now()})
            counts["open table rows linked by their cells"] += 1
        odd = {chain[k][0] for k in jumps(chain, order=False)}
        confirmed = {sid for sid in odd if three_agree(votes.get(sid, {}))}   # a jump three readers back is real
        counts["jump confirmed by 3 readers"] = len(confirmed)
        odd -= confirmed
        unique = {e["src"] for e in edges if e["src"] in odd and e["by"] in ("spine-code:A1", "spine-code:A2")}
        counts["jump kept: text found only there (A1/A2)"] = len(unique)    # the book orders it differently
        odd -= unique
        in_order = odd - {chain[k][0] for k in jumps(chain)}
        counts["jump kept: in order between its neighbours"] = len(in_order)
        odd -= in_order
        for e in edges:        # kept: the seg slices (built without kept edges) do not change under the readers
            if e["src"] in unique:
                e["kept"] = "jump, text found only there"
            elif e["src"] in in_order:
                e["kept"] = "jump, in order between its neighbours"
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

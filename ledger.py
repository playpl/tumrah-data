"""The ledger: every link to the handout is one row, whoever made it (owner, 2026-11-10: lowest error rate).

A link ties one thing to handout lines: a lesson (its ranges), a question (the lines that teach it), a doctor-book
block, a part of a recording. Each reader writes its own row (`runner`: script, fleet, web, owner...), so two readers
of the same thing can be compared and nothing is overwritten. What the site may use is decided here, by state:

    proposed   one reader said so, nobody checked
    agreed     two independent readers chose the same lines
    conflict   two readers chose different lines: held until a judge or the owner picks
    owner      the owner said so (never changed by code)
    rejected   the owner marked it wrong in a spot check

Ready for the site = agreed or owner, plus the proposed rows of a reader whose spot checks pass config.json `ready`.
Lesson membership is never stored: a question belongs to a lesson when its lines lie inside the lesson's ranges.

    py ledger.py sync [module]     read every flow's files into ledger.db, mark agreement (changes no other file)
    py ledger.py status [module]   counts by kind, reader and state; measured error per reader
Counts and ids only: this file prints no question, book or transcript text.
"""
import json
import math
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import lectures
from flows.common import read_jsonl

ROOT = Path(__file__).resolve().parent
DB = ROOT / "ledger.db"
MODULE = "year2-cns"
KINDS = ("lesson", "question", "block", "part")
SCHEMA = """
CREATE TABLE IF NOT EXISTS links(module TEXT, kind TEXT, src TEXT, runner TEXT, lines TEXT, found INTEGER, reason TEXT,
  scope TEXT, model TEXT, job TEXT, at REAL, state TEXT DEFAULT 'proposed', PRIMARY KEY(kind, src, runner));
CREATE INDEX IF NOT EXISTS links_state ON links(module, kind, state);
CREATE TABLE IF NOT EXISTS gold(kind TEXT, src TEXT, runner TEXT, verdict TEXT, at REAL, PRIMARY KEY(kind, src, runner));
CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY, kind TEXT, title TEXT, detail TEXT, options TEXT, payload TEXT,
  state TEXT DEFAULT 'open', answer TEXT, at REAL);
CREATE TABLE IF NOT EXISTS rules(key TEXT PRIMARY KEY, value TEXT, at REAL);
"""
READY_DEFAULT = {"max_error": 0.05, "min_checked": 30}  # config.json `ready`: the owner's threshold


def connect(path=None):
    db = sqlite3.connect(path or DB, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


BACKUP_DIR = ROOT / "backups_ledger"      # full copies of ledger.db (ignored by git), newest KEEP kept
OWNER_JSON = ROOT / "data_backup" / "ledger_owner.json"  # the owner's answers as text, tracked in git
KEEP = 20


def backup(db_path=None, backup_dir=None, owner_json=None, keep=KEEP):
    """Safe copy of ledger.db (sqlite online backup) plus the owner's answers (gold, rules, answered decisions,
    runner 'owner' links) as a small JSON that git tracks. Rewritten only when the answers changed."""
    db_path, backup_dir, owner_json = Path(db_path or DB), Path(backup_dir or BACKUP_DIR), Path(owner_json or OWNER_JSON)
    if not db_path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    out = backup_dir / time.strftime("ledger-%Y%m%d-%H%M%S.db")
    src, dst = sqlite3.connect(db_path, timeout=30), sqlite3.connect(out)
    try:
        src.backup(dst)
    finally:
        dst.close()
    src.row_factory = sqlite3.Row
    try:
        owner = {
            "gold": [dict(r) for r in src.execute("SELECT * FROM gold ORDER BY kind, src, runner")],
            "rules": [dict(r) for r in src.execute("SELECT * FROM rules ORDER BY key")],
            "decisions": [dict(r) for r in src.execute("SELECT * FROM decisions WHERE state != 'open' ORDER BY id")],
            "links": [dict(r) for r in src.execute("SELECT * FROM links WHERE runner = 'owner' ORDER BY kind, src")],
        }
    finally:
        src.close()
    text = json.dumps(owner, ensure_ascii=False, indent=1, sort_keys=True)
    owner_json.parent.mkdir(parents=True, exist_ok=True)
    if not owner_json.exists() or owner_json.read_text(encoding="utf-8") != text:
        owner_json.write_text(text, encoding="utf-8")
    for old in sorted(backup_dir.glob("ledger-*.db"))[:-keep]:
        old.unlink()
    return out


def put(db, module, kind, src, runner, lines, found=True, reason=None, scope=None, model=None, job=None, state=None):
    """One reader's link. A row whose lines did not change keeps its state (agreed, rejected...); new lines start again
    as proposed. The owner's rows are written only by the owner (runner 'owner')."""
    lines = json.dumps(lines)
    db.execute(
        "INSERT INTO links(module, kind, src, runner, lines, found, reason, scope, model, job, at, state) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(kind, src, runner) DO UPDATE SET lines=excluded.lines, "
        "found=excluded.found, reason=excluded.reason, scope=excluded.scope, model=excluded.model, job=excluded.job, "
        "at=CASE WHEN links.lines=excluded.lines THEN links.at ELSE excluded.at END, "
        "state=CASE WHEN ? IS NOT NULL THEN excluded.state WHEN links.lines=excluded.lines THEN links.state ELSE 'proposed' END",
        (module, kind, src, runner, lines, int(bool(found)), reason, scope, model, job, time.time(),
         state or ("owner" if runner == "owner" else "proposed"), state))


# ---- the handout order ---------------------------------------------------------------------------------------------
def order(module):
    """line id -> its index in lines.jsonl (handout order)."""
    return {ln["id"]: i for i, ln in enumerate(read_jsonl(ROOT / "modules" / module / "lines.jsonl"))}


def range_ids(ranges, idx, ids, page_of):
    """The line ids inside a lecture's ranges. A range marked `cut` (set at a heading, placement.py) runs from its
    `from` line to its `to` line in handout order; an older range is whole pages (a page's figures are not always
    between its first and last text line in lines.jsonl, so those go by page)."""
    out = set()
    for r in ranges or []:
        if r.get("cut"):
            a, b = idx.get(r["from"]), idx.get(r["to"])
            if a is not None and b is not None:
                out.update(ids[a:b + 1])
        else:
            a, b = r["pages"]
            out.update(i for i in ids if a <= page_of[i] <= b)
    return out


def lesson_ids(module, kinds=("lecture",)):
    """lecture id -> the handout line ids its ranges hold (lecture.json is the truth for a lesson's place)."""
    rows = read_jsonl(ROOT / "modules" / module / "lines.jsonl")
    ids = [ln["id"] for ln in rows]
    idx, page_of = {i: n for n, i in enumerate(ids)}, {ln["id"]: ln["page"] for ln in rows}
    return {m["id"]: range_ids(m.get("ranges"), idx, ids, page_of) for m in lectures.all_lectures(module)
            if m.get("kind", "lecture") in kinds}


# ---- sync: every flow's files into the ledger ------------------------------------------------------------------------
def _runner(note):
    return "web" if "gemini" in (note or "") else "fleet"


def sync(module=MODULE, db=None):
    """Reads what the flows already wrote (nothing else is changed) and marks agreement. Returns counts."""
    own = db is None
    db = db or connect()
    n = Counter()
    for m in lectures.all_lectures(module):
        if m.get("ranges"):
            by = m.get("placed_by") or "unknown"
            put(db, module, "lesson", m["id"], by, [[r["from"], r["to"]] for r in m["ranges"]],
                state="owner" if by == "owner" else None)
            n["lesson"] += 1
    fp = ROOT / "modules" / module / "site" / "fast_points.json"
    for wk, p in (json.loads(fp.read_text(encoding="utf-8")) if fp.exists() else {}).items():
        if p.get("reader"):
            continue  # fast_lessons copied a better reading from this ledger: not the script's own choice
        put(db, module, "question", wk, "script", p["lines"], scope=f"label:{p.get('lecture_id')}")
        n["question script"] += 1
    qdb = ROOT / "queue.db"
    jobs = []
    if qdb.exists():
        q = sqlite3.connect(qdb)
        jobs = q.execute("SELECT flow, key, payload, note FROM jobs WHERE status='passed' AND flow IN "
                         "('pointers', 'books', 'lecture_links')").fetchall()
        q.close()
    link_note = {}
    for flow, key, payload, note in jobs:
        d = ROOT / "jobs" / flow / key
        p = json.loads(payload)
        if flow == "pointers" and (d / "pointers.jsonl").exists() and p.get("module") == module:
            wk = {b["qid"]: b.get("word_key") for b in p["batch"]}
            for r in read_jsonl(d / "pointers.jsonl"):
                src = wk.get(r["question_id"])
                if not src or r.get("reason") == "other_lecture":
                    continue  # "not in this lecture" says nothing about where it is
                ids = [i for s in r.get("spans") or [] for i in s.get("line_ids") or []]
                put(db, module, "question", src, _runner(note), ids, found=r["found"], reason=r.get("reason"),
                    scope=f"lecture:{p.get('lecture')}" if p.get("lecture") else "module", job=key)
                n["question ai"] += 1
        elif flow == "books" and (d / "aligned.jsonl").exists() and p.get("module") == module:
            for page in read_jsonl(d / "aligned.jsonl"):
                for b in page.get("blocks") or []:
                    if b.get("match") == "not_content":
                        continue
                    put(db, module, "block", f"{page['book_id']}:{page['page']}:{b['n']}", _runner(note),
                        b.get("line_ids") or [], found=bool(b.get("line_ids")), reason=b.get("match"), job=key)
                    n["block"] += 1
        elif flow == "lecture_links":
            link_note[p.get("lecture")] = note
    for m in lectures.all_lectures(module):
        f = lectures.folder(m["id"]) / "links.jsonl"
        for r in read_jsonl(f) if f.exists() else []:
            put(db, module, "part", f"{m['id']}:{r['part']}.{r.get('sub', 0)}", _runner(link_note.get(m["id"])),
                r.get("line_ids") or [], found=bool(r.get("line_ids")), scope=f"lecture:{m['id']}")
            n["part"] += 1
    n.update(agree(db, module))
    db.commit()
    if own:
        db.close()
    return dict(n)


def agree(db, module, kind="question"):
    """Two readers of one thing: the same line (any shared line) = agreed; no shared line = conflict. The owner's and
    rejected rows are left alone, and a thing the owner settled has no conflict."""
    by_src = {}
    for r in db.execute("SELECT src, runner, lines, found, state FROM links WHERE module=? AND kind=?", (module, kind)):
        by_src.setdefault(r["src"], []).append(r)
    n = Counter()
    for src, rows in by_src.items():
        live = [r for r in rows if r["found"] and r["state"] not in ("owner", "rejected")]
        if len(live) < 2 or any(r["state"] == "owner" for r in rows):
            continue
        sets = [set(json.loads(r["lines"])) for r in live]
        state = "agreed" if all(sets[0] & s for s in sets[1:]) else "conflict"
        db.execute(f"UPDATE links SET state=? WHERE kind=? AND src=? AND runner IN ({','.join('?' * len(live))})",
                   (state, kind, src, *[r["runner"] for r in live]))
        n[state] += 1
    return n


# ---- gold: the owner's spot checks, and what they say about each reader ----------------------------------------------
def mark(db, kind, src, runner, right):
    """The owner looked at one link: right or wrong. A wrong link is rejected and leaves the site files."""
    db.execute("INSERT OR REPLACE INTO gold(kind, src, runner, verdict, at) VALUES(?,?,?,?,?)",
               (kind, src, runner, "right" if right else "wrong", time.time()))
    db.execute("UPDATE links SET state=? WHERE kind=? AND src=? AND runner=? AND state!='owner'",
               ("rejected" if not right else "agreed", kind, src, runner))
    db.commit()


def wilson(wrong, n, z=1.96):
    """(rate, low, high) of the true error rate at 95%; (None, 0, 1) with nothing checked."""
    if not n:
        return None, 0.0, 1.0
    p = wrong / n
    mid, half = (p + z * z / (2 * n)) / (1 + z * z / n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, max(0.0, mid - half), min(1.0, mid + half)


def errors(db):
    """(kind, runner) -> {checked, wrong, rate, low, high} from the spot checks."""
    out = {}
    for r in db.execute("SELECT kind, runner, COUNT(*) n, SUM(verdict='wrong') w FROM gold GROUP BY kind, runner"):
        rate, low, high = wilson(r["w"], r["n"])
        out[(r["kind"], r["runner"])] = {"checked": r["n"], "wrong": r["w"], "rate": rate, "low": low, "high": high}
    return out


def ready_rule():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    return {**READY_DEFAULT, **(cfg.get("ready") or {})}


def passing(db):
    """The (kind, runner) classes whose spot checks pass the owner's threshold."""
    rule = ready_rule()
    return {k for k, e in errors(db).items() if e["checked"] >= rule["min_checked"] and e["rate"] <= rule["max_error"]}


def ready(db, module, kind):
    """The rows the site may use, one per src: the owner's first, then agreed, then a passing reader's proposal."""
    ok = passing(db)
    rank = {"owner": 0, "agreed": 1, "proposed": 2}
    best = {}
    for r in db.execute("SELECT * FROM links WHERE module=? AND kind=? AND found=1 AND state IN ('owner','agreed','proposed')",
                        (module, kind)):
        if r["state"] == "proposed" and (kind, r["runner"]) not in ok:
            continue
        key = (rank[r["state"]], r["runner"] == "script")  # at the same state an AI reading beats the word-overlap script
        if r["src"] not in best or key < best[r["src"]][0]:
            best[r["src"]] = (key, r)
    return {src: r for src, (_, r) in best.items()}


def members(db, module):
    """lecture id -> the ready questions whose lines lie inside it. Computed, never stored: a moved boundary moves them."""
    lessons = lesson_ids(module)
    out = {lid: [] for lid in lessons}
    for src, r in ready(db, module, "question").items():
        ids = set(json.loads(r["lines"]))
        for lid, lines in lessons.items():
            if ids & lines:
                out[lid].append(src)
    return out


def status(module=MODULE, db=None):
    db = db or connect()
    rows = db.execute("SELECT kind, runner, state, COUNT(*) n FROM links WHERE module=? GROUP BY kind, runner, state", (module,))
    out = {"links": {}, "ready": {}, "errors": {}}
    for r in rows:
        out["links"].setdefault(r["kind"], {}).setdefault(r["runner"], {})[r["state"]] = r["n"]
    for kind in KINDS:
        out["ready"][kind] = len(ready(db, module, kind))
    out["errors"] = {f"{k} by {r}": e for (k, r), e in errors(db).items()}
    out["threshold"] = ready_rule()
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    module = sys.argv[2] if len(sys.argv) > 2 else MODULE
    print(json.dumps(sync(module) if cmd == "sync" else status(module), indent=1))

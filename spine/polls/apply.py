"""py -m spine polls apply [--go]: the two polls changes the owner ordered (GO given 2026-11-17, "as counted").

    A. Batch58ATM (Year 2 backbone): polls labelled with a `drop_modules` module (year2-endocrine-and-reproductive,
       year2-other) are deleted for good: their polls.db rows and our own votes on them, their sightings in
       polls/ready/ and bank/. No archive (owner). Their message ids go to polls/tombstones.jsonl, so a rescrape
       never lists them again.
    B. zagpolls58 (Year 1 archive): leaves the live stores for the grade 5 store, nothing destroyed:
       polls/grade5/questions.jsonl (the bank rows `registry.plan` calls grade5, with their label),
       polls/grade5/polls.db (its polls.db rows, own votes and channel row), polls/grade5/raw/zagpolls58/ (moved).

A question also seen in a kept channel, or in a doctor's quiz, form or MCQ book, stays and only loses the dropped
sightings ("trim"). polls/ready/ holds polls only: a row with no poll sighting left leaves it (the bank keeps the
question through its other source). A kept poll marked `dupe` whose keyed twin is gone goes back to `need`, so the
next polls job votes it (else a rebuild of ready/ would hold it with no key).

Dry run by default: prints what would change, writes nothing. `--go` applies. The polls job must not be running.
"""
import json
import os
import shutil
import sqlite3
import time
from collections import Counter

from spine import ROOT
from spine.polls import registry

POLLS, BANK = registry.POLLS, registry.BANK
GRADE5 = POLLS / "grade5"
TOMBSTONES = POLLS / "tombstones.jsonl"


def _engine(polls_dir=POLLS):
    import importlib.util
    spec = importlib.util.spec_from_file_location("polls_engine_apply", polls_dir / "engine.py")
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    return engine


def dropped(sighting, module, reg):
    """True when a poll sighting leaves the live stores: its channel is an archive, or drops this module."""
    if sighting.get("source", "poll") != "poll":
        return False
    c = next((c for c in reg if c["chat"] == sighting.get("chat")), None)
    return bool(c) and (c.get("role") == "archive" or module in c.get("drop_modules", []))


def trim_row(row, module, reg):
    """The row with its dropped sightings taken out (a copy), and how many were taken out."""
    keep = [s for s in row.get("sightings", []) if not dropped(s, module, reg)]
    out = dict(row, sightings=keep)
    if "source_url" in row and keep:
        out["source_url"] = keep[0].get("link") or row["source_url"]
    return out, len(row.get("sightings", [])) - len(keep)


def _write_jsonl(path, rows):
    tmp = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def plan_files(polls_dir=POLLS, bank_dir=BANK, reg=None, engine=None):
    """Everything the change does to the files, computed in memory: new bank rows, grade 5 rows, new ready and
    held rows, and counts."""
    reg = registry.channels() if reg is None else reg
    engine = engine or _engine(polls_dir)
    labels = {r["word_key"]: r.get("module") or registry.UNLABELLED
              for r in registry._stream(bank_dir / "labels.jsonl")}
    n = Counter()
    bank, grade5 = [], []
    for row in registry._stream(bank_dir / "questions.jsonl"):
        module = labels.get(row["word_key"], registry.UNLABELLED)
        verdict = registry.plan(row, module, reg)[0]
        n[f"bank {verdict}"] += 1
        if verdict == "grade5":
            grade5.append(dict(row, module=module))
        elif verdict == "trim":
            new, k = trim_row(row, module, reg)
            n["bank sightings dropped"] += k
            bank.append(new)
        elif verdict == "keep":
            bank.append(row)
    ready = {}
    for name in ("questions", "held"):
        rows = []
        for row in registry._stream(polls_dir / "ready" / f"{name}.jsonl"):
            wk = engine.word_key(row["question"], row["options"])
            new, k = trim_row(row, labels.get(wk, registry.UNLABELLED), reg)
            if not new["sightings"]:
                n[f"ready {name} removed"] += 1
                continue
            n[f"ready {name} trimmed"] += bool(k)
            rows.append(new)
        n[f"ready {name} before"] = n[f"ready {name} removed"] + len(rows)
        ready[name] = rows
    return {"bank": bank, "grade5": grade5, "ready": ready, "counts": n, "labels": labels}


def plan_db(con, labels, reg):
    """(A rows, archive rows, dupes to vote again) of polls.db, as lists of (chat, msg_id)."""
    drop = {c["chat"]: set(c.get("drop_modules", [])) for c in reg}
    archives = {c["chat"] for c in reg if c.get("role") == "archive"}
    a_rows, b_rows, kept = [], [], []
    for chat, msg_id, wk, status in con.execute("SELECT chat, msg_id, word_key, status FROM polls"):
        if labels.get(wk, registry.UNLABELLED) in drop.get(chat, ()):
            a_rows.append((chat, msg_id))
        elif chat in archives:
            b_rows.append((chat, msg_id))
        else:
            kept.append((chat, msg_id, wk, status))
    keyed = {wk for _, _, wk, status in kept if status == "keyed"}
    pending = {wk for _, _, wk, status in kept if status in ("need", "claimed")}
    revote = []
    for chat, msg_id, wk, status in kept:
        if status == "dupe" and wk not in keyed and wk not in pending:
            revote.append((chat, msg_id))
            pending.add(wk)                              # one vote per question is enough
    return a_rows, b_rows, revote


def job_running(con):
    row = con.execute("SELECT v FROM state WHERE k='beat'").fetchone()
    return bool(row) and time.time() - float(row[0] or 0) < 15


def apply(go=False, polls_dir=POLLS, bank_dir=BANK, reg=None, config_path=None, out=print):
    reg = registry.channels() if reg is None else reg
    engine = _engine(polls_dir)
    archives = [c["chat"] for c in reg if c.get("role") == "archive"]
    db = polls_dir / "polls.db"
    con = sqlite3.connect(db, timeout=30, isolation_level=None)
    try:
        if job_running(con):
            out("STOP: the polls job is running (its heartbeat is fresh). Stop it on the polls page first.")
            return 2
        files = plan_files(polls_dir, bank_dir, reg, engine)
        a_rows, b_rows, revote = plan_db(con, files["labels"], reg)
        a_own = _count_own(con, a_rows)
        b_own = _count_own(con, b_rows)
        n = files["counts"]
        out(f"{'APPLY' if go else 'DRY RUN (nothing written; --go applies)'}: polls changes A and B")
        out(f"  polls.db: A deletes {len(a_rows):,} rows and {a_own:,} own votes; B moves {len(b_rows):,} rows and "
            f"{b_own:,} own votes to {(polls_dir / 'grade5' / 'polls.db').relative_to(ROOT) if _under_root(polls_dir) else 'grade5/polls.db'}")
        out(f"  polls.db: {len(revote):,} kept dupes whose keyed twin leaves go back to 'need' (the next polls job votes them)")
        out(f"  bank/questions.jsonl: keep {n['bank keep']:,}, trim {n['bank trim']:,} ({n['bank sightings dropped']:,} "
            f"sightings dropped), delete {n['bank delete']:,}, grade 5 {n['bank grade5']:,}; "
            f"{len(files['bank']):,} rows after")
        for name in ("questions", "held"):
            out(f"  ready/{name}.jsonl: {n[f'ready {name} before']:,} rows, {n[f'ready {name} removed']:,} leave, "
                f"{n[f'ready {name} trimmed']:,} trimmed, {len(files['ready'][name]):,} after")
        out(f"  grade5/questions.jsonl: {len(files['grade5']):,} questions")
        out(f"  tombstones: {len(a_rows):,} message ids (A); raw/{', raw/'.join(archives)} moved under grade5/raw/")
        if not go:
            return 0
        _write_grade5_db(con, polls_dir / "grade5" / "polls.db", b_rows, archives, engine)
        _write_jsonl(polls_dir / "grade5" / "questions.jsonl", files["grade5"])
        with open(polls_dir / "tombstones.jsonl", "a", encoding="utf-8") as f:
            for chat, msg_id in a_rows:
                f.write(json.dumps({"chat": chat, "msg_id": msg_id, "why": "A: non-CNS Year 2 (owner 2026-11-17)"}) + "\n")
        con.execute("BEGIN IMMEDIATE")
        try:
            for table in ("polls", "own"):
                con.executemany(f"DELETE FROM {table} WHERE chat=? AND msg_id=?", a_rows + b_rows)
            for chat in archives:
                con.execute("DELETE FROM own WHERE chat=?", (chat,))
                con.execute("DELETE FROM polls WHERE chat=?", (chat,))
                con.execute("DELETE FROM channels WHERE chat=?", (chat,))
            con.executemany("UPDATE polls SET status='need', claimed_by=NULL WHERE chat=? AND msg_id=? AND status='dupe'",
                            revote)
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        _write_jsonl(polls_dir / "ready" / "questions.jsonl", files["ready"]["questions"])
        _write_jsonl(polls_dir / "ready" / "held.jsonl", files["ready"]["held"])
        _write_jsonl(bank_dir / "questions.jsonl", files["bank"])
        _write_counts(bank_dir, files["bank"])
        for chat in archives:
            src = polls_dir / "raw" / chat
            if src.exists():
                dst = polls_dir / "grade5" / "raw" / chat
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
        _drop_from_config(config_path or ROOT / "config.json", archives)
        out("applied")
        return 0
    finally:
        con.close()


def _under_root(p):
    try:
        p.relative_to(ROOT)
        return True
    except ValueError:
        return False


def _count_own(con, rows):
    want = set(rows)
    return sum((chat, msg_id) in want for chat, msg_id in con.execute("SELECT chat, msg_id FROM own"))


def _write_grade5_db(con, path, rows, archives, engine):
    """polls.db rows, own votes and channel rows of the archive channels, in the polls.db schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    g = engine.db(path)
    want = set(rows)
    cols = [r[1] for r in con.execute("PRAGMA table_info(polls)")]
    g.execute("BEGIN")
    for r in con.execute(f"SELECT {', '.join(cols)} FROM polls"):
        if (r[0], r[1]) in want:
            g.execute(f"INSERT OR REPLACE INTO polls({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})", r)
    for r in con.execute("SELECT chat, msg_id, account, option, ts FROM own"):
        if r[0] in archives:
            g.execute("INSERT OR REPLACE INTO own VALUES(?,?,?,?,?)", r)
    for r in con.execute("SELECT chat, last_id, top_id FROM channels"):
        if r[0] in archives:
            g.execute("INSERT OR REPLACE INTO channels VALUES(?,?,?)", r)
    g.execute("COMMIT")
    g.close()


def _write_counts(bank_dir, rows):
    import importlib.util
    spec = importlib.util.spec_from_file_location("merge_apply", ROOT / "merge.py")
    merge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(merge)
    (bank_dir / "counts.json").write_text(json.dumps(merge.counts(rows), indent=1), encoding="utf-8")


def _drop_from_config(path, chats):
    if not path.exists():
        return
    """Takes the chats out of config.json `poll_channels` by a text edit (the rest of the file keeps its layout)."""
    import re
    text = path.read_text(encoding="utf-8")
    m = re.search(r'"poll_channels"\s*:\s*\{[^{}]*\}', text)
    if not m:
        return
    block = m.group(0)
    for chat in chats:
        q = re.escape(json.dumps(chat))
        block = re.sub(r"\s*" + q + r"\s*,", "", block)              # "chat", followed by more
        block = re.sub(r",\s*" + q + r"(?=\s*\])", "", block)         # last in its list
        block = re.sub(r"(?<=\[)\s*" + q + r"\s*(?=\])", "", block)   # alone in its list
    new = text[:m.start()] + block + text[m.end():]
    json.loads(new)                                                   # never write a broken config
    if new != text:
        path.write_text(new, encoding="utf-8")


def run(a):
    return apply(go=a.go)


def add(sub):
    p = sub.add_parser("apply", help="changes A and B (dry run unless --go)")
    p.add_argument("--go", action="store_true", help="apply; without it nothing is written")
    p.set_defaults(run=run)

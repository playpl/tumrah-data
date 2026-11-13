"""The owner's inbox (owner, 2026-11-10: "if I had to make any decisions, make it smooth for me").

Everything that needs the owner becomes one card on the admin page's Today screen, with the suggested answer first.
Nothing waits in a chat or a report. Rules:
- No card blocks the work: an undecided thing stays off the site ("not found" beats a guess) and the rest goes on.
- Asked once: an answer is kept (ledger.db `decisions`, `rules`); a card comes back only when its facts change.
- Every review answer is also a gold row (ledger.mark), so the error figures are measured, not estimated.

    py decisions.py [module]     refresh the cards, print their ids and titles (titles hold ids and counts only)
Question, book and transcript text passes from the files to the page; this file never prints it.
"""
import json
import random
import sys
import time
from pathlib import Path

import ledger
import lectures
import placement
import runners
from flows.common import read_jsonl

ROOT = Path(__file__).resolve().parent
SPOT_PER_DAY = 10


def _pages(spans):
    return ", ".join(f"{a}-{b}" if a != b else str(a) for a, b in spans) or "none"


def cards(module, db):
    """Today's cards from the facts: [{id, kind, title, detail, options, payload}]. The first option is the suggestion."""
    out = []
    h = runners.health()
    if not h["any"]:
        out.append({"id": "runner", "kind": "runner", "title": "No AI can work now",
                    "detail": f"Fleet: {h['fleet']['note'] or 'down'}. Web: {h['web']['note']}. Code steps still run; "
                              "readings, pointers and alignment wait.", "options": ["Check again"], "payload": {}})
    looks = placement.look(module)
    agree = [x for x in looks if x["verdict"] == "agree"]
    if agree:
        out.append({"id": "bounds_bulk", "kind": "bounds_bulk",
                    "title": f"{len(agree)} lesson places match the recording",
                    "detail": "The current pages and the reading of the recording agree, and no gate objects: "
                              + ", ".join(x["id"] for x in agree) + ". Accepting cuts each at its section starts.",
                    "options": [f"Accept all {len(agree)}", "Not now"],
                    "payload": {"spans": {x["id"]: x["spans"] for x in agree}}})
    for x in looks:
        if x["verdict"] != "differs":
            continue
        out.append({"id": f"bound:{x['id']}", "kind": "bound",
                    "title": f"{x['id']} {x['title']}: pages {_pages(x['pages'])}, the recording says {_pages(x['suggest_pages'])}",
                    "detail": f"{x['doctor']}. {'; '.join(x['flags'])}. Reading ({x['reader']}): from \"{x['from_title']}\" "
                              f"to \"{x['to_title']}\".",
                    "options": ["Use the reading", "Keep current pages", "Edit pages"],
                    "payload": {"lecture": x["id"], "spans": x["spans"], "pages": x["pages"]}})
    waits = [x for x in looks if x["verdict"] == "waits"]
    if waits:
        can = [x["id"] for x in waits if x["has_recording"]]
        out.append({"id": "waits", "kind": "waits", "title": f"{len(waits)} lesson places wait for a reading of the recording",
                    "detail": f"{len(can)} have a transcript and can be read now; {len(waits) - len(can)} have no transcript yet. "
                              "Until then they keep their current pages, unconfirmed.",
                    "options": ["Read them now", "Later"], "payload": {"n": len(waits), "can": len(can)}})
    n = db.execute("SELECT COUNT(DISTINCT src) FROM links WHERE module=? AND kind='question' AND state='conflict'",
                   (module,)).fetchone()[0]
    if n:
        out.append({"id": "conflicts", "kind": "review", "title": f"{n} questions where two readers chose different lines",
                    "detail": "Both choices are shown on the handout. Your pick is final, and it scores both readers.",
                    "options": ["Review them", "Later"], "payload": {"review": "conflict", "n": n}})
    left = len(spot_items(module, db, peek=True))
    if left:
        out.append({"id": f"spot:{time.strftime('%Y-%m-%d')}", "kind": "review",
                    "title": f"Spot check: {left} links, about {max(1, left // 5)} minutes",
                    "detail": "Right or wrong on each. This is what makes the error figure a measured one.",
                    "options": ["Start", "Skip today"], "payload": {"review": "spot", "n": left}})
    import doctors_folder
    for d in sorted(p for m in doctors_folder.DOCTORS.glob("*/*") for p in m.iterdir() if p.is_dir()):
        key = doctors_folder.key_of(d.name)
        if not doctors_folder.ALIASES.get(key) and not rule(db, f"alias:{key}"):
            out.append({"id": f"doctor:{key}", "kind": "doctor", "title": f"{key} has no doctor on the site",
                        "detail": "Type the site doctor id (like dr-name-subj). Asked once: it becomes a rule for every "
                                  "later file. Until then this doctor's files stay held.",
                        "options": ["Set site doctor", "Keep held"], "payload": {"key": key, "input": "site doctor id"}})
    cf = ROOT / "bank" / "counts.json"
    kf = ROOT / "bank" / "key_decisions.json"
    conflicts = (json.loads(cf.read_text(encoding="utf-8")).get("key_conflicts") or 0) if cf.exists() else 0
    decided = len(json.loads(kf.read_text(encoding="utf-8"))) if kf.exists() else 0
    if conflicts > decided:
        out.append({"id": "keys", "kind": "open", "title": f"{conflicts - decided} answer-key conflicts",
                    "detail": "Two sources give different keys. Never settled by an AI: they stay off the site until you pick.",
                    "options": ["Open", "Keep held"], "payload": {"tab": "Polls"}})
    return out


def refresh(module=ledger.MODULE, db=None):
    """Writes today's cards. An answered card stays answered unless its facts (payload) changed; a card whose reason
    is gone is closed. Returns the open cards."""
    own = db is None
    db = db or ledger.connect()
    now = {c["id"]: c for c in cards(module, db)}
    old = {r["id"]: r for r in db.execute("SELECT * FROM decisions")}
    for cid, c in now.items():
        payload = json.dumps(c["payload"], sort_keys=True)
        o = old.get(cid)
        if o and o["payload"] == payload and o["state"] != "gone":
            db.execute("UPDATE decisions SET title=?, detail=?, options=? WHERE id=?",
                       (c["title"], c["detail"], json.dumps(c["options"]), cid))
            continue
        db.execute("INSERT OR REPLACE INTO decisions(id, kind, title, detail, options, payload, state, answer, at) "
                   "VALUES(?,?,?,?,?,?,'open',NULL,?)",
                   (cid, c["kind"], c["title"], c["detail"], json.dumps(c["options"]), payload, time.time()))
    for cid, o in old.items():
        if cid not in now and o["state"] == "open":
            db.execute("UPDATE decisions SET state='gone' WHERE id=?", (cid,))
    db.commit()
    rows = [dict(r) for r in db.execute("SELECT * FROM decisions WHERE state='open' ORDER BY at")]
    if own:
        db.close()
    for r in rows:
        r["options"], r["payload"] = json.loads(r["options"]), json.loads(r["payload"])
    order = ["runner", "bounds_bulk", "bound", "waits", "review", "doctor", "open"]
    return sorted(rows, key=lambda r: order.index(r["kind"]) if r["kind"] in order else 99)


def rule(db, key):
    r = db.execute("SELECT value FROM rules WHERE key=?", (key,)).fetchone()
    return r["value"] if r else None


def rules(prefix, db=None):
    """{key without the prefix: value}: the owner's standing answers (doctors_folder reads `alias:`)."""
    own = db is None
    db = db or ledger.connect()
    out = {r["key"][len(prefix):]: r["value"] for r in db.execute("SELECT key, value FROM rules WHERE key LIKE ?", (prefix + "%",))}
    if own:
        db.close()
    return out


def answer(card_id, choice, value=None, module=ledger.MODULE):
    """The owner clicked option number `choice` (0 = the suggestion) on a card. Returns {done, message, open}."""
    db = ledger.connect()
    c = db.execute("SELECT * FROM decisions WHERE id=?", (card_id,)).fetchone()
    if c is None or c["state"] != "open":
        db.close()
        return {"error": "that card is no longer open"}
    p, kind, msg, state = json.loads(c["payload"]), c["kind"], "", "done" if choice == 0 else "skipped"
    if kind == "bounds_bulk" and choice == 0:
        for lid, spans in p["spans"].items():
            placement.apply(lid, spans)
        msg = f"{len(p['spans'])} lesson places confirmed"
    elif kind == "bound" and choice == 0:
        msg = f"{p['lecture']} now on pages {_pages(placement.apply(p['lecture'], p['spans']))}"
    elif kind == "bound" and choice == 1:
        meta = lectures.load(p["lecture"])
        meta["placed_by"] = "owner"
        lectures.save(meta)
        msg, state = f"{p['lecture']} keeps its pages, confirmed by you", "done"
    elif kind == "bound":
        db.close()
        return {"open": "Lectures", "lecture": p["lecture"]}  # edited there by hand; the card closes when the facts change
    elif kind == "waits" and choice == 0:
        db.close()
        return {"run": "ai"}  # the page starts runners.run_ai in the background; the card stays until readings arrive
    elif kind == "doctor" and choice == 0:
        if not (value or "").strip():
            db.close()
            return {"error": "type the site doctor id first"}
        db.execute("INSERT OR REPLACE INTO rules(key, value, at) VALUES(?,?,?)", (f"alias:{p['key']}", value.strip(), time.time()))
        import doctors_folder
        doctors_folder.ALIASES[p["key"]] = value.strip()  # this process now; a new process reads it in owner_aliases
        msg = f"{p['key']} is {value.strip()} from now on"
    elif kind in ("review", "open") and choice == 0:
        db.close()
        return {"review": p["review"]} if kind == "review" else {"open": p["tab"]}
    elif kind == "runner":
        runners._CACHE["at"] = 0
        state = "open"
    db.execute("UPDATE decisions SET state=?, answer=?, at=? WHERE id=?", (state, json.dumps([choice, value]), time.time(), card_id))
    db.commit()
    db.close()
    return {"done": True, "message": msg}


# ---- review: conflicts and the daily spot check -------------------------------------------------------------------------
def spot_items(module, db, n=SPOT_PER_DAY, peek=False):
    """Today's sample: links nobody checked, spread over the (kind, reader) classes, the same all day (seeded by date).
    Checked ones drop out, so the list shrinks to nothing as the owner goes."""
    day = time.strftime("%Y-%m-%d")
    done = db.execute("SELECT COUNT(*) FROM gold WHERE date(at, 'unixepoch', 'localtime')=?", (day,)).fetchone()[0]
    want = max(0, n - done)
    rows = db.execute(
        "SELECT l.kind, l.src, l.runner, l.lines FROM links l LEFT JOIN gold g ON g.kind=l.kind AND g.src=l.src AND "
        "g.runner=l.runner WHERE l.module=? AND l.kind IN ('question','block','part') AND l.found=1 AND "
        "l.state IN ('proposed','agreed') AND g.src IS NULL ORDER BY l.kind, l.src, l.runner", (module,)).fetchall()
    by = {}
    for r in rows:
        by.setdefault((r["kind"], r["runner"]), []).append(r)
    rnd = random.Random(day)
    for v in by.values():
        rnd.shuffle(v)
    out, classes = [], sorted(by)
    while len(out) < want and any(by[c] for c in classes):
        for c in classes:
            if by[c] and len(out) < want:
                out.append(by[c].pop())
    return out if peek else [_item(module, r["kind"], r["src"], [r]) for r in out]


def conflict_items(module, db, limit=20):
    srcs = [r["src"] for r in db.execute("SELECT DISTINCT src FROM links WHERE module=? AND kind='question' AND "
                                         "state='conflict' ORDER BY src LIMIT ?", (module, limit))]
    return [_item(module, "question", s, db.execute(
        "SELECT kind, src, runner, lines FROM links WHERE kind='question' AND src=? AND state='conflict'", (s,)).fetchall())
        for s in srcs]


_TEXT = {"mtime": None, "lines": {}}


def _lines(module):
    f = ROOT / "modules" / module / "lines.jsonl"
    if _TEXT["mtime"] != f.stat().st_mtime:
        _TEXT.update(mtime=f.stat().st_mtime, lines={ln["id"]: ln for ln in read_jsonl(f)})
    return _TEXT["lines"]


def _source(module, kind, src):
    """What the owner must see to judge a link: the question, the book block or the lecture part (text for the page)."""
    if kind == "question":
        with open(ROOT / "bank" / "questions.jsonl", encoding="utf-8") as f:
            for line in f:
                if src in line:
                    q = json.loads(line)
                    if q["word_key"] == src:
                        return {"question": q["question"], "options": q["options"], "key": q.get("key")}
        return {"question": f"(not in the bank: {src})", "options": [], "key": None}
    if kind == "block":
        book, page, n = src.rsplit(":", 2)
        for f in (ROOT / "jobs" / "books").glob(f"{module}-{book}-p*/aligned.jsonl"):
            for row in read_jsonl(f):
                if str(row["page"]) == page:
                    b = next((b for b in row["blocks"] if str(b["n"]) == n), None)
                    if b:
                        return {"book": book, "page": int(page), "text": b["text"], "match": b.get("match")}
        return {"book": book, "page": page, "text": "(block text not found)"}
    lid, part = src.split(":")
    f = lectures.folder(lid) / "links.jsonl"
    r = next((r for r in read_jsonl(f) if f"{r['part']}.{r.get('sub', 0)}" == part), {}) if f.exists() else {}
    return {"lecture": lid, "title": r.get("title"), "start": r.get("start"), "end": r.get("end")}


def _item(module, kind, src, rows):
    lines = _lines(module)
    return {"kind": kind, "src": src, "source": _source(module, kind, src),
            "choices": [{"runner": r["runner"], "lines": [
                {"page": lines[i]["page"], "text": lines[i].get("text") or f"[FIGURE: {lines[i].get('figure')}]"}
                for i in json.loads(r["lines"]) if i in lines]} for r in rows]}


def review_answer(kind, src, pick, module=ledger.MODULE):
    """Spot check: pick = {"runner": r, "right": bool}. Conflict: pick = {"runner": r} (that reader was right) or
    {"runner": None} (neither). The owner's pick becomes an owner row; every reader is scored."""
    db = ledger.connect()
    rows = db.execute("SELECT runner, lines, state FROM links WHERE kind=? AND src=?", (kind, src)).fetchall()
    if "right" in pick:
        ledger.mark(db, kind, src, pick["runner"], bool(pick["right"]))
    else:
        for r in rows:
            if r["state"] == "conflict":
                ledger.mark(db, kind, src, r["runner"], r["runner"] == pick["runner"])
        chosen = next((r for r in rows if r["runner"] == pick["runner"]), None)
        if chosen:
            ledger.put(db, module, kind, src, "owner", json.loads(chosen["lines"]), scope="owner pick")
            db.commit()
    db.close()
    return {"saved": True}


def review_items(kind, module=ledger.MODULE):
    db = ledger.connect()
    out = conflict_items(module, db) if kind == "conflict" else spot_items(module, db)
    db.close()
    return out


# ---- the Today screen -------------------------------------------------------------------------------------------------
_SYNC = {"at": 0.0}


def today(module=ledger.MODULE, sync_age=600):
    """Everything the Today screen shows: who can work, what is ready, the measured error, the steps, the cards and the
    import report. The ledger is re-read from the flows' files at most every `sync_age` seconds."""
    import sqlite3
    db = ledger.connect()
    if time.time() - _SYNC["at"] > sync_age:
        ledger.sync(module, db)
        _SYNC["at"] = time.time()
    open_cards = refresh(module, db)
    one = lambda sql, *a: db.execute(sql, a).fetchone()[0]  # noqa: E731
    ready = {k: len(ledger.ready(db, module, k)) for k in ("question", "block", "part")}
    checked, wrong = one("SELECT COUNT(*) FROM gold"), one("SELECT COALESCE(SUM(verdict='wrong'), 0) FROM gold")
    rate, low, high = ledger.wilson(wrong, checked)
    found = one("SELECT COUNT(DISTINCT kind || src) FROM links WHERE module=? AND kind!='lesson' AND found=1", module)
    held = one("SELECT COUNT(DISTINCT kind || src) FROM links WHERE module=? AND state IN ('conflict','rejected')", module)
    metas = lectures.all_lectures(module)
    lec = [m for m in metas if m.get("kind", "lecture") == "lecture"]
    has = lambda m, name: (lectures.folder(m["id"]) / name).exists()  # noqa: E731
    owner = sum(m.get("placed_by") == "owner" for m in lec)
    books = {"passed": 0, "all": 0}
    qdb = ROOT / "queue.db"
    if qdb.exists():
        q = sqlite3.connect(qdb)
        for status, n in q.execute("SELECT status, COUNT(*) FROM jobs WHERE flow='books' GROUP BY status"):
            books["all"] += n
            books["passed"] += n if status == "passed" else 0
        q.close()
    ai_q = one("SELECT COUNT(DISTINCT src) FROM links WHERE module=? AND kind='question' AND runner!='script'", module)
    all_q = one("SELECT COUNT(DISTINCT src) FROM links WHERE module=? AND kind='question'", module)
    recorded = [m for m in metas if m.get("source")]
    pipeline = [
        {"name": "Transcribe", "text": f"{sum(has(m, 'raw.txt') for m in recorded)} of {len(recorded)}"},
        {"name": "Place", "text": f"{owner} of {len(lec)} confirmed", "warn": owner < len(lec)},
        {"name": "Point", "text": f"{ai_q} of {all_q} read by an AI", "warn": ai_q < all_q},
        {"name": "Align books", "text": f"{books['passed']} of {books['all']} jobs"},
        {"name": "Link lectures", "text": f"{sum(has(m, 'links.jsonl') for m in recorded)} of {sum(has(m, 'raw.txt') for m in recorded)}"},
        {"name": "Spot checks", "text": f"{checked} done"},
    ]
    rule = ledger.ready_rule()
    errs = ledger.errors(db)
    report = [f"{module}, {time.strftime('%Y-%m-%d %H:%M')}. Ready = agreed by two readers, set by the owner, or from a reader "
              f"whose spot checks show at most {round(100 * rule['max_error'])}% wrong over {rule['min_checked']} or more checks.",
              f"Lesson places confirmed by the owner: {owner} of {len(lec)}.",
              *[f"{k}: {n} ready." for k, n in ready.items()],
              f"Held (two readers disagree, or marked wrong): {held}. Not checked yet: {found - sum(ready.values()) - held}.",
              *[f"Measured, {k} by {r}: {e['wrong']} wrong of {e['checked']} ({round(100 * e['low'])}-{round(100 * e['high'])}% at 95%)."
                for (k, r), e in sorted(errs.items())],
              "Site files take the ready readings on the next `py fast_lessons.py build`. Nothing is sent to the site from here."]
    db.close()
    return {"module": module, "runner": runners.health(),
            "metrics": {"ready": sum(ready.values()), "unchecked": found - sum(ready.values()) - held, "held": held,
                        "error": {"checked": checked, "wrong": wrong, "rate": rate, "low": low, "high": high}},
            "pipeline": pipeline, "cards": open_cards, "report": "\n".join(report)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for c in refresh(sys.argv[1] if len(sys.argv) > 1 else ledger.MODULE):
        print(c["id"], "|", c["kind"], "|", c["title"] if c["kind"] != "bound" else c["id"])

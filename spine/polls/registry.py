"""The polls channel registry and a read-only inventory of what the polls stores hold.

    py -m spine polls inventory      counts per channel x module, and exactly what the two owner-ordered
                                     changes would touch. Reads only; nothing is written or deleted.

Registry: `polls/channels.json` (university, batch, year, role, grade, harvest, seed_old, drop_modules, store).
It describes the state the owner ordered on 2026-11-16; `polls/engine.py` still reads its own CHANNELS until
the changes are applied:
  A. Batch58ATM (Year 2 backbone): polls labelled as non-CNS Year 2 are deleted for good. CNS, unlabelled and
     Year-1-labelled polls stay (the labels were made by the fleet, not by the owner).
  B. zagpolls58 (Year 1 archive): its questions leave the live bank for the grade 5 store. A question also
     seen in a backbone channel stays with the backbone.
"""
import json
import sqlite3
from collections import Counter

from spine import ROOT, read_json, read_jsonl

POLLS, BANK = ROOT / "polls", ROOT / "bank"
REGISTRY = POLLS / "channels.json"
UNLABELLED = "(no label)"


def channels():
    return read_json(REGISTRY, [])


def channel(chat):
    return next((c for c in channels() if c["chat"] == chat), None)


def _stream(path):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def plan(row, module, reg):
    """What the ordered changes do to one bank question: "keep", "delete" (A), "grade5" (B) or "trim" (it stays,
    but loses its sightings in a dropped or archived channel). Returns (verdict, poll chats it is seen in, also seen in
    a quiz, form or MCQ book)."""
    polls = [s for s in row.get("sightings", []) if s.get("source", "poll") == "poll"]
    others = [s for s in row.get("sightings", []) if s.get("source", "poll") != "poll"]   # quiz bots, forms, MCQ books
    chats = {s["chat"] for s in polls}
    left = set(chats)
    for c in reg:
        if c["chat"] in left and module in c.get("drop_modules", []):
            left.discard(c["chat"])
    dropped = left != chats
    archives = {c["chat"] for c in reg if c.get("role") == "archive"}
    if dropped and not left and not others:
        return "delete", chats, False
    if left and left <= archives and not others:
        return "grade5", chats, False
    if dropped or (left & archives):
        return "trim", chats, bool(others)
    return "keep", chats, bool(others)


def inventory(polls_dir=POLLS, bank_dir=BANK, reg=None):
    """Counts as nested dicts. Opens every store read-only."""
    reg = channels() if reg is None else reg
    labels = {r["word_key"]: r.get("module") or UNLABELLED for r in _stream(bank_dir / "labels.jsonl")}
    out = {"db": Counter(), "db_status": Counter(), "own": Counter(), "raw": Counter(), "bank": Counter(),
           "bank_plan": Counter(), "bank_total": 0, "ready": Counter(), "ready_total": 0, "db_plan": Counter(),
           "own_plan": Counter(), "surprises": Counter()}
    drop = {c["chat"]: set(c.get("drop_modules", [])) for c in reg}
    archives = {c["chat"] for c in reg if c.get("role") == "archive"}
    verdict_of = {}
    for row in _stream(bank_dir / "questions.jsonl"):
        out["bank_total"] += 1
        module = labels.get(row["word_key"], UNLABELLED)
        verdict, chats, other = plan(row, module, reg)
        verdict_of[row["word_key"]] = verdict
        key = "+".join(sorted(chats) + (["quiz/form/book"] if other else [])) or "(not a poll)"
        out["bank"][(key, module)] += 1
        out["bank_plan"][(verdict, key, module)] += 1
        if verdict in ("grade5", "trim") and chats & archives and module.startswith("year2"):
            out["surprises"][f"archive question labelled {module} ({verdict})"] += 1
    db = polls_dir / "polls.db"
    if db.exists():
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        doomed = set()
        for chat, msg_id, wk, status in con.execute("SELECT chat, msg_id, word_key, status FROM polls"):
            module = labels.get(wk, UNLABELLED)
            out["db"][(chat, module)] += 1
            out["db_status"][(chat, status)] += 1
            if module in drop.get(chat, ()):
                out["db_plan"][("delete", chat, module)] += 1
                doomed.add((chat, msg_id))
            elif chat in archives:
                out["db_plan"][("grade5", chat, module)] += 1
                doomed.add((chat, msg_id))
        for chat, msg_id in con.execute("SELECT chat, msg_id FROM own"):
            out["own"][chat] += 1
            if (chat, msg_id) in doomed:
                out["own_plan"][chat] += 1
        con.close()
    for d in sorted((polls_dir / "raw").glob("*/messages.jsonl")):
        with open(d, encoding="utf-8") as f:
            out["raw"][d.parent.name] = sum(1 for _ in f)
    ready = polls_dir / "ready" / "questions.jsonl"
    if ready.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("polls_engine", polls_dir / "engine.py")
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
        for row in _stream(ready):
            out["ready_total"] += 1
            wk = engine.word_key(row["question"], row["options"])
            out["ready"][(verdict_of.get(wk, "not in bank"), labels.get(wk, UNLABELLED))] += 1
    return out


def report(inv, reg=None):
    """The inventory as text a person can read."""
    reg = channels() if reg is None else reg
    lines = ["POLLS INVENTORY (read-only; nothing was changed)", ""]
    lines.append("Channels (polls/channels.json):")
    for c in reg:
        lines.append(f"  {c['chat']:<13} {c['university']} batch {c['batch']}, year {c['year']} {c['role']}, grade "
                     f"{c['grade']}, harvest {'yes' if c['harvest'] else 'no'}"
                     + (f", drops {', '.join(c['drop_modules'])}" if c.get("drop_modules") else "")
                     + (f", store {c['store']}" if c.get("store") else ""))
    chats = [c["chat"] for c in reg]
    modules = sorted({m for _, m in inv["db"]})
    lines += ["", "polls.db rows, channel x label:"]
    for chat in chats:
        lines.append(f"  {chat}: {sum(n for (c, _), n in inv['db'].items() if c == chat):,} rows; "
                     + ", ".join(f"{s} {n:,}" for (c, s), n in sorted(inv["db_status"].items()) if c == chat)
                     + f"; own votes {inv['own'][chat]:,}; raw messages {inv['raw'][chat]:,}")
        for m in modules:
            if inv["db"][(chat, m)]:
                lines.append(f"      {m:<36} {inv['db'][(chat, m)]:>7,}")
    lines += ["", f"bank/questions.jsonl: {inv['bank_total']:,} questions, seen in x label:"]
    for (key, m), n in sorted(inv["bank"].items()):
        lines.append(f"  {key:<42} {m:<36} {n:>7,}")
    lines += ["", f"polls/ready/questions.jsonl: {inv['ready_total']:,} questions"]

    def total(counter, verdict, pick=lambda k: True):
        return sum(n for k, n in counter.items() if k[0] == verdict and pick(k))

    lines += ["", "CHANGE A: delete the non-CNS Year 2 polls of Batch58ATM (for good, no archive)"]
    for (v, chat, m), n in sorted(inv["db_plan"].items()):
        if v == "delete":
            lines.append(f"  polls.db   {chat} {m:<36} {n:>7,} rows")
    lines.append(f"  own votes of those rows: {sum(inv['own_plan'][c['chat']] for c in reg if c.get('drop_modules')):,}")
    lines.append(f"  bank questions deleted: {total(inv['bank_plan'], 'delete'):,}")
    for (v, key, m), n in sorted(inv["bank_plan"].items()):
        if v == "delete":
            lines.append(f"      seen in {key:<40} {m:<36} {n:>7,}")
    lines.append(f"  ready questions deleted: {total(inv['ready'], 'delete'):,}")
    lines += ["", "CHANGE B: move zagpolls58 (Year 1 archive) to the grade 5 store; nothing destroyed"]
    for (v, chat, m), n in sorted(inv["db_plan"].items()):
        if v == "grade5":
            lines.append(f"  polls.db   {chat} {m:<36} {n:>7,} rows")
    lines.append(f"  bank questions moved to grade 5: {total(inv['bank_plan'], 'grade5'):,}")
    for (v, key, m), n in sorted(inv["bank_plan"].items()):
        if v == "grade5":
            lines.append(f"      seen in {key:<40} {m:<36} {n:>7,}")
    lines.append(f"  ready questions moved to grade 5: {total(inv['ready'], 'grade5'):,}")
    lines += ["", f"Questions that stay but lose a sighting (repeated in a kept channel or in a quiz, form or book): "
                  f"{total(inv['bank_plan'], 'trim'):,}"]
    for (v, key, m), n in sorted(inv["bank_plan"].items()):
        if v == "trim":
            lines.append(f"      seen in {key:<40} {m:<36} {n:>7,}")
    lines += ["", f"Kept untouched: {total(inv['bank_plan'], 'keep'):,} bank questions"]
    if inv["surprises"]:
        lines += ["", "LOOK AT THIS BEFORE APPLYING:"] + [f"  {k}: {n:,}" for k, n in sorted(inv["surprises"].items())]
    return "\n".join(lines)

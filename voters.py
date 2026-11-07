"""Voters update (owner, 2026-11-07): re-read the vote counts of every keyed poll, without voting, and push the new
totals to the site's importer-owned `stats`.

Read only on Telegram: each poll is re-read by an account that already voted on it (results show only to voters),
our own votes are taken out (`net`), reposts add up in the bank, and the site gets attempts = net voters and
correct = net votes on the key. A key is never changed here; a poll whose key now reads differently is counted.

    py dm.py voters            refresh, rebuild, dry-run the site import, print the report
    py dm.py voters --apply    the same, then write `stats` on the site (undo file first)
"""
import asyncio
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "polls"))
import engine  # noqa: E402

BATCH = 100


def owners(c):
    """(chat, msg_id) -> an account that voted on that poll, else the scanner."""
    out = {}
    for r in c.execute("SELECT chat, msg_id, account FROM own"):
        if r["account"] != "old":
            out.setdefault((r["chat"], r["msg_id"]), r["account"])
    return out


def plan(c):
    """account -> chat -> [msg_id] for every keyed poll in a live channel."""
    who = owners(c)
    todo = defaultdict(lambda: defaultdict(list))
    for r in c.execute("SELECT chat, msg_id FROM polls WHERE status='keyed'"):
        if r["chat"] in engine.CHANNELS:
            todo[who.get((r["chat"], r["msg_id"]), engine.SCANNER)][r["chat"]].append(r["msg_id"])
    return todo


def apply_read(c, chat, mid, got, report):
    """Store new counts for one poll; never its key."""
    row = c.execute("SELECT key, votes, total, seen FROM polls WHERE chat=? AND msg_id=?", (chat, mid)).fetchone()
    if not row or got["votes"] is None:
        report["no_results"] += 1
        return
    report["read"] += 1
    if got["key"] is not None and row["key"] is not None and got["key"] != row["key"]:
        report["key_reads_differently"] += 1
    own = [(r["option"], r["ts"]) for r in c.execute("SELECT option, ts FROM own WHERE chat=? AND msg_id=?", (chat, mid))]
    before = engine.net(json.loads(row["votes"]), row["total"], own, row["seen"])[1] if row["votes"] else 0
    now = time.time()
    after = engine.net(got["votes"], got["total"], own, now)[1]
    if after != before:
        report["polls_changed"] += 1
        report["new_voters"] += max(0, after - before)
    c.execute("UPDATE polls SET votes=?, total=?, seen=? WHERE chat=? AND msg_id=?",
              (json.dumps(got["votes"]), got["total"], now, chat, mid))


async def refresh(c, connect, report):
    for account, chats in plan(c).items():
        client = await connect(account)
        try:
            ents = {d.entity.username: d.entity async for d in client.iter_dialogs()
                    if getattr(d.entity, "username", None) in chats}
            for chat, ids in chats.items():
                if chat not in ents:
                    report["skipped_not_member"] += len(ids)
                    continue
                for i in range(0, len(ids), BATCH):
                    for msg in await client.get_messages(ents[chat], ids=ids[i:i + BATCH]):
                        if msg and hasattr(getattr(msg, "media", None), "poll"):
                            apply_read(c, chat, msg.id, engine.read_results(msg.media.poll, msg.media.results), report)
                        else:
                            report["gone"] += 1
                    await asyncio.sleep(1)
        finally:
            await client.disconnect()


def site_stats(bank_rows, site_index):
    """Bank questions found on the site -> importer rows {question_id, attempts, correct}."""
    out = []
    for q in bank_rows:
        sid = site_index.get(q["word_key"])
        if sid and q["key"] is not None and q["total"] > 0 and not q["key_conflict"]:
            out.append({"question_id": sid, "attempts": q["total"], "correct": q["votes"][q["key"]]})
    return out


def run(apply=False):
    import cover
    import db
    import merge
    c = engine.db()
    if engine.status(c)["running"]:
        sys.exit("the polls job is running and holds the sessions: try again when it is done")
    sys.path[:0] = [str(engine.TELEGRAM / "quizbot"), str(engine.TELEGRAM), str(engine.OLD)]
    import tg as telegram
    report = defaultdict(int)
    asyncio.run(refresh(c, telegram.connect, report))
    engine.build_ready(c)
    merge.build()
    rows = site_stats(merge.read_jsonl(ROOT / "bank" / "questions.jsonl"), cover.site_index(db.Reader.live()))
    out = ROOT / "bank" / "stats.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    report["site_questions"] = len(rows)
    backend = Path(r"C:\Users\Ahmed\Desktop\tumrah\backend")
    dns = ROOT / "tools_dns.cjs"
    dns.write_text('require("dns").setServers(["1.1.1.1"]);\n', encoding="utf-8")
    cmd = ["node", "../node_modules/tsx/dist/cli.mjs", "src/scripts/importHubData.ts", "stats", "--file", str(out),
           "--source", "voters-" + time.strftime("%Y-%m-%d")] + (["--apply"] if apply else [])
    res = subprocess.run(cmd, cwd=backend, capture_output=True, text=True, env={**os.environ,
                                                                  "NODE_OPTIONS": f"--require {dns}"})
    report["site_import"] = (res.stdout.strip().splitlines() or [res.stderr.strip()[-300:]])[-1]
    return dict(report)

"""Polls job: scrape the channels, vote for keys on every account, top up, then write ready data.

Order: a first scrape lists the polls, every account votes (one vote per distinct question, the vote shows the key),
a last scrape picks up polls posted meanwhile, and polls/ready/ gets the result. Start again resumes where it stopped.

Keys come only from Telegram's correct flag, read per account right after its vote: a quiz hides its results from
accounts that did not vote, so a later scrape cannot read them. Our own votes never count: every vote goes in the
`own` table and net() takes it out of the counts (owner, 2026-11-06).

Run with Python 3.13: python polls/engine.py   (polls/control.py does this from the page)
"""
import asyncio
import json
import random
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

HOME = Path(__file__).resolve().parent
DB, RAW, READY, STOP = HOME / "polls.db", HOME / "raw", HOME / "ready", HOME / "stop.flag"
OLD = Path(r"C:\Users\Ahmed\Desktop\tumrah for med\telegram_raw_export_2026-10-12")
TELEGRAM = Path(r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram")
REGISTRY, TOMBSTONES = HOME / "channels.json", HOME / "tombstones.jsonl"


def load_channels(path=REGISTRY):
    """({chat: channel id} of the harvested channels in voting order, chats whose old vote-job keys are seeded).
    polls/channels.json is the registry (owner, 2026-11-16/17): `harvest` false = not scraped or voted (zagpolls58
    went to the grade 5 store), `vote` = voting order (Batch58ATM first), `seed_old` = seed_old_keys reads it."""
    reg = json.loads(path.read_text(encoding="utf-8"))
    live = sorted((c for c in reg if c.get("harvest")), key=lambda c: c.get("vote", 99))
    return {c["chat"]: c["chat_id"] for c in live}, {c["chat"] for c in live if c.get("seed_old")}


def tombstones(path=TOMBSTONES):
    """{(chat, msg_id)} deleted for good (change A, owner 2026-11-17): a scrape never lists them again."""
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {(r["chat"], r["msg_id"]) for r in map(json.loads, filter(str.strip, f))}


CHANNELS, SEED_OLD = load_channels()  # voting order
SCANNER = "scraper"  # it voted the most in past rounds, so its scrape reads the most keys for free
BATCH, MAX_INTERVAL, MAX_NO_FLAG = 20, 60.0, 100

SCHEMA = """
CREATE TABLE IF NOT EXISTS polls(chat TEXT, msg_id INTEGER, word_key TEXT, status TEXT DEFAULT 'need', claimed_by TEXT,
  key INTEGER, solution TEXT, votes TEXT, total INTEGER, seen REAL, note TEXT, PRIMARY KEY(chat, msg_id));
CREATE INDEX IF NOT EXISTS polls_status ON polls(status);
CREATE INDEX IF NOT EXISTS polls_word ON polls(word_key);
CREATE TABLE IF NOT EXISTS own(chat TEXT, msg_id INTEGER, account TEXT, option INTEGER, ts REAL,
  PRIMARY KEY(chat, msg_id, account));
CREATE INDEX IF NOT EXISTS own_ts ON own(ts);
CREATE TABLE IF NOT EXISTS channels(chat TEXT PRIMARY KEY, last_id INTEGER DEFAULT 0, top_id INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS accounts(label TEXT PRIMARY KEY, state TEXT, channels INTEGER DEFAULT 0,
  votes INTEGER DEFAULT 0, floods INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS state(k TEXT PRIMARY KEY, v TEXT);
"""

NUMBERING = re.compile(r"^\s*(?:(?:Q\s*\.?\s*\d+|\(\s*\d+\s*\)|\d+)\s*[:.)\-–]\s+|Q\s*\d+\s*[:.)]\s*)", re.I)
LABEL = re.compile(r"^\s*[A-Fa-f][).]\s*")
CHANNEL_ORDER = " ".join(f"WHEN '{name}' THEN {i}" for i, name in enumerate(CHANNELS))


def db(path=None):
    c = sqlite3.connect(path or DB, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.executescript(SCHEMA)
    return c


def get(c, k, default=None):
    row = c.execute("SELECT v FROM state WHERE k=?", (k,)).fetchone()
    return row["v"] if row else default


def put(c, k, v):
    c.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (k, str(v)))


def words(text):
    """Letters, marks and digits, as `words` in importSfQuestions.ts."""
    return "".join(ch for ch in NUMBERING.sub("", text or "").lower() if unicodedata.category(ch)[0] in "LMN")


def option_word(text):
    return words(LABEL.sub("", text or ""))


def word_key(stem, options):
    """The zero-lossy duplicate key of `wordKey` in importSfQuestions.ts."""
    return f"{words(stem)}#{'|'.join(sorted(option_word(o) for o in options))}"


def read_results(poll, res):
    """Key, vote split and this account's own choice, mapped by option bytes (result order can differ)."""
    rows = {r.option: r for r in (res.results or [])} if res else {}
    index = {a.option: i for i, a in enumerate(poll.answers)}
    return {"key": next((index[o] for o, r in rows.items() if getattr(r, "correct", False) and o in index), None),
            "chosen": next((index[o] for o, r in rows.items() if getattr(r, "chosen", False) and o in index), None),
            "votes": [rows[a.option].voters if a.option in rows else 0 for a in poll.answers] if rows else None,
            "total": res.total_voters if res else 0,
            "solution": getattr(res, "solution", None) or None}


def net(votes, total, own, seen):
    """Counts without our votes. `own`: (option, ts); a vote cast after the snapshot `seen` is not in it."""
    votes = list(votes)
    for option, ts in own:
        if ts <= seen:
            if 0 <= option < len(votes):
                votes[option] = max(0, votes[option] - 1)
            total -= 1
    return votes, max(0, total)


def add_own(c, chat, msg_id, account, option, ts):
    c.execute("INSERT OR IGNORE INTO own VALUES(?,?,?,?,?)", (chat, msg_id, account, option, ts))


def claim(c, label, chats, n=BATCH):
    """Up to n polls for one account, in channel order, newest first. One transaction, so no poll has two owners."""
    marks = ",".join("?" * len(chats))
    c.execute("BEGIN IMMEDIATE")
    rows = c.execute(f"SELECT chat, msg_id FROM polls WHERE status='need' AND chat IN ({marks}) "
                     f"ORDER BY CASE chat {CHANNEL_ORDER} END, msg_id DESC LIMIT ?", (*chats, n)).fetchall()
    c.executemany("UPDATE polls SET status='claimed', claimed_by=? WHERE chat=? AND msg_id=?",
                  [(label, r["chat"], r["msg_id"]) for r in rows])
    c.execute("COMMIT")
    return [(r["chat"], r["msg_id"]) for r in rows]


def release(c, label=None):
    c.execute("UPDATE polls SET status='need', claimed_by=NULL WHERE status='claimed' AND (?1 IS NULL OR claimed_by=?1)",
              (label,))


def save(c, chat, msg_id, got, status):
    c.execute("UPDATE polls SET status=?, claimed_by=NULL, key=?, solution=?, votes=?, total=?, seen=? "
              "WHERE chat=? AND msg_id=?",
              (status, got["key"], got["solution"], json.dumps(got["votes"]) if got["votes"] else None, got["total"],
               time.time(), chat, msg_id))


def mark_dupes(c):
    """One vote per distinct question: a question with a key needs no vote, and of the others one posting gets it."""
    c.execute("BEGIN IMMEDIATE")
    c.execute("UPDATE polls SET status='dupe' WHERE status='need' "
              "AND word_key IN (SELECT word_key FROM polls WHERE status='keyed')")
    seen = set()
    for r in c.execute(f"SELECT chat, msg_id, word_key FROM polls WHERE status='need' "
                       f"ORDER BY CASE chat {CHANNEL_ORDER} END, msg_id DESC").fetchall():
        if r["word_key"] in seen:
            c.execute("UPDATE polls SET status='dupe' WHERE chat=? AND msg_id=?", (r["chat"], r["msg_id"]))
        seen.add(r["word_key"])
    c.execute("COMMIT")


def seed_old_keys(c):
    """Keys the old vote jobs already paid for. Those jobs always clicked option 0; that vote is taken out too."""
    for chat in CHANNELS:
        if chat not in SEED_OLD:
            continue
        f = OLD / chat / "keys_revealed.jsonl"
        if not f.exists():
            continue
        for r in map(json.loads, f.read_text(encoding="utf-8").splitlines()):
            if not r.get("option_votes"):
                continue
            add_own(c, chat, r["msg_id"], r.get("account") or "old", 0, 0.0)
            if r.get("correct_option_index") is not None:
                c.execute("UPDATE polls SET status='keyed', key=?, solution=?, votes=?, total=?, seen=? "
                          "WHERE chat=? AND msg_id=? AND status IN ('need','dupe')",
                          (r["correct_option_index"], r.get("solution"), json.dumps(r["option_votes"]),
                           r.get("total_voters", 0), 1.0, chat, r["msg_id"]))


def build_ready(c, raw=RAW, ready=READY):
    """questions.jsonl (a key from Telegram) and held.jsonl (no key): one row per distinct question, reposts merged.
    Reposts that key different options: the newest repost's key wins (`key_source` "newer_repost"; owner 2026-11-14)."""
    ready.mkdir(parents=True, exist_ok=True)
    own = {}
    for r in c.execute("SELECT chat, msg_id, option, ts FROM own"):
        own.setdefault((r["chat"], r["msg_id"]), []).append((r["option"], r["ts"]))
    rows = {(r["chat"], r["msg_id"]): r for r in c.execute("SELECT * FROM polls")}
    merged = {}
    for chat in CHANNELS:
        f = raw / chat / "messages.jsonl"
        if not f.exists():
            continue
        header, messages = "", {}
        with open(f, encoding="utf-8") as lines:
            for line in lines:
                m = json.loads(line)
                messages[m["msg_id"]] = m
        for mid in sorted(messages):
            m = messages[mid]
            p = m.get("poll")
            if not p:
                if (m.get("text") or "").strip():
                    header = m["text"].strip().split("\n")[0][:120]
                continue
            row = rows.get((chat, mid))
            if not row or row["status"] == "gone":
                continue
            q = merged.setdefault(row["word_key"], {"question": p["question"], "options": p["options"], "key": None,
                                                    "solution": None, "votes": [0] * len(p["options"]), "total": 0,
                                                    "key_conflict": False, "sightings": []})
            q["sightings"].append({"chat": chat, "msg_id": mid, "date": m.get("date"), "header": header})
            place = {option_word(o): i for i, o in enumerate(q["options"])}
            mine = [place.get(option_word(o)) for o in p["options"]]
            if row["key"] is not None and row["key"] < len(mine):
                key = mine[row["key"]]
                q["key_conflict"] = q["key_conflict"] or (q["key"] is not None and q["key"] != key)
                q["key"] = key if q["key"] is None else q["key"]
                q["solution"] = q["solution"] or row["solution"]
                stamp = (m.get("date") or "", mid)       # owner 2026-11-14: reposts that disagree, the newer one wins
                if stamp >= q.get("_newest", ("", -1, 0))[:2]:
                    q["_newest"] = (*stamp, key, row["solution"])
            if row["votes"]:
                votes, total = net(json.loads(row["votes"]), row["total"], own.get((chat, mid), []), row["seen"])
                for i, v in enumerate(votes):
                    if i < len(mine) and mine[i] is not None:
                        q["votes"][mine[i]] += v
                q["total"] += total
    counts = {"questions": 0, "held": 0, "conflicts": 0}
    with open(ready / "questions.jsonl", "w", encoding="utf-8") as good, \
            open(ready / "held.jsonl", "w", encoding="utf-8") as held:
        for q in merged.values():
            newest = q.pop("_newest", None)
            if q["key_conflict"] and newest:
                q.update(key=newest[2], solution=newest[3] or q["solution"], key_conflict=False, key_source="newer_repost")
                counts["newer_repost"] = counts.get("newer_repost", 0) + 1
            keyed = q["key"] is not None
            (good if keyed else held).write(json.dumps(q, ensure_ascii=False) + "\n")
            counts["questions" if keyed else "held"] += 1
            counts["conflicts"] += q["key_conflict"]
    put(c, "ready", json.dumps(counts))
    return counts


def status(c):
    by = {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM polls GROUP BY status")}
    now = time.time()
    recent = c.execute("SELECT COUNT(*) n FROM own WHERE ts>?", (now - 600,)).fetchone()["n"]
    to_vote = by.get("need", 0) + by.get("claimed", 0)
    return {"running": now - float(get(c, "beat", 0)) < 15, "stage": get(c, "stage", "idle"), "note": get(c, "note", ""),
            "interval": float(get(c, "interval", 8)), "polls": by, "to_vote": to_vote,
            "per_hour": recent * 6, "eta_hours": round(to_vote / (recent * 6), 1) if recent else None,
            "ready": json.loads(get(c, "ready", "null")),
            "channels": [dict(r) for r in c.execute("SELECT * FROM channels")],
            "accounts": [dict(r) for r in c.execute("SELECT * FROM accounts ORDER BY label")]}


class Halt(Exception):
    """Stop every account and tell the owner why."""


async def scrape(client, c, entities, format_raw_message):
    """Append each channel's new messages to raw/<chat>/messages.jsonl and list its quiz polls. Resumes by message id."""
    dead = tombstones()

    async def one(chat):
        ent = entities[chat]
        c.execute("INSERT OR IGNORE INTO channels(chat) VALUES(?)", (chat,))
        last = c.execute("SELECT last_id FROM channels WHERE chat=?", (chat,)).fetchone()["last_id"]
        top = (await client.get_messages(ent, limit=1))[0].id
        c.execute("UPDATE channels SET top_id=? WHERE chat=?", (top, chat))
        folder = RAW / chat
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "messages.jsonl", "a", encoding="utf-8") as out:
            count = 0
            async for msg in client.iter_messages(ent, reverse=True, min_id=last, wait_time=0.5):
                if STOP.exists():
                    return
                record = format_raw_message(msg, ent.id)
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                p = record.get("poll")
                if p and p["quiz"] and (chat, msg.id) not in dead:
                    got = read_results(msg.media.poll, msg.media.results)
                    c.execute("INSERT OR IGNORE INTO polls(chat, msg_id, word_key) VALUES(?,?,?)",
                              (chat, msg.id, word_key(p["question"], p["options"])))
                    if got["key"] is not None:
                        save(c, chat, msg.id, got, "keyed")
                        if got["chosen"] is not None:
                            add_own(c, chat, msg.id, SCANNER, got["chosen"], 0.0)
                count += 1
                if count % 200 == 0:
                    out.flush()
                    c.execute("UPDATE channels SET last_id=? WHERE chat=?", (msg.id, chat))
        c.execute("UPDATE channels SET last_id=? WHERE chat=?", (top, chat))

    await asyncio.gather(*(one(chat) for chat in CHANNELS if chat in entities))


async def pause(seconds):
    end = time.time() + seconds
    while time.time() < end and not STOP.exists():
        await asyncio.sleep(min(1, max(0, end - time.time())))


async def vote_one(client, c, label, ent, chat, mid, msg, tg):
    """Vote on one poll and record its key. Returns False when the vote showed no correct flag."""
    if not msg or not hasattr(getattr(msg, "media", None), "poll"):
        c.execute("UPDATE polls SET status='gone', claimed_by=NULL WHERE chat=? AND msg_id=?", (chat, mid))
        return True
    poll = msg.media.poll
    got = read_results(poll, msg.media.results)
    if got["key"] is None:
        pick = random.randrange(len(poll.answers))
        update = await client(tg.SendVoteRequest(peer=ent, msg_id=mid, options=[poll.answers[pick].option]))
        got = read_results(poll, next(u.results for u in update.updates if hasattr(u, "results")))
        got["chosen"] = pick if got["chosen"] is None else got["chosen"]
    if got["chosen"] is not None:
        add_own(c, chat, mid, label, got["chosen"], time.time() - 1)
    save(c, chat, mid, got, "keyed" if got["key"] is not None else "held")
    return got["key"] is not None


async def join_missing(client, have, tg):
    """Put an account in every polls channel, so nobody sits idle. Returns what went wrong, or an empty string."""
    problem = ""
    for chat, channel_id in CHANNELS.items():
        if chat in have:
            continue
        try:
            ent = await client.get_entity(chat)
            if ent.id != channel_id:
                raise ValueError(f"{chat} now points at another chat")
            await client(tg.JoinChannelRequest(ent))
            have[chat] = ent
            await asyncio.sleep(2)
        except Exception as e:  # noqa: BLE001 - the account still votes in the channels it has
            problem = f"join failed: {str(e)[:70]}"
    return problem


async def run_voters(start, retry, every=60):
    """Wait for all voters; every minute, an account that logged in meanwhile joins the running job."""
    tasks = start()
    waited = 0
    while any(not t.done() for t in tasks):
        await asyncio.sleep(1)
        waited += 1
        if waited >= every:
            waited = 0
            tasks += await retry()


async def voter(label, client, entities, c, tg, shared):
    chats = [chat for chat in CHANNELS if chat in entities]
    scale, no_flag = 1.0, 0
    client.flood_sleep_threshold = 0  # FloodWait reaches this loop, which waits and slows this account down
    c.execute("UPDATE accounts SET state='voting' WHERE label=?", (label,))
    try:
        while not STOP.exists() and not shared["halt"]:
            batch = claim(c, label, chats)
            if not batch:
                break
            for chat in {b[0] for b in batch}:
                ids = [b[1] for b in batch if b[0] == chat]
                try:
                    messages = await client.get_messages(entities[chat], ids=ids)
                except tg.FloodWaitError as e:
                    tg.check_fatal(e, label)
                    scale = min(scale * 1.5, 8)
                    release(c, label)
                    c.execute("UPDATE accounts SET floods=floods+1, state=? WHERE label=?",
                              (f"waiting {e.seconds} s", label))
                    await pause(e.seconds + 2)
                    break
                for mid, msg in zip(ids, messages):
                    if STOP.exists() or shared["halt"]:
                        return
                    try:
                        keyed = await vote_one(client, c, label, entities[chat], chat, mid, msg, tg)
                        c.execute("UPDATE accounts SET votes=votes+1, state='voting' WHERE label=?", (label,))
                        no_flag = 0 if keyed else no_flag + 1
                        if no_flag > MAX_NO_FLAG:
                            raise Halt(f"{label}: {MAX_NO_FLAG} votes showed no key")
                    except tg.FloodWaitError as e:
                        tg.check_fatal(e, label)
                        scale = min(scale * 1.5, 8)
                        c.execute("UPDATE polls SET status='need', claimed_by=NULL WHERE chat=? AND msg_id=?", (chat, mid))
                        c.execute("UPDATE accounts SET floods=floods+1, state=? WHERE label=?",
                                  (f"waiting {e.seconds} s", label))
                        await pause(e.seconds + 2)
                    except (tg.Stop, Halt):
                        raise
                    except Exception as e:  # noqa: BLE001 - one broken poll is held, the rest go on
                        tg.check_fatal(e, label)
                        c.execute("UPDATE polls SET status='held', claimed_by=NULL, note=? WHERE chat=? AND msg_id=?",
                                  (str(e)[:200], chat, mid))
                    await pause(min(float(get(c, "interval", 8)) * scale, MAX_INTERVAL) * random.uniform(0.8, 1.2))
    except tg.Stop as e:
        text = str(e).upper()
        if "AUTH_KEY" in text or "SESSION_REVOKED" in text:
            c.execute("UPDATE accounts SET state='needs login' WHERE label=?", (label,))
        else:  # rule F2: a restriction or a FloodWait over 1 hour stops every account
            shared["halt"] = str(e)
    except Halt as e:
        shared["halt"] = str(e)
    except Exception as e:  # noqa: BLE001 - a lost connection ends this account only
        c.execute("UPDATE accounts SET state=? WHERE label=?", (f"error: {str(e)[:80]}", label))
    finally:
        release(c, label)
        c.execute("UPDATE accounts SET state='idle' WHERE label=? AND (state='voting' OR state LIKE 'waiting%')", (label,))


async def heartbeat(c):
    while True:
        put(c, "beat", time.time())
        await asyncio.sleep(3)


async def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path[:0] = [str(TELEGRAM / "quizbot"), str(TELEGRAM), str(OLD)]
    from export_telegram_raw import format_raw_message
    from reveal_keys_round3 import VOTING_ACCOUNTS_PATH
    from telethon.errors import FloodWaitError
    from telethon.tl.functions.channels import JoinChannelRequest
    from telethon.tl.functions.messages import SendVoteRequest
    import tg as telegram

    class tg:  # what voter() needs from Telegram
        pass
    tg.FloodWaitError, tg.SendVoteRequest, tg.JoinChannelRequest = FloodWaitError, SendVoteRequest, JoinChannelRequest
    tg.Stop, tg.check_fatal = telegram.Stop, telegram.check_fatal

    c = db()
    beat = asyncio.create_task(heartbeat(c))
    release(c)
    put(c, "note", "")
    put(c, "stage", "connecting")
    clients, entities, signed_out = {}, {}, []
    wanted = {cid: name for name, cid in CHANNELS.items()}

    async def attach(label):
        """Connect one account and put it in every channel. False while it needs a login."""
        try:
            client = await telegram.connect(label)
            have = {wanted[d.entity.id]: d.entity async for d in client.iter_dialogs() if d.entity.id in wanted}
        except Exception:  # noqa: BLE001 - signed out, or its session is busy with a login right now
            c.execute("UPDATE accounts SET state='needs login', channels=0 WHERE label=?", (label,))
            return False
        problem = await join_missing(client, have, tg)
        clients[label], entities[label] = client, have
        c.execute("UPDATE accounts SET state=?, channels=? WHERE label=?", (problem or "idle", len(have), label))
        return True

    for acc in json.loads(VOTING_ACCOUNTS_PATH.read_text(encoding="utf-8")):
        c.execute("INSERT OR IGNORE INTO accounts(label) VALUES(?)", (acc["label"],))
        if not await attach(acc["label"]):
            signed_out.append(acc["label"])
    shared = {"halt": None}

    def start_voter(label):
        return asyncio.create_task(voter(label, clients[label], entities[label], c, tg, shared))

    async def late_logins():
        back = [label for label in list(signed_out) if await attach(label)]
        signed_out[:] = [label for label in signed_out if label not in back]
        return [start_voter(label) for label in back if entities[label]]

    try:
        for stage in ("first scrape", "vote", "last scrape", "vote"):
            put(c, "stage", stage)
            if stage.endswith("scrape"):
                clients[SCANNER].flood_sleep_threshold = 3600  # a scrape just waits
                await scrape(clients[SCANNER], c, entities[SCANNER], format_raw_message)
                if not STOP.exists():
                    seed_old_keys(c)
                    mark_dupes(c)
            else:
                await run_voters(lambda: [start_voter(label) for label in clients if entities[label]], late_logins)
            if STOP.exists() or shared["halt"]:
                break
        if shared["halt"] or STOP.exists():
            put(c, "stage", "stopped")
            put(c, "note", shared["halt"] or "")
        else:
            put(c, "stage", "building")
            build_ready(c)
            put(c, "stage", "done")
    except Exception as e:
        put(c, "stage", "stopped")
        put(c, "note", f"{type(e).__name__}: {str(e)[:200]}")
        raise
    finally:
        beat.cancel()
        put(c, "beat", 0)
        for client in clients.values():
            await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

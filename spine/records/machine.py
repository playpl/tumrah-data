"""The records machine: every lecture, mini lecture and revision of a mother tree's lists, from the Telegram channel to
the site's private storage, in small batches that can be stopped and resumed at any point.

Which records: the agreed maps of `py -m spine mother run --year 1` (sources/mother/<channel>/<list>/<sha>.json); a
link the map calls lecture, mini or revision is one record. A map whose list changed since (other sha) is reported
and its list skipped: run `mother run` again first.

Ids: `y1-<subject channel>-<post>` (y1-bio-38, y1-anat-112); a YouTube link with no channel post: `y1-<chan>-yt<video>`.
They never look like a year 2 lecture id (cns-001) and they live outside `lectures/`, so the year 2 flow (Update data,
mother.lecture_index, queue.db) never sees them.

Files:
    sources/records/<channel>/<post>/<name>             the Telegram original (read only, kept)
    sources/records/<channel>/<post>/<name>.partial     a stopped download; the next run goes on from its size
    sources/records/<channel>/yt-<video>/               YouTube captions (yt*.vtt) or, with --youtube-audio, its audio
    modules/<m>/records/<id>/recording.48k.m4a          what is uploaded: AAC mono 48 kbps (upload_media.compress)
    modules/<m>/records/<id>/raw.txt                    YouTube captions as a raw transcript ([mm:ss] paragraphs)
    modules/<m>/graph/records.jsonl                     state log, one row per change; the last row per id wins

States of a Telegram record: seen -> downloaded -> compressed -> uploaded (key lectures/<m>/<id>/recording.48k.m4a).
A YouTube record is not uploaded (the site plays the YouTube video): seen -> downloaded (captions, or audio).
`transcript` (youtube | fleet) is kept apart from the state: transcription runs beside the upload.

Owner's rules: never upload an original file (owner 2026-11-17, slow internet: compress first); one Telegram reader at
a time (`sources/records/telegram.lock`; Update data's reader locks the session file too, reported as such).
"""
import asyncio
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from spine import ROOT, append_jsonl, graph_dir, module_dir, now, read_json, read_jsonl
from spine.tg import mother

SOURCES = ROOT / "sources" / "records"
LOCK = SOURCES / "telegram.lock"
SHORT = {"ZAG59_Anatomy": "anat", "ZAG59_physio": "phys", "ZAG59_Histo": "hist", "ZAG59_bio": "bio",
         "RecordsBatch58ATM": "rec"}
MEDIA = ("audio", "video")
SUFFIX = ".48k.m4a"                    # = upload_media.SUFFIX: AAC mono 48 kbps
CHUNK = 1024 * 1024                    # Telegram download piece (the largest it allows); a resume offset is a multiple of it
BLOCK_PIECES = 4                       # pieces one parallel fetch takes at once (4 MB)
UPLOAD_TRIES = 4
STALL_S = 120                          # no piece for this long: the download is stopped (the next run resumes)
BEAT_S = 60                            # a progress line this often during one file
BACKEND = Path(r"C:\Users\Ahmed\Desktop\tumrah\backend")
ACCOUNT = "voter2"
FINAL = {"telegram": "uploaded", "youtube": "downloaded"}
YT_ID = re.compile(r"(?:youtu\.be/|v=|/live/|/shorts/)([\w-]{6,})")


# --- the plan -------------------------------------------------------------------------------------------------
def year_doctors(year=1):
    """(module, doctors). Year 1 rows carry `channel` and `list`; year 2 rows carry `new` (the list imported; `old` is
    fallback data, never planned) and the channel once for the whole year. Both come out as `channel` + `list`."""
    trees = read_json(mother.TREES)
    t = trees[f"year{year}"]
    out = []
    for d in t["doctors"]:
        d = dict(d)
        d.setdefault("channel", t.get("channel"))
        if "list" not in d:
            d["list"] = d.get("new")
        out.append(d)
    return t["module"], out


def short(channel):
    return SHORT.get(channel) or re.sub(r"[^a-z]", "", channel.lower())[-5:]


def yt_id(url):
    m = YT_ID.search(url or "")
    return m.group(1) if m else None


def record_id(year, channel, post, url=None):
    if post:
        return f"y{year}-{short(channel)}-{post}"
    return f"y{year}-{short(channel)}-yt{yt_id(url)}"


def plan(year=1, doctor=None, problems=None):
    """[record] in tree order, then message order. `problems` (a list) collects what kept a list out."""
    module, doctors = year_doctors(year)
    problems = [] if problems is None else problems
    out = []
    skipped = [d for d in doctors if d.get("subject") in SKIP_SUBJECTS]
    if skipped:
        problems.append(f"{', '.join(sorted({d['subject'] for d in skipped}))}: {len(skipped)} lists skipped "
                        f"(owner 2026-11-17: no biochemistry for anyone in these modules)")
    for d in doctors:
        ref = f"{d['channel']}/{d['list']}"
        if d in skipped or (doctor and not matches(d, ref, doctor)):
            continue
        if d.get("skip") or not d.get("list"):
            why = d.get("note") if d.get("skip") and d.get("note") else "skipped by the owner" if d.get("skip") else                 "no new list (old data is fallback only)" + (f"; {d['note']}" if d.get("note") else "")
            problems.append(f"{d['name']} ({d['subject']}): {why}")
            continue
        lst, row = mother.load(ref), mother.cached(ref)
        if not lst or not row:
            problems.append(f"{ref} {d['name']}: no {'list' if not lst else 'agreed map'} yet (py -m spine mother run --year {year})")
            continue
        if row["sha"] != mother.cache_key(lst):
            problems.append(f"{ref} {d['name']}: the list changed since its map (py -m spine mother run --year {year})")
            continue
        for i, r in enumerate(records_of(year, module, d, lst, row)):
            r["rank"], r["doctor_order"] = i, doctors.index(d)
            out.append(r)
    return out


SUBJECTS = ("anatomy", "physiology", "histology", "biochemistry")
# Owner, 2026-11-17: "No biochemistry for anyone in these modules at all." Its lists are never downloaded,
# uploaded, transcribed or imported.
SKIP_SUBJECTS = {"biochemistry"}


def priority(recs):
    """First lessons of every subject first (owner, 2026-11-17): every doctor's 1st record, then every 2nd, ...;
    within one rank the subjects in SUBJECTS order, then the tree's doctor order."""
    def key(r):
        subj = SUBJECTS.index(r["subject"]) if r["subject"] in SUBJECTS else len(SUBJECTS)
        return r.get("rank", 0), subj, r.get("doctor_order", 0)
    return sorted(recs, key=key)


def matches(d, ref, word):
    w = word.lower()
    return w in d["name"].lower() or w == ref.lower() or w == str(d.get("list"))


def records_of(year, module, d, lst, row):
    ls = {l["k"]: l for l in mother.links(lst)}
    ids, out = {}, []
    for k in sorted(row["map"], key=int):
        if row["map"][k]["role"] != "ignore":
            l = ls[int(k)]
            ids[int(k)] = record_id(year, d["channel"], l["post"], l["url"])
    for k in sorted(row["map"], key=int):
        v = row["map"][k]
        if v["role"] == "ignore":
            continue
        l = ls[int(k)]
        post = lst["posts"].get(str(l["post"])) or {}
        url = (post.get("youtube") or [None])[0] or l["url"]
        kind = post.get("kind") or l["kind"]
        out.append({"id": ids[int(k)], "module": module, "year": year, "channel": d["channel"], "list": d["list"],
                    "post": l["post"], "k": int(k), "doctor": d["name"], "site": d.get("site"), "subject": d["subject"],
                    "role": v["role"], "chapter": v["chapter"], "name": v["name"],
                    "covers": [ids[c] for c in sorted(v["covers"]) if c in ids],
                    "kind": kind, "source": "youtube" if kind == "youtube" else "telegram" if kind in MEDIA else None,
                    "size": post.get("size"), "duration": post.get("duration"), "youtube": url if kind == "youtube" else None,
                    "file_name": post.get("file_name"), "mime": post.get("mime")})
    return out


# --- state ----------------------------------------------------------------------------------------------------
def state_file(module):
    return graph_dir(module) / "records.jsonl"


def states(module):
    """{id: merged row}: the log folded, later rows over earlier ones."""
    out = {}
    for r in read_jsonl(state_file(module)):
        out.setdefault(r["id"], {}).update(r)
    return out


def mark(module, rid, state=None, **extra):
    row = {"id": rid, "at": now(), **({"state": state} if state else {}), **extra}
    append_jsonl(state_file(module), row)
    return row


ORDER = ("seen", "downloaded", "compressed", "uploaded")


def reached(st, rid, state):
    have = (st.get(rid) or {}).get("state") or "seen"
    return ORDER.index(have) >= ORDER.index(state)


def record_dir(rec):
    return module_dir(rec["module"]) / "records" / rec["id"]


def compressed_path(rec):
    return record_dir(rec) / f"recording{SUFFIX}"


def hear_path(rec):
    """The small Opus copy the fleet hears when the 48k file is not on this PC (made by the GitHub runner)."""
    return record_dir(rec) / "hear.16k.ogg"


def upload_key(rec):
    return f"lectures/{rec['module']}/{rec['id']}/recording{SUFFIX}"


def source_dir(rec):
    if rec["source"] == "youtube":
        return SOURCES / rec["channel"] / f"yt-{yt_id(rec['youtube'])}"
    return SOURCES / rec["channel"] / str(rec["post"])


def original(rec):
    """The finished Telegram original, or None."""
    d = source_dir(rec)
    files = [f for f in d.glob("*") if f.is_file() and not f.name.endswith(".partial")] if d.exists() else []
    return files[0] if files else None


# --- Telegram download ----------------------------------------------------------------------------------------
def resume_offset(have, chunk=CHUNK):
    """Where a stopped download goes on: its size rounded down to a whole piece (Telegram reads aligned pieces)."""
    return (have // chunk) * chunk


class Budget:
    """Bytes one run may fetch; a file that crosses it stops mid-way (its .partial is resumed next run)."""

    def __init__(self, max_mb, max_seconds=None, clock=time.monotonic):
        self.left = None if max_mb is None else int(max_mb * 1e6)
        self.clock = clock
        self.deadline = None if max_seconds is None else clock() + max_seconds

    def take(self, n):
        if self.left is not None:
            self.left -= n

    @property
    def spent(self):
        """Out of bytes, or out of time (the GitHub runner is killed at its timeout: stop before it)."""
        if self.deadline is not None and self.clock() >= self.deadline:
            return True
        return self.left is not None and self.left <= 0


async def parallel_stream(client, media, off, total, workers=4, chunk=None, block=BLOCK_PIECES):
    """The pieces of `media` from `off`, in order, fetched by `workers` blocks at a time. One request after another is
    bound by the round trip to Telegram (one piece per round trip); several blocks in flight use the whole link.
    Same contract as `client.iter_download(...)`: an async iterator of byte pieces."""
    chunk = chunk or CHUNK
    size = chunk * block
    starts = list(range(off, total, size))

    async def fetch(start):
        n = -(-(min(start + size, total) - start) // chunk)
        return [p async for p in client.iter_download(media, offset=start, limit=n, request_size=chunk, file_size=total)]

    window, nxt = [], 0
    try:
        while nxt < len(starts) or window:
            while nxt < len(starts) and len(window) < workers:
                window.append(asyncio.ensure_future(fetch(starts[nxt])))
                nxt += 1
            for piece in await window.pop(0):
                yield piece
    finally:
        for t in window:
            t.cancel()
        await asyncio.gather(*window, return_exceptions=True)


async def fetch_into(part, total, stream, budget, stall=None, beat=None, clock=time.monotonic):
    """Appends the pieces of `stream(offset)` to `part` from the resume offset. True when the file is whole.
    `stall` seconds with no piece raises TimeoutError (a silent hang never eats the run); `beat(size)` is called
    about every BEAT_S seconds so the log shows the file moving."""
    have = part.stat().st_size if part.exists() else 0
    off = resume_offset(have)
    if have != off:
        with open(part, "r+b") as f:
            f.truncate(off)
    it = stream(off).__aiter__()
    last = clock()
    try:
        with open(part, "ab") as f:
            while True:
                try:
                    nxt = it.__anext__()
                    piece = await (asyncio.wait_for(nxt, stall) if stall else nxt)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    raise TimeoutError(f"no data for {stall} s") from None
                f.write(piece)
                budget.take(len(piece))
                if beat and clock() - last >= BEAT_S:
                    last = clock()
                    beat(f.tell())
                if budget.spent and f.tell() < total:
                    break
    finally:
        close = getattr(it, "aclose", None)
        if close:
            try:
                await close()
            except Exception:  # noqa: BLE001 - closing a dead stream
                pass
    return part.stat().st_size >= total


def lock():
    import upload_media
    SOURCES.mkdir(parents=True, exist_ok=True)
    try:
        pid = int(LOCK.read_text().strip())
    except (OSError, ValueError):
        pid = None
    if pid and upload_media.alive(pid):
        raise RuntimeError(f"another Telegram reader of the records machine is alive (pid {pid})")
    LOCK.write_text(str(__import__("os").getpid()))


def unlock():
    LOCK.unlink(missing_ok=True)


async def _download_telegram(recs, budget, say, account=ACCOUNT, on_done=None, parallel=1, connections=0, finishers=1):
    """Downloads `recs` in order until `budget` is spent. `on_done(rec)` (sync, run in a thread) is called after each
    whole file, in a worker thread beside the next download (compress and upload never hold the link idle); a run
    that is stopped (timeout, dropped link) still waits for the records already downloaded, so it keeps everything it
    finished. `connections` > 0: each file over that many connections at once (fast.py; Telegram limits one
    connection's speed); else `parallel` blocks over the client's one connection (1: one request after another).
    `finishers` records are compressed and uploaded at once."""
    from cloud import tg as cloud_tg
    runner = cloud_tg.on_runner()
    if runner:                                       # the GitHub runner: its own session (cloud/tg.py)
        client = await cloud_tg.connect()
    else:
        sys.path.insert(0, r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\quizbot")
        from tg import connect
        client = await connect(account)
    done, pending = [], []
    ents = {}
    pool = ThreadPoolExecutor(max(1, finishers))      # compress + upload beside the downloads
    conns, conns_ok = None, False
    if connections > 0:
        from spine.records import fast
        conns = fast.Pool(client, connections, say)
    loop = asyncio.get_running_loop()

    async def finish(rec):
        try:
            await loop.run_in_executor(pool, on_done, rec)
        except Exception as e:  # noqa: BLE001 - one record's compress/upload never stops the others
            say(f"  {rec['id']}: after download FAILED ({type(e).__name__}: {str(e)[:120]})")
    try:
        for rec in recs:                                # in the order given: priority() puts first lessons first
            if budget.spent:
                return done
            try:
                if rec["channel"] not in ents:
                    ents[rec["channel"]] = await asyncio.wait_for(client.get_entity(rec["channel"]), STALL_S)
                m = await asyncio.wait_for(client.get_messages(ents[rec["channel"]], ids=rec["post"]), STALL_S)
            except Exception as e:  # noqa: BLE001 - a flood wait, a channel the account cannot see, a stall
                say(f"  {rec['id']}: post {rec['post']} of {rec['channel']} not read ({type(e).__name__}: {str(e)[:120]})")
                continue
            if m is None or not m.media or not m.file:
                say(f"  {rec['id']}: post {rec['post']} has no file")
                continue
            d = source_dir(rec)
            d.mkdir(parents=True, exist_ok=True)
            name = safe_name(m.file.name or f"{rec['post']}{m.file.ext or ''}")
            final, part = d / name, d / (name + ".partial")
            total = m.file.size
            if not (final.exists() and final.stat().st_size == total):
                before = part.stat().st_size if part.exists() else 0
                t0 = time.time()

                def stream(off, m=m):
                    if conns:
                        return fast.stream(conns, m.media, off, total, CHUNK, fallback=lambda o: client.iter_download(
                            m.media, offset=o, request_size=CHUNK, file_size=total))
                    if parallel > 1:
                        return parallel_stream(client, m.media, off, total, parallel)
                    return client.iter_download(m.media, offset=off, request_size=CHUNK, file_size=total)

                def beat(size, rid=rec["id"], t0=t0, before=before):
                    say(f"  {rid}: {size / 1e6:.0f} of {total / 1e6:.0f} MB "
                        f"({(size - before) / 1e3 / max(time.time() - t0, 1):.0f} KB/s)")
                say(f"  {rec['id']}: downloading {total / 1e6:.0f} MB (post {rec['post']})")
                try:
                    whole = await fetch_into(part, total, stream, budget, stall=STALL_S, beat=beat)
                except Exception as e:     # an expired file reference, a dropped link: the next run resumes
                    say(f"  {rec['id']}: stopped at {part_mb(part)} of {total / 1e6:.0f} MB ({type(e).__name__}: {str(e)[:80]})")
                    if conns and not conns_ok:   # the connections never worked: the rest of the run on one
                        say("  several connections failed before any whole file: back to the client's one connection")
                        await conns.close()
                        conns = None
                    continue
                if conns:
                    conns_ok = True
                got = (part.stat().st_size - before) / 1e6
                rate = got / max(time.time() - t0, 1)
                if not whole:
                    say(f"  {rec['id']}: {part_mb(part)} of {total / 1e6:.0f} MB so far ({rate * 1000:.0f} KB/s); batch limit reached")
                    return done
                part.replace(final)
                say(f"  {rec['id']}: downloaded {total / 1e6:.1f} MB ({rate * 1000:.0f} KB/s)")
            mark(rec["module"], rec["id"], "downloaded", file=str(final.relative_to(ROOT)), size=total,
                 **({"where": "runner"} if runner else {}))
            done.append(rec["id"])
            if on_done:
                pending.append(asyncio.ensure_future(finish(rec)))
    finally:
        if conns:
            await conns.close()
        await client.disconnect()
        if pending:
            say(f"  waiting for {sum(not t.done() for t in pending)} record(s) still being compressed or uploaded")
            await asyncio.gather(*pending)
        pool.shutdown()
    return done


def part_mb(part):
    return f"{(part.stat().st_size if part.exists() else 0) / 1e6:.0f}"


def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "file"


# --- YouTube --------------------------------------------------------------------------------------------------
def youtube_captions(rec):
    """Captions only (a few KB). Writes records/<id>/raw.txt; True when YouTube has captions."""
    import lectures
    d = source_dir(rec)
    d.mkdir(parents=True, exist_ok=True)
    subs = sorted(d.glob("yt*.vtt"))
    if not subs:
        subprocess.run(["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", "ar.*,en.*,ar,en",
                        "--sub-format", "vtt", "-o", str(d / "yt.%(ext)s"), rec["youtube"]], capture_output=True, text=True)
        subs = d.glob("yt*.vtt")
    subs = sorted(subs, key=lambda p: (".orig" not in p.name, "auto" in p.name))
    raw = lectures.vtt_to_raw(subs[0].read_text(encoding="utf-8")) if subs else ""
    if not raw.strip():
        return False
    out = record_dir(rec) / "raw.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(raw, encoding="utf-8")
    return True


def youtube_audio(rec):
    """The smallest audio stream, for the fleet to hear (no captions on YouTube)."""
    d = source_dir(rec)
    have = [f for f in d.glob("yt_audio.*") if not f.name.endswith((".part", ".ytdl"))]
    if have:
        return have[0]
    subprocess.run(["yt-dlp", "-f", "worstaudio", "-o", str(d / "yt_audio.%(ext)s"), rec["youtube"]],
                   capture_output=True, text=True)
    have = [f for f in d.glob("yt_audio.*") if not f.name.endswith((".part", ".ytdl"))]
    return have[0] if have else None


# --- steps ----------------------------------------------------------------------------------------------------
def download(recs, budget=None, youtube_audio_too=False, say=print):
    """YouTube captions, then Telegram media until `budget` (a Budget, shared across doctors) is spent."""
    st = states(recs[0]["module"]) if recs else {}
    budget = budget or Budget(None)
    yt = [r for r in recs if r["source"] == "youtube" and not reached(st, r["id"], "downloaded")]
    for r in yt:
        if youtube_captions(r):
            mark(r["module"], r["id"], "downloaded", transcript="youtube")
            say(f"  {r['id']}: YouTube captions")
        elif youtube_audio_too and not budget.spent:
            f = youtube_audio(r)
            if f:
                budget.take(f.stat().st_size)
                mark(r["module"], r["id"], "downloaded", file=str(f.relative_to(ROOT)), size=f.stat().st_size)
                say(f"  {r['id']}: YouTube audio {f.stat().st_size / 1e6:.1f} MB (no captions)")
            else:
                say(f"  {r['id']}: YouTube audio failed")
        else:
            say(f"  {r['id']}: no YouTube captions (audio waits for --youtube-audio)")
    tg = [r for r in priority(recs) if r["source"] == "telegram" and not reached(st, r["id"], "downloaded")]
    if not tg or budget.spent:
        return
    lock()
    try:
        asyncio.run(_download_telegram(tg, budget, say))
    except Exception as e:
        if "database is locked" in str(e):
            raise RuntimeError("Telegram session is in use (Update data or tg_lists.py fetch is running): run again after it")
        raise
    finally:
        unlock()


def compress(recs, say=print):
    import lectures
    import upload_media
    st = states(recs[0]["module"]) if recs else {}
    for r in priority(recs):
        if r["source"] != "telegram" or not reached(st, r["id"], "downloaded") or reached(st, r["id"], "compressed"):
            continue
        src = original(r)
        if not src:
            say(f"  {r['id']}: the original is gone from {source_dir(r)}")
            continue
        out = compressed_path(r)
        try:
            upload_media.compress(src, out)
            secs = round(lectures.duration(out), 1)
        except Exception as e:
            say(f"  {r['id']}: compress FAILED {str(e)[-160:]}")
            continue
        mark(r["module"], r["id"], "compressed", compressed=str(out.relative_to(ROOT)), compressed_size=out.stat().st_size,
             duration_s=secs)
        say(f"  {r['id']}: {src.stat().st_size / 1e6:.1f} MB -> {out.stat().st_size / 1e6:.1f} MB ({secs / 60:.0f} min)")


def check_uploadable(path):
    """Only a compressed recording goes up, never an original (owner 2026-11-17)."""
    p = Path(path)
    if not p.name.endswith(SUFFIX) or "records" not in p.parts:
        raise ValueError(f"refusing to upload {p}: only modules/<m>/records/<id>/recording{SUFFIX} is uploaded")
    return p


def send(file, key):
    res = None
    for attempt in range(UPLOAD_TRIES):    # a streamed body is never retried by the S3 client: retry the whole file
        res = subprocess.run(["node", "../node_modules/tsx/dist/cli.mjs", "src/scripts/uploadLessonMedia.ts", "--file",
                              str(file), "--key", key], cwd=BACKEND, capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0:
            break
        time.sleep(15 * (attempt + 1))
    return res.returncode == 0, (res.stdout or res.stderr or "").strip()[-160:]


def upload(recs, limit=None, say=print, sender=send):
    st = states(recs[0]["module"]) if recs else {}
    todo = [r for r in priority(recs) if r["source"] == "telegram" and reached(st, r["id"], "compressed")
            and not reached(st, r["id"], "uploaded")]
    for r in todo[:limit]:
        f = check_uploadable(compressed_path(r))
        if not f.exists():
            say(f"  {r['id']}: compressed file missing, compress again")
            continue
        ok, out = sender(f, upload_key(r))
        if ok:
            mark(r["module"], r["id"], "uploaded", key=upload_key(r), uploaded_size=f.stat().st_size)
        say(f"  {r['id']}: {'uploaded' if ok else 'upload FAILED'} {f.stat().st_size / 1e6:.1f} MB {'' if ok else out}")


# --- reports --------------------------------------------------------------------------------------------------
def by_doctor(recs):
    out = {}
    for r in recs:
        out.setdefault((r["doctor"], f"{r['channel']}/{r['list']}"), []).append(r)
    return out


def plan_lines(recs):
    lines = [f"{'doctor':<44} {'list':<17} rec  tg   MB    yt  none"]
    tot = [0, 0, 0.0, 0, 0]
    for (doc, ref), rs in by_doctor(recs).items():
        tg = [r for r in rs if r["source"] == "telegram"]
        mb = sum(r["size"] or 0 for r in tg) / 1e6
        yt = sum(r["source"] == "youtube" for r in rs)
        none = sum(r["source"] is None for r in rs)
        lines.append(f"{doc[:44]:<44} {ref:<17} {len(rs):>3} {len(tg):>3} {mb:>6.0f} {yt:>4} {none:>4}")
        for i, v in enumerate((len(rs), len(tg), mb, yt, none)):
            tot[i] += v
    lines.append(f"{'total':<44} {'':<17} {tot[0]:>3} {tot[1]:>3} {tot[2]:>6.0f} {tot[3]:>4} {tot[4]:>4}")
    return lines


def status_lines(recs):
    st = states(recs[0]["module"]) if recs else {}
    lines = [f"{'doctor':<36} tg: down comp  up  MB left | yt: caps  wait"]
    left_mb, left = 0.0, 0
    for (doc, ref), rs in by_doctor(recs).items():
        tg = [r for r in rs if r["source"] == "telegram"]
        yt = [r for r in rs if r["source"] == "youtube"]
        n = {s: sum(reached(st, r["id"], s) for r in tg) for s in ("downloaded", "compressed", "uploaded")}
        mb = sum((r["size"] or 0) - partial_size(r) for r in tg if not reached(st, r["id"], "downloaded")) / 1e6
        caps = sum(reached(st, r["id"], "downloaded") for r in yt)
        left_mb += mb
        left += len(tg) - n["uploaded"] + len(yt) - caps
        lines.append(f"{doc[:36]:<36} {len(tg):>3} {n['downloaded']:>4} {n['compressed']:>4} {n['uploaded']:>3} {mb:>7.0f} |"
                     f" {len(yt):>3} {caps:>4} {len(yt) - caps:>5}")
    lines.append(f"left: {left} records, {left_mb:.0f} MB still to download from Telegram")
    return lines


def partial_size(rec):
    d = source_dir(rec)
    return sum(f.stat().st_size for f in d.glob("*.partial")) if d.exists() else 0

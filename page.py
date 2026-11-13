"""The data admin page: http://127.0.0.1:8770 (py dm.py page). Local only; reads the live site through db.py and
writes it only through the tumrah repo's importers.

Screens: Today (the owner's inbox: what is ready, the measured error, one-click decisions, spot checks), Progress, Handout (upload, split into lines), Questions (filter, tick, Hand over), Polls (counts, key
conflicts for the owner), Lectures (add, Transcribe), Word fixes, Books (add with doctor, % aligned), Coverage, Voters,
Lecture questions, Highlights, Gap map.
"""
import json
import re
import subprocess
import threading
import time
from collections import Counter
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import checks
import control
import decisions
import highlights
import lectures
import queue_db
import runners
from flows.common import read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parent
PORT = 8770
HANDOVER = ROOT / "handover"
BACKEND = Path(r"C:\Users\Ahmed\Desktop\tumrah\backend")
PAGE_SIZE = 50
OID = re.compile(r"^[0-9a-f]{24}$")
JOBS = {}  # background actions: name -> {"state", "result", "at"}


def background(name, fn, *args):
    if JOBS.get(name, {}).get("state") == "running":
        return {"started": False, "reason": f"{name} is already running"}
    JOBS[name] = {"state": "running", "result": None, "at": time.strftime("%H:%M")}

    def go():
        try:
            JOBS[name].update(state="done", result=fn(*args))
        except BaseException as e:  # noqa: BLE001 - shown on the page
            JOBS[name].update(state="failed", result=f"{type(e).__name__}: {str(e)[:300]}")
    threading.Thread(target=go, daemon=True).start()
    return {"started": True}


# ---- questions ---------------------------------------------------------------------------------------------------
def question_filter(reader, module=None, doctor=None, test_type=None, pointer=None, after=None):
    from bson import ObjectId
    flt = {"type": "med_question"}
    if module:
        m = reader.find("academicmodules", {"code": module}, {"_id": 1}, limit=1)
        flt["academicModule"] = m[0]["_id"] if m else None
    if doctor:
        flt["doctor"] = doctor
    if test_type:
        flt["test_type"] = test_type
    if pointer == "with":
        flt["book_found"] = {"$exists": True}
    elif pointer == "without":
        flt["book_found"] = {"$exists": False}
    if after and OID.match(after):
        flt["_id"] = {"$gt": ObjectId(after)}
    return flt


def questions(reader, **kw):
    """One page of questions (never the whole bank), and the cursor for the next."""
    rows = reader.find("questions", question_filter(reader, **kw),
                       {"question_text": 1, "doctor": 1, "test_type": 1, "book_found": 1, "status": 1},
                       limit=PAGE_SIZE, sort=[("_id", 1)])
    out = [{"id": str(r["_id"]), "text": (r.get("question_text") or "")[:220], "doctor": r.get("doctor"),
            "set": r.get("test_type"), "pointer": "book_found" in r, "status": r.get("status")} for r in rows]
    return {"rows": out, "next": out[-1]["id"] if len(out) == PAGE_SIZE else None}


def handover(reader, module, ids):
    """Writes handover/<date>-<module>.json for the pointer flow; questions with pointers are skipped."""
    from bson import ObjectId
    ids = [i for i in ids if OID.match(i)]
    have = {str(r["_id"]): r for r in reader.find(
        "questions", {"_id": {"$in": [ObjectId(i) for i in ids]}}, {"book_found": 1}, limit=len(ids) or 1)}
    take = [i for i in ids if i in have and "book_found" not in have[i]]
    HANDOVER.mkdir(exist_ok=True)
    path = HANDOVER / f"{date.today().isoformat()}-{module}-{int(time.time())}.json"
    path.write_text(json.dumps({"module": module, "questions": take}), encoding="utf-8")
    return {"file": path.name, "handed_over": len(take), "skipped_with_pointers": len(ids) - len(take)}


# ---- lectures and word fixes ---------------------------------------------------------------------------------------
def job_state(q, flow, key):
    r = q.db.execute("SELECT status, note FROM jobs WHERE flow=? AND key=?", (flow, key)).fetchone()
    return {"status": r["status"], "note": r["note"]} if r else None


def lecture_list(q=None):
    out = []
    for f in sorted(lectures.LECTURES.glob("*/lecture.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        d = f.parent
        stage = "aligned" if (d / "links.jsonl").exists() else "transcribed" if (d / "raw.txt").exists() else \
            "waiting" if m.get("transcribe") else "no recording" if not m.get("source") else "not transcribed"
        sl = json.loads((d / "shortlist.json").read_text(encoding="utf-8")) if (d / "shortlist.json").exists() else None
        row = {**{k: m.get(k) for k in ("id", "module", "title", "doctor", "kind", "lesson", "pdf_pages", "transcribe",
                                        "duration_s", "report", "fixes", "placed_by", "place_note", "source", "covers")},
               "stage": stage, "pages": lectures.page_ranges(m), "required": len(m.get("required") or []),
               "doctor_questions": len(m.get("doctor_questions") or []), "shortlist": sl}
        if q is not None:
            import shortlist
            res = shortlist.results(m["id"], q)
            sent = json.loads((d / "sent.json").read_text(encoding="utf-8")) if (d / "sent.json").exists() else []
            row.update(place=job_state(q, "place", m["id"]), sent=len(sent), pointed=sum(r["found"] for r in res.values()),
                       other_lecture=sum(r["reason"] == "other_lecture" for r in res.values()), answered=len(res))
        out.append(row)
    return out


def new_lecture(b, q):
    """The owner names a lecture; the place agent is queued at once when the module has its handout lines."""
    module = b.get("module", "")
    if module not in module_codes():
        return {"error": f"unknown module {module}"}
    if not (ROOT / "modules" / module / "lines.jsonl").exists():
        return {"error": f"add the {module} handout first (Handout tab)"}
    covers = [c.strip() for c in (b.get("covers") or []) if c.strip()] if isinstance(b.get("covers"), list) else \
        [c for c in re.split(r"[\s,]+", b.get("covers") or "") if c]
    try:
        meta = lectures.create(module, b.get("title", ""), b.get("doctor", ""), kind=b.get("kind") or "lecture",
                               covers=covers)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e) if isinstance(e, ValueError) else f"no lecture {e.filename}"}
    if meta["kind"] != "lecture":  # a mini lecture or revision takes its pages from what it covers
        return {"id": meta["id"], "queued": None, "pages": lectures.page_ranges(meta)}
    q.add_jobs("place", [{"key": meta["id"], "payload": {"lecture": meta["id"]}}])
    return {"id": meta["id"], "queued": "place"}


def set_pages(lecture_id, text):
    """The owner's own handout pages for a lecture ("49-57, 80-82"); they replace the agent's and are never overwritten."""
    spans = re.findall(r"(\d+)\s*-\s*(\d+)|(\d+)", text or "")
    pages = sorted([int(a), int(b)] if a else [int(c), int(c)] for a, b, c in spans)
    meta = lectures.load(lecture_id)
    lines = read_jsonl(ROOT / "modules" / meta["module"] / "lines.jsonl")
    errors = checks.check_place({"ranges": [{"first_page": a, "last_page": b} for a, b in pages], "note": "set by the owner by hand on the admin page"}, lines)
    if errors:
        return {"error": "; ".join(errors)}
    lectures.set_ranges(meta, lines, pages, "owner")
    return {"pages": lectures.page_ranges(meta)}


_BANK = {"mtime": None, "rows": [], "by": {}}


def bank_rows():
    """The bank, slim and cached until bank/questions.jsonl changes (the Lecture screen searches it)."""
    qf = BANK / "questions.jsonl"
    if not qf.exists():
        return [], {}
    m = qf.stat().st_mtime
    if _BANK["mtime"] != m:
        rows = []
        with qf.open(encoding="utf-8") as f:
            for line in f:
                q = json.loads(line)
                row = {k: q.get(k) for k in ("word_key", "question", "options", "key", "key_conflict", "doctors",
                                             "repetition_count", "total")}
                row["sightings"] = [{"chat": x.get("chat"), "date": x.get("date")} for x in q.get("sightings") or []]
                rows.append(row)
        _BANK.update(mtime=m, rows=rows, by={r["word_key"]: r for r in rows})
    return _BANK["rows"], _BANK["by"]


def lecture_bank(lecture_id, text="", page=0):
    """Bank questions for the owner to pick from: the lecture's shortlist order when it is built, else the whole bank;
    `text` narrows to questions holding every typed word. 50 per page."""
    import shortlist
    meta = lectures.load(lecture_id)
    rows, by = bank_rows()
    sl = lectures.folder(lecture_id) / "shortlist.jsonl"
    order = [by[r["word_key"]] for r in read_jsonl(sl) if r["word_key"] in by] if sl.exists() and not text else rows
    want = [w.lower() for w in (text or "").split()]
    if want:
        order = [r for r in order if all(w in (" ".join([r["question"] or "", *(o or "" for o in r["options"] or [])])).lower()
                                         for w in want)]
    picked = {r.get("word_key"): name for name in ("required", "doctor_questions") for r in meta.get(name) or []}
    out = order[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    return {"rows": [{**{k: v for k, v in r.items() if k != "sightings"}, "qid": shortlist.qid_of(r["word_key"]),
                      "picked": picked.get(r["word_key"])} for r in out],
            "total": len(order), "from": "search" if want else "shortlist" if sl.exists() else "bank"}


def lecture_picks(lecture_id):
    """The owner's two lists with each question's text (bank) or file row, in order."""
    meta = lectures.load(lecture_id)
    _, by = bank_rows()
    out = {}
    for name in ("required", "doctor_questions"):
        out[name] = [{**r, "question": (by.get(r.get("word_key")) or r.get("row") or {}).get("question"),
                      "options": (by.get(r.get("word_key")) or r.get("row") or {}).get("options")} for r in meta.get(name) or []]
    return out


def pick(lecture_id, word_key, into):
    """Puts one bank question in the owner's Required or Doctor's other list (or takes it out with into=None)."""
    meta = lectures.load(lecture_id)
    for name in ("required", "doctor_questions"):
        meta[name] = [r for r in meta.get(name) or [] if r.get("word_key") != word_key]
    if into in ("required", "doctor_questions"):
        meta[into].append({"word_key": word_key, "by": "owner", "at": time.strftime("%Y-%m-%d %H:%M")})
    lectures.save(meta)
    return {"required": len(meta["required"]), "doctor_questions": len(meta["doctor_questions"])}


def add_file(lecture_id, into, name, content):
    """The doctor's own sheet: every row is looked up first (cover.py: exact in the bank and on the site, then the fleet
    for near matches). Bank matches join the list now; site matches and unmatched rows wait in the list as such."""
    if into not in ("required", "doctor_questions"):
        return {"error": "list"}
    path = save_cover_file(f"{lecture_id}-{into}-{name}", content)
    return background(f"lecture-file {lecture_id}", file_into_lecture, lecture_id, into, path)


def file_into_lecture(lecture_id, into, path, only=None):
    """Files a covered file's questions into a lecture's owner list; `only`: just these row numbers."""
    import cover
    done = run_cover(path)
    entry = cover.covered(path)
    rows = read_jsonl(BANK / f"cover_{entry['sha']}.jsonl") if entry else []
    _, by = bank_rows()
    prefix = {k[:16]: k for k in by}
    meta = lectures.load(lecture_id)
    have = {r.get("word_key") for n in ("required", "doctor_questions") for r in meta.get(n) or []}
    rows_in = {(r.get("file"), r.get("n")) for n in ("required", "doctor_questions") for r in meta.get(n) or [] if r.get("file")}
    added = Counter()
    for i, r in enumerate(rows):
        if only is not None and i not in only:
            continue
        m = r.get("match")
        wk = prefix.get(m[5:]) if isinstance(m, str) and m.startswith("bank:") else None
        if (wk and wk in have) or (entry["sha"], i) in rows_in:
            added["already listed"] += 1
            continue
        item = {"by": "owner", "file": entry["sha"], "n": i, "at": time.strftime("%Y-%m-%d %H:%M")}
        if wk:
            item["word_key"] = wk
            added["in the bank"] += 1
        elif m:
            item["site_id"] = m
            added["on the site"] += 1
        else:
            item["row"] = {"question": r.get("question"), "options": r.get("options"), "key": r.get("key")}
            added["new (no match yet)"] += 1
        meta[into].append(item)
    lectures.save(meta)
    return f"{done}\nAdded to {into}: " + ", ".join(f"{v} {k}" for k, v in added.items())


def lecture_shortlist(lecture_id):
    import shortlist
    rows, _ = bank_rows()
    return shortlist.build(lecture_id, rows)


def lecture_send(lecture_id, q):
    import shortlist
    rows, _ = bank_rows()
    return shortlist.send(lecture_id, q, rows)


def set_transcribe(lecture_id, on, q):
    meta = lectures.load(lecture_id)
    meta["transcribe"] = bool(on)
    lectures.save(meta)
    d = lectures.folder(lecture_id)
    if on and (d / "audio.ogg").exists() and not (d / "raw.txt").exists():
        q.add_jobs("transcribe", [{"key": lecture_id, "payload": {"lecture": lecture_id}}])
    return {"transcribe": meta["transcribe"]}


def decisions_of(lecture_id):
    p = lectures.folder(lecture_id) / "fix_decisions.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def pending_fixes(lecture_id):
    """Fixes under 0.9 with their decision so far (the owner's screen)."""
    fixes = read_jsonl(lectures.folder(lecture_id) / "fixes.jsonl") if (lectures.folder(lecture_id) / "fixes.jsonl").exists() else []
    dec = decisions_of(lecture_id)
    return [{"index": i, **f, "decision": dec.get(str(i))} for i, f in enumerate(fixes) if f["confidence"] < checks.APPLY_AT]


def decide_fix(lecture_id, index, take):
    """Keep or take one fix: clean.txt is rewritten and must still pass check_clean, or nothing changes."""
    d = lectures.folder(lecture_id)
    fixes = read_jsonl(d / "fixes.jsonl")
    dec = decisions_of(lecture_id)
    new = {**dec, str(index): "take" if take else "keep"}
    raw, clean = (d / "raw.txt").read_text(encoding="utf-8"), (d / "clean.txt").read_text(encoding="utf-8")
    f = fixes[index]
    was_on = f in checks.applied(fixes, dec)
    now_on = f in checks.applied(fixes, new)
    if was_on != now_on:
        old, rep = (f["meant"], f["heard"]) if was_on else (f["heard"], f["meant"])
        clean = replace_near(clean, f["at"], old, rep)
    errors = checks.check_clean(raw, clean, fixes, new)
    if errors:
        return {"saved": False, "errors": errors}
    (d / "clean.txt").write_text(clean, encoding="utf-8")
    (d / "fix_decisions.json").write_text(json.dumps(new), encoding="utf-8")
    return {"saved": True}


def replace_near(text, at, old, new):
    """Replace the first `old` at or after the paragraph stamped [at]."""
    start = text.find(f"[{at}]")
    start = 0 if start < 0 else start
    m = re.compile(r"(?<!\w)" + re.escape(old) + r"(?!\w)", re.I).search(text, start)
    return text if not m else text[:m.start()] + new + text[m.end():]


# ---- modules, handouts and uploads ---------------------------------------------------------------------------------
MODULE_CODE = re.compile(r"^year\d-[a-z0-9-]+$")
BOOK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
CHUNK = 1 << 20


def module_codes():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    return [c for c in cfg["label_modules"] if not c.endswith("-other")]


def module_list():
    """Every module the site teaches with its handout state: the Handout tab and the module pickers."""
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    out = []
    for code in module_codes():
        d = ROOT / "modules" / code
        lines = d / "lines.jsonl"
        text = lines.read_text(encoding="utf-8").splitlines() if lines.exists() else []
        first = json.loads(text[0]) if text else {}
        out.append({"code": code, "name": cfg["label_modules"][code], "handout": (d / "handout.pdf").exists(),
                    "lines": len(text),
                    "hash": first.get("hash"), "books": len(list((d / "books").glob("*.pdf"))) if (d / "books").exists() else 0})
    return out


def save_upload(stream, size, dest):
    """Streams an uploaded PDF to dest (through a .part file, so a broken upload never replaces a good file)."""
    if size <= 0:
        raise ValueError("empty upload")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    left, head = size, b""
    with open(part, "wb") as f:
        while left:
            chunk = stream.read(min(CHUNK, left))
            if not chunk:
                break
            head = head or chunk[:5]
            f.write(chunk)
            left -= len(chunk)
    if left or head[:4] != b"%PDF":
        part.unlink(missing_ok=True)
        raise ValueError("not a whole PDF file" if left else "not a PDF file")
    part.replace(dest)
    return dest


def put_handout(module, stream, size):
    """Saves modules/<code>/handout.pdf, keeping a replaced handout and its lines under old/<time>/, and splits it."""
    if module not in module_codes():
        return {"error": f"unknown module {module}"}
    d = ROOT / "modules" / module
    new = save_upload(stream, size, d / "handout.new.pdf")
    replaced = (d / "handout.pdf").exists()
    if replaced:
        old = d / "old" / time.strftime("%Y-%m-%d-%H%M%S")
        old.mkdir(parents=True)
        for name in ("handout.pdf", "lines.jsonl"):
            if (d / name).exists():
                (d / name).replace(old / name)
    new.replace(d / "handout.pdf")
    started = background(f"handout {module}", run_dm, "lines", module)
    return {**started, "replaced": replaced}


def put_book(a, stream, size):
    """Saves modules/<code>/books/<id>.pdf and queues it for alignment with its title and doctor (dm.py add books)."""
    module, book = a.get("module", ""), (a.get("book") or "").strip().lower()
    if module not in module_codes():
        return {"error": f"unknown module {module}"}
    if not BOOK_ID.match(book):
        return {"error": "book id: lowercase letters, digits and dashes, e.g. b101"}
    if not (ROOT / "modules" / module / "lines.jsonl").exists():
        return {"error": f"add the {module} handout first (Handout tab)"}
    pages = (a.get("pages") or "").strip()
    if pages and not re.fullmatch(r"\d+-\d+", pages):
        return {"error": "pages: first-last, e.g. 1-200"}
    pdf = save_upload(stream, size, ROOT / "modules" / module / "books" / f"{book}.pdf")
    args = ["add", "books", module, "--book", book, "--file", str(pdf)]
    for k in ("pages", "doctor", "title"):
        if (a.get(k) or "").strip():
            args += [f"--{k}", a[k].strip()]
    return background(f"book {book}", run_dm, *args)


def run_dm(*args):
    res = subprocess.run(["py", str(ROOT / "dm.py"), *args], capture_output=True, text=True, cwd=ROOT,
                         encoding="utf-8", errors="replace")
    return (res.stdout + res.stderr).strip()


def doctors(reader):
    """The site's doctors for the book form: doctorId (what importSiteBook.ts --doctor takes) and English name."""
    try:
        return [{"id": r["doctorId"], "name": r.get("nameEn")} for r in
                reader.find("doctorprofiles", {}, {"doctorId": 1, "nameEn": 1}, limit=500, sort=[("nameEn", 1)])]
    except Exception:  # noqa: BLE001 - the form still takes a typed doctor id
        return []


# ---- polls and the question bank -----------------------------------------------------------------------------------
POLLS_READY = ROOT / "polls" / "ready"
BANK = ROOT / "bank"
DECISIONS = BANK / "key_decisions.json"
_CONFLICTS = {"mtime": None, "rows": []}


def polls_summary():
    """Counts only: the finished polls job, its channels, and the merged bank."""
    rows = keyed = conflicts = 0
    chans = {}
    qf = POLLS_READY / "questions.jsonl"
    if qf.exists():
        with qf.open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                rows += 1
                keyed += r.get("key") is not None
                conflicts += bool(r.get("key_conflict"))
                for c in {s.get("chat") for s in r.get("sightings", [])}:
                    chans[c] = chans.get(c, 0) + 1
    hf = POLLS_READY / "held.jsonl"
    held = len(hf.read_text(encoding="utf-8").splitlines()) if hf.exists() else 0
    bank = json.loads((BANK / "counts.json").read_text(encoding="utf-8")) if (BANK / "counts.json").exists() else {}
    return {"polls": {"questions": rows, "keyed": keyed, "key_conflicts": conflicts, "held": held,
                      "channels": dict(sorted(chans.items(), key=lambda x: -x[1])),
                      "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(qf.stat().st_mtime)) if qf.exists() else None},
            "bank": bank, "decided": len(key_decisions())}


def key_decisions():
    return json.loads(DECISIONS.read_text(encoding="utf-8")) if DECISIONS.exists() else {}


def conflicts():
    """The bank's key conflicts, each with its options, votes, sightings and the owner's decision so far."""
    qf = BANK / "questions.jsonl"
    if not qf.exists():
        return []
    m = qf.stat().st_mtime
    if _CONFLICTS["mtime"] != m:
        rows = []
        with qf.open(encoding="utf-8") as f:
            for line in f:
                if '"key_conflict": true' not in line and '"key_source": "owner"' not in line:
                    continue
                q = json.loads(line)
                if q.get("key_conflict") or q.get("key_source") == "owner":
                    rows.append({"id": q["word_key"], "question": q["question"], "options": q["options"], "votes": q["votes"],
                                 "total": q["total"], "key": q["key"], "solution": q.get("solution"),
                                 "links": [s["link"] for s in q["sightings"] if s.get("link")][:5]})
        _CONFLICTS.update(mtime=m, rows=rows)
    dec = key_decisions()
    return [{**r, "decision": dec.get(r["id"], {}).get("key")} for r in _CONFLICTS["rows"]]


def decide_key(word_key, key):
    """The owner's key for one conflict (an option index), or None to undo. merge.build applies it on the next bank."""
    dec = key_decisions()
    if key is None:
        dec.pop(word_key, None)
    else:
        dec[word_key] = {"key": int(key), "at": time.strftime("%Y-%m-%d %H:%M")}
    BANK.mkdir(exist_ok=True)
    DECISIONS.write_text(json.dumps(dec, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"saved": True, "decided": len(dec)}


# ---- books, progress, gap map --------------------------------------------------------------------------------------
def books(q):
    """Each queued book with its title, doctor and percent aligned (pages in passed jobs / pages queued)."""
    out = {}
    for r in q.db.execute("SELECT key, payload, status FROM jobs WHERE flow='books'"):
        p = json.loads(r["payload"])
        b = out.setdefault((p["module"], p["book_id"]), {"module": p["module"], "book": p["book_id"], "pages": 0,
                                                         "aligned": 0, "held": 0})
        b["pages"] += len(p["pages"])
        b["aligned"] += len(p["pages"]) if r["status"] == "passed" else 0
        b["held"] += len(p["pages"]) if r["status"] == "held" else 0
    for b in out.values():
        b["percent"] = round(100 * b["aligned"] / b["pages"], 1) if b["pages"] else 0.0
        meta = ROOT / "modules" / b["module"] / "books" / f"{b['book']}.json"
        m = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
        b["title"], b["doctor"] = m.get("title"), m.get("doctor")
    return sorted(out.values(), key=lambda b: (b["module"], b["book"]))


FLEET = {"proc": None}  # the dispatcher this page started (py dm.py run)


def fleet_running():
    p = FLEET["proc"]
    return bool(p and p.poll() is None)


def fleet(action):
    """Start: runs `py dm.py run` in the background (log jobs/run.out). Stop: jobs/stop.flag; running jobs finish first."""
    jobs = ROOT / "jobs"
    jobs.mkdir(exist_ok=True)
    if action == "start" and not fleet_running():
        log = open(jobs / "run.out", "a", encoding="utf-8")
        FLEET["proc"] = subprocess.Popen(["py", str(ROOT / "dm.py"), "run"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif action == "stop" and fleet_running():
        (jobs / "stop.flag").touch()
    return {"running": fleet_running(), "stopping": (jobs / "stop.flag").exists() and fleet_running()}


def progress(q):
    import dispatch
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    accounts = [{"account": a, "lane": cfg["lanes"].get(a), "slots": n, "cooling": dispatch.cooling(dispatch.FLEET / "state.json", a),
                 "running": q.db.execute("SELECT COUNT(*) FROM jobs WHERE status='running' AND account=?", (a,)).fetchone()[0]}
                for a, n in cfg["slots"].items()]
    done = q.db.execute("SELECT flow, AVG(finished-started) s FROM jobs WHERE status='passed' GROUP BY flow").fetchall()
    per = {r["flow"]: r["s"] for r in done}
    flows = q.progress()
    slots = sum(cfg["slots"].values())
    left = sum(per.get(f, 0) * (c.get("queued", 0) + c.get("running", 0)) for f, c in flows.items())
    return {"flows": flows, "accounts": accounts, "hours_left": round(left / slots / 3600, 1) if per else None,
            "fleet": {"running": fleet_running(), "stopping": (ROOT / "jobs" / "stop.flag").exists() and fleet_running()}}


def gap_map(reader, module):
    """Per handout page: questions pointed at it (site), doctor book lines on it (site), lecture parts on it (local)."""
    lines_file = ROOT / "modules" / module / "lines.jsonl"
    if not lines_file.exists():
        return {"pages": [], "error": f"run `py dm.py lines {module}` first"}
    pages = sorted({json.loads(x)["page"] for x in open(lines_file, encoding="utf-8")})
    m = reader.find("academicmodules", {"code": module}, {"_id": 1}, limit=1)
    mid = m[0]["_id"] if m else None
    qs = {r["_id"]: r["n"] for r in reader.aggregate("questions", [
        {"$match": {"academicModule": mid, "book_found": True}}, {"$unwind": "$book_refs"},
        {"$group": {"_id": "$book_refs.pdf_page", "n": {"$sum": 1}}}])} if mid else {}
    book_ids = [b["_id"] for b in reader.find("sitebooks", {"academicModule": mid, "kind": {"$ne": "handout"}}, {"_id": 1}, limit=200)] if mid else []
    bk = {r["_id"]: r["n"] for r in reader.aggregate("bookalignmentpages", [
        {"$match": {"book": {"$in": book_ids}}}, {"$unwind": "$handoutPages"},
        {"$group": {"_id": "$handoutPages", "n": {"$sum": 1}}}])} if book_ids else {}
    page_of = {}
    for x in open(lines_file, encoding="utf-8"):
        ln = json.loads(x)
        page_of[ln["id"]] = ln["page"]
    lec = {}
    for f in lectures.LECTURES.glob("*/parts.jsonl"):
        for p in read_jsonl(f):
            for pg in {page_of.get(i) for i in p["line_ids"]} - {None}:
                lec[pg] = lec.get(pg, 0) + 1
    return {"pages": [{"page": p, "questions": qs.get(p, 0), "book": bk.get(p, 0), "lecture": lec.get(p, 0)} for p in pages]}


# ---- coverage, voters, lecture questions ---------------------------------------------------------------------------
def save_cover_file(name, content):
    inbox = ROOT / "bank" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / re.sub(r"[^\w.-]", "_", name)
    path.write_text(content, encoding="utf-8")
    return path


def run_cover(path):
    res = subprocess.run(["py", str(ROOT / "dm.py"), "cover", str(path)], capture_output=True, text=True, cwd=ROOT)
    return (res.stdout + res.stderr).strip()


def covered_list():
    seen = {}
    for e in read_jsonl(ROOT / "bank" / "covered.jsonl") if (ROOT / "bank" / "covered.jsonl").exists() else []:
        seen[e["sha"]] = e  # the latest entry per file wins (after the fleet pass)
    return list(seen.values())


def lecture_questions(reader, lesson):
    from bson import ObjectId
    if not OID.match(lesson or ""):
        return {"required": [], "extra": []}
    rows = reader.find("lecturequestions", {"lesson": ObjectId(lesson)}, {"question": 1, "kind": 1, "parts": 1}, limit=500)
    out = {"required": [], "extra": []}
    for r in rows:
        out[r["kind"]].append({"question": str(r["question"]), "parts": r.get("parts", [])})
    return out


def set_required(lesson, ids, remove=False):
    """The owner's hand-picked questions for one lecture, through the site importer (applied)."""
    if not OID.match(lesson or ""):
        return {"error": "lesson id"}
    rows = [{"question_id": i, **({"remove": True} if remove else {})} for i in ids if OID.match(i)]
    path = ROOT / "bank" / f"required_{lesson}.jsonl"
    path.parent.mkdir(exist_ok=True)
    write_jsonl(path, rows)
    return importer("required", "--lesson", lesson, "--file", str(path), "--apply")


def importer(kind, *args):
    import os
    import tempfile
    # NODE_OPTIONS splits on spaces, and ROOT sits under "Tumrah projects": keep the preload in the temp folder.
    dns = Path(tempfile.gettempdir()) / "tumrah_data_dns.cjs"
    dns.write_text('require("dns").setServers(["1.1.1.1"]);\n', encoding="utf-8")
    res = subprocess.run(["node", "../node_modules/tsx/dist/cli.mjs", "src/scripts/importHubData.ts", kind, *args],
                         cwd=BACKEND, capture_output=True, text=True, env={**os.environ, "NODE_OPTIONS": f"--require {dns}"})
    last = (res.stdout.strip().splitlines() or [""])[-1]
    try:
        return json.loads(last)
    except ValueError:
        return {"error": (res.stderr or res.stdout).strip()[-300:]}


# ---- importance highlights ------------------------------------------------------------------------------------------
def highlight_lessons(module, q):
    lines = highlights.module_lines(module) if (ROOT / "modules" / module / "lines.jsonl").exists() else []
    return [{**L, "lectures": len(highlights.lesson_lectures(module, L["pages"], lines)),
             "state": highlights.state(q, L["key"]), "summary": highlights.summary(module, L["key"])}
            for L in highlights.lessons(module)]


def queue_highlights(reader, module, keys):
    q = queue_db.Queue()
    try:
        queued = [highlights.queue(q, reader, L) for L in highlights.lessons(module) if L["key"] in keys]
    finally:
        q.close()
    return f"{sum(bool(k) for k in queued)} queued, {sum(not k for k in queued)} already waiting. Run py dm.py run."


# ---- HTTP ------------------------------------------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    reader = None

    def log_message(self, *args):
        pass

    def reply(self, body, kind="application/json", code=200):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def get_reader(self):
        if Handler.reader is None:
            import db
            Handler.reader = db.Reader.live()
        return Handler.reader

    def do_GET(self):
        u = urlparse(self.path)
        a = {k: v[0] for k, v in parse_qs(u.query).items()}
        q = queue_db.Queue()
        try:
            if u.path == "/":
                return self.reply((ROOT / "page.html").read_bytes(), "text/html; charset=utf-8")
            routes = {
                "/api/progress": lambda: progress(q),
                "/api/questions": lambda: questions(self.get_reader(), module=a.get("module"), doctor=a.get("doctor"),
                                                    test_type=a.get("set"), pointer=a.get("pointer"), after=a.get("after")),
                "/api/lectures": lambda: lecture_list(q),
                "/api/lecture-bank": lambda: lecture_bank(a["id"], a.get("text", ""), int(a.get("page", 0))),
                "/api/lecture-picks": lambda: lecture_picks(a["id"]),
                "/api/fixes": lambda: pending_fixes(a["lecture"]),
                "/api/books": lambda: books(q),
                "/api/gap": lambda: gap_map(self.get_reader(), a.get("module", "year2-cns")),
                "/api/covered": covered_list,
                "/api/lecture-questions": lambda: lecture_questions(self.get_reader(), a.get("lesson")),
                "/api/jobs": lambda: JOBS,
                "/api/highlights": lambda: highlight_lessons(a.get("module", "year2-cns"), q),
                "/api/highlight-view": lambda: highlights.preview(a["module"], a["key"]),
                "/api/modules": module_list,
                "/api/doctors": lambda: doctors(self.get_reader()),
                "/api/polls": polls_summary,
                "/api/conflicts": conflicts,
                "/api/today": lambda: decisions.today(a.get("module", "year2-cns"), 0 if a.get("fresh") else 600),
                "/api/review": lambda: decisions.review_items(a.get("kind", "spot"), a.get("module", "year2-cns")),
                "/api/control": control.look,
                "/api/control/chat": lambda: control.chat(int(a.get("since", 0))),
                "/api/control/log": lambda: control.run_log(a.get("id"), int(a.get("since", 0))),
            }
            if u.path in routes:
                return self.reply(routes[u.path]())
            return self.reply({"error": "not found"}, code=404)
        finally:
            q.close()

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin != f"http://127.0.0.1:{self.server.server_port}":
            return self.reply({"error": "other site"}, code=403)  # a web page must not drive this
        size = int(self.headers.get("Content-Length") or 0)
        u = urlparse(self.path)
        if u.path in ("/api/handout", "/api/book"):  # the body is the PDF itself; the form fields ride in the query
            a = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                if u.path == "/api/handout":
                    return self.reply(put_handout(a.get("module", ""), self.rfile, size))
                return self.reply(put_book(a, self.rfile, size))
            except ValueError as e:
                return self.reply({"error": str(e)})
        b = json.loads(self.rfile.read(size) or "{}")
        q = queue_db.Queue()
        try:
            if self.path.startswith("/api/control/"):  # the Claude tab (control.py)
                op = self.path.rsplit("/", 1)[1]
                acts = {"run": lambda: control.run(b.get("key")), "stop-run": lambda: control.stop_run(b.get("id")),
                        "ask": lambda: control.ask(b.get("text")), "stop": control.stop_claude, "new": control.new_chat,
                        "board": lambda: control.board_op(b.get("op"), b.get("id"), b.get("text"), b.get("state"))}
                return self.reply(acts[op]() if op in acts else {"error": "not found"})
            if self.path == "/api/decide":  # one click on a Today card
                r = decisions.answer(b["id"], int(b.get("choice", 0)), b.get("value"))
                if r.get("run") == "ai":
                    background("ai work", runners.run_ai)
                    r = {"job": "ai work"}
                return self.reply(r)
            if self.path == "/api/review":
                return self.reply(decisions.review_answer(b["kind"], b["src"], b.get("pick") or {}))
            if self.path == "/api/key":
                return self.reply(decide_key(b["id"], b.get("key")))
            if self.path == "/api/bank":
                return self.reply(background("bank", run_dm, "bank"))
            if self.path == "/api/handover":
                return self.reply(handover(self.get_reader(), b["module"], b.get("ids", [])))
            if self.path == "/api/lecture":
                cmd = ["py", str(ROOT / "dm.py"), "lecture", b["id"], "--module", b["module"], "--title", b.get("title") or b["id"]]
                for k in ("file", "youtube", "lesson", "pages", "doctor"):
                    if b.get(k):
                        cmd += [f"--{k}", str(b[k])]
                if not b.get("transcribe", True):
                    cmd.append("--no-transcribe")
                return self.reply(background(f"lecture {b['id']}", lambda: subprocess.run(
                    cmd, capture_output=True, text=True, cwd=ROOT).stdout.strip()))
            if self.path == "/api/lecture-new":
                return self.reply(new_lecture(b, q))
            if self.path == "/api/lecture-pages":
                return self.reply(set_pages(b["id"], b.get("pages")))
            if self.path == "/api/pick":
                return self.reply(pick(b["id"], b["word_key"], b.get("into")))
            if self.path == "/api/lecture-file":
                return self.reply(add_file(b["id"], b.get("into"), b.get("name", "sheet.jsonl"), b.get("content", "")))
            if self.path == "/api/lecture-shortlist":
                return self.reply(background(f"shortlist {b['id']}", lecture_shortlist, b["id"]))
            if self.path == "/api/lecture-send":
                try:
                    return self.reply(lecture_send(b["id"], q))
                except ValueError as e:
                    return self.reply({"error": str(e)})
            if self.path == "/api/transcribe":
                return self.reply(set_transcribe(b["id"], b.get("on", True), q))
            if self.path == "/api/fix":
                return self.reply(decide_fix(b["lecture"], int(b["index"]), bool(b["take"])))
            if self.path == "/api/cover":
                path = save_cover_file(b["name"], b["content"])
                return self.reply(background("coverage", run_cover, path))
            if self.path == "/api/voters":
                import voters
                return self.reply(background("voters", voters.run, bool(b.get("apply"))))
            if self.path == "/api/fleet":
                return self.reply(fleet(b.get("action")))
            if self.path == "/api/highlight":
                return self.reply(background("highlight", queue_highlights, self.get_reader(), b["module"], b.get("keys", [])))
            if self.path == "/api/required":
                return self.reply(set_required(b.get("lesson"), b.get("ids", []), bool(b.get("remove"))))
            return self.reply({"error": "not found"}, code=404)
        finally:
            q.close()


def serve():
    control.start()
    print(f"Data admin page: http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

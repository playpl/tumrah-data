"""The data admin page: http://127.0.0.1:8770 (py dm.py page). Local only; reads the live site through db.py and
writes it only through the tumrah repo's importers.

Screens: Questions (filter, tick, Hand over), Lectures (add, Transcribe), Word fixes, Books (% aligned), Coverage,
Voters, Lecture questions, Gap map, Progress.
"""
import json
import re
import subprocess
import threading
import time
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import checks
import lectures
import queue_db
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
def lecture_list():
    out = []
    for f in sorted(lectures.LECTURES.glob("*/lecture.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        d = f.parent
        stage = "aligned" if (d / "links.jsonl").exists() else "transcribed" if (d / "raw.txt").exists() else \
            "waiting" if m.get("transcribe") else "not transcribed"
        out.append({**{k: m.get(k) for k in ("id", "module", "title", "lesson", "pdf_pages", "transcribe", "duration_s",
                                              "report", "fixes")}, "stage": stage})
    return out


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


# ---- books, progress, gap map --------------------------------------------------------------------------------------
def books(q):
    """Each queued book with its percent aligned (pages in passed jobs / pages queued)."""
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
    return sorted(out.values(), key=lambda b: (b["module"], b["book"]))


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
    return {"flows": flows, "accounts": accounts, "hours_left": round(left / slots / 3600, 1) if per else None}


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
    dns = ROOT / "tools_dns.cjs"
    dns.write_text('require("dns").setServers(["1.1.1.1"]);\n', encoding="utf-8")
    import os
    res = subprocess.run(["node", "../node_modules/tsx/dist/cli.mjs", "src/scripts/importHubData.ts", kind, *args],
                         cwd=BACKEND, capture_output=True, text=True, env={**os.environ, "NODE_OPTIONS": f"--require {dns}"})
    last = (res.stdout.strip().splitlines() or [""])[-1]
    try:
        return json.loads(last)
    except ValueError:
        return {"error": (res.stderr or res.stdout).strip()[-300:]}


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
                "/api/lectures": lecture_list,
                "/api/fixes": lambda: pending_fixes(a["lecture"]),
                "/api/books": lambda: books(q),
                "/api/gap": lambda: gap_map(self.get_reader(), a.get("module", "year2-cns")),
                "/api/covered": covered_list,
                "/api/lecture-questions": lambda: lecture_questions(self.get_reader(), a.get("lesson")),
                "/api/jobs": lambda: JOBS,
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
        b = json.loads(self.rfile.read(size) or "{}")
        q = queue_db.Queue()
        try:
            if self.path == "/api/handover":
                return self.reply(handover(self.get_reader(), b["module"], b.get("ids", [])))
            if self.path == "/api/lecture":
                cmd = ["py", str(ROOT / "dm.py"), "lecture", b["id"], "--module", b["module"], "--title", b.get("title") or b["id"]]
                for k in ("file", "youtube", "lesson", "pages"):
                    if b.get(k):
                        cmd += [f"--{k}", str(b[k])]
                if not b.get("transcribe", True):
                    cmd.append("--no-transcribe")
                return self.reply(background(f"lecture {b['id']}", lambda: subprocess.run(
                    cmd, capture_output=True, text=True, cwd=ROOT).stdout.strip()))
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
            if self.path == "/api/required":
                return self.reply(set_required(b.get("lesson"), b.get("ids", []), bool(b.get("remove"))))
            return self.reply({"error": "not found"}, code=404)
        finally:
            q.close()


def serve():
    print(f"Data admin page: http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

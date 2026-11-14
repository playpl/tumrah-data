"""Queue jobs done by Gemini on the web while the Antigravity fleet is down (owner, 2026-11-10).

Gemini web (C:/Users/Ahmed/gemini-web/gweb, 4 accounts, one Google session) is a chat: it reads attached files but has no
tools. So each job is turned into one self-contained prompt, Gemini answers in a compact form, code rebuilds the
flow's own output file from that answer, and the flow's own checker decides as always. A Gemini PASS is never trusted.

    py gemini_run.py pieces [--workers 8] [--model flash-lite] [--limit N]   transcribe: cut queued lectures, hear pieces
    py gemini_run.py place [--model carbon] [--dry]                          all queued place jobs in one call
    py gemini_run.py books [--model carbon] [--workers 4] [--limit N]        align book pages, one job per call
    py gemini_run.py links [--model carbon] [--workers 4] [--limit N]        transcript parts -> handout lines
    py gemini_run.py bounds [--limit N] [--dry]                              what each recording covers, as outline sections
    py gemini_run.py pointers [--limit CALLS] [--per-call 40] [--dry]        questions -> handout lines, one handout lecture per call
    py gemini_run.py status

bounds and pointers write ledger rows (ledger.py, runner "web"), not queue jobs: a lecture or question with a web row
is done, so a rerun only takes what is left.

links: clean.txt is raw.txt unchanged and fixes.jsonl stays empty (misheard-word fixes are not asked for yet).

Owner's model rule: transcription = 3.5 Flash-Lite; everything that needs thought = Argon only, never 3.1 Pro or 4 Carbon
(Carbon used up three accounts' 5-hour usage in 20 minutes, 2026-11-10). Pointers and aligning: big chunks per call.
Claude never reads question text or Arabic: this file prints counts and ids only.
"""
import argparse
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import checks
import lectures
import queue_db
from flows import REGISTRY, common

ROOT = Path(__file__).resolve().parent
GWEB = r"C:\Users\Ahmed\gemini-web\.venv\Scripts\python.exe"
GWEB_PY = r"C:\Users\Ahmed\gemini-web\gweb.py"
NOTE = "gemini web"
LOG = ROOT / "jobs" / "gemini_run.log"
MIN_CHARS_PER_MIN = 450   # the fleet's passed CNS transcripts: 530-1285; a condensed (summarised) answer falls under this
_log_lock = threading.Lock()


def log(*parts):
    line = time.strftime("%H:%M:%S ") + " ".join(str(p) for p in parts)
    with _log_lock:
        print(line, flush=True)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# Measured 2026-11-10: ~20 Flash-Lite pieces moved an account's 5-hour usage by 2%; a few Carbon calls moved accounts to
# 70-93%. An account at 100% stops transcribing too, so a heavy call only goes to an account under HEAVY_CAP.
HEAVY_CAP = 80
# Owner 2026-11-10: "Do not use 3.1 or Carbon. Use Argon only. Carbon is what fucked up the usage." Transcription stays
# on 3.5 Flash-Lite. Argon was not in any account's model list on 2026-11-10 (only Flash-Lite, Flash, 3.1 Pro, 4 Carbon):
# heavy steps then fail with "model 'argon' not found" and their jobs stay queued.
ALLOWED_MODELS = {"flash-lite", "gemini-flash-lite", "flash", "gemini-flash"}  # owner 2026-11-10: "we will use 3.8 flash, no more Argon"
_heavy_lock = threading.Lock()


# `work` (/u/1) answers 3.8 Flash and Argon with error cards (gemini-web notes 2026-11-05; again 2026-11-10), and an error
# card rests the account for 5 minutes, which also stops its transcription: heavy calls never go there.
HEAVY_SKIP = {"work"}


def heavy_account():
    """The usable account (not in HEAVY_SKIP) with the lowest 5-hour usage under HEAVY_CAP, or None."""
    try:
        run = subprocess.run([GWEB, GWEB_PY, "status", "--json"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=120)
        rows = json.loads(run.stdout)
    except (subprocess.TimeoutExpired, ValueError):
        return None
    ok = [r for r in rows if r.get("usable") and r.get("cause") != "cookie_dead"  # gweb keeps `usable` on a dead login
          and r.get("slot") not in HEAVY_SKIP and (r.get("used_5h") or 0) < HEAVY_CAP]
    return min(ok, key=lambda r: r.get("used_5h") or 0)["slot"] if ok else None


def ask(prompt_file, model, attach=(), timeout=1500, account=None):
    """(text, meta) from one fresh, temporary Gemini chat; text None on failure (meta holds the error).
    Any model but Flash-Lite waits for an account under HEAVY_CAP (never `work`) and stays on it."""
    if model.lower() not in ALLOWED_MODELS:
        return None, {"error": f"model {model} is not allowed (owner 2026-11-10: 3.8 Flash or 3.5 Flash-Lite only)"}
    cmd = [GWEB, GWEB_PY, "ask", "--json", "--temporary", "-m", model, "-f", str(prompt_file)]
    if "lite" not in model:
        cmd.append("-t")  # owner 2026-11-10: 3.8 Flash "set it on high" = extended thinking
    if "lite" not in model and not account:
        while True:
            with _heavy_lock:
                account = heavy_account()
            if account:
                break
            log("heavy call waits: every account is at", HEAVY_CAP, "% of its 5-hour usage or resting")
            time.sleep(300)
        cmd += ["-a", account]
    elif account:
        cmd += ["-a", account, "--fallback"]
    for a in attach:
        cmd += ["--attach", str(a)]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, {"error": "timeout"}
    try:
        out = json.loads(run.stdout)
    except ValueError:
        return None, {"error": (run.stderr or run.stdout).strip()[-300:], "code": run.returncode}
    text = out.get("text")
    return (text if run.returncode == 0 and text else None), {k: out.get(k) for k in ("account", "model", "secs")}


def strip_fence(text):
    m = re.search(r"```(?:json|jsonl)?\s*\n(.*?)```", text, re.S)
    return m.group(1) if m else text


# ---- transcription -------------------------------------------------------------------------------------------
# Tested 2026-11-10 on one piece: asked for timestamps, 3.5 Flash-Lite condensed the speech to ~280-360 characters a
# minute (3 of 3 runs); asked for plain paragraphs it wrote ~545 a minute (3 of 3, the fleet's CNS transcripts: 530-1285).
# So Gemini writes paragraphs only and code sets each paragraph's [mm:ss] inside the piece by character position. The
# piece's own offset in the lecture stays exact (pieces are cut at 5:00), so a time is off by seconds, not minutes.
PIECE_PROMPT = """The attached audio is a 5-minute piece of a recorded medical lecture (Egyptian Arabic mixed with English medical terms).
Write a full verbatim transcript of it: every single word as spoken, from the first second to the last (Arabic speech in Arabic script, English terms in English). This is word-for-word dictation, not notes: never summarise, shorten, translate, correct or skip anything, including repetitions and side remarks.
Split it into short paragraphs (a new paragraph every few sentences), separated by blank lines. No timestamps, no speaker names.
If the piece has no speech at all, reply with exactly: SILENT
Reply with the transcript only: no heading, no notes, no code block.
"""
PARA_SECONDS = 30


def piece_text(answer, seconds):
    """Gemini's plain paragraphs as the flow's [mm:ss] paragraphs ('' for a silent piece). Too few paragraphs are
    re-cut by words into ~30-second ones; each start time is the piece length times the share of text before it."""
    if answer.strip().upper().strip(".") == "SILENT":
        return ""
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n|\n", strip_fence(answer)) if p.strip()]
    want = max(1, round(seconds / PARA_SECONDS))
    if len(paras) < want / 2 or max(len(p) for p in paras) > 0.25 * sum(len(p) for p in paras):
        words = " ".join(paras).split()
        size = max(1, -(-len(words) // want))
        paras = [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
    total = sum(len(p) for p in paras) or 1
    out, before = [], 0
    for p in paras:
        t = int(seconds * before / total)
        out.append(f"[{t // 60:02d}:{t % 60:02d}] {p}")
        before += len(p)
    return "\n".join(out) + "\n"


def expand_transcribe(q):
    """Code-only step: cut each queued lecture into 5-minute pieces and queue the piece jobs."""
    flow, n = REGISTRY["transcribe"], 0
    while True:
        job = q.claim("transcribe", "code", only=True)
        if job is None:
            return n
        try:
            for name, jobs in flow.expand(job):
                q.add_jobs(name, jobs)
            q.finish(job["id"], "passed", NOTE)
            n += 1
        except Exception as e:  # noqa: BLE001 - a lecture whose audio cannot be cut waits for a look
            q.finish(job["id"], "held", f"cut failed: {type(e).__name__}: {e}"[:300])
            log("transcribe", job["key"], "held: cut failed")


def run_piece(q, job, model, tries=3):
    flow = REGISTRY["piece"]
    d = ROOT / "jobs" / "piece" / job["key"]
    d.mkdir(parents=True, exist_ok=True)
    flow.prepare(job, d)
    prompt = d / "gemini_prompt.txt"
    prompt.write_text(PIECE_PROMPT, encoding="utf-8")
    seconds = lectures.duration(d / "piece.ogg")
    last = "no answer"
    for t in range(1, tries + 1):
        answer, meta = ask(prompt, model, [d / "piece.ogg"], timeout=900)
        if answer is None:
            last = f"gemini: {meta.get('error')}"[:200]
            if "no account ready" in last:  # every account rests: not the job's fault, no try counted
                q.release(job["id"])
                log("piece", job["key"], "released: no account ready")
                time.sleep(300)
                return None
            log("piece", job["key"], f"try {t}", last)
            continue
        text = piece_text(answer, seconds)
        body = sum(len(b) for _, b in checks.paragraphs(text))
        rate = body / max(seconds / 60, 1)
        if seconds > 90 and rate < MIN_CHARS_PER_MIN:  # an empty answer is condensed too (it passed as 0 chars/min before)
            last = f"condensed: {rate:.0f} chars/min"
            log("piece", job["key"], f"try {t}", last, meta.get("account"))
            continue
        (d / "piece.txt").write_text(text, encoding="utf-8")
        errors = flow.check(job, d)
        if errors:
            last = "; ".join(errors)[:200]
            log("piece", job["key"], f"try {t}", "check:", last)
            continue
        q.finish(job["id"], "passed", f"{NOTE} {meta.get('model')} {meta.get('account')}")
        for name, jobs in flow.then(job, d):
            q.add_jobs(name, jobs)
        log("piece", job["key"], "passed", f"{rate:.0f} chars/min", meta.get("account"), f"{meta.get('secs')}s")
        return True
    q.finish(job["id"], "failed", last)
    return False


def pieces(args):
    q = queue_db.Queue()
    if not args.no_cut:
        q.recover()
        log("transcribe: cut", expand_transcribe(q), "lectures")
    stats = {"passed": 0, "failed": 0}
    left = [args.limit or 10 ** 9]
    lock = threading.Lock()

    def worker():
        wq = queue_db.Queue()
        while True:
            with lock:
                if left[0] <= 0 or (ROOT / "jobs" / "gemini.stop").exists():
                    break
                left[0] -= 1
            job = wq.claim("piece", f"gemini-{threading.current_thread().name}", only=True)
            if job is None:
                break
            try:
                ok = run_piece(wq, job, args.model)
            except Exception as e:  # noqa: BLE001 - one bad job never stops the worker
                wq.finish(job["id"], "failed", f"gemini_run: {type(e).__name__}: {e}"[:300])
                ok = False
            if ok is None:
                continue  # released while every account rests
            with lock:
                stats["passed" if ok else "failed"] += 1
        wq.close()

    threads = [threading.Thread(target=worker, name=str(i)) for i in range(args.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log("pieces done", stats, q.progress().get("piece"))
    q.close()


# ---- handout as text ----------------------------------------------------------------------------------------
def handout_text(module, path, ids=False):
    """The module's handout as one text file: a header per pdf page, then its lines. With ids, every line starts with
    a short label <pdf page>.<n> (figures <pdf page>.F<n>) the answer can name."""
    rows = common.read_jsonl(common.module_dir(module) / "lines.jsonl")
    out, page, labels = [], None, {}
    for ln in rows:
        if ln["page"] != page:
            page = ln["page"]
            out.append(f"\n=== pdf_page {page} (printed page {ln.get('printed')}) ===")
        fig = ln.get("figure")
        label = f"{ln['page']}.{'F' if fig is not None else ''}{ln['n']}"
        labels[label] = ln
        body = f"[FIGURE: {fig}]" if fig is not None else ln["text"]
        out.append(f"{label} {body}" if ids else body)
    Path(path).write_text("\n".join(out).strip() + "\n", encoding="utf-8")
    return labels


# ---- place ---------------------------------------------------------------------------------------------------
PLACE_PROMPT = """You are helping build a study website for medical students (module: CNS & Special Senses, year 2).
The attached file handout.txt is the whole handout (the College Book) as text. Each page starts with a header line
"=== pdf_page N (printed page P) ===". Use the pdf_page numbers, never the printed ones.

Below are {n} recorded lectures. For EACH lecture, find the handout pages that lecture teaches: the page where its topic
starts and the last page before the next topic starts. Read the contents pages and the headings; the title words alone
are not enough. Usually one range; give two or more only when the handout teaches the lecture in separate places (in
handout order, never overlapping). A doctor's lessons of one chapter usually follow each other: give each lesson only its
own share of the chapter. If the handout does not teach a lecture, give the closest pages and say so in the note.
{placed}
LECTURES (id | subject | doctor | chapter | title | the doctor's lessons of this chapter, in order):
{lectures}

Answer with one JSON object only, no other text:
{{"<lecture id>": {{"ranges": [{{"first_page": <pdf page>, "last_page": <pdf page>}}], "note": "<how you found it: which contents entry or headings start and end it, 6 to 40 words, English>"}}, ...}}
Every lecture id above must be a key."""


def place(args):
    flow = REGISTRY["place"]
    q = queue_db.Queue()
    rows = q.db.execute("SELECT id, flow, key, payload FROM jobs WHERE flow='place' AND status='queued' "
                        "ORDER BY added").fetchall()
    if not rows:
        log("place: nothing queued")
        return
    metas = [lectures.load(json.loads(r["payload"])["lecture"]) for r in rows]
    module = metas[0]["module"]
    d = ROOT / "jobs" / "gemini" / "place"
    d.mkdir(parents=True, exist_ok=True)
    handout_text(module, d / "handout.txt")
    placed = [m for m in lectures.all_lectures(module) if m.get("ranges") and m["id"] not in {x["id"] for x in metas}]
    placed_txt = ("\nThese lectures are already placed (other lectures may share or follow their pages):\n" +
                  "".join(f"- {m['title']} ({m.get('subject')}): pdf pages "
                          f"{', '.join(f'{a}-{b}' for a, b in lectures.page_ranges(m))}\n" for m in placed)) if placed else ""
    lines = "".join(f"{m['id']} | {m.get('subject') or '-'} | {m.get('doctor') or '-'} | {m.get('chapter') or '-'} | "
                    f"{m['title']} | {'; '.join(m.get('chapter_lessons') or []) or '-'}\n" for m in metas)
    prompt = d / "prompt.txt"
    prompt.write_text(PLACE_PROMPT.format(n=len(metas), placed=placed_txt, lectures=lines), encoding="utf-8")
    if args.dry:
        log("place: dry run, prompt at", prompt)
        return
    answer, meta = ask(prompt, args.model, [d / "handout.txt"], timeout=2400)
    if answer is None:
        log("place: gemini failed", meta)
        return
    (d / "answer.txt").write_text(answer, encoding="utf-8")
    try:
        got = json.loads(strip_fence(answer))
    except ValueError as e:
        log("place: answer is not JSON", e)
        return
    ok = bad = 0
    for r in rows:
        job = {"id": r["id"], "flow": "place", "key": r["key"], "payload": json.loads(r["payload"])}
        jd = ROOT / "jobs" / "place" / r["key"]
        jd.mkdir(parents=True, exist_ok=True)
        flow.prepare(job, jd)
        ans = got.get(job["payload"]["lecture"])
        if ans is None:
            log("place", r["key"], "no answer")
            bad += 1
            continue
        (jd / "place.json").write_text(json.dumps(ans, ensure_ascii=False), encoding="utf-8")
        errors = flow.check(job, jd)
        if errors:
            log("place", r["key"], "check:", "; ".join(errors)[:200])
            bad += 1
            continue
        q.finish(r["id"], "passed", f"{NOTE} {meta.get('model')}")
        for name, jobs in flow.then(job, jd):
            q.add_jobs(name, jobs)
        ok += 1
    log("place:", ok, "passed,", bad, "left queued", meta)
    q.close()


# ---- books (alignment) ---------------------------------------------------------------------------------------
BOOK_PROMPT = """You are helping build a study website for medical students. The handout (the College Book) is the root: a
doctor's book is shown beside it, line by line, so a student sees which handout lines each book line teaches.

The attached handout.txt is the whole handout. Each page starts with "=== pdf_page N (printed page P) ===" and every
line starts with its label (<pdf page>.<n>, figures <pdf page>.F<n>).
{reference}
Below are {n} pages of a doctor's book, cut into numbered blocks (one printed line each). For EVERY block decide:
- "same": the handout says the same thing in (nearly) the same words
- "reworded": same fact, other words or language
- "partial": the handout teaches part of it
- "extra": not in the handout (never guess: if you are not sure the handout says it, use extra)
- "not_content": titles, page numbers, headers, footers, names, decoration
For same/reworded/partial give the labels of the smallest whole handout lines it matches (most important first, at
most 4). Read both texts: never choose by matching words alone.

BOOK PAGES:
{pages}

Answer with JSON lines only, one line per book page, no other text:
{{"page": <page>, "page_kind": "content" or "not_content", "lecture_id": <a lecture id from the list or null>, "blocks": [[<block n>, "<match>", ["<label>", ...]], ...]}}
Every block of every page must appear once, in order. A page that is only a picture: page_kind "not_content", every block not_content."""


def book_blocks(text):
    """One block per non-empty printed line; a line over the word limit is split in pieces."""
    out = []
    for line in text.splitlines():
        words = line.split()
        for i in range(0, len(words), checks.MAX_BLOCK_WORDS):
            piece = " ".join(words[i:i + checks.MAX_BLOCK_WORDS])
            if piece:
                out.append(piece)
    return out


def book_rows(answer, payload, labels):
    """Gemini's compact JSON lines as the flow's out.jsonl rows (texts copied by code from the pages and handout)."""
    pages = {p["page"]: p for p in payload["pages"]}
    rows = []
    for line in strip_fence(answer).splitlines():
        line = line.strip().rstrip(",")
        if not line.startswith("{"):
            continue
        a = json.loads(line)
        page = pages.get(a.get("page"))
        if page is None:
            continue
        texts = book_blocks(page["text"])
        kinds = {int(b[0]): b for b in a.get("blocks", []) if isinstance(b, list) and b}
        blocks = []
        for n, text in enumerate(texts, 1):
            b = kinds.get(n, [n, "extra", []])
            match = b[1] if len(b) > 1 else "extra"
            if a.get("page_kind") == "not_content":
                match = "not_content"
            spans = []
            for lab in (b[2] if len(b) > 2 and match in checks.LINKED else []):
                ln = labels.get(str(lab))
                if ln is None:
                    continue
                fig = ln.get("figure")
                spans.append({"pdf_page": ln["page"], "printed_page": ln.get("printed"),
                              "text": "FIGURE" if fig is not None else ln["text"], "figure": fig})
            if match in checks.LINKED and not spans:
                match = "extra"  # named no real handout line: not linked
            blocks.append({"n": n, "text": text, "figure": None, "match": match, "handout": spans})
        rows.append({"book_id": payload["book_id"], "page": page["page"], "page_kind": a.get("page_kind", "content"),
                     "lecture_id": a.get("lecture_id"), "blocks": blocks, "note": None})
    return rows


WORD = re.compile(r"[a-z]{4,}")


HANDOUT_LECTURES = ROOT / "modules" / "year2-cns" / "old" / "agent-lecture-list-2026-11-08" / "reference.json"
BOOK_SUBJECT = {"hist": "Histology", "anat": "Anatomy", "phys": "Physiology"}


def subject_pages(book_id):
    """(subject, the handout pages of that subject's handout lectures) for a book id like ammar-hist-1; (None, None)
    when the id names no subject. Owner 2026-11-10: tell the AI this subject, this doctor, this area only."""
    subject = next((s for k, s in BOOK_SUBJECT.items() if f"-{k}" in book_id), None)
    if not subject or not HANDOUT_LECTURES.exists():
        return None, None
    pages = set()
    for x in json.loads(HANDOUT_LECTURES.read_text(encoding="utf-8"))["lectures"]:
        if (x.get("subject") or "").lower() == subject.lower() and x.get("pdf_pages"):
            pages |= set(range(x["pdf_pages"][0], x["pdf_pages"][1] + 1))
    return subject, pages


def candidate_pages(book_pages, labels, per_page=5, allowed=None):
    """Handout pages worth reading for these book pages (like find.py: it finds pages to read, it never chooses a
    match): the top pages by shared rare English words per book page, with the page before and after each. `allowed`
    (the book's subject pages) limits the search to that subject."""
    import math
    from collections import Counter, defaultdict
    words = defaultdict(set)
    for ln in labels.values():
        if allowed and ln["page"] not in allowed:
            continue
        words[ln["page"]] |= set(WORD.findall((ln.get("text") or ln.get("figure") or "").lower()))
    df = Counter(w for ws in words.values() for w in ws)
    n = len(words)
    keep = set()
    for p in book_pages:
        mine = set(WORD.findall(p["text"].lower()))
        scores = sorted(((sum(math.log(n / df[w]) for w in mine & ws), pg) for pg, ws in words.items()), reverse=True)
        for s, pg in scores[:per_page]:
            if s > 0:
                keep |= {pg - 1, pg, pg + 1}
    return sorted(pg for pg in keep if pg in words)


def handout_subset(labels, pages, path):
    keep, out, page = set(pages), [], None
    for lab, ln in labels.items():
        if ln["page"] not in keep:
            continue
        if ln["page"] != page:
            page = ln["page"]
            out.append(f"\n=== pdf_page {page} (printed page {ln.get('printed')}) ===")
        out.append(f"{lab} " + (f"[FIGURE: {ln['figure']}]" if ln.get("figure") is not None else ln["text"]))
    Path(path).write_text("\n".join(out).strip() + "\n", encoding="utf-8")


def run_book(q, job, model, labels, handout, tries=2):
    flow = REGISTRY["books"]
    d = ROOT / "jobs" / "books" / job["key"]
    d.mkdir(parents=True, exist_ok=True)
    flow.prepare(job, d)
    ref_path = d / "inputs" / "reference.json"
    ref = json.loads(ref_path.read_text(encoding="utf-8")) if ref_path.exists() else {}
    lecs = ref.get("lectures") or []
    reference = ("\nLectures (for lecture_id: the lecture most of a page's linked lines belong to):\n" +
                 "".join(f"- {x['lecture_id']}: {x.get('title')}" + (f" (pdf pages {x['pdf_pages']})" if x.get("pdf_pages")
                                                                     else "") + "\n" for x in lecs)) if lecs else ""
    pages_txt = ""
    for p in job["payload"]["pages"]:
        pages_txt += f"\n--- book page {p['page']} ---\n" + "".join(f"{n}. {t}\n" for n, t in
                                                              enumerate(book_blocks(p["text"]), 1))
    prompt = d / "gemini_prompt.txt"
    prompt.write_text(BOOK_PROMPT.format(reference=reference, n=len(job["payload"]["pages"]), pages=pages_txt)
                      .replace("The attached handout.txt is the whole handout.",
                               "The attached handout.txt holds the handout pages that may match these book pages."),
                      encoding="utf-8")
    subset = d / "handout.txt"
    subject, allowed = subject_pages(job["payload"]["book_id"])
    if subject:
        prompt.write_text(prompt.read_text(encoding="utf-8").replace(
            "Below are", f"This is a {subject} book: the attached pages are {subject} pages of the handout only.\n\nBelow are",
            1), encoding="utf-8")
    handout_subset(labels, candidate_pages(job["payload"]["pages"], labels, allowed=allowed), subset)
    last = "no answer"
    for t in range(1, tries + 1):
        answer, meta = ask(prompt, model, [subset], timeout=2400)
        if answer is None:
            last = f"gemini: {meta.get('error')}"[:200]
            log("books", job["key"], f"try {t}", last)
            continue
        (d / "gemini_answer.txt").write_text(answer, encoding="utf-8")
        try:
            rows = book_rows(answer, job["payload"], labels)
        except (ValueError, KeyError, TypeError, IndexError) as e:
            last = f"answer: {type(e).__name__}"
            log("books", job["key"], f"try {t}", last)
            continue
        common.write_jsonl(d / "out.jsonl", rows)
        errors = flow.check(job, d)
        if errors:
            last = "; ".join(errors)[:300]
            log("books", job["key"], f"try {t}", "check:", len(errors), "errors;", last[:200])
            continue
        linked = sum(b["match"] in checks.LINKED for r in rows for b in r["blocks"])
        total = sum(len(r["blocks"]) for r in rows)
        q.finish(job["id"], "passed", f"{NOTE} {meta.get('model')} {meta.get('account')}")
        for name, jobs in (flow.then(job, d) if hasattr(flow, "then") else []):
            q.add_jobs(name, jobs)
        log("books", job["key"], "passed", f"{linked}/{total} blocks linked", meta.get("account"), f"{meta.get('secs')}s")
        return True
    q.finish(job["id"], "failed", last)
    return False


def books(args):
    q = queue_db.Queue()
    q.recover()
    row = q.db.execute("SELECT payload FROM jobs WHERE flow='books' AND status='queued' LIMIT 1").fetchone()
    if row is None:
        log("books: nothing queued")
        return
    module = json.loads(row["payload"])["module"]
    handout = ROOT / "jobs" / "gemini" / f"handout-{module}-ids.txt"
    labels = handout_text(module, handout, ids=True)
    left, lock, stats = [args.limit or 10 ** 9], threading.Lock(), {"passed": 0, "failed": 0}

    def worker():
        wq = queue_db.Queue()
        while True:
            with lock:
                if left[0] <= 0:
                    break
                left[0] -= 1
            job = wq.claim("books", f"gemini-{threading.current_thread().name}", only=True)
            if job is None:
                break
            try:
                ok = run_book(wq, job, args.model, labels, handout)
            except Exception as e:  # noqa: BLE001
                wq.finish(job["id"], "failed", f"gemini_run: {type(e).__name__}: {e}"[:300])
                ok = False
            with lock:
                stats["passed" if ok else "failed"] += 1
        wq.close()

    threads = [threading.Thread(target=worker, name=f"b{i}") for i in range(args.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log("books done", stats, q.progress().get("books"))
    q.close()


# ---- lecture links -------------------------------------------------------------------------------------------
LINK_PROMPT = """You are helping build a study website for medical students. A recorded lecture is linked to the handout (the
College Book), so a student can jump from any handout line to the minute the doctor explains it.

Attached:
- transcript.txt: the lecture "{title}" word for word ({minutes} minutes, {seconds} seconds), with [mm:ss] at each
  paragraph. It is automatic speech recognition, often Egyptian Arabic with English terms.
- handout_pages.txt: the handout pages of this lecture (pdf pages {pages}). Each line starts with its label
  (<pdf page>.<n>, figures <pdf page>.F<n>).

Split the lecture into parts (sub 0) as the doctor moves from topic to topic, at least {need} parts, and optionally
sub-parts (sub 1, 2, ...) inside a part. For each, give its start and end in seconds from the transcript's [mm:ss]
times, and the labels of EVERY handout line that part explains (read both: the doctor must really explain that line;
usually 3 to 30 lines per part). Parts are numbered 1, 2, 3..., follow each other, never overlap and together cover
the whole recording from 0 to {seconds}. A sub-part sits inside its part's times. A part with no handout line
(greetings, exam news) has no labels. At least three quarters of the recording should sit in parts with lines.

Answer with JSON lines only, one line per part or sub-part, in order, no other text:
{{"part": 1, "sub": 0, "title": "<short English title>", "start": <seconds>, "end": <seconds>, "lines": ["<label>", ...]}}"""


def run_link(q, job, model, labels, tries=2):
    flow = REGISTRY["lecture_links"]
    meta = lectures.load(job["payload"]["lecture"])
    d = ROOT / "jobs" / "lecture_links" / job["key"]
    d.mkdir(parents=True, exist_ok=True)
    flow.prepare(job, d)
    a, b = meta["pdf_pages"]
    by_label = {lab: ln for lab, ln in labels.items() if a <= ln["page"] <= b}
    page, out = None, []
    for lab, ln in by_label.items():
        if ln["page"] != page:
            page = ln["page"]
            out.append(f"\n=== pdf_page {page} (printed page {ln.get('printed')}) ===")
        out.append(f"{lab} " + (f"[FIGURE: {ln['figure']}]" if ln.get("figure") is not None else ln["text"]))
    pages_file = d / "handout_pages.txt"
    pages_file.write_text("\n".join(out).strip() + "\n", encoding="utf-8")
    shutil_copy(d / "raw.txt", d / "transcript.txt")
    dur = meta["duration_s"]
    prompt = d / "gemini_prompt.txt"
    prompt.write_text(LINK_PROMPT.format(title=meta["title"], minutes=round(dur / 60), seconds=int(dur), pages=f"{a}-{b}",
                                         need=max(1, int(dur // (checks.LINK_MINUTES_PER_PART * 60)))), encoding="utf-8")
    last = "no answer"
    for t in range(1, tries + 1):
        answer, m = ask(prompt, model, [d / "transcript.txt", pages_file], timeout=2400)
        if answer is None:
            last = f"gemini: {m.get('error')}"[:200]
            log("links", job["key"], f"try {t}", last)
            continue
        (d / "gemini_answer.txt").write_text(answer, encoding="utf-8")
        parts = []
        for line in strip_fence(answer).splitlines():
            line = line.strip().rstrip(",")
            if not line.startswith("{"):
                continue
            try:
                p = json.loads(line)
            except ValueError:
                continue
            ids = [by_label[str(x)]["id"] for x in p.get("lines") or [] if str(x) in by_label]
            parts.append({"part": p.get("part"), "sub": p.get("sub", 0), "title": p.get("title") or "",
                          "start": p.get("start"), "end": min(p.get("end") or 0, dur), "line_ids": list(dict.fromkeys(ids))})
        # clean.txt = raw.txt laid out as it is (no word changed); misheard-word fixes wait (fixes.jsonl empty)
        (d / "clean.txt").write_text((d / "raw.txt").read_text(encoding="utf-8"), encoding="utf-8")
        (d / "fixes.jsonl").write_text("", encoding="utf-8")
        common.write_jsonl(d / "parts.jsonl", parts)
        errors = flow.check(job, d)
        if errors:
            last = "; ".join(errors)[:300]
            log("links", job["key"], f"try {t}", "check:", len(errors), "errors;", last[:200])
            continue
        q.finish(job["id"], "passed", f"{NOTE} {m.get('model')} {m.get('account')}")
        for name, jobs in flow.then(job, d):
            q.add_jobs(name, jobs)
        log("links", job["key"], "passed", len(parts), "parts", m.get("account"), f"{m.get('secs')}s")
        return True
    q.finish(job["id"], "failed", last)
    return False


def shutil_copy(src, dst):
    import shutil
    shutil.copy2(src, dst)


def links(args):
    q = queue_db.Queue()
    q.recover()
    labels = handout_text("year2-cns", ROOT / "jobs" / "gemini" / "handout-year2-cns-ids.txt", ids=True)
    left, lock, stats = [args.limit or 10 ** 9], threading.Lock(), {"passed": 0, "failed": 0}

    def worker():
        wq = queue_db.Queue()
        while True:
            with lock:
                if left[0] <= 0:
                    break
                left[0] -= 1
            job = wq.claim("lecture_links", f"gemini-{threading.current_thread().name}", only=True)
            if job is None:
                break
            try:
                ok = run_link(wq, job, args.model, labels)
            except Exception as e:  # noqa: BLE001
                wq.finish(job["id"], "failed", f"gemini_run: {type(e).__name__}: {e}"[:300])
                ok = False
            with lock:
                stats["passed" if ok else "failed"] += 1
        wq.close()

    threads = [threading.Thread(target=worker, name=f"l{i}") for i in range(args.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log("links done", stats, q.progress().get("lecture_links"))
    q.close()


# ---- bounds: what a recording covers, as outline sections (placement.py) ---------------------------------------
BOUNDS_PROMPT = """You are helping build a study website for medical students. Each recorded lecture must be tied to the exact
part of the handout (the College Book) the doctor explains in it.

Attached:
- transcript.txt: the lecture "{title}" ({subject}) word for word, with [mm:ss] times. It is automatic speech
  recognition, often Egyptian Arabic with English terms.
- handout_sections.txt: the part of the handout this lecture may cover and the handout lectures around it, cut into
  numbered sections. Each section starts with a line "### S<number> | pdf page <page>".

Which sections does the doctor explain in this recording? Read the transcript from start to end and follow it in the
handout. A section counts only when he really explains its content (not when he only names the topic, or says it comes
next time). A lesson is usually one run of sections that follow each other; give two runs only when he clearly skips.
When he stops in the middle of a topic, stop there.

Answer with one JSON object only, no other text:
{{"sections": [<section numbers in handout order>], "note": "<where he starts and stops, 6 to 30 words, English>"}}"""


def bounds_scope(meta, secs):
    """The outline sections to show for one lecture: the handout lectures its current pages touch, plus the handout
    lecture before and after each in its own subject (so a place that is too narrow can be seen). No pages yet: the
    whole subject."""
    sub = (meta.get("subject") or "").lower()
    mine = list(dict.fromkeys(s["lecture"] for s in secs if s["subject"] == sub))
    pages = {pg for a, b in lectures.page_ranges(meta) for pg in range(a, b + 1)}
    touched = {s["lecture"] for s in secs if s["page"] in pages}
    keep = set(touched)
    for i, lec in enumerate(mine):
        if lec in touched:
            keep |= set(mine[max(0, i - 1):i + 2])
    keep = keep or set(mine)
    return [n for n, s in enumerate(secs) if s["lecture"] in keep]


def bounds_spans(answer, scope, secs):
    """(spans [(first line index, last line index)], errors) from Gemini's answer: runs of sections that follow each other."""
    try:
        got = json.loads(strip_fence(answer))
        nums = sorted({int(x) for x in got["sections"]})
    except (ValueError, KeyError, TypeError) as e:
        return [], [f"answer is not the JSON asked for ({type(e).__name__})"]
    if not nums:
        return [], ["no sections named"]
    bad = [n for n in nums if n not in set(scope)]
    if bad:
        return [], [f"sections outside the ones shown: {bad[:5]}"]
    runs = []
    for n in nums:
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return [(secs[a]["i0"], secs[b]["i1"]) for a, b in runs], []


def bounds(args):
    """One call per lecture that has a transcript and no web reading yet (the owner's places are left alone)."""
    import ledger
    import outline
    module = "year2-cns"
    lines = common.read_jsonl(common.module_dir(module) / "lines.jsonl")
    secs = outline.load(module)
    db = ledger.connect()
    have = {r["src"] for r in db.execute("SELECT src FROM links WHERE kind='lesson' AND runner='web'")}
    todo = [m for m in lectures.all_lectures(module) if m.get("kind", "lecture") == "lecture" and m["id"] not in have
            and m.get("placed_by") != "owner" and (lectures.folder(m["id"]) / "raw.txt").exists()]
    todo = todo[:args.limit] if args.limit else todo
    ok = 0
    for m in todo:
        d = ROOT / "jobs" / "gemini" / "bounds" / m["id"]
        d.mkdir(parents=True, exist_ok=True)
        scope = bounds_scope(m, secs)
        out = []
        for n in scope:
            out.append(f"\n### S{n} | pdf page {secs[n]['page']}")
            out += [f"[FIGURE: {ln['figure']}]" if ln.get("figure") is not None else ln["text"]
                    for ln in lines[secs[n]["i0"]:secs[n]["i1"] + 1]]
        (d / "handout_sections.txt").write_text("\n".join(out).strip() + "\n", encoding="utf-8")
        shutil_copy(lectures.folder(m["id"]) / "raw.txt", d / "transcript.txt")
        (d / "prompt.txt").write_text(BOUNDS_PROMPT.format(title=m["title"], subject=m.get("subject") or "-"), encoding="utf-8")
        if args.dry:
            log("bounds", m["id"], "dry:", len(scope), "sections shown")
            continue
        answer, meta = ask(d / "prompt.txt", args.model, [d / "transcript.txt", d / "handout_sections.txt"], timeout=2400)
        if answer is None:
            log("bounds", m["id"], "gemini:", str(meta.get("error"))[:160])
            continue
        (d / "answer.txt").write_text(answer, encoding="utf-8")
        spans, errors = bounds_spans(answer, scope, secs)
        if errors:
            log("bounds", m["id"], "check:", "; ".join(errors)[:200])
            continue
        ledger.put(db, module, "lesson", m["id"], "web", [[lines[a]["id"], lines[b]["id"]] for a, b in spans],
                   scope=f"sections:{scope[0]}-{scope[-1]}", model=meta.get("model"))
        db.commit()
        ok += 1
        log("bounds", m["id"], "read:", len(spans), "run(s)", meta.get("account"), f"{meta.get('secs')}s")
    log("bounds done:", ok, "read of", len(todo))
    db.close()


# ---- pointers: questions -> the handout lines that teach them, one handout lecture per call -------------------------
POINTER_PROMPT = """You are helping build a study website for medical students. After a student answers a question, the site shows
"Read this in your College Book" with the exact lines of the handout (the College Book) that teach it.

The attached handout_pages.txt holds pdf pages {pages} of the handout. Every line starts with its label
(<pdf page>.<n>, figures <pdf page>.F<n>).

Below are {n} questions thought to be taught on these pages; some are not. For EACH question find the smallest set of
whole lines that teaches what a student must know to choose the option marked with *: the exact sentence(s), bullet(s)
or table row(s). Not a paragraph, and never a line that only shares a word with the question. Read the lines you cite.
- The pages teach only part of it: add "partial": true.
- These pages do not teach it: "none": "other_lecture". The question cannot be understood: "none": "question_unclear".
- Never guess: a wrong pointer is worse than "other_lecture". Never judge or mention the marked option.

Answer with JSON lines only, one line per question, in order, no other text:
{{"q": 1, "lines": ["<label>", "<label>"], "partial": false}}
{{"q": 2, "none": "other_lecture"}}

QUESTIONS
{questions}"""
POINTER_MAX_LINES = 12
POINTER_NONE = {"other_lecture", "question_unclear"}


def clean_key(q):
    return q.get("key") is not None and not q.get("key_conflict") and 2 <= len(q["options"]) <= 5 \
        and all(str(o).strip() for o in q["options"])


def pointer_groups(module, db):
    """{(first page, last page): [bank rows]}: the labelled, cleanly keyed questions no AI has read yet, grouped by
    the handout pages their label names, only where a lesson teaches some of those pages."""
    import fast_lessons
    bank, labels, _, _ = fast_lessons.labelled()
    read = {r["src"] for r in db.execute("SELECT src FROM links WHERE module=? AND kind='question' AND runner!='script'", (module,))}
    taught = {pg for m in lectures.all_lectures(module) for a, b in lectures.page_ranges(m) for pg in range(a, b + 1)}
    out = {}
    for q in bank:
        lab = labels.get(q["word_key"])
        if not lab or q["word_key"] in read or not clean_key(q):
            continue
        ranges = tuple(fast_lessons.label_ranges(lab))  # a title naming several lectures gives several ranges
        if taught & {pg for lo, hi in ranges for pg in range(lo, hi + 1)}:
            out.setdefault(ranges, []).append(q)
    return out


def pointer_answers(answer, n, by_label):
    """({q number: {"ids": [...], "partial": bool} or {"none": reason}}, errors) from Gemini's JSON lines."""
    got, errors = {}, []
    for line in strip_fence(answer).splitlines():
        line = line.strip().rstrip(",")
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
            k = int(r["q"])
        except (ValueError, KeyError, TypeError):
            continue
        if r.get("none"):
            if r["none"] not in POINTER_NONE:
                errors.append(f"Q{k}: none must be one of {sorted(POINTER_NONE)}")
            else:
                got[k] = {"none": r["none"]}
            continue
        labs = [str(x) for x in r.get("lines") or []]
        unknown = [x for x in labs if x not in by_label]
        if not labs or unknown or len(labs) > POINTER_MAX_LINES:
            errors.append(f"Q{k}: " + ("no lines" if not labs else f"labels not on the pages shown: {unknown[:3]}" if unknown
                                        else f"more than {POINTER_MAX_LINES} lines"))
            continue
        got[k] = {"ids": list(dict.fromkeys(by_label[x]["id"] for x in labs)), "partial": bool(r.get("partial"))}
    got = {k: v for k, v in got.items() if 1 <= k <= n}
    missing = [k for k in range(1, n + 1) if k not in got]
    if missing:
        errors.append(f"{len(missing)} questions unanswered or refused by the check: {missing[:5]}")
    return got, errors


def run_pointer_call(db, module, pages, qs, labels, model, scope, tries=2):
    """One call: these questions against these pages. Passed answers go to the ledger (runner web). Returns how many."""
    import hashlib
    import ledger
    ranges = [tuple(pages)] if isinstance(pages[0], int) else [tuple(r) for r in pages]
    keep = {pg for lo, hi in ranges for pg in range(lo, hi + 1)}
    tag = hashlib.md5(qs[0]["word_key"].encode()).hexdigest()[:8]
    d = ROOT / "jobs" / "gemini" / "pointers" / f"{scope.replace(':', '-')}-{tag}"
    d.mkdir(parents=True, exist_ok=True)
    handout_subset(labels, sorted(keep), d / "handout_pages.txt")
    by_label = {lab: ln for lab, ln in labels.items() if ln["page"] in keep}
    text = "\n\n".join(f"Q{i}. {q['question']}\n" + "\n".join(
        f"{' *' if j == q['key'] else '  '} {'ABCDE'[j]}. {o}" for j, o in enumerate(q["options"])) for i, q in enumerate(qs, 1))
    (d / "prompt.txt").write_text(POINTER_PROMPT.format(pages=", ".join(f"{lo}-{hi}" for lo, hi in ranges), n=len(qs), questions=text), encoding="utf-8")
    for t in range(1, tries + 1):
        answer, meta = ask(d / "prompt.txt", model, [d / "handout_pages.txt"], timeout=2400)
        if answer is None:
            log("pointers", scope, f"try {t} gemini:", str(meta.get("error"))[:160])
            continue
        (d / "answer.txt").write_text(answer, encoding="utf-8")
        got, errors = pointer_answers(answer, len(qs), by_label)
        if errors and t < tries:
            log("pointers", scope, f"try {t} check:", len(errors), "errors;", errors[0][:120])
            continue
        for k, a in got.items():  # after the last try, the questions that passed are kept; the rest stay unread
            ledger.put(db, module, "question", qs[k - 1]["word_key"], "web", a.get("ids", []), found="ids" in a,
                       reason=a.get("none") or ("partial" if a.get("partial") else None), scope=scope, model=meta.get("model"))
        db.commit()
        log("pointers", scope, len(got), "of", len(qs), "read", meta.get("account"), f"{meta.get('secs')}s")
        return len(got)
    return 0


def escalation_groups(module, db, labels):
    """Questions the first scope called "other_lecture": {(pages of the next handout lecture to try): [bank rows]}.
    Code only picks which pages to show next (the same-subject handout lecture sharing the most rare words with the
    question); the reader still chooses, and a second "other_lecture" is final."""
    import math
    from collections import Counter
    import fast_lessons
    import outline
    refs = outline.reference(module)
    by_id = {x["lecture_id"]: x for x in refs}
    bag = {x["lecture_id"]: set() for x in refs}
    for ln in labels.values():
        for x in refs:
            if x["pdf_pages"][0] <= ln["page"] <= x["pdf_pages"][1]:
                bag[x["lecture_id"]] |= set(fast_lessons.words(ln.get("text")))
    df = Counter(w for ws in bag.values() for w in ws)
    again = {r["src"]: r["scope"] for r in db.execute(
        "SELECT src, scope FROM links WHERE module=? AND kind='question' AND runner='web' AND found=0 AND "
        "reason='other_lecture' AND scope LIKE 'pages:%'", (module,))}
    if not again:
        return {}
    bank, _, _, _ = fast_lessons.labelled()
    out = {}
    for q in bank:
        if q["word_key"] not in again:
            continue
        lo = int(again[q["word_key"]][6:].split("-")[0])
        home = next((x for x in refs if x["pdf_pages"][0] <= lo <= x["pdf_pages"][1]), None)
        if home is None:
            continue
        qw = set(fast_lessons.words(q["question"])) | set(fast_lessons.words(q["options"][q["key"]]))
        scored = sorted(((sum(math.log(len(bag) / df[w]) for w in qw & ws), lid) for lid, ws in bag.items()
                         if lid != home["lecture_id"] and by_id[lid].get("subject") == home.get("subject")), reverse=True)
        if scored and scored[0][0] > 0:
            out.setdefault(tuple(by_id[scored[0][1]]["pdf_pages"]), []).append(q)
    return out


def pointers(args):
    import ledger
    module = "year2-cns"
    labels = handout_text(module, ROOT / "jobs" / "gemini" / f"handout-{module}-ids.txt", ids=True)
    db = ledger.connect()
    left, done = [args.limit or 10 ** 9], 0
    for name in ("pages", "escalated"):
        groups = pointer_groups(module, db) if name == "pages" else escalation_groups(module, db, labels)
        calls = [(pg, qs[i:i + args.per_call]) for pg, qs in sorted(groups.items()) for i in range(0, len(qs), args.per_call)]
        log("pointers", name, "scope:", sum(len(q) for _, q in calls), "questions in", len(calls), "calls")
        if args.dry:
            continue
        for pg, qs in calls:
            if left[0] <= 0:
                break
            left[0] -= 1
            done += run_pointer_call(db, module, pg, qs, labels, args.model, f"{name}:{pg[0]}-{pg[1]}" if isinstance(pg[0], int) else f"{name}:" + "_".join(f"{a}-{b}" for a, b in pg))
    if not args.dry:
        log("pointers done:", done, "questions read;", dict(ledger.agree(db, module)))
        db.commit()
    db.close()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pieces")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--model", default="flash-lite")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--no-cut", action="store_true", help="only hear pieces already cut (another process cuts)")
    p = sub.add_parser("place")
    p.add_argument("--model", default="flash")
    p.add_argument("--dry", action="store_true")
    p = sub.add_parser("books")
    p.add_argument("--model", default="flash")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit", type=int, default=0)
    p = sub.add_parser("links")
    p.add_argument("--model", default="flash")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit", type=int, default=0)
    p = sub.add_parser("bounds")
    p.add_argument("--model", default="flash")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--dry", action="store_true")
    p = sub.add_parser("pointers")
    p.add_argument("--model", default="flash")
    p.add_argument("--limit", type=int, default=0, help="calls, not questions")
    p.add_argument("--per-call", type=int, default=40)
    p.add_argument("--dry", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args()
    if args.cmd == "status":
        q = queue_db.Queue()
        print(json.dumps(q.progress(), indent=1))
        return
    {"pieces": pieces, "place": place, "books": books, "links": links, "bounds": bounds, "pointers": pointers}[args.cmd](args)


if __name__ == "__main__":
    main()

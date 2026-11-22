"""MSK doctors' MCQ books (the zagexam59 link tree, 2026-11-22) copied by Gemini web (4 Hydrogen), two readers.

Each book is cut into chunks of PAGES pages; a chunk's PDF also carries the book's answer-table pages (found by code:
pages that are mostly bare numbers and letters A-E), because most books key their questions in a table at the end of a
section or of the book. Two separate chats (A, B) copy every question of the chunk as JSON lines. A question is kept
only when both copies agree (same stem and options, `same`) and both give the same key that the book shows ("marked",
"answer_line" or "answer_list"); a key never comes from a reader's own judgement or from code. Reader A's copy is kept.

    py msk_mcq.py jobs              job folders jobs/msk_mcq/<post>/cNN/{A,B}/ (pages.pdf + task.txt)
    py msk_mcq.py run [--workers 4] Gemini web answers every unanswered job (waits at a usage cap)
    py msk_mcq.py collect           -> sources/msk_quizzes/mcq_books.jsonl (agreed, keyed) + counts per book
`msk_questions.py build` files them: grade 2 on the doctor's own lesson that holds the line (1 when he has no quiz
there), else grade 3 where the polls go, else waiting with the handout link.
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PDFS = ROOT / "sources" / "lists_pdf" / "zagexam59"
JOBS = ROOT / "jobs" / "msk_mcq"
OUT = ROOT / "sources" / "msk_quizzes" / "mcq_books.jsonl"
PAGES = 12
READERS = ("A", "B")
MODEL = "hydrogen"
WAIT = 900

ANAT, HIST, PHYS = [f"L{i:02d}" for i in range(1, 21)], [f"L{i:02d}" for i in range(21, 25)], \
    [f"L{i:02d}" for i in range(25, 40)]
# post -> (doctor, title, the handout lessons its questions are searched in). Read from the captions by Claude.
BOOKS = {
    529: ("dr-basel-sherif-hist", "Cartilage chapter MCQ book (Dr. Basel)", ["L21"]),
    533: ("dr-ibrahim-el-azouni-anat", "MSK MCQ part 1 (Dr. Elazouny)", ANAT),
    560: ("dr-ibrahim-el-azouni-anat", "MSK MCQ part 2 (Dr. Elazouny)", ANAT),
    540: ("dr-islam-gamal-anat", "Pectoral Region 1 quiz (Dr. Eslam Gamal)", ["L01"]),
    541: ("dr-islam-gamal-anat", "Pectoral Region 2 quiz (Dr. Eslam Gamal)", ["L01"]),
    562: ("dr-wajih-el-husseiny-anat", "MSK MCQ book (Dr. Wagih El-Husseiny)", ANAT),
    563: ("dr-ahmed-ammar-hist", "Musculoskeletal MCQ book (Dr. Ahmed Ammar)", HIST),
    567: ("dr-mahmoud-el-husseiny-hist", "MCQ book (Dr. Mahmoud El-Husseiny)", HIST),
    568: ("dr-mohamed-zahran-hist", "MCQ all parts (Dr. Zahran)", HIST),
    575: ("dr-amr-mesafer-anat", "MCQ book (Dr. Amr Mosafer)", ANAT),
}

PROMPT = """The attached PDF holds pages {a} to {b} of a doctor's multiple-choice question book (the file's first page is \
book page {a}){extra}.

Copy every multiple-choice question whose stem is printed on book pages {a} to {b}. Write one JSON object per line and \
nothing else:
{{"page": <book page of the stem>, "n": "<the question's number as printed>", "section": "<the nearest heading above \
it>", "q": "<the stem, word for word>", "o": ["<option text without its letter>", ...], "key": "<letter of the \
correct option>" or null, "how": "marked" or "answer_line" or "answer_list" or null}}

Rules:
- Copy the words exactly as printed (English). Do not fix, shorten or translate.
- A shared case ("Questions 44-47: A 10-year-old boy ...") goes in front of each of its stems.
- The key only as the book shows it: an option printed differently from the others (bold, coloured, ticked, \
highlighted) -> "marked"; an answer written under the question -> "answer_line"; the answer table -> "answer_list" \
(match the table of the same section and number). If the book shows no key, "key": null. Never answer a question \
yourself.
- Skip anything that is not a question with options (titles, notes, answer tables).
Last line: END"""


def answer_pages(doc):
    """Book pages (1-based) that are mostly an answer table: bare numbers and single letters A-E."""
    out = []
    for i in range(doc.page_count):
        toks = re.findall(r"\S+", doc[i].get_text())
        if len(toks) < 20:
            continue
        bare = sum(bool(re.fullmatch(r"\d{1,3}[.)]?|[A-Ea-e][.)]?", t)) for t in toks)
        if bare / len(toks) >= 0.6:
            out.append(i + 1)
    return out


def pdf_of(post):
    return next((PDFS / str(post)).glob("*.pdf"))


def jobs(say=print):
    import fitz
    made = 0
    for post in sorted(BOOKS):
        src = fitz.open(pdf_of(post))
        keys = answer_pages(src)
        n = src.page_count
        for c, a in enumerate(range(1, n + 1, PAGES)):
            b = min(n, a + PAGES - 1)
            extra_pages = [p for p in keys if not a <= p <= b]
            for r in READERS:
                d = JOBS / str(post) / f"c{c:02d}" / r
                if (d / "task.txt").exists():
                    continue
                d.mkdir(parents=True, exist_ok=True)
                out = fitz.open()
                out.insert_pdf(src, from_page=a - 1, to_page=b - 1)
                for p in extra_pages:
                    out.insert_pdf(src, from_page=p - 1, to_page=p - 1)
                out.save(d / "pages.pdf", garbage=3, deflate=True)
                extra = (f", followed by the book's answer-table pages {', '.join(map(str, extra_pages))}"
                         if extra_pages else "")
                (d / "task.txt").write_text(PROMPT.format(a=a, b=b, extra=extra), encoding="utf-8")
                (d / "meta.json").write_text(json.dumps({"post": post, "a": a, "b": b, "answer_pages": extra_pages}),
                                             encoding="utf-8")
                made += 1
        say(f"  {post}: {n} pages, answer-table pages {keys or 'none'}")
    say(f"msk_mcq jobs: {made} job folders written")
    return made


def todo():
    return sorted(d for d in JOBS.glob("*/c*/*") if (d / "task.txt").exists() and not (d / "answer.txt").exists())


def ask_one(d, ask=None):
    if ask is None:
        import functools
        import gemini_browser
        ask = functools.partial(gemini_browser.ask, fallback=False)
    text, meta = ask((d / "task.txt").read_text(encoding="utf-8"), model=MODEL, attach=[str(d / "pages.pdf")],
                     wait=WAIT)
    if text is None and (meta.get("until") or "capped" in str(meta.get("error") or "")):
        return "capped", float(meta.get("until") or time.time() + 1200)
    if text and parse(text):
        (d / "answer.txt").write_text(text, encoding="utf-8")
        (d / "browser.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return "answered", None
    (d / "reply_failed.txt").write_text(text or json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return "failed", None


def run(workers=4, say=print):
    stats = {}

    def work(d):
        for _ in range(48):                    # a capped job waits for the renewal, at most two days
            st, until = ask_one(d)
            if st != "capped":
                break
            time.sleep(max(60, until - time.time() + 30))
        stats[st] = stats.get(st, 0) + 1
        say(f"  {d.relative_to(JOBS)}: {st}", flush=True)

    with ThreadPoolExecutor(max(1, min(4, workers))) as ex:
        list(ex.map(work, todo()))
    say(f"msk_mcq run: {stats}")
    return stats


def parse(text):
    out = []
    for line in (text or "").splitlines():
        line = line.strip().strip(",")
        if not line.startswith("{"):
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("q") and isinstance(r.get("o"), list) and 2 <= len(r["o"]) <= 6:
            out.append(r)
    return out


def words(t):
    return set(re.findall(r"[a-z0-9]+", (t or "").lower()))


def same(x, y):
    """The same question copied twice: nearly the same stem words and the same option words."""
    a, b = words(x["q"]), words(y["q"])
    oa, ob = [words(o) for o in x["o"]], [words(o) for o in y["o"]]
    return (a and b and len(a & b) / len(a | b) >= 0.85 and len(oa) == len(ob)
            and all(p == q or (p | q and len(p & q) / len(p | q) >= 0.8) for p, q in zip(oa, ob)))


def key_index(r):
    k = (r.get("key") or "").strip().upper()[:1]
    return "ABCDEF".index(k) if k and k in "ABCDEF"[:len(r["o"])] else None


def collect(say=print):
    rows, counts = [], {}
    for post in sorted(BOOKS):
        c = counts.setdefault(post, {"A": 0, "agreed": 0, "kept": 0, "no key": 0, "keys differ": 0, "one reader": 0})
        for chunk in sorted((JOBS / str(post)).glob("c*")):
            got = {r: parse((chunk / r / "answer.txt").read_text(encoding="utf-8"))
                   if (chunk / r / "answer.txt").exists() else None for r in READERS}
            if any(v is None for v in got.values()):
                continue
            meta = json.loads((chunk / "A" / "meta.json").read_text(encoding="utf-8"))
            left = list(got["B"])
            for x in got["A"]:
                if not meta["a"] <= int(x.get("page") or meta["a"]) <= meta["b"]:
                    continue
                c["A"] += 1
                y = next((y for y in left if same(x, y)), None)
                if y is None:
                    c["one reader"] += 1
                    continue
                left.remove(y)
                c["agreed"] += 1
                ka, kb = key_index(x), key_index(y)
                if ka is None or kb is None or x.get("how") not in ("marked", "answer_line", "answer_list"):
                    c["no key"] += 1
                    continue
                if ka != kb:
                    c["keys differ"] += 1
                    continue
                c["kept"] += 1
                rows.append({"post": post, "doctor": BOOKS[post][0], "title": BOOKS[post][1],
                             "lessons": BOOKS[post][2], "page": x.get("page"), "n": x.get("n"),
                             "section": x.get("section"), "stem": x["q"].strip(),
                             "options": [str(o).strip() for o in x["o"]], "key": ka, "how": x.get("how"),
                             "url": f"https://t.me/zagexam59/{post}"})
        say(f"  {post} {BOOKS[post][1][:45]:45} {c}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    say(f"msk_mcq collect: {len(rows)} agreed keyed questions -> {OUT.relative_to(ROOT)}")
    return rows


def questions():
    """The agreed keyed book questions (msk_questions.py reads them)."""
    return [json.loads(x) for x in OUT.read_text(encoding="utf-8").splitlines() if x.strip()] if OUT.exists() else []


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "run":
        run(int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4)
    else:
        {"jobs": jobs, "collect": collect}[cmd]()

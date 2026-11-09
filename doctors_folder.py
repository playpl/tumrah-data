"""The owner's doctors/ folder (2026-11-08): one folder per doctor, one text file per lesson.

    doctors/<module>/<subject>/<doctor>/<n- chapter>/<n- lesson>.txt
    doctors/<module>/<subject>/<doctor>/<book>.pdf          the doctor's book ("Partial ..." in the name: partial)

A lesson file holds links, one per line, optionally labelled:
    https://youtu.be/...                       the recording
    quiz: https://forms.gle/...                the doctor's quiz (a "required quiz" holds Required questions)
    mini lec https://t.me/c/<chat>/<msg>       a mini lecture on Telegram

`scan()` reads it all and says what each lesson has; nothing is changed. Module folders are short names (cns, msk).
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCTORS = ROOT / "doctors"
MODULES = {"cns": "year2-cns", "msk": "year1-musculoskeletal"}
URL = re.compile(r"https?://\S+")
ORDER = re.compile(r"^\s*(\d+)\s*-\s*(.+?)\s*$")


def kind_of(label, url):
    label = label.lower()
    if "mini" in label:
        return "mini_lecture"
    if "quiz" in label or "forms.gle" in url or "docs.google.com/forms" in url:
        return "required_quiz" if "required" in label else "quiz"
    if "youtu" in url:
        return "recording"
    if "t.me/" in url:
        return "telegram"
    return "link"


def links(text):
    out = []
    for line in text.splitlines():
        m = URL.search(line)
        if m:
            out.append({"kind": kind_of(line[:m.start()], m.group(0)), "url": m.group(0)})
    return out


def numbered(name):
    m = ORDER.match(name)
    return (int(m.group(1)), m.group(2)) if m else (None, name)


# Folder names the name matcher cannot tie to a site doctor on its own (checked by hand, 2026-11-08).
ALIASES = {"elsamahy": "dr-abdullah-el-samahi-phys"}


def match_doctor(folder_name, site_doctors):
    """The site doctorId whose English name holds every word of the folder name (spelling may differ a little)."""
    def norm(s):
        return re.sub(r"[^a-z ]", " ", s.lower().replace("ss", "s").replace("ou", "o").replace("e", "a"))
    if folder_name.lower() in ALIASES and any(d["id"] == ALIASES[folder_name.lower()] for d in site_doctors):
        return ALIASES[folder_name.lower()]
    want = norm(folder_name).split()
    hits = [d["id"] for d in site_doctors if all(w in norm(d.get("name") or "") + " " + norm(d["id"]) for w in want)]
    return hits[0] if len(hits) == 1 else None


def scan(site_doctors=()):
    """[{module, subject, doctor_folder, doctor_id, chapter, chapter_n, title, n, file, links}] and the books."""
    lessons, books = [], []
    if not DOCTORS.exists():
        return lessons, books
    for mod in sorted(p for p in DOCTORS.iterdir() if p.is_dir()):
        for subj in sorted(p for p in mod.iterdir() if p.is_dir()):
            for doc in sorted(p for p in subj.iterdir() if p.is_dir()):
                did = match_doctor(doc.name, site_doctors)
                for pdf in sorted(doc.glob("*.pdf")):
                    name = pdf.name.lower()
                    kind = "mcq" if "mcq" in name else "partial" if name.startswith("partial") else "full"
                    books.append({"module": MODULES.get(mod.name, mod.name), "subject": subj.name, "doctor_folder": doc.name,
                                  "doctor_id": did, "file": str(pdf), "kind": kind, "partial": kind == "partial"})
                for f in sorted(doc.rglob("*.txt")):
                    chap = f.parent if f.parent != doc else None
                    cn, ctitle = numbered(chap.name) if chap else (None, None)
                    n, title = numbered(f.stem)
                    lessons.append({"module": MODULES.get(mod.name, mod.name), "subject": subj.name,
                                    "doctor_folder": doc.name, "doctor_id": did, "chapter": ctitle, "chapter_n": cn,
                                    "title": title, "n": n, "file": str(f),
                                    "links": links(f.read_text(encoding="utf-8", errors="replace"))})
            for f in sorted(subj.glob("*.txt")):  # a lesson file with no doctor folder yet
                n, title = numbered(f.stem)
                lessons.append({"module": MODULES.get(mod.name, mod.name), "subject": subj.name, "doctor_folder": None,
                                "doctor_id": None, "chapter": None, "chapter_n": None, "title": title, "n": n,
                                "file": str(f), "links": links(f.read_text(encoding="utf-8", errors="replace"))})
    return lessons, books


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    docs = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
    ls, bs = scan(docs)
    for b in bs:
        print(f"BOOK {b['module']} {b['subject']} {b['doctor_folder']} -> {b['doctor_id']} partial={b['partial']}")
    for x in ls:
        print(f"{x['module']} | {x['subject']} | {x['doctor_folder']} -> {x['doctor_id']} | ch {x['chapter_n']} {x['chapter']} | "
              f"{x['n']} {x['title']} | " + ", ".join(k['kind'] for k in x["links"]))


# ---- import: the folder becomes lectures, recordings, quizzes and book jobs ------------------------------------------
FORMS_SCRIPTS = Path(r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\forms")


def nice(title):
    return title[:1].upper() + title[1:] if title else title


def book_id(b):
    """mossafer-anat-1 (a partial book, the first one added), zahran-hist-full, elsamahy-phys-mcq."""
    suffix = {"partial": "1", "full": "full", "mcq": "mcq"}[b.get("kind", "partial")]
    return f"{b['doctor_folder'].split()[-1].lower()}-{b['subject'][:4].lower()}-{suffix}"


def read_form(url, out):
    """One Google Form's public page as {question, options} rows (read only: never submits, so no keys)."""
    import sys
    sys.path.insert(0, str(FORMS_SCRIPTS))
    import fetch_forms
    _, rows = fetch_forms.parse(url, *fetch_forms.fetch(url))
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({**r, "question": r.get("question"), "options": r.get("options")}, ensure_ascii=False) + "\n")
    return len(rows)


def plan(site_doctors=()):
    """What import would do, lesson by lesson; nothing is changed."""
    import lectures
    ls, bs = scan(site_doctors)
    have = {(m["module"], m["title"].lower()): m["id"] for m in lectures.all_lectures()}
    out = []
    for x in ls:
        if x["doctor_folder"] is None or not x["links"]:
            out.append({**x, "action": "skip: no doctor folder or no links"})
            continue
        sib = sorted((y for y in ls if y["doctor_folder"] == x["doctor_folder"] and y["chapter"] == x["chapter"]
                      and y["subject"] == x["subject"]), key=lambda y: (y["n"] or 0))
        out.append({**x, "title": nice(x["title"]), "chapter_lessons": [nice(y["title"]) for y in sib],
                    "lecture": have.get((x["module"], nice(x["title"]).lower())),
                    "action": "exists" if have.get((x["module"], nice(x["title"]).lower())) else "create"})
    return out, [{**b, "book": book_id(b)} for b in bs]


def import_all(q, site_doctors=(), kbps=16):
    """Names every lesson (with its chapter context) and queues its place job; adds its recording (linked once placed);
    reads its quiz into the owner's lists (a "required quiz" into Required, any other quiz into Doctor's other); queues
    every doctor's book for alignment. Returns a report."""
    import subprocess
    import lectures
    import page
    lessons, books = plan(site_doctors)
    report = []
    for x in lessons:
        if x["action"].startswith("skip"):
            report.append(f"skip {x['file']}: {x['action']}")
            continue
        lid = x["lecture"]
        if not lid:
            meta = lectures.create(x["module"], x["title"], x["doctor_id"] or x["doctor_folder"], subject=x["subject"],
                                   chapter=x["chapter"], chapter_lessons=x["chapter_lessons"])
            lid = meta["id"]
            q.add_jobs("place", [{"key": lid, "payload": {"lecture": lid}}])
            report.append(f"{lid}: named '{x['title']}' ({x['doctor_id'] or x['doctor_folder'] + ', no site doctor'}), place queued")
        meta = lectures.load(lid)
        for link in x["links"]:
            if link["kind"] == "recording" and not meta.get("source"):
                nxt = lectures.add(lid, x["module"], x["title"], kbps, url=link["url"])
                meta = lectures.load(lid)
                if nxt == "transcribe" or (nxt == "lecture_links" and meta.get("ranges")):
                    q.add_jobs(nxt, [{"key": lid, "payload": {"lecture": lid}}])
                report.append(f"{lid}: recording {meta.get('duration_s')} s, transcript from "
                              f"{meta['source'].get('transcript', 'the fleet')}")
            elif link["kind"] in ("quiz", "required_quiz") and not meta.get(f"quiz_read_{link['kind']}"):
                into = "required" if link["kind"] == "required_quiz" else "doctor_questions"
                f = lectures.folder(lid) / f"{link['kind']}.jsonl"
                n = read_form(link["url"], f)
                path = page.save_cover_file(f"{lid}-{into}-{f.name}", f.read_text(encoding="utf-8"))
                res = page.file_into_lecture(lid, into, path)
                meta = lectures.load(lid)
                meta[f"quiz_read_{link['kind']}"] = True
                lectures.save(meta)
                report.append(f"{lid}: {link['kind']} {n} questions into {into}; " + res.splitlines()[-1])
            elif link["kind"] == "mini_lecture":
                mini = next((m for m in lectures.all_lectures(x["module"])
                             if m.get("kind") == "summary" and m.get("covers") == [lid]), None)
                if not mini:
                    mini = lectures.create(x["module"], f"{x['title']} (mini lecture)", meta["doctor"], kind="summary",
                                           covers=[lid], subject=x["subject"], chapter=x["chapter"])
                    mini["source"] = {"telegram": link["url"]}  # the video waits for a Telegram session to download
                    lectures.save(mini)
                    report.append(f"{mini['id']}: mini lecture of {lid}, pages {lectures.page_ranges(mini)}; its "
                                  f"video {link['url']} waits for a Telegram session")
            elif link["kind"] == "telegram":
                report.append(f"{lid}: telegram {link['url']} kept for later (needs a Telegram session)")
    for b in books:
        if b["kind"] == "mcq":  # a doctor's MCQ book: its questions are copied out, never aligned as a book
            import mcq
            added = mcq.queue_book(q, b["module"], b["book"], b["file"], b["doctor_id"] or b["doctor_folder"], b["subject"])
            report.append(f"mcq book {b['book']}: {added}")
            continue
        jobs_file = ROOT / "modules" / b["module"] / "books" / f"{b['book']}.json"
        if jobs_file.exists():
            report.append(f"book {b['book']}: already queued")
            continue
        args = ["py", str(ROOT / "dm.py"), "add", "books", b["module"], "--book", b["book"], "--file", b["file"],
                "--title", f"{b['doctor_folder'].title()} {b['subject']} ({b['kind']})"]
        if b["doctor_id"]:
            args += ["--doctor", b["doctor_id"]]
        res = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
        report.append(f"book {b['book']}: {(res.stdout + res.stderr).strip()}")
    return report

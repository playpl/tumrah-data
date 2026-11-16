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
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCTORS = ROOT / "doctors"
MODULES = {"cns": "year2-cns", "msk": "year1-musculoskeletal"}
URL = re.compile(r"(?:https?://|(?:www\.)?youtube\.com/|youtu\.be/)\S+")
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
            url = m.group(0) if m.group(0).startswith("http") else "https://" + m.group(0)  # " lec youtube.com/watch?v=x"
            out.append({"kind": kind_of(line[:m.start()], url), "url": url})
    return out


def numbered(name):
    m = ORDER.match(name)
    return (int(m.group(1)), m.group(2)) if m else (None, name)


def clean_name(name):
    """A folder's name as plain text: Unicode letter styles flattened, "(auto)" and other bracketed notes dropped.
    '𝚆𝚊𝚐𝚒𝚑 𝙴𝚕𝚑𝚞𝚜𝚜𝚎𝚒𝚗𝚢 (auto)' -> 'Wagih Elhusseiny'."""
    return " ".join(re.sub(r"\([^)]*\)", " ", unicodedata.normalize("NFKC", name or "")).split())


def key_of(name):
    return clean_name(name).lower()


LIST_NAMES = (("auto", "all here updates"), ("auto", "get all lectures from here"), ("old", "old data"))


def list_files(doc):
    """The doctor folder's Telegram list files (owner, 2026-11-10): `all here updates (auto).txt` holds the link of the
    message the channel keeps editing (auto doctors: new lectures appear there), `old data.txt` the backup list (the
    previous batch's recordings). {"auto": message id, "old": message id}; a missing file is left out."""
    out = {}
    for f in sorted(Path(doc).glob("*.txt")):
        low = unicodedata.normalize("NFKC", f.stem).lower()
        for what, name in LIST_NAMES:
            if low.startswith(name):
                m = re.search(r"t\.me/(?:c/\d+|\w+)/(\d+)", f.read_text(encoding="utf-8", errors="replace"))
                if m:
                    out[what] = int(m.group(1))
    return out


def find_doctor_folder(subject, key, module="cns"):
    """The real folder of a doctor (its name may carry "(auto)" or fancy letters): doctors/<module>/<subject>/<key...>."""
    base = DOCTORS / module / subject
    for d in sorted(base.iterdir()) if base.exists() else []:
        if d.is_dir() and key_of(d.name) == key.lower():
            return d
    raise FileNotFoundError(f"no doctor folder '{key}' in {base}")


# Folder names the name matcher cannot tie to a site doctor on its own (checked by hand, 2026-11-08 and 2026-11-10).
# Keys are key_of(folder name). A folder with no entry and no match here has no site doctor yet (Cocci: ask the owner).
ALIASES = {"elsamahy": "dr-abdullah-el-samahi-phys", "ammar": "dr-ahmed-ammar-hist", "nageb": "dr-naguib-el-husseiny-phys",
           "azony": "dr-ibrahim-el-azouni-anat", "zahran": "dr-mohamed-zahran-hist", "amr mossafer": "dr-amr-mesafer-anat",
           "wagih elhusseiny": "dr-wajih-el-husseiny-anat", "mahmoud elhusseiny": "dr-mahmoud-el-husseiny-hist",
           "basel": "dr-basel-sherif-hist"}


def owner_aliases(db=None):
    """{folder key: site doctor id} the owner typed on the Today screen ("Set site doctor": ledger.db `rules`, keys
    `alias:<key>`). Read straight from the file, read only: decisions.py imports this module, so it is not imported here."""
    import sqlite3
    db = Path(db or ROOT / "ledger.db")
    if not db.exists():
        return {}
    con = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    try:
        return {k[len("alias:"):]: v for k, v in con.execute("SELECT key, value FROM rules WHERE key LIKE 'alias:%'") if v}
    except sqlite3.Error:
        return {}  # an older ledger with no rules table
    finally:
        con.close()


ALIASES.update(owner_aliases())  # the owner's answer wins; decisions.answer adds a new one to the running process too


def match_doctor(folder_name, site_doctors):
    """The site doctorId whose English name holds every word of the folder name (spelling may differ a little)."""
    def norm(s):
        return re.sub(r"[^a-z ]", " ", s.lower().replace("ss", "s").replace("ou", "o").replace("e", "a"))
    if key_of(folder_name) in ALIASES and (not site_doctors or any(d["id"] == ALIASES[key_of(folder_name)] for d in site_doctors)):
        return ALIASES[key_of(folder_name)]
    want = norm(clean_name(folder_name)).split()
    hits = [d["id"] for d in site_doctors if all(w in norm(d.get("name") or "") + " " + norm(d["id"]) for w in want)]
    return hits[0] if len(hits) == 1 else None


MEDIA = {".mp3", ".m4a", ".mp4", ".wav", ".ogg", ".opus", ".webm", ".aac"}


def url_file(f):
    """The link inside a Windows .url shortcut."""
    m = re.search(r"^URL=(\S+)", f.read_text(encoding="utf-8", errors="replace"), re.M)
    return m.group(1) if m else None


SETTLE_SECONDS = 180  # a file changed this recently may still be copying or recording: wait


def settling(f):
    return time.time() - Path(f).stat().st_mtime < SETTLE_SECONDS


def split_note(title):
    """("pain Revision", "for 1 and 2") from "pain Revision (for 1 and 2)": a bracket that starts with "for " is the owner's
    note to Claude, never part of the title (owner, 2026-11-12). Any other bracket stays in the title."""
    m = re.search(r"\(\s*(for\s[^)]*)\)\s*$", title, re.I)
    return (title[:m.start()].strip(), m.group(1).strip()) if m else (title, None)


def is_revision(title):
    return "revision" in title.lower()


def chapter_files(mod, subj, doc, did, have):
    """Lessons kept as files inside a chapter folder (owner, 2026-11-09): "3- Nerve fiber.mp3" is lesson 3's recording
    and "3- Nerve Fiber test.url" its quiz. A numbered .url with no lesson of its number in that chapter (Mossafer's
    "3- mcq.url") is the chapter's quiz: its questions go to the chapter lessons that teach them. A .txt lesson of the
    same number gets these links added. An unnumbered recording ("Pain 2 .mp3") is the chapter's next lesson, in name
    order; one with "revision" in its name is a revision of that chapter (kind "revision"). A file changed within
    SETTLE_SECONDS is reported as waiting. Files at the doctor folder's top (Azouny's mp4s, Nagib's forms) are handled
    by new_doctors.py and nagib_quizzes.py, not here."""
    out = []
    for chap in sorted(p for p in doc.iterdir() if p.is_dir()):
        cn, ctitle = numbered(chap.name)
        groups, loose = {}, []
        for f in sorted(chap.iterdir(), key=lambda p: p.name.lower()):
            n, _ = numbered(f.stem)
            if f.suffix.lower() not in MEDIA | {".url"}:
                continue
            if n is None:
                if f.suffix.lower() in MEDIA:
                    loose.append(f)
                continue
            groups.setdefault(n, []).append(f)
        base = {"module": MODULES.get(mod.name, mod.name), "subject": subj.name, "doctor_folder": doc.name,
                "doctor_id": did, "chapter": ctitle or chap.name, "chapter_n": cn}
        top = max([k for k in groups] + [x["n"] for x in have if Path(x["file"]).parent == chap and x["n"] is not None], default=0)
        for f in loose:
            title, note = split_note(f.stem.strip())
            if is_revision(title):
                out.append({**base, "n": 900 + len(out), "title": title, "file": str(f), "kind": "revision", "note": note,
                            "links": [{"kind": "recording", "file": str(f)}], "waiting": settling(f)})
            else:
                top += 1
                out.append({**base, "n": top, "title": title, "file": str(f),
                            "links": [{"kind": "recording", "file": str(f)}], "waiting": settling(f)})
        for n, files in sorted(groups.items()):
            media = [f for f in files if f.suffix.lower() in MEDIA]
            urls = [f for f in files if f.suffix.lower() == ".url"]
            row_links = [{"kind": "recording", "file": str(f)} for f in media[:1]]
            for f in urls:
                u = url_file(f)
                if u:
                    row_links.append({"kind": kind_of(f.stem + " quiz", u), "url": u})
            txt = next((x for x in have if Path(x["file"]).parent == chap and x["n"] == n), None)
            if txt:
                txt["links"] += [k for k in row_links if k["kind"] != "recording" or
                                 not any(y["kind"] == "recording" for y in txt["links"])]
                continue
            waiting = any(settling(f) for f in media)
            if media:
                out.append({**base, "n": n, "title": numbered(media[0].stem)[1], "file": str(media[0]), "links": row_links,
                            "waiting": waiting})
            else:
                out.append({**base, "n": n, "title": numbered(urls[0].stem)[1], "file": str(urls[0]), "links": row_links,
                            "chapter_quiz": True})
    return out


HAS_OWN_QUIZ_SCRIPT = {"nageb"}  # Nagib's top-level forms: nagib_quizzes.py


def doctor_quizzes(mod, subj, doc, did):
    """A form shortcut at the doctor folder's top (Wagih's "full quiz on all spinal cord.url") is a quiz for the doctor's
    first chapter of the subject: filed like a chapter quiz, into the lessons that teach each question."""
    if key_of(doc.name) in HAS_OWN_QUIZ_SCRIPT:
        return []
    from dm import CHAPTERS
    out = []
    for f in sorted(doc.glob("*.url")):
        u = url_file(f)
        if u:
            out.append({"module": MODULES.get(mod.name, mod.name), "subject": subj.name, "doctor_folder": doc.name,
                        "doctor_id": did, "chapter": CHAPTERS.get(subj.name), "chapter_n": None, "n": 0, "title": f.stem,
                        "file": str(f), "links": [{"kind": kind_of(f.stem + " quiz", u), "url": u}], "chapter_quiz": True})
    return out


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
                    if "mcq" in name:  # "mcq first chapter only.pdf" is cut short; "Full MCQ book .pdf" is not
                        kind = "mcq_partial" if ("only" in name or name.startswith("partial")) else "mcq"
                    else:
                        kind = "partial" if name.startswith("partial") else "full"
                    books.append({"module": MODULES.get(mod.name, mod.name), "subject": subj.name, "doctor_folder": doc.name,
                                  "doctor_id": did, "file": str(pdf), "kind": kind, "partial": kind in ("partial", "mcq_partial")})
                for f in sorted(doc.rglob("*.txt")):
                    chap = f.parent if f.parent != doc else None
                    cn, ctitle = numbered(chap.name) if chap else (None, None)
                    n, title = numbered(f.stem)
                    lessons.append({"module": MODULES.get(mod.name, mod.name), "subject": subj.name,
                                    "doctor_folder": doc.name, "doctor_id": did, "chapter": ctitle, "chapter_n": cn,
                                    "title": title, "n": n, "file": str(f),
                                    "links": links(f.read_text(encoding="utf-8", errors="replace"))})
                lessons += chapter_files(mod, subj, doc, did, lessons)
                lessons += doctor_quizzes(mod, subj, doc, did)
            for f in sorted(subj.glob("*.txt")):  # a lesson file with no doctor folder yet
                n, title = numbered(f.stem)
                lessons.append({"module": MODULES.get(mod.name, mod.name), "subject": subj.name, "doctor_folder": None,
                                "doctor_id": None, "chapter": None, "chapter_n": None, "title": title, "n": n,
                                "file": str(f), "links": links(f.read_text(encoding="utf-8", errors="replace"))})
    return lessons, books


if __name__ == "__main__" and sys.argv[1:2] == ["import"]:
    pass  # handled at the end of the file, once import_all is defined
elif __name__ == "__main__":
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


ACRONYMS = {"csf", "cns", "pns", "mcq", "ans", "ecg"}


def nice(title):
    """First letter up; a lone acronym word in capitals ("csf " -> "CSF")."""
    title = (title or "").strip()
    return title.upper() if title.lower() in ACRONYMS else title[:1].upper() + title[1:]


def book_id(b):
    """mossafer-anat-1 (a partial book, the first one added), zahran-hist-full, elsamahy-phys-mcq."""
    suffix = {"partial": "1", "full": "full", "mcq": "mcq", "mcq_partial": "mcq"}[b.get("kind", "partial")]
    # A second MCQ book that is another part, not a longer copy ("CNS MCQ Dr Elazony(part 2).pdf") keeps its own id.
    part = re.search(r"part\s*(\d+)", Path(b.get("file") or "").stem.lower()) if suffix == "mcq" else None
    if part and int(part.group(1)) > 1:
        suffix += part.group(1)
    return f"{key_of(b['doctor_folder']).split()[-1]}-{b['subject'][:4].lower()}-{suffix}"


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


def mini_target(x, metas):
    """The lecture a revision file's note names ("(for Pain analgesia system pain control)"), when it is one lecture of the
    same doctor and chapter; else None."""
    note = (x.get("note") or "")
    if x.get("kind") != "revision" or not note.lower().startswith("for "):
        return None
    want = note[4:].strip().lower()
    hit = [m for m in metas if m.get("kind", "lecture") == "lecture" and m.get("title", "").lower() == want
           and m.get("module") == x["module"] and m.get("chapter") == x["chapter"]]
    return hit[0] if len(hit) == 1 else None


def source_keys(module, sources):
    """Keys that tie a folder lesson to its lecture whatever its title: each recording file path and YouTube video id.
    Titles are rewritten from mother_lists.json ("Spinal cord 1" becomes "Spinal cord part 1"), so a title alone no
    longer finds the lecture (2026-11-15: a dry run would have re-created 13 lectures)."""
    out = set()
    for s in sources:
        if s.get("file"):
            out.add((module, "file", str(Path(s["file"])).lower()))
        url = s.get("url") or s.get("youtube")
        m = re.search(r"(?:youtu\.be/|[?&]v=|/shorts/)([\w-]{11})", url or "")
        if m:
            out.add((module, "yt", m.group(1)))
    return out


def plan(site_doctors=()):
    """What import would do, lesson by lesson; nothing is changed."""
    import lectures
    ls, bs = scan(site_doctors)
    metas = lectures.all_lectures()
    title_have = {(m["module"], m["title"].lower()): m["id"] for m in metas}
    by_src = {}
    for m in metas:
        for k in source_keys(m["module"], [m.get("source") or {}]):
            by_src.setdefault(k, set()).add(m["id"])

    class _Have(dict):
        """(module, title) -> lecture id; a folder lesson is first found by its recording (source_keys), then by title."""
        def get(self, key, default=None):
            return dict.get(self, key, title_have.get(key, default))

    have = _Have()
    for x in ls:
        if x.get("title") is None:
            continue
        ids = set()
        for k in source_keys(x["module"], [ln for ln in x.get("links") or [] if ln.get("kind") == "recording"]):
            ids |= by_src.get(k, set())
        if len(ids) == 1:
            have[(x["module"], nice(x["title"]).lower())] = ids.pop()
    by_id = {m["id"]: m for m in metas}
    # The site doctor of a folder: the one its already named lessons carry (the site has no doctors table to match).
    folder_doctor = {}
    for x in ls:
        lid = have.get((x["module"], nice(x["title"] or "").lower()))
        if x["doctor_folder"] and lid and (by_id[lid].get("doctor") or "").startswith("dr-"):
            folder_doctor.setdefault((x["module"], x["subject"], x["doctor_folder"]), by_id[lid]["doctor"])
    out = []
    for x in ls:
        if x["doctor_folder"] is None or not x["links"]:
            out.append({**x, "action": "skip: no doctor folder or no links"})
            continue
        if x["n"] is None:  # "all here updates", "2.5- quiz ...": notes and Telegram lists, not lessons (new_doctors.py)
            out.append({**x, "action": "skip: not a numbered lesson"})
            continue
        if x.get("waiting"):  # a recording still being copied or recorded (settling): next run takes it
            out.append({**x, "title": nice(x["title"]), "action": "skip: still being written, wait"})
            continue
        x = {**x, "doctor_id": x["doctor_id"] or folder_doctor.get((x["module"], x["subject"], x["doctor_folder"]))
             or ALIASES.get(key_of(x["doctor_folder"]))}
        if x.get("chapter_quiz"):
            out.append({**x, "action": "chapter quiz"})
            continue
        sib = sorted((y for y in ls if y["doctor_folder"] == x["doctor_folder"] and y["chapter"] == x["chapter"]
                      and y["subject"] == x["subject"] and y["n"] is not None and not y.get("chapter_quiz") and y.get("kind") != "revision"),
                     key=lambda y: (y["n"] or 0))
        mini = mini_target(x, metas)
        if mini:  # "x Revision (for <lecture title>)" is that lecture's mini lecture, not a revision (owner, 2026-11-12)
            x = {**x, "kind": "summary", "covers": [mini["id"]], "title": f"{mini['title']} (mini lecture)"}
        out.append({**x, "title": nice(x["title"]), "chapter_lessons": [nice(y["title"]) for y in sib],
                    "lecture": have.get((x["module"], nice(x["title"]).lower())),
                    "action": "exists" if have.get((x["module"], nice(x["title"]).lower())) else "create"})
    fulls = {}
    for b in bs:
        if b["kind"] == "full":
            fulls.setdefault((b["module"], b["subject"], b["doctor_folder"]), []).append(b)
    books = []
    for b in bs:
        bid = book_id(b)
        if b["kind"] == "full" and len(fulls[(b["module"], b["subject"], b["doctor_folder"])]) > 1:
            bid += "-" + re.sub(r"[^a-z0-9]+", "-", Path(b["file"]).stem.lower()).strip("-")  # several full books
        books.append({**b, "book": bid,
                      "doctor_id": b["doctor_id"] or folder_doctor.get((b["module"], b["subject"], b["doctor_folder"]))
                      or ALIASES.get(key_of(b["doctor_folder"]))})
    return out, books


def media_row(module, lid, file):
    ext = Path(file).suffix.lower()
    return {"lecture": lid, "file": str(file), "key": f"lectures/{module}/{lid}/recording{ext}",
            "field": "videoUrl" if ext in (".mp4", ".webm") else "audioUrl"}


def media_merge(module, rows):
    """Adds rows to modules/<module>/site/media.json (uploadLessonMedia.ts), one per lecture: a lecture's new row
    replaces its old one, every other lecture's row is kept."""
    f = ROOT / "modules" / module / "site" / "media.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    new = {r["lecture"] for r in rows}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps([r for r in old if r["lecture"] not in new] + rows, indent=1), encoding="utf-8")


# Doctors whose books are never aligned: Elazouny's PDFs are pictures with no text; every one of his lectures gets all
# his files instead (owner, 2026-11-09).
NO_ALIGN = {"azony"}

CHAPTER_QUIZZES = "chapter_quizzes.json"  # modules/<module>/site/: {form url: report} of the chapter quizzes filed


def chapter_quiz_filed(x):
    """True when this chapter quiz's form is already in chapter_quizzes.json (import_all would only say "already filed")."""
    done_f = ROOT / "modules" / x["module"] / "site" / CHAPTER_QUIZZES
    done = json.loads(done_f.read_text(encoding="utf-8")) if done_f.exists() else {}
    return x["links"][0]["url"] in done


def chapter_quiz(x):
    """A chapter's quiz (Mossafer's "3- mcq.url"): read the form (read only, never submitted), match it to the bank
    (`dm.py cover`), and file each question into the doctor's lesson of that chapter that teaches it (the lesson its
    handout pointer falls in, fast_points.json). Questions no lesson claims go to the chapter's first lesson."""
    import lectures
    import page
    import cover
    done_f = ROOT / "modules" / x["module"] / "site" / CHAPTER_QUIZZES
    done = json.loads(done_f.read_text(encoding="utf-8")) if done_f.exists() else {}
    url = x["links"][0]["url"]
    if url in done:
        return [f"chapter quiz {x['file']}: already filed"]
    doctor = x["doctor_id"] or x["doctor_folder"]
    order = {t.lower(): i for i, t in enumerate(next((m.get("chapter_lessons") for m in lectures.all_lectures(x["module"])
                                                      if m.get("doctor") == doctor and m.get("chapter") == x["chapter"]
                                                      and m.get("chapter_lessons")), []))}
    mine = sorted((m for m in lectures.all_lectures(x["module"]) if m.get("kind", "lecture") == "lecture"
                   and m.get("doctor") == doctor and m.get("subject") == x["subject"] and m.get("chapter") in (x["chapter"], None)),
                  key=lambda m: (order.get(m["title"].lower(), 99), m["id"]))
    if not mine:
        return [f"chapter quiz {x['file']}: no named lesson of {doctor} in {x['chapter']} yet"]
    tmp = ROOT / "bank" / "inbox" / f"chapter-{re.sub(r'[^a-z0-9]+', '-', (x['doctor_folder'] + ' ' + x['chapter'] + ' ' + x['title']).lower())}.jsonl"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    n = read_form(url, tmp)
    path = tmp
    page.run_cover(path)
    entry = cover.covered(path)
    rows = page.read_jsonl(ROOT / "bank" / f"cover_{entry['sha']}.jsonl") if entry else []
    _, by = page.bank_rows()
    prefix = {k[:16]: k for k in by}
    pts_f = ROOT / "modules" / x["module"] / "site" / "fast_points.json"
    points = json.loads(pts_f.read_text(encoding="utf-8")) if pts_f.exists() else {}
    ids = [m["id"] for m in mine]
    home = {}
    for i, r in enumerate(rows):
        m = r.get("match")
        wk = prefix.get(m[5:]) if isinstance(m, str) and m.startswith("bank:") else None
        homes = [h for h in ids if h in ((points.get(wk) or {}).get("homes") or [])]
        home.setdefault(homes[0] if homes else ids[0], set()).add(i)
    report = [f"chapter quiz {x['title']} ({doctor}, {x['chapter']}): {n} questions"]
    for lid, only in home.items():
        res = page.file_into_lecture(lid, "doctor_questions", path, only=only)
        report.append(f"  {lid}: {len(only)} rows; " + res.splitlines()[-1])
    done[url] = report
    done_f.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
    return report


def repair_paths():
    """A doctor's folder renamed ("azony" -> "azony (auto)") or a file moved: every lecture's local recording and every
    media.json row that points at a file that is gone is pointed at the file of the same name (and size) now in doctors/.
    Returns report lines."""
    import lectures
    where = {}
    for f in DOCTORS.rglob("*") if DOCTORS.exists() else []:
        if f.is_file():
            where.setdefault(f.name.lower(), []).append(f)

    def find(old):
        name = Path(old).name.lower()
        c = where.get(name, [])
        if not c:  # renumbered by the owner: "Pain 2 .mp3" -> "4- Pain 2 .mp3"
            c = [f for n, fs in where.items() if n.endswith(name) and re.fullmatch(r"\d+(\.\d+)?-\s*", n[:-len(name)])
                 for f in fs]
        if not c:  # renumbered again: "4- csf .mp3" -> "5- csf .mp3"
            bare = re.sub(r"^\d+(\.\d+)?-\s*", "", name)
            c = [f for n, fs in where.items() if re.sub(r"^\d+(\.\d+)?-\s*", "", n) == bare for f in fs]
        return c[0] if len(c) == 1 else None

    report = []
    for m in lectures.all_lectures():
        f = (m.get("source") or {}).get("file")
        if f and not Path(f).exists() and (new := find(f)):
            m["source"]["file"] = str(new)
            lectures.save(m)
            report.append(f"{m['id']}: recording path now {new.name}")
    for mod in set(MODULES.values()):
        mf = ROOT / "modules" / mod / "site" / "media.json"
        if not mf.exists():
            continue
        rows = json.loads(mf.read_text(encoding="utf-8"))
        changed = False
        for r in rows:
            if not Path(r["file"]).exists() and (new := find(r["file"])):
                r["file"] = str(new)
                changed = True
                report.append(f"media.json {r['lecture']}: file now {new.name}")
        if changed:
            mf.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return report


def chapter_quizzes_done(module):
    f = ROOT / "modules" / module / "site" / CHAPTER_QUIZZES
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def revision_covers(x):
    """The lectures a revision file reviews: the same doctor's lectures of its chapter whose title shares a word with the
    revision's name ("pain Revision" -> the pain lectures); every lecture of the chapter when none does."""
    import lectures
    doctor = x["doctor_id"] or x["doctor_folder"]
    mine = [m for m in lectures.all_lectures(x["module"]) if m.get("kind", "lecture") == "lecture"
            and m.get("doctor") == doctor and (x["chapter"] is None or m.get("chapter") == x["chapter"])]
    words = {w for w in re.findall(r"[a-z]+", x["title"].lower()) if w != "revision" and len(w) > 2}
    named = [m for m in mine if words & set(re.findall(r"[a-z]+", m["title"].lower()))]
    nums = set(re.findall(r"\d+", x.get("note") or ""))  # "(for 1 and 2)": the lessons of that name ending in 1 and in 2
    if nums:
        pick = [m for m in named if (re.search(r"(\d+)\s*$", m["title"]) or [None, None])[1] in nums]
        if pick:
            return [m["id"] for m in pick]
    return [m["id"] for m in (named or mine)]


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
        if x["action"] == "chapter quiz":
            report += chapter_quiz(x)
            continue
        lid = x["lecture"]
        if not lid:
            kind = x.get("kind", "lecture")
            ctx = {}
            if kind == "summary":
                ctx["covers"] = x["covers"]
            if kind == "revision":
                ctx["covers"] = revision_covers(x)
                if not ctx["covers"]:
                    report.append(f"revision '{x['title']}': no lecture of {x['doctor_folder']} in {x['chapter']} to cover yet, waits")
                    continue
            meta = lectures.create(x["module"], x["title"], x["doctor_id"] or x["doctor_folder"], kind=kind,
                                   subject=x["subject"], chapter=x["chapter"], chapter_lessons=x["chapter_lessons"], **ctx)
            lid = meta["id"]
            q.add_jobs("place", [{"key": lid, "payload": {"lecture": lid}}])
            report.append(f"{lid}: named '{x['title']}' ({x['doctor_id'] or x['doctor_folder'] + ', no site doctor'}), place queued")
        meta = lectures.load(lid)
        if x.get("kind", "lecture") == "lecture" and x["n"] is not None and x["n"] < 900                 and meta.get("order_key") != [x.get("chapter_n") or 0, x["n"]]:
            meta["order_key"] = [x.get("chapter_n") or 0, x["n"]]  # the owner's file number: the lesson's place (dm.lesson_order)
            lectures.save(meta)
        for link in x["links"]:
            if link["kind"] == "recording" and (not meta.get("source") or meta.get("backup")):  # new data replaces a backup
                nxt = lectures.add(lid, x["module"], x["title"], kbps, url=link.get("url"), file=link.get("file"))
                meta = lectures.load(lid)
                if link.get("file"):  # a local recording is uploaded to the site by uploadLessonMedia.ts
                    media_merge(x["module"], [media_row(x["module"], lid, link["file"])])
                if nxt == "transcribe" or (nxt == "lecture_links" and meta.get("ranges")):
                    q.add_jobs(nxt, [{"key": lid, "payload": {"lecture": lid}}])
                report.append(f"{lid}: recording {meta.get('duration_s')} s, transcript from "
                              f"{meta['source'].get('transcript', 'the fleet')}")
            elif link["kind"] in ("quiz", "required_quiz") and not meta.get(f"quiz_read_{link['kind']}"):
                if link["url"] in chapter_quizzes_done(x["module"]):
                    report.append(f"{lid}: quiz {link['url'][-12:]} is already filed as a chapter quiz, not added again")
                    continue
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
                if mini and (mini.get("source") or {}).get("telegram") != link["url"] and not mini["source"].get("file"):
                    mini["source"]["telegram"] = link["url"]  # the owner's newer link replaces the old one
                    lectures.save(mini)
                    report.append(f"{mini['id']}: mini lecture link now {link['url']}")
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
        if b["kind"] == "mcq_partial" and any(o["kind"] == "mcq" and (o["module"], o["subject"], o["doctor_folder"]) ==
                                              (b["module"], b["subject"], b["doctor_folder"]) for o in books):
            continue  # the full MCQ book is here: books_merge moves this one aside
        if b["kind"] in ("mcq", "mcq_partial"):  # a doctor's MCQ book: its questions are copied out, never aligned as a book
            import mcq  # (a NO_ALIGN doctor's MCQ book too: it has text, owner 2026-11-14 added Azony's part 2)
            added = mcq.queue_book(q, b["module"], b["book"], b["file"], b["doctor_id"] or b["doctor_folder"], b["subject"])
            report.append(f"mcq book {b['book']}: {added}")
            continue
        if key_of(b["doctor_folder"]) in NO_ALIGN:
            report.append(f"book {b['book']}: not aligned ({b['doctor_folder']}: picture-only books, owner 2026-11-09)")
            continue
        jobs_file = ROOT / "modules" / b["module"] / "books" / f"{b['book']}.json"
        if b["kind"] == "partial" and not jobs_file.exists() and any(
                o["kind"] == "full" and (o["module"], o["subject"], o["doctor_folder"]) == (b["module"], b["subject"], b["doctor_folder"])
                for o in books):
            report.append(f"book {b['book']}: not queued, the doctor's full book is here (its pages are folded into it)")
            continue
        if jobs_file.exists():
            report.append(f"book {b['book']}: already queued")
            continue
        args = ["py", str(ROOT / "dm.py"), "add", "books", b["module"], "--book", b["book"], "--file", b["file"],
                "--title", f"{b['doctor_folder'].title()} {b['subject']} ({b['kind']})"]
        if b["doctor_id"]:
            args += ["--doctor", b["doctor_id"]]
        res = subprocess.run(args, capture_output=True, text=True, cwd=ROOT)
        report.append(f"book {b['book']}: {(res.stdout + res.stderr).strip()}")
    import books_merge
    report += books_merge.merge_partials(q, books)
    return report


if __name__ == "__main__" and sys.argv[1:2] == ["import"]:
    # py doctors_folder.py import: names new lessons, adds recordings, files quizzes, queues books (see import_all)
    import queue_db
    sys.stdout.reconfigure(encoding="utf-8")
    for line in import_all(queue_db.Queue()):
        print(line)

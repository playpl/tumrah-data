"""What is missing (owner, 2026-11-10: "tell me if anything is missing in our files"). Counts and ids only; reads files.

    py audit.py        lectures (recording, transcript, handout placement, site lesson, owner questions and keys),
                       books and alignment, MCQ books, doctor folders and PDFs, queue.
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import doctors_folder
import lectures

ROOT = Path(__file__).resolve().parent
MODULE = "year2-cns"


def ids(xs, n=12):
    xs = list(xs)
    return ", ".join(xs[:n]) + (f" (+{len(xs) - n})" if len(xs) > n else "") if xs else "none"


def run():
    out = []
    metas = [m for m in lectures.all_lectures(MODULE)]
    lec = [m for m in metas if m.get("kind", "lecture") == "lecture"]
    d = lambda m: lectures.folder(m["id"])  # noqa: E731
    no_rec = [m["id"] for m in metas if not m.get("source")]
    no_tr = [m["id"] for m in metas if m.get("source") and not (d(m) / "raw.txt").exists() and not (d(m) / "clean.txt").exists()]
    no_place = [m["id"] for m in metas if not m.get("ranges")]
    no_site = [m["id"] for m in metas if not m.get("lesson")]
    no_links = [m["id"] for m in metas if m.get("source") and not (d(m) / "links.jsonl").exists()]
    out.append(f"LECTURES {len(metas)} ({len(lec)} lectures, {len(metas) - len(lec)} mini lectures/revisions)")
    out.append(f"  no recording:                 {len(no_rec)}  {ids(no_rec)}")
    out.append(f"  recording, no transcript yet: {len(no_tr)}  {ids(no_tr)}   (fleet is down)")
    out.append(f"  not placed in the handout:    {len(no_place)}  {ids(no_place)}   (place jobs wait for the fleet)")
    out.append(f"  no handout links (lecture_links): {len(no_links)}")
    out.append(f"  not a lesson on the site yet: {len(no_site)}  {ids(no_site)}")
    old = [m["id"] for m in metas if m.get("backup")]
    out.append(f"  on a backup recording: {len(old)}  {ids(old)}")
    dq = Counter()
    for m in metas:
        for name in ("required", "doctor_questions"):
            for it in m.get(name) or []:
                r = it.get("row")
                dq[(name, "no key (a form or book with no key yet)" if r and r.get("key") is None else "ok")] += 1
    out.append(f"  owner question rows without a key: {sum(v for (n, k), v in dq.items() if k != 'ok')} of {sum(dq.values())}")
    out.append(f"  lectures with no required list: {len([m['id'] for m in lec if not m.get('required')])} of {len(lec)}")

    db = sqlite3.connect(ROOT / "queue.db")
    rows = db.execute("SELECT flow, status, COUNT(*) FROM jobs GROUP BY flow, status").fetchall()
    out.append("QUEUE " + ", ".join(f"{f}:{s} {n}" for f, s, n in rows if s != "passed"))
    books = sorted((ROOT / "modules" / MODULE / "books").glob("*.json"))
    out.append("BOOKS (aligned pages = passed jobs)")
    for b in books:
        bid = b.stem
        st = Counter(s for (s,) in db.execute("SELECT status FROM jobs WHERE flow='books' AND key LIKE ?", (f"{MODULE}-{bid}-p%",)))
        out.append(f"  {bid}: " + (", ".join(f"{k} {v}" for k, v in st.items()) or "not queued"))
    mcq = Counter()
    for (k, s) in db.execute("SELECT key, status FROM jobs WHERE flow='mcq'"):
        mcq[(k.split("-p")[0].replace(MODULE + "-", ""), s)] += 1
    out.append("MCQ BOOKS " + "; ".join(f"{b}:{s} {n}" for (b, s), n in sorted(mcq.items())))

    out.append("DOCTORS FOLDER")
    lessons, bks = doctors_folder.scan()
    for x in lessons:
        if x["n"] is not None and not x["links"]:
            out.append(f"  lesson file with no link: {x['file']}")
    empty = [x for x in lessons if x["doctor_folder"] is None or (not x["links"] and x["n"] is None)]
    for x in empty:
        out.append(f"  empty or doctor-less file: {x['file']}")
    for d_ in sorted(p for m in doctors_folder.DOCTORS.glob("*/*") for p in m.iterdir() if p.is_dir()):
        parts = []
        k = doctors_folder.key_of(d_.name)
        if not doctors_folder.ALIASES.get(k):
            parts.append("no site doctor")
        if not any(b["doctor_folder"] == d_.name for b in bks):
            parts.append("no book")
        if not any(x["doctor_folder"] == d_.name and x["links"] for x in lessons) and not doctors_folder.list_files(d_):
            parts.append("no lessons")
        if parts:
            out.append(f"  {k}: " + ", ".join(parts))
    lists = ROOT / "sources" / "lists"
    n_pdf = 0
    for f in lists.glob("*.json") if lists.exists() else []:
        if f.name.endswith(".prev.json") or f.stem == "sync":
            continue
        dd = json.loads(f.read_text(encoding="utf-8"))
        for it in (dd.get("sections") or {}).get("pdfs", []):
            for p in it["parts"]:
                post = (dd.get("posts") or {}).get(str(p["post"])) or {}
                if post.get("size") and not any(post["size"] == b.stat().st_size for b in doctors_folder.DOCTORS.rglob("*.pdf")):
                    n_pdf += 1
    out.append(f"  PDFs the Telegram lists link that are not in any doctor folder: {n_pdf}")
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(run()))

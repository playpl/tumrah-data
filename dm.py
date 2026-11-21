"""tumrah-data command line. Commands are added as the plan builds them."""
import argparse
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "modules"
POLLS_PAGE = "http://127.0.0.1:8765/status"
sys.stdout.reconfigure(encoding="utf-8")


def cmd_status(_):
    print("modules:")
    for d in sorted(p for p in MODULES.glob("*") if p.is_dir()):
        lines = d / "lines.jsonl"
        n = sum(1 for _ in lines.open(encoding="utf-8")) if lines.exists() else 0
        print(f"  {d.name}: handout {'yes' if (d / 'handout.pdf').exists() else 'MISSING'}, lines {n or 'not split'}")
    if (ROOT / "queue.db").exists():
        import queue_db
        q = queue_db.Queue()
        for flow, counts in sorted(q.progress().items()):
            print(f"queue {flow}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        q.close()
    try:
        with urllib.request.urlopen(POLLS_PAGE, timeout=3) as r:
            s = json.load(r)
        print(f"polls: stage {s['stage']}, to vote {s['to_vote']}, about {s['eta_hours']} h left"
              f"{', running' if s['running'] else ''}")
    except OSError:
        print("polls: page off (Polls.bat starts it; the job may still run)")


def cmd_lines(args):
    import hub
    pdf = MODULES / args.module / "handout.pdf"
    if not pdf.exists():
        sys.exit(f"no handout: put it at {pdf}")
    lines = hub.split_handout(pdf, args.module)
    hub.write_lines(lines, pdf.with_name("lines.jsonl"))
    kinds = Counter("page" if ln.figure == "page" else "figure" if ln.figure is not None else "line" for ln in lines)
    printed = {ln.page: ln.printed for ln in lines}
    print(f"{args.module} {lines[0].hash}: {len(printed)} pages, {kinds['line']} lines, {kinds['figure']} figures, "
          f"{kinds['page']} pages with no text, {sum(v is None for v in printed.values())} pages without a printed number")


POINTER_BATCH, BOOK_BATCH = 25, 10  # 10 book pages: one per subagent (owner 2026-11-08)


def pointer_jobs(module, questions, order):
    """Batches of 25 in the owner's set order (doctor, quiz, past exam, ai; unknown sets last)."""
    import hashlib
    rank = {s: i for i, s in enumerate(order)}
    qs = sorted(questions, key=lambda q: (rank.get(q.get("set"), len(rank)), q.get("lesson") or "", q["qid"]))
    jobs = []
    for i in range(0, len(qs), POINTER_BATCH):
        batch = qs[i:i + POINTER_BATCH]
        key = f"{module}-" + hashlib.sha1(",".join(q["qid"] for q in batch).encode()).hexdigest()[:12]
        jobs.append({"key": key, "payload": {"module": module, "batch": batch}})
    return jobs


def book_jobs(module, book_id, pages):
    return [{"key": f"{module}-{book_id}-p{pages[i]['page']:04d}",
             "payload": {"module": module, "book_id": book_id, "pages": pages[i:i + BOOK_BATCH]}}
            for i in range(0, len(pages), BOOK_BATCH)]


def book_pages(pdf, book_id, first=None, last=None):
    import fitz
    with fitz.open(pdf) as doc:
        a, b = first or 1, min(last or doc.page_count, doc.page_count)
        return [{"book_id": book_id, "page": n, "text": doc[n - 1].get_text("text")} for n in range(a, b + 1)]


def cmd_add(args):
    import queue_db
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if not (MODULES / args.module / "lines.jsonl").exists():
        sys.exit(f"run `py dm.py lines {args.module}` first")
    if args.flow == "reference":
        jobs = [{"key": args.module, "payload": {"module": args.module}}]
    elif not args.file:
        sys.exit("--file is required")
    elif args.flow == "pointers":
        from flows.common import read_jsonl
        jobs = pointer_jobs(args.module, read_jsonl(args.file), cfg["pointer_order"])
    else:
        import shutil
        first, last = (int(x) for x in args.pages.split("-")) if args.pages else (None, None)
        keep = MODULES / args.module / "books" / f"{args.book}.pdf"
        keep.parent.mkdir(parents=True, exist_ok=True)
        if Path(args.file).resolve() != keep.resolve():
            shutil.copy2(args.file, keep)
        meta = keep.with_suffix(".json")
        old = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
        meta.write_text(json.dumps({"book_id": args.book, "title": args.title or old.get("title"),
                                    "doctor": args.doctor or old.get("doctor")}, ensure_ascii=False), encoding="utf-8")
        jobs = book_jobs(args.module, args.book, book_pages(keep, args.book, first, last))
    q = queue_db.Queue()
    added = q.add_jobs(args.flow, jobs)
    q.close()
    print(f"{args.flow}: {len(jobs)} jobs, {added} new")


def cmd_lecture(args):
    import lectures
    import queue_db
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if not (args.file or args.youtube):
        sys.exit("give --file <audio or video> or --youtube <url>")
    pages = [int(x) for x in args.pages.split("-")] if args.pages else None
    nxt = lectures.add(args.id, args.module, args.title or args.id, cfg["lecture_audio_kbps"], file=args.file,
                       url=args.youtube, lesson=args.lesson, pdf_pages=pages, transcribe=not args.no_transcribe,
                       doctor=args.doctor)
    meta = lectures.load(args.id)
    print(f"{args.id}: {meta['duration_s']} s, transcript from {meta['source'].get('transcript', 'the fleet')}")
    if nxt:
        q = queue_db.Queue()
        q.add_jobs(nxt, [{"key": args.id, "payload": {"lecture": args.id}}])
        q.close()
        print(f"queued {nxt}")
    else:
        print("not queued: Transcribe is off for this lecture")


# The handout's own chapter names for the first chapter of each subject (the doctors' folders say "chapter 1").
CHAPTERS = {"anatomy": "Spinal cord", "histology": "Nervous tissue", "physiology": "Sensations"}


def list_chapters(module):
    """(lecture id -> chapter title, subject -> titles in order, doctor id -> its list items, subject -> {key: title}): the chapter is the item of the doctor's Telegram list (the
    mother message) the lecture is posted under: "- Spinal cord" with its parts 1, 2, 3 (owner, 2026-11-14: chapters come from
    the message, never from the handout or from our own guess). The same title in two doctors' lists is one chapter; order =
    first appearance (doctors in folder order, items in list order)."""
    import auto_doctors
    import tg_lists
    import doctors_folder
    docs = [d for d in auto_doctors.auto_doctors() if d["module"] == module and d["auto"]]
    lists = {d["auto"]: tg_lists.load(d["auto"]) for d in docs}
    posts = {pid: p for l in lists.values() if l for pid, p in l["posts"].items()}
    post_to_lecture = auto_doctors.known(module, posts)
    of, order, seen, by_doctor = {}, {}, {}, {}
    for d in docs:
        lst = lists[d["auto"]]
        for item in (lst or {}).get("sections", {}).get("lectures", []):
            title = (item["title"] or "").strip()  # exactly as the message says (owner, 2026-11-14): no capitalizing, no fixing
            subj = d["subject"].lower()
            key = _re_words(title)
            by_doctor.setdefault(d["doctor_id"], []).append((title, key))
            seen.setdefault(subj, {})
            if key not in seen[subj]:
                seen[subj][key] = title
                order.setdefault(subj, []).append(title)
            for part in item["parts"]:
                lid = post_to_lecture.get(part["post"]) if part["post"] is not None else None
                if lid:
                    of[lid] = seen[subj][key]
    return of, order, by_doctor, seen


def _re_words(title):
    import re
    return " ".join(re.findall(r"[a-z0-9]+", (title or "").lower()))


def lesson_order(metas):
    """{lecture id: site order}. A doctor's lectures are numbered 1, 2, 3... by the owner's file numbers in his folder, then in
    the order they were named (owner, 2026-11-10: Pain 1 showed after Pain 2 because titles and stale chapter lists set the
    order; one rule now for every doctor).
    A mini lecture or revision sits just after the last lesson it covers (+0.5)."""
    order, count, taken = {}, {}, set()
    # The owner's own numbers win ("4- Pain analgesia.mp3": lecture.json `order_key` [chapter, number] from the doctors/ folder);
    # lectures without one (auto lists) follow, in the order they were named.
    def sequence(m):
        k = m.get("order_key")
        return (0, k[0], k[1], m["id"]) if k else (1, 0, 0, m["id"])
    for m in sorted((m for m in metas if m.get("kind", "lecture") == "lecture"), key=sequence):
        count[m.get("doctor")] = count.get(m.get("doctor"), 0) + 1
        order[m["id"]] = count[m.get("doctor")]
    for m in sorted((m for m in metas if m.get("kind", "lecture") != "lecture"), key=lambda m: m["id"]):
        covered = [order[c] for c in m.get("covers") or [] if c in order]
        at = (max(covered) if covered else count.get(m.get("doctor"), 0) + 1) + 0.5
        while (m.get("doctor"), at) in taken:  # two revisions after the same lesson keep their naming order
            at = round(at + 0.01, 2)
        taken.add((m.get("doctor"), at))
        order[m["id"]] = at
    return order


def lesson_rows(module):
    """Every named lecture of a module as an importHubData `lessons` row (summaries and revisions after what they cover)."""
    import re as _re
    import lectures
    import doctors_folder
    out = []
    metas = lectures.all_lectures(module)
    by_id = {m["id"]: m for m in metas}
    order_of = lesson_order(metas)
    import auto_doctors
    chap_of, chap_order, by_doctor, seen = list_chapters(module)
    resolved = {}
    for m in sorted(metas, key=lambda m: bool(m.get("covers"))):  # what a mini lecture or revision covers is filed first
        base = by_id[m["covers"][0]] if m.get("covers") else m
        subject = (base.get("subject") or "").lower()
        order = order_of[m["id"]]
        title = (resolved.get(base["id"]) if base is not m else None) or chap_of.get(base["id"]) or chap_of.get(m["id"])
        if not title:  # not matched by post: the doctor's list item that shares the most words with its title
            all_words = lambda t: auto_doctors._words(t)
            mine = all_words(m["title"]) | all_words(base["title"])
            score = lambda t: (len({w for w in mine & all_words(t) if not w.isdigit()}), len({w for w in mine & all_words(t) if w.isdigit()}))
            scored = sorted(((score(t), t) for t, _k in by_doctor.get(m.get("doctor"), [])), reverse=True)
            if scored and scored[0][0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                title = scored[0][1]
        if not title:
            title = CHAPTERS.get(subject) or (base.get("chapter") or "").capitalize()
            print(f"  chapter: {m['id']} '{m['title']}' is in no Telegram list item, filed under '{title}' (the old chapter)")
        order_list = chap_order.setdefault(subject, [])
        titles = {_re_words(t): t for t in order_list}
        title = titles.get(_re_words(title), title)
        if title not in order_list:
            order_list.append(title)
        chap = {"title": title, "order": order_list.index(title) + 1}
        resolved[m["id"]] = title
        url = (m.get("source") or {}).get("youtube")
        doctor = m.get("doctor")
        doctor = doctors_folder.ALIASES.get((doctor or "").lower(), doctor)
        out.append({"key": f"lecture:{m['id']}", "subject": subject,
                    "chapter": ({"title": chap["title"], "order": chap["order"]} if chap else
                                {"title": CHAPTERS.get(subject) or (base.get("chapter") or "").capitalize(), "order": 1}),
                    "name": m["title"], "order": order,
                    "kind": "lesson" if m.get("kind", "lecture") == "lecture" else m["kind"],
                    "doctorId": doctor if doctor and doctor.startswith("dr-") else None,
                    "videoUrl": _re.sub(r"\?si=.*$", "", url) if url else None,
                    **({"oldData": True} if m.get("backup") else {}),  # the recording is the previous batch's: the site warns
                    "covers": [f"lecture:{c}" for c in m.get("covers") or []],
                    "ranges": lectures.site_ranges(m)})
    return sorted(out, key=lambda r: (r["kind"] != "lesson", r["key"]))


def cmd_site(args):
    """Writes lectures/<id>/site/ranges.jsonl (importHubData ranges) for each lecture, and prints the import command
    for those that know their site lesson. Nothing is written to the site here."""
    import lectures
    from flows.common import write_jsonl
    for module in sorted({m["module"] for m in lectures.all_lectures()}):
        rows = lesson_rows(module)
        f = ROOT / "modules" / module / "site" / "lessons.jsonl"
        f.parent.mkdir(exist_ok=True)
        write_jsonl(f, rows)
        print(f"{module}: {len(rows)} lessons -> {f}  (importHubData lessons --module {module} --file <that>)")
    ids = args.lectures or [m["id"] for m in lectures.all_lectures()]
    for lid in ids:
        meta = lectures.load(lid)
        d = lectures.folder(lid) / "site"
        d.mkdir(exist_ok=True)
        rows = [{"from": r["from"], "to": r["to"]} for r in meta.get("ranges") or []]
        write_jsonl(d / "ranges.jsonl", rows)
        cmd = (f"node ../node_modules/tsx/dist/cli.mjs src/scripts/importHubData.ts ranges --lesson {meta['lesson']} "
               f"--file \"{d / 'ranges.jsonl'}\"") if meta.get("lesson") else "no site lesson yet: the site has no lesson for it to load into"
        print(f"{lid} {meta.get('kind', 'lecture')} {meta['title']}: {len(rows)} range(s) {lectures.page_ranges(meta)}; {cmd}")


def cmd_highlight(args):
    """Lists a module's book lessons with their highlight state, or queues lessons for the highlights flow."""
    import db
    import highlights
    import queue_db
    q = queue_db.Queue()
    lessons = highlights.lessons(args.module)
    pick = [L for L in lessons if args.all or L["key"] in args.lessons or L["name"] in args.lessons]
    if not pick:
        for L in lessons:
            print(f"{L['key']} | {L['name']} | pdf {L['pages'][0]}-{L['pages'][1]} | "
                  f"{highlights.state(q, L['key']) or 'never run'} | {highlights.summary(args.module, L['key']) or ''}")
        q.close()
        return
    reader = db.Reader.live()
    for L in pick:
        print(L["name"], "->", highlights.queue(q, reader, L) or "already waiting")
    q.close()


def cmd_bank(_):
    import merge
    print(json.dumps(merge.build()))


def cmd_cover(args):
    import cover
    import db
    import queue_db
    done = cover.covered(args.file)
    if done and not args.again:
        sys.exit(f"already covered on {done['at']}: {done['matched']} of {done['questions']} ({done['percent']}%)")
    rows = cover.read_jsonl(args.file)
    reader = db.Reader.live()
    index = {**cover.bank_index(), **cover.site_index(reader, refresh=args.refresh)}
    matches = cover.script_match(rows, index)
    entry = cover.record(args.file, rows, matches)
    print(f"script: {entry['matched']} of {entry['questions']} matched ({entry['percent']}%)")
    left = [i for i, m in enumerate(matches) if m is None]
    if not left:
        return
    pool, df = cover.pool_of([{"id": r["id"], "text": r["t"]} for r in cover.read_jsonl(cover.SITE_KEYS)])
    text = {p["id"]: p["text"] for p in pool}
    items = []
    for i in left:
        ids = cover.candidates(rows[i], pool, df)
        if ids:
            items.append({"i": i, "question": rows[i]["question"], "options": rows[i].get("options") or [],
                          "candidates": [{"id": c, "text": text[c]} for c in ids]})
    jobs = [{"key": f"{entry['sha']}-{n:03d}", "payload": {"file": str(args.file), "sha": entry["sha"],
                                                         "items": items[n:n + POINTER_BATCH]}}
            for n in range(0, len(items), POINTER_BATCH)]
    q = queue_db.Queue()
    q.add_jobs("cover", jobs)
    q.close()
    print(f"fleet: {len(items)} questions with candidates in {len(jobs)} jobs; {len(left) - len(items)} have none (new)")


def cmd_labels(_):
    import labels
    labels.step(json.loads((ROOT / "config.json").read_text(encoding="utf-8")))


def cmd_voters(args):
    import voters
    print(json.dumps(voters.run(apply=args.apply), indent=1))


def cmd_page(_):
    import page
    page.serve()


def cmd_run(args):
    import dispatch
    import flows
    import queue_db
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    q = queue_db.Queue()
    d = dispatch.Dispatcher(q, slots=cfg["slots"], lanes=cfg["lanes"], flows=flows.REGISTRY, jobs_root=ROOT / "jobs")
    (ROOT / "jobs" / "stop.flag").unlink(missing_ok=True)
    if (ROOT / "handover").exists():
        import threading
        import db
        import intake

        def take_handovers():  # new hand-over files from the admin page become pointer jobs, once
            while not d.stopping():
                hq = queue_db.Queue()
                try:
                    for name, n in intake.intake(db.Reader.live(), hq, cfg["pointer_order"]).items():
                        print(f"hand-over {name}: {n} pointer jobs", flush=True)
                finally:
                    hq.close()
                d.stop.wait(60)
        threading.Thread(target=take_handovers, daemon=True).start()
    print(f"dispatcher: {sum(cfg['slots'].values())} slots, flows: {', '.join(flows.REGISTRY) or 'none yet'}"
          f"{' (until the queue is empty)' if args.once else ' (create jobs/stop.flag or Ctrl+C to stop)'}", flush=True)
    print(json.dumps(d.run(once=args.once)))
    q.close()


def main():
    ap = argparse.ArgumentParser(prog="dm.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="modules, lines and the polls job").set_defaults(fn=cmd_status)
    p = sub.add_parser("lines", help="split modules/<code>/handout.pdf into modules/<code>/lines.jsonl")
    p.add_argument("module")
    p.set_defaults(fn=cmd_lines)
    p = sub.add_parser("add", help="queue work: pointers <module> --file questions.jsonl | books <module> --book <id> "
                                   "--file book.pdf | reference <module> (its lecture list from the handout)")
    p.add_argument("flow", choices=["pointers", "books", "reference"])
    p.add_argument("module")
    p.add_argument("--file")
    p.add_argument("--book", help="book id (books)")
    p.add_argument("--pages", help="first-last book pages (books); default all")
    p.add_argument("--doctor", help="the site doctorId whose book it is (books); importSiteBook.ts --doctor")
    p.add_argument("--title", help="the book's title (books)")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("lecture", help="add a lecture: --file <audio> or --youtube <url>; queues transcription")
    p.add_argument("id")
    p.add_argument("--module", required=True)
    p.add_argument("--title")
    p.add_argument("--file")
    p.add_argument("--youtube")
    p.add_argument("--lesson", help="site lesson id")
    p.add_argument("--pages", help="first-last handout pdf pages of the lecture")
    p.add_argument("--no-transcribe", action="store_true", help="register only (an old recording kept as a taste)")
    p.add_argument("--doctor", help="the doctor who gives the lecture (highlights record it)")
    p.set_defaults(fn=cmd_lecture)
    p = sub.add_parser("site", help="write each lecture's site files (handout ranges) and print the import commands")
    p.add_argument("lectures", nargs="*", help="lecture ids; none: every lecture")
    p.set_defaults(fn=cmd_site)
    p = sub.add_parser("highlight", help="list a module's book lessons, or queue the highlights flow for some")
    p.add_argument("module")
    p.add_argument("lessons", nargs="*", help="lesson keys or names; none lists them")
    p.add_argument("--all", action="store_true", help="every lesson of the module")
    p.set_defaults(fn=cmd_highlight)
    sub.add_parser("page", help="the admin page on http://127.0.0.1:8770").set_defaults(fn=cmd_page)
    sub.add_parser("bank", help="merge polls, QuizBot and forms into bank/questions.jsonl").set_defaults(fn=cmd_bank)
    p = sub.add_parser("cover", help="is this question file already in our data? records it as covered")
    p.add_argument("file")
    p.add_argument("--again", action="store_true", help="check a file that was already covered")
    p.add_argument("--refresh", action="store_true", help="re-read the site's questions")
    p.set_defaults(fn=cmd_cover)
    p = sub.add_parser("importfile", help="bank/import_<msk|cns>.json for importSfQuestions.ts (dry run it first)")
    p.add_argument("module")
    p.set_defaults(fn=lambda a: __import__("importfile").run(a.module))
    p = sub.add_parser("labels", help="module, lecture and doctor labels for the bank: one step each run")
    p.set_defaults(fn=cmd_labels)
    p = sub.add_parser("voters", help="re-read vote counts (no voting) and update the site's stats")
    p.add_argument("--apply", action="store_true", help="write the site (dry run without it)")
    p.set_defaults(fn=cmd_voters)
    import sources
    sources.add_parser(sub)
    p = sub.add_parser("run", help="run queued jobs across the fleet accounts")
    p.add_argument("--once", action="store_true", help="stop when nothing is queued or running")
    p.set_defaults(fn=cmd_run)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

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


POINTER_BATCH, BOOK_BATCH = 25, 5


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
    if args.flow == "pointers":
        from flows.common import read_jsonl
        jobs = pointer_jobs(args.module, read_jsonl(args.file), cfg["pointer_order"])
    else:
        import shutil
        first, last = (int(x) for x in args.pages.split("-")) if args.pages else (None, None)
        keep = MODULES / args.module / "books" / f"{args.book}.pdf"
        keep.parent.mkdir(parents=True, exist_ok=True)
        if Path(args.file).resolve() != keep.resolve():
            shutil.copy2(args.file, keep)
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
                       url=args.youtube, lesson=args.lesson, pdf_pages=pages, transcribe=not args.no_transcribe)
    meta = lectures.load(args.id)
    print(f"{args.id}: {meta['duration_s']} s, transcript from {meta['source'].get('transcript', 'the fleet')}")
    if nxt:
        q = queue_db.Queue()
        q.add_jobs(nxt, [{"key": args.id, "payload": {"lecture": args.id}}])
        q.close()
        print(f"queued {nxt}")
    else:
        print("not queued: Transcribe is off for this lecture")


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


def cmd_run(args):
    import dispatch
    import flows
    import queue_db
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    q = queue_db.Queue()
    d = dispatch.Dispatcher(q, slots=cfg["slots"], lanes=cfg["lanes"], flows=flows.REGISTRY, jobs_root=ROOT / "jobs")
    (ROOT / "jobs" / "stop.flag").unlink(missing_ok=True)
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
    p = sub.add_parser("add", help="queue work: pointers <module> --file questions.jsonl | books <module> --book <id> --file book.pdf")
    p.add_argument("flow", choices=["pointers", "books"])
    p.add_argument("module")
    p.add_argument("--file", required=True)
    p.add_argument("--book", help="book id (books)")
    p.add_argument("--pages", help="first-last book pages (books); default all")
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
    p.set_defaults(fn=cmd_lecture)
    sub.add_parser("bank", help="merge polls, QuizBot and forms into bank/questions.jsonl").set_defaults(fn=cmd_bank)
    p = sub.add_parser("cover", help="is this question file already in our data? records it as covered")
    p.add_argument("file")
    p.add_argument("--again", action="store_true", help="check a file that was already covered")
    p.add_argument("--refresh", action="store_true", help="re-read the site's questions")
    p.set_defaults(fn=cmd_cover)
    import sources
    sources.add_parser(sub)
    p = sub.add_parser("run", help="run queued jobs across the fleet accounts")
    p.add_argument("--once", action="store_true", help="stop when nothing is queued or running")
    p.set_defaults(fn=cmd_run)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

"""py -m spine records plan | status | download | compress | upload | run  (see spine/records/__init__.py)."""
from spine.records import machine


def _recs(args):
    problems = []
    recs = machine.plan(args.year, args.doctor, problems)
    for p in problems:
        print("SKIPPED", p)
    if args.doctor and not recs:
        print(f"no records for '{args.doctor}'")
    return recs


def cmd_plan(args):
    recs = _recs(args)
    for line in machine.plan_lines(recs):
        print(line)
    if args.list:
        for r in recs:
            size = f"{r['size'] / 1e6:.1f}MB" if r["size"] else ""
            print(f"{r['id']:<16} {r['role']:<8} {r['source'] or 'NO MEDIA':<8} {size:>8}  {r['chapter'][:28]:<28} | {r['name'][:50]}")


def cmd_status(args):
    for line in machine.status_lines(_recs(args)):
        print(line)


def per_doctor(args, step):
    """A step runs doctor by doctor, so a report follows each doctor."""
    recs = _recs(args)
    for (doc, ref), rs in machine.by_doctor(recs).items():
        print(f"{doc} ({ref})")
        step(rs)


def cmd_download(args):
    budget = machine.Budget(args.max_mb)
    recs = _recs(args)
    for (doc, ref), rs in machine.by_doctor(recs).items():
        print(f"{doc} ({ref})")
        machine.download(rs, budget, args.youtube_audio)   # YouTube captions (a few KB) run even when the MB limit is spent
    if budget.spent:
        print(f"batch limit of {args.max_mb:.0f} MB reached")
    for line in machine.status_lines(recs):
        print(line)


def cmd_compress(args):
    per_doctor(args, machine.compress)


def cmd_upload(args):
    left = [args.limit]

    def step(rs):
        machine.upload(rs, left[0])
    per_doctor(args, step)


def cmd_transcribe(args):
    from spine.records import transcribe
    recs = _recs(args)
    n = transcribe.run(recs, args.limit, args.workers, via=args.via)
    print(f"{n} pieces heard")
    for line in machine.status_lines(recs):
        print(line)


def cmd_run(args):
    cmd_download(args)
    cmd_compress(args)
    cmd_upload(args)
    for line in machine.status_lines(_recs(args)):
        print(line)


def register(sub):
    p = sub.add_parser("records", help="year 1 records: plan, download, compress, upload")
    rs = p.add_subparsers(dest="records_cmd")
    for name, fn, hlp in (("plan", cmd_plan, "what would be fetched, MB per doctor"),
                          ("status", cmd_status, "state of every record and what is left"),
                          ("download", cmd_download, "Telegram media (resumable) and YouTube captions"),
                          ("compress", cmd_compress, "AAC mono 48 kbps of every downloaded Telegram record"),
                          ("upload", cmd_upload, "compressed recordings to the site's storage"),
                          ("transcribe", cmd_transcribe, "5-minute pieces heard by Gemini web (Flash-Lite)"),
                          ("run", cmd_run, "download, compress, upload")):
        q = rs.add_parser(name, help=hlp)
        q.add_argument("--year", type=int, default=1)
        q.add_argument("--doctor", help="part of a doctor's name, or a list (ZAG59_bio/29)")
        if name == "plan":
            q.add_argument("--list", action="store_true", help="one line per record")
        if name in ("download", "run"):
            q.add_argument("--max-mb", type=float, default=300, help="MB one run may fetch from Telegram (default 300)")
            q.add_argument("--youtube-audio", action="store_true", help="audio of YouTube posts with no captions")
        if name in ("upload", "run"):
            q.add_argument("--limit", type=int, help="at most N uploads per doctor")
        if name == "transcribe":
            q.add_argument("--limit", type=int, help="at most N pieces this run")
            q.add_argument("--workers", type=int, default=4, help="Gemini web workers (the fleet uses one per account)")
            q.add_argument("--via", choices=("fleet", "browser", "gemini"), default="fleet")
        q.set_defaults(run=fn)

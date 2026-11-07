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
    p = sub.add_parser("run", help="run queued jobs across the fleet accounts")
    p.add_argument("--once", action="store_true", help="stop when nothing is queued or running")
    p.set_defaults(fn=cmd_run)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

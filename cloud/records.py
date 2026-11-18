"""Records on the GitHub runner: Telegram download -> AAC mono 48 kbps -> the site's private storage.

    python -m cloud.records [--year 1|2] [--max-mb 3000] [--max-minutes 120] [--parallel 4]

Year 1: the records of the mother maps (spine.records.machine.plan). Year 2: the PC's to-do list (cloud/year2.py,
`ops/tumrah-data/inputs/year2_todo.json`), uploaded under the site's own lecture key (owner 2026-11-18: no heavy
transfers on the PC). Each year has its own records log (cloud/state.py).

1. pull the inputs (list messages, mother maps; year 2: the to-do list) and the records log from the bucket;
2. download the next Telegram records (first lessons of every subject first) up to --max-mb or --max-minutes,
   --parallel blocks of a file at once (one request after another is bound by the round trip, about 1.2 MB/s);
3. after each download, in a worker thread beside the next download: compress it, upload it (only the compressed
   file, never the original), make its hear copy and push the records log, so a run that is stopped keeps every
   record it finished;
4. push the records log back at the end too (merged; the PC's rows are kept).

Every line is printed with the time, unbuffered: the GitHub step log shows progress live.

YouTube captions stay on the PC (a few KB each; YouTube often refuses datacenter addresses). Transcription stays on
the PC's fleet: it fetches the compressed file (about 21 MB an hour) from the bucket when it needs it.
"""
import argparse
import functools
import sys
import time

from cloud import r2, state


HEAR_KBPS = 16          # what the fleet hears: Opus mono 16 kbps, about 7 MB an hour (the PC fetches this, not the 48k)


def hear_key(rec):
    return r2.OPS + f"hear/{rec['module']}/{rec['id']}.16k.ogg"


def hear_copies(recs, say=print):
    """For each uploaded record: a small Opus copy for the PC's transcription, in the bucket; `hear_key` in the log."""
    import lectures
    from spine.records import machine
    st = machine.states(recs[0]["module"]) if recs else {}
    for r in recs:
        row = st.get(r["id"]) or {}
        if not machine.reached(st, r["id"], "uploaded") or row.get("hear_key"):
            continue
        src, out = machine.compressed_path(r), machine.hear_path(r)
        try:
            lectures.compress(src, out, HEAR_KBPS)
            r2.put_bytes(hear_key(r), out.read_bytes(), "audio/ogg")
        except Exception as e:  # noqa: BLE001 - the PC can still make it from the 48k file
            say(f"  {r['id']}: hear copy FAILED {str(e)[-120:]}")
            continue
        machine.mark(r["module"], r["id"], hear_key=hear_key(r), hear_size=out.stat().st_size)
        say(f"  {r['id']}: hear copy {out.stat().st_size / 1e6:.1f} MB")


def say(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def todo(recs, st):
    """Telegram records this runner should fetch: not uploaded, and not downloaded by the PC (the PC compresses and
    uploads its own). A record the runner downloaded earlier but did not upload (a stopped run) is fetched again:
    the runner's disk is gone after every run."""
    from spine.records import machine
    out = []
    for r in recs:
        if r["source"] != "telegram" or machine.reached(st, r["id"], "uploaded"):
            continue
        row = st.get(r["id"]) or {}
        if machine.reached(st, r["id"], "downloaded") and row.get("where") != "runner":
            continue
        out.append(r)
    return out


def finish(rec, say=say):
    """One downloaded record: compress, upload, hear copy, records log pushed. The original is deleted once the
    record is uploaded (the runner's disk is small and gone after the run anyway)."""
    from spine.records import machine
    machine.compress([rec], say=say)
    machine.upload([rec], say=say, sender=r2.send)
    hear_copies([rec], say=say)
    if machine.reached(machine.states(rec["module"]), rec["id"], "uploaded"):
        src = machine.original(rec)
        if src:
            src.unlink(missing_ok=True)
    say(f"  {rec['id']}: records log pushed: {state.push_log(rec['module'])} rows")


def plan(year, no_inputs, print=say):              # noqa: A002
    """(records, report lines) of one year."""
    from spine.records import machine
    if year == 2:
        from cloud import year2
        rows = state.pull_year2_todo()
        print(f"year 2 to-do: {len(rows)} lectures")
        return year2.records(rows)
    if not no_inputs:
        print(f"inputs: {state.pull_inputs()} files")
    problems = []
    recs = machine.plan(1, problems=problems)
    for p in problems:
        print(f"SKIPPED {p}")
    return recs


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--year", type=int, choices=(1, 2), default=1)
    a.add_argument("--max-mb", type=float, default=3000)
    a.add_argument("--parallel", type=int, default=4, help="blocks of one file fetched at once (1: one after another)")
    a.add_argument("--max-minutes", type=float, default=120,
                   help="stop starting downloads after this many minutes (the job's timeout is 150)")
    a.add_argument("--no-inputs", action="store_true", help="use the inputs already on disk")
    args = a.parse_args(argv)
    print = say                                                    # noqa: A001 - every line timed and flushed
    import logging                                                 # Telethon's flood waits and reconnects, in the log
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(levelname)s %(message)s", stream=sys.stdout)
    from spine.records import machine
    module = state.YEAR2 if args.year == 2 else state.MODULE
    before, after = state.pull_log(module)
    print(f"records log {module}: {before} -> {after} rows")
    recs = plan(args.year, args.no_inputs, print)
    if not recs:
        print("no records")
        return 0 if args.year == 2 else 1
    st = machine.states(module)
    tg = todo(recs, st)
    print(f"to fetch: {len(tg)} Telegram records, {sum(r['size'] or 0 for r in tg) / 1e6:.0f} MB; this run: "
          f"{args.max_mb:.0f} MB, {args.max_minutes:.0f} min, {args.parallel} blocks at once")
    got = []
    try:
        if tg:
            import asyncio
            machine.lock()
            try:
                budget = machine.Budget(args.max_mb, args.max_minutes * 60)
                got = asyncio.run(machine._download_telegram(machine.priority(tg), budget, print,
                                                             on_done=functools.partial(finish, say=print),
                                                             parallel=args.parallel))
            finally:
                machine.unlock()
        print(f"downloaded this run: {len(got)}")
    finally:
        print(f"records log pushed: {state.push_log(module)} rows")
    st = machine.states(module)
    left = [r for r in recs if r["source"] == "telegram" and not machine.reached(st, r["id"], "uploaded")]
    print(f"left: {len(left)} Telegram records not uploaded yet")
    return 0


if __name__ == "__main__":
    sys.exit(main())

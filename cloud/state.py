"""State shared by the PC and the GitHub runner through the private bucket (prefix `ops/tumrah-data/`).

    py -m cloud.state push     PC: the inputs the runner needs (year 1 list messages, mother maps; year 2 to-do list)
                               + both records logs
    py -m cloud.state pull     PC or runner: the records logs merged with the bucket's copy (and, on the runner, inputs)

A records log (`modules/<module>/graph/records.jsonl`: year1-musculoskeletal, year2-cns) is append-only and its rows
carry `at`, so a merge is the union of both sides in time order: the PC and the runner never overwrite each other's rows.

Year 2 (owner, 2026-11-18: no heavy transfers on the PC): the PC makes the lectures from the Telegram lists without
downloading; `year2_todo()` lists the ones whose recording is not on the site yet, the runner downloads, compresses and
uploads them under the site's own key, and `cloud.year2.pull` writes the result back into each lecture (no audio moves).
"""
import io
import json
import sys
import tarfile

from cloud import r2
from spine import LOG_LOCK, ROOT

MODULE = "year1-musculoskeletal"
YEAR2 = "year2-cns"
INPUTS_KEY = r2.OPS + "inputs/year1.tar.gz"
YEAR2_TODO_KEY = r2.OPS + "inputs/year2_todo.json"


def log_path(module=MODULE):
    return ROOT / "modules" / module / "graph" / "records.jsonl"


def log_key(module=MODULE):
    return r2.OPS + f"records/{module}.jsonl"


LOG, LOG_KEY = log_path(), log_key()                 # year 1 (kept for callers that name them)


def input_files():
    """The small files `machine.plan(1)` reads that git does not hold."""
    out = []
    for pat in ("sources/lists/ZAG59_*/*.json", "sources/mother/ZAG59_*/*/*.json", "sources/mother/fixes.json"):
        out += sorted(ROOT.glob(pat))
    return out


def _rows(text):
    return [json.loads(x) for x in (text or "").splitlines() if x.strip()]


def merge(a, b):
    """Union of two row lists (same row once), in time order; ties keep a's order first."""
    seen, out = set(), []
    for r in a + b:
        k = json.dumps(r, sort_keys=True, ensure_ascii=False)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return sorted(out, key=lambda r: r.get("at") or "")


def _text(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def pull_log(module=MODULE):
    """The bucket's log merged into the local one. Returns (rows before, rows after)."""
    path = log_path(module)
    remote = _rows((r2.get_bytes(log_key(module)) or b"").decode("utf-8"))      # network first, outside the lock
    with LOG_LOCK:                                                              # no row appended meanwhile is lost
        local = _rows(path.read_text(encoding="utf-8")) if path.exists() else []
        rows = merge(local, remote)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_text(rows), encoding="utf-8")
    return len(local), len(rows)


def push_log(module=MODULE):
    """The local log merged into the bucket's copy (and back, so both sides end equal). Returns rows."""
    path = log_path(module)
    remote = _rows((r2.get_bytes(log_key(module)) or b"").decode("utf-8"))
    with LOG_LOCK:
        local = _rows(path.read_text(encoding="utf-8")) if path.exists() else []
        rows = merge(local, remote)
        text = _text(rows)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    r2.put_bytes(log_key(module), text.encode("utf-8"), "application/x-ndjson")
    return len(rows)


def push_year2_todo(rows):
    r2.put_bytes(YEAR2_TODO_KEY, json.dumps(rows, ensure_ascii=False).encode("utf-8"), "application/json")
    return len(rows)


def pull_year2_todo():
    data = r2.get_bytes(YEAR2_TODO_KEY)
    return json.loads(data.decode("utf-8")) if data else []


def push_inputs():
    buf = io.BytesIO()
    files = input_files()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in files:
            tar.add(f, arcname=f.relative_to(ROOT).as_posix())
    r2.put_bytes(INPUTS_KEY, buf.getvalue(), "application/gzip")
    return len(files)


def pull_inputs():
    data = r2.get_bytes(INPUTS_KEY)
    if not data:
        raise RuntimeError("no inputs in the bucket yet: run `py -m cloud.state push` on the PC once")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        names = []
        for m in tar.getmembers():
            if not m.isfile() or m.name.startswith(("/", "..")) or ".." in m.name.split("/"):
                continue                     # only plain files inside the repo
            target = ROOT / m.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(m).read())
            names.append(m.name)
    return len(names)


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "push":
        from cloud import year2
        print(f"inputs: {push_inputs()} files; year 2 to-do: {push_year2_todo(year2.todo())} lectures; "
              f"records logs: {push_log()} + {push_log(YEAR2)} rows")
    elif cmd == "pull":
        if "--inputs" in argv:
            print(f"inputs: {pull_inputs()} files")
        for module in (MODULE, YEAR2):
            before, after = pull_log(module)
            print(f"records log {module}: {before} -> {after} rows")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

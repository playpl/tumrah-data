"""State shared by the PC and the GitHub runner through the private bucket (prefix `ops/tumrah-data/`).

    py -m cloud.state push     PC: the inputs the runner needs (year 1 list messages, mother maps) + the records log
    py -m cloud.state pull     PC or runner: the records log merged with the bucket's copy (and, on the runner, inputs)

The records log (`modules/year1-musculoskeletal/graph/records.jsonl`) is append-only and its rows carry `at`, so a merge
is the union of both sides in time order: the PC and the runner never overwrite each other's rows.
"""
import io
import json
import sys
import tarfile

from cloud import r2
from spine import ROOT

MODULE = "year1-musculoskeletal"
LOG = ROOT / "modules" / MODULE / "graph" / "records.jsonl"
LOG_KEY = r2.OPS + f"records/{MODULE}.jsonl"
INPUTS_KEY = r2.OPS + "inputs/year1.tar.gz"


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


def pull_log():
    """The bucket's log merged into the local one. Returns (rows before, rows after)."""
    local = _rows(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    remote = _rows((r2.get_bytes(LOG_KEY) or b"").decode("utf-8"))
    rows = merge(local, remote)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(_text(rows), encoding="utf-8")
    return len(local), len(rows)


def push_log():
    """The local log merged into the bucket's copy (and back, so both sides end equal). Returns rows."""
    local = _rows(LOG.read_text(encoding="utf-8")) if LOG.exists() else []
    remote = _rows((r2.get_bytes(LOG_KEY) or b"").decode("utf-8"))
    rows = merge(local, remote)
    r2.put_bytes(LOG_KEY, _text(rows).encode("utf-8"), "application/x-ndjson")
    LOG.write_text(_text(rows), encoding="utf-8")
    return len(rows)


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
        print(f"inputs: {push_inputs()} files; records log: {push_log()} rows")
    elif cmd == "pull":
        if "--inputs" in argv:
            print(f"inputs: {pull_inputs()} files")
        before, after = pull_log()
        print(f"records log: {before} -> {after} rows")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

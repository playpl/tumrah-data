"""spine: the rebuilt data pipeline. The college handout is the spine; everything links to its sentences.

Run as `py -m spine <command>`. Plan and design: docs/spine/PLAN.md, docs/spine/DESIGN_agent.md.

Record files (the truth; `spine/graph.db` is only an index rebuilt from them by `py -m spine store rebuild`):

    modules/<m>/graph/graph.json                   the tree: university, year, subjects, chapters, lessons
    modules/<m>/graph/chapters.json                handout chapters (built once, checked by the owner)
    modules/<m>/graph/sentences.jsonl              handout sentences, in handout order
    modules/<m>/graph/books/<book>.sentences.jsonl book sentences, in book order
    modules/<m>/graph/books/<book>.pages.jsonl     book page -> handout lesson (scope by code)
    modules/<m>/graph/edges/<book>.jsonl           accepted links, one row per (src, dst)
    modules/<m>/graph/votes/<book>.<reader>.jsonl  one row per (src, reader)
    modules/<m>/graph/records.jsonl                record upload states (append log, last row per post wins)

Row shapes shared by every subpackage:

    sentence  {"id", "i", "kind": "heading|fact|table_row|figure", "marker", "text", "rows": [line ids],
               "lesson", "section", "ctx": [heading path, list lead-in], "splitter": 1}
    edge      {"src": book sentence id, "dst": handout sentence id, "rel": "S|R|P", "grp": n, "conf": 0.0-1.0,
               "by": "spine-code:A1|spine-fleet|spine-claude|old", "state": "accepted|flagged", "at": iso time}
    vote      {"src", "reader": "code|fleetA|fleetB|old|web|claude",
               "answer": {"dst": [handout sentence ids], "rel": "S|R|P"} or "0" (not in list) or "X" (not content),
               "at": iso time}

Old scripts keep "Update data" working while a phase is in shadow mode: config.json "spine": {"p1", "p2", "mother"}.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPLITTER = 1   # bump when a sentence join rule changes; every sentence row carries it


def module_dir(module):
    return ROOT / "modules" / module


def graph_dir(module):
    return module_dir(module) / "graph"


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    """Whole file at once, through a temp file, so a stopped run never leaves half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def append_jsonl(path, row):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    tmp.replace(path)


def config():
    """config.json "spine" block with the defaults filled in. Every phase starts in shadow mode."""
    cfg = (read_json(ROOT / "config.json", {}) or {}).get("spine", {})
    return {"p1": "shadow", "p2": "shadow", "mother": "shadow", "claude_budget_tokens": 300000, "records_batch_mb": 400,
            "auto_publish_records": False, **cfg}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

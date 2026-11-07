"""Loads the job's handout lines (inputs/lines.jsonl) and reference. Standard library only."""
import json
from pathlib import Path

JOB = Path(__file__).resolve().parent.parent


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def lines():
    return read_jsonl(JOB / "inputs" / "lines.jsonl")


def reference():
    p = JOB / "inputs" / "reference.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def pages():
    """pdf page -> (printed page, [rendered lines]); a figure shows as [FIGURE: its nearby text]."""
    out = {}
    for ln in lines():
        printed, rows = out.setdefault(ln["page"], (ln.get("printed"), []))
        if ln.get("figure") is None:
            rows.append(ln["text"])
        else:
            rows.append(f"[FIGURE: {ln['figure'] or 'no nearby text'}]")
    return out

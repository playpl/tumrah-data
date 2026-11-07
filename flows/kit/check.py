"""Checks this job's output with the same code the dispatcher runs. Prints PASS or every error.

    python tools/check.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks  # noqa: E402
from handout import JOB, lines, read_jsonl, reference  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
job = json.loads((JOB / "job.json").read_text(encoding="utf-8"))
out = JOB / job["output"]
if not out.exists():
    sys.exit(f"FAIL: {job['output']} does not exist")
try:
    rows = read_jsonl(out)
except ValueError as e:
    sys.exit(f"FAIL: {job['output']} has a line that is not JSON ({e})")
errors = getattr(checks, job["checker"])(rows, read_jsonl(JOB / job["batch"]), lines(), reference())
for e in errors[:40]:
    print(e)
print(f"FAIL: {len(errors)} errors" if errors else f"PASS: {len(rows)} rows")
sys.exit(1 if errors else 0)

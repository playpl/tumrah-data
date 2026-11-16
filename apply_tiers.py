"""Applies every lecture's Required and Doctor lists to the site (importHubData required|doctor --apply), from the tier
files `tiers.py` wrote. Production: the importer writes an undo file per call.   py apply_tiers.py [--dry]"""
import json
import os
import subprocess
import sys
from pathlib import Path

import lectures

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "modules" / "year2-cns" / "site"
BACKEND = Path(r"C:\Users\Ahmed\Desktop\tumrah\backend")
DNS = os.environ.get("DNS_PRELOAD", "")


def main(dry):
    env = {**os.environ, **({"NODE_OPTIONS": f"--require {DNS}"} if DNS else {})}
    for m in sorted(lectures.all_lectures("year2-cns"), key=lambda m: m["id"]):
        if not m.get("lesson") or m.get("hold"):  # held duplicates are drafts on the site
            continue
        for kind in ("required", "doctor"):
            f = SITE / f"tier_{kind}_{m['id']}.jsonl"
            if not f.exists() or not f.read_text(encoding="utf-8").strip():
                continue
            cmd = ["node", "../node_modules/tsx/dist/cli.mjs", "src/scripts/importHubData.ts", kind, "--lesson", m["lesson"], "--file", str(f)]
            res = subprocess.run(cmd + ([] if dry else ["--apply"]), cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", env=env)
            line = (res.stdout.strip().splitlines() or [res.stderr.strip()[-200:]])[-1]
            try:
                j = json.loads(line)
                line = f"rows {j['rows']} created {j['created']} changed {j['changed']} unchanged {j['unchanged']} skipped {j['skipped']}"
            except Exception:  # noqa: BLE001
                pass
            print(f"{m['id']} {kind}: {line}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main("--dry" in sys.argv)

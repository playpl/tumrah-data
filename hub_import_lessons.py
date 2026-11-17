"""Runs the tumrah repo's `importHubData.ts lessons` for year2-cns with the lessons file this repo wrote (owner, 2026-11-12).

    py hub_import_lessons.py           dry run: prints counts, writes nothing
    py hub_import_lessons.py --apply   writes an undo file under the importer's backups folder first, then writes
    py hub_import_lessons.py --module year1-musculoskeletal [--apply]   the year 1 records (spine/records/flow.py)

One fixed command on purpose: the Claude Code permission rule for it (`.claude/settings.local.json`) allows only this file,
so no other importer or flag runs without the owner's own approval. Only the `lessons` importer, only the modules in
MODULES and each one's own modules/<m>/site/lessons.jsonl (year 1 added by the owner's order of 2026-11-17).
The backend's .env may point at production: --apply is the only call that writes.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = Path(r"C:\Users\Ahmed\Desktop\tumrah\backend")
MODULE = "year2-cns"
MODULES = ("year2-cns", "year1-musculoskeletal")


def main(argv):
    apply = "--apply" in argv
    argv = [a for a in argv if a != "--apply"]
    module = MODULE
    if argv[:1] == ["--module"] and len(argv) == 2 and argv[1] in MODULES:
        module, argv = argv[1], []
    if argv:
        sys.exit(f"only --apply and --module <{'|'.join(MODULES)}> are accepted")
    FILE = ROOT / "modules" / module / "site" / "lessons.jsonl"
    if not FILE.exists():
        sys.exit(f"{FILE} is missing: run `py site_lessons.py write`")
    pre = Path(tempfile.gettempdir()) / "tumrah_dns_preload.cjs"  # Atlas SRV lookups fail on this PC's resolver
    pre.write_text('require("dns").setServers(["1.1.1.1"]);\n', encoding="utf-8")
    env = dict(os.environ, NODE_OPTIONS=f'--require "{pre.as_posix()}"')  # NODE_OPTIONS eats backslashes
    cmd = ["node", "../node_modules/tsx/dist/cli.mjs", "src/scripts/importHubData.ts", "lessons",
           "--module", module, "--file", str(FILE)] + (["--apply"] if apply else [])
    print("APPLY (writes)" if apply else "DRY RUN (writes nothing)", flush=True)
    sys.exit(subprocess.run(cmd, cwd=BACKEND, env=env).returncode)


if __name__ == "__main__":
    main(sys.argv[1:])

"""The whole site import of year2-cns in one command (owner, 2026-11-16: "always push"; 2026-11-17: one command).

    py site_import.py           the real import: writes the production website
    py site_import.py --dry     only the lesson dry run: what would be created or changed; writes nothing

Steps, in order (each prints one line; the first failure stops the run):
  1 site files    site_lessons.py write, fast_lessons.py build
  2 lessons       hub_import_lessons.py --apply, then site_lessons.py ids (lesson ids back into lecture.json)
  3 questions     importSfQuestions (questions.json)
  4 pointers      fast_lessons.py pointers, importHubData pointers
  5 tiers         tiers.py, apply_tiers.py
  6 extras        recomputeLessonExtras for every published CNS lesson

Run `py update_data.py` first: it imports the new lectures and starts the upload of the new recordings
(compressed to AAC mono 48 kbps before upload). Lessons whose doctor has no site id are left out.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = Path(r"C:\Users\Ahmed\Desktop\tumrah\backend")
MODULE, MODULE_NAME = "year2-cns", "Central Nervous System"
SITE = ROOT / "modules" / MODULE / "site"
TSX = ["node", "../node_modules/tsx/dist/cli.mjs"]


def node_env():
    pre = Path(tempfile.gettempdir()) / "tumrah_dns_preload.cjs"  # Atlas SRV lookups fail on this PC's resolver
    pre.write_text('require("dns").setServers(["1.1.1.1"]);\n', encoding="utf-8")
    return dict(os.environ, NODE_OPTIONS=f'--require "{pre.as_posix()}"', PYTHONIOENCODING="utf-8")


def run(cmd, cwd=ROOT, env=None, keep=None):
    """Runs one command; returns its output. `keep` = substrings of the lines worth printing (None: the last line)."""
    res = subprocess.run(cmd, cwd=cwd, env=env or dict(os.environ, PYTHONIOENCODING="utf-8"), capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    out = (res.stdout or "") + (res.stderr or "")
    lines = [l for l in out.splitlines() if l.strip()]
    shown = [l for l in lines if any(k in l for k in keep)] if keep else lines[-1:]
    for l in shown:
        print("   " + l.strip()[:300], flush=True)
    if res.returncode:
        print(f"   FAILED (exit {res.returncode}): {' '.join(str(c) for c in cmd)[:200]}")
        for l in lines[-6:]:
            print("   | " + l[:300])
        sys.exit(res.returncode)
    return out


def main(argv):
    dry = "--dry" in argv
    env = node_env()
    print("== 1 site files", flush=True)
    run(["py", "site_lessons.py", "write"], keep=["lessons (", "NOT IN mother_lists", "NO SITE DOCTOR"])
    if dry:
        print("== 2 lessons (dry run, nothing is written)", flush=True)
        run(["py", "hub_import_lessons.py"], env=env)
        return
    run(["py", "fast_lessons.py", "build"], keep=["in_two_lectures", "not_in_bank_no_key"])
    print("== 2 lessons", flush=True)
    out = run(["py", "hub_import_lessons.py", "--apply"], env=env)
    last = Path(tempfile.gettempdir()) / "tumrah_lessons_last.txt"
    last.write_text([l for l in out.splitlines() if l.strip()][-1], encoding="utf-8")
    run(["py", "site_lessons.py", "ids", str(last)])
    print("== 3 questions", flush=True)
    run(TSX + ["src/scripts/importSfQuestions.ts", "--file", str(SITE / "questions.json"), "--backups",
               str(ROOT / "modules" / MODULE / "backups"), "--apply"], cwd=BACKEND, env=env,
        keep=["question_writes", "inserted", "updated", "hidden", "key_holds"])
    print("== 4 pointers", flush=True)
    run(["py", "fast_lessons.py", "pointers"])
    run(TSX + ["src/scripts/importHubData.ts", "pointers", "--module", MODULE, "--file", str(SITE / "pointers_fast.jsonl"),
               "--source", "script-index-" + time.strftime("%Y-%m-%d"), "--apply"], cwd=BACKEND, env=env)
    print("== 5 tiers", flush=True)
    run(["py", "tiers.py"], keep=["\x00"])
    out = run(["py", "apply_tiers.py"], keep=["\x00"])
    calls = [l for l in out.splitlines() if l.strip()]
    print(f"   {len(calls)} calls, problems: {sum(1 for l in calls if chr(39) + 'question_not_found' + chr(39) + ': 0' not in l)}")
    print("== 6 extras", flush=True)
    sys.path.insert(0, str(ROOT))
    import db
    ids = [str(l["_id"]) for l in db.Reader.live()._db.lessons.find({"moduleName": MODULE_NAME, "status": "published"}, {"_id": 1})]
    out = run(TSX + ["src/scripts/recomputeLessonExtras.ts"] + ids, cwd=BACKEND, env=env, keep=["\x00"])
    print(f"   {len([l for l in out.splitlines() if l.strip()])} lessons recomputed (of {len(ids)} published)")
    print("== done")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])

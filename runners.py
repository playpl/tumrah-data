"""Which AI can work now (owner, 2026-11-10: "we use the fleet, and for now it's down, so we use the web").

Two runners do the same jobs with the same checkers: the Antigravity fleet (folder jobs with tools, `dm.py run`) and
Gemini web (one prompt per job, `gemini_run.py`). Every ledger row names its runner, so when both are up one audits
the other. This file only says who is up and starts the web steps; it never chooses a link.

    py runners.py            health of both runners
    py runners.py ai         run the waiting AI steps on whoever is up (bounds, then pointers)
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GWEB = [r"C:\Users\Ahmed\gemini-web\.venv\Scripts\python.exe", r"C:\Users\Ahmed\gemini-web\gweb.py"]
HEAVY_CAP = 80           # same cap as gemini_run.py: a thinking call only goes to an account under this 5-hour usage
_CACHE = {"at": 0, "web": None}


def fleet():
    """ponytail: the fleet is up when config.json says so; a live ping of the agy CLI is the upgrade."""
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("fleet") or {}
    return {"up": not cfg.get("down"), "note": cfg.get("note") or ""}


def web(max_age=300):
    """Gemini web accounts from `gweb status` (cached 5 minutes: the call takes a few seconds)."""
    if _CACHE["web"] is not None and time.time() - _CACHE["at"] < max_age:
        return _CACHE["web"]
    try:
        run = subprocess.run([*GWEB, "status", "--json"], capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=120)
        rows = json.loads(run.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        rows, err = [], f"gweb status failed: {type(e).__name__}"
    else:
        err = None
    dead = [r["slot"] for r in rows if r.get("cause") == "cookie_dead"]
    # gweb keeps `usable` true on a dead login (state READY, cause cookie_dead: seen 2026-11-11), so the cause decides
    usable = [r["slot"] for r in rows if r.get("usable") and r["slot"] not in dead]
    note = err or ("the Google login is dead on every account: export the cookies again" if rows and len(dead) == len(rows)
                   else f"{len(usable)} of {len(rows)} accounts usable")
    out = {"up": bool(usable), "usable": usable, "note": note,
           "thinking": [r["slot"] for r in rows if r["slot"] in usable and (r.get("used_5h") or 0) < HEAVY_CAP]}
    _CACHE.update(at=time.time(), web=out)
    return out


def health():
    f, w = fleet(), web()
    return {"fleet": f, "web": w, "any": f["up"] or w["up"],
            "working": "fleet" if f["up"] else "web" if w["up"] else None}


def auditor(producer):
    """The runner that should re-read a sample of `producer`'s rows: the other one when it is up, else None."""
    h = health()
    other = "web" if producer == "fleet" else "fleet"
    return other if h[other]["up"] else None


def run_ai(steps=("bounds", "pointers")):
    """The waiting AI steps, on the web runner (the fleet takes queue jobs through `dm.py run`, started from the page)."""
    h = health()
    if not h["web"]["up"]:
        return [f"web runner is down: {h['web']['note']}"]
    out = []
    for step in steps:
        run = subprocess.run(["py", str(ROOT / "gemini_run.py"), step], capture_output=True, text=True, cwd=ROOT,
                             encoding="utf-8", errors="replace")
        out.append(f"{step}: " + ((run.stdout.strip().splitlines() or [run.stderr.strip()[-200:]])[-1]))
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run_ai() if sys.argv[1:] == ["ai"] else health(), indent=1))

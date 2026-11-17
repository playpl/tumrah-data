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
_CACHE = {"at": 0, "web": None}


def fleet():
    """ponytail: the fleet is up when config.json says so; a live ping of the agy CLI is the upgrade."""
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8")).get("fleet") or {}
    return {"up": not cfg.get("down"), "note": cfg.get("note") or ""}


def web(max_age=600):
    """Gemini web = the four signed-in Chrome profiles (gemini_browser.status, cached: a live check opens each)."""
    if _CACHE["web"] is not None and time.time() - _CACHE["at"] < max_age:
        return _CACHE["web"]
    try:
        import gemini_browser
        rows, err = gemini_browser.status(max_age), None
    except Exception as e:  # noqa: BLE001 - no Chrome, no Playwright, no tumrah-book driver: the web runner is down
        rows, err = {}, f"browser status failed: {type(e).__name__}"
    usable = [k for k, v in rows.items() if v == "signed in"]
    note = err or ("no Chrome profile is signed in: the owner runs `py -m flow.images.browser login <n>` in tumrah-book"
                   if rows and not usable else f"{len(usable)} of {len(rows)} accounts usable")
    out = {"up": bool(usable), "usable": usable, "note": note, "thinking": usable}
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

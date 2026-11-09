"""Fleet health check (owner, 2026-11-09: watch the agents every half hour). Counts only.

For every running job: minutes running, minutes since it last wrote a file in its folder, and whether its worker log
shows a picture or PDF being opened (the worst slowdown) or a denied command loop. Plus queue totals, account
cool-downs and the dispatcher process.

    py fleet_watch.py
"""
import json
import re
import sqlite3
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PIC = re.compile(r'"(?:read_file|view_file|view_image)"[^\n]{0,300}?\.(?:png|jpe?g|gif|webp|tiff?|pdf)\b|get_pixmap|pdftoppm', re.I)


def main():
    now = time.time()
    db = sqlite3.connect(ROOT / "queue.db")
    db.row_factory = sqlite3.Row
    rows = db.execute("SELECT id, flow, key, account, started, tries FROM jobs WHERE status='running'").fetchall()
    out = []
    for r in rows:
        d = ROOT / "jobs" / r["flow"] / r["key"]
        files = [p for p in d.rglob("*") if p.is_file() and "tools" not in p.parts and "inputs" not in p.parts]
        last = max((p.stat().st_mtime for p in files), default=r["started"] or now)
        logs = list(d.glob(".agy-*.ndjson"))
        text = "".join(p.read_text(encoding="utf-8", errors="ignore")[-400000:] for p in logs)
        out.append({"job": r["id"], "acct": r["account"], "min": round((now - (r["started"] or now)) / 60),
                    "idle_min": round((now - last) / 60), "tries": r["tries"], "pictures": len(PIC.findall(text)),
                    "denied": text.count("permission check failed")})
    totals = {f"{x['flow']}:{x['status']}": x["n"] for x in db.execute(
        "SELECT flow, status, COUNT(*) n FROM jobs GROUP BY flow, status")}
    state = json.loads(Path(r"C:\Users\Ahmed\agy-fleet\state.json").read_text(encoding="utf-8")).get("cooldown", {})
    cooling = {a: t for a, t in state.items() if t > time.strftime("%Y-%m-%dT%H:%M:%S")}
    alive = "dm.py run" in subprocess.run(["powershell", "-NoProfile", "-Command",
                                           "(Get-CimInstance Win32_Process -Filter \"name='python.exe'\").CommandLine"],
                                          capture_output=True, text=True).stdout
    print(json.dumps({"at": time.strftime("%H:%M"), "dispatcher": alive, "cooling": cooling, "running": out,
                      "queue": totals}, indent=1))


if __name__ == "__main__":
    main()

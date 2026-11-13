"""Watches the owner's doctors/ folder for new or changed files (owner, 2026-11-09: check every hour, alert me, and
check whenever Claude starts working).

    py doctors_watch.py check     compare with the last look; new or changed files -> Windows notification and
                                  doctors_pending.json (Windows Task Scheduler runs this every hour)
    py doctors_watch.py hook      the same check, then print what is pending (Claude Code's SessionStart hook)
    py doctors_watch.py pending   print what is pending
    py doctors_watch.py done      clear the pending list (after `py doctors_folder.py import` handled it)

Only file names, sizes and times are read. The first check sets the baseline and reports nothing.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCTORS = ROOT / "doctors"
SEEN = ROOT / "doctors_seen.json"
PENDING = ROOT / "doctors_pending.json"
SKIP_SUFFIX = {".tmp", ".crdownload", ".part", ".partial"}
SKIP_NAME = {"desktop.ini", "thumbs.db"}


def snapshot(root):
    out = {}
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix.lower() in SKIP_SUFFIX or f.name.lower() in SKIP_NAME or f.name.startswith("~$"):
            continue
        st = f.stat()
        out[f.relative_to(root).as_posix()] = [st.st_size, int(st.st_mtime)]
    return out


def changes(root=DOCTORS, state=SEEN, save=True):
    """{new, changed, gone}: files since the last look (relative paths). The first look only sets the baseline."""
    now = snapshot(root) if root.exists() else {}
    if not state.exists():
        old = now
    else:
        old = json.loads(state.read_text(encoding="utf-8"))
    out = {"new": sorted(k for k in now if k not in old),
           "changed": sorted(k for k in now if k in old and now[k] != old[k]),
           "gone": sorted(k for k in old if k not in now)}
    if save:
        state.write_text(json.dumps(now, indent=0), encoding="utf-8")
    return out


def add_pending(found):
    pend = json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else []
    known = {p["file"] for p in pend}
    stamp = time.strftime("%Y-%m-%d %H:%M")
    for kind in ("new", "changed", "gone"):
        for f in found[kind]:
            if f not in known:
                pend.append({"file": f, "what": kind, "seen": stamp})
                known.add(f)
    PENDING.write_text(json.dumps(pend, indent=1, ensure_ascii=False), encoding="utf-8")
    return pend


def notify(title, text):
    """A Windows toast (shown under PowerShell's name); a message box if toasts fail."""
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "''")
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$x.LoadXml('<toast><visual><binding template=\"ToastGeneric\"><text>{esc(title)}</text><text>{esc(text)}</text>"
        "</binding></visual></toast>');"
        "$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show("
        "[Windows.UI.Notifications.ToastNotification]::new($x))")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                         creationflags=flags)
    if res.returncode != 0:
        subprocess.run(["msg", "*", f"{title}: {text}"], creationflags=flags)


def summary(items):
    by = {}
    for p in items:
        parts = p["file"].split("/")
        who = "/".join(parts[:3]) if len(parts) > 3 else "/".join(parts[:-1])
        by.setdefault(who, []).append(p)
    return "; ".join(f"{who}: {len(v)} file(s)" for who, v in by.items())


def check(quiet=False):
    found = changes()
    if not any(found.values()):
        return []
    fresh = found["new"] + found["changed"] + found["gone"]
    add_pending(found)
    if not quiet:
        notify("Tumrah: doctors folder updated", summary([{"file": f} for f in fresh]))
    return fresh


def main(cmd):
    if sys.stdout:  # pythonw (Task Scheduler) has no console
        sys.stdout.reconfigure(encoding="utf-8")
    if cmd == "check":
        check()
    elif cmd == "hook":
        check(quiet=True)
        pend = json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else []
        if pend:
            print(f"doctors/ folder: {len(pend)} file(s) added or changed since the last import, not handled yet "
                  f"({summary(pend)}). Tell the owner, then run `py update_data.py` (the owner's \"Update data\": folder import, "
                  f"auto doctors' Telegram lists, books, quizzes; it clears this list when done). "
                  f"`py doctors_watch.py pending` lists the files.")
    elif cmd == "pending":
        for p in json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else []:
            print(f"{p['seen']}  {p['what']:<7}  {p['file']}")
    elif cmd == "done":
        PENDING.unlink(missing_ok=True)
        print("pending list cleared")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")

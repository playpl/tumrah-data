"""Pause or resume every fleet process at once (owner 2026-11-14: "pause them, they're taking my internet").

Freezes the dispatchers (`dm.py run`, `extra_dispatcher.py`) and every process under them (fleet.py, agy workers) with
NtSuspendProcess, so nothing uses the network and no job is lost. Resume picks up where they stopped; a worker whose
connection dropped while frozen fails once and its job is retried.

    py fleet_pause.py pause | resume | status
"""
import ctypes
import json
import subprocess
import sys

MARKS = ("dm.py run", "dm.py\" run", "extra_dispatcher.py")


def processes():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | "
                          "ConvertTo-Json -Compress"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(out.stdout or "[]")


def fleet_tree():
    procs = processes()
    kids = {}
    for p in procs:
        kids.setdefault(p["ParentProcessId"], []).append(p)
    roots = [p for p in procs if any(m in (p.get("CommandLine") or "") for m in MARKS)]
    seen, todo = {}, list(roots)
    while todo:
        p = todo.pop()
        if p["ProcessId"] in seen:
            continue
        seen[p["ProcessId"]] = p
        todo += kids.get(p["ProcessId"], [])
    return list(seen.values())


def act(fn_name):
    ntdll = ctypes.WinDLL("ntdll")
    k32 = ctypes.WinDLL("kernel32")
    fn = getattr(ntdll, fn_name)
    done = 0
    for p in fleet_tree():
        h = k32.OpenProcess(0x0800, False, p["ProcessId"])  # PROCESS_SUSPEND_RESUME
        if h:
            if fn(h) == 0:
                done += 1
            k32.CloseHandle(h)
    return done


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "pause":
        print("paused", act("NtSuspendProcess"), "processes")
    elif cmd == "resume":
        print("resumed", act("NtResumeProcess"), "processes")
    else:
        tree = fleet_tree()
        print(len(tree), "fleet processes:", ", ".join(sorted({p["Name"] for p in tree})))

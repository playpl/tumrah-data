"""The control room: the "Claude" tab of the admin page (py dm.py page, http://127.0.0.1:8770).

One screen to follow and run everything (owner, 2026-11-11):
 - Run: the owner's commands as buttons (Update data, ledger, tests...). Output streams to the page; logs land in
   control/runs/.
 - Ask Claude: the owner types, the server starts Claude Code headless (`claude -p`, stream-json) in this folder and
   shows every step live: what it reads, what it runs, its task list (TodoWrite), its answer. One conversation is
   kept (resume by session id) until the owner presses New chat. The same session opens in the Claude app with
   `claude --resume <id>`.
 - Board: the owner's own list. The owner adds, edits and ticks items; Claude adds and ticks them too
   (`py control.py board add "text"`, `py control.py board done <id>`, `py control.py board list`).
 - Pulse: a beat number that climbs every 2 seconds while the server is up, so the page shows it is alive.

State lives in control/ (chat.jsonl, board.json, state.json, runs/). Nothing here writes the website.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIR = ROOT / "control"
RUN_DIR = DIR / "runs"
CHAT = DIR / "chat.jsonl"
BOARD = DIR / "board.json"
STATE = DIR / "state.json"
LOCK = threading.RLock()
MAX_LINES = 4000  # per run kept in memory; the whole log is on disk

# The buttons. Only these run from the page: a label maps to a fixed command, nothing typed by hand reaches a shell.
COMMANDS = {
    "update-dry": {"label": "Update data (dry run)", "cmd": ["py", "update_data.py", "--dry"], "group": "Data"},
    "update": {"label": "Update data", "cmd": ["py", "update_data.py"], "group": "Data"},
    "update-notg": {"label": "Update data, no Telegram", "cmd": ["py", "update_data.py", "--no-telegram"], "group": "Data"},
    "site-dry": {"label": "Site import (dry run)", "cmd": ["py", "site_import.py", "--dry"], "group": "Data"},
    "site-import": {"label": "Site import (writes the website)", "cmd": ["py", "site_import.py"], "group": "Data"},
    "ledger-sync": {"label": "Ledger sync", "cmd": ["py", "ledger.py", "sync"], "group": "Ledger"},
    "ledger-status": {"label": "Ledger status", "cmd": ["py", "ledger.py", "status"], "group": "Ledger"},
    "placement": {"label": "Placement verdicts", "cmd": ["py", "placement.py"], "group": "Ledger"},
    "decisions": {"label": "Refresh decisions", "cmd": ["py", "decisions.py"], "group": "Ledger"},
    "status": {"label": "Modules status", "cmd": ["py", "dm.py", "status"], "group": "Look"},
    "runners": {"label": "Who can work", "cmd": ["py", "runners.py"], "group": "Look"},
    "backup": {"label": "Backup status", "cmd": ["py", "backup.py", "status"], "group": "Look"},
    "tests": {"label": "Run tests", "cmd": ["py", "-m", "unittest", "discover", "tests"], "group": "Look"},
}

SYSTEM = """You are driven from the owner's control page (the "Claude" tab of the data admin page, page.py). The owner
reads your messages there, not in a terminal: short, plain words, no tables wider than the screen.
- Follow CLAUDE.md and the memory rules in full. Never write the website. Never answer the owner's decision cards.
- For any work with more than one step, keep a task list with TodoWrite: the page draws it as the live plan.
- The owner's board (their own to-do list) is in control/board.json. Read it with `py control.py board list`. When you
  finish an item, tick it: `py control.py board done <id>`. Add follow-ups the owner must see: `py control.py board add "text"`.
- The page has buttons for Update data, ledger sync/status, placement, tests. You may run the same commands yourself.
- End with what changed, what waits, and what needs the owner, in a few lines."""

BEAT = {"n": 0, "since": time.strftime("%Y-%m-%d %H:%M")}
RUNS = {}  # run id -> {"key", "label", "state", "lines", "started", "ended", "rc", "proc"}
CLAUDE = {"proc": None, "busy": False, "started": None}


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path, data):
    DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _env():
    return {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def _beat():
    while True:
        time.sleep(2)
        BEAT["n"] += 1


def start():
    """Called once by the page server."""
    DIR.mkdir(exist_ok=True)
    RUN_DIR.mkdir(exist_ok=True)
    threading.Thread(target=_beat, daemon=True).start()


# ---- runs ------------------------------------------------------------------------------------------------------------
def run(key):
    c = COMMANDS.get(key)
    if not c:
        return {"error": "unknown command"}
    with LOCK:
        if any(r["key"] == key and r["state"] == "running" for r in RUNS.values()):
            return {"error": f"{c['label']} is already running"}
        rid = time.strftime("%m%d-%H%M%S-") + key
        r = RUNS[rid] = {"key": key, "label": c["label"], "state": "running", "lines": [], "started": time.strftime("%H:%M:%S"),
                         "ended": None, "rc": None, "proc": None}
        while len(RUNS) > 30:  # keep the newest 30
            old = next(k for k, v in RUNS.items() if v["state"] != "running")
            RUNS.pop(old)

    def go():
        log = (RUN_DIR / f"{rid}.log").open("w", encoding="utf-8")
        log.write("$ " + " ".join(c["cmd"]) + "\n")
        try:
            p = r["proc"] = subprocess.Popen(c["cmd"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                             encoding="utf-8", errors="replace", env=_env(),
                                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in p.stdout:
                log.write(line)
                log.flush()
                r["lines"].append(line.rstrip("\n"))
                if len(r["lines"]) > MAX_LINES:
                    del r["lines"][:500]
            r["rc"] = p.wait()
            r["state"] = "done" if r["rc"] == 0 else ("stopped" if r["state"] == "stopping" else "failed")
        except Exception as e:  # noqa: BLE001 - shown on the page
            r["lines"].append(f"{type(e).__name__}: {e}")
            r["state"] = "failed"
        finally:
            r["ended"] = time.strftime("%H:%M:%S")
            r["proc"] = None
            log.close()
    threading.Thread(target=go, daemon=True).start()
    return {"id": rid}


def stop_run(rid):
    r = RUNS.get(rid)
    if r and r["proc"]:
        r["state"] = "stopping"
        _kill(r["proc"])
        return {"ok": True}
    return {"error": "not running"}


def run_log(rid, since=0):
    r = RUNS.get(rid)
    if not r:
        return {"error": "gone"}
    return {"state": r["state"], "rc": r["rc"], "lines": r["lines"][since:], "next": len(r["lines"])}


def runs_list():
    return [{"id": k, "label": v["label"], "state": v["state"], "started": v["started"], "ended": v["ended"],
             "last": v["lines"][-1] if v["lines"] else ""} for k, v in reversed(RUNS.items())]


def _kill(p):
    if os.name == "nt":  # the whole tree: py and the children it started
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        p.kill()


# ---- chat with Claude ------------------------------------------------------------------------------------------------
def _chat_add(kind, text="", **extra):
    with LOCK:
        n = sum(1 for _ in CHAT.open(encoding="utf-8")) if CHAT.exists() else 0
        row = {"n": n, "at": time.strftime("%H:%M:%S"), "kind": kind, "text": text, **extra}
        with CHAT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def chat(since=0):
    rows = []
    if CHAT.exists():
        with CHAT.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= since:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass
    st = _load(STATE, {})
    return {"rows": rows, "next": since + len(rows), "busy": CLAUDE["busy"], "since": CLAUDE["started"],
            "session": st.get("session"), "todos": st.get("todos", []), "cost": st.get("cost", 0.0)}


def _tool_text(name, inp):
    pick = {"Bash": "description", "PowerShell": "description", "Read": "file_path", "Edit": "file_path", "Write": "file_path",
            "Grep": "pattern", "Glob": "pattern", "Agent": "description", "WebFetch": "url", "WebSearch": "query",
            "Skill": "skill"}
    t = inp.get(pick.get(name, ""), "") or inp.get("command", "")
    if name in ("Bash", "PowerShell") and inp.get("command"):
        return f"{t}\n{inp['command']}" if t else inp["command"]
    if isinstance(t, str) and t.startswith(str(ROOT)):
        t = t[len(str(ROOT)) + 1:]
    return t if isinstance(t, str) else json.dumps(t)[:300]


def _result_text(content):
    if isinstance(content, list):
        content = "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    content = str(content or "")
    return content if len(content) < 1500 else content[:1500] + f"\n... ({len(content)} characters)"


def ask(text):
    text = (text or "").strip()
    if not text:
        return {"error": "empty"}
    exe = shutil.which("claude")
    if not exe:
        return {"error": "the claude command is not installed on this computer"}
    with LOCK:
        if CLAUDE["busy"]:
            return {"error": "Claude is still working: wait, or press Stop"}
        CLAUDE.update(busy=True, started=time.strftime("%H:%M:%S"))
    st = _load(STATE, {})
    _chat_add("you", text)
    cmd = [exe, "-p", text, "--output-format", "stream-json", "--verbose", "--permission-mode", "auto",
           "--append-system-prompt", SYSTEM]
    if st.get("session"):
        cmd += ["--resume", st["session"]]
    tools = {}  # tool_use id -> chat row number, to mark its result

    def go():
        try:
            p = CLAUDE["proc"] = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                                  stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                                  env=_env(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in p.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                _event(ev, tools)
            rc = p.wait()
            if rc and not CLAUDE.get("stopped"):
                err = (p.stderr.read() or "").strip()[-600:]
                _chat_add("error", err or f"Claude stopped with code {rc}")
        except Exception as e:  # noqa: BLE001 - shown on the page
            _chat_add("error", f"{type(e).__name__}: {e}")
        finally:
            if CLAUDE.pop("stopped", None):
                _chat_add("error", "Stopped by the owner.")
            CLAUDE.update(busy=False, proc=None)
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


def _event(ev, tools):
    t = ev.get("type")
    st = _load(STATE, {})
    if ev.get("session_id") and st.get("session") != ev["session_id"]:
        st["session"] = ev["session_id"]
        _save(STATE, st)
    if t == "assistant":
        for b in ev.get("message", {}).get("content", []):
            if b.get("type") == "text" and b.get("text", "").strip():
                _chat_add("claude", b["text"].strip())
            elif b.get("type") == "tool_use":
                inp = b.get("input") or {}
                if b.get("name") == "TodoWrite":
                    st = _load(STATE, {})
                    st["todos"] = [{"text": x.get("content", ""), "state": x.get("status", "pending")} for x in inp.get("todos", [])]
                    _save(STATE, st)
                    continue
                row = _chat_add("tool", _tool_text(b.get("name", ""), inp), tool=b.get("name"), state="running")
                tools[b.get("id")] = row["n"]
    elif t == "user":
        for b in ev.get("message", {}).get("content", []) if isinstance(ev.get("message", {}).get("content"), list) else []:
            if b.get("type") == "tool_result" and b.get("tool_use_id") in tools:
                _chat_add("output", _result_text(b.get("content")), of=tools[b["tool_use_id"]], error=bool(b.get("is_error")))
    elif t == "result":
        st = _load(STATE, {})
        st["cost"] = round(st.get("cost", 0.0) + (ev.get("total_cost_usd") or 0.0), 4)
        _save(STATE, st)
        secs = round((ev.get("duration_ms") or 0) / 1000)
        _chat_add("done", f"Finished in {secs // 60} min {secs % 60} s" if secs >= 60 else f"Finished in {secs} s",
                  error=bool(ev.get("is_error")))


def stop_claude():
    p = CLAUDE.get("proc")
    if not p:
        return {"error": "Claude is not working"}
    CLAUDE["stopped"] = True
    _kill(p)
    return {"ok": True}


def new_chat():
    if CLAUDE["busy"]:
        return {"error": "Claude is still working"}
    with LOCK:
        if CHAT.exists():
            CHAT.replace(DIR / f"chat_{time.strftime('%Y%m%d-%H%M%S')}.jsonl")  # kept, never deleted
        st = _load(STATE, {})
        st.update(session=None, todos=[])
        _save(STATE, st)
    return {"ok": True}


# ---- the board -------------------------------------------------------------------------------------------------------
def board():
    return _load(BOARD, [])


def board_op(op, item_id=None, text=None, state=None, by="owner"):
    with LOCK:
        items = board()
        if op == "add":
            if not (text or "").strip():
                return {"error": "empty"}
            items.append({"id": uuid.uuid4().hex[:6], "text": text.strip(), "state": "todo", "by": by,
                          "at": time.strftime("%Y-%m-%d %H:%M")})
        else:
            it = next((x for x in items if x["id"] == item_id), None)
            if not it:
                return {"error": "no such item"}
            if op == "edit":
                it["text"] = (text or it["text"]).strip()
            elif op == "state":
                it["state"] = state if state in ("todo", "doing", "done") else it["state"]
                it["done_by" if it["state"] == "done" else "moved_by"] = by
            elif op == "delete":
                items = [x for x in items if x["id"] != item_id]
        _save(BOARD, items)
        return {"ok": True, "items": items}


# ---- the pulse -------------------------------------------------------------------------------------------------------
_LOOK = {"at": 0, "data": {}}


def look():
    """Beat, Claude, runs and the headline numbers. The slow parts (runners, decisions) at most once a minute."""
    if time.time() - _LOOK["at"] > 60:
        _LOOK["at"] = time.time()
        threading.Thread(target=_refresh_look, daemon=True).start()
    exe = shutil.which("claude")
    return {"beat": BEAT["n"], "up_since": BEAT["since"], "claude": bool(exe), "busy": CLAUDE["busy"],
            "session": _load(STATE, {}).get("session"), "runs": runs_list(),
            "commands": [{"key": k, "label": v["label"], "group": v["group"]} for k, v in COMMANDS.items()],
            "board": board(), **_LOOK["data"]}


def _refresh_look():
    out = {}
    try:
        import runners
        h = runners.health()
        out["workers"] = {"fleet": h["fleet"].get("note") if not h["fleet"]["up"] else "up",
                          "web": h["web"].get("note") if not h["web"]["up"] else h["web"].get("note", "up")}
    except Exception as e:  # noqa: BLE001
        out["workers"] = {"error": str(e)[:200]}
    try:
        import decisions
        t = decisions.today(sync_age=600)
        out["cards"] = len(t.get("cards", []))
        out["metrics"] = t.get("metrics")
    except Exception as e:  # noqa: BLE001
        out["cards_error"] = str(e)[:200]
    _LOOK["data"] = out


# ---- command line for Claude -----------------------------------------------------------------------------------------
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if a[:1] == ["board"]:
        op = a[1] if len(a) > 1 else "list"
        if op == "list":
            for it in board():
                print(f"{it['id']}  [{it['state']}]  {it['text']}")
        elif op == "add":
            print(board_op("add", text=" ".join(a[2:]), by="claude"))
        elif op in ("done", "doing", "todo"):
            print(board_op("state", item_id=a[2], state=op, by="claude").get("error", "ok"))
        else:
            print("py control.py board list | add <text> | done|doing|todo <id>")
    else:
        print(__doc__)

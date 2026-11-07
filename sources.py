"""Telegram sources outside the polls channels: QuizBot quizzes and Google Forms.

The scrapers live in the tumrah repo (scripts/telegram/{export,quizbot,forms}); this file runs them on
tumrah-data folders through their folder overrides (TG_EXPORT_DIR, TG_EXPORTS, QUIZBOT_OUT, FORMS_OUT).

    py dm.py tg export [--account voter2]   fresh read-only export of every chat the account is in (never joins)
    py dm.py tg collect [--old]             list quizzes and forms with every sighting (no network)
    py dm.py tg plan                        choose MSK / CNS quizzes and forms (config.json module_windows)
    py dm.py tg play [--account scraper]    play the planned quizzes: Telegram's correct flag gives each key
    py dm.py tg forms [--keys]              read every form page; --keys submits planned forms to read their score keys

Keys come only from the source: QuizBot's correct flag, the form's own score page. Nothing is guessed.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "sources"
EXPORT, QUIZBOT, FORMS = SRC / "export", SRC / "quizbot", SRC / "forms"
TELEGRAM = Path(r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram")
PY313 = r"C:\Users\Ahmed\AppData\Local\Programs\Python\Python313\python.exe"  # Telethon lives here
OLD = Path(r"C:\Users\Ahmed\Desktop\tumrah for med")
OLD_DECISIONS = OLD / "quizbot_2026-10-14" / "quiz_modules.json"
OLD_NAMES = {"Musculoskeletal": "year1-musculoskeletal", "CNS & Special Senses": "year2-cns"}


def env():
    e = dict(os.environ, TG_EXPORT_DIR=str(EXPORT), QUIZBOT_OUT=str(QUIZBOT), FORMS_OUT=str(FORMS))
    if (EXPORT / "raw").exists():
        e["TG_EXPORTS"] = str(EXPORT / "raw")
    return e


def run(script, *args, extra_env=None):
    cmd = [PY313, str(TELEGRAM / script), *map(str, args)]
    print("$", " ".join(cmd[1:]), flush=True)
    return subprocess.run(cmd, env={**env(), **(extra_env or {})}).returncode


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def in_window(sighting, windows):
    batch, day = str(sighting.get("chat_batch")), (sighting.get("date") or "")[:10]
    return any(batch == str(w["batch"]) and w["from"] <= day <= w.get("to", "9999-12-31") for w in windows)


def plan(items, windows_by_module, decided=None):
    """{module: [item]}. A reader's earlier decision wins; otherwise a sighting inside a module's posting window."""
    decided = decided or {}
    out = {m: [] for m in windows_by_module}
    for item in items:
        key = item.get("param") or item.get("link")
        old = decided.get(key)
        if old and old not in ("check", "not_a_quiz"):
            module = OLD_NAMES.get(old)
            reason = f"read on 2026-10-14 as {old}"
        else:
            hits = [m for m, w in windows_by_module.items() if any(in_window(s, w) for s in item["sightings"])]
            module = hits[0] if len(hits) == 1 else None
            reason = "posted inside the module's window" if module else None
        if module in out:
            out[module].append({**item, "module": module, "reason": reason})
    return out


def cmd_export(args):
    EXPORT.mkdir(parents=True, exist_ok=True)
    if run("export/list_dialogs.py", args.account):
        sys.exit("list_dialogs failed")
    dialogs = json.loads((EXPORT / f"dialogs_{args.account}.json").read_text(encoding="utf-8"))
    ids = [d["id"] for d in dialogs if d.get("kind") != "user"]
    print(f"{len(ids)} chats to export with {args.account}")
    sys.exit(run("export/export_chats.py", args.account, *ids))


def cmd_collect(args):
    for d in (QUIZBOT, FORMS):
        d.mkdir(parents=True, exist_ok=True)
    extra = {"TG_EXPORTS": ""} if args.old else None  # empty: the scripts fall back to the October exports
    if not args.old and not (EXPORT / "raw").exists():
        sys.exit("no fresh export yet: run `py dm.py tg export`, or pass --old to read the October exports")
    run("quizbot/collect_quizbot.py", extra_env=extra)
    run("forms/collect_forms.py", extra_env=extra)


def cmd_plan(_):
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    windows = cfg["module_windows"]
    decided = {k: v["module"] for k, v in json.loads(OLD_DECISIONS.read_text(encoding="utf-8")).items()} \
        if OLD_DECISIONS.exists() else {}
    quizzes = plan(read_jsonl(QUIZBOT / "quizbot_links.jsonl"), windows, decided)
    play = [{"param": q["param"], "module": q["module"], "reason": q["reason"]} for m in quizzes.values() for q in m]
    (QUIZBOT / "play_list.json").write_text(json.dumps(play, ensure_ascii=False, indent=1), encoding="utf-8")
    forms = plan(read_jsonl(FORMS / "forms_links.jsonl"), windows)
    rows = [{"link": f["link"], "url": f["url"], "module": f["module"], "reason": f["reason"]} for m in forms.values() for f in m]
    with open(FORMS / "forms_plan.jsonl", "w", encoding="utf-8") as out:
        for r in rows:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    for m in windows:
        print(f"{m}: {len(quizzes[m])} quizzes, {len(forms[m])} forms")


def cmd_play(args):
    if not (QUIZBOT / "play_list.json").exists():
        sys.exit("run `py dm.py tg plan` first")
    sys.exit(run("quizbot/play_quizzes.py", args.account))


def cmd_forms(args):
    if run("forms/fetch_forms.py"):
        sys.exit("fetch_forms failed")
    if not args.keys:
        return
    fetched = {r["link"]: r for r in read_jsonl(FORMS / "forms_fetched.jsonl")}
    planned = read_jsonl(FORMS / "forms_plan.jsonl")
    (FORMS / "labeled").mkdir(exist_ok=True)
    with open(FORMS / "labeled" / "forms_labeled.jsonl", "w", encoding="utf-8") as out:
        for p in planned:
            out.write(json.dumps({**p, "status": fetched.get(p["link"], {}).get("status", "not_read")}) + "\n")
    for module in sorted({p["module"] for p in planned}):
        run("forms/reveal_form_keys.py", "--module", module)


def add_parser(sub):
    p = sub.add_parser("tg", help="QuizBot and Google Forms outside the polls channels")
    s = p.add_subparsers(dest="tg", required=True)
    e = s.add_parser("export")
    e.add_argument("--account", default="voter2")
    e.set_defaults(fn=cmd_export)
    c = s.add_parser("collect")
    c.add_argument("--old", action="store_true", help="read the October exports instead of the fresh one")
    c.set_defaults(fn=cmd_collect)
    s.add_parser("plan").set_defaults(fn=cmd_plan)
    pl = s.add_parser("play")
    pl.add_argument("--account", default="scraper")
    pl.set_defaults(fn=cmd_play)
    f = s.add_parser("forms")
    f.add_argument("--keys", action="store_true", help="submit planned forms to read their score keys")
    f.set_defaults(fn=cmd_forms)

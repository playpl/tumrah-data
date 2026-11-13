"""Answer keys for Google Forms, from the form's own score page (owner, 2026-11-10: "after submitting, answers show").

A form's public page has no answers; its score page, shown after a submission, marks the correct option. This submits
each form (first option everywhere, "Tumrah" in required text fields, no personal data; a form that hides the correct
answer is resubmitted with the next option, at most 5 times: `reveal_form_keys.py`, owner rule D47), reads the score page
and saves the key. The key is only what the form shows. Sign-in forms are recorded and skipped.

    py form_keys.py lectures          the quiz forms of the owner's lecture files (doctors/ folder, chapter quizzes)
    py form_keys.py plan              the planned MSK forms (sources/forms/forms_plan.jsonl)
    py form_keys.py url <link> ...    these forms
      --limit N                       at most N forms this run          --apply   then also fill the lecture lists

Resumable: forms done are skipped (errors are retried). Outputs: sources/forms/keys/form_keys.jsonl and
form_status.jsonl (what `merge.py` reads: rerun `py dm.py bank` to give the bank these keys) and
sources/forms/keys/own_form_keys.jsonl (question text + options + key, to fill lecture rows by `apply`).

    py form_keys.py apply             fill the key of every lecture row (required / doctor list) whose question a form keyed;
                                      then `py site_questions.py year2-cns`, `py fast_lessons.py build`, `py tiers.py`.
"""
import json
import os
import re
import sys
import time

import lectures  # first: the forms scripts put another `lectures` module on sys.path
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("FORMS_OUT", str(ROOT / "sources" / "forms"))  # before reveal_form_keys reads it
sys.path.insert(0, r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\forms")
import reveal_form_keys as R  # noqa: E402

KEYS = ROOT / "sources" / "forms" / "keys"


def fold(t):
    return re.sub(r"\s+", " ", (t or "").replace("\u00a0", " ")).strip().lower()


def lecture_links():
    import doctors_folder
    lessons, _ = doctors_folder.scan()
    out = [k["url"] for x in lessons for k in x["links"] if k["kind"] in ("quiz", "required_quiz") and k.get("url")]
    for f in ("chapter_quizzes.json",):
        p = ROOT / "modules" / "year2-cns" / "site" / f
        out += list(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else []
    nag = doctors_folder.find_doctor_folder("physiology", "nageb")
    out += [doctors_folder.url_file(f) for f in nag.glob("*.url")]
    return [u for u in dict.fromkeys(out) if u]


def plan_links():
    return [json.loads(x)["link"] for x in open(ROOT / "sources" / "forms" / "forms_plan.jsonl", encoding="utf-8")]


def run(links, limit=None):
    KEYS.mkdir(parents=True, exist_ok=True)
    status_f, keys_f, own_f = KEYS / "form_status.jsonl", KEYS / "form_keys.jsonl", KEYS / "own_form_keys.jsonl"
    done = {r["link"] for r in (json.loads(x) for x in open(status_f, encoding="utf-8"))
            if not r["status"].startswith("error")} if status_f.exists() else set()
    todo = [u for u in links if u not in done][:limit]
    seen = {}
    real_read = R.read_form

    def capture(op, link):  # keep the form's question text and options for `apply`
        form, status = real_read(op, link)
        if form:
            seen[link] = form
        return form, status
    R.read_form = capture
    totals = {"forms": 0, "keys": 0, "submissions": 0, "no_keys": 0}
    for link in todo:
        try:
            status, keys, rounds = R.solve(R.opener(), link)
        except Exception as e:  # noqa: BLE001 - one bad form is recorded; the run goes on
            status, keys, rounds = f"error:{type(e).__name__}:{getattr(e, 'code', '')}", [], 0
        with open(keys_f, "a", encoding="utf-8") as out:
            for k in keys:
                out.write(json.dumps(k, ensure_ascii=False) + "\n")
        form = seen.get(link)
        if form and keys:
            by_id = {q["item_id"]: q for q in form["questions"]}
            with open(own_f, "a", encoding="utf-8") as out:
                for k in keys:
                    q = by_id.get(str(k["item_id"]))
                    if q:
                        out.write(json.dumps({"link": link, "item_id": k["item_id"], "question": q["title"], "options": q["options"],
                                              "correct_index": k["correct_index"]}, ensure_ascii=False) + "\n")
        with open(status_f, "a", encoding="utf-8") as out:
            out.write(json.dumps({"link": link, "status": status, "keys": len(keys), "submissions": rounds}) + "\n")
        totals["forms"] += 1
        totals["keys"] += len(keys)
        totals["submissions"] += rounds
        totals["no_keys"] += not keys
        print(f"{totals['forms']}/{len(todo)} {status} keys={len(keys)} rounds={rounds}", flush=True)
        time.sleep(R.PACE)
    return totals


def apply():
    """Fills `key` of lecture rows (item["row"]) from the keys forms showed, matched by question text and option set."""
    f = KEYS / "own_form_keys.jsonl"
    if not f.exists():
        return ["no form keys yet"]
    by = {}
    for x in (json.loads(l) for l in open(f, encoding="utf-8")):
        by[(fold(x["question"]), frozenset(fold(o) for o in x["options"]))] = x
    filled = rows = 0
    for m in lectures.all_lectures():
        changed = False
        for name in ("required", "doctor_questions"):
            for it in m.get(name) or []:
                r = it.get("row")
                if not r:
                    continue
                rows += 1
                if r.get("key") is not None:
                    continue
                x = by.get((fold(r["question"]), frozenset(fold(o) for o in r["options"])))
                if x:
                    r["key"] = next(i for i, o in enumerate(r["options"]) if fold(o) == fold(x["options"][x["correct_index"]]))
                    filled += 1
                    changed = True
        if changed:
            lectures.save(m)
    return [f"{filled} lecture row(s) got their key from a form's score page ({rows} rows without a bank match checked)"]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    limit = int(a[a.index("--limit") + 1]) if "--limit" in a else None
    cmd = a[0] if a else "lectures"
    if cmd == "apply":
        print("\n".join(apply()))
        sys.exit()
    links = lecture_links() if cmd == "lectures" else plan_links() if cmd == "plan" else [x for x in a[1:] if x.startswith("http")]
    print(json.dumps(run(links, limit)))
    if "--apply" in a or cmd in ("lectures", "url"):
        print("\n".join(apply()))

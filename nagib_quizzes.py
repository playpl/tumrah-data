"""Dr. Nagib's chapter quizzes (owner, 2026-11-09): his Google Forms are the Required questions, but each covers a
whole chapter, so every question goes to the lecture whose handout lines it points at.

Step 1 (here): read each form (read only, never submitted) and match its questions to the bank by script
(`dm.py cover`). Matched questions carry the bank's source key. Writes modules/year2-cns/site/nagib_quiz.json:
[{form, n, word_key | null}]. Counts only.
Step 2 (tiers.py): a matched question becomes Required for the Nagib lecture whose pages hold its pointer.

    py nagib_quizzes.py
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import doctors_folder
import page

ROOT = Path(__file__).resolve().parent
NAGEB = doctors_folder.find_doctor_folder("physiology", "nageb")
OUT = ROOT / "modules" / "year2-cns" / "site" / "nagib_quiz.json"


def main():
    import cover
    _, by = page.bank_rows()
    prefix = {k[:16]: k for k in by}
    rows, counts = [], Counter()
    for f in sorted(NAGEB.glob("*.url")):
        url = re.search(r"URL=(\S+)", f.read_text(encoding="utf-8")).group(1)
        tmp = ROOT / "bank" / "inbox" / f"nagib-{re.sub(r'[^a-z0-9]+', '-', f.stem.lower())}.jsonl"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        n = doctors_folder.read_form(url, tmp)
        page.run_cover(tmp)
        entry = cover.covered(tmp)
        matched = json.loads("[" + ",".join((ROOT / "bank" / f"cover_{entry['sha']}.jsonl").read_text(encoding="utf-8").split("\n")[:-1]) + "]") \
            if entry else []
        for i, r in enumerate(matched):
            m = r.get("match")
            wk = prefix.get(m[5:]) if isinstance(m, str) and m.startswith("bank:") else None
            rows.append({"form": f.stem, "n": i, "word_key": wk, "site": m if m and not wk else None})
            counts[f"{f.stem}: {'bank' if wk else 'site' if m else 'no match'}"] += 1
        counts[f"{f.stem}: questions"] += n
    OUT.write_text(json.dumps(rows), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(counts, indent=1))


def keys():
    """Owner approved 2026-11-09: submit each of Nagib's forms (no personal data) and read the keys its own score page
    shows (tumrah scripts/telegram/forms/reveal_form_keys.solve). Writes modules/year2-cns/site/nagib_quiz_keyed.jsonl:
    one row per question with its form, question, options and the form's key. Counts only."""
    sys.path.insert(0, r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\forms")
    import reveal_form_keys as R
    out, counts = [], Counter()
    for f in sorted(NAGEB.glob("*.url")):
        url = re.search(r"URL=(\S+)", f.read_text(encoding="utf-8")).group(1)
        op = R.opener()
        form, _ = R.read_form(op, url)
        status, found, rounds = R.solve(R.opener(), url)
        by_item = {k["item_id"]: k for k in found}
        for q in (form or {}).get("questions", []):
            if q["type"] == 4:
                continue
            k = by_item.get(q["item_id"])
            out.append({"form": f.stem, "url": url, "item_id": q["item_id"], "question": q["title"], "options": q["options"],
                        "key": k["correct_index"] if k else None, "key_source": k["key_source"] if k else None})
            counts[f"{f.stem}: {'keyed' if k else 'no key'}"] += 1
        counts[f"{f.stem}: status {status}, {rounds} submissions"] += 1
    path = OUT.with_name("nagib_quiz_keyed.jsonl")
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":
    keys() if sys.argv[1:] == ["keys"] else main()

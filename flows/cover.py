"""Cover flow: a worker decides, for each question the script could not match, whether one of its listed candidates is
the same question (every word of stem and options the same, apart from spelling and punctuation) or none is.

Payload: {"file": path, "sha": id, "items": [{"i", "question", "options", "candidates": [{"id", "text"}]}]}.
"""
import json
from pathlib import Path

import cover
from flows import common

BRIEF = """# Brief: is this question already in our bank?

For each item in `batch.jsonl` you get one question (`question`, `options`) and up to 5 `candidates` from our bank
(`id`, `text` = stem | option | option ...). The candidates were listed because they share rare words; they are only
an index. Read each one.

- A candidate is the same question only if the stem and the options say the same thing word for word (spelling,
  spacing, punctuation, numbering and option order do not matter). One different word (arm / leg, increase /
  decrease, EXCEPT) makes a different question: answer null.
- Never judge which option is right.

Write `out.jsonl`, one line per item: `{"i": <item i>, "match": "<candidate id>" or null}`.
Run `python tools/check.py` until it prints PASS. Final reply: the PASS line and how many matched.
"""


class CoverFlow:
    lane = "pointers"
    timeout = 45

    def prepare(self, job, job_dir: Path):
        p = job["payload"]
        batch = [{"i": it["i"], "question": it["question"], "options": it["options"],
                  "candidates": [c["id"] for c in it["candidates"]], "candidate_text": it["candidates"]} for it in p["items"]]
        common.build(job_dir, None, batch, "check_cover", "out.jsonl", BRIEF)
        prompt = job_dir / "prompt.md"
        prompt.write_text("Read BRIEF.md in this folder to the end and follow it exactly. " + common.SUBAGENTS + "\n",
                          encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        rows = common.output_rows(job_dir)
        if rows is None:
            return ["out.jsonl is missing"]
        batch = [{"i": it["i"], "candidates": [c["id"] for c in it["candidates"]]} for it in job["payload"]["items"]]
        errors = cover.check_cover(rows, batch)
        if not errors:
            sha = job["payload"]["sha"]
            path = cover.BANK / f"cover_{sha}.jsonl"
            results = cover.read_jsonl(path)
            for r in rows:
                if r["match"] is not None:
                    results[r["i"]]["match"] = r["match"]
            common.write_jsonl(path, results)
            matched = sum(x["match"] is not None for x in results)
            entry = {"file": job["payload"]["file"], "sha": sha, "questions": len(results), "matched": matched,
                     "percent": round(100 * matched / len(results), 1), "at": "after fleet", "fleet_job": job["key"]}
            with open(cover.BANK / "covered.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        return errors

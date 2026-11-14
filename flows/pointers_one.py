"""One-read pointer flow (owner, 2026-11-14: fewer tokens, more accurate; design checked with Fable).

Code writes one file, `read.txt`: the scoped handout pages as `LINEID text` (figures marked), then 25 questions with the
keyed option marked, plus 2 decoys (questions taught in another lecture). The worker reads it once and writes
`answers.jsonl` with line IDs, no copied text and no search tools. Two independent reads (reader A, reader B: other
batch order, pages in reverse) are two ledger runners (`haiku-A`, `haiku-B`); agreement makes a link ready.

Payload: {module, reader: "A"|"B", scope: {title, ranges, lectures}, batch: [pointer rows], decoys: [pointer rows]}.
"""
import json
import random
import re
from pathlib import Path

from flows import common

ROOT = Path(__file__).resolve().parents[1]
PY = "C:/Users/Ahmed/AppData/Local/Programs/Python/Python313/python.exe"
NONE_REASONS = {"other_lecture", "not_in_book"}
WORD = re.compile(r"[a-z0-9][a-z0-9]{2,}")  # 3+ characters: PAG, SGR, CSF are key terms
GENERIC = set("""which following about there their these those other because during between after before under with
from that this have been were does most least true false except correct statement regarding concerning""".split())

INSTRUCTIONS = """# Point each question at the handout lines that teach its answer

Below are handout pages ({pages}) under the title "{title}", one line per row: `LINEID text`. A figure is
`LINEID [FIGURE] caption`. Then {n} questions; the keyed option is marked `*` (context only: never judge it).

For each question give the fewest lines that hold what a student needs to understand the keyed option: the exact
sentence(s), bullet(s) or table row(s), never a heading alone and never a line that only shares a word. Some
questions are not taught on these pages: answer none for them. A wrong pointer is worse than none.

Write `answers.jsonl`, one JSON object per question, in question order:
{{"q": 1, "ids": ["p132:l2", ...], "because": "<12 words or fewer, quoting the key term from your line>"}}
{{"q": 2, "none": "other_lecture"}}   (taught elsewhere in the handout)   or   {{"q": 2, "none": "not_in_book"}}

Then run `python check.py`. Fix every error it prints and run it again until it prints PASS.
"""


def handout_lines(module):
    return common.read_jsonl(ROOT / "modules" / module / "lines.jsonl")


def pages_of(ranges):
    return {p for a, b in ranges for p in range(a, b + 1)}


def short(line_id):
    """year2-cns:d30dcde2:p132:l2 -> p132:l2 (what the worker reads and writes)."""
    return line_id.split(":", 2)[2]


def line_text(ln):
    if ln.get("figure") is not None and not ln.get("text"):
        return f"[FIGURE] {ln.get('figure') or ''}".strip()
    return ln.get("text") or ""


def question_text(i, q):
    k = q.get("correct_index")
    opts = "\n".join(f"{' *' if j == k else '  '} {'ABCDE'[j]}. {o}" for j, o in enumerate(q["options"]))
    case = f"\n{q['case_text']}" if q.get("case_text") else ""
    return f"Q{i}. {q['stem']}{case}\n{opts}"


class PointerOneFlow:
    lane = "pointers"
    timeout = 30

    def prepare(self, job, job_dir: Path):
        p = job["payload"]
        job_dir.mkdir(parents=True, exist_ok=True)
        keep = pages_of(p["scope"]["ranges"])
        rows = [ln for ln in handout_lines(p["module"]) if ln["page"] in keep and line_text(ln)]
        if p.get("reader") == "B":
            rows = sorted(rows, key=lambda ln: -ln["page"])  # same lines, pages in reverse: an independent read
        items = [dict(q, decoy=False) for q in p["batch"]] + [dict(q, decoy=True) for q in p.get("decoys") or []]
        random.Random(f"{job['key']}:{p.get('reader')}").shuffle(items)
        page = None
        out = [INSTRUCTIONS.format(pages=", ".join(f"{a}-{b}" for a, b in p["scope"]["ranges"]),
                                   title=p["scope"]["title"], n=len(items)), "## Handout pages"]
        for ln in rows:
            if ln["page"] != page:
                page = ln["page"]
                out.append(f"\n=== pdf page {page} ===")
            out.append(f"{short(ln['id'])} {line_text(ln)}")
        out.append("\n## Questions\n")
        out += [question_text(i, q) + "\n" for i, q in enumerate(items, 1)]
        (job_dir / "read.txt").write_text("\n".join(out), encoding="utf-8")
        common.write_jsonl(job_dir / "items.jsonl", [{"q": i, "qid": q["qid"], "decoy": q["decoy"]}
                                                    for i, q in enumerate(items, 1)])
        (job_dir / "check.py").write_text(
            "import subprocess, sys\nfrom pathlib import Path\n"
            f"PY = {PY!r}\n"
            "if sys.version_info < (3, 12):  # the PATH python is too old for this repo: run under 3.13\n"
            "    sys.exit(subprocess.run([PY, __file__]).returncode)\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "from flows.pointers_one import check_dir\n"
            "sys.stdout.reconfigure(encoding='utf-8')\n"
            "errors = check_dir(Path(__file__).resolve().parent)\n"
            "print('\\n'.join(errors) if errors else 'PASS')\n", encoding="utf-8")
        (job_dir / "job.json").write_text(json.dumps({"key": job["key"], "payload": p}, ensure_ascii=False), encoding="utf-8")
        prompt = job_dir / "prompt.md"
        prompt.write_text("Read read.txt in this folder from top to bottom (all of it), follow its instructions, write "
                          "answers.jsonl in this folder, then run `python check.py` until it prints PASS. Do not use "
                          "any other tool, script or search. Reply with the PASS line.\n", encoding="utf-8")
        return prompt

    def check(self, job, job_dir: Path):
        errors = check_dir(job_dir)
        if not errors:
            common.write_jsonl(job_dir / "pointers.jsonl", import_rows(job_dir))
        return errors


def _load(job_dir):
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    items = {r["q"]: r for r in common.read_jsonl(job_dir / "items.jsonl")}
    by_id = {}
    for ln in handout_lines(job["payload"]["module"]):
        by_id[ln["id"]] = by_id[short(ln["id"])] = ln
    return job, items, by_id


def check_dir(job_dir: Path):
    """Every question answered once; IDs exist and lie in the scope; decoys answered none; `because` quotes the line."""
    job, items, by_id = _load(job_dir)
    keep = pages_of(job["payload"]["scope"]["ranges"])
    f = job_dir / "answers.jsonl"
    if not f.exists():
        return ["answers.jsonl is missing"]
    errors, seen, decoy_hits = [], set(), []
    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            q = int(r["q"])
        except (ValueError, KeyError, TypeError):
            errors.append(f"line {n}: not {{\"q\": <number>, ...}} JSON")
            continue
        if q not in items:
            errors.append(f"Q{q}: there is no such question")
            continue
        if q in seen:
            errors.append(f"Q{q}: answered twice")
        seen.add(q)
        if "none" in r:
            if r["none"] not in NONE_REASONS:
                errors.append(f"Q{q}: none must be one of {sorted(NONE_REASONS)}")
            continue
        ids = r.get("ids") or []
        if not ids:
            errors.append(f"Q{q}: give ids or none")
            continue
        if items[q]["decoy"]:  # a planted question from another lecture: a hit is a quality signal, not an error
            decoy_hits.append(q)  # (some decoys turn out to be taught here too, owner 2026-11-14)
            continue
        bad = [i for i in ids if i not in by_id or by_id[i]["page"] not in keep]
        if bad:
            errors.append(f"Q{q}: {bad[:3]} are not lines on these pages")
            continue
        if len(ids) > 8:
            errors.append(f"Q{q}: {len(ids)} lines: give the fewest lines that teach it")
        because = set(WORD.findall(str(r.get("because") or "").lower())) - GENERIC
        text = " ".join(line_text(by_id[i]).lower() for i in ids)
        quote = " ".join(str(r.get("because") or "").lower().split())
        if not (quote and quote in " ".join(text.split())) and (not because or not any(w in text for w in because)):
            errors.append(f"Q{q}: `because` must quote the key term as it is written in your lines")
    (job_dir / "decoy_hits.json").write_text(json.dumps(decoy_hits), encoding="utf-8")
    missing = sorted(set(items) - seen)
    if missing:
        errors.append(f"not answered: {', '.join(f'Q{m}' for m in missing[:10])}")
    return errors


def import_rows(job_dir: Path):
    """pointers.jsonl in the shape ledger.sync reads (decoys left out)."""
    job, items, by_id = _load(job_dir)
    out = []
    for r in common.read_jsonl(job_dir / "answers.jsonl"):
        it = items.get(int(r["q"]))
        if not it or it["decoy"]:
            continue
        ids = [by_id[i]["id"] for i in r.get("ids") or [] if i in by_id]
        out.append({"question_id": it["qid"], "found": bool(ids), "partial": False, "lecture_id": None,
                    "reason": r.get("none"), "other_module": None, "spans": [{"line_ids": ids}] if ids else []})
    return out

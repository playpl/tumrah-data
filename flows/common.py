"""Builds a job folder: tools (the kit plus hub.py and checks.py), the module's handout lines and reference,
the batch and job.json. Workers see only this folder."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = Path(__file__).resolve().parent / "kit"
MODULES = ROOT / "modules"

SUBAGENTS = ("Never look at a picture, and start every subagent's prompt with: \"Never open, view or analyse any "
             "image or PDF page; work only from text.\" You are the lead worker.Start 4 subagents in parallel (never more: 16 jobs share 4 accounts' quota) and split "
             "the work between them (for example a few pages, questions or lecture parts each); with fewer than 4 items, "
             "one subagent per item, and a job of one item you do yourself. Monitor them, check each part they return, and give "
             "a part that is wrong or missing to a new subagent. You own the merged output file: run the check on the whole "
             "file yourself before you finish.")


WORKING_RULES = """

## Working rules (every job)
- NEVER LOOK AT A PICTURE. This is the worst thing you can do: it makes the job many times slower. Work only from
  text (the files in this folder and the text the tools print). Never open, view, render, screenshot or analyse an
  image or a PDF page (no .png/.jpg/.pdf with read_file, no pdftoppm, magick, get_pixmap or PIL). A figure is the text
  the tools print for it, nothing more. Tell every subagent this rule in its first line.
- Stay inside this folder. Never list, open or read anything outside it (no `..`, no other jobs' folders, no
  other workers' output): every input you need is here, and copying someone else's answer is a failure.
- The tools are for running, not for reading: never open or print their source (`tools/*.py`, `inspect`,
  `getsource`). `python tools/check.py` tells you exactly what is wrong; fix that by reading the pages again.
- Never write test, dummy or placeholder content into the output file, not even to see what the checker says: the
  output file holds only your real answer. The checker's messages already tell you the rules.
- Commands: use `python ...` (and the tools) for everything, counting lines included. `powershell -Command`, `cmd /c`
  and anything that deletes, downloads or uses git is blocked. When a command is denied, never stop: do the same
  thing another way (a python one-liner) and carry on.
- Work fast: you are the lead. Start 4 subagents in parallel, never more (16 jobs share 4 accounts' quota), for
  example a few pages, questions or lecture parts each, each writing its own part file in this folder. With fewer than
  4 items, one subagent per item; a job of one item you do yourself, with no subagents. Split by item, never one item across subagents. Give each subagent these same rules.
  Monitor them: check each part as it comes back, and give a wrong or missing part to a new subagent. When all are
  done, merge the parts into the output file named in BRIEF.md yourself (part files alone count as nothing), then run
  `python tools/check.py` on the whole file.
"""


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def module_dir(code):
    d = MODULES / code
    if not (d / "lines.jsonl").exists():
        raise FileNotFoundError(f"run `py dm.py lines {code}` first")
    return d


def build(job_dir, module, batch, checker, output, brief, extra_inputs=(), extra=None):
    tools, inputs = job_dir / "tools", job_dir / "inputs"
    tools.mkdir(parents=True, exist_ok=True)
    inputs.mkdir(exist_ok=True)
    for f in [*KIT.glob("*.py"), ROOT / "hub.py", ROOT / "checks.py"]:
        shutil.copy2(f, tools / f.name)
    src = module_dir(module) if module else None  # cover jobs need no handout
    for name in ("lines.jsonl", "reference.json", *extra_inputs) if src else ():
        if (src / name).exists() and not (inputs / name).exists():
            shutil.copy2(src / name, inputs / name)
    write_jsonl(job_dir / "batch.jsonl", batch)
    (job_dir / "job.json").write_text(json.dumps({"module": module, "batch": "batch.jsonl", "checker": checker,
                                                  "output": output, **(extra or {})}), encoding="utf-8")
    (job_dir / "BRIEF.md").write_text(brief + WORKING_RULES, encoding="utf-8")


def output_rows(job_dir):
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    out = job_dir / job["output"]
    return read_jsonl(out) if out.exists() else None

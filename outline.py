"""The handout outline: handout lecture (the module's reference list) -> sections (one per heading) -> lines.

The outline is the skeleton every link hangs on (owner, 2026-11-10: the handout is the centre). A lesson is placed as a
run of sections, so its ends fall on headings, never in the middle of a paragraph; an AI call is shown whole sections.
Headings are found by code from the line geometry: they are only places to cut, never a match.

    py outline.py year2-cns     -> modules/year2-cns/outline.json, prints counts
"""
import json
import re
import sys
from pathlib import Path

from flows.common import read_jsonl

ROOT = Path(__file__).resolve().parent
TITLE_HEIGHT = 28      # pt; a line this tall is a lecture or part title
MAX_HEADING_WORDS = 9
MIN_SECTION_LINES = 4  # a heading closer than this to the last one stays inside that section
LETTERS = re.compile(r"[A-Za-z]")


def reference(module):
    """The module's handout lectures [{lecture_id, title, subject, pdf_pages}], in handout order."""
    d = ROOT / "modules" / module
    files = [d / "reference.json", *sorted(d.glob("old/*/reference.json"), reverse=True)]
    f = next((p for p in files if p.exists()), None)
    if f is None:
        raise FileNotFoundError(f"{module}: no reference.json (the handout's lecture list)")
    return sorted(json.loads(f.read_text(encoding="utf-8"))["lectures"], key=lambda x: x["pdf_pages"][0])


def is_heading(ln, left):
    """ponytail: geometry and punctuation only (tall line, or a short line at the margin ending with a colon, or a
    short line in capitals). Reading font weight from the PDF is the upgrade if cuts land badly."""
    text = (ln.get("text") or "").strip()
    if not text or ln.get("figure") is not None or len(text.split()) > MAX_HEADING_WORDS:
        return False
    x0, y0, _, y1 = ln["bbox"]
    letters = LETTERS.findall(text)
    return (y1 - y0 >= TITLE_HEIGHT or (text.endswith(":") and x0 <= left + 20)
            or (len(letters) >= 6 and text.upper() == text))


def build(module, lines=None):
    """Sections in handout order: {id, lecture, subject, title, from, to, page, i0, i1} (i = index in lines.jsonl)."""
    lines = lines or read_jsonl(ROOT / "modules" / module / "lines.jsonl")
    left = {}
    for ln in lines:
        if ln.get("text"):
            left[ln["page"]] = min(left.get(ln["page"], 1e9), ln["bbox"][0])
    out = []
    for lec in reference(module):
        a, b = lec["pdf_pages"]
        cur = None
        for i, ln in enumerate(lines):
            if not a <= ln["page"] <= b:
                continue
            if cur is None or (is_heading(ln, left.get(ln["page"], 0)) and i - cur["i0"] >= MIN_SECTION_LINES):
                cur = {"id": f"{lec['lecture_id']}/s{sum(1 for s in out if s['lecture'] == lec['lecture_id']) + 1}",
                       "lecture": lec["lecture_id"], "subject": (lec.get("subject") or "").lower(),
                       "title": (ln.get("text") or lec["title"]).strip()[:80], "from": ln["id"], "page": ln["page"], "i0": i}
                out.append(cur)
            cur["to"], cur["i1"] = ln["id"], i
    return out


def load(module):
    f = ROOT / "modules" / module / "outline.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else write(module)


def write(module):
    own = ROOT / "modules" / module / "cut.py"
    if own.exists():   # its sections are cut by sentence there; the page-only cut here put 38 overlaps back (2026-11-18)
        raise RuntimeError(f"{module} has its own cutter: run `py {own.relative_to(ROOT).as_posix()} build`, not outline.py")
    secs = build(module)
    (ROOT / "modules" / module / "outline.json").write_text(json.dumps(secs, ensure_ascii=False), encoding="utf-8")
    return secs


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    s = write(sys.argv[1])
    sizes = sorted(x["i1"] - x["i0"] + 1 for x in s)
    print(json.dumps({"lectures": len({x["lecture"] for x in s}), "sections": len(s),
                      "lines_per_section": {"min": sizes[0], "median": sizes[len(sizes) // 2], "max": sizes[-1]}}))

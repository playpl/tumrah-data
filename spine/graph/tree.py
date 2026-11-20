"""The tree above the sentences: University -> Year -> Subject -> Chapter -> Lesson.

    modules/<m>/graph/chapters.json   the handout's own chapters, read from its contents pages. Written once;
                                      the owner looks at it and may correct it by hand (it is never overwritten).
    modules/<m>/graph/graph.json      the whole tree, rebuilt from chapters.json and the handout's lesson list.

A lesson belongs to the chapter its first page falls in. A subject's chapters are the handout chapters in which
that subject has lessons, so each subject keeps the handout's chapter numbers (Anatomy: 1, 3, 4).
"""
import re

import outline
from spine import graph_dir, module_dir, read_json, read_jsonl, write_json
from spine.graph import handout

UNIVERSITY = {"year2-cns": ("ZU", 2), "year1-musculoskeletal": ("ZU", 1), "nu-year1-musculoskeletal": ("ZNU", 1)}  # NU modules will be named nu-year1-<name>; ZU keeps the bare codes
CONTENTS_PAGES = range(1, 10)
_CHAPTER = re.compile(r"^Chapter\s+([IVX]+)\s*:\s*(.+)$", re.I)
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}


def read_contents(module):
    """Chapters as the contents pages print them: [{n, title, printed_from, units: [{n, title}], source}]."""
    tables = handout.find_tables(module)
    chapters = []
    for page in CONTENTS_PAGES:
        for table in tables.get(page, []):
            for row in table["rows"]:
                cells = [" ".join((c or "").split()) for c in row["cells"]]
                m = _CHAPTER.match(cells[0]) if cells else None
                if m:
                    chapters.append({"n": _ROMAN.get(m.group(1).upper()), "title": m.group(2).strip(),
                                     "printed_from": None, "units": [], "source": f"contents p{page}"})
                elif chapters:
                    if cells[0].isdigit() and len(cells) > 1 and cells[1]:
                        chapters[-1]["units"].append({"n": int(cells[0]), "title": cells[1]})
                    first = re.match(r"\d+", cells[-1] or "")
                    if first and chapters[-1]["printed_from"] is None:
                        chapters[-1]["printed_from"] = int(first.group(0))
    return chapters


def chapters(module):
    """chapters.json, made from the contents pages the first time."""
    path = graph_dir(module) / "chapters.json"
    saved = read_json(path)
    if saved:
        return saved
    lessons = outline.reference(module)
    first_page = min(l["pdf_pages"][0] for l in lessons)
    printed = {}        # printed page number -> pdf page (the offset changes at every unnumbered divider page)
    for ln in read_jsonl(module_dir(module) / "lines.jsonl"):
        if ln.get("printed") is not None and ln["page"] >= first_page:
            printed.setdefault(ln["printed"], ln["page"])
    found, starts = [], []
    for c in read_contents(module):
        page = printed.get(c["printed_from"])
        at = next((i for i, l in enumerate(lessons) if page and l["pdf_pages"][0] <= page <= l["pdf_pages"][1]), None)
        if at is not None:      # a chapter starts with the lesson that holds its first printed page
            found.append(c)
            starts.append(at)
    for i, c in enumerate(found):
        mine = lessons[starts[i]:starts[i + 1] if i + 1 < len(found) else len(lessons)]
        c["id"], c["pdf_pages"] = f"{module}:C{c['n']}", [mine[0]["pdf_pages"][0], mine[-1]["pdf_pages"][1]]
        c["lessons"] = [l["lecture_id"] for l in mine]
    write_json(path, found)
    return found


def build(module):
    """Write graph.json. Returns a one-line summary."""
    chaps, lessons = chapters(module), outline.reference(module)
    lines = read_jsonl(module_dir(module) / "lines.jsonl")
    university, year = UNIVERSITY.get(module, ("ZU", None))
    chapter_of = {lid: c for c in chaps for lid in c["lessons"]}
    subjects = {}
    for l in lessons:
        c = chapter_of.get(l["lecture_id"])
        subj = subjects.setdefault(l["subject"].lower(), {})
        key = c["n"] if c else 0
        subj.setdefault(key, {"id": f"{l['subject'].lower()}/c{key}", "n": key,
                              "title": c["title"] if c else "(no chapter)", "handout_chapter": c["id"] if c else None,
                              "lessons": []})["lessons"].append(
            {"id": l["lecture_id"], "title": l["title"], "pdf_pages": l["pdf_pages"]})
    graph = {"university": university, "year": year, "module": module,
             "handout": {"sha8": lines[0]["hash"], "pages": max(ln["page"] for ln in lines)},
             "subjects": [{"id": name, "chapters": [subjects[name][k] for k in sorted(subjects[name])]}
                          for name in sorted(subjects)]}
    write_json(graph_dir(module) / "graph.json", graph)
    return (f"{university} year {year}, {len(graph['subjects'])} subjects, {len(chaps)} handout chapters, "
            f"{len(lessons)} lessons")


def load(module):
    return read_json(graph_dir(module) / "graph.json")


def lessons(module):
    """{lesson id: {"subject", "chapter", "title", "pdf_pages"}} from graph.json."""
    out = {}
    for s in load(module)["subjects"]:
        for c in s["chapters"]:
            for l in c["lessons"]:
                out[l["id"]] = {"subject": s["id"], "chapter": c["id"], **l}
    return out


def check(module):
    graph = load(module)
    if not graph:
        return [("graph.json exists", False, "run: py -m spine graph build " + module)]
    placed = [l["id"] for s in graph["subjects"] for c in s["chapters"] for l in c["lessons"]]
    want = [l["lecture_id"] for l in outline.reference(module)]
    orphans = [l["id"] for s in graph["subjects"] for c in s["chapters"] if not c["handout_chapter"]
               for l in c["lessons"]]
    return [("every lesson is in the tree once", sorted(placed) == sorted(want), f"{len(placed)} of {len(want)}"),
            ("every lesson has a handout chapter", not orphans, f"no chapter: {orphans}")]

"""Files that belong to one lesson: the doctor's whiteboard notes (owner, 2026-11-13).

    doctors/<module>/<subject>/<doctor>/<n- chapter>/<any folder>/<n- name>.pdf

A PDF in a folder inside a chapter folder (Elsamahy's "ملفات السبورة ascendeng tracts") whose name starts with a lesson's
number belongs to that lesson: the lecture whose recording sits in the same chapter folder with the same number.
`py lesson_files.py` writes modules/<module>/site/lesson_files.jsonl, one row per file, for the website importer:
    {lesson: "lecture:cns-076", doctorId, kind: "whiteboard", name, file, size, sha256}
Nothing is uploaded or written to the site here. Files whose lesson is not named yet are listed in the report.
"""
import hashlib
import json
import sys
from pathlib import Path

import doctors_folder
import lectures

ROOT = Path(__file__).resolve().parent
KIND = "whiteboard"


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rows(module):
    """([row], [report line]) for every whiteboard file of the module's lectures."""
    metas = lectures.all_lectures(module)
    by_place = {}
    for m in metas:
        src = (m.get("source") or {}).get("file")
        if src and m.get("kind", "lecture") == "lecture":
            p = Path(src)
            n, _ = doctors_folder.numbered(p.stem)
            if n is not None:
                by_place[(str(p.parent).lower(), n)] = m
    out, report = [], []
    for pdf in sorted(doctors_folder.DOCTORS.rglob("*.pdf")):
        chap = pdf.parent.parent  # <chapter folder>/<notes folder>/<n- name>.pdf
        n, name = doctors_folder.numbered(pdf.stem)
        if n is None or pdf.parent == chap:
            continue
        m = by_place.get((str(chap).lower(), n))
        if m is None:
            report.append(f"whiteboard file '{pdf.name}': no lecture {n} in {chap.name} yet, waits")
            continue
        out.append({"lesson": f"lecture:{m['id']}", "doctorId": doctors_folder.ALIASES.get((m.get("doctor") or "").lower(), m.get("doctor")),
                    "kind": KIND, "name": name or pdf.stem, "file": str(pdf), "size": pdf.stat().st_size, "sha256": _sha(pdf),
                    "folder": pdf.parent.name})
        report.append(f"{m['id']} '{m['title']}': whiteboard file {pdf.name} ({pdf.stat().st_size / 1e6:.1f} MB)")
    return out, report


def write(module):
    out, report = rows(module)
    f = ROOT / "modules" / module / "site" / "lesson_files.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), encoding="utf-8")
    return f, out, report


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for module in sorted({m["module"] for m in lectures.all_lectures()}):
        f, out, report = write(module)
        print(f"{module}: {len(out)} lesson file(s) -> {f}")
        print("\n".join("  " + r for r in report))

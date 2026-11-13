"""A doctor's OWN questions (owner, 2026-11-10): his own test is the only `required` set of his lessons, and his own MCQ
book is his `doctor` set; other doctors' questions never count as his (they stay `extra`).

    py own_questions.py elsamahy        file Elsamahy's QuizBot test ("quiz for all receptors") as Required

The MCQ book needs nothing here: `fast_lessons.py build` already points every keyed question of `modules/<m>/mcq/*.jsonl`
at handout lines inside that doctor's own lessons and files it under his doctor id.
The test's questions are not in the poll bank, so each goes to the lesson of the doctor whose handout lines it
matches best (IDF word overlap of the stem and the keyed answer, scores only: no text is read); a weak match goes to his
first lesson. Keys come only from the source: QuizBot's own correct flag. Safe to run again.
"""
import json
import sys
from pathlib import Path

import lectures
import page

ROOT = Path(__file__).resolve().parent
MODULE = "year2-cns"
DOCTORS = {
    "elsamahy": {"id": "dr-abdullah-el-samahi-phys", "book": "elsamahy-phys-mcq",
                 "quizbot": ROOT / "sources" / "quizbot" / "elsamahy" / "quizbot_questions.jsonl"},
    # Basel's two QuizBot tests (owner, 2026-11-12: "need separation and pointing so they work with the correct lectures")
    "basel": {"id": "dr-basel-sherif-hist", "book": "basel-hist-mcq",
              "quizbot": ROOT / "sources" / "quizbot" / "basel" / "quizbot_questions.jsonl"},
}


def write_rows(name, rows):
    return page.save_cover_file(name, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def script_homes(rows, doctor_id):
    """[lecture id per row]: the doctor's lesson whose handout lines (its ranges) the row matches best."""
    import math
    from collections import Counter
    import fast_lessons as F
    from flows.common import read_jsonl
    lines = [ln for ln in read_jsonl(ROOT / "modules" / MODULE / "lines.jsonl") if ln.get("text")]
    df = Counter()
    toks = {}
    for ln in lines:
        toks[ln["id"]] = set(F.words(ln["text"]))
        df.update(toks[ln["id"]])
    idf = {w: math.log(len(lines) / (1 + n)) for w, n in df.items()}
    mine = [m for m in sorted(lectures.all_lectures(MODULE), key=lambda m: m["id"])
            if m.get("kind", "lecture") == "lecture" and m.get("doctor") == doctor_id and m.get("ranges")]
    owner = {}
    for m in mine:
        for r in m["ranges"]:
            a, b = r["from"].split(":"), r["to"].split(":")
            pa, pb = int(a[2][1:]), int(b[2][1:])
            for ln in lines:
                if pa <= ln["page"] <= pb:
                    owner.setdefault(ln["id"], m["id"])
    out = []
    for r in rows:
        qw = Counter(F.words(r["question"]))
        if r.get("key") is not None:
            for w in F.words(r["options"][r["key"]]):
                qw[w] += 2
        best = (0.0, 0, None)
        for lid_line, lec in owner.items():
            hit = [w for w in qw if w in toks[lid_line]]
            sc = sum(idf.get(w, 0) for w in hit)
            if sc > best[0]:
                best = (sc, len(hit), lec)
        out.append(best[2] if best[0] >= F.MIN_SCORE and best[1] >= F.MIN_WORDS else mine[0]["id"])
    return out


def file_test(doctor_id, rows, tag):
    """Files the test's rows as Required, each into its script-chosen lesson; earlier filing of this test is redone."""
    import cover
    path = write_rows(f"own-{tag}.jsonl", rows)
    page.run_cover(path)
    sha = cover.covered(path)["sha"]
    homes = script_homes(rows, doctor_id)
    for m in lectures.all_lectures(MODULE):  # redo: drop this test's earlier rows from every lesson
        if any(it.get("file") == sha for it in m.get("required") or []):
            m["required"] = [it for it in m["required"] if it.get("file") != sha]
            lectures.save(m)
    report = [f"{tag}: {len(rows)} questions into required"]
    for lid in sorted(set(homes)):
        only = {i for i, h in enumerate(homes) if h == lid}
        res = page.file_into_lecture(lid, "required", path, only=only)
        report.append(f"   {lid} {len(only)}: " + res.splitlines()[-1])
    return report


def test_of(name):
    cfg = DOCTORS[name]
    quiz = [json.loads(x) for x in cfg["quizbot"].read_text(encoding="utf-8").splitlines() if x.strip()]
    rows = [{"question": r["question"], "options": r["options"], "key": r["correct_index"]} for r in quiz]
    return file_test(cfg["id"], rows, f"{name}-test")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for line in test_of(sys.argv[1]):
        print(line)

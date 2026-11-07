"""Hand-over intake: each new file in handover/ (written by the admin page) becomes pointer jobs, once."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HANDOVER = ROOT / "handover"
LETTERS = "ABCDE"


def batch_row(doc):
    """A site question as a pointer batch row (the worker never judges the key; it is context only)."""
    opts = doc.get("options") or {}
    keys = [k for k in LETTERS if isinstance(opts.get(k), dict)]
    key = doc.get("correct_option")
    return {"qid": str(doc["_id"]), "subject_hint": doc.get("subject_slug") or doc.get("moduleName"),
            "stem": doc.get("question_text") or "", "case_text": doc.get("case_text"),
            "options": [opts[k].get("text", "") for k in keys], "correct_index": keys.index(key) if key in keys else None,
            "set": doc.get("test_type"), "lesson": str(doc["lesson"]) if doc.get("lesson") else None}


def intake(reader, q, order, folder=HANDOVER):
    """Returns {file: jobs added}. A file is taken once (handover/done.txt)."""
    from bson import ObjectId
    import dm
    done_file = folder / "done.txt"
    done = set(done_file.read_text(encoding="utf-8").split()) if done_file.exists() else set()
    out = {}
    for f in sorted(folder.glob("*.json")) if folder.exists() else []:
        if f.name in done:
            continue
        h = json.loads(f.read_text(encoding="utf-8"))
        ids = [ObjectId(i) for i in h["questions"]]
        docs = []
        for n in range(0, len(ids), 400):
            docs += reader.find("questions", {"_id": {"$in": ids[n:n + 400]}},
                                {"question_text": 1, "options": 1, "correct_option": 1, "test_type": 1, "lesson": 1,
                                 "case_text": 1, "moduleName": 1, "book_found": 1}, limit=400)
        rows = [batch_row(d) for d in docs if "book_found" not in d]
        out[f.name] = q.add_jobs("pointers", dm.pointer_jobs(h["module"], rows, order)) if rows else 0
        with open(done_file, "a", encoding="utf-8") as w:
            w.write(f.name + "\n")
    return out

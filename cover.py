"""Coverage check: does a file of questions (a doctor's sheet, a past exam) already sit in our data?

1. Script, zero-lossy: every question whose word_key is in the bank or on the site is matched.
2. Fleet, for the rest: a `cover` job shows each left question beside a short list of candidates that share its rarer
   words (an index to read, never a choice); the worker answers the candidate's id or null. The checker accepts only a
   listed candidate.
3. The file is recorded as covered in bank/covered.jsonl with its percent matched, so it never needs review again.

Input file: JSONL, one question per line with `question` and `options` (any other fields are kept).
"""
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path

from checks import check_cover  # noqa: F401 (the checker lives with the others, for the worker kit)
from merge import read_jsonl, word_key

ROOT = Path(__file__).resolve().parent
BANK = ROOT / "bank"
SITE_KEYS = BANK / "site_keys.jsonl"
CANDIDATES = 5
WORD = re.compile(r"[^\W\d_]{4,}")


def site_index(reader, refresh=False):
    """word_key -> site question id, for every question on the site (cached in bank/site_keys.jsonl)."""
    if SITE_KEYS.exists() and not refresh:
        return {r["k"]: r["id"] for r in read_jsonl(SITE_KEYS)}
    BANK.mkdir(exist_ok=True)
    out, last = {}, None
    with open(SITE_KEYS, "w", encoding="utf-8") as f:
        while True:
            flt = {"_id": {"$gt": last}} if last else {}
            page = reader.find("questions", flt, {"question_text": 1, "options": 1}, limit=500, sort=[("_id", 1)])
            if not page:
                break
            for d in page:
                opts = [o.get("text", "") for o in (d.get("options") or {}).values() if isinstance(o, dict)]
                k = word_key(d.get("question_text") or "", opts)
                out.setdefault(k, str(d["_id"]))
                text = " | ".join([d.get("question_text") or "", *opts])
                f.write(json.dumps({"k": k, "id": str(d["_id"]), "t": text}, ensure_ascii=False) + "\n")
            last = page[-1]["_id"]
    return out


def bank_index():
    return {q["word_key"]: f"bank:{q['word_key'][:16]}" for q in read_jsonl(BANK / "questions.jsonl")}


def script_match(rows, index):
    return [index.get(word_key(r["question"], r.get("options") or [])) for r in rows]


def words(text):
    return {w.lower() for w in WORD.findall(text or "")}


def candidates(row, pool, df, n=CANDIDATES):
    """Pool entries that share the most of the row's rarer words. An index for the reader, never the match."""
    mine = words(row["question"] + " " + " ".join(row.get("options") or []))
    scored = sorted(((sum(1 / df[w] for w in mine & p["words"]), p["id"]) for p in pool if mine & p["words"]), reverse=True)
    return [pid for _, pid in scored[:n]]


def record(file, rows, matches):
    BANK.mkdir(exist_ok=True)
    sha = hashlib.sha256(Path(file).read_bytes()).hexdigest()[:12]
    matched = sum(m is not None for m in matches)
    entry = {"file": str(file), "sha": sha, "questions": len(rows), "matched": matched,
             "percent": round(100 * matched / len(rows), 1) if rows else 100.0, "at": time.strftime("%Y-%m-%d %H:%M")}
    with open(BANK / "covered.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    with open(BANK / f"cover_{sha}.jsonl", "w", encoding="utf-8") as f:
        for r, m in zip(rows, matches):
            f.write(json.dumps({**r, "match": m}, ensure_ascii=False) + "\n")
    return entry


def covered(file):
    sha = hashlib.sha256(Path(file).read_bytes()).hexdigest()[:12]
    return next((e for e in read_jsonl(BANK / "covered.jsonl") if e["sha"] == sha), None)


def pool_of(site_rows):
    """[{id, words, text}] for candidate finding, with document frequencies."""
    pool = [{"id": r["id"], "words": words(r["text"]), "text": r["text"]} for r in site_rows]
    df = Counter(w for p in pool for w in p["words"])
    return pool, df

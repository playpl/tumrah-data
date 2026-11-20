"""Transcript consistency check: 20 random pieces of Gemini-heard CNS lectures heard again, then compared.
Run from tumrah-data:  py <this> run   then   py <this> report
"""
import json
import random
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(r"C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data")
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).with_name("rehear")
sys.stdout.reconfigure(encoding="utf-8")


def pick(n=20, seed=20261121):
    pool = []
    for d in sorted((ROOT / "lectures").glob("cns-*")):
        m = json.loads((d / "lecture.json").read_text(encoding="utf-8"))
        if (m.get("source") or {}).get("transcript") == "youtube" or not (d / "raw.txt").exists():
            continue
        for p in sorted((d / "pieces").glob("c*.ogg")):
            if p.with_suffix(".txt").exists() and p.with_suffix(".txt").stat().st_size > 500:
                pool.append(p)
    rng = random.Random(seed)
    lecs = sorted({p.parent.parent.name for p in pool})
    chosen = []
    for lid in rng.sample(lecs, min(n, len(lecs))):             # one piece per lecture: spread over doctors
        chosen.append(rng.choice([p for p in pool if p.parent.parent.name == lid]))
    return chosen


def one(p):
    import gemini_run
    import lectures
    key = f"{p.parent.parent.name}_{p.stem}"
    d = OUT / key
    d.mkdir(parents=True, exist_ok=True)
    if (d / "new.txt").exists():
        return key, "kept"
    shutil.copy(p, d / p.name)
    shutil.copy(p.with_suffix(".txt"), d / "old.txt")
    (d / "prompt.txt").write_text(gemini_run.PIECE_PROMPT, encoding="utf-8")
    secs = lectures.duration(d / p.name)
    import gemini_browser
    answer, meta = gemini_browser.ask(gemini_run.PIECE_PROMPT, "hydrogen", [d / p.name], wait=900)
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    if answer is None:
        return key, f"failed: {meta.get('error')}"
    (d / "new.txt").write_text(gemini_run.piece_text(answer, secs), encoding="utf-8")
    return key, f"ok {meta.get('account')} {meta.get('model')}"


def run():
    OUT.mkdir(exist_ok=True)
    ps = pick()
    print(len(ps), "pieces:", " ".join(f"{p.parent.parent.name}/{p.stem}" for p in ps), flush=True)
    with ThreadPoolExecutor(3) as ex:
        for key, res in ex.map(one, ps):
            print(key, res, flush=True)


def norm(t):
    t = re.sub(r"\[\d+:\d+(?::\d+)?\]", " ", t)
    t = re.sub(r"\[cite[^\]]*\]", " ", t)
    t = re.sub(r"[ًٌٍَُِّْـ]", "", t)                          # Arabic diacritics, tatweel
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return t.split()


def report():
    rows = []
    for d in sorted(OUT.glob("*")):
        if not (d / "new.txt").exists():
            continue
        a, b = norm((d / "old.txt").read_text(encoding="utf-8")), norm((d / "new.txt").read_text(encoding="utf-8"))
        sm = SequenceMatcher(None, a, b, autojunk=False)
        lat_a = {w for w in a if re.fullmatch(r"[a-z]{4,}", w)}
        lat_b = {w for w in b if re.fullmatch(r"[a-z]{4,}", w)}
        terms = len(lat_a & lat_b) / max(1, len(lat_a | lat_b))
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        rows.append((d.name, len(a), len(b), sm.ratio(), terms, meta.get("model")))
    for r in rows:
        print(f"{r[0]:<16} words old {r[1]:>5} new {r[2]:>5}  word agreement {r[3]:.0%}  English terms shared {r[4]:.0%}  {r[5]}")
    if rows:
        import statistics
        print(f"{len(rows)} pieces: word agreement median {statistics.median(r[3] for r in rows):.0%}, "
              f"min {min(r[3] for r in rows):.0%}; terms shared median {statistics.median(r[4] for r in rows):.0%}")


if __name__ == "__main__":
    {"run": run, "report": report}[sys.argv[1]]()

import re, random, json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data")
ACC = "001 002 003 004 005 006 007 008 010 013 014 015 017 018 019 020 021 022 023 024 027 036 038 040 045".split()
rng = random.Random(20261120)
LINE = re.compile(r"^P(\d+)(?:-P(\d+))?\s*=\s*(.+)$")
def amap(txt):
    m = {}
    for ln in txt.splitlines():
        g = LINE.match(ln.strip())
        if g:
            a, b = int(g[1]), int(g[2] or g[1])
            for p in range(a, b + 1): m[p] = g[3].strip()
    return m
def blines(spec):
    out = []
    for part in re.findall(r"B(\d+)(?:-B(\d+))?", spec):
        a, b = int(part[0]), int(part[1] or part[0])
        out += list(range(a, b + 1))
    return out
rows = []
for n in ACC:
    d = ROOT / "jobs" / "sp_seg" / f"cns-{n}"
    task = (d / "A" / "task.txt").read_text(encoding="utf-8")
    P = {int(k): v for k, v in re.findall(r"^P(\d+) (.*)$", task, re.M)}
    B = {int(k): v for k, v in re.findall(r"^B(\d+) (.*)$", task, re.M)}
    A = amap((d / "A" / "answer.txt").read_text(encoding="utf-8"))
    Bm = amap((d / "B" / "answer.txt").read_text(encoding="utf-8")) if (d / "B" / "answer.txt").exists() else {}
    for p in rng.sample(sorted(A), 2):
        rows.append({"lec": f"cns-{n}", "p": p, "A": A[p], "B": Bm.get(p)})
        print(f"### {len(rows)}. cns-{n} P{p}  A: {A[p]}  | B: {Bm.get(p)}")
        print("  P-1:", P.get(p - 1, "")[:160])
        print("  P  :", P.get(p, "")[:600])
        for b in blines(A[p])[:4]:
            print(f"  B{b}:", B.get(b, "?")[:260])
        if A[p] == "NONE":
            print("  (book slice starts:", B.get(min(B))[:80], ")")
json.dump(rows, open(Path(__file__).with_name("seg_sample.json"), "w"), ensure_ascii=False, indent=1)

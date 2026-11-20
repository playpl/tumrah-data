import re, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data")
HOLE = re.compile(r"(?:^|\s)ال(?:\s+(?=[ء-ي])|\s*[،.؟?,]|\s*$)", re.M)   # bare article before Arabic or punctuation: the term was dropped
CITE = re.compile(r"\[cite[^\]]*\]")
LAT = re.compile(r"[A-Za-z]{3,}")
rows = []
files = list((ROOT / "lectures").glob("*/raw.txt")) + list((ROOT / "modules").glob("*/records/*/raw.txt"))
for f in files:
    t = f.read_text(encoding="utf-8", errors="replace")
    words = max(1, len(t.split()))
    src = "youtube" if "records" in f.parts and (f.parent / "raw.txt").exists() and "yt" in str(f.parent) else ""
    rows.append((f.parent.name, words, len(HOLE.findall(t)) * 1000 / words, len(CITE.findall(t)), len(LAT.findall(t)) * 100 / words))
rows.sort(key=lambda r: -r[2])
print(f"{len(rows)} transcripts; holes per 1000 words (bare 'ال'), cite tags, % Latin words")
bad = [r for r in rows if r[2] >= 5]
print("holes >= 5/1000:", len(bad), "| any cite tag:", sum(r[3] > 0 for r in rows))
for r in rows[:25]:
    print(f"  {r[0]:<22} words {r[1]:>6}  holes {r[2]:5.1f}  cite {r[3]:>3}  latin {r[4]:4.1f}%")
import statistics
print("median holes", statistics.median(r[2] for r in rows))

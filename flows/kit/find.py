"""Lists every handout page that holds a phrase, in page order. It helps a reader FIND pages to read (like a
book's index); it never ranks or chooses. Read the pages and decide yourself.

    python tools/find.py "Herring bodies"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handout import pages  # noqa: E402

if len(sys.argv) != 2:
    sys.exit(__doc__)
sys.stdout.reconfigure(encoding="utf-8")
want = " ".join(sys.argv[1].split()).lower()
hits = [p for p, (_, rows) in sorted(pages().items()) if want in " ".join(" ".join(rows).split()).lower()]
print(f'"{sys.argv[1]}" is on pdf pages: {hits if hits else "none"}')

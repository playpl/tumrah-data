"""Prints handout pages, line by line, so a reader can read them.

    python tools/page.py 57          # one page
    python tools/page.py 57 59       # pages 57 to 59
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handout import pages  # noqa: E402

if len(sys.argv) not in (2, 3):
    sys.exit(__doc__)
sys.stdout.reconfigure(encoding="utf-8")
first = int(sys.argv[1])
last = int(sys.argv[2]) if len(sys.argv) == 3 else first
for p, (printed, rows) in sorted(pages().items()):
    if first <= p <= last:
        print(f"===== pdf_page {p} (printed page {printed}) =====")
        print("\n".join(rows))

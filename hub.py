"""The hub: every handout line and figure gets a stable ID.

ID: "<module>:<hash8>:p<pdf page>:l<n>" for text rows, ":f<n>" for figures.
The hash is the handout file's sha256, so a new handout file gives new IDs and
the same file always gives the same IDs. Pointers, doctor book blocks and
lecture parts store these IDs; two items are linked when they share one.
"""
import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path


MIN_FIGURE_AREA = 2000      # pt^2; smaller images are icons and bullets
CAPTION_GAP = 30            # pt between a figure and the text row that names it
PAGE_NUMBER_BAND = 0.12     # top/bottom share of the page where a bare number is the printed page


@dataclass
class Line:
    id: str
    module: str
    hash: str
    page: int               # pdf page, 1-based
    printed: int | None     # page number printed on the page
    n: int
    text: str
    figure: str | None      # None for text rows; nearby text for figures, "page" for a page with no text
    bbox: list


def line_id(module, handout_hash, page, n, figure=False):
    return f"{module}:{handout_hash}:p{page}:{'f' if figure else 'l'}{n}"


def word_key(text):
    """Letters, marks and digits only, lowercased (as `words` in importSfQuestions.ts, without numbering)."""
    return "".join(ch for ch in (text or "").lower() if unicodedata.category(ch)[0] in "LMN")


def file_hash(pdf):
    return hashlib.sha256(Path(pdf).read_bytes()).hexdigest()[:8]


def _rows(page):
    """Visual rows: a bullet glyph and its text, or the cells of a table row, become one line.

    ponytail: rows span the full page width, so a two-column page would interleave its columns;
    the handouts seen are single-column. Split by column when one shows up.
    """
    raw = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for ln in block["lines"]:
            text = "".join(sp["text"] for sp in ln["spans"])
            if text.strip():
                raw.append((ln["bbox"], text))
    raw.sort(key=lambda r: (round(r[0][1], 1), r[0][0]))
    rows = []
    for bbox, text in raw:
        if rows:
            band = rows[-1]["band"]
            overlap = min(band[3], bbox[3]) - max(band[1], bbox[1])
            if overlap >= 0.5 * min(band[3] - band[1], bbox[3] - bbox[1]):
                rows[-1]["parts"].append((bbox, text))
                continue
        rows.append({"band": bbox, "parts": [(bbox, text)]})
    out = []
    for row in rows:
        parts = sorted(row["parts"], key=lambda p: p[0][0])
        box = [min(p[0][0] for p in parts), min(p[0][1] for p in parts),
               max(p[0][2] for p in parts), max(p[0][3] for p in parts)]
        out.append((box, " ".join(" ".join(t.split()) for _, t in parts)))
    return out


def _figures(page):
    figs = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] == 1:
            x0, y0, x1, y1 = block["bbox"]
            if (x1 - x0) * (y1 - y0) >= MIN_FIGURE_AREA:
                figs.append(list(block["bbox"]))
    return figs


def _caption(fig, rows):
    below = [(r[0][1] - fig[3], t) for r in rows for t in [r[1]] if 0 <= r[0][1] - fig[3] <= CAPTION_GAP]
    above = [(fig[1] - r[0][3], t) for r in rows for t in [r[1]] if 0 <= fig[1] - r[0][3] <= CAPTION_GAP]
    near = sorted(below) or sorted(above)
    return near[0][1] if near else ""


def split_handout(pdf, module):
    import fitz  # only here: fleet workers import this file for word_key and resolve_span without PyMuPDF
    h = file_hash(pdf)
    out = []
    with fitz.open(pdf) as doc:
        for i, page in enumerate(doc, start=1):
            height = page.rect.height
            rows, printed = [], None
            for box, text in _rows(page):
                edge = box[1] > (1 - PAGE_NUMBER_BAND) * height or box[3] < PAGE_NUMBER_BAND * height
                if edge and text.strip().isdigit() and printed is None:
                    printed = int(text.strip())
                else:
                    rows.append((box, text))
            items = [(box[1], "l", box, text, None) for box, text in rows]
            items += [(fig[1], "f", fig, "", _caption(fig, rows)) for fig in _figures(page)]
            if not items:
                items = [(0, "f", [0, 0, page.rect.width, height], "", "page")]
            items.sort(key=lambda it: (it[0], it[2][0]))
            count = {"l": 0, "f": 0}
            for _, kind, box, text, fig in items:
                count[kind] += 1
                out.append(Line(line_id(module, h, i, count[kind], kind == "f"), module, h, i, printed,
                                count[kind], text, fig, [round(v, 1) for v in box]))
    return out


def resolve_span(lines, pdf_page, text, figure=None):
    """Line IDs a pointer span covers on one pdf page; [] when it is not there.

    Text spans match on word_key, so spacing, punctuation and line breaks do not matter.
    A "FIGURE" span matches a figure by its nearby text, or the page's only figure.
    """
    on_page = [ln for ln in lines if ln.page == pdf_page]
    if text == "FIGURE":
        figs = [ln for ln in on_page if ln.figure is not None]
        want = word_key(figure)
        hits = [f for f in figs if word_key(f.figure) and want and
                (word_key(f.figure) in want or want in word_key(f.figure))]
        if len(hits) == 1:
            return [hits[0].id]
        return [figs[0].id] if not hits and len(figs) == 1 else []
    target = word_key(text)
    if not target:
        return []
    joined, spans = "", []
    for ln in on_page:
        if ln.figure is None:
            key = word_key(ln.text)
            spans.append((len(joined), len(joined) + len(key), ln.id))
            joined += key
    start = joined.find(target)
    if start < 0:
        return []
    end = start + len(target)
    return [lid for a, b, lid in spans if a < end and b > start]


def write_lines(lines, path):
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps(asdict(ln), ensure_ascii=False) + "\n")

"""IDs of the graph. One place builds them and one place reads them.

    handout row       year2-cns:d30dcde2:p60:l5        (hub.line_id; the site's contract, never changed)
    handout figure    year2-cns:d30dcde2:p60:f1        (the figure row itself is the unit)
    handout sentence  year2-cns:d30dcde2:p60:s5        module : handout sha8 : page of its first row : first row number
                      year2-cns:d30dcde2:p60:s5a / s5b when one row holds two sentences
    book sentence     bk:mossafer-anat-full:6f2a91c0:p12:s3
    Tumrah book       tb:year2-cns/anatomy/c1/spinal-cord:s3fa9c1   (content addressed: survives an HTML rebuild)

A sentence ID is anchored to its first row, so a changed join rule moves only the sentences it touches.
"""
import hashlib
import re

from hub import word_key

_TAIL = re.compile(r"^p(\d+):([slf])(\d+)([a-z]?)$")


def line_id(module, sha8, page, n, figure=False):
    return f"{module}:{sha8}:p{page}:{'f' if figure else 'l'}{n}"


def sent_id(module, sha8, page, n, sub=""):
    return f"{module}:{sha8}:p{page}:s{n}{sub}"


def book_sent_id(book, sha8, page, n, sub=""):
    return f"bk:{book}:{sha8}:p{page}:s{n}{sub}"


def tumrah_sent_id(path, text):
    """path = <module>/<subject>/<chapter>/<lesson dir>. The same words give the same ID."""
    return f"tb:{path}:s{hashlib.sha256(word_key(text).encode('utf-8')).hexdigest()[:6]}"


def parse(id_):
    """{"space": handout|book|tumrah, "module"|"book"|"path", "sha8", "page", "kind": s|l|f, "n", "sub"}.

    Raises ValueError on anything else, so a bad ID never travels silently.
    """
    parts = id_.split(":")
    if parts[0] == "tb" and len(parts) == 3 and re.fullmatch(r"s[0-9a-f]{6}", parts[2]):
        return {"space": "tumrah", "path": parts[1], "hash": parts[2][1:]}
    if parts[0] == "bk" and len(parts) == 5:
        space, owner, sha8, tail = "book", {"book": parts[1]}, parts[2], ":".join(parts[3:])
    elif len(parts) == 4:
        space, owner, sha8, tail = "handout", {"module": parts[0]}, parts[1], ":".join(parts[2:])
    else:
        raise ValueError(f"not a spine id: {id_!r}")
    m = _TAIL.match(tail)
    if not m or (m.group(4) and m.group(2) != "s"):
        raise ValueError(f"not a spine id: {id_!r}")
    return {"space": space, **owner, "sha8": sha8, "page": int(m.group(1)), "kind": m.group(2),
            "n": int(m.group(3)), "sub": m.group(4)}


def is_sentence(id_):
    try:
        p = parse(id_)
    except ValueError:
        return False
    return p["space"] == "tumrah" or p["kind"] in "sf"


def first_row(id_):
    """The handout row a handout sentence starts on (its anchor)."""
    p = parse(id_)
    if p["space"] != "handout":
        raise ValueError(f"not a handout id: {id_!r}")
    return line_id(p["module"], p["sha8"], p["page"], p["n"], figure=p["kind"] == "f")


def order_key(id_):
    """Sort key in document order for handout and book IDs."""
    p = parse(id_)
    return (p.get("module") or p.get("book") or p.get("path"), p.get("page", 0), p.get("n", 0),
            p.get("kind", "") == "f", p.get("sub", ""))


def short(id_):
    """`p60:s5`: for reports and logs, never stored."""
    return ":".join(id_.split(":")[-2:])

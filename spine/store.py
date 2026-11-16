"""spine/graph.db: a SQLite index over the record files. Delete it and `py -m spine store rebuild` brings it back.

Owner answers never live here: `ledger.db` stays their only home.
"""
import json
import sqlite3
from pathlib import Path

from spine import ROOT, now, read_jsonl

DB = Path(__file__).resolve().parent / "graph.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, kind TEXT, module TEXT, parent TEXT, ord INTEGER,
                                 text TEXT, meta TEXT);
CREATE INDEX IF NOT EXISTS nodes_parent ON nodes(parent, ord);
CREATE TABLE IF NOT EXISTS rows(sent_id TEXT, line_id TEXT, PRIMARY KEY(sent_id, line_id));
CREATE INDEX IF NOT EXISTS rows_line ON rows(line_id);
CREATE TABLE IF NOT EXISTS edges(src TEXT, dst TEXT, rel TEXT, grp INTEGER, conf REAL, by TEXT, state TEXT, at TEXT,
                                 PRIMARY KEY(src, dst));
CREATE INDEX IF NOT EXISTS edges_dst ON edges(dst);
CREATE TABLE IF NOT EXISTS votes(src TEXT, reader TEXT, answer TEXT, at TEXT, PRIMARY KEY(src, reader));
CREATE TABLE IF NOT EXISTS records(channel TEXT, post INTEGER, lecture_id TEXT, state TEXT, detail TEXT, at TEXT,
                                   PRIMARY KEY(channel, post));
CREATE TABLE IF NOT EXISTS mother(list_id TEXT, sha TEXT, edit_date TEXT, map TEXT, at TEXT,
                                  PRIMARY KEY(list_id, sha));
"""


def connect(path=None, readonly=False):
    path = Path(path or DB)
    if readonly:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    else:
        con = sqlite3.connect(path)
        con.executescript(SCHEMA)
    con.row_factory = sqlite3.Row
    return con


def put_sentences(con, module, sentences, parent_kind="handout"):
    """Handout or book sentences into nodes (+ rows for handout sentences). `parent` = lesson or book."""
    for s in sentences:
        meta = {k: s[k] for k in ("marker", "section", "ctx", "splitter", "page") if k in s}
        con.execute("INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?)",
                    (s["id"], f"{parent_kind}:{s.get('kind', 'fact')}", module, s.get("lesson") or s.get("book"),
                     s.get("i"), s.get("text", ""), json.dumps(meta, ensure_ascii=False)))
        for line in s.get("rows", []):
            con.execute("INSERT OR REPLACE INTO rows VALUES (?,?)", (s["id"], line))


def put_edge(con, src, dst, rel, conf, by, state="accepted", grp=0, at=None):
    con.execute("INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?,?,?)",
                (src, dst, rel, grp, conf, by, state, at or now()))


def edges(con, src=None, dst=None, state=None):
    q, args = "SELECT * FROM edges WHERE 1=1", []
    for col, val in (("src", src), ("dst", dst), ("state", state)):
        if val is not None:
            q += f" AND {col}=?"
            args.append(val)
    return [dict(r) for r in con.execute(q, args)]


def put_vote(con, src, reader, answer, at=None):
    con.execute("INSERT OR REPLACE INTO votes VALUES (?,?,?,?)",
                (src, reader, json.dumps(answer, ensure_ascii=False), at or now()))


def votes(con, src):
    return {r["reader"]: json.loads(r["answer"]) for r in con.execute("SELECT * FROM votes WHERE src=?", (src,))}


def line_ids(con, sent_ids):
    """Handout row IDs of these sentences, in order, no repeats: the site's contract."""
    out, seen = [], set()
    for sid in sent_ids:
        for r in con.execute("SELECT line_id FROM rows WHERE sent_id=? ORDER BY rowid", (sid,)):
            if r[0] not in seen:
                seen.add(r[0])
                out.append(r[0])
    return out


def sentences_of_line(con, line_id):
    return [r[0] for r in con.execute("SELECT sent_id FROM rows WHERE line_id=?", (line_id,))]


def cross(con, sentence_id):
    """Sentences of other books that share a handout sentence with this one. Computed, never stored."""
    q = """SELECT DISTINCT b.src FROM edges a JOIN edges b ON a.dst=b.dst
           WHERE a.src=? AND b.src<>? AND a.state='accepted' AND b.state='accepted'"""
    return [r[0] for r in con.execute(q, (sentence_id, sentence_id))]


def rebuild(path=None):
    """Drop the index and load every record file again. Returns the row counts."""
    path = Path(path or DB)
    for f in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        if f.exists():
            f.unlink()
    con = connect(path)
    for mdir in sorted((ROOT / "modules").glob("*/graph")):
        module = mdir.parent.name
        put_sentences(con, module, read_jsonl(mdir / "sentences.jsonl"))
        for f in sorted(mdir.glob("books/*.sentences.jsonl")):
            put_sentences(con, module, read_jsonl(f), parent_kind="book")
        for f in sorted(mdir.glob("edges/*.jsonl")):
            for e in read_jsonl(f):
                put_edge(con, e["src"], e["dst"], e.get("rel"), e.get("conf"), e.get("by"),
                         e.get("state", "accepted"), e.get("grp", 0), e.get("at"))
        for f in sorted(mdir.glob("votes/*.jsonl")):
            for v in read_jsonl(f):
                put_vote(con, v["src"], v["reader"], v["answer"], v.get("at"))
        for r in read_jsonl(mdir / "records.jsonl"):
            con.execute("INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?)",
                        (r["channel"], r["post"], r.get("lecture_id"), r.get("state"),
                         json.dumps(r.get("detail"), ensure_ascii=False), r.get("at")))
    con.commit()
    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("nodes", "rows", "edges", "votes", "records", "mother")}
    con.close()
    return counts


def status(path=None):
    path = Path(path or DB)
    if not path.exists():
        return None
    con = connect(path, readonly=True)
    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
              for t in ("nodes", "rows", "edges", "votes", "records", "mother")}
    con.close()
    return counts


def register(sub):
    p = sub.add_parser("store", help="the graph.db index").add_subparsers(dest="store_cmd")
    p.add_parser("rebuild", help="drop graph.db and load every record file").set_defaults(
        run=lambda a: print("graph.db rebuilt:", rebuild()))
    p.add_parser("status", help="row counts").set_defaults(
        run=lambda a: print("graph.db:", status() or "not built (py -m spine store rebuild)"))

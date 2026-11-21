"""One university's handout onto another's (owner, 2026-11-21, ZNU sources: "It's the same").

ZNU year 1 uses the same doctors, lectures and polls as ZU, on its own handout. The two handouts share most of their
text, so code maps every ZU handout sentence to the ZNU sentence that says the same thing, and the ZU lessons'
handout ranges and the questions' handout pointers are carried over through that map. No reader is needed.

    py -m spine graph twin nu-year1-musculoskeletal --from year1-musculoskeletal

Tiers (both strictly one to one):
    T1  the same words (normalised tokens, 3 or more), the key unique on both sides
    T2  content-word Jaccard >= 0.8, best match clear of the second best by 0.1
Then the order check: a match far from the longest in-order chain (more than JUMP sentences from where its
neighbours put it) is dropped, so a repeated sentence never lands in another chapter.

Writes (modules/<dst>/):
    graph/twin.<src>.jsonl     {"src", "dst", "tier", "score"}
    site/lessons.jsonl         the src lessons with ranges on the dst handout ("twinOf": the src module)
    site/points.json           {source_id: {"lecture_id": dst lesson, "lines": [dst line ids], "from": src lesson}}
                               for every src question pointer (live ones in msk_points.json, waiting ones in
                               msk_waiting.jsonl)
"""
import json
from bisect import bisect_left
from collections import Counter, defaultdict

from spine import graph_dir, module_dir, read_jsonl, write_json, write_jsonl
from spine import text as T

KINDS = ("fact", "table_row", "heading")
JACCARD, MARGIN, JUMP, GAP = 0.8, 0.1, 40, 15


def sentences(module):
    return read_jsonl(graph_dir(module) / "sentences.jsonl")


def _key(s):
    return " ".join(T.tokens(s["text"]))


def match(src, dst):
    """{src sentence id: (dst sentence id, tier, score)} for the sentences of src that dst also says."""
    A = [s for s in src if s["kind"] in KINDS and s.get("lesson")]
    B = [s for s in dst if s["kind"] in KINDS and s.get("lesson")]
    ka, kb = Counter(_key(s) for s in A), Counter(_key(s) for s in B)
    by_key = {_key(s): s for s in B}
    out, used = {}, set()
    for s in A:
        k = _key(s)
        if len(k.split()) >= 3 and ka[k] == 1 and kb[k] == 1:
            out[s["id"]] = (by_key[k]["id"], "T1", 1.0)
            used.add(by_key[k]["id"])
    bset = [set(T.content(s["text"])) for s in B]
    index = defaultdict(set)
    for i, words in enumerate(bset):
        for w in words:
            index[w].add(i)
    claims = defaultdict(list)                      # dst index -> [(score, src id)]
    for s in A:
        if s["id"] in out:
            continue
        a = set(T.content(s["text"]))
        if len(a) < 3:
            continue
        hits = Counter()
        for w in a:
            if len(index.get(w, ())) <= 200:        # a word on every page says nothing
                hits.update(index.get(w, ()))
        scored = sorted(((n / len(a | bset[i]), i) for i, n in hits.items() if B[i]["id"] not in used), reverse=True)
        if not scored or scored[0][0] < JACCARD:
            continue
        if len(scored) > 1 and scored[0][0] - scored[1][0] < MARGIN:
            continue
        claims[scored[0][1]].append((scored[0][0], s["id"]))
    for i, cl in claims.items():
        if len(cl) == 1:
            out[cl[0][1]] = (B[i]["id"], "T2", round(cl[0][0], 3))
    return in_order(out, src, dst)


def in_order(m, src, dst):
    """Drops the matches more than JUMP dst sentences away from the longest in-order chain of matches."""
    si = {s["id"]: s["i"] for s in src}
    di = {s["id"]: s["i"] for s in dst}
    pairs = sorted((si[a], di[b], a) for a, (b, _, _) in m.items())
    tails, prev, idx = [], [None] * len(pairs), []          # longest increasing subsequence on the dst index
    for n, (_, d, _) in enumerate(pairs):
        k = bisect_left(tails, d)
        if k == len(tails):
            tails.append(d)
            idx.append(n)
        else:
            tails[k], idx[k] = d, n
        prev[n] = idx[k - 1] if k else None
    chain, n = [], idx[-1] if idx else None
    while n is not None:
        chain.append(n)
        n = prev[n]
    chain = sorted(chain)
    keep = {}
    cs = [pairs[c][0] for c in chain]
    for s_i, d_i, a in pairs:
        k = bisect_left(cs, s_i)
        near = [pairs[chain[j]][1] for j in (k - 1, k) if 0 <= j < len(chain)]
        if not near or min(abs(d_i - x) for x in near) <= JUMP:
            keep[a] = m[a]
    return keep


def _row_index(sents):
    return {r: s for s in sents for r in s["rows"]}


def carry_range(frm, to, src, dst, m):
    """The src handout range (line ids) as dst ranges: runs of the dst sentences its sentences map to."""
    rows = _row_index(src)
    a, b = rows.get(frm), rows.get(to)
    if not a or not b:
        return []
    dpos = {s["id"]: s for s in dst}
    got = sorted({dpos[m[s["id"]][0]]["i"] for s in src[a["i"]:b["i"] + 1] if s["id"] in m})
    if not got:
        return []
    by_i = {s["i"]: s for s in dst}
    runs, start = [], got[0]
    for x, y in zip(got, got[1:] + [None]):
        if y is None or y - x > GAP:
            runs.append((start, x))
            start = y
    return [{"from": by_i[p]["rows"][0], "to": by_i[q]["rows"][-1]} for p, q in runs if q > p or len(got) == 1]


def carry_lines(lines, src, dst, m):
    """Pointer line ids on src -> (dst line ids, dst lesson)."""
    rows, dpos = _row_index(src), {s["id"]: s for s in dst}
    out, lessons = [], Counter()
    for near in (0, 1, 2):            # a line dst words differently: its nearest mapped neighbour in the same lesson
        for ln in lines:
            s = rows.get(ln)
            if not s:
                continue
            for j in sorted({s["i"] - near, s["i"] + near}):
                n = src[j] if 0 <= j < len(src) else None
                if n and n.get("lesson") == s.get("lesson") and n["id"] in m:
                    d = dpos[m[n["id"]][0]]
                    out += [r for r in d["rows"] if r not in out]
                    lessons[d["lesson"]] += 1
                    break
        if out:
            break
    return out, (lessons.most_common(1)[0][0] if lessons else None)


def run(dst_module, src_module):
    src, dst = sentences(src_module), sentences(dst_module)
    m = match(src, dst)
    write_jsonl(graph_dir(dst_module) / f"twin.{src_module}.jsonl",
                [{"src": a, "dst": b, "tier": t, "score": sc} for a, (b, t, sc) in m.items()])
    content = [s for s in src if s["kind"] in KINDS and s.get("lesson")]
    report = [f"{len(m)} of {len(content)} {src_module} sentences found on {dst_module} "
              f"(T1 {sum(1 for v in m.values() if v[1] == 'T1')}, T2 {sum(1 for v in m.values() if v[1] == 'T2')})"]
    per = defaultdict(Counter)
    dl = {s["id"]: s["lesson"] for s in dst}
    for s in content:
        if s["id"] in m:
            per[s["lesson"]][dl[m[s["id"]][0]]] += 1
    for les in sorted({s["lesson"] for s in content}):
        n = sum(1 for s in content if s["lesson"] == les)
        hit = sum(per[les].values())
        top = ", ".join(f"{k.split(':')[-1]} {v}" for k, v in per[les].most_common(2))
        report.append(f"  {les.split(':')[-1]}: {hit}/{n} -> {top or 'nothing'}")
    site_in, site_out = module_dir(src_module) / "site", module_dir(dst_module) / "site"
    site_out.mkdir(parents=True, exist_ok=True)
    lessons, empty = [], []
    for row in read_jsonl(site_in / "lessons.jsonl"):
        ranges = [r for x in row.get("ranges") or [] for r in carry_range(x["from"], x["to"], src, dst, m)]
        if row.get("ranges") and not ranges:
            empty.append(row["key"])
        lessons.append(dict(row, ranges=ranges, twinOf=src_module))
    write_jsonl(site_out / "lessons.jsonl", lessons)
    report.append(f"{len(lessons)} lessons carried; no {dst_module} range: {len(empty)}"
                  + (f" ({', '.join(empty)})" if empty else ""))
    points, lost = {}, 0
    live = json.loads((site_in / "msk_points.json").read_text(encoding="utf-8")) if (site_in / "msk_points.json").exists() else {}
    waiting = {r["source_id"]: {"lines": r["lines"], "lecture_id": None} for r in read_jsonl(site_in / "msk_waiting.jsonl")
               if r.get("lines")} if (site_in / "msk_waiting.jsonl").exists() else {}
    for qid, p in {**waiting, **live}.items():
        lines, les = carry_lines(p["lines"], src, dst, m)
        if lines:
            points[qid] = {"lecture_id": les, "lines": lines, "from": p.get("lecture_id"),
                           "waiting": qid not in live}
        else:
            lost += 1
    write_json(site_out / "points.json", points)
    report.append(f"{len(points)} question pointers carried ({sum(1 for p in points.values() if p['waiting'])} of "
                  f"them waiting on {src_module}); {lost} not found on {dst_module}")
    return report


def add(p):
    t = p.add_parser("twin", help="another university's handout: sentences, lessons and pointers carried over")
    t.add_argument("module", help="the handout to carry onto (nu-year1-musculoskeletal)")
    t.add_argument("--from", dest="src", required=True, help="the module it shares its sources with")
    t.set_defaults(run=lambda a: print("\n".join(run(a.module, a.src))))

"""Phase 1, the part with no LLM: scope a book page to handout lessons, accept what code can prove, and list
the few handout sentences a reader must choose from for the rest.

Tiers (docs/spine/DESIGN_agent.md section C, measured on the old links):
  A1  the sentence's letters (word_key, 20 or more) are found exactly once in the whole handout
  A2  found several times, but exactly once inside the page's lesson scope
  A3  fuzzy match >= 90 with the BM25 top-1 sentence of the scope, lying between two A1/A2 anchors
  A4  under 20 letters, exact, and the hit lies between the targets of its resolved neighbours (gap <= 3)
An item is a dict {"text", "scope": [lesson ids]}; items are in book order. Targets are positions in `Handout.sents`.
"""
import bisect
import math
from collections import Counter

from rapidfuzz import fuzz

from spine import text as T
from spine.align.bm25 import Index
from spine.graph import handout as handout_graph, tree

LONG = 20               # letters; below this an exact match proves nothing on its own
FUZZY = 90
NEAR = 3                # sentences of slack around anchors and neighbours
TOP_K, WIDE_K, CAP, CORRIDOR = 8, 3, 80, 60
CHANGE, BACK = 0.25, 0.5      # page scope: cost of changing lesson between pages, extra cost of going back
MARGIN = 0.2


class Handout:
    """The handout's sentences (headings, facts, table rows inside a lesson) with the indexes matching needs."""

    def __init__(self, module, sentences=None, lessons=None):
        sents = handout_graph.load(module) if sentences is None else sentences
        self.sents = [s for s in sents if s["kind"] != "figure" and s.get("lesson") and s["text"].strip()]
        self.pos = {s["id"]: n for n, s in enumerate(self.sents)}
        self.lesson = [s["lesson"] for s in self.sents]
        self.keys = [T.word_key(s["text"]) for s in self.sents]
        self.starts, self.joined = [], ""
        for k in self.keys:
            self.starts.append(len(self.joined))
            self.joined += k
        self.norm = [" ".join(T.tokens(s["text"])) for s in self.sents]
        self.index = Index([(T.content(s["text"]), T.content(" ".join(s.get("ctx") or []))) for s in self.sents])
        self.by_lesson = {}
        for n, l in enumerate(self.lesson):
            self.by_lesson.setdefault(l, set()).add(n)
        self.whole = {}
        for n, k in enumerate(self.keys):
            self.whole.setdefault(k, []).append(n)
        info = tree.lessons(module) if lessons is None else lessons
        self.order = sorted(self.by_lesson, key=lambda l: min(self.by_lesson[l]))
        self.subject = {l: info[l]["subject"] for l in self.order if l in info}
        vocab = {l: Counter(t for n in self.by_lesson[l] for t in T.content(self.sents[n]["text"])) for l in self.order}
        df = Counter(t for l in vocab for t in vocab[l])
        self.lesson_idf = {t: math.log(len(vocab) / c) for t, c in df.items()}
        self.vocab = vocab

    def exact(self, key):
        """Every place the letters occur: [(first sentence, ..., last sentence)], crossing sentence ends."""
        out, at = [], self.joined.find(key)
        while at >= 0:
            a = bisect.bisect_right(self.starts, at) - 1
            b = bisect.bisect_left(self.starts, at + len(key)) - 1
            out.append(tuple(range(a, b + 1)))
            at = self.joined.find(key, at + 1)
        return out

    def allowed(self, scope):
        out = set()
        for l in scope or ():
            out |= self.by_lesson.get(l, set())
        return out or None

    # --- scope ------------------------------------------------------------------------------------------------
    def page_scores(self, page_text, subject=None):
        """{lesson: IDF-weighted share of the page's words that the lesson has}, best = 1.0."""
        words = set(T.content(page_text))
        raw = {l: sum(self.lesson_idf[t] for t in words if t in self.vocab[l])
               for l in self.order if subject is None or self.subject.get(l) == subject}
        best = max(raw.values(), default=0)
        return {l: v / best for l, v in raw.items()} if best else {}

    def page_lessons(self, pages, subject=None):
        """[[lesson ids]] per page: the best path through the pages (a book follows the handout, mostly), plus
        the runner-up when the page itself is not sure. [] for a page with no words in common."""
        scores = [self.page_scores(p, subject) for p in pages]
        rank = {l: n for n, l in enumerate(self.order)}
        best, back = [], []
        for sc in scores:
            if not sc:
                best.append(best[-1] if best else {})
                back.append(None)
                continue
            cur, ptr = {}, {}
            for l, v in sc.items():
                prev = best[-1] if best else {}
                if prev:
                    cands = [(pv - (0 if pl == l else CHANGE + (BACK if rank[l] < rank[pl] else 0)), pl)
                             for pl, pv in prev.items()]
                    top = max(cands)
                    cur[l], ptr[l] = top[0] + v, top[1]
                else:
                    cur[l], ptr[l] = v, None
            best.append(cur)
            back.append(ptr)
        path, l = [None] * len(pages), None
        for i in range(len(pages) - 1, -1, -1):
            if back[i] is None:
                continue
            if l is None or l not in best[i]:
                l = max(best[i], key=best[i].get)
            path[i] = l
            l = back[i].get(l)
        out = []
        for sc, chosen in zip(scores, path):
            if not sc:
                out.append([])
                continue
            ranked = sorted(sc, key=sc.get, reverse=True)
            scope = [chosen] + [x for x in ranked[:1] if x != chosen]
            if len(ranked) > 1 and sc[ranked[0]] - sc[ranked[1]] < MARGIN and ranked[1] not in scope:
                scope.append(ranked[1])
            out.append(scope)
        return out


def _neighbours(res, i, reach=3):
    """Targets of the nearest resolved items before and after item i (None when there is none within reach)."""
    before = next((res[j][1][-1] for j in range(i - 1, max(-1, i - 1 - reach), -1) if res[j]), None)
    after = next((res[j][1][0] for j in range(i + 1, min(len(res), i + 1 + reach)) if res[j]), None)
    return before, after


def code_tiers(items, H):
    """[(tier, (target positions)) or None] for every item."""
    res = [None] * len(items)
    keys = [T.word_key(it["text"]) for it in items]
    for i, it in enumerate(items):
        if len(keys[i]) >= LONG:
            hits = H.exact(keys[i])
            if len(hits) == 1:
                res[i] = ("A1", hits[0])
            elif hits:
                inside = [h for h in hits if H.lesson[h[0]] in (it.get("scope") or ())]
                if len(inside) == 1:
                    res[i] = ("A2", inside[0])
    anchors = [(i, r[1]) for i, r in enumerate(res) if r]
    spots = [i for i, _ in anchors]
    for i, it in enumerate(items):
        if res[i] or len(keys[i]) < LONG:
            continue
        at = bisect.bisect_left(spots, i)
        if at == 0 or at == len(anchors):
            continue
        lo, hi = anchors[at - 1][1][-1], anchors[at][1][0]
        top = H.index.top(T.content(it["text"]), 1, H.allowed(it.get("scope")))
        if top and lo - NEAR <= top[0][0] <= hi + NEAR and lo <= hi + NEAR:
            n = top[0][0]
            if fuzz.partial_ratio(" ".join(T.tokens(it["text"])), H.norm[n]) >= FUZZY:
                res[i] = ("A3", (n,))
    for i, it in enumerate(items):
        if res[i] or not 4 <= len(keys[i]) < LONG:
            continue
        before, after = _neighbours(res, i)
        if before is None or after is None or after < before:
            continue
        hits = [n for n in H.whole.get(keys[i], []) if before <= n <= after
                and (n - before <= NEAR or after - n <= NEAR)]
        if len(hits) == 1:
            res[i] = ("A4", (hits[0],))
    return res


def candidates(items, res, window, H):
    """Handout positions a reader chooses from for the open items of one window, in handout order (<= CAP).

    The corridor between the anchors around the window comes first; then each open item's BM25 hits in its
    scope, best ranks first, each with the sentence before and after it."""
    first, last = window[0], window[-1]
    before = next((res[j][1][-1] for j in range(first - 1, -1, -1) if res[j]), None)
    after = next((res[j][1][0] for j in range(last + 1, len(items)) if res[j]), None)
    picked = []
    if before is not None and after is not None and 0 <= after - before <= CORRIDOR:
        picked += range(max(0, before - NEAR), min(len(H.sents), after + NEAR + 1))
    ranked = []
    for i in window:
        if res[i]:
            picked += res[i][1]
            continue
        words = T.content(items[i]["text"])
        hits = [n for n, _ in H.index.top(words, TOP_K, H.allowed(items[i].get("scope")))]
        # the page scope can be wrong: the best hits of the whole handout go in right after the best scoped hit
        wide = [n for n, _ in H.index.top(words, WIDE_K) if n not in hits]
        ranked.append(hits[:1] + wide + hits[1:])
    for depth in range(TOP_K + WIDE_K):
        for hits in ranked:
            if depth < len(hits):
                n = hits[depth]
                picked += [n] + [m for m in (n - 1, n + 1) if 0 <= m < len(H.sents) and H.lesson[m] == H.lesson[n]]
    out = []
    for n in picked:
        if n not in out:
            out.append(n)
        if len(out) >= CAP:
            break
    return sorted(out)


def windows(n, res, width=12, stride=10, shift=0):
    """Runs of item numbers [i, i+width); a window with nothing open is skipped."""
    out = []
    for start in range(-shift if shift else 0, n, stride):
        w = list(range(max(0, start), min(n, start + width)))
        if w and any(not res[i] for i in w):
            out.append(w)
    return out

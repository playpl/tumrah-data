"""BM25 in plain Python. One handout sentence is one document; its heading path is a second, lighter field.

    index = Index([(tokens, ctx_tokens), ...])      # or a list of token lists
    index.top(query_tokens, k=8, allowed={3, 4, 9}) -> [(doc number, score)], best first

No dependency: the whole handout indexes in about a second.
"""
import math
from collections import Counter

K1, B, CTX_WEIGHT = 1.4, 0.6, 0.3


class Index:
    def __init__(self, docs, k1=K1, b=B, ctx_weight=CTX_WEIGHT):
        self.k1, self.b = k1, b
        self.postings, self.length = {}, []
        for n, doc in enumerate(docs):
            body, ctx = doc if isinstance(doc, tuple) else (doc, ())
            tf = Counter(body)
            for t, c in Counter(ctx).items():
                tf[t] += ctx_weight * c
            self.length.append(sum(tf.values()))
            for t, c in tf.items():
                self.postings.setdefault(t, []).append((n, c))
        self.n = len(self.length)
        self.avg = (sum(self.length) / self.n) if self.n else 0.0
        self.idf = {t: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

    def scores(self, query, allowed=None):
        out = Counter()
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for n, tf in self.postings[t]:
                if allowed is not None and n not in allowed:
                    continue
                norm = tf + self.k1 * (1 - self.b + self.b * self.length[n] / (self.avg or 1))
                out[n] += idf * tf * (self.k1 + 1) / norm
        return out

    def top(self, query, k=8, allowed=None):
        return sorted(self.scores(query, allowed).items(), key=lambda x: (-x[1], x[0]))[:k]

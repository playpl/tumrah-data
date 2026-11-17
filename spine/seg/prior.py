"""The zero-token prior of Phase 2: transcript paragraphs -> the doctor's book sentences, strictly forward.

A paragraph is one stamped line of the transcript (`[mm:ss] ...`, about 30 s of speech). Its words are the
transcript's own English words plus the English terms its Arabic-script words most likely say (consonant
skeletons, `text.restore_terms`). Each book sentence is scored by IDF overlap; a monotone dynamic programme
then picks, for every paragraph, one book sentence or NONE, never going back. The prior gives the reader its
book slice and is the fallback a reader's answer is checked against.
"""
import math
import re
from collections import Counter

from spine import text

STAMP = re.compile(r"^\[(?:(\d+):)?(\d{1,2}):(\d{2})\]\s*(.*)$")
NONE_SCORE = 0.35        # a paragraph that matches nothing better than this is NONE
STEP_COST = 0.002        # per book sentence skipped forward: favours the nearest next match


def paragraphs(raw):
    """[{n, start (s), text}] from a stamped transcript; unstamped lines join the paragraph before them."""
    out = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = STAMP.match(line)
        if m:
            h, mi, s, body = m.groups()
            out.append({"n": len(out) + 1, "start": int(h or 0) * 3600 + int(mi) * 60 + int(s), "text": body})
        elif out:
            out[-1]["text"] += " " + line
        else:
            out.append({"n": 1, "start": 0, "text": line})
    return out


def stamp(seconds):
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    return f"{h}:{rest // 60:02d}:{rest % 60:02d}" if h else f"{rest // 60:02d}:{rest % 60:02d}"


def book_words(s):
    return set(text.content(s["text"] + " " + " ".join(s.get("ctx") or [])))


def lexicon(sents):
    return text.Lexicon({w for s in sents for w in text.tokens(s["text"]) if w.isascii()})


def para_words(p, lex):
    words = set(text.content(p["text"]))
    return words | text.restore_terms(p["text"], lex)


def scores(paras, sents, lex=None):
    """Matrix (paragraph x sentence) of IDF overlap, each row scaled to its own best = 1 (0 when nothing matches)."""
    import numpy as np
    lex = lex or lexicon(sents)
    bw = [book_words(s) for s in sents]
    df = Counter(w for ws in bw for w in ws)
    n = len(sents)
    idf = {w: math.log((n + 1) / (c + 0.5)) for w, c in df.items()}
    index = {}
    for j, ws in enumerate(bw):
        for w in ws:
            index.setdefault(w, []).append(j)
    norm = np.array([math.sqrt(sum(idf[w] for w in ws)) or 1.0 for ws in bw])
    m = np.zeros((len(paras), n))
    for i, p in enumerate(paras):
        for w in para_words(p, lex):
            for j in index.get(w, ()):
                m[i, j] += idf[w]
        m[i] /= norm
        top = m[i].max()
        if top > 0:
            m[i] /= top
            m[i][m[i] < 0.5] = 0           # weak hits are noise: only a paragraph's strong matches count
    return m


def path(m, none_score=NONE_SCORE, step=STEP_COST):
    """Best monotone path: for each paragraph a sentence index (never smaller than the one before) or None."""
    import numpy as np
    n_p, n_s = m.shape
    if not n_p or not n_s:
        return [None] * n_p
    pos = np.arange(n_s) * step
    best = np.zeros(n_s)               # best score of a path whose position is <= j... ending at j
    back = []
    for i in range(n_p):
        shifted = best + pos           # prefix max of best[j'] - step*(j-j') over j' <= j
        arg = np.maximum.accumulate(np.where(shifted == np.maximum.accumulate(shifted), np.arange(n_s), 0))
        pref = np.maximum.accumulate(shifted) - pos
        matched = pref + m[i]
        matched[m[i] <= 0] = -np.inf   # matching a sentence the paragraph shares nothing with is not allowed
        unmatched = best + none_score   # NONE keeps the position
        take = matched >= unmatched
        back.append((take, arg))
        best = np.where(take, matched, unmatched)
    j = int(np.argmax(best))
    out = []
    for i in range(n_p - 1, -1, -1):
        take, arg = back[i]
        if take[j]:
            out.append(j)
            j = int(arg[j])
        else:
            out.append(None)
    return out[::-1]


def prior(paras, sents, lex=None):
    if not paras or not sents:
        return [None] * len(paras)
    return path(scores(paras, sents, lex))


def window(points, n_sents, margin=30, trim=0.1):
    """(lo, hi) book indexes the reader gets: the prior's matches without the outer `trim` share, +- margin."""
    hits = sorted(p for p in points if p is not None)
    if not hits:
        return 0, n_sents - 1
    k = int(len(hits) * trim)
    core = hits[k:len(hits) - k] or hits
    return max(0, core[0] - margin), min(n_sents - 1, core[-1] + margin)

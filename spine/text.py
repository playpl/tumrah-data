"""Text helpers shared by every matcher: tokens, Arabic normalising, sentence ends, transliterated terms.

One tokeniser for the whole package, so a BM25 index, an overlap check and a prior all count the same words.
"""
import re
import unicodedata

from hub import word_key  # noqa: F401  (re-exported: the one normalising key of the repo)

_TOKEN = re.compile(r"[a-z0-9؀-ۿ]+")
_AR_MARKS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")   # tashkeel, Quranic marks, tatweel
_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
                         "ک": "ك", "ی": "ي", "گ": "ك", "پ": "ب", "ڤ": "ف", "چ": "ج"})
_AR_LETTER = re.compile(r"[ء-ي]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")

STOP = frozenset("""a an and are as at be been by can for from has have in into is it its may of on or that the their
them then there these they this those to was were which will with within also but not than such each both all any
between through during other more most some called known due""".split())

# A dot after one of these does not end a sentence.
ABBREVIATIONS = frozenset("""e.g i.e fig figs n.b etc vs viz no nos dr prof approx ca cf al st vol eq ex resp
a.k.a i.v i.m""".split())
SENTENCE_END = (".", "?", "!", ":", ";")


def nfkc(s):
    return unicodedata.normalize("NFKC", s or "")


def ar_norm(s):
    """Arabic made comparable: no marks, one alef, ya for alef maqsura, ha for ta marbuta."""
    return _AR_MARKS.sub("", nfkc(s)).translate(_AR_MAP)


def tokens(s):
    """Every word and number, NFKC, lowercased, Arabic normalised. Order kept, repeats kept."""
    return _TOKEN.findall(ar_norm(s).lower())


def content(s):
    """Tokens that carry meaning: longer than 2 letters and not a stop word. For overlap and BM25."""
    return [t for t in tokens(s) if len(t) > 2 and t not in STOP]


def overlap(a, b):
    """Share of a's content words that b also has (0.0 when a has none)."""
    ta, tb = set(content(a)), set(content(b))
    return len(ta & tb) / len(ta) if ta else 0.0


def arabic_share(s):
    """Share of the letters that are Arabic script."""
    ar, la = len(_AR_LETTER.findall(s or "")), len(_LATIN_LETTER.findall(s or ""))
    return ar / (ar + la) if ar + la else 0.0


def ends_sentence(s):
    """True when the text ends a sentence: closing punctuation that is not an abbreviation's dot."""
    s = (s or "").rstrip().rstrip("\"')]”’")
    if not s or not s.endswith(SENTENCE_END):
        return False
    if s.endswith("."):
        last = s.split()[-1].rstrip(".").lower().lstrip("(")
        if last in ABBREVIATIONS or (len(last) == 1 and last.isalpha()):
            return False
    return True


# --- transliterated terms -------------------------------------------------------------------------------------
# A doctor says "thalamus" and the captions write "ثالاموس". Both sides are reduced to a consonant skeleton and
# compared, so the code prior can anchor an Arabic-script transcript on English book words. Zero tokens.

_AR_CONS = {"ب": "b", "ت": "t", "ط": "t", "ث": "t", "ج": "g", "غ": "g", "د": "d", "ض": "d", "ذ": "s", "ز": "s",
            "ظ": "s", "س": "s", "ص": "s", "ش": "s", "ر": "r", "ف": "f", "ق": "k", "ك": "k", "ل": "l", "م": "m",
            "ن": "n", "خ": "k"}          # ا و ي ه ح ع ء carry vowels or are silent in loan words: dropped
_EN_SUBS = [("ph", "f"), ("ck", "k"), ("ch", "k"), ("sh", "s"), ("th", "t"), ("qu", "k"), ("x", "ks"),
            ("ce", "se"), ("ci", "si"), ("cy", "sy"), ("c", "k"), ("q", "k"), ("j", "g"), ("v", "f"), ("p", "b"),
            ("z", "s")]


def _squeeze(s):
    return re.sub(r"(.)\1+", r"\1", s)


def skeleton_ar(word):
    return _squeeze("".join(_AR_CONS.get(ch, "") for ch in ar_norm(word)))


def skeleton_en(word):
    w = word.lower()
    for a, b in _EN_SUBS:
        w = w.replace(a, b)
    return _squeeze(re.sub(r"[^bdfgklmnrst]", "", w))


class Lexicon:
    """English terms (handout or book words) indexed by consonant skeleton."""

    def __init__(self, terms, min_len=5):
        self.by_skel = {}
        for term in {t.lower() for t in terms if len(t) >= min_len and t.isascii() and t.isalpha()}:
            sk = skeleton_en(term)
            if len(sk) >= 3:
                self.by_skel.setdefault(sk, set()).add(term)
        self._keys = sorted(self.by_skel)

    def lookup(self, ar_word, fuzzy=88):
        sk = skeleton_ar(ar_word)
        if len(sk) < 3:
            return set()
        if sk in self.by_skel:
            return set(self.by_skel[sk])
        if len(sk) < 5:
            return set()
        from rapidfuzz import fuzz, process
        hit = process.extractOne(sk, self._keys, scorer=fuzz.ratio, score_cutoff=fuzzy)
        return set(self.by_skel[hit[0]]) if hit else set()


def restore_terms(ar_text, lexicon):
    """English terms an Arabic-script text most likely says, read through the lexicon's skeletons."""
    if not isinstance(lexicon, Lexicon):
        lexicon = Lexicon(lexicon)
    found = set()
    for tok in set(tokens(ar_text)):
        if _AR_LETTER.match(tok) and len(tok) >= 4:
            found |= lexicon.lookup(tok)
    return found

"""CNS doctors' own quizzes (Google Forms and QuizBot) from the ZMSUMcqs58 link tree (root 2098), 2026-11-22.

Before this only 5 of the tree's 56 quiz forms had been keyed (the old importers read other channels). Every post
below was read by Claude and filed by its own caption: doctor, topic, and that doctor's CNS lectures on the topic.
Keys come only from the source (`form_keys.py url`: the form's score page; `play_quizzes.py`, QUIZBOT_OUT=
sources/cns_quizzes/quizbot: QuizBot's correct flag). Reading the keyed rows: `msk_quizzes.questions` (same cleaning).

Each question goes on the one lecture (of the post's lectures) whose site handout range holds its best line (IDF word
overlap, as fast_lessons scores); a post with one lecture puts all its questions there. It is written into that
lecture.json `required` list (owner's grade 1, 2026-11-20: the doctor's own quiz = Required), `by` "zmsumcqs58":
with the bank's word_key when the bank holds the same question with the same key (it keeps its poll votes), else with
the source row. `apply` first removes every earlier "zmsumcqs58" row, so it can be run again. The owner's own rows are
never touched. A post with no lecture of its doctor waits in modules/year2-cns/site/quiz_waiting.jsonl.

    py cns_quizzes.py fetch    key the forms, play the QuizBot quizzes (resumable)
    py cns_quizzes.py show     keyed questions per post (no network)
    py cns_quizzes.py apply    -> lecture.json required rows; then `py site_import.py` carries them to the site
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

import msk_quizzes as MQ

ROOT = Path(__file__).resolve().parent
TREE = ROOT / "sources" / "tree" / "ZMSUMcqs58_2098.json"
OUT = ROOT / "sources" / "cns_quizzes"
QUIZBOT = OUT / "quizbot" / "quizbot_questions.jsonl"
MODULE = "year2-cns"
BY = "zmsumcqs58"

AZ, WG, MS = "dr-ibrahim-el-azouni-anat", "dr-wajih-el-husseiny-anat", "dr-amr-mesafer-anat"
ZH, BS, MH = "dr-mohamed-zahran-hist", "dr-basel-sherif-hist", "dr-mahmoud-el-husseiny-hist"
SM, NG = "dr-abdullah-el-samahi-phys", "dr-naguib-el-husseiny-phys"


def c(*n):
    return [f"cns-{x:03d}" for x in n]


SAMAHY_ALL = c(5, 6, 18, 23, 24, 76, 77, 84, 107, 119, 140, 150, 183, 184, 185)
# post -> (doctor, caption topic, [], his CNS lectures on it: [] = none of his lectures covers it)
ITEMS = {
    2143: (NG, "Sensory receptor", [], c(13, 14)),
    2145: (NG, "Pain sensation", [], c(15, 70)),
    2148: (NG, "Type of sensation", [], c(80)),
    2152: (NG, "Sensory pathway", [], c(102, 103)),
    2164: (NG, "Sensory disturbance", [], c(104, 105)),
    2172: (NG, "Reflex action", [], c(85)),
    2191: (NG, "UMNL & LMNL", [], c(123, 124)),
    2192: (NG, "Spinal cord lesion", [], c(126, 127)),
    2194: (NG, "Stretch reflex", [], c(143, 144)),
    2205: (NG, "Properties of reflex", [], c(163, 174)),
    2206: (NG, "Cerebral cortex", [], c(175, 176, 177)),
    2213: (NG, "Motor pathways", [], c(120, 121, 122)),
    2214: (NG, "Speech & Aphasia", [], c(190, 191)),
    2144: (MH, "Nerve cell", [], c(62)),
    2155: (MH, "Neuron processes & classification", [], c(62)),
    2147: (AZ, "Spinal cord", [], c(8, 10, 9)),
    2156: (AZ, "Medulla oblongata", [], c(63, 64, 112)),
    2165: (AZ, "Pons", [], c(65, 66, 78, 79)),
    2166: (AZ, "Midbrain", [], c(78, 79)),
    2186: (AZ, "Fourth ventricle", [], c(87, 88, 89)),
    2215: (AZ, "Internal capsule", [], c(167, 168)),
    2150: (MS, "Spinal cord 1", [], c(2, 3)),
    2159: (MS, "Spinal segments, nerves, meninges", [], c(2, 3, 21)),
    2163: (MS, "Spinal cord blood supply", [], c(2, 3, 21)),
    2169: (MS, "CSF", [], c(22)),
    2171: (MS, "Diencephalon & Thalamus", [], c(75)),
    2184: (MS, "White matter", [], c(108)),
    2190: (MS, "Basal ganglia", [], c(129)),
    2195: (MS, "Internal capsule", [], c(145)),
    2198: (MS, "Arterial supply of the brain", [], c(165)),
    2202: (MS, "Arterial supply of the brainstem & cerebrum", [], c(164)),
    2212: (MS, "Third & lateral ventricles", [], c(178)),
    2230: (MS, "4th ventricle", [], c(192)),
    2234: (MS, "Scalp 1", [], []),
    2151: (SM, "Sensory receptor", [], c(5, 6)),
    2170: (SM, "Pain", [], c(18, 23, 24)),
    2183: (SM, "Ascending tract", [], c(76, 77)),
    2196: (SM, "Reflexes", [], c(119, 140)),
    2207: (SM, "Revision", [], SAMAHY_ALL),
    2208: (SM, "Stretch reflex", [], c(150, 183)),
    2228: (SM, "Descending tract", [], c(184, 185)),
    2153: (ZH, "Neuron", [], c(1, 4)),
    2154: (ZH, "Neuron processes & classification", [], c(1, 4)),
    2161: (ZH, "Nerve fiber", [], c(19)),
    2162: (ZH, "Ganglia & nerve trunk", [], c(20)),
    2180: (ZH, "Glial cells & myelination", [], c(82)),
    2182: (ZH, "Degeneration & regeneration", [], c(92)),
    2187: (ZH, "Receptors", [], c(117)),
    2197: (ZH, "Meninges", [], c(139)),
    2203: (ZH, "Spinal cord", [], c(172, 173)),
    2229: (ZH, "Eye 1", [], c(182)),
    2158: (WG, "Spinal cord", [], c(26, 27, 28, 67)),
    2176: (WG, "Cerebellum & 4th ventricle", [], c(69, 90)),
    2216: (WG, "Diencephalon & 3rd ventricle", [], c(91, 133)),
    2217: (WG, "Limbic system & basal ganglia", [], c(135, 136)),
    2235: (WG, "Maxillary nerve", [], []),
    2236: (WG, "Muscles of mastication", [], c(181)),
    2237: (WG, "Mandibular nerve", [], []),
    2240: (WG, "Maxillary artery", [], []),
    2221: (BS, "Neuron", [], c(29, 30)),
    2222: (BS, "Nerve cell processes & classification of neuron", [], c(31, 32)),
    2223: (BS, "Nerve fiber", [], c(33)),
    2224: (BS, "Degeneration & regeneration of nerve", [], c(34)),
    2225: (BS, "Ganglia", [], c(35)),
    2226: (BS, "Neuroglia", [], c(36)),
    2227: (BS, "Receptors", [], c(37, 38)),
}
# Left out: 2218/2219 Professional Practice quizzes (another module).


def questions():
    return MQ.questions(ITEMS, TREE, QUIZBOT, channel="ZMSUMcqs58")


def show():
    got = Counter(q["post"] for q in questions())
    src = MQ.sources(ITEMS, TREE)
    for post, (doctor, title, _, lecs) in sorted(ITEMS.items()):
        print(f"{post} {src.get(post, ('-',))[0]:8} {doctor[3:22]:20} {title[:40]:40} keyed {got.get(post, 0):3}"
              f"  {', '.join(lecs) if lecs else 'no lecture: waits'}")
    print(f"{sum(got.values())} keyed questions from {len(got)} of {len(ITEMS)} posts")


def fetch():
    import os
    import subprocess
    import sources as S
    links = [ref for kind, ref in MQ.sources(ITEMS, TREE).values() if kind == "form"]
    subprocess.run([sys.executable, str(ROOT / "form_keys.py"), "url", *links], cwd=ROOT, check=False)
    subprocess.run([S.PY313, str(S.TELEGRAM / "quizbot" / "play_quizzes.py"), "scraper"], cwd=ROOT, check=False,
                   env={**os.environ, "QUIZBOT_OUT": str(OUT / "quizbot")})
    show()


def _range_lines(meta, lines, order):
    import lectures
    out = []
    for r in lectures.site_ranges(meta):
        a, b = order.get(r["from"]), order.get(r["to"])
        if a is not None and b is not None:
            out.extend(lines[a:b + 1])
    return out


def apply(say=print):
    import fast_lessons as F
    import lectures
    sys.path.insert(0, str(ROOT / "polls"))
    from engine import word_key
    from flows.common import read_jsonl
    lines = [ln for ln in read_jsonl(ROOT / "modules" / MODULE / "lines.jsonl")]
    order = {ln["id"]: i for i, ln in enumerate(lines)}
    toks = [set(F.words(ln.get("text") or "")) for ln in lines]
    df = Counter(w for t in toks for w in t)
    idf = {w: math.log(len(toks) / (1 + n)) for w, n in df.items()}
    bank = {q["word_key"]: q for q in read_jsonl(ROOT / "bank" / "questions.jsonl")}
    metas, span = {}, {}
    stats, waiting, rows, per_post = Counter(), [], {}, Counter()
    for q in questions():
        lecs = [x for x in q["own"] if (lectures.folder(x) / "lecture.json").exists()]
        if not lecs:
            stats["waits: no lecture of his on it"] += 1
            waiting.append({"post": q["post"], "doctorId": q["doctor"], "title": q["title"], "stem": q["stem"]})
            continue
        for x in lecs:
            if x not in metas:
                metas[x] = lectures.load(x)
                span[x] = {order[ln["id"]] for ln in _range_lines(metas[x], lines, order)}
        qw = Counter(F.words(q["stem"]))
        for w in F.words(q["options"][q["key"]]):
            qw[w] += 2

        def score(x):
            return max((sum(idf.get(w, 0) for w in qw if w in toks[i]) for i in span[x]), default=0.0)
        best = max(lecs, key=lambda x: (score(x), -lecs.index(x))) if len(lecs) > 1 else lecs[0]
        wk = word_key(q["stem"], q["options"])
        b = bank.get(wk)
        per_post[q["post"]] += 1                # a stable site id: the post and the question's place in it
        item = {"by": BY, "file": f"{BY}:{q['post']}", "n": per_post[q["post"]], "at": "2026-11-22"}
        if b and b.get("key") == q["key"] and not b.get("key_conflict"):
            item["word_key"] = wk
            stats["same question in the bank (votes kept)"] += 1
        else:
            item["row"] = {"question": q["stem"], "options": q["options"], "key": q["key"]}
        rows.setdefault(best, []).append(item)
        stats["filed"] += 1
    changed = 0
    for lid in sorted({p.parent.name for p in (ROOT / "lectures").glob("*/lecture.json")}):
        m = lectures.load(lid)
        old = m.get("required") or []
        keep = [x for x in old if x.get("by") != BY]
        new = keep + rows.get(lid, [])
        if new != old:
            m["required"] = new
            lectures.save(m)
            changed += 1
    w = ROOT / "modules" / MODULE / "site" / "quiz_waiting.jsonl"
    w.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in waiting), encoding="utf-8")
    stats["lectures changed"] = changed
    say(json.dumps(dict(stats), ensure_ascii=False, indent=1))
    return stats


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"fetch": fetch, "show": show, "apply": apply}[sys.argv[1]]()

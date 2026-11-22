"""MSK doctors' own quizzes (Google Forms and QuizBot) from the zagexam59 link tree (root 503), 2026-11-22.

The tree's list posts name the doctors, but their links are shifted (Nagib's "Skin structure" sits under Samahy's list,
Samahy's "Ca homeostasis l" under Mahmoud's): every post below was read by Claude and filed by its OWN caption.
Keys come only from the source: the form's score page (`form_keys.py url`), QuizBot's correct flag
(`play_quizzes.py`, QUIZBOT_OUT=sources/msk_quizzes/quizbot). Nothing is guessed.

Owner's grades (2026-11-20): 1 = the doctor's own quiz on his lesson (Required on that lesson); a doctor with no lecture
on that area yet (Wagih, Basel, Mosafer's later regions, ...) = 3 (another doctor's file): it goes where the polls go
(the live lesson holding that handout lesson), or waits with its handout link (msk_waiting.jsonl).

    py msk_quizzes.py fetch     form keys for every form below, then the QuizBot quizzes (resumable)
    py msk_quizzes.py show      the questions per post: keyed / unkeyed (no network)
`msk_questions.py build` reads `questions()`; `msk_questions.py import` writes the Required lists.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TREE = ROOT / "sources" / "tree" / "zagexam59_503.json"
OUT = ROOT / "sources" / "msk_quizzes"
FORM_KEYS = ROOT / "sources" / "forms" / "keys" / "own_form_keys.jsonl"
QUIZBOT = OUT / "quizbot" / "quizbot_questions.jsonl"

AZ, WG, MS = "dr-ibrahim-el-azouni-anat", "dr-wajih-el-husseiny-anat", "dr-amr-mesafer-anat"
ZH, AM, BS = "dr-mohamed-zahran-hist", "dr-ahmed-ammar-hist", "dr-basel-sherif-hist"
MH, SM, NG = "dr-mahmoud-el-husseiny-hist", "dr-abdullah-el-samahi-phys", "dr-naguib-el-husseiny-phys"


def k(*ids):
    return [f"lecture:{i}" for i in ids]


# post -> (doctor, caption title, handout lessons, the doctor's own site lessons on it: [] = none yet)
ITEMS = {
    523: (AZ, "Pectoral region", ["L01"], k("y1-anat-161", "y1-anat-163", "y1-anat-165")),
    524: (AZ, "Axilla", ["L02"], k("y1-anat-177")),
    534: (AZ, "Brachial Plexus Anatomy and Injuries", ["L02", "L09"], k("y1-anat-193", "y1-anat-194", "y1-anat-196")),
    559: (AZ, "Shoulder region", ["L03"], k("y1-anat-178", "y1-anat-185", "y1-anat-187", "y1-anat-186")),
    586: (AZ, "Muscles of back", ["L04"], k("y1-anat-188", "y1-anat-187", "y1-anat-186")),
    525: (WG, "Pectoral region 1", ["L01"], []),
    527: (WG, "Pectoral region 2", ["L01"], []),
    528: (WG, "Axilla", ["L02"], []),
    544: (WG, "Brachial plexus", ["L02", "L09"], []),
    545: (WG, "Axillary artery and axillary lymph nodes", ["L02"], []),
    550: (WG, "Shoulder region 1", ["L03"], []),
    551: (WG, "Shoulder region 2", ["L03"], []),
    553: (WG, "Axillary Nerve", ["L03", "L09"], []),
    554: (WG, "Inter-muscular spaces", ["L03"], []),
    569: (WG, "Back", ["L04"], []),
    577: (WG, "Muscles of arm", ["L05"], []),
    578: (WG, "Nerves of arm", ["L05", "L09"], []),
    590: (WG, "Vessels of arm", ["L05", "L08"], []),
    591: (WG, "Cubital fossa", ["L05", "L06"], []),
    536: (MS, "Pectoral Region 1 Quiz", ["L01"], k("y1-anat-166")),
    537: (MS, "Pectoral Region 2 Quiz", ["L01"], k("y1-anat-167")),
    538: (MS, "Axilla Quiz", ["L02"], k("y1-anat-169")),
    539: (MS, "Shoulder Region 1 Quiz", ["L03"], []),
    542: (MS, "Shoulder Region 2 Quiz", ["L03"], []),
    570: (MS, "Back 1 Quiz", ["L04"], []),
    571: (MS, "Back 2 Quiz", ["L04"], []),
    572: (MS, "Arm 1 Quiz", ["L05"], []),
    573: (MS, "Arm 2 Quiz", ["L05"], []),
    583: (MS, "Forearm 1 Quiz", ["L06"], []),
    585: (MS, "Forearm 2 Quiz", ["L06"], []),
    522: (ZH, "Cartilage quiz 1 from previous years exams", ["L21"], k("y1-hist-223")),
    535: (ZH, "Cartilage quiz 2", ["L21"], k("y1-hist-227")),
    552: (ZH, "Cartilage 3", ["L21"], []),
    589: (ZH, "Cartilage chapter quiz", ["L21"], k("y1-hist-223", "y1-hist-227")),
    579: (ZH, "Bone 1", ["L22"], []),
    580: (ZH, "Bone 2", ["L22"], []),
    521: (AM, "Cartilage quiz 1", ["L21"], k("y1-hist-230")),
    532: (AM, "Cartilage quiz 2", ["L21"], k("y1-hist-232")),
    588: (AM, "Bone 1", ["L22"], k("y1-hist-238")),
    564: (AM, "Bone 2", ["L22"], k("y1-hist-243")),
    587: (AM, "Bone 3&4", ["L22"], []),
    520: (BS, "Cartilage quiz 1", ["L21"], []),
    547: (BS, "Bone 1", ["L22"], []),
    574: (BS, "Bone 2&3", ["L22"], []),
    592: (BS, "Bone 4", ["L22"], []),
    519: (MH, "Cartilage quiz 1", ["L21"], k("y1-hist-ytss6-mfuyabg-84f8df")),
    543: (MH, "Cartilage quiz 2", ["L21"], k("y1-hist-ytl1iceq-a-lq-81ebf3")),
    549: (MH, "Cartilage quiz 3", ["L21"], k("y1-hist-235")),
    556: (MH, "Cartilage chapter quiz", ["L21"], k("y1-hist-ytss6-mfuyabg-84f8df", "y1-hist-ytl1iceq-a-lq-81ebf3",
                                                   "y1-hist-235")),
    576: (MH, "Bone 1 (from previous years exams)", ["L22"], k("y1-hist-246")),
    584: (MH, "Bone 2", ["L22"], k("y1-hist-248")),
    594: (MH, "Bone 3", ["L22"], []),
    557: (SM, "Ca homeostasis I", ["L26"], k("y1-phys-256")),
    558: (SM, "Ca homeostasis II", ["L26"], k("y1-phys-256")),
    561: (SM, "Excitability", ["L28"], k("y1-phys-258")),
    526: (NG, "Skin structure", ["L25"], k("y1-phys-245", "y1-phys-247")),
}
# Left out on purpose: 566 Cocci's skin quiz (Cocci stays off the site), 531/546/555/582/593 Professional Practice
# (another module), 516-518 first-term (S&F) exams, 530 an answers picture.


def read_jsonl(f):
    f = Path(f)
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []


def sources():
    """{post: (kind, url or QuizBot param)} from the saved tree (nodes and the posts no list links to)."""
    t = json.loads(TREE.read_text(encoding="utf-8"))
    out = {}
    for x in t["nodes"] + t["unreached"]:
        for o in x.get("outer") or []:
            if x["id"] in ITEMS and o.get("kind") in ("form", "quizbot"):
                url = o["url"]
                if "/forms/d/" in url and "/forms/d/e/" not in url:    # an editor's link: its public page answers
                    url = re.sub(r"/(edit|viewform)\b.*$", "/viewform", url)
                out[x["id"]] = ("quizbot", re.search(r"start=(\w+)", url)[1]) if o["kind"] == "quizbot" else ("form", url)
    return out


NUM = re.compile(r"^\s*(?:\[\d+/\d+\]|\(?\d{1,3}[.)\-]|Q\s*\d{1,3}[.):\-]?)\s*", re.I)
LETTER = re.compile(r"^\s*\(?([A-Ea-e])[.)\-]?\s+")
BULLET = re.compile(r"^\s*[-–•·*]\s*")


def clean(stem, options):
    """A quiz's own numbering ("[1/6] ", "3. ") and option letters ("A Choroid plexus") are not question text."""
    stem = NUM.sub("", stem or "", count=1).strip()
    if options and all(BULLET.match(o or "") for o in options):
        options = [BULLET.sub("", o, count=1) for o in options]
    lets = [LETTER.match(o or "") for o in options]
    if all(lets) and [m[1].lower() for m in lets] == list("abcde"[:len(options)]):
        options = [LETTER.sub("", o, count=1).strip() for o in options]
    return stem, [str(o).strip() for o in options]


def questions():
    """[{post, doctor, title, lessons, own, kind, url, stem, options, key}] of every keyed question below."""
    src = sources()
    forms, bot = {}, {}
    for r in read_jsonl(FORM_KEYS):
        forms.setdefault(r["link"], {})[str(r["item_id"])] = r           # the latest key of an item wins
    for r in read_jsonl(QUIZBOT):
        bot.setdefault(r["param"], {})[r.get("position")] = r
    out = []
    for post, (doctor, title, lessons, own) in sorted(ITEMS.items()):
        kind, ref = src.get(post, (None, None))
        rows = list((forms if kind == "form" else bot).get(ref, {}).values()) if kind else []
        for r in rows:
            if r.get("correct_index") is None:
                continue
            stem, options = clean(r["question"], r["options"])
            if not stem or not 2 <= len(options) <= 5 or any(not o for o in options) \
                    or not 0 <= r["correct_index"] < len(options):
                continue
            out.append({"post": post, "doctor": doctor, "title": title, "lessons": lessons, "own": own, "kind": kind,
                        "url": f"https://t.me/zagexam59/{post}", "stem": stem, "options": options,
                        "key": r["correct_index"], "solution": r.get("solution")})
    return out


def show():
    src = sources()
    got = {}
    for q in questions():
        got[q["post"]] = got.get(q["post"], 0) + 1
    for post, (doctor, title, _, own) in sorted(ITEMS.items()):
        print(f"{post} {src.get(post, ('-',))[0]:8} {doctor[3:22]:20} {title[:40]:40} keyed {got.get(post, 0):3}"
              f"  {'own ' + str(len(own)) if own else 'grade 3'}")
    print(f"{sum(got.values())} keyed questions from {len(got)} of {len(ITEMS)} posts")


def fetch():
    import os
    import subprocess
    src = sources()
    links = [ref for kind, ref in src.values() if kind == "form"]
    subprocess.run([sys.executable, str(ROOT / "form_keys.py"), "url", *links], cwd=ROOT, check=False)
    (OUT / "quizbot").mkdir(parents=True, exist_ok=True)
    plan = [{"param": ref, "title": f"zagexam59 {post}: {ITEMS[post][1]}", "questions": None}
            for post, (kind, ref) in sorted(src.items()) if kind == "quizbot"]
    (OUT / "quizbot" / "play_list.json").write_text(json.dumps(plan, ensure_ascii=False, indent=0), encoding="utf-8")
    import sources as S
    subprocess.run([S.PY313, str(S.TELEGRAM / "quizbot" / "play_quizzes.py"), "scraper"], cwd=ROOT, check=False,
                   env={**os.environ, "QUIZBOT_OUT": str(OUT / "quizbot")})
    show()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"fetch": fetch, "show": show}[sys.argv[1]]()

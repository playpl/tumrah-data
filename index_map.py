"""Channel index -> exact lesson for each bank question (owner, 2026-11-09).

Batch58ATM's CNS subject indexes (59452 anatomy, 59453 physiology, 59454 histology) link to lists (New / Old, per
doctor or year, and "Code blue special" = AI-made), and each list links to the first message of one lesson's polls.
A lesson's polls run from its first message to the next first message of any list. Every bank question seen at a
message in such a run gets that lesson, branch (new / old / ai) and list. Counts only.

    py index_map.py         -> sources/index/cns_segments.json, sources/index/cns_question_map.json
"""
import json
import re
import sys
from bisect import bisect_right
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IDX = ROOT / "sources" / "index"
CHANNEL = "Batch58ATM"
SUBJECTS = {59452: "anatomy", 59453: "physiology", 59454: "histology"}


# The doctor a list names (its header line) -> the bank's doctor name.
DOCTORS = {"elazouny": "Ibrahim Elazouny", "azouny": "Ibrahim Elazouny", "wagih": "Wagih El-Husseiny",
           "amr": "Amr Mosafer", "nagib": "Nagib El-Husseiny", "nageeb": "Nagib El-Husseiny",
           "samahy": "Abdalla Elsamahy", "khaled": "Khaled Abualfadle", "zahran": "Mohamed Zahran",
           "basel": "Basel Sherif", "ammar": "Ahmed Ammar", "mahmoud": "Mahmoud Hisham", "mahran": "Mahran"}
# The named lessons' doctors (lectures/<id>/lecture.json `doctor`) in the bank's spelling.
LESSON_DOCTOR = {"dr-mohamed-zahran-hist": "Mohamed Zahran", "dr-amr-mesafer-anat": "Amr Mosafer",
                 "dr-abdullah-el-samahi-phys": "Abdalla Elsamahy"}
# Index lesson name (lowercase words) -> handout lecture (reference list) per subject. First match wins.
LECTURE_RULES = {
    "anatomy": [("spinal cord", "L03"), ("mo ", "L05"), ("medulla", "L05"), ("pons", "L05"), ("midbrain", "L05"),
                ("brain stem", "L05"), ("cranial nuclei", "L05"), ("cerebellum", "L07"), ("4th ventricle", "L08"),
                ("diencephalon", "L10"), ("thalamus", "L10"), ("3rd ventricle", "L11"), ("limbic", "L12"),
                ("internal capsule", "L13"), ("white matter", "L13"), ("basal ganglion", "L13"),
                ("lateral ventricle", "L14"), ("csf", "L15"), ("arterial", "L16"), ("blood supply", "L16"),
                ("scalp", "L37"), ("face", "L38"), ("mastication", "L39"), ("infratemporal", "L39"),
                ("mandibular", "L41"), ("maxillary nerve", "L42"), ("maxillary n", "L42"), ("pterygopalatine", "L43"),
                ("maxillary artery", "L44"), ("venous", "L45"), ("sinus", "L45"), ("dural", "L45"),
                ("middle meningeal", "L46"), ("cervical fascia", "L47"), ("triangle", "L48"), ("lymph", "L49"),
                ("glossopharyngeal", "L50"), ("vagus", "L51"), ("accessory", "L52"), ("hypoglossal", "L53"),
                ("eye", "L54"), ("ear", "L57"), ("facial", "L58"), ("vestibulocochlear", "L59")],
    "histology": [("neuron", "L01"), ("nerve", "L01"), ("ganglia", "L01"), ("ganglion", "L01"), ("glial", "L01"),
                  ("neuroglia", "L01"), ("generation", "L01"), ("receptor", "L01"), ("synapse", "L01"),
                  ("chapter 1 mixed", "L01"), ("meninges", "L02"), ("spinal cord", "L04"), ("medulla", "L06"),
                  ("pons", "L06"), ("midbrain", "L06"), ("brainstem", "L06"), ("cerebellum", "L09"),
                  ("cerebrum", "L17"), ("cortex", "L17"), ("eye", "L55"), ("ear", "L60"), ("corti", "L60")],
    "physiology": [("functional unit", "L18"), ("introduction to cns", "L18"), ("sensory receptor", "L19"),
                   ("receptor", "L19"), ("sensory principles", "L19"), ("pain", "L20"), ("sensation & pain", "L20"),
                   ("touch", "L20"), ("temperature", "L20"), ("itch", "L20"), ("ascending", "L20"),
                   ("sensory tract", "L20"), ("sensations", "L20"), ("disturbance", "L21"), ("distrubance", "L21"),
                   ("synapse", "L22"), ("reflex", "L22"), ("stretch", "L23"), ("tone", "L23"),
                   ("descending", "L24"), ("motor tract", "L24"), ("motor lesion", "L25"), ("spinal cord lesion", "L25"),
                   ("cerebellum", "L26"), ("basal ganglion", "L27"), ("thalamus", "L28"), ("hypothalamus", "L29"),
                   ("limbic", "L30"), ("reticular", "L31"), ("arousal", "L31"), ("sleep", "L32"), ("eeg", "L33"),
                   ("cortex", "L34"), ("aphasia", "L35"), ("speech", "L35"), ("memory", "L36"), ("higher functions", "L36"),
                   ("vision", "L56"), ("retina", "L56"), ("cornea", "L56"), ("eye", "L56"), ("hearing", "L61"),
                   ("inner ear", "L61"), ("middle ear", "L61"), ("ear", "L61"), ("vestibular", "L62"),
                   ("smell", "L63"), ("taste", "L64")],
}
STRIP = re.compile(r"[^a-z0-9&,. ]+")


def lecture_of(subject, name):
    s = " " + " ".join(STRIP.sub(" ", (name or "").lower()).split()) + " "
    for key, lec in LECTURE_RULES[subject]:
        if key in s:
            return f"year2-cns:{lec}"
    return None


def list_info():
    """list message id -> (doctor, [lesson name per link, for AI lists]) from the list headers."""
    lists = json.loads((IDX / "cns_lists.json").read_text(encoding="utf-8"))
    out = {}
    for lid, v in lists.items():
        doctor = None
        for line in v["lines"][:4]:
            low = line.lower()
            hit = [d for k, d in DOCTORS.items() if k in low]  # "Dr.Abdullah Elsamahy": no word boundary
            if "dr" in low and hit:
                doctor = hit[0]
                break
        names, header = [], None
        for line in v["lines"]:
            n = len(re.findall(r"easy|hard|cases", line, re.I))
            if n:
                names += [header] * n
            elif not re.search("[؀-ۿ]", line):
                header = " ".join(STRIP.sub(" ", line.lower()).split()) or header
        out[int(lid)] = (doctor, names)
    return out


def segments():
    segs = []
    info = list_info()
    for root, subject in SUBJECTS.items():
        nodes = {n["id"]: n for n in json.loads((IDX / f"{CHANNEL}_{root}.json").read_text(encoding="utf-8"))["nodes"]}
        for n, lst in enumerate(nodes[root]["links"]):
            branch = "ai" if "code blue" in lst["anchor"].lower() else lst["anchor"].strip().lower()
            doctor, names = info.get(lst["id"], (None, []))
            leaves = nodes.get(lst["id"], {}).get("links") or []
            for k, leaf in enumerate(leaves):
                name = " ".join(leaf["anchor"].split())
                if branch == "ai":
                    name = names[k] if len(names) == len(leaves) and names[k] else name
                segs.append({"subject": subject, "branch": branch, "doctor": None if branch == "ai" else doctor,
                             "list": lst["id"], "list_n": n, "n": k, "lesson": name,
                             "lecture_id": lecture_of(subject, name), "start": leaf["id"]})
    kinds = {}
    for f in IDX.glob(f"{CHANNEL}_kinds_*.json"):
        kinds.update({int(k): v for k, v in json.loads(f.read_text(encoding="utf-8")).items()})
    starts = sorted({s["start"] for s in segs})
    for s in segs:
        # The run is the unbroken block of polls at or after the linked message (a header, or the first poll); it
        # ends at the first message that is not a poll, or at the next lesson's first message.
        i = bisect_right(starts, s["start"])
        stop = starts[i] if i < len(starts) else s["start"] + 2000
        m = s["start"] + (kinds.get(s["start"]) != "p")
        while m < stop and kinds.get(m, "p") == "p" and m - s["start"] < 2000:
            m += 1
        s["end"] = m - 1
    return segs


def run():
    segs = segments()
    by_start = {}
    for s in segs:
        by_start.setdefault(s["start"], []).append(s)
    starts = sorted(by_start)
    qmap, stats = {}, Counter()
    with open(ROOT / "bank" / "questions.jsonl", encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            hits = []
            for s in q["sightings"]:
                if str(s.get("chat")) != CHANNEL or not s.get("msg_id"):
                    continue
                m = int(s["msg_id"])
                i = bisect_right(starts, m) - 1
                if i >= 0:
                    for seg in by_start[starts[i]]:
                        if m <= seg["end"]:
                            hits.append({k: seg[k] for k in ("subject", "branch", "doctor", "list", "lesson", "lecture_id", "start")} | {"msg": m})
            if hits:
                qmap[q["word_key"]] = hits
                stats["questions"] += 1
                stats["branch:" + "+".join(sorted({h["branch"] for h in hits}))] += 1
    IDX.joinpath("cns_segments.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    IDX.joinpath("cns_question_map.json").write_text(json.dumps(qmap, ensure_ascii=False), encoding="utf-8")
    seg_n = Counter((h["subject"], h["branch"], h["lesson"]) for hs in qmap.values() for h in hs)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"segments": len(segs), **stats}, indent=1))
    for (sub, br, les), n in sorted(seg_n.items()):
        print(f"{sub:10} {br:4} {n:5}  {les[:40]}")


if __name__ == "__main__":
    run()

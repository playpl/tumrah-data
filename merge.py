"""One question bank from every source: polls, QuizBot, Google Forms (and any later source with the same row shape).

Duplicates follow the zero-lossy rule (`word_key` in polls/engine.py: one changed word is a new question), and what a
duplicate means depends on where it repeats (owner, 2026-11-07):
- across channels or reposts: one question; net votes add up and the repeat is forgotten (no importance);
- across doctors: a real signal; `repetition_count` counts the doctors and `importance_score` rises with it.
Every sighting is kept with its Telegram link for a later "open on Telegram" button. Keys come only from the source;
two sources that key different options give `key_conflict`, never a chosen key; only the owner settles one
(`apply_decisions`, from the admin page's Polls tab).

Row shape (every loader returns it): {question, options, key (index or None), solution, votes (list), total,
sightings: [{source, chat, msg_id, date, header, doctor, link}]}.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "polls"))
from engine import option_word, word_key  # noqa: E402

POSITION = re.compile(r"^\s*\[\d+/\d+\]\s*")
LABEL = re.compile(r"^\s*[A-Fa-f][).]\s*")


def telegram_link(chat, msg_id):
    if not chat or msg_id is None:
        return None
    m = re.fullmatch(r"id-?(?:100)?(\d+)", str(chat))
    return f"https://t.me/c/{m.group(1)}/{msg_id}" if m else f"https://t.me/{chat}/{msg_id}"


def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def load_polls(path, doctors=None):
    """polls/ready/questions.jsonl. `doctors` maps (chat, msg_id) to a doctor once polls are labeled (task 13)."""
    doctors = doctors or {}
    out = []
    for q in read_jsonl(path):
        out.append({"question": q["question"], "options": q["options"], "key": q["key"], "solution": q.get("solution"),
                    "key_conflict": bool(q.get("key_conflict")),  # the polls engine's own conflict (reposts disagree)
                    "votes": q.get("votes") or [0] * len(q["options"]), "total": q.get("total", 0),
                    "sightings": [{"source": "poll", "chat": s["chat"], "msg_id": s["msg_id"], "date": s.get("date"),
                                   "header": s.get("header"), "doctor": doctors.get((s["chat"], s["msg_id"])),
                                   "link": telegram_link(s["chat"], s["msg_id"])} for s in q["sightings"]]})
    return out


def load_quizbot(questions_path, links_path):
    """QuizBot rows: "[n/N]" and "A)" labels stripped; sightings are the posts that link the quiz."""
    posts = {r["param"]: r["sightings"] for r in read_jsonl(links_path)}
    out = []
    for q in read_jsonl(questions_path):
        options = [LABEL.sub("", o).strip() for o in q["options"]]
        sightings = [{"source": "quizbot", "chat": s["chat"], "msg_id": s["msg_id"], "date": s.get("date"),
                      "header": s.get("header"), "doctor": s.get("chat_doctor"), "quiz": q["param"],
                      "link": telegram_link(s["chat"], s["msg_id"])} for s in posts.get(q["param"], [])]
        out.append({"question": POSITION.sub("", q["question"]).strip(), "options": options,
                    "key": q.get("correct_index"), "solution": q.get("solution"), "votes": [0] * len(options),
                    "total": 0, "sightings": sightings or [{"source": "quizbot", "quiz": q["param"], "chat": None,
                                                            "msg_id": None, "date": None, "header": None,
                                                            "doctor": None, "link": None}]})
    return out


def load_forms(questions_path, keys_path, links_path):
    """Form questions; the key only where the form's own score page showed it."""
    keys = {(k["link"], str(k["item_id"])): k for k in read_jsonl(keys_path)}
    posts = {r["link"]: r["sightings"] for r in read_jsonl(links_path)}
    out = []
    for q in read_jsonl(questions_path):
        if q.get("type") not in ("multiple_choice", "dropdown"):
            continue
        k = keys.get((q["link"], str(q["item_id"])))
        out.append({"question": q["question"], "options": q["options"], "key": k["correct_index"] if k else None,
                    "solution": None, "votes": [0] * len(q["options"]), "total": 0,
                    "sightings": [{"source": "form", "form": q["link"], "chat": s["chat"], "msg_id": s["msg_id"],
                                   "date": s.get("date"), "header": s.get("header"), "doctor": s.get("chat_doctor"),
                                   "link": telegram_link(s["chat"], s["msg_id"])} for s in posts.get(q["link"], [])]})
    return out


NUMBER = re.compile(r"^\s*\d+\s*[.)]\s*")
QUIZBOT_DOCTORS = {"elsamahy": "dr-abdullah-el-samahi-phys", "basel": "dr-basel-sherif-hist"}  # sources/quizbot/<folder>/


def load_mcq_books(folder=ROOT / "modules"):
    """Every doctor's MCQ book copied by the flow (modules/<m>/mcq/*.jsonl; owner 2026-11-12: new questions join the bank).
    The key is the book's own (`key_from`); a book with no key gives none."""
    out = []
    for f in sorted(Path(folder).glob("*/mcq/*.jsonl")):
        for q in read_jsonl(f):
            if len(q.get("options") or []) < 2:
                continue
            out.append({"question": q["question"], "options": q["options"], "key": q.get("key"), "solution": None,
                        "votes": [0] * len(q["options"]), "total": 0,
                        "sightings": [{"source": "mcq_book", "book": q.get("book"), "page": q.get("page"), "chat": None,
                                       "msg_id": None, "date": None, "header": None, "doctor": q.get("doctor"), "link": None}]})
    return out


def load_doctor_quizbot(src):
    """The owner's own QuizBot tests played by play_quizzes.py into sources/quizbot/<doctor folder>/ (keys: QuizBot's flag)."""
    out = []
    for folder, doctor in QUIZBOT_DOCTORS.items():
        for q in read_jsonl(Path(src) / "quizbot" / folder / "quizbot_questions.jsonl"):
            options = [LABEL.sub("", o).strip() for o in q["options"]]
            out.append({"question": POSITION.sub("", q["question"]).strip(), "options": options, "key": q.get("correct_index"),
                        "solution": q.get("solution"), "votes": [0] * len(options), "total": 0,
                        "sightings": [{"source": "quizbot", "quiz": q.get("param"), "chat": None, "msg_id": None, "date": None,
                                       "header": None, "doctor": doctor, "link": None}]})
    return out


def load_inbox_forms(folder):
    """Doctors' own Google Form quizzes read by `doctors_folder.chapter_quiz` (bank/inbox/*.jsonl): no key (forms show none),
    so a duplicate of a keyed bank question only adds a sighting. Doctor stays empty here: the file name is not a doctor."""
    out = []
    for f in sorted(Path(folder).glob("*.jsonl")):
        for q in read_jsonl(f):
            if q.get("type") not in ("multiple_choice", "dropdown") or len(q.get("options") or []) < 2:
                continue
            options = [LABEL.sub("", o).strip() for o in q["options"]]
            out.append({"question": NUMBER.sub("", q["question"]).strip(), "options": options, "key": None, "solution": None,
                        "votes": [0] * len(options), "total": 0,
                        "sightings": [{"source": "form", "form": q.get("link"), "chat": None, "msg_id": None, "date": None,
                                       "header": None, "doctor": None, "link": None}]})
    return out


def merge(rows):
    """Group by word_key; map keys and votes by option text, since sources order options differently."""
    bank = {}
    for r in rows:
        k = word_key(r["question"], r["options"])
        q = bank.setdefault(k, {"word_key": k, "question": r["question"], "options": list(r["options"]), "key": None,
                                "solution": None, "votes": [0] * len(r["options"]), "total": 0, "key_conflict": False,
                                "sightings": []})
        place = {option_word(o): i for i, o in enumerate(q["options"])}
        mine = [place.get(option_word(o)) for o in r["options"]]
        if r["key"] is not None and r["key"] < len(mine) and mine[r["key"]] is not None:
            key = mine[r["key"]]
            q["key_conflict"] = q["key_conflict"] or (q["key"] is not None and q["key"] != key)
            q["key"] = key if q["key"] is None else q["key"]
        q["key_conflict"] = q["key_conflict"] or bool(r.get("key_conflict"))
        q["solution"] = q["solution"] or r.get("solution")
        for i, v in enumerate(r.get("votes") or []):
            if i < len(mine) and mine[i] is not None:
                q["votes"][mine[i]] += v
        q["total"] += r.get("total") or 0
        q["sightings"] += r["sightings"]
    for q in bank.values():
        doctors = sorted({s["doctor"] for s in q["sightings"] if s.get("doctor")})
        q["doctors"] = doctors
        q["repetition_count"] = max(1, len(doctors))       # repeats across channels never count
        q["importance_score"] = max(1, len(doctors))
        q["source_url"] = next((s["link"] for s in q["sightings"] if s.get("link")), None)
    return list(bank.values())


def apply_decisions(bank, decisions):
    """The owner's key for a conflict (admin page, bank/key_decisions.json): the conflict is settled by the owner,
    never by code, and `key_source` says so."""
    for q in bank:
        d = decisions.get(q["word_key"])
        if q["key_conflict"] and d and 0 <= d["key"] < len(q["options"]):
            q.update(key=d["key"], key_conflict=False, key_source="owner")
    return bank


def counts(bank):
    return {"questions": len(bank), "keyed": sum(q["key"] is not None for q in bank),
            "key_conflicts": sum(q["key_conflict"] for q in bank),
            "repeated_across_doctors": sum(q["repetition_count"] > 1 for q in bank),
            "seen_more_than_once": sum(len(q["sightings"]) > 1 for q in bank)}


def build(out_dir=ROOT / "bank"):
    """Writes bank/questions.jsonl from every source present, and bank/counts.json."""
    src = ROOT / "sources"
    rows = load_polls(ROOT / "polls" / "ready" / "questions.jsonl") + \
        load_quizbot(src / "quizbot" / "quizbot_questions.jsonl", src / "quizbot" / "quizbot_links.jsonl") + \
        load_forms(src / "forms" / "forms_questions.jsonl", src / "forms" / "keys" / "form_keys.jsonl",
                   src / "forms" / "forms_links.jsonl") +         load_mcq_books() + load_doctor_quizbot(src) + load_inbox_forms(out_dir / "inbox")
    decisions = out_dir / "key_decisions.json"
    bank = apply_decisions(merge(rows), json.loads(decisions.read_text(encoding="utf-8")) if decisions.exists() else {})
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / "questions.jsonl", "w", encoding="utf-8") as f:
        for q in bank:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    c = counts(bank)
    (out_dir / "counts.json").write_text(json.dumps(c, indent=1), encoding="utf-8")
    return c

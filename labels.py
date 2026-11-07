"""Labels for the bank (plan task 13): module, lecture, doctor and kind for every question, read by the fleet.

Order (owner): script rules first, the fleet for the rest, every label from a closed list.
1. Posting windows (config.json module_windows): a sighting posted inside a module's window has that module.
2. Headers: every (chat, header) a question was posted under, with 3 sample questions, labelled once by the fleet
   (module or "mixed"/"none", lecture, doctor, kind). About 1,000 headers cover all 108,000 sightings.
3. Questions: only rows the headers cannot settle (a "mixed" header, or a module with a lecture list and no lecture)
   are labelled one by one.
4. bank/labels.jsonl: one row per bank question; bank/label_counts.json: counts only.

    py dm.py labels      one step each run: queues what is missing, or writes the labels when nothing is
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BANK = ROOT / "bank"
OUT = ROOT / "labels"
MODULES = ROOT / "modules"
PHASE1 = Path(r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\phase1")
BATCH = 40
SAMPLES = 3


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def short(*parts):
    return hashlib.sha1("\x00".join(map(str, parts)).encode("utf-8")).hexdigest()[:12]


def hid(chat, header):
    return short(chat, header)


def wid(word_key):
    return short(word_key)


def doctors():
    """The doctors table of the earlier pipeline (English names), the one closed list of doctors."""
    sys.path.insert(0, str(PHASE1))
    import tables
    return sorted(tables.DOCTORS)


def lecture_lists():
    return {d.name: json.loads((d / "reference.json").read_text(encoding="utf-8"))["lectures"]
            for d in sorted(MODULES.iterdir()) if (d / "reference.json").exists()} if MODULES.exists() else {}


def lists(config):
    return {"modules": config["label_modules"], "lectures": lecture_lists(), "doctors": doctors()}


def headed(s):
    return s.get("chat") is not None and bool(s.get("header"))


def header_items(bank):
    """One item per (chat, header): how many questions sit under it, when it was posted, 3 sample questions."""
    groups = {}
    for q in bank:
        for s in {(s["chat"], s["header"]): s for s in q["sightings"] if headed(s)}.values():
            g = groups.setdefault((s["chat"], s["header"]), {"hid": hid(s["chat"], s["header"]), "chat": s["chat"],
                                                             "header": s["header"], "count": 0, "first": None,
                                                             "last": None, "samples": []})
            g["count"] += 1
            day = (s.get("date") or "")[:10] or None
            if day:
                g["first"] = min(g["first"] or day, day)
                g["last"] = max(g["last"] or day, day)
            if len(g["samples"]) < SAMPLES:
                g["samples"].append(q["question"])
    return sorted(groups.values(), key=lambda g: g["hid"])


def batch_of(config):
    return {c: (59 if year == "1" else 58) for year, chans in config["poll_channels"].items() for c in chans}


def window_modules(q, config):
    batches, found = batch_of(config), set()
    for s in q["sightings"]:
        b, day = batches.get(s.get("chat")), (s.get("date") or "")[:10]
        for m, ws in config["module_windows"].items():
            if b and day and any(b == w["batch"] and w["from"] <= day <= w.get("to", "9999-12-31") for w in ws):
                found.add(m)
    return found


def header_labels_of(q, header_rows):
    return [header_rows[h] for h in {hid(s["chat"], s["header"]) for s in q["sightings"] if headed(s)} if h in header_rows]


def decide(q, header_rows, config, question_row=None):
    """(module, by, lecture, window_disagrees) from the window, then the headers, then the question's own label."""
    win, heads = window_modules(q, config), header_labels_of(q, header_rows)
    head_modules = Counter(h["module"] for h in heads if h["module"] not in ("mixed", "none"))
    if win:
        module, by = sorted(win)[0], "window"
    elif head_modules:
        module, by = head_modules.most_common(1)[0][0], "header"
    elif question_row:
        module, by = question_row["module"], "question"
    elif heads and all(h["module"] == "none" for h in heads):
        module, by = "none", "header"
    else:
        module, by = None, None
    lecture = next((h["lecture_id"] for h in heads if h["module"] == module and h["lecture_id"]), None)
    if lecture is None and question_row and question_row["module"] == module:
        lecture = question_row["lecture_id"]
    others = set(head_modules) | ({question_row["module"]} if question_row else set())
    disagrees = bool(win) and bool(others - win - {"none"})
    return module, by, lecture, disagrees


def question_items(bank, header_rows, config, lectures):
    """Rows the headers cannot settle: no module yet, or a module with a lecture list and no lecture."""
    todo = []
    for q in bank:
        module, _, lecture, _ = decide(q, header_rows, config)
        if module is None or (module in lectures and lecture is None):
            first = next((s["header"] for s in q["sightings"] if s.get("header")), None)
            todo.append({"wid": wid(q["word_key"]), "header": first, "question": q["question"], "options": q["options"]})
    return todo


def final_labels(bank, header_rows, question_rows, config):
    out = []
    for q in bank:
        heads = header_labels_of(q, header_rows)
        module, by, lecture, disagrees = decide(q, header_rows, config, question_rows.get(q["word_key"]))
        out.append({"word_key": q["word_key"], "module": module, "lecture_id": lecture, "by": by,
                    "doctors": sorted({h["doctor"] for h in heads if h["doctor"]}),
                    "kinds": sorted({h["kind"] for h in heads}), "window_disagrees": disagrees})
    return out


def header_doctors(bank, header_rows):
    """{(chat, header): doctor} for merge.py: a doctor named by the header makes the question that doctor's."""
    out = {}
    for q in bank:
        for s in q["sightings"]:
            if headed(s):
                h = header_rows.get(hid(s["chat"], s["header"]))
                if h and h["doctor"]:
                    out[(s["chat"], s["header"])] = h["doctor"]
    return out


def saved(stage, id_field):
    d = OUT / stage
    return {r[id_field]: {k: v for k, v in r.items() if k != id_field}
            for f in sorted(d.glob("*.jsonl")) for r in read_jsonl(f)} if d.exists() else {}


def jobs(stage, items, the_lists):
    return [{"key": f"{stage}-{short(*(i.get('hid') or i['wid'] for i in items[n:n + BATCH]))}",
             "payload": {"stage": stage, "lists": the_lists, "batch": items[n:n + BATCH]}}
            for n in range(0, len(items), BATCH)]


def step(config, queue=None):
    """Queues the missing header labels, else the missing question labels, else writes bank/labels.jsonl."""
    import queue_db
    bank = read_jsonl(BANK / "questions.jsonl")
    the_lists = lists(config)
    header_rows = saved("headers", "hid")
    items = [i for i in header_items(bank) if i["hid"] not in header_rows]
    stage = "headers"
    if not items:
        stage = "questions"
        done = saved("questions", "wid")
        items = [i for i in question_items(bank, header_rows, config, the_lists["lectures"]) if i["wid"] not in done]
    if items:
        q = queue or queue_db.Queue()
        added = q.add_jobs("labels", jobs(stage, items, the_lists))
        print(f"labels: {len(items)} {stage} to label, {added} new jobs queued (run `py dm.py run`)")
        return stage
    by_wid = {wid(q["word_key"]): q["word_key"] for q in bank}
    question_rows = {by_wid[w]: r for w, r in saved("questions", "wid").items() if w in by_wid}
    final = final_labels(bank, header_rows, question_rows, config)
    with open(BANK / "labels.jsonl", "w", encoding="utf-8") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    counts = {"questions": len(final), "by": dict(Counter(r["by"] for r in final)),
              "module": dict(Counter(r["module"] for r in final)),
              "with_lecture": dict(Counter(r["module"] for r in final if r["lecture_id"])),
              "window_disagrees": sum(r["window_disagrees"] for r in final)}
    (BANK / "label_counts.json").write_text(json.dumps(counts, indent=1), encoding="utf-8")
    OUT.mkdir(exist_ok=True)
    (OUT / "header_doctors.json").write_text(json.dumps(
        [[c, h, d] for (c, h), d in header_doctors(bank, header_rows).items()], ensure_ascii=False), encoding="utf-8")
    print(json.dumps(counts, indent=1))
    return "done"

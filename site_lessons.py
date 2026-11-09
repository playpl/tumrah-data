"""Every named CNS lecture as an importHubData `lessons` file, with uploaded recordings (owner, 2026-11-09).

dm.py lesson_rows gives YouTube videos; recordings uploaded with uploadLessonMedia.ts (private `r2:` keys) are added
here: video for mp4, audio for audio files. Held lectures (lecture.json `hold`) stay off the site.

    py site_lessons.py write                 -> modules/year2-cns/site/lessons.jsonl
    py site_lessons.py ids <result.json>     -> records each lecture's site lesson id from the import result
"""
import json
import sys
from pathlib import Path

import dm
import lectures
import new_doctors

ROOT = Path(__file__).resolve().parent
MODULE = "year2-cns"
SITE = ROOT / "modules" / MODULE / "site"
# Uploaded recordings: lecture id -> (field, r2 link).
MEDIA = {
    "cns-008": ("videoUrl", "r2:lectures/year2-cns/azouny/spinal_cord_1.mp4"),
    "cns-009": ("videoUrl", "r2:lectures/year2-cns/azouny/spinal_cord_2.mp4"),
    "cns-010": ("videoUrl", "r2:lectures/year2-cns/azouny/spinal_cord_3_and_medulla.mp4"),
    "cns-015": ("audioUrl", "r2:lectures/year2-cns/cns-015/recording.m4a"),
}


def write():
    held = {m["id"] for m in lectures.all_lectures(MODULE) if m.get("hold")}
    titles = [t for _, _, _, t, _, _ in new_doctors.LECTURES]
    rows = []
    for r in dm.lesson_rows(MODULE):
        lid = r["key"].split(":", 1)[1]
        if lid in held:
            continue
        meta = lectures.load(lid)
        if meta["title"] in titles:  # the new doctors' lectures follow their list order, after the first lessons
            r["order"] = 10 + titles.index(meta["title"])
        if lid in MEDIA:
            field, url = MEDIA[lid]
            r[field] = url
        rows.append(r)
    out = SITE / "lessons.jsonl"
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    print(f"{len(rows)} lessons ({len(held)} held) -> {out}")


def ids(result_file):
    res = json.loads(Path(result_file).read_text(encoding="utf-8").strip().splitlines()[-1])
    n = 0
    for key, lesson in (res.get("lessons") or {}).items():
        meta = lectures.load(key.split(":", 1)[1])
        if lesson and meta.get("lesson") != lesson:
            meta["lesson"] = lesson
            lectures.save(meta)
            n += 1
    print(f"{n} lectures got their site lesson id")


if __name__ == "__main__":
    write() if sys.argv[1] == "write" else ids(sys.argv[2])

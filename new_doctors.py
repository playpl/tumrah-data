"""The owner's three added CNS doctors and Elsamahy's new lecture (owner, 2026-11-09).

- Elazouny (anatomy): three local mp4 recordings. Never aligned; every lecture gets all of his files.
- Nagib (physiology) and Ammar (histology): lectures come from a Telegram list message in RecordsBatch58ATM (1638,
  1675) that the channel keeps updated: YouTube links or audio files posted there.
- Elsamahy: "3- pain 1" (YouTube).

Each lecture is named here, its recording prepared (YouTube captions, else audio for the fleet), and its media listed in
modules/year2-cns/site/media.json for uploadLessonMedia.ts. Handout pages: a first, coarse placement from the handout's
lecture list (`placed_by: "claude-coarse"`); the recording links narrow it later. Run again: existing lectures are kept.

    py new_doctors.py create      name lectures, fetch captions / audio, write media.json
"""
import asyncio
import json
import sys
from pathlib import Path

import lectures

ROOT = Path(__file__).resolve().parent
MODULE = "year2-cns"
DOC = ROOT / "doctors" / "cns"
SITE = ROOT / "modules" / MODULE / "site"
AZ = DOC / "anatomy" / "azony"

# (doctor id, subject, chapter, title, source, coarse handout pages)
LECTURES = [
    ("dr-ibrahim-el-azouni-anat", "anatomy", "chapter 1", "Spinal cord 1 (Dr. Azouny)", {"file": AZ / "spinal cord 1.mp4"}, [[49, 57]]),
    ("dr-ibrahim-el-azouni-anat", "anatomy", "chapter 1", "Spinal cord 2 (Dr. Azouny)", {"file": AZ / "Spinal cord 2.mp4"}, [[49, 57]]),
    ("dr-ibrahim-el-azouni-anat", "anatomy", "chapter 1", "Spinal cord 3 and medulla (Dr. Azouny)",
     {"file": AZ / "spinal cord 3 and medulla.mp4"}, [[49, 57], [71, 76]]),
    ("dr-naguib-el-husseiny-phys", "physiology", "sensations", "Lecture 1 (Dr. Nagib)", {"youtube": "https://youtu.be/kyWw4dbPAhA"}, []),
    ("dr-naguib-el-husseiny-phys", "physiology", "sensations", "Lecture 2 (Dr. Nagib)", {"youtube": "https://youtu.be/tD5RZPGk7Ik"}, []),
    ("dr-naguib-el-husseiny-phys", "physiology", "sensations", "Sensory receptors 1 (Dr. Nagib)", {"youtube": "https://youtu.be/Xszh4uAs98o"}, [[139, 144]]),
    ("dr-naguib-el-husseiny-phys", "physiology", "sensations", "Sensory receptors 2 (Dr. Nagib)", {"youtube": "https://youtu.be/-uma7XhtIGQ"}, [[139, 144]]),
    ("dr-naguib-el-husseiny-phys", "physiology", "sensations", "Pain 1 (Dr. Nagib)", {"telegram": 1685}, [[145, 168]]),
    ("dr-naguib-el-husseiny-phys", "physiology", "sensations", "Pain 2 (Dr. Nagib)", {"telegram": 1686}, [[145, 168]]),
    ("dr-ahmed-ammar-hist", "histology", "nervous tissue", "Classification of neuron & Nerve fiber (Dr. Ammar)",
     {"youtube": "https://youtu.be/pnanTke7MZA"}, [[11, 25]]),
    ("dr-abdullah-el-samahi-phys", "physiology", "sensations", "Pain 1", {"youtube": "https://www.youtube.com/watch?v=GABrSUDznYE"}, [[145, 168]]),
]


async def download(ids, out_dir):
    """RecordsBatch58ATM message id -> downloaded file (read only)."""
    sys.path.insert(0, r"C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\quizbot")
    from tg import connect
    client = await connect("voter2")
    got = {}
    try:
        ent = await client.get_entity("RecordsBatch58ATM")
        for m in await client.get_messages(ent, ids=list(ids)):
            d = out_dir / str(m.id)
            d.mkdir(parents=True, exist_ok=True)
            have = list(d.glob("*.*"))
            got[m.id] = have[0] if have else Path(await client.download_media(m, file=str(d)))
    finally:
        await client.disconnect()
    return got


def create():
    lines = [json.loads(x) for x in open(ROOT / "modules" / MODULE / "lines.jsonl", encoding="utf-8")]
    existing = {m["title"]: m for m in lectures.all_lectures(MODULE)}
    tg = [s["telegram"] for *_, s, _ in LECTURES if "telegram" in s]
    files = asyncio.run(download(tg, ROOT / "sources" / "records")) if tg else {}
    media, report = [], []
    for doctor, subject, chapter, title, src, pages in LECTURES:
        meta = existing.get(title) or lectures.create(MODULE, title, doctor, subject=subject, chapter=chapter)
        lid = meta["id"]
        if not meta.get("source"):
            if "youtube" in src:
                nxt = lectures.add(lid, MODULE, title, 16, url=src["youtube"], doctor=doctor)
            else:
                f = src.get("file") or files[src["telegram"]]
                nxt = lectures.add(lid, MODULE, title, 16, file=f, doctor=doctor)
            meta = lectures.load(lid)
            if "telegram" in src:
                meta["source"]["telegram"] = f"https://t.me/RecordsBatch58ATM/{src['telegram']}"
                lectures.save(meta)
        else:
            nxt = "lecture_links" if (lectures.folder(lid) / "raw.txt").exists() else "transcribe"
        if pages and not meta.get("ranges"):
            meta = lectures.set_ranges(meta, lines, pages, "claude-coarse")
        local = src.get("file") or (files.get(src.get("telegram")) if "telegram" in src else None)
        if local:
            ext = Path(local).suffix.lower()
            media.append({"lecture": lid, "file": str(local), "key": f"lectures/{MODULE}/{lid}/recording{ext}",
                          "field": "videoUrl" if ext in (".mp4", ".webm") else "audioUrl"})
        report.append({"lecture": lid, "title": title, "next": nxt, "transcript": (meta.get("source") or {}).get("transcript"),
                       "duration_s": meta.get("duration_s"), "pages": lectures.page_ranges(meta)})
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "media.json").write_text(json.dumps(media, indent=1), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for r in report:
        print(json.dumps(r, ensure_ascii=False))
    print(f"{len(media)} recordings to upload -> {SITE / 'media.json'}")


if __name__ == "__main__":
    {"create": create}[sys.argv[1]]()

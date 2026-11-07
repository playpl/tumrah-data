"""One-off live check of the timing pass on the 2026-11-07 spike lecture (not a unit test; run by hand).

    py tests/live_timing_spike.py prepare   job folder in agy-fleet/jobs/_txtiming with the spike transcript
    py tests/live_timing_spike.py check     the flow's own checker; prints counts only
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import checks  # noqa: E402
import lectures  # noqa: E402
from flows import lecture  # noqa: E402

SPIKE = Path(r"C:\Users\Ahmed\agy-fleet\jobs\_txspike\opus16")
JOB = Path(r"C:\Users\Ahmed\agy-fleet\jobs\_txtiming")
LID = "_txspike16"
STEP2 = ("transcript.txt in this folder is already written (step 1 is done; do not change it). Read prompt_full.md "
         "and do only its step 2 and the check.\n")

if sys.argv[1] == "prepare":
    lectures.save({"id": LID, "module": "year2-cns", "title": "spike", "lesson": None, "pdf_pages": None,
                   "transcribe": True, "source": {"file": str(SPIKE / "lecture.ogg")},
                   "duration_s": round(lectures.duration(SPIKE / "lecture.ogg"), 1)})
    shutil.copy2(SPIKE / "lecture.ogg", lectures.folder(LID) / "audio.ogg")
    prompt = lecture.TranscribeFlow().prepare({"payload": {"lecture": LID}}, JOB)
    shutil.copy2(prompt, JOB / "prompt_full.md")
    prompt.write_text(STEP2, encoding="utf-8")
    shutil.copy2(SPIKE / "transcript.txt", JOB / "transcript.txt")
    print(json.loads((JOB / "job.json").read_text(encoding="utf-8")))
else:
    errors = lecture.TranscribeFlow().check({"payload": {"lecture": LID}}, JOB)
    print("errors:", errors)
    heard = checks.paragraphs((JOB / "transcript.txt").read_text(encoding="utf-8"))
    raw = lectures.folder(LID) / "raw.txt"
    if raw.exists():
        timed = checks.paragraphs(raw.read_text(encoding="utf-8"))
        print("paragraphs", len(timed), "worker last", heard[-1][0], "timed last", timed[-1][0],
              "duration", lectures.load(LID)["duration_s"])
        print("worker vs timed (s):", [(a[0], b[0]) for a, b in zip(heard, timed)][::5])

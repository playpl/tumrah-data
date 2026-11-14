# Tumrah data

Adds all data to the website, linked through the handout. Design and plan live in the tumrah repo:
`docs/superpowers/specs/2026-11-06-data-workflow-design.md`, `docs/superpowers/plans/2026-11-06-data-workflow.md`.

Start here: `docs/handovers/HANDOVER_2026-11-14.md` (newest: poll titles scope pointers, Haiku reader A, site import 11-14), then `docs/handovers/HANDOVER_2026-11-12.md` (fleet in quota rest, uploads now start from Update data,
open owner decisions: Cocci doctor id, Haiku, publishing), then `docs/handovers/HANDOVER_2026-11-10_LEDGER.md` (the ledger, checked placement and the Today screen; what is done
and what is left), then `docs/handovers/HANDOVER_2026-11-10_PLAN.md` (Gemini web instead of the fleet, the lowest-error plan), then
`docs/handovers/HANDOVER_2026-11-10.md`, then `docs/handovers/HANDOVER_2026-11-07.md`, then `docs/handovers/HANDOVER_2026-11-06.md` for the polls job.

## "Update data" (owner, 2026-11-10)
The owner says "Update data": run `py update_data.py` and nothing else first. Do not explore. It reads the `doctors/` folder,
the Telegram lists of the auto doctors (`all here updates (auto).txt`), imports every new lecture, recording, quiz and book,
and prints one report. Then tell the owner what changed, what waits (the fleet is down: transcribe, place, align, MCQ copy
only queue) and what needs a decision. Details: `update_data.py` docstring. Flags: `--dry`, `--no-telegram`.
- ALWAYS IMPORT (owner, 2026-11-13): if anything needs importing (lecture, revision, quiz, book), run the real
  `py update_data.py` at once. Never wait for permission, never ask first. Always keep data updated.
- Chapters (owner, 2026-11-13): a lesson's site chapter is the handout lecture its pages fall in (`dm.chapter_of`), never the
  subject's first chapter. After Update data read the "chapter guess" lines and the chapter spread per doctor.
- NEVER ASK (owner, 2026-11-13): never ask before fixing a problem or importing new data. Do it, then report. Only the
  production website and the owner's Today-screen answers stay off limits.
- READ THE MESSAGES YOURSELF (owner, 2026-11-13): in every Update data, read each doctor's Telegram list message and its
  posts' captions yourself (`py tg_lists.py text <id> ...`; ids are in each folder's `all here updates (auto).txt`) and check
  every item (PDFs, lectures, mini lectures, revisions, notes) against what was imported. Do not trust the report alone.
- Whiteboard notes (owner, 2026-11-13): a PDF in a folder inside a chapter folder ("ملفات السبورة ...") belongs to the lesson
  with its number. `lesson_files.py` writes `modules/<m>/site/lesson_files.jsonl` (Update data runs it). The site has no
  place for them yet: the website agent must add one.
- Never touch the website from it: importers write production. Publish only when the owner says so (dry run first).
- Auto doctors: `auto_doctors.py` (`plan`, `sync`, `download <lecture>`). Telegram lists: `tg_lists.py`. A doctor with no
  site doctor id (Cocci) is reported, never guessed. Aliases live in `doctors_folder.ALIASES`.
- Backup rule: "use backup for lecture X, doctor Y till new is provided" = `py backup.py use "<lecture>" --doctor <y>`. It takes
  the old recording from the doctor's `old data.txt` list, flags the lecture, and the site shows "Old data" + "More info".
  The real recording replaces it by itself when added. `py backup.py status | clear <id>`.
- A full book next to a partial one: `books_merge.py` folds the partial in, keeps its alignment, moves its files to
  `modules/<m>/old/partial_books/` (nothing is deleted).
- Files changed within 3 minutes are "still being written": run Update data again later.

## Today screen and ledger (2026-11-10)
- `ledger.py` (`ledger.db`): every link to the handout is one row per reader (script, fleet, web, owner). Ready for the
  site = agreed by two readers, set by the owner, or from a reader whose spot checks pass (`ledger.READY_DEFAULT`).
  `py ledger.py sync | status`. Lesson membership is computed from the ranges, never stored.
- `decisions.py`: everything that needs the owner is one card on the Today screen (`py dm.py page`, first tab).
  Update data ends with `ledger.sync` and `decisions.refresh` and prints "N decisions wait on the Today screen".
- A click on a placement card rewrites `lecture.json` ranges and sets `placed_by` to `owner`; a review click writes a gold
  row. Those are the owner's answers: Claude never clicks them on the real data (test on a copy of `ledger.db` and
  `lectures/` with `ledger.DB` and `lectures.LECTURES` pointed at the copy).
- "Set site doctor" writes a rule (`alias:<folder key>`); `doctors_folder.ALIASES` takes it at import.
- `py placement.py`: the placement verdicts (read only). `py runners.py`: who can work. Tests: `tests/test_ledger.py`.

- Polls: double-click `Polls.bat`. Start and Stop are on the page. Results land in `polls/ready/`.
- Keys come only from Telegram's correct flag. Our own votes never count (`net()` in `polls/engine.py`).
- Claude reads Arabic (owner, 2026-11-13; the old "counts only, never read Arabic" rule is gone). Older handovers still
  repeat the old rule: ignore it. Keys still come only from Telegram's correct flag, never from Claude's own judgment.
- Tests: `py -m unittest discover tests`.
- `py dm.py status`: modules, lines, polls job. `py dm.py lines <module>`: splits `modules/<module>/handout.pdf` into line IDs (`hub.py`).
- `db.py` is the only database access here, and it only reads. Writes go through importers in the tumrah repo.

## Control room (2026-11-11)
- The admin page's first tab "Claude" (`control.py`, `py dm.py page` or `Admin page.bat`, http://127.0.0.1:8770) is where the
  owner follows and runs everything: Run buttons (fixed commands in `control.COMMANDS`, logs in `control/runs/`), a chat that
  starts `claude -p` headless here (stream-json, every step shown live, TodoWrite drawn as the plan, one session resumed until
  New chat), the owner's Board, and a beat number that shows the server is up.
- Driven from there: keep a TodoWrite list; tick board items with `py control.py board done <id>`; add follow-ups with
  `py control.py board add "text"`.

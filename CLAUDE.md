# Tumrah data

Adds all data to the website, linked through the handout. Design and plan live in the tumrah repo:
`docs/superpowers/specs/2026-11-06-data-workflow-design.md`, `docs/superpowers/plans/2026-11-06-data-workflow.md`.

Cloud (GitHub Actions, year 1 records off the PC): `docs/handovers/HANDOVER_2026-11-17_CLOUD.md`.
Spine rebuild: `docs/spine/HANDOVER.md`.

Start here: `docs/handovers/HANDOVER_2026-11-14_EVENING.md` (site data rework, hand-written mother_lists.json, balanced questions), then `docs/handovers/HANDOVER_2026-11-14.md` (newest: poll titles scope pointers, Haiku reader A, site import 11-14), then `docs/handovers/HANDOVER_2026-11-12.md` (fleet in quota rest, uploads now start from Update data,
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
- Chapters (owner, 2026-11-14; replaces the 2026-11-13 handout rule): a lesson's site chapter is the item of the doctor's Telegram
  list (the "mother message") it is posted under ("- Spinal cord" with parts 1-3 = chapter "Spinal cord"). Since the evening
  of 11-14 it is written BY HAND in `modules/year2-cns/site/mother_lists.json` (see MOTHER MESSAGES BY HAND below);
  `dm.list_chapters` code matching is only a fallback for a lecture missing there. Never from the handout or a guess.
  Mini lectures and revisions sit with what they cover.
- Questions per lesson (2026-11-14): students see `Question.lesson` (one lesson per question). `fast_lessons.build` spreads a
  shared question to the least loaded lesson. Every site import = lessons, importSfQuestions, importHubData pointers,
  apply_tiers, then recomputeLessonExtras for ALL published CNS lessons. Held lectures (duplicates) stay drafts.
- NEVER ASK (owner, 2026-11-13): never ask before fixing a problem or importing new data. Do it, then report. Only the
  production website and the owner's Today-screen answers stay off limits.
- READ THE MESSAGES YOURSELF (owner, 2026-11-13): in every Update data, read each doctor's Telegram list message and its
  posts' captions yourself (`py tg_lists.py text <id> ...`; ids are in each folder's `all here updates (auto).txt`) and check
  every item (PDFs, lectures, mini lectures, revisions, notes) against what was imported. Do not trust the report alone.
- Whiteboard notes (owner, 2026-11-13): a PDF in a folder inside a chapter folder ("ملفات السبورة ...") belongs to the lesson
  with its number. `lesson_files.py` writes `modules/<m>/site/lesson_files.jsonl` (Update data runs it). The site has no
  place for them yet: the website agent must add one.
- Never touch the website from it: importers write production. Publish only when the owner says so (dry run first).
- MOTHER MESSAGES BY HAND (owner, 2026-11-14 evening, angry): from a doctor's Telegram list message you care ONLY about
  lectures, mini lectures, revisions and their records. Never PDFs. Read the message yourself (`py tg_lists.py text <id>`),
  then write by hand `modules/year2-cns/site/mother_lists.json`: per doctor, each list item = one chapter (in list order),
  and under it its lectures (the item's parts), mini lectures and revisions. Not code matching, not guesses. `site_lessons.py`
  takes chapter, name, kind, covers and order ONLY from that file; a lesson missing from it is reported. Update it by hand in
  every Update data when a list changes (new lecture = new line under its item).
- EXACT TO THE MOTHER MESSAGE (owner, 2026-11-15): after editing `mother_lists.json` run `py mother_check.py`; it must
  print "exact" (chapters = the list's lecture items in order and words; every lecture/mini/revision post is in the file).
  A doctor's wrong link (e.g. Azouny's Medulla Part 3 linked to 1708, really post 1709) is fixed by hand in
  `sources/lists/link_fixes.json` (find the right post by its caption); Update data prints "BROKEN LINK" for a post an
  item links twice. A sync that was stopped mid-download is finished by the next sync (`auto_doctors.finish_interrupted`).
- List PDFs (owner, 2026-11-14, evening; replaces the morning rule): ONLY THE OWNER ADDS PDFs. Update data reports "PDF post N
  ... not in the folder"; that is information only. Never download, open, compare, file or use a list PDF. Books are only what
  the owner put in the doctors' folders.
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

## Mother trees (owner, 2026-11-17)
- Both years' doctor lists are in `spine/tg/trees.json` (the trees the owner pasted). Start: `docs/spine/HANDOVER.md`.
- Year 2 "Old data" lists are FALLBACK only: never imported unless the owner names lecture and doctor
  (`backup.py use`). A doctor's `old data.txt` only tells `backup.py` where the old list is.
- Year 1 (channels `ZAG59_Anatomy`, `ZAG59_physio`, `ZAG59_Histo`, `ZAG59_bio`; 20 lists): ALL of it is old data
  and all of it is to be imported; the website needs a note that says so. Lists: `py tg_lists.py fetch -c <channel>
  <ids>` -> `sources/lists/<channel>/`; maps: `py -m spine mother run --year 1`. Never put a `ZAG59_*` link in
  `doctors/`: the old flow reads only the number and would open a `RecordsBatch58ATM` post.
- A lecture whose doctor has no site doctor id stays off the site (`site_lessons.py` prints "NO SITE DOCTOR").
- One Telegram reader at a time: `tg_lists.py fetch` during Update data locks the session ("database is locked").

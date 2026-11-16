# Handover 2026-11-14 evening (read first; then HANDOVER_2026-11-14.md)

Owner: "All the data on the website is completely messed up. Fix it... I can't stand that lesson having 500 questions while
other having 2." Then: chapters and lectures BY HAND from the mother messages, PDFs ignored, only the owner adds PDFs.
Then: take the Today-screen decisions, then resume the fleet (`py fleet_pause.py resume`).

## 1. What was wrong
- Students see a lesson's questions by `Question.lesson` (one lesson per question; `courseWorkspacePreload`). The
  `LectureQuestion` rows (required/doctor/extra) are not served to students at all.
- `fast_lessons.build` put each question in `homes[0]`: the first lesson whose pages hold its line. Naguib's 54-page
  "Lecture 1" took 1,366; Elsamahy's Pain 2 got 2 (Naguib's Pain 1 covers the same pages); 50 CNS lessons had 0.
- 3,100 local pointers were never imported (live had 1,753 CNS pointers); extras were recomputed only for lessons that got
  a tier import.
- Mother messages vs data: Azony Spinal cord part 2/3 titles swapped (post 1650 = part 2: the transcript opens "the second part
  of the lecture"; post 1673 = part 3: "last time we did not finish spinal cord"); duplicate lessons (Amr cns-074/cns-086
  Spinal revision, cns-075/cns-097 Diencephalon); Basel's revisions in word-matched chapters ("Mid Revision" under Mid brain,
  "Brain stem" under Brain barriers); Elsamahy "Pain control Revision" filed as a mini lecture.

## 2. What was done
- `modules/year2-cns/site/mother_lists.json`: written BY HAND from the 9 lists (Cocci has no lectures). `site_lessons.py write`
  takes chapter, name, kind, covers, order only from it (lecture.json title/kind/covers follow it) and prints
  "NOT IN mother_lists.json" for anything missing. Backups of the edited lecture.json: `modules/year2-cns/old/lecture_json_before_list_fix_2026-11-14/`.
- Held as duplicates (lecture.json `hold`): cns-086 (of cns-074), cns-097 (of cns-075); cns-016 already. Held lectures are
  skipped by site_questions, fast_lessons and apply_tiers. On the site the 3 lessons are set to `draft`
  (undo: `C:\Users\Ahmed\Desktop\tumrah for med\backups\hide_duplicate_lessons_2026-11-14.json`).
- `fast_lessons.build`: a shared question goes to the least loaded of its lessons (ties: narrowest).
- Interim pages (`claude-coarse`, the fleet's placement replaces them) for the 7 lessons with no transcript yet: cns-091
  108-112, cns-092 33-35, cns-102/103 161-168, cns-104/105/107 169-174.
- Today screen (owner: "you will take decisions for me"): all 13 placement cards + the bulk card answered "use the reading"
  (recording-based pages), applied with `placed_by: claude-reading` (not owner). cns-085 kept continuous 175-186 (its reading
  runs from "THE REFLEX ACTION" to "visceral spinal reflexes"; the cut left a gap). Ledger backup before:
  `backups_ledger/ledger_before_claude_decisions_2026-11-14.db`. NOT decided (rules): 128 answer-key conflicts (keys only from
  Telegram's correct flag), 1,166 reader conflicts and the spot check (owner gold), Cocci (no site doctor exists).
- Site imports (production, undo files in `tumrah for med\backups` and `modules/year2-cns/backups`): lessons (103),
  importSfQuestions, importHubData pointers (`--source script-index-2026-11-14`), apply_tiers, recomputeLessonExtras for every
  published CNS lesson. Recipe: `$TEMP/claude/s/import_all.sh` pattern, written into CLAUDE.md ("Questions per lesson").
- Narrowing "CNS تأسيس 1" to its recording's pages moved ~630 questions on pages no lecture teaches yet (motor, limbic,
  cerebellum physiology) out of the lessons; importSfQuestions sets them to draft. They return when those lectures exist.
- Six list PDFs were downloaded by mistake and deleted unused (owner: only he adds PDFs). Rule changed in CLAUDE.md + memory.

## 3. Left
- Fleet resumed after the import (transcribe 7 lessons + duplicates' pieces, place, pointers_one, MCQ copy).
  When transcripts land: placement replaces the claude-coarse pages; then rerun the import chain.
- Website session: serve `LectureQuestion` (required/doctor/extra) on the lesson page, or allow one question in several doctors'
  lessons; today a shared question reaches one doctor's students only. Also `WEBSITE_TASKS_2026-11-13.md` (Cocci, whiteboard files).

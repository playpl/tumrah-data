# What the data side needs from the website repo (for the website session)

Written 2026-11-17 by the tumrah-data session. The data side cannot build these: the website repo
(`C:\Users\Ahmed\Desktop\tumrah`) had uncommitted work from another session in `backend/src/scripts/importHubData.ts`
itself, and website code belongs to the website session. Each item: a branch, a dry run first, an undo file like the
other importer kinds. The data side has its half ready or ready to write once the field exists.

## W1. `importHubData lessons`: a per-row `status`, and `--only-keys`
- Row field `status`: `published` (default, today's behaviour) or `draft`. A draft row keeps its lesson but hides it.
- `--only-keys lecture:a,lecture:b`: import only those rows of the file (the rest of the file is still validated).
- Why: Telegram deletions and replacements are mirrored as drafts, never deletions (owner: "Hide as draft").
- Data side: `spine/tg/flow.py` already finds edits and deletions per list and applies the hold rule
  (`spine.tg.mother.held`: two fetches 10 minutes apart; more than 3 lessons or 20% of a doctor waits for the owner).
  It only reports them today.

## W2. `importHubData lessons-status --keys a,b --status draft --reason telegram-delete`
- Flips only `status` of the named lessons, writes an undo file, prints `{changed, unchanged, missing}`.
- Data side: the same flow calls it for a deletion that passed the hold rule, with `--reason telegram-delete`.

## W3. Whiteboards: a `resources` kind into `CourseResource`
- Row: `{key: "file:<lecture id>:<n>", lesson: "lecture:<id>" (sourceRef), title, file: "r2:<key>", type: "pdf"}`.
- `uploadLessonMedia.ts` `TYPES` gains `.pdf .jpg .png` (whiteboards are uploaded as they are, never re-encoded).
- `CourseResource` today has `status: pending|ready`, no lesson link: it needs `lesson` (ObjectId) or `sourceRef`.
- Data side: `lesson_files.py` already writes `modules/year2-cns/site/lesson_files.jsonl` (2 files today: cns-076
  "6- Ascending Tracts .pdf", cns-077 "7- Ascending Tracts.pdf").

## W4. `lectures`: batch mode, one file for many lessons keyed by `sourceRef` (transcript links of Phase 2).

## W5. `AcademicModule.university` (`ZU|NU`, default `ZU`): the NU modules (`nu-year1-musculoskeletal`, Tumrah book).

## New (2026-11-17): a deadline date per lesson
- The Tumrah book session (tumrah-book repo) gives every lesson a deadline (`modules/<code>/schedule.json` there,
  and `exports/<module>/READY.jsonl` one line per signed lesson: `{lesson, deadline, bundle_sha256, signed, at}`).
- The site has deadlines only on Camp and Race, none on Lesson. Needed: `Lesson.deadline` (date), shown to students,
  and the lessons importer accepting a `deadline` field per row.

## New (2026-11-17): year 1 is old data
- Every year 1 lesson is imported with `oldData: true` (74 lessons on 2026-11-17). Students need a note on the
  module or lesson page that all first-year data is old data (owner, 2026-11-17).
- Biochemistry: the MSK curriculum module exists, but `doctorRoster.ts` hides biochemistry from MSK students (owner
  rule of 2026-11-05). 72 biochemistry records wait on the data side until the owner says otherwise.

## W6 (2026-11-21): question grades and a file question's poll votes
- The owner's grades (CLAUDE.md 2026-11-20): 1 the lesson doctor's own quizzes, 2 his MCQ files (1 when that lecture
  has no quiz from him), 3 other doctors' MCQ files, 4 polls, 5 archive (the AI-questions reservoir, not lesson
  questions). Data side: `py -m spine questions grades` writes `modules/<m>/site/grades.jsonl`, one row per site
  question `{source_id, lesson, grade, why, poll}` (CNS 2026-11-21: 944 grade 1, 147 grade 2, 11,444 grade 4; MSK 388
  grade 4).
- Needed: `Question.grade` (1-5) set by an importer from that file (keyed by `source_id`), and lessons sorting their
  questions by grade; `poll` (`bank:<id>` or `poll:<chat>:<msg>`, 888 of 1,091 quiz/file questions) so a quiz or
  file question shows the class's votes of the same poll.

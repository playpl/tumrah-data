# Handover and plan, 2026-11-10 evening: best routes to the lowest error rate (Gemini web instead of the fleet)

For a stronger model with no memory of this work. Read `CLAUDE.md`, then `HANDOVER_2026-11-10.md` (state this morning),
then this file. This file is a plan to improve, not a finished design: challenge it.

## 1. The goal (owner, 2026-11-10)
"Get the best results possible from the AI in managing all the data, and achieve the lowest error rate possible."
Users report many mistakes on the site. The Antigravity fleet is dead, so Gemini on the web does the AI work.

How the data works: the handout (College Book) of a module is the root. Every handout line has an ID
(`modules/<m>/lines.jsonl`, 9,837 lines, 456 pdf pages for `year2-cns`). Everything else is linked to handout lines:
- a lesson (one doctor's recorded lecture) -> the handout pages it teaches (`lectures/<id>/lecture.json` `ranges`)
- a question -> the handout lines it tests (pointer)
- a doctor's book block -> the handout lines it teaches (alignment)
- a part of a lecture recording -> the handout lines it explains (lecture links)
The site decides what belongs to a lesson by these links: a lesson's questions are the questions pointing into its
pages. So **one wrong lesson range or one wrong pointer spreads to many wrong items**. The owner's method to cut errors:
tell the AI exactly which subject, doctor and handout area it works on (for example only the Pain lesson's pages).

## 2. Rules that bite (owner)
- Claude never reads question text or Arabic: counts, ids and structure only. Gemini may read them (code passes them).
- Answer keys come only from sources (Telegram's correct flag, QuizBot, a book's own key list). Never from an AI.
- **This repo does data only. Never write to the website** (no importHubData / importSfQuestions / importSiteBook /
  apply_tiers / uploadLessonMedia). Another session of the owner imports. Report which files are ready.
- Models: transcription = 3.5 Flash-Lite. Thinking jobs = **3.8 Flash with thinking on** (`gweb ask -t`; owner:
  "we will use 3.8 flash, no more Argon. And set it on high"). **Never 3.1 Pro ("too stupid"), never 4 Carbon ("too
  expensive"), no Argon.** `gemini_run.py` refuses other models (`ALLOWED_MODELS`) and adds `-t` to non-Lite calls.
- Ask before any Claude Haiku batch (cost). Elazouny's books are never aligned. Highlights are skipped.

## 3. Tools
- **gweb** (`C:\Users\Ahmed\gemini-web\gweb`, skill `gemini-web`): Gemini web on the owner's subscription, 4 accounts
  of one Google session: `zero` /u/0, `work` /u/1, `personal` /u/2, `other` /u/3. `gweb status` shows each account's
  5-hour usage. Cookies were re-imported today from `Downloads\Gemini Cookies` (all four exports are the same session).
  Runs are logged in `gemini-web\runs\` (prompt, answer). Calls use `--temporary`, so they are **not in the owner's
  Gemini history** (the owner asked about this: say so when reporting usage).
- **`gemini_run.py`** (new today, uncommitted): runs queue jobs through gweb. Each job becomes one self-contained prompt;
  Gemini answers compactly (labels like `48.12` = pdf page 48 line 12); code rebuilds the flow's own output file from
  the answer, copying all verbatim text itself; the flow's own checker (`flows/*.py`, `checks.py`) passes or fails it.
  Commands: `pieces` (transcription), `place`, `books`, `links`, `status`. Log: `jobs/gemini_run.log`.
- Queue: `queue.db` (`queue_db.py`); flows in `flows/` (`REGISTRY`); `haiku_run.py` is the older outside-runner.

## 4. Measured today (facts, not guesses)
- Transcription, 3.5 Flash-Lite, one 5-minute piece: asked for timestamps it condensed the speech to ~280-360 characters
  a minute (3 of 3); asked for plain paragraphs ~545 a minute (3 of 3; the fleet's passed transcripts: 530-1285). So it
  writes paragraphs and code sets each paragraph's time inside the piece by character position (piece offsets exact).
  Gate: under 450 chars/min = retry. 3.8 Flash answered audio only with error cards.
- Quota: ~20 Flash-Lite pieces moved an account's 5-hour usage ~2%; ~10 Carbon calls with the whole 470 KB handout
  attached took 3 of 4 accounts to 100% in ~20 minutes (back at 21:53 `zero`, 22:27 `personal`, 23:30 `other`).
  An account at 100% stops everything on it, transcription too. 3.8 Flash cost per call is **not measured yet**.
- `work` returns error cards for 3.8 Flash (and Argon, older notes); an error card rests the account 5 minutes, so
  `gemini_run.py` keeps heavy calls off `work` (`HEAVY_SKIP`) and only sends them to accounts under 80%.
- Argon is in the owner's browser picker ("4 Argon - Code & analysis") but **not** in the model list the server sends
  gweb (it sends `gemini-carbon` "4 Carbon" id `95a4c0abcba24364` in that slot). Same session cookies. gweb resolves
  models by id from that list, so Argon cannot be called until its model id is known (read it from the owner's browser
  page or network request when Argon is picked, then send that id directly). `gemini-argon` worked until 2026-11-09.
- Book alignment, candidate pages: showing only the ~50 handout pages that share rare words with the book pages kept
  97-100% of the links Carbon found with the whole handout. Restricting to the book's subject pages (from the handout's
  lecture list `modules/year2-cns/old/agent-lecture-list-2026-11-08/reference.json`) kept 100% of the links in 3 of 4 jobs;
  in the 4th (Nagib physiology p21-30) 10 of 307 links were on histology pages: almost surely wrong.

## 5. State now (about 20:40)
- Transcription: 292 of 353 five-minute pieces passed (only `work` has quota). 53 of 64 lectures have `raw.txt`.
- Lesson placement (`ranges`): 46 lectures placed today by 4 Carbon in one call (title, subject, doctor, chapter, the
  doctor's chapter lessons, the already placed lectures; no transcripts). `placed_by`: agent 50, claude-coarse 9,
  claude 4, covers 1. **None of it is verified.** The 9 "claude-coarse" ones are old coarse ranges (for example Nagib
  "Lecture 1" spans 13 separate ranges).
- Lecture links: 14 lectures linked (fleet, 11-07/08). 29 lectures transcribed and queued for `links`.
- Book alignment: 43 of 76 book jobs passed in all (fleet earlier + 9 by Carbon today, unscoped); 33 queued.
- Question pointers: almost all come from `fast_lessons.py`, an IDF word-overlap script (no AI reading): 3,506 kept,
  3,325 weak matches dropped, 7,799 outside the named lessons. Only 31 pointer jobs were ever done by AI (fleet).
  **This is the most likely source of the mistakes users report.** The AI flow already exists (`flows/pointers.py`,
  with a lecture-scoped mode: only that lecture's pages, `other_lecture` when not taught there); it only lacks a
  Gemini adapter.
- MCQ copy (24 jobs): not built for Gemini. Cover (14): not looked at.
- Pushed to the site today by this session (before the owner moved site work elsewhere): lessons with ranges and
  recordings (undo files `hub_lessons_2026-11-10T17-30-15-043Z.json`, `...T18-08-45-800Z.json` in
  `Desktop\tumrah for med\backups`), Ammar's book `ammar-hist-1` (20 pages, partial), CNS questions (862 new,
  2,770 updated; backup `modules/year2-cns/backups/cns_questions_2026-11-10T18-27-35-130Z`), Required/Doctor lists
  (Elsamahy's Pain QuizBot test `t.me/QuizBot?start=03tAzRTl`, 24 keyed, filed with `own_questions.py`).
- **Still running in the background** when this was written: `gemini_run.py pieces --no-cut --workers 3` and a chain
  `gemini_run.py links --workers 2 --model flash` then `books --workers 2 --model flash`, waiting for an account
  under 80% (starts by itself about 21:53). To stop: kill the `python.exe` whose command line holds `gemini_run.py`
  (then `py -c "import queue_db; queue_db.Queue().recover()"`). Decide whether 3.8 Flash should do these at all.

## 6. Proposed routes (improve these)

### Principles
1. **Order by dependency: placement first.** Every other link is judged against a lesson's pages. Fix placement before
   spending quota on pointers, links or tiers, or the errors are baked in.
2. **Scope every call as narrowly as the data allows**: one subject, one doctor, one lesson's pages; show only those
   handout pages (with line labels) and say so in the prompt.
3. **Big chunks inside one scope** (owner: give Argon a huge chunk at once): all lessons of one subject in one placement
   call; all candidate questions of one lesson in one pointer call (split only when the answer would be too long).
4. **The AI chooses, code copies.** Answers name labels; code copies every verbatim text from the source and runs the
   flow's own checker. Scripts only pick which pages to show, never a match.
5. **"Not found" beats a guess.** Every prompt allows `extra` / `other_lecture` / `not_in_book`.
6. **Measure, don't assume.** Per link type, an audit sample re-done independently (different chunk order, ideally a
   different model once Argon is back); report agreement as the error estimate; disagreements go to a third "judge"
   call that sees both answers and the pages, or to the owner.
7. **Quota is part of the design.** Small attachments (subject or lesson pages, not the 470 KB handout); measure each
   model's cost per call; keep `work` for transcription; never let an account reach 100%.

### Route A. Lesson placement (verify and fix)
- Per subject (histology, anatomy, physiology), one call: the subject's handout pages with labels, every lesson of that
  subject (doctor, chapter, the doctor's lesson order, title) and, for each lesson, its transcript or a summary of
  what the doctor covers in order (most lectures now have `raw.txt`). Ask for ranges that start and stop where the
  doctor really starts and stops; a doctor's lessons follow each other without overlap.
- Compare with today's ranges; differences go to a judge call or the owner (`placed_by "owner"` is never overwritten).
- Revisions and mini lectures follow what they cover (`covers`); check those after.
- Open: 9 "claude-coarse" ranges; Nagib "Lecture 1/2" are multi-topic and may need several ranges by design.

### Route B. Question pointers (replace word overlap)
- Per lesson: candidates = every question whose label (handout lecture / subject) overlaps the lesson's pages, plus the
  doctor's own questions (MCQ book, quizzes), not only today's word-overlap keeps (the 3,325 weak matches are still
  candidates). Show the lesson's pages only; ask per question: the smallest lines that teach the keyed fact, `partial`,
  or `other_lecture`. Use `flows/pointers.py` and `checks.check_pointers` unchanged.
- Then `fast_lessons.py build` must prefer the AI pointer over the word-overlap one (and drop `other_lecture` from that
  lesson); `tiers.py` follows.
- A question found in no lesson: one more call scoped to its subject's pages (it may belong to a lesson not yet placed).

### Route C. Lecture links (transcript parts -> lines)
- Per lecture, scoped to its (verified) pages: `gemini_run.py links`. Today it lays out `clean.txt` = `raw.txt` unchanged
  and asks no misheard-word fixes; consider a separate fixes call (medical terms misheard by Flash-Lite), which also
  helps pointers that use the transcript (Azouny's Required = transcript-linked).

### Route D. Book alignment
- Per job, the book's subject pages narrowed to candidate pages (built today in `gemini_run.py books`). After Route A,
  narrow further to the doctor's lessons' pages plus neighbours, but a doctor's book covers more than his recorded
  lessons, so keep "extra" honest.
- Redo the 9 jobs Carbon aligned today without subject scope (`jobs/books/*` with notes `gemini web gemini-carbon`).

### Route E. Transcription quality
- Done by Flash-Lite with a density gate only. Audit idea (counts only, no reading): transcribe a sample piece twice and
  measure word agreement; low agreement = re-do. Misheard terms: Route C fixes.

### Route F. Audit and report
- One audit job per link type (placement, pointers, book blocks, lecture parts): 5% sample (`config.json`
  `audit_sample`), independent call, agreement rate, list of disagreements. Only data whose audit passes a threshold
  the owner sets is reported as ready for import.

## 7. Decisions for the owner
- (Settled: 3.8 Flash with thinking for every thinking job; Argon is dropped.)
- Audit threshold for "ready to import" (for example 95% agreement).
- 133 form-key conflicts (MSK forms) still wait for the owner; never settle one.
- Cocci (no site doctor), Basel/Mahmoud books, 30 Telegram PDFs in no doctor folder (from the morning handover).

## 8. Files touched today (all uncommitted in this repo)
`gemini_run.py` (new), `sources/quizbot/elsamahy/play_list.json` (Pain test added), lecture.json ranges of cns-019..064,
`jobs/` (job folders, `gemini_run.log`), `modules/year2-cns/site/*` (rebuilt lessons, questions, tiers).
Memory notes added: `gemini-model-rule`, `no-website-writes`, `goal-lowest-error`.

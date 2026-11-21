# What is left of the owner's plan (2026-11-21)

The plan = the owner's master prompt "The Ultimate Data Orchestra" (`docs/spine/OWNER_WORDS.md` message 3), as changed by
his later answers (`CLAUDE.md`, memory, `docs/spine/PLAN.md`). Item-by-item state on 2026-11-18:
`docs/spine/COVERAGE_2026-11-18.md`; what happened since: the "Progress" section of `HANDOVER_2026-11-18_MEGA.md`.
This file is the starting point for a new session. Branch `spine-rebuild`, push to `origin main`.

## Prompt for the new session (copy and paste)

```
Read CLAUDE.md, then docs/handovers/PLAN_REMAINING_2026-11-21.md in tumrah-data. Check section 0 (what may still be
running from the last session), then work the streams in order. Each stream ends with tests green
(py -m unittest discover tests), a commit, a push and one line under "Progress" at the bottom of this file.
Readers: Gemini web 4 Hydrogen for Arabic and judgement work (capped account -> 3.5 Flash-Lite until renewal); the fleet
only for code-checkable work (transcription pieces); Haiku last, paid, estimate first. Never ask before fixing or
importing; ask only the owner questions in section 3, and only when a stream reaches them.
```

## 0. State at hand-off (2026-11-21, about 01:40 UTC)

Running when this was written (check before starting anything that uses the same readers):
- Gemini web: `py -m spine p1 run year1-musculoskeletal --workers 4` (MSK books -> handout, 121 jobs), log
  `logs/p1_msk_2026-11-21.log`. Then `py -m spine p1 accept year1-musculoskeletal`.
- Fleet (zero, work, personal): `py -m spine records hear2 --via fleet --accounts zero,work,personal`, log
  `logs/hear2_fleet_2026-11-21.log`; 444 pieces queued, 32 transcripts finished at 01:30, 0 check failures. Account
  `other` fails sign-in (`py C:\Users\Ahmed\agy-fleet\fleet.py login other`).
- Site import `logs/site_import_2026-11-21_b.log` (cns-197/198 audio).
Numbers at hand-off: seg 73 accepted, 10 rejected, 4 disputed, 6 stale of 93; MSK 39 lessons, 388 questions live
(296 pointed), about 600 MSK questions waiting for a lesson; all recordings uploaded (year 2 and the 42 MSK records).

## 1. Streams, in order (what, where, done when)

### S1. Transcripts complete and checked (master prompt 3A "transcription")
- Fleet run above finishes the year 2 lectures with no `raw.txt` and the six looped pieces
  (`backups_pre_update/rehear_loops_2026-11-21/`).
- Year 1: `py -m spine records transcribe --via browser` for the MSK Telegram records (21; YouTube ones have captions).
- No second hearing of fleet pieces (owner Q4: "None"); the code checks (length, loop, 2400 chars/min) are enough.
- Quality report fixes left (`docs/spine/quality_2026-11-20/REPORT.md`): worst YouTube captions re-heard (cns-006, 001,
  158, 003, 002); a gold set of read paragraphs per book as a third check beside A=B agreement.
- Done when: every recorded lecture of both years has a transcript (or a logged failure); `dup_scan.py` shows no
  40+ word repeat.

### S2. Segmentation finished and primary (master prompt 4, step 2)
- `py -m spine seg jobs` (new transcripts and the 6 stale), `seg run --workers 4 --wait`, `seg collect`.
- The 10 rejected and 4 disputed: read them (Claude reads Arabic), fix the cause (prompt, scope, book table lines),
  re-run; what still fails becomes a Today card.
- Primary switch (PLAN.md Phase 2 step 5): the Today screen and the site's `LectureLink` rows read
  `lectures/<id>/spine/`; `clean.txt` and the old placement flow retire. The 71 `claude-coarse` CNS placements are
  replaced by the ranges the segments give.
- Year 1 (MSK): same flow once S3 accepts the MSK books; MSK lessons' handout ranges then come from the segments, not
  `modules/year1-musculoskeletal/site/placement.json`.
- Done when: every lecture with a transcript and a book is accepted or a Today card; `seg audit` zero backward jumps;
  `parity p2` written; the site import carries the new links (dry run first).

### S3. Books -> handout (master prompt 4, step 1)
- CNS tail: about 470 open sentences (`py -m spine p1 jobs year2-cns`, `p1 run`, `p1 accept`), the 200-link audit per
  book (126 read, 0 wrong), `parity p1`, then `config.json` `"spine": {"p1": "primary"}`.
- MSK: the run above; then the audit. Elazouny's books are SKIPPED in every module and year (owner Q3); his lectures
  are segmented against the handout itself (`seg` with `handout=True`).
- Known limits: `mossafer-anat-full` "P a g e | 99" lines; Ammar's tables (splitter).
- Done when: every content sentence of every book has an accepted edge or a logged "no handout match"; audits read.

### S4. Questions (master prompt 3C and 4 step 3; the owner's grades, CLAUDE.md 2026-11-20)
- Grades on every bank row: 1 the doctor's own quizzes, 2 his MCQ files (1 when that lecture has no quiz from him),
  3 other doctors' MCQ files, 4 polls, 5 archive. Every quiz/file question matched to its poll for votes.
- MCQ files: extract (old flow did CNS books), link to doctor and book, archive the raw file. The link trees
  (`zagexam59` 503, `ZMSUMcqs58` 2098) classified by position and caption; unclear = Today card.
- Every question linked to handout sentences (scope by header/tree position, BM25, closed window; Gemini reads the
  hard ones). The "no quiz outside a lecture" check = 0.
- MSK: `msk_questions.py` (polls, grade 4): 388 live; 508 wait with their handout link in
  `modules/year1-musculoskeletal/site/msk_waiting.jsonl` (413 with a line) until a doctor's lecture covers that handout
  area (owner Q1); `site_import.py` step 8 files them. Grade 5 is NOT imported as lesson questions: it is the site's
  "AI questions" reservoir (owner Q2; brief `docs/handovers/TO_TAMRAH_BOOK_HELPER_2026-11-21.md`, for the
  "Tamra book helper" session; a cross-session message was not delivered: paste the file there).
- Done when: every site question has a grade, a lesson and a handout pointer; the check is 0.

### S5. Telegram sync completeness (master prompt 3A)
- Mother agent is primary (owner 2026-11-20); Claude still reads every changed list (`py tg_lists.py text <id>`).
  Nagib 1638: the readers disagree on link 40 and "Internal capsule" twice: fix the agent's rule for a name used twice.
- Edits and deletions (draft + undo, two-fetch rule, mass hold): code diff exists in `spine/tg/flow.py`; needs the
  website's W1/W2.
- Doctors' wrong links, Claude fixes them (owner 2026-11-21: "I can't ask doctors to fix any links. You have to deal"):
  Wagih list 1631: revision "Basal ganglia" links 1848 (gone) and "limbic system" links 1847 (the lecture itself): look
  for the real revision posts by caption near those ids (`py tg_lists.py text 1631`); found -> `sources/lists/link_fixes.json`;
  none -> leave the items out and say so. Ammar MSK "Cartilage 2" (ZAG59_Histo 232) holds the same YouTube as his
  revision 231: find the right video (channel posts near 232, captions); none -> hide lesson `lecture:y1-hist-232`
  (`backend/src/scripts/hideLessons.ts`) so students do not get the revision twice.
- Done when: an edited or deleted list item reaches the site as draft with undo; the wrong links above are settled.

### S6. Website asks (another session, `C:\Users\Ahmed\Desktop\tumrah`; `docs/spine/WEBSITE_ASKS.md`)
- W1 importer honours `status` and `--only-keys`; W2 lessons draft + undo; W3 whiteboard/file section
  (`lesson_files.jsonl` and the MSK smart-board PDFs 224, 234, 247 wait for it); W4 lectures batch by `sourceRef`;
  W5 `AcademicModule.university` (ZNU waits for it); the year 1 "old data" note; review and commit
  `backend/src/scripts/hideLessons.ts` (written by tumrah-data 2026-11-21, used once); grade 5 as the AI-questions
  reservoir (`docs/handovers/TO_TAMRAH_BOOK_HELPER_2026-11-21.md`).

### S7. ZNU year 1 (master prompt 2)
- `modules/nu-year1-musculoskeletal/`: handout + lines only. `py -m spine graph build nu-year1-musculoskeletal`,
  check the splitter as the MSK note did. Sources = the same as ZU (owner Q5): map the ZU lessons and questions onto
  the ZNU handout (books -> ZNU handout, lessons' ranges, questions' pointers). Site module waits for website W5.

### S8. Tumrah book -> handout
- Waits for the tumrah-book session's export (READY.jsonl bundles). Same window engine as S3.

### S9. Cleanup the plan asked for (master prompt 1: "rebuild, fix, delete legacy")
- Old fleet flows still in code (`dm.py run`, `runners.py`, queue.db `place`/`lecture_links`/`transcribe` lanes): move
  what is still needed to the spine, put the rest in `legacy/`.

## 2. Owner tasks (things only the owner can do)
- T1. Listen to the five pieces in `listen_2026-11-20/` (README inside) and say which transcript is right.
- T2. Today screen: 24 cards wait (`py dm.py page`, first tab).
- T3. (owner doing it 2026-11-21) Sign the fleet's `other` account in once: `py C:\Users\Ahmed\agy-fleet\fleet.py login other`.
- (T4 moved to S5: the owner cannot ask doctors to fix links; Claude deals with them.)

## 3. Owner questions (asked 2026-11-21; answers go here)
- Q1. Waiting MSK questions -> ANSWERED: link them to the handout, wait for a doctor's lecture on that area. The owner
  thinks year 1 data already covers everything: it does not (see Q7).
- Q2. Grade 5 -> ANSWERED: the website's "fake AI questions" reservoir: served first when a student asks for AI
  questions, real AI questions after he finishes them. Website session "Tamra book helper".
- Q3. Elazouny -> ANSWERED: always skipped, all modules and years; his books are pictures.
- Q4. Fleet re-hearing -> ANSWERED: none.
- Q5. ZNU sources -> ANSWERED "It's the same": ZNU uses the same Telegram sources as ZU (same doctors' lists, polls).
  So ZNU = the same lectures and questions placed on the ZNU handout (its own graph); the site module waits for W5.
- Q6. The first-term lessons on MSK -> ANSWERED "remove them" (S&F is next year's work). DONE 2026-11-21: the 80 still
  published were set to draft with `C:/Users/Ahmed/Desktop/tumrah/backend/src/scripts/hideLessons.ts` (new, not
  committed in the tumrah repo); undo file
  `modules/year1-musculoskeletal/backups/hide_lessons_undo_2026-11-21T02-23-33-609Z.json`
  (`hideLessons.ts --undo <file> --apply`). MSK now shows its 39 lessons. Permanent deletion only if the owner asks.
- Q8. Other MSK poll/quiz channels -> ANSWERED: ZAG_59_Polls is all.
- Q7. The rest of the MSK lectures -> ANSWERED "That's all I got": the 42 records are all; ~500 MSK questions wait.

## Progress
- 2026-11-21 02:40 UTC (session that wrote this plan, paused at session limits). Still running at hand-off: Gemini
  `p1 run year1-musculoskeletal` (acct capped on Hydrogen -> Flash-Lite fallback), fleet `hear2` (36 transcripts done).
  Next session: section 0 checks, then S1.

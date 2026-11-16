All reads were read-only. The polls, ledger and queue SQLite files were opened with `mode=ro`. Nothing was written, run against Telegram or the website, or committed.

**Paths below are relative to `R = C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data\`.**

## Headline findings for Phase 0
1. **"Year 1 polls" cannot be deleted by channel alone.** `config.json:17-25` groups channels by batch, not by the year of their content:
   - `ZAG_59_Polls` (batch 59, listed under year "1"): all Year 1.
   - `zagpolls58` (listed under year "2"): batch 58's Year 1 archive, posted 2025-04 to 2026-09. 40,450 bank questions there are labelled year1, 219 year2-cns, 102 year2-endocrine.
   - `Batch58ATM` (year "2"): mostly Year 2, but 1,097 year1-labelled and 1,013 unlabelled questions.
   - 768 ready rows merge sightings from both `ZAG_59_Polls` and `zagpolls58`.
2. **Year 2 is more than CNS.** `Batch58ATM` also holds year2-endocrine-and-reproductive (22,595) and year2-other (4,305). "Keep all Year 2 CNS" leaves these undecided. This needs an owner call.
3. **The labels are fleet-made and gitignored.** The module label (`bank/labels.jsonl`) comes from the fleet reading headers, not the owner. CNS rows (22,071) are identified only by it.
4. **Deleted keys would come back.** `polls/engine.py:145` `seed_old_keys` re-seeds keys from an outside folder, `C:\Users\Ahmed\Desktop\tumrah for med\telegram_raw_export_2026-10-12`. `engine.CHANNELS` is hardcoded at `polls/engine.py:26`.
5. **No university dimension exists.** NU and ZU appear nowhere. The channel names ("ZAG"), and an exported channel titled "Zagazig Doctors 2nd Year", suggest all current data is ZU.
6. **No MSK module exists yet, but MSK data does:**
   - `doctors/msk/{anatomy,histology,physiology}`: only one empty `histology/1st lec.txt`.
   - `sources/forms/forms_plan.jsonl`: 208 forms, all `year1-musculoskeletal`. Keys are in `sources/forms/keys/`.
   - The bank has 2,262 questions labelled year1-musculoskeletal.
   - `config.json:40` sets an MSK window: batch 59 from 2026-11-04.
   - MSK is pre-wired in `doctors_folder.py:22`, `importfile.py:17`, `site_questions.py:19` and the module dropdowns in `page.html`.
7. **Hand-written files are not in git:**
   - `modules/*/site/` is ignored, including the hand-written `mother_lists.json`.
   - Also ignored: `sources/lists/link_fixes.json`, `bank/key_decisions.json` (the owner's key answers), `ledger.db`, all of `lectures/`.
   - Only `data_backup/ledger_owner.json` backs up owner answers.

## 1. Inventory
**Python:** 111 project `.py` files (57 at root, 17 in `flows/` + `flows/kit/`, 2 in `polls/`, 35 in `tests/`), 17,281 lines. `jobs/` holds another 4,857 generated copies of the kit tools.

**20 largest `.py` files (lines):**

| File | Lines | File | Lines |
|---|---|---|---|
| gemini_run.py | 1009 | ledger.py | 306 |
| checks.py | 887 | tests/test_engine.py | 305 |
| page.py | 796 | fast_lessons.py | 283 |
| doctors_folder.py | 670 | tg_lists.py | 268 |
| polls/engine.py | 480 | tests/test_update_flow.py | 267 |
| tests/test_ledger.py | 479 | highlights.py | 249 |
| dm.py | 429 | lectures.py | 247 |
| control.py | 384 | flows/highlights.py | 233 |
| decisions.py | 369 | shortlist.py | 222 |
| titles.py, auto_doctors.py | 336 each | flows/lecture.py | 319 |

**Folders:**

| Folder | Size | Files | Git | Purpose |
|---|---|---|---|---|
| doctors/ | 3,070 MB | 82 | ignored | owner's input: `<cns\|msk>/<subject>/<doctor>/` (PDFs, mp4, list links) |
| sources/ | 2,964 MB | 321 | ignored | `records/` (2.5 GB, 110 recordings), `export/raw` (460 MB, 46 chats), `forms/`, `quizbot/`, `index/`, `lists/` |
| modules/ | 1,835 MB | 547 | partly: `mcq/*.jsonl` and `outline.json` only | only `year2-cns/` exists |
| jobs/ | 1,398 MB | 19,190 | ignored | fleet/Haiku/Gemini job folders (piece 338M, place 244M, lecture_links 240M, books 217M, pointers 159M…) |
| lectures/ | 1,084 MB | 1,975 | ignored | `cns-001..` folders (143), `lecture.json`, transcripts |
| polls/ | 340 MB | 18 | code only | polls engine, `polls.db` (+2 backups), `raw/`, `ready/` |
| bank/ | 307 MB | 55 | ignored | merged question bank, labels, inbox quizzes |
| backups_ledger/ | 95 MB | 12 | ignored | `ledger.db` copies |
| backups_pre_update/ | 64 MB | 172 | ignored | queue/media snapshots from 11-10 |
| labels/, highlights/, logs/, exports/, control/ | under 0.5 MB each | | ignored | fleet label output, highlight marks, logs, book export, control-room state |
| data_backup/ | small | 1 | tracked | `ledger_owner.json` |
| flows/ | 0.2 MB | 29 | tracked | dispatcher flows and worker kit |
| docs/, tests/, .claude/ | small | | tracked (except `settings.local.json`) | |

**Root files (non-`.py`):**

| File | Size | Purpose |
|---|---|---|
| `ledger.db` | 14.5 MB | handout-link ledger |
| `queue.db` | 19.9 MB | job queue |
| `config.json` | | settings |
| `CLAUDE.md` | | project rules |
| `Polls.bat` | | starts `polls\control.py` |
| `Admin page.bat` | | starts `dm.py page` |
| `page.html` | | admin page UI |
| `doctors_seen.json` | | doctors_watch state |
| `tools_dns.cjs` | | DNS preload for node |
| `*.out` | | stray logs |

**Code under git:** 131 tracked files. The other data folders are ignored (`.gitignore` lines 1-42).

## 2. Polls
**polls/ tree:**
- `engine.py`, `control.py` (page on port 8765), `page.html`, `engine.log`
- `polls.db` (59.6 MB, plus WAL), `polls.before-refresh-2026-11-14.db`, `polls.before-retire-2026-11-07.db`
- `raw/{Batch58ATM,ZAG_59_Polls,zagpolls58}/messages.jsonl`, `raw/channels.json`, `raw/ZAG_59_Polls/missing_ids.txt`
- `ready/questions.jsonl` (42.5 MB), `ready/questions.before-newer-repost-2026-11-14.jsonl`, `ready/held.jsonl` (1 row)

**`polls/engine.py`:**
- The job runs scrape, vote on every account, scrape again, vote, then `build_ready` (`:449`).
- Keys come from `read_results` (`:81`): the option with Telegram's `correct` flag, read per account right after its vote.
- Every vote goes into the `own` table. `net()` (`:92-100`) subtracts those votes when they were cast before the snapshot `seen`.
- Duplicates use `word_key` (`:76`), which is the same key as `wordKey` in `importSfQuestions.ts`. `mark_dupes` (`:131`) gives one vote per distinct question.
- `build_ready` (`:162`) merges reposts across channels. The uncommitted change is "newest repost key wins" (`key_source:"newer_repost"`).
- But the current `ready/questions.jsonl` has no `key_source` field and still has 130 `key_conflict` rows.
- External imports: Telethon/`tg` from `Desktop\tumrah\scripts\telegram`; voting accounts come from `reveal_keys_round3.VOTING_ACCOUNTS_PATH`.

**`Polls.bat`:** runs Python 3.13 `polls\control.py`.

**Data per channel (`polls.db`):**

| Channel | Batch / year | Raw lines (ids) | polls.db rows | own votes | Dates |
|---|---|---|---|---|---|
| Batch58ATM | 58, Year 2 now | 56,583 (56,583) | 51,785 keyed, 3,186 dupe, 1 held | 52,558 | 2026-08-17 to 2026-11-13 |
| zagpolls58 | 58, its Year 1 archive | 49,575 (49,575) | 48,582 keyed | 49,775 | 2025-04-18 to 2026-09-28 |
| ZAG_59_Polls | 59, Year 1 now | 12,629 (6,350, scraped twice) | 5,179 keyed, 852 dupe | 5,179 | 2026-08-20 to 2026-11-06 |

**`ready/questions.jsonl`:** 95,866 rows, one per distinct question.
- By channel: Batch58ATM only 50,845; zagpolls58 only 39,986; ZAG59 only 4,250; ZAG59 + zag58 768; Batch58 + zag58 17.
- By label: Y1 45,791; Y2-CNS 22,071; Y2-other 26,991; unlabelled 1,013.

**What a "delete Year 1 polls" would touch:**
- In `polls.db`, the rows are mixed per channel; `own`, `channels`, `accounts` and `state` are shared.
- The raw folders.
- `ready/questions.jsonl`, which mixes years in one file.
- Backups: the 2 `polls.before-*.db` files and `questions.before-newer-repost`.
- `bank/questions.jsonl` (102,565 rows, all sources mixed) plus 2 `questions.before-*` backups.
- `bank/labels.jsonl`, `bank/stats.jsonl`, `bank/counts.json`.
- `labels/headers`, `labels/questions`, `labels/header_doctors.json`, `jobs/labels/`.
- `sources/export/raw/ZAG_59_Polls`.
- The outside OLD export folder.
- `config.json` `poll_channels` and `engine.CHANNELS`.

**Bank question counts, label × channel (`bank/labels.jsonl`):**

| Channel | Y1 | Y2-CNS | Y2-other | Unlabelled |
|---|---|---|---|---|
| Batch58ATM | 1,097 | 21,852 | 26,900 | 1,013 |
| zagpolls58 | 40,450 | 219 | 102 | 0 |
| ZAG_59_Polls | 5,018 | 0 | 0 | 0 |

**Production website:** only CNS was imported (`source_id bank:<sha12>`, batch "58"), so no Year 1 data is on the site.

## 3. Modules and the hierarchy
Only `modules/year2-cns` exists. Module codes come from `config.json:58-67` `label_modules`: 5 year1 and 3 year2 codes.

**year2-cns:**

| Item | Contents |
|---|---|
| `handout.pdf` | 28 MB |
| `lines.jsonl` | 9,837 lines, hash d30dcde2 |
| `outline.json` | 789 sections |
| `books/` | 18 files, 324 MB: 9 PDFs with `.json` metadata (ammar ×2, basel, elhusseiny, elsamahy 218 MB, mossafer, nageb, nagib-partial, zahran) |
| `mcq/` | 14 files, 92 MB: 7 `.jsonl` + PDFs. azony ×2 are untracked |
| `site/` | 365 files, 1.1 GB: `compressed/` 117 m4a, `alignment/` 7, 107 `tier_required_*` + 107 `tier_doctor_*`, `questions.json`, `fast_points.json`, `pointers_fast.jsonl`, `lessons.jsonl`, `mother_lists.json`, `media.json`, import results, old `questions_applied_*` |
| `old/` | 117 files: `agent-lecture-list-2026-11-08/reference.json`, 2 `lecture_json_before_*`, `partial_books/`, `removed_lectures/` |
| `backups/` | 30 files, 248 MB: 9 `cns_questions_<ts>/` (chapters, lessons, `questions_owned.json`) |

**How the hierarchy is modelled today:**
- **Year and subject:** year is only in the module code string (`year2-cns`). Subject is the `doctors/<module>/<subject>/` folder name and `lecture.json.subject`.
- **Two separate chapter notions:**
  - Doctor chapters: Telegram list items, written by hand in `site/mother_lists.json` (`{doctors:[{doctor,list,subject,chapters:[{title,items:[{id,name,post,kind,covers}]}]}]}`). Fallback is `dm.list_chapters` (`dm.py:133`).
  - Handout lectures `year2-cns:L01..`: `old/.../reference.json` (64) and `outline.json` sections.
- **Lesson:** `lectures/cns-NNN/lecture.json` (`lesson` = site id, `ranges` = line-ID spans, `chapter`, `required`, `doctor_questions`, `hold`).
- **Atomic unit is a line, not a sentence:** `hub.py` IDs look like `<module>:<sha8>:p<page>:l<n>` or `:f<n>`.
- **Stale path:** `labels.lecture_lists()` (`labels.py:52`) reads `modules/*/reference.json`, which now lives in `old/`, so it returns nothing.

## 4. Questions today
**MCQ row schema** (`mcq/*.jsonl`): `qid, book, doctor, subject, page, n, question, options, key, key_from`. Example rows, trimmed:
- `{"qid":"mcq:basel-hist-mcq:p3:1","doctor":"dr-basel-sherif-hist","page":3,"question":"Which one … increases with age?","options":[4],"key":2,"key_from":"answer_list"}`
- `{"qid":"mcq:basel-hist-mcq:p3:2","question":"Nissl granules:","key":1,…}`

**Pipeline:**
- `merge.py:199 build`: polls + QuizBot + forms + MCQ books + doctor QuizBot + `bank/inbox` go into `bank/questions.jsonl`.
- Grouping is by `word_key`. Repeats across doctors raise `repetition_count`/`importance_score`.
- Key conflicts are flagged only. They are settled by the owner (`apply_decisions` `:170`, `bank/key_decisions.json`, 3 so far) or by doctor files (`apply_doctor_prior` `:180`).
- `site_questions.py:29`: the owner's `required` and `doctor_questions` lists become `site/questions.json`. Rows with no key, a conflict or a held lecture are skipped.
- `fast_lessons.py:139 build`: IDF word-overlap pointing, plus ledger "ready" readings that override it. Each question goes to the least-loaded lesson. It writes the full `questions.json` and `fast_points.json`; `pointers` (`:256`) writes `pointers_fast.jsonl`.
- Tiers (`tiers.py`):
  - **required:** the owner's or doctor's own quiz. If there is none, the doctor's "new" branch questions.
  - **doctor:** the rest of that doctor's questions, plus the owner's "Doctor's other" list.
  - **extra:** everything else, computed on the site.
- `required_rule.py` adds: no quiz → the doctor's MCQ-book questions (`by: rule:mcq_book`).
- `apply_tiers.py` pushes `tier_*.jsonl` to production with `importHubData`.
- Own-doctor quizzes: `own_questions.py` (QuizBot: elsamahy, basel), `nagib_quizzes.py` (forms → `nagib_quiz_keyed.jsonl`), `bank/inbox/*.jsonl` (21 files, 474 rows).
- Pointers are stored in `ledger.db` `links(kind='question', src=word_key, runner, lines, state)`, in `fast_points.json` and in `pointers_fast.jsonl`.

**year2-cns counts:**

| Item | Count |
|---|---|
| Poll questions labelled CNS | 22,071 (12,447 with a lecture) |
| MCQ-book rows | 1,925 (1,403 keyed) |
| Quiz rows | inbox 474, Nagib keyed 59, own QuizBot 189 on site |
| `site/questions.json` | 9,247 (bank 8,290, mcq 723, own 189, form 45), 94 lessons |
| `fast_points.json` | 9,042 |
| `pointers_fast.jsonl` | 8,957 |
| Ledger question sources | 13,863 distinct, 6,812 agreed |
| Required list rows | 220 |

**Bug:** `elsamahy-phys-mcq.jsonl` has `doctor:"elsamahy"` instead of a `dr-…` id. All 127 of its questions are therefore never pointed: 0 appear in `fast_points.json`.

## 5. db.py
`db.py` reads live MongoDB through `MONGODB_URI`, taken from the `config.json` `backend_env` file (`:16`) with DNS pinned to 1.1.1.1. The database is `tumrah`.

It defines no query functions of its own. `Reader.find`/`count`/`aggregate` (`:46-59`) cap results at 500 rows and block `$out`/`$merge`.

**Callers:**

| Caller | Collection(s) |
|---|---|
| `page.py:56,555` | academicmodules |
| `page.py:73,85,557` | questions |
| `page.py:421` | doctorprofiles |
| `page.py:560` | sitebooks |
| `page.py:561` | bookalignmentpages |
| `page.py:601` | lecturequestions |
| `fast_lessons.py:264`, `tiers.py:70`, `cover.py:37`, `highlights.py:90`, `intake.py:35` | questions |

`Reader.live` is also called from `dm.py:280,299,356`, `voters.py:127` and `flows/lecture.py:310`.

## 6. Tests
Run with `py -m unittest discover tests`. There are 35 files and 257 test methods; they were not run here.

| File | Tests | File | Tests |
|---|---|---|---|
| test_ledger | 47 | test_labels | 8 |
| test_engine (polls) | 25 | test_titles | 8 |
| test_update_flow | 17 | test_dispatcher, test_queue | 7 each |
| test_lecture_checks | 14 | test_control, test_lecture_flows | 5 each |
| test_owner_lectures | 14 | test_cover, test_db, test_mcq, test_pointers, test_minis, test_link_fixes | 4 each |
| test_merge | 11 | test_alignment, test_chapters, test_sources, test_voters, test_folder_source_match | 3 each |
| test_doctors_folder | 10 | test_dm, test_importfile, test_pieces, test_upload_media, test_key_conflict_card | 2 each |
| test_highlights | 10 | test_handover, test_lesson_files | 1 each |
| test_hub, test_page | 9 each | live_timing_spike.py | spike, 0 tests |

**No tests:** apply_tiers, tiers, site_lessons, required_rule, own_questions, nagib_quizzes, new_doctors, outline, update_data, form_keys, hub_import_lessons, book_export, index_tree, oob_transcribe, haiku_run, haiku_audit, fleet_pause, fleet_watch, extra_dispatcher, mother_check, polls/control.py.
- `fast_lessons` is covered only through test_titles.
- `site_questions` is covered by one case in test_update_flow.

## 7. Docs
Specs and plans live in the tumrah repo, not here: `Desktop\tumrah\docs\superpowers\specs\2026-11-06-data-workflow-design.md`, `plans\2026-11-06-data-workflow.md`, and the highlights spec of 11-08. The only design doc in this repo is `docs/2026-11-08-owner-named-lectures-design.md` (owner-named lectures, place flow, shortlist).

| Handover | Summary |
|---|---|
| 11-06 | Polls job design (3 channels, accounts, rate limits, keys only from the flag). "Batch 58 is year 2, batch 59 is year 1." |
| 11-07 | Vote job near done; zagpolls58 retired then restored. QuizBot/forms commands; 25 of 30 plan tasks pass. |
| 11-10 | Fleet dead, jobs queue only. MSK form keys: 208 forms, 1,728 keys. Bank had 133 key conflicts. |
| 11-10_PLAN | Gemini web replaces the fleet. Lowest-error routes; MSK form conflicts wait. |
| 11-10_LEDGER | Ledger, checked placement, Today screen. About two thirds built. |
| 11-12 | 82 CNS lessons live. Uploads automatic, Haiku MCQ copy, required rule. 7 open decisions. |
| 11-14 | `titles.py`, `pointers_one`, Haiku reader A (4,024 questions). Site import: 4,162 inserted, 5,004 updated. |
| 11-14_EVENING | Site rework: `mother_lists` by hand, least-loaded spreading, duplicate lectures held, cards answered by Claude. |
| WEBSITE_TASKS_11-13 | Chapters from lists, Cocci, whiteboard files, mini lecture kind. |

**Open in the newest three handovers:**
- 128-131 answer-key conflicts, owner only.
- About 1,166 reader conflicts plus the spot check.
- Cocci has no site doctor id.
- The site should serve `LectureQuestion` tiers, or allow one question in several lessons.
- 15 chapters still to create.
- Reader A: 354 queued + 87 held. Reader B not created. A Haiku token estimate is needed before any batch.
- cns-102..105 have no ranges; 7 lessons are on interim `claude-coarse` pages.
- About 630 questions were drafted after narrowing "CNS تأسيس 1".
- From 11-12: 1,310 unpointed MCQ-book questions; Basel p0051; cns-075 recording is silent; lecture_links cost; Azouny's first MCQ part was never queued.
- `ledger.db` has 25 open decision cards.

## 8. Config and secrets (names only)
- `config.json` stores paths, slots, windows and `backend_env`, which points to `Desktop\tumrah\backend\.env` (`MONGODB_URI`, read by `db.py`).
- No `.env`, `.session` or cookie files are inside the repo.
- Telegram sessions and voting accounts live in `Desktop\tumrah\scripts\telegram` (`tg`, `reveal_keys_round3`).
- Gemini cookies: `C:\Users\Ahmed\gemini-web`. Fleet state: `C:\Users\Ahmed\agy-fleet\state.json`.
- `.claude/settings.json` has a SessionStart hook (`doctors_watch.py hook`). `settings.local.json` allows `py hub_import_lessons.py`.
- Privacy and size risk: `sources/export/raw` holds an export of a voter account's dialogs, 46 chats of about 460 MB. Many are unrelated (news, political, deals channels).

## 9. Dead weight
**Scripts:**

| Item | Evidence |
|---|---|
| `book_export.py` | Not referenced in code, tests or docs |
| `index_tree.py` | One-off fetch from 11-09, no references |
| `oob_transcribe.py` | Workaround from 11-09, no references |
| `new_doctors.py` | One-off from 11-09; mentioned only in comments |
| `fleet_watch.py` | No references |
| `importfile.py` (`dm importfile`) | Replaced by `site_questions`/`fast_lessons`; no `bank/import_*.json` exists |
| `tests/live_timing_spike.py` | Spike, no tests |
| `gemini_run.py`, `haiku_run.py`, `extra_dispatcher.py` | Workarounds for the fleet being down; still wired in |
| `highlights.py` | Paused (`config` `highlights.auto=false`) |

**Data:**

| Item | Size |
|---|---|
| `polls/*.before-*.db` | 112 MB |
| `ready/questions.before-*` | 42 MB |
| `bank/questions.before-*` | 163 MB |
| `backups_ledger/` | 95 MB |
| `backups_pre_update/` | 64 MB |
| `jobs/pointer_jobs_before_trim_2026-11-14.json` | 16 MB |
| `jobs/*.out`, root `*.out` | small logs |
| `site/questions_applied_*`, `fast_points_0948.json`, `pointers_fleet.jsonl`, `questions_owner_only.json`, `required_cns-001.jsonl`, `doctor_cns-002.jsonl` | old snapshots from 11-09 |
| `modules/year2-cns/backups/` | 248 MB |
| Unrelated chats in `sources/export/raw` | about 400 MB |

**Stale state:**
- `polls/raw/ZAG_59_Polls/messages.jsonl` has every message twice.
- The working tree has 19 modified and 7 untracked files, not committed.
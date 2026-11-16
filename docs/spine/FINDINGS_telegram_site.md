The pipeline today is the opposite of the new design in four places. Each lecture's Telegram list is parsed by regex. The chapters in `mother_lists.json` are typed by hand. Lessons only get added, never edited or removed from the list. A recording reaches students only after a person runs a production import. The pieces you can keep are the R2 upload path, the 5-minute audio pieces for transcription, `mother_check.py`, the edit snapshots and the control room. Everything below was read from source or data files. Nothing was edited or run that writes.

Repos: data is `C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data`. The website is `C:\Users\Ahmed\Desktop\tumrah`, found through `config.json` `backend_env`.

## 1. `update_data.py` (197 lines)

The docstring (lines 1-23) lists 8 steps. Each step runs inside `step()` at :33, so one failure does not stop the others.

| # | Where | What it does | What it calls |
|---|---|---|---|
| 1 | :160, `folder_look` :41 | Compares the `doctors/` folder with the last look | `doctors_watch.check`; reads/writes `doctors_seen.json` and `doctors_pending.json` |
| 2 | :161 | Re-points moved recording files | `doctors_folder.repair_paths` :492; writes `lecture.json` and `media.json` |
| 3 | :162-164 | Telegram auto doctors | `auto_doctors.sync` :212, which calls `tg_lists.fetch_many`, `plan`, `describe`, `finish_interrupted`, `convert_to_mini`, `make`, `add_recording`, `lectures.create/add`, `media_merge`, `queue_db.add_jobs` |
| 4 | :165-171 | Folder import (`--dry` only plans) | `doctors_folder.plan` :342 or `import_all` :558, which calls `lectures`, `page.file_into_lecture`, `read_form`, `mcq.queue_book`, `dm.py add books`, `books_merge.merge_partials` |
| 5 | :172-173 | Nagib's quiz forms, only if their `.url` files changed | runs `nagib_quizzes.py` |
| 6 | :175, `waiting_telegram` :60 | Lectures that have a post link but no file | `tg_lists.info/download`, `lectures.add`, `media_merge` |
| 7 | :176, `site_files` :105 | Writes the site files | runs `site_lessons.py write`, then `lesson_files.write` |
| 8 | :177-179 | Starts uploads in the background | `upload_media.start_background` :90 |
| 9 | :180, `state` :115 | Queue counts, lectures with no recording, lectures on backup | `queue_db.progress`, `config.json` |
| 10 | :182, `today_cards` :132 | Today screen cards | `ledger.sync`, `decisions.refresh`, `ledger.backup` |
| 11 | :183-193 | Prints the report, clears the pending list | |

Two notes:
- **Not in this script:** `fast_lessons build`, `site_questions`, `tiers.py`, starting the dispatcher, and every site import. All of those are run by hand.
- **Stale docstring:** it says "`dm.py site`" and "the fleet is down". The code actually runs `site_lessons.py`, and `config.json` says the fleet is up.

## 2. Telegram

**Client and login**
- Library is Telethon, through `C:\Users\Ahmed\Desktop\tumrah\scripts\telegram\quizbot\tg.py:33 connect(label)`.
- The session file path comes from the voting accounts config (`reveal_keys_round3`), and `tg.py` raises `Stop` if the session needs a login.
- Account `voter2`. Every call (`fetch`, `info`, `download`) opens its own connection.
- Only channel `RecordsBatch58ATM` is read.

**Modules**

| Module | Lines | What it does | Called by others |
|---|---|---|---|
| `tg_lists.py` | 268 | Regex parser for list messages | `message_id` :27, `parse` :37, `parse_post` :99, `apply_link_fixes` :123, `twice_linked` :142, `fetch_many` :170, `download` :205, `load` :210, `info` :246 |
| `auto_doctors.py` | 336 | Diffs the lists and makes new lectures | `auto_doctors` :32, `known` :53, `plan` :144, `sync` :212, `finish_interrupted` :235, `download_waiting` :316 (the `download` command); `BIG_MB=200` :26, `KBPS=16` :27 |
| `mother_check.py` | 71 | Read-only diff of `mother_lists.json` against the saved lists | `check` :56; prints "exact" when they match |

**How the parser works (`tg_lists.parse` :37)**
- Section headers are matched by keyword (`SECTIONS` :24: mini, pdf, lecture, revision). Older lists fall back to "numbered blocks" (:57-68).
- A line starting with `-` or `1.` starts an item. The links under it become its parts.
- Links come from the message entities. Only links to `RecordsBatch58ATM` get a post id; `/c/` links and other channels get `post: None` and are ignored.
- YouTube links are found in the linked post's text and entities (:107).

**Cache:** `sources/lists/<id>.json` holds `{id, date, edit_date, title, text, sections{pdfs, lectures, minis, revisions, other}, media, fixed, posts{id: {kind, file_name, mime, size, duration, caption, youtube, album}}}`. Every sync fetches everything again; nothing is incremental.

**Edits and deletions**
- Only snapshots: `<id>.prev.json` is written when `sections` changed (:180).
- `plan()` finds only new parts: a post that is not `known()` by post id, YouTube id or file size.
- A removed or renamed item is never mirrored. `edit_date` is stored but never used.
- `mother_check` only reports "not linked by the list".

**Waiting recordings:** posts over `BIG_MB` (200 MB) wait for "download <lid>" from the owner. `finish_interrupted` (:235) finishes downloads that were cut off.

**List files:** one `all here updates (auto).txt` per doctor folder (10 folders), plus `old data.txt` for backup lists (1335, 1205, 1267). `doctors_folder.list_files` :68 matches the names "all here updates", "get all lectures from here" and "old data".

**`sources/lists/link_fixes.json`:** `{list_id: [{item, label, linked, post, why}]}`. One fix today: list 1630, Medulla Part 3, post 1708 → 1709.

**`modules/year2-cns/site/mother_lists.json` (hand-written, 18 KB)**
- Shape: `{_about, doctors: [{doctor, list, subject, chapters: [{title, items: [{id, name, post, kind?, covers?}]}]}]}`.
- Example (Mesafer, list 1632):
  - "Spinal cord": cns-002 "Spinal cord part 1" (post 1660), cns-003 part 2 (1683), cns-021 part 3 (1701).
  - "CSF": cns-022 (1705), then cns-130 "CSF (revision)", `kind: revision`, `covers: [cns-022]`, post 1839.
- 9 doctors, 139 items (rewritten from scratch on 2026-11-16).

## 3. `doctors/` folder and lectures

**`doctors_folder.py` (670 lines)**
- Lessons (`scan` :232):
  - Each `.txt` holds links; `kind_of` :27 sorts them into recording, quiz, required_quiz, mini_lecture and telegram.
  - In chapter folders, `chapter_files` :157 reads numbered media/`.url` files; unnumbered media become the chapter's next lesson, or a revision if the name says "revision".
  - Quizzes: `doctor_quizzes` :216 (top-level `.url`), `chapter_quiz` :444.
- Books: top-level PDFs; the name decides `mcq`, `mcq_partial`, `partial` or `full`.
- `ALIASES` :94 maps 9 folder keys to site doctor ids, plus the owner's rules from `ledger.db` (:100-116).
- Other functions others call: `plan` :342, `import_all` :558, `media_row` :414, `media_merge` :420, `repair_paths` :492, `revision_covers` :541, `key_of` :61, `numbered` :50, `nice` :287.
- `NO_ALIGN={"azony"}` :432.

**Example tree** (`cns/anatomy/amr mossafer/`):
- `Full MCQ book .pdf`, `Full main book .pdf`, `all here updates (auto).txt`, `old data.txt`
- `chapter 1/`: `1- spinal cord 1.txt`, `2- spinal cord 2.txt`, `3- spinal cord 3.mp3`, `3- spinal cord 3 test.url`, `Spinal cord revision .mp4`
- `chapter 2/`: `4- diencephalin and thalamus .mp3` plus its quiz `.url`, `5- csf .mp3` plus its test `.url`
- Only Mesafer, Zahran and Elsamahy have chapter subfolders. The other 7 folders hold only the list file and PDFs.

**`lectures.py` (247 lines)**
- Storage: `lectures/<id>/` with `lecture.json`, `audio.ogg` (16 kbps Opus), `raw.txt`, `clean.txt`, `fixes.jsonl`, `parts.jsonl`, `links.jsonl`, `pieces/`, `site/`.
- Functions: `create` :116, `add` :207 (runs yt-dlp captions, otherwise downloads audio; ffmpeg compress; returns the next flow), `chunks` :55, `cover_ranges` :143, `set_ranges` :161, `all_lectures` :197, `load/save` :33/37.
- `lecture.json` fields: `id, module, title, doctor, kind (lecture|summary|revision), covers, lesson (site ObjectId), ranges [{from, to, pages, cut?}], placed_by, required, doctor_questions, transcribe, source {file|youtube|telegram|transcript}, duration_s, pdf_pages, created, subject`. Optional: `chapter, chapter_lessons, order_key, place_note, report {lines_covered, recording_linked}, fixes {applied, for_owner}, hold, backup, quiz_read_*, list_fix`.
- Example cns-021: Mesafer, `ranges` p55-57 with `cut`, `placed_by: claude-reading`, source file `chapter 1\3- spinal cord 3.mp3`, 2633.8 s.

**`backup.py` (192 lines)**
- `use` :107 matches the lecture title to an item in the old list and downloads it (200 MB cap, 400 MB with `--big`; parts joined to `sources/backup/<lid>-old.ogg`).
- Then it calls `lectures.add(backup=...)` and `media_merge`. Also `status` :145, `clear` :150.
- No lecture is on a backup today.

**`lesson_files.py` (72 lines)**
- Only PDFs inside a subfolder of a chapter folder, named `<n>- name.pdf`. They are matched to the lecture with the same number in that chapter.
- `write` :59 produces `lesson_files.jsonl` rows: `{lesson: "lecture:cns-076", doctorId, kind: "whiteboard", name, file, size, sha256, folder}`.
- 2 rows today (Elsamahy, Ascending Tracts). Nothing is uploaded, and the site has no model for them.

## 4. Media upload

- **Where it goes:** private S3-compatible object storage (Cloudflare R2; env `S3_BUCKET`, `S3_ENDPOINT`). The site row stores `r2:<key>`.
- **How it plays:** the backend signs a 6-hour GET link (`objectStorageService.ts:35 resolveMediaUrl`, used in `studentCourseWorkspace.ts:280-283`).
- **YouTube is never uploaded.** The `https://youtu.be` link is used as `videoUrl` (`dm.lesson_rows` :227-236).

Path from download to student:
1. A file gets a row in `media.json` (`media_row` :414): `{lecture, file, key: lectures/<m>/<lid>/recording.<ext>, field: videoUrl for mp4/webm, else audioUrl}`. This happens in `import_all`, `add_recording` or `waiting_telegram`.
2. `upload_media.py` (165 lines):
   - Audio is converted locally to AAC mono 48 kbps `.m4a` under `site/compressed/`. Video is uploaded as it is.
   - 3 workers, 4 tries each. Each try runs `backend/src/scripts/uploadLessonMedia.ts` (95 lines; 8 MB multipart parts, skips a key that already holds the same size).
   - On success it sets `uploaded_size` and `key=...48k.m4a`.
   - It then runs `site_lessons.py write`, which puts `r2:<key>` in `lessons.jsonl`.
   - 3 keys are hard-coded in `site_lessons.MEDIA` :20 (cns-008/009/010).
3. Students get it only after someone runs `importHubData lessons --apply` on production by hand.

Today: `media.json` has 121 rows (116 audio, 5 video), 118 uploaded. `lessons.jsonl` has 139 rows: 112 audio, 27 video (22 YouTube).

**Size limits:** `BIG_MB=200` for Telegram downloads (backup 200, or 400 with `--big`). There is no limit on upload.

**Coupling:**
- Not coupled to transcription.
- But it is serial behind everything else in one update run: the list fetch, the download, the blocking 16 kbps ffmpeg compression in `lectures.add`, the folder import and the site files all happen first.
- It is also gated on the manual production import.

## 5. Transcription

**Two runners do the same work**
- Antigravity fleet: `dm.py run` :339 → `dispatch.py` (205 lines) → `agy-fleet\fleet.py run -a <acct> --cwd <job>`.
- Gemini web: `gemini_run.py pieces` (1009 lines) through `gweb.py`. Only `flash-lite` and `flash` are allowed (:62).
- `runners.py` (79 lines) reports which one is up.

**Flow** (`flows/lecture.py`, 319 lines)
1. `TranscribeFlow.expand` :188 runs no worker. It cuts `audio.ogg` into 300 s pieces (`checks.CHUNK_SECONDS` :272, `lectures.chunks`: ffmpeg segment, 16k Opus) at `lectures/<id>/pieces/cNN.ogg`. It then queues one `piece` job per piece.
2. Piece job folder `jobs/piece/<lid>-cNN/`: `piece.ogg`, `prompt.md`, `gemini_prompt.txt`, `piece.txt`, `result.json`, `fleet.log`. On Gemini web, the text has no times; code sets `[mm:ss]` by character position (`piece_text` :136). Answers under 450 characters per minute are rejected.
3. The last piece triggers `merge_pieces` :163, which writes `raw.txt` (`[mm:ss] text` per paragraph, times shifted by each piece's start). Chunking is by duration only, never by size.
4. `lecture_links` (`LectureLinkFlow` :265) writes `clean.txt`, `fixes.jsonl` and `parts.jsonl`: `{part, sub, title, start, end, line_ids}` with **handout** line ids, not the doctor's book. Copied to `links.jsonl`.
   - Order checks: times must rise with no overlap (`checks.check_links` :450). Nothing requires handout lines to move forward monotonically.
   - It needs `ranges` from the `place` flow (`flows/place.py`) first.
5. YouTube lectures with captions skip all of this (`vtt_to_raw`).

**year2-cns counts**

| Count | Value |
|---|---|
| Lectures | 143 (107 lecture, 27 revision, 9 summary; 4 held) |
| With `raw.txt` | 95 (12 from YouTube captions) |
| Linked to the handout (`links.jsonl`) | 62 |
| Placed on handout pages (`ranges`) | 115 |
| Queue: transcribe | 36 queued, 94 passed |
| Queue: piece | 581 passed, 2 running, 10 held |
| Queue: lecture_links | 62 passed, 32 held |
| Queue: place | 17 queued, 15 running, 13 held |

I found no record that `LectureLink` rows were ever imported (`importHubData lectures` is never invoked anywhere).

## 6. Site export and import

**Export files (tumrah-data)**

| File | Lines | Writes | Calls |
|---|---|---|---|
| `site_lessons.py` | 106 | `lessons.jsonl` (139 rows): `{key: lecture:<id>, subject, chapter {title, order}, name, order, kind lesson/summary/revision, doctorId, videoUrl, audioUrl?, oldData?, covers, ranges [{from, to}]}` | `mother_lists` :27, `sync_meta` :49 (rewrites `lecture.json` title/kind/covers), `write` :61, `ids` :93 |
| `site_questions.py` | 101 | `questions.json` and `question_lists.json` | `build` :29, `sid_of` :23 |
| `fast_lessons.py` | 283 | `questions.json` `{module, module_name, lessons[94], questions[9247]}`, `fast_points.json`, `pointers_fast.jsonl` (8957 rows) | `build` :139, `pointers` :256 (reads Mongo through `db.py`) |
| `tiers.py` | 83 | `tier_required_<lid>.jsonl`, `tier_doctor_<lid>.jsonl` | |
| `apply_tiers.py` | 39 | Runs `importHubData required/doctor --lesson --apply` for each lecture (production) | |

`media.json` and `lesson_files.jsonl` are described above.

**Import order (by hand; CLAUDE.md:24):** `importHubData lessons` → `importSfQuestions` → `importHubData pointers` → `apply_tiers` → `recomputeLessonExtras` for every published CNS lesson. Then `site_lessons.py ids <result>` writes the lesson ids back into `lecture.json`.

**Website importers.** The database is MongoDB Atlas through mongoose. There is no Prisma.

| Importer | Lines | Behaviour |
|---|---|---|
| `backend/src/scripts/importHubData.ts` | 414 | Kinds: lines, pointers, lectures, stats, required, doctor, ranges, lessons. Dry run unless `--apply`; writes an undo file to `C:\Users\Ahmed\Desktop\tumrah for med\backups`. `importLessons` :232 upserts by `sourceRef`, finds or creates `Chapter` by title and updates its order (:272-295), always sets `status: 'published'`, `isOfficial: !doctorId`. It never deletes or drafts a lesson that is missing from the file. |
| `importSfQuestions.ts` | 382 | Module `cns` → `year2-cns`. Upserts by `source` + `source_id`. Questions it no longer writes go to **draft**; this is the only place a removal is mirrored. |
| `recomputeLessonExtras.ts` | 26 | `lectureQuestionService.recomputeExtras` for each lesson id |
| `uploadLessonMedia.ts` | 95 | See section 4 |

**Models**

| Model | Lines | Fields |
|---|---|---|
| `Lesson.ts` | 78 | `subject, moduleName, module, chapter, name, order, doctorProfile, videoUrl, audioUrl, bookUrl, status, kind, covers[], sourceRef (unique), handoutRanges [{from, to}], oldData` |
| `Chapter.ts` | 25 | `module, title, order`; unique on `(module, title)` |
| `DoctorProfile.ts` | 53 | `doctorId, nameEn, nameAr, subjectSlugs, moduleCodes, aliases, …` |
| `Question.ts` | 441 | `lesson` (one per question), `academicModule, doctorProfile, source, source_id, book_refs[].line_ids, book_lecture_id, status, stats` |
| `LectureLink` | 34 | `lesson, part, sub, title, startSec, endSec, lineIds, source` |
| `HandoutLine` | 35 | `lineId, pdfPage, …` |
| `LectureQuestion` | 34 | `lesson, question, kind required/doctor/extra` (not served to students, per the 11-14 evening handover) |

There is no model for lesson files or whiteboards.

**Spec and plan (2026-11-06) in 15 lines**
1. tumrah-data is its own repo. Python reads; only the tumrah importers write.
2. The hub is handout line ids, versioned by the handout's hash.
3. Pointers, book blocks and lecture parts all store line ids. Links between them are computed, never stored.
4. A local admin page: questions hand-over, lectures (Transcribe checkbox), books, progress, gap map, word fixes, voters, coverage.
5. Flows: polls, pointers (25 questions per job), book alignment (5 pages per job), lectures.
6. Lectures: YouTube captions first. Otherwise compressed Opus, ideally heard whole in one context (chunks only as a fallback; later reversed to 5-minute pieces).
7. `raw.txt` is never edited after it is written.
8. A second worker writes clean text, fixes (0.9 or more applied) and parts with line ids, all in one context.
9. Parts become `LectureLink` rows. Transcripts never reach students.
10. Answer keys come only from Telegram's correct flag; our own votes never count.
11. One dispatcher, SQLite queue, lanes and slots. The worker's PASS is never trusted.
12. Publishing was meant to be automatic after checkers plus a sampled audit, with undo files. Never built: owner later said only on command.
13. The lecture is the unit sent to the site. Required questions are hand-picked; extras come from pointers.
14. Website changes are additive only: `HandoutLine`, `LectureLink`, `LectureQuestion`, importers, ADR 0016.
15. Plan tasks P0-P8: project, hub, website models and importers, queue, flows, admin page, auto-publish, first run, owner additions.

## 7. year2-cns doctors

The site doctor id comes from `ALIASES` / `mother_lists.json`. Every folder has an auto list file; "Folder" in the How column means it also has hand-made chapter folders.

| Doctor | Subject | Site id | List (old list) | How | Lectures L/S/R (site items) | Book in repo |
|---|---|---|---|---|---|---|
| Amr Mossafer | anatomy | dr-amr-mesafer-anat | 1632 (1335) | Folder + list | 8/3/5 (14) | full + MCQ |
| Azony | anatomy | dr-ibrahim-el-azouni-anat | 1630 (1205) | Auto | 13/0/0 (13) | 8 picture-only PDFs, never aligned (NO_ALIGN); MCQ 1 + 2 |
| Wagih Elhusseiny | anatomy | dr-wajih-el-husseiny-anat | 1631 (1267) | Auto | 13/0/9 (21) | partial + MCQ |
| Ammar | histology | dr-ahmed-ammar-hist | 1675 | Auto | 1 (1) | 2 partials + MCQ |
| Basel | histology | dr-basel-sherif-hist | 1562 | Auto | 27/0/6 (33) | full + MCQ |
| Zahran | histology | dr-mohamed-zahran-hist | 1635 | Folder + list | 9/6/0 (15) | full, no MCQ |
| Mahmoud Elhusseiny | histology | dr-mahmoud-el-husseiny-hist | 1657 | Auto | 1 (1) | none |
| Elsamahy | physiology | dr-abdullah-el-samahi-phys | 1637 | Folder + list | 11/0/5 (16) | partial (book json doctor is `null`) + MCQ |
| Nagib | physiology | dr-naguib-el-husseiny-phys | 1638 | Auto + form quizzes | 24/0/2 (25) | 2 partials |
| Cocci | physiology | none | 1636 | Auto | 0 | none |

Books live in `modules/year2-cns/books/*.json|pdf` and `modules/year2-cns/mcq/*.jsonl`.

## 8. Control room and Today screen

- **`page.py`** (796 lines, `127.0.0.1:8770`, started by `dm.py page` :334): imports `control`, `decisions`, `lectures`, `queue_db`, `runners`. Routes include `/api/today`, `/api/review`, `/api/control*` and POST `/api/decide`.
- **`control.py`** (384 lines):
  - The Run buttons are the fixed list `COMMANDS` :36 (`update_data.py` with flags, `ledger.py sync/status`, `placement.py`, `decisions.py`, `dm.py status`, `runners.py`, `backup.py status`, tests).
  - State lives in `control/` (`chat.jsonl`, `board.json`, `state.json`, `runs/`). Chat runs `claude -p`.
  - `look` :337 depends on `runners.health` and `decisions.today`.
- **`decisions.py`** (369 lines):
  - Cards come from `placement.look`, `ledger`, `runners.health`, `doctors_folder.ALIASES`/`DOCTORS`, `bank/questions.jsonl` and `fast_points.json`.
  - `answer` :160 writes `lecture.json` through `placement.apply` and alias rules into `ledger.db`.
  - `today` :311 reads `lectures/*/raw.txt` and `links.jsonl`, plus `queue.db` books counts.
- **What a rebuild must keep:**
  - `lectures/<id>/lecture.json` with `ranges`, `placed_by`, `kind`, `doctor`, `source`.
  - The file names `raw.txt` and `links.jsonl`.
  - `modules/<m>/lines.jsonl`, `queue.db` (`jobs` table), `ledger.db` (`links`, `gold`, `decisions`, `rules`), `fast_points.json`, `config.json` `fleet`.
  - `doctors_folder.ALIASES`/`DOCTORS`/`key_of`, `ledger.sync`/`lesson_ids`/`ready`, `placement.look`/`apply`.
  - The CLI strings in `control.COMMANDS`.

## Against the new Phase 2 design

**Already fits**
- Following list links to posts and finding audio, video or YouTube in them (`tg_lists.parse_post`). The list cache with `.prev.json` snapshots of edits.
- PDFs are ignored for lectures (`auto_doctors.plan` :160, `mother_check`).
- Uploading to R2 is already separate from transcription. Uploads run detached, retry, are idempotent, and play through signed links.
- Duration-based chunking (300 s pieces), async fleet and Gemini queues, and a checker that never trusts a worker's PASS.
- Hand link fixes. `mother_check` as a validator for the parsed map.
- Whiteboard PDFs are tied to exactly one lesson (`lesson_files.jsonl`).
- The importers are idempotent, keyed by `sourceRef`, and write undo files.

**Contradicts it**
- **Parsing:** regex and heuristics in `tg_lists.parse`. The chapter/lecture map is `mother_lists.json` typed by hand. `dm.list_chapters` and `auto_doctors.mini_parent` guess by word overlap.
- **Mirroring:** additions only. Edits and deletions are not mirrored; `importLessons` never drafts or deletes a lesson, and renames are not followed.
- **Upload timing:** not immediate. It waits behind the whole update run (list fetch, download, blocking ffmpeg Opus compression, folder import, site files). Videos over 200 MB wait for the owner.
- **Publishing:** the "never touch the website" rule and the manual production import chain. A lesson reaches students only through a hand-run `importHubData lessons --apply`.
- **Mapping target:** transcripts are mapped to **handout** line ids, not the doctor's book. Parts only need rising times, not monotonic line order.
- **Whiteboards:** only PDFs in local chapter subfolders. Telegram PDFs/A3 sheets are never taken (owner rule: only the owner adds PDFs). Nothing is uploaded.

**Missing**
- An LLM parser for the Mother Message, with a cached parsed map and a diff (add, edit, delete) against the site.
- A non-blocking upload triggered per new record, plus an automatic lesson upsert or draft on the site.
- Size-based chunking. The fleet's `transcribe` lane goes through `expand` instead of a whole-lecture prompt.
- Linear segmentation of the transcript mapped to the doctor's book, with a strict monotonic check.
- `LectureLink` import (`links.jsonl` exists for 62 lectures and was never applied).
- A website model, storage and importer for lesson files (whiteboards).
- A site doctor for Cocci.
- Handling for private `/c/` links and links to other channels.
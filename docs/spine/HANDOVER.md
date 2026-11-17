# Spine rebuild: live handover

Updated after every step. A new session reads this file first, then `START_HERE.md` only for background.
Finished items are deleted from "Left to do" and moved to "Done" as one line.

## Prompt for the next session (copy and paste)

```
Read docs/spine/HANDOVER.md in tumrah-data and continue from "Left to do", item 1. The GitHub Actions setup has
its own handover (docs/handovers/HANDOVER_2026-11-17_CLOUD.md) and waits for the owner. Rules: no Claude
sub-agents; work inline; branch spine-rebuild (GitHub: playpl/tumrah-data main = spine-rebuild); commit after
each step and keep the handover current; tests stay green (py -m unittest discover tests). Year 1 is all old
data; year 2 "Old data" lists are fallback only. Compress every recording before upload (AAC mono 48 kbps).
One Telegram reader at a time. Do not ask before importing or fixing; report after.
```

## How to run the import (owner)

1. New lectures and recordings: `py update_data.py` (or the "Update data" button on the admin page). It reads the
   doctors' lists, downloads the new recordings, compresses them (AAC mono 48 kbps) and uploads them in the
   background (`logs/upload_media_auto.log`). Stopped half way: run it again, it goes on where it stopped.
2. The website: `py site_import.py` (button "Site import (writes the website)"). Lessons, questions, pointers,
   tiers, extras, in that order; the first failure stops it and prints why; running it again is safe.
   `py site_import.py --dry` (button "Site import (dry run)") only shows what the lesson step would create.
   Run it after the upload has finished, so the new lessons point at their recordings.
3. Year 1 has no import yet (item 1 below).

## Rules for the session that continues

- **No Claude sub-agents** (owner, 2026-11-17: three build agents burned 30% of his 5-hour limit at once). Build
  inline, one step at a time. The free Gemini fleet is still the run-time reader.
- Branch `spine-rebuild`, this checkout. Commit after each step. Keep `py -m unittest discover tests` green.
- Update this file and commit it with every step.
- Hard limits: no poll deletion or move before the owner has seen `py -m spine polls inventory`; nothing else
  is deleted; website importer work goes on a branch in `C:\Users\Ahmed\Desktop\tumrah`, dry run first; never
  click the owner's Today-screen answers; Phase 3 (questions) only after Phases 0 to 2 work.
- `.gitignore` is not tracked here (the global gitignore ignores it); its local lines for `*.db-shm`,
  `*.db-wal`, `spine/graph.db` and the big `modules/*/graph/` files exist only in this checkout.

## Done

- 2026-11-16 `80997f1` snapshot of the 26 pending source files on `master`; `020b419` docs; branch `spine-rebuild`.
- 2026-11-17 `400ce0e` skeleton: `spine/__init__.py` (file layout, row shapes, jsonl helpers, `config()`),
  `__main__.py` (each part has `register(subparsers)`; unbuilt parts are skipped), `ids.py`, `text.py`
  (tokens, Arabic normalising, `ends_sentence`, transliterated-term `Lexicon`), `store.py` (`graph.db`,
  `store rebuild | status`), `parity/__init__.py`, `runners/flows.py`, `tests/test_spine_core.py` (10 tests).
- The three sub-agents that were launched wrote no file before they were stopped.
- 2026-11-17 Phase 0 graph: `spine/rows.py` (rows -> sentences; shared with the books), `spine/graph/handout.py`,
  `tree.py`, `cli.py`, `tests/test_spine_handout.py` (14 tests). `py -m spine graph build year2-cns` writes
  `modules/year2-cns/graph/sentences.jsonl`, `chapters.json`, `graph.json`; `graph check` passes (11 invariants);
  `graph sample` prints sentences with their raw rows. Ruled tables come from the PDF (`find_tables`, cached in
  `graph/work/tables.json`).
- 2026-11-17 Spot check of 100 random sentences (34 anatomy, 34 physiology, 32 histology) by me: 0 wrong joins,
  0 wrong splits, 3 small misses (below). Good enough to align against.

## Known limits of the sentence splitter (splitter version 1)

- Tables with no ruling lines (two or three text columns side by side, for example p30, p208, p255) stay as
  merged visual rows: one unit per visual row, columns run together. About 1 in 100 sampled units.
- A wrapped line in a narrow column beside a figure is joined only when the next row starts with a small
  letter, `(`, `&` or an arrow. A continuation that starts with a capital there is missed (about 20-30 units).
- A centred second line under a numbered heading is not joined.
- Changing a rule: bump `spine.SPLITTER`, rebuild, rerun `graph check`; links keep `rows`, so they re-derive.

- 2026-11-17 Polls: `spine/polls/registry.py`, `cli.py`, `polls/channels.json` (the ordered target state;
  `polls/engine.py` still uses its own `CHANNELS`), `tests/test_spine_polls.py`. `py -m spine polls inventory
  --save` is read-only and wrote `docs/spine/POLLS_INVENTORY.md`. `registry.plan(row, module, reg)` already
  decides per bank question: keep / delete / grade5 / trim.

- 2026-11-17 Link trees: `spine/linktree/crawl.py`, `cli.py`, `tests/test_spine_linktree.py`.
  `py -m spine tree fetch zagexam59 503` and `py -m spine tree fetch ZMSUMcqs58 2098` ran (account `voter2`,
  read only, no file downloaded) and saved `sources/tree/<channel>_<root>.json`; `tree show` prints the
  outline. Shape of both trees: root -> one list per doctor -> that doctor's quizzes (Google Form, QuizBot
  or a file), each link's anchor text is the lesson name. Posts after the root that no list links to are
  kept under `unreached`. Classifying the files and attaching each quiz to a lesson is Phase 3.

- 2026-11-17 Phase 1, the part with no LLM: `spine/books/split.py` + `cli.py` (`books split`, `books dedupe`;
  sentences in `modules/year2-cns/graph/books/<book>.sentences.jsonl`), `spine/align/bm25.py`,
  `prefilter.py` (`Handout` index, page scope, tiers A1-A4, candidates, windows), `old.py` (`p1 grade-old`,
  verdicts in `graph/work/old_grade.jsonl`), `recall.py` (`p1 recall`), `cli.py`, `tests/test_spine_align.py`.

- 2026-11-17 Fleet window task and pilot: `spine/align/windows.py` (prompt, `render`, `parse` with grammar,
  hidden probe, flags), `spine/align/pilot.py` (`p1 pilot make | check`). The 20-window pilot ran on the four
  fleet accounts (`jobs/sp_align/pilot/job1..4`, 5 windows per job, plain `fleet.py run`, no tools).

## How to run a fleet job by hand (what the pilot did)

`py C:/Users/Ahmed/agy-fleet/fleet.py run -a <zero|work|personal|other> --cwd <job dir> -f prompt.md --out
result.json --timeout 15`, from Bash with the sandbox off (the fleet's sign-ins live in the real profile).
The answer is `result.json["response"]`; tokens are in `result.json["usage"]`.

- 2026-11-17 Phase 1 engine: `spine/align/engine.py` (`p1 code`, `p1 jobs`, `p1 run`, `p1 accept`). Votes per
  reader in `modules/year2-cns/graph/votes/<book>.<reader>.jsonl`, links in `graph/edges/<book>.jsonl`.
  `p1 code` + `p1 accept` ran: with no fleet reader yet, 3,855 of 7,154 book sentences are linked
  (110 more are flagged as jumps, 1,412 have one reader, 1,773 have none).
- 2026-11-17 Mother message, first half: `spine/tg/mother.py` (render, prompt, parse, validate, agree,
  lecture ids, `to_doctor` in the `mother_lists.json` shape, cache, diff, the mass-delete hold). It imports and
  `render(load(1632))` gives 2,738 characters and 18 links. NOT done: its CLI, tests, the fleet run, parity.

## Fleet readers A and B: finished (2026-11-17)

Both ran to the end (144 and 146 job folders, 705 and 713 windows, 25 and 24 windows rejected by the parser).
`py -m spine p1 accept year2-cns`: 7,154 book sentences: accepted 6,280, not in the handout or not content
404, jump (flagged) 219, one reader only 157, readers disagree 46, one reader says no 35, no reader yet 13.
`py -m spine p1 audit year2-cns` prints the audit lists per book; `--sample N` prints random accepted links
with both sentences; `--list split-vote | one-reader | one-no | no-reader | jump | orphan-handout` prints one
list with every reader's answer. Read by me: 126 random accepted links (18 per book, seed 7): 0 wrong.

## Mother message agent: exact to the hand file (2026-11-17)

`py -m spine mother run` (two fleet readers per list, different accounts) then `py -m spine parity mother`
printed "9 of 9 doctors exact" against `modules/year2-cns/site/mother_lists.json` (before the lists changed
again the same day, see below). What made it exact:
- A reader gives only `role` and `covers` per link. Code sets chapter (the list item a lecture stands under,
  or the sub-heading in a first-year list) and name (the item's words, part number added), ignores a post
  the doctor linked twice (the owner is the link whose section fits the caption) and a link to a post that
  does not exist, and maps a held duplicate lecture to its twin's id.
- What a message does not say is fixed by hand in `sources/mother/fixes.json` (not tracked, like
  `link_fixes.json`): Basel's "Nervous tissues" and "Mid Revision & MCQ" revisions, Elsamahy's
  "Sensation & Ascending tracts..." revision. Applied over both readers' answers.
- `mother render | job | run | show | diff`; `--year 1 | 2` takes the lists of `spine/tg/trees.json`.
  A list reference is `1632` (year 2 channel) or `ZAG59_bio/29`. Maps are cached in
  `sources/mother/<channel>/<list>/<sha>.json`; a changed message or a new `mother.VERSION` means a new read.
- NOT done: `spine/tg/flow.py` (the dispatcher flow) and going from shadow to primary (the hand file is still
  the one `site_lessons.py` reads).
- Found while reading: Basel's post 1592 holds a second video (Brain meninges & barriers,
  youtu.be/w64A973Tqe8) that is no lesson anywhere.

## The mother trees (owner, 2026-11-17)

The owner pasted both trees; they are in `spine/tg/trees.json` (tracked): year 2 (`RecordsBatch58ATM`, new and
old list per doctor) and year 1 (20 lists in `ZAG59_Anatomy`, `ZAG59_physio`, `ZAG59_Histo`, `ZAG59_bio`).
Owner's rules (also in memory): year 1 data is ALL old data and is imported; the website needs a note that
says so (not done). Year 2 "Old data" lists are fallback only: never imported unless the owner names
lecture and doctor (`backup.py`).
- `tg_lists.py` takes a channel: `py tg_lists.py fetch -c ZAG59_Anatomy 39 40`, saved in
  `sources/lists/<channel>/<id>.json` (the year 2 channel keeps `sources/lists/<id>.json`). For another channel
  the parser reads the first-year format: Arabic headers, "Books" / "Recs", bullets `. • ● _`, and a
  sub-heading ("Chapter 1 (CHO)", a line between two red triangles) becomes the items' `group`.
- Year 2: new doctor folders `doctors/cns/physiology/khaled aboelfadl (auto)` (list 1639, 12 YouTube
  lectures) and `doctors/cns/anatomy/cocci (auto)` (list 1634, empty), and `old data.txt` for Zahran (1598),
  Ammar (1538), Elsamahy (1373), Nagib (1457). Dr. Ayman Khorshed (1706) is one post with a YouTube playlist:
  no importer reads a playlist. Khaled Aboelfadl and Cocci have no site doctor.
- Year 1 is NOT in `doctors/`: the old flow reads only the list number from a link (`doctors_folder.list_files`),
  so a `ZAG59_*` link there would be read as a `RecordsBatch58ATM` post. Year 1 goes through the spine only.
- Never run two Telegram readers at once (`tg_lists.py fetch` while Update data runs): the session file locks
  and Update data prints "FAILED OperationalError: database is locked".

## Year 1: what the 20 lists hold (read by two fleet readers each, 2026-11-17)

`py -m spine mother run --year 1`: all 20 lists have an agreed map in `sources/mother/ZAG59_*/<list>/`
(17 at once, 3 after hand fixes in `sources/mother/fixes.json`: Mahmoud Hisham's two practical videos are
ignored; Elsamahy's two sympathetic revisions and Mohamed Hisham's CHO "tricks" and "written" videos are
revisions of their chapter's lectures). A revision or mini lecture whose lecture is not in the list stands
alone (its own chapter). Totals: 232 lectures, 22 mini lectures, 34 revisions; 7.5 GB of Telegram media and
152 YouTube posts.

| subject | doctor | list | lectures | minis | revisions | chapters | Telegram MB | YouTube |
|---|---|---|---|---|---|---|---|---|
| anatomy | Elazouny | ZAG59_Anatomy/39 | 2 | 0 | 0 | 1 | 821 | 0 |
| anatomy | Wagih Elhusseiny | ZAG59_Anatomy/41 | 1 | 0 | 0 | 1 | 0 | 1 |
| anatomy | Amr Mosafer | ZAG59_Anatomy/40 | 5 | 3 | 3 | 5 | 359 | 7 |
| anatomy | Eslam Gamal | ZAG59_Anatomy/42 | 6 | 0 | 0 | 6 | 1441 | 1 |
| anatomy | Mahmoud Hisham | ZAG59_Anatomy/43 | 4 | 0 | 0 | 4 | 0 | 4 |
| anatomy | Basel Hagag | ZAG59_Anatomy/44 | 7 | 0 | 0 | 7 | 467 | 0 |
| anatomy | Ahmed Hamada | ZAG59_Anatomy/45 | 1 | 0 | 0 | 1 | 0 | 1 |
| physiology | Abdullah Elsamahy | ZAG59_physio/54 | 25 | 0 | 3 | 25 | 907 | 6 |
| physiology | Nagib Elhusseiny | ZAG59_physio/55 | 20 | 0 | 6 | 17 | 402 | 9 |
| physiology | Cocci (Mohamed Ezzat) | ZAG59_physio/58 | 26 | 0 | 0 | 26 | 0 | 26 |
| physiology | Zain | ZAG59_physio/59 | 13 | 1 | 4 | 13 | 395 | 16 |
| histology | Ahmed Ammar | ZAG59_Histo/41 | 4 | 0 | 2 | 4 | 96 | 5 |
| histology | Zahran | ZAG59_Histo/43 | 8 | 4 | 0 | 2 | 222 | 6 |
| histology | Basel Sherif | ZAG59_Histo/40 | 22 | 0 | 5 | 20 | 695 | 5 |
| histology | Mahmoud Elhusseiny | ZAG59_Histo/42 | 20 | 3 | 0 | 3 | 310 | 7 |
| biochemistry | Ibrahim Elhusseiny | ZAG59_bio/29 | 31 | 3 | 4 | 5 | 1128 | 11 |
| biochemistry | Mohamed Hisham | ZAG59_bio/30 | 19 | 4 | 6 | 4 | 0 | 29 |
| biochemistry | Elzaeem | ZAG59_bio/32 | 9 | 0 | 1 | 1 | 0 | 10 |
| biochemistry | Omar Abdelaziz | ZAG59_bio/33 | 5 | 0 | 0 | 1 | 270 | 0 |
| biochemistry | Mohamed Elkassar (list title "Ahmed kassab") | ZAG59_bio/34 | 4 | 4 | 0 | 1 | 0 | 8 |

Not done for year 1 (in this order): (1) the records machine (Left to do, item 5) must take a channel, then
download and transcribe these 288 records into a year 1 module; (2) there is no year 1 handout graph, so no
lecture can be placed yet; (3) no year 1 doctor has a site doctor id in `trees.json` (`site: null`); (4) the
"all first-year data is old data" note on the website.

## Year 2 Update data of 2026-11-17 (after the trees)

`py update_data.py` imported 17 lectures: cns-147 Diencephalon and cns-148 Cerebrum (Azouny), cns-149 Barriers
(Zahran), cns-150 Stretch reflex (Elsamahy), cns-151 to cns-162 (Khaled Aboelfadl, 12 YouTube lectures),
cns-163 Properties of reflex (Nagib). An earlier run the same day made cns-145 Internal capsule and cns-146
Basal ganglia (revision) (Mosafer). The hand file `mother_lists.json` got the 7 lectures that have a site
doctor (6 new chapters), added from the agent's maps by a script that only adds; `py -m spine parity mother`
= 9 of 9 exact. `mother_check.py` prints one line that is the doctor's own link to a post that does not
exist (Wagih, Basal ganglia revision, post 1848).
`site_lessons.py write` now leaves a lecture with no site doctor out of `lessons.jsonl` and prints
"NO SITE DOCTOR" (Khaled's 12 lessons would have been created on the site with no doctor).
Elsamahy's "Pain revision" (post 1702) flipped between two reads (parts 1-2, then 1-3): fixed by hand.
Site, same day: the 5 new Telegram recordings were compressed (AAC mono 48 kbps, 64 MB in place of 137 MB) and
uploaded; then the whole import chain ran (source tag `script-index-2026-11-17`): 7 lessons created, 9,079
questions updated, 8,957 pointers, tiers 87 calls with 0 problems, extras for 146 lessons. Owner, 2026-11-17:
"make sure to compress before uploading" (slow internet): `upload_media.py` already does it for year 2; the
year 1 records machine must do the same and never upload an original file.

## Year 1 records machine (2026-11-17, `655c5b3`, `84e811b`)

`spine/records/` (`machine.py`, `transcribe.py`, `cli.py`), `tests/test_spine_records.py` (17 tests).
`py -m spine records plan | status | download | compress | upload | transcribe | run [--doctor X]`.
- Records = links the agreed year 1 maps call lecture, mini or revision: 288 (136 Telegram audio/video, 7.5 GB;
  152 YouTube). A list whose map is stale (other sha) is skipped and reported.
- Ids `y1-<anat|phys|hist|bio>-<post>` (YouTube with no post: `y1-<chan>-yt<video>`). They live in
  `modules/year1-musculoskeletal/records/<id>/` (ignored by git), never in `lectures/`, so Update data, queue.db and
  `mother.lecture_index` never see them. State log: `modules/year1-musculoskeletal/graph/records.jsonl` (last row
  per id wins): seen -> downloaded -> compressed -> uploaded; `transcript` (youtube | gemini) apart.
- Telegram download resumes from `<name>.partial` (whole 512 KB pieces); `--max-mb` (default 300) caps one run;
  lock `sources/records/telegram.lock`; "database is locked" = Update data's reader is running.
- Compress = `upload_media.compress` (AAC mono 48 kbps) into `recording.48k.m4a`; `upload` refuses any other file
  (`check_uploadable`); key `lectures/year1-musculoskeletal/<id>/recording.48k.m4a`. YouTube is not uploaded (the
  site plays the video); its captions become `raw.txt`.
- Transcribe: 5-minute pieces. `--via fleet` (default: one worker per account, model `lite`, the year 2 piece
  prompt and check, two tries per piece per run). `--via browser`: Gemini web (see below), the piece pasted
  into the prompt box, Flash-Lite, about 36 s a piece, the answer through `gemini_run.piece_text` and the 450
  characters a minute floor; a failed piece moves to another account.

## Gemini web = the signed-in Chrome profiles (owner, 2026-11-17: "Completely replace your old cookie stuff")

`gemini_browser.py` (root) is the only way to Gemini web here; gweb and cookie files are gone from the code.
It reuses tumrah-book's driver `C:/Users/Ahmed/Desktop/tumrah-book/flow/images/browser.py`: profiles
`~/.tumrah-chrome/acct1..4` (the owner signs in once: `py -m flow.images.browser login <n>` from tumrah-book),
Chrome with `--remote-debugging-port=934<n>` over CDP, model picked before every prompt, `acct<n>.busy` locks.
`ask(prompt, model, attach, wait, account)` pastes attachments as files and returns the answer's body text (a
trailing chip with a file name is dropped); a faulted account hands the call to the next. `gemini_run.ask` calls
it (every `gemini_run.py` step), `runners.web()` reads `gemini_browser.status()` (cached `status.json`).
`py gemini_browser.py` checks the four profiles live. Faults are logged in tumrah-book's `flow/live.log`
(its `fault()`). Tested 2026-11-17: a text attachment on acct1 (27 s), audio pieces on acct1 and acct2.
The old `HEAVY_SKIP` / `HEAVY_CAP` account choice of `gemini_run.py` (read from gweb usage) is gone.
- First doctor end to end: Ammar (ZAG59_Histo/41): y1-hist-93 96 MB -> 7.1 MB, uploaded, fleet transcript
  (19 min, 22K characters); his 5 YouTube records have captions. Telegram ran at about 1.2 MB/s.
- The stand-alone batch loop was STOPPED by the owner (2026-11-17). Year 1 now runs inside the two owner commands
  (`spine/records/flow.py`, commit `5c36fc0`):
  - `py update_data.py`, step "year 1 records": one Telegram batch (`spine.config()["records_batch_mb"]`, 400 MB),
    then `py -m spine records finish` (compress, upload, fleet transcription) detached, log `logs/records_y1.log`,
    one at a time (`sources/records/finish.lock`). `--dry` only reports; `--no-telegram` skips the download.
  - `py site_import.py`, step 7: `modules/year1-musculoskeletal/site/lessons.jsonl` (one `oldData` lesson per record
    with a site doctor and a recording on the site; covers only lessons in the file), then
    `hub_import_lessons.py --module year1-musculoskeletal --apply`; lesson ids go into the records state (`lesson`).
  - Priority (owner): first lessons of every subject first (`machine.priority`: every doctor's 1st record, then
    every 2nd...; anatomy, physiology, histology, biochemistry) for download, compress, upload and transcription.
  - State when stopped: Telegram 136: downloaded 7, compressed 2, uploaded 2 (y1-anat-46, y1-hist-93); YouTube
    captions 115 of 152; 6,215 MB left on Telegram. Dry run of step 7: 0 lessons, all 20 doctors lack a site id.
  - Biochemistry: the site's year1-musculoskeletal has no biochemistry curriculum (backend `doctorRoster`): those
    lessons are reported and left out until the website session adds it (`flow.SITE_SUBJECTS`).

## Shadow mode: what is live and what is not

Everything in `spine/` is in shadow mode. "Update data", the Today screen, the control room, `ledger.db`,
`queue.db`, `lectures/`, the hand-written `mother_lists.json` and the website are untouched and work as before.
`config.json` has no `"spine"` block yet (`spine.config()` supplies the defaults: p1, p2, mother = shadow).
`CLAUDE.md` has one new section, "Mother trees" (the owner's rules of 2026-11-17); no spine rule replaces an old
rule yet. Live changes made on 2026-11-17 outside `spine/`: `tg_lists.py` takes a channel, `site_lessons.py`
leaves doctor-less lectures off the site, `site_import.py` (the import chain as one command, also two
buttons in `control.COMMANDS`).
Tests: `py -m unittest discover tests` = 335 tests, all pass.

## The original plan (owner's pasted plan, OWNER_WORDS.md message 3) against what exists (review 2026-11-17)

| Original item | State |
|---|---|
| Handout = SSOT, sentence-level graph, tree University > Year > Subject > Chapter > Lesson > Sentence | year2-cns DONE (6,704 sentences, 11 invariants). Year 1 MSK: NOT done (no MSK handout graph). NU: schema only |
| Phase 0 polls: Year 1 polls handled, Year 2 CNS kept, MSK schema | NOT done: inventory only, waits for the owner's "go" (Questions for the owner). `polls/channels.json` written but `engine.py` still uses its own list |
| Phase 1 code pre-filter (embeddings + BM25) | DONE with BM25 only; the recall gate (95% reworded) passed, so no embeddings (plan decision 8) |
| Phase 1 AI window aligner | DONE for the 7 CNS doctor books: 6,280 of 7,154 sentences accepted by two readers |
| Phase 1 audit (orphans, jumps, low confidence) | PARTIAL: audit lists exist; 470 open sentences unsettled; third reader, Haiku pass, `compat.py`, `parity p1`, 200-link audit per book (126 read) NOT done |
| Tumrah book alignment | NOT done |
| Books cross-link through the handout | by design (no stored cross-links); nothing reads it yet |
| Whiteboards uploaded as-is to a Whiteboards section | NOT done: `lesson_files.jsonl` is written; the site has no section (W3) |
| MCQ files: extract, link, archive | NOT done (Phase 3) |
| Phase 2 mother-message agent (LLM, cached) | DONE in shadow: 9 of 9 year 2 doctors exact; 20 year 1 lists mapped. Primary switch and `tg/flow.py` NOT done (the hand file still drives year 2) |
| Phase 2 live sync of additions, edits, deletions | additions DONE through Update data + site import; edits and deletions (draft + undo, two-fetch rule, mass hold) NOT done (needs W1, W2) |
| Phase 2 immediate upload | year 2: background upload in Update data; year 1: merged today. Not "immediate": runs when Update data runs; no `records watch` process |
| Phase 2 async transcription on the fleet | year 2: queue + fleet; year 1: `records finish` (fleet) and `--via browser` (Gemini web profiles) |
| Phase 2 monotonic segmentation to the doctor's book | NOT built (`spine/seg/` empty): the biggest open piece of Phases 0 to 2 |
| Phase 3 questions | deferred as ordered; link trees fetched (zagexam59 503, ZMSUMcqs58 2098); nothing else |
| Migration: shadow > parity > primary, `legacy/`, CLAUDE.md rules | NOT done: everything in `spine/` is shadow; no `config.json` "spine" block |
| Website W1 to W5 | NOT done |

So Phases 0 to 2 are NOT complete: open are the polls changes, the Phase 1 tail, Tumrah book alignment, whiteboards,
edit/delete sync, segmentation, the year 1 handout graph, and the shadow-to-primary switch.

## Owner answers and findings of 2026-11-17 (late; session moved, nothing built after this)

- POLLS: the owner said GO for changes A and B as counted. DONE 2026-11-17 night (see Left to do, item 0). Design read from the code:
  `bank/questions.jsonl` is rebuilt by `merge.build` from `polls/ready/questions.jsonl` (+ quizbot, forms, MCQ
  books); `ready/` is rebuilt by `engine.build_ready` from `polls.db` rows + `raw/`; scrape resumes by
  `channels.last_id`. So `spine/polls/apply.py` (`--dry` default) must, in one run: (1) write
  `polls/grade5/questions.jsonl` from the bank rows `registry.plan` calls grade5, and the zagpolls58 `polls`+`own`
  rows to a grade 5 file; (2) delete A rows (Batch58ATM labelled year2-endocrine-and-reproductive / year2-other)
  and all zagpolls58 rows from `polls.db` (`polls`, `own`); (3) filter `ready/questions.jsonl` and
  `bank/questions.jsonl` by the same verdicts (delete / grade5 rows out, trim = drop the dropped/archive
  sightings); (4) `polls/tombstones.jsonl` (chat, msg_id only) and a skip in `engine.scrape`; (5) `engine.CHANNELS`
  and `seed_old_keys` from `polls/channels.json` (harvest / seed_old; keep voting order Batch58ATM first);
  `config.json` `poll_channels["2"]` still lists zagpolls58: remove it; (6) `raw/zagpolls58/` moved (not deleted)
  under `polls/grade5/raw/`. Owner: no archive of the A rows; old backup files stay. Check the polls job is not
  running first. Then rerun `py -m spine polls inventory` and compare with POLLS_INVENTORY.md.
- KHORSHED: skipped by the owner. `spine/tg/trees.json` now has `"new": null, "skip": true` for him.
- SITE DOCTOR IDS (from the "Data helper agent" session, read-only from prod DoctorProfile): DONE 2026-11-17
  (18 year 1 ids + Khaled in `spine/tg/trees.json` `site`; Khaled also in `doctors_folder.ALIASES`):
  ZAG59_Anatomy/39 dr-ibrahim-el-azouni-anat, /41 dr-wajih-el-husseiny-anat, /40 dr-amr-mesafer-anat,
  /42 dr-islam-gamal-anat, /43 dr-mahmoud-hisham-anat, /44 dr-basel-el-haggag-anat, /45 dr-ahmed-hamada-anat;
  ZAG59_physio/54 dr-abdullah-el-samahi-phys, /55 dr-naguib-el-husseiny-phys, /59 dr-zein-phys;
  ZAG59_Histo/41 dr-ahmed-ammar-hist, /43 dr-mohamed-zahran-hist, /40 dr-basel-sherif-hist,
  /42 dr-mahmoud-el-husseiny-hist; ZAG59_bio/29 dr-ibrahim-el-husseiny-biochem, /30 dr-mohamed-hisham-biochem,
  /32 dr-el-zaeem-biochem, /33 dr-omar-abdel-aziz-biochem.
  OWNER DECIDES: ZAG59_physio/58 Cocci (dr-cocci-phys is year2-cns only; dr-mohamed-ezzat-phys has no modules;
  dr-mohamed-ezzat-free-phys has all 4 modules and is in DOCTOR_MODULE_ROSTER, most likely); ZAG59_bio/34
  (dr-mohamed-el-kassar-biochem or dr-ahmed-kassab-biochem, both exist).
  Year 2 Dr. Khaled Aboelfadl = dr-khaled-abualfadle-phys (then item 3 of Left to do can run).
  Biochemistry: the MSK CurriculumModule for biochemistry EXISTS on the site (so `flow.SITE_SUBJECTS` may add it),
  but backend `doctorRoster.ts` hides biochemistry from MSK students (owner rule of 2026-11-05): the 72
  biochemistry records would not show unless the owner reverses that rule.
- Flows that exist (owner asked): transcription = `flows/lecture.py` transcribe + piece (queue.db, fleet or
  `gemini_run.py pieces`) for year 2, `py -m spine records transcribe|finish` for year 1; questions = `pointers`,
  `pointers_one`, `mcq` flows + `fast_lessons.py` + ledger (old system; Phase 3 of the spine is not built); file
  aligning = `books` flow (old) and `py -m spine p1 ...` (new, CNS doctor books run; Tumrah book and year 1 not).

## Session of 2026-11-17 night (what was done)

Step 1 DONE: site ids in `trees.json`; Khaled's 12 lectures (cns-151 to cns-162,
   12 chapters, one per list item) added to `mother_lists.json` from the agent's map; `py -m spine parity mother`
   = 10 of 10 exact; `mother_check.py` prints only the known Wagih post 1848 line. Cocci (ZAG59_physio/58) and
   ZAG59_bio/34 stay null (owner decides).
   Step 2 DONE: polls changes A and B applied by `py -m spine polls apply --go` (`spine/polls/apply.py`; dry run
   without `--go`). Exactly as counted: polls.db A deleted 30,264 rows + 28,287 own votes; B moved 48,582 rows +
   49,775 own votes to `polls/grade5/polls.db`; bank 102,565 -> 35,942 (keep 34,905, trim 1,037 = 1,393 sightings
   dropped; delete 26,669; grade 5 39,954 in `polls/grade5/questions.jsonl` with their label); ready 95,866 ->
   28,980 (263 more than the bank count leave ready because ready holds polls only: they keep their quiz/form/book
   source in the bank); `raw/zagpolls58` moved to `polls/grade5/raw/`; `polls/tombstones.jsonl` (30,264 A ids,
   `engine.scrape` skips them); 120 kept dupes whose keyed twin left went back to `need` (the next polls job
   votes them). `engine.CHANNELS` / `SEED_OLD` now come from `polls/channels.json` (`harvest`, `vote` order,
   `seed_old`); `config.json` `poll_channels` lost zagpolls58. Inventory after: `docs/spine/POLLS_INVENTORY_AFTER.md`
   (0 rows left to change). No backup of the A rows (owner). `polls/grade5/` and the tombstones are not tracked.
   Step 3: `py update_data.py` (2026-11-17 night): no new year 2 lecture; year 1 batch downloaded y1-anat-62
   (227 MB), y1-anat-66 partial (193 of 210 MB); 37 new YouTube captions (151 of 152); 5,815 MB left on
   Telegram; queue: transcribe 43, place 36, lecture_links 12. `site_import.py` step 7 failed its dry run on
   YouTube record ids with capitals (the site key allows `[a-z0-9-]`): fixed by `records.flow.site_key` (lowered,
   plus 6 hex of the real id). Dry run then: year 2 creates 12 (Khaled), year 1 creates 74 old-data lessons
   (left out: 97 not uploaded yet, Cocci and ZAG59_bio/34 no site id, biochemistry hidden, 1 mini lecture).
   Elsamahy's book card had `doctor: null`: set to dr-abdullah-el-samahi-phys (cards are not tracked).
   Step 4 started: `spine/seg/` (prior, scope, segment, flow, cli; `tests/test_spine_seg.py`): `seg prior | jobs
   | run | collect | audit`. The slice comes from the lecture's handout placement through the Phase 1 edges
   (cns-002 -> book pages 5-13, cns-003 -> 5-19); a whole-book prior drifts on Arabic-script transcripts, so it
   is only the fallback. 69 lectures have a transcript and a split book. Pilot jobs: cns-002, cns-021 (A and B).
   Phase 1 third reader C (`p1 jobs --reader C`, only windows with an open sentence); `books.split.dedupe` is
   cached in `graph/work/dedupe.json` (opening every PDF ran out of memory).
   Site import ran for real: year 2 +12 lessons (Khaled), 9,056 questions updated, pointers unchanged; year 1 +74
   old-data lessons, ids saved. Step 5 had printed "87 problems": `apply_tiers.py` ran without the DNS preload and
   never reached Mongo (fixed in `site_import.py`; rerun: 87 calls, 0 problems, all unchanged).
   Seg pilot (fleet, default model): cns-002 A answered but coarse ("P1-P40 = NONE", then 30-paragraph blocks),
   cns-002 B hit "No capacity available" (503), cns-021 B answered (11 segments), cns-021 A no answer. About
   150K fleet tokens and 10 minutes per read. Next: shorter segments in the prompt (MAX_PARAS 12, "the opening
   talk maps to the first book lines"), then rerun and `seg collect`.
   OFF THE PC (owner, 2026-11-17: slow, limited internet, PC not always on; chose GitHub Actions): `cloud/`
   (`r2.py` storage via boto3, `state.py` shared records log + inputs in the bucket under `ops/tumrah-data/`,
   `tg.py` the runner's own Telegram session + `login`, `records.py` the runner job, `SETUP.md` the owner's steps)
   and `.github/workflows/records.yml` (every 2 hours, 3 GB a run, `concurrency: telegram-records`). PC side:
   `spine.config()["records_cloud"]` (default false) makes Update data pull/push the log, fetch only YouTube
   captions, and the fleet hear the runner's 16 kbps copy (`hear_key`). Tested on the PC: push/pull against the
   bucket, the runner script with 0 MB, an upload + skip + delete under `ops/`. NOT done: the GitHub repo (no
   remote, no `gh` here), the secrets and the runner's Telegram login (owner, `cloud/SETUP.md`); then set
   `records_cloud` true. Stage 2 later: year 2 Telegram lists + site import on the runner.

   Later the same night: reader C (third fleet reader, `p1 jobs|run --reader C`, only windows holding an open
   sentence or a jump) ran: accepted 6,280 -> 6,480 of 7,154 (a jump that three readers agree on is accepted:
   `engine.three_agree`). Unsettled after the first C run: one reader 35, readers disagree 17, one says no 7,
   no reader 7, jumps 148 (C was reading the jumps when this was written: see the log `logs/p1_readerC2.log`).
   `py -m spine parity p1` (new): elhusseiny PASS; Mossafer reaches 99.2% and Elsamahy 97.1% of the old linked
   rows, Zahran 83.1%, Ammar 71.5% (the old flow linked fragments of Ammar's no-ruling tables, e.g. "Anatomical |
   1- Central nervous system", that the new readers call extra: a known splitter limit, for the 200-link audit).
   `spine/compat.py` writes the legacy aligned-block shape (shadow, `graph/compat/aligned/<book>.jsonl`, new match
   word `open` for unsettled sentences). `spine/tg/flow.py` (`py -m spine mother flow`) runs inside Update data:
   changed lists re-read, new items ADDED to the hand file (never edited/removed), edits/deletions reported with the
   hold rule, parity mother (10 of 10). Website asks written: `docs/spine/WEBSITE_ASKS.md` (the website repo had
   another session's uncommitted work in importHubData.ts, so nothing was changed there). Seg prompt v2 (segments
   of at most 12 paragraphs, NONE only for talk with no book line): cns-002 A 12 segments, cns-003 B 15 segments,
   all forward; the rest of the pilot was running (log `logs/seg_pilot2.log`, then `py -m spine seg collect`).

## Left to do (in order)

1. Seg pilot (cns-002, cns-003, cns-021, readers A and B, prompt v2): read `logs/seg_pilot2.log`, run
   `py -m spine seg collect cns-002 cns-003 cns-021` and `py -m spine seg audit <lecture>` for each. Accept rule:
   both readers usable and 90% of paragraphs within 5 book lines. If they agree, run all 69 lectures
   (`py -m spine seg jobs` then `seg run`, about 150K fleet tokens and 10 minutes per read; the fleet sometimes
   answers "No capacity available" (503): rerun, answered folders are kept). Not built: `parity p2` (segments'
   handout pages against the old `lecture.json` ranges: `flow.audit` already prints the share per lecture) and
   `compat.lecture_files` (links.jsonl / ranges for the Today screen and `LectureLink` rows for the site).
   Lectures of doctors with no split book (Azouny, Khaled, Mahmoud Elhusseiny) need the design's handout-target
   variant (H numbers, monotonic only flagged): not built.
2. Phase 1 tail: after reader C's jump run, `py -m spine p1 accept year2-cns` and `parity p1`. Then the 200-link
   random audit per book (`p1 audit year2-cns --sample 200 --book <b>`; 126 read so far, 0 wrong) and settle the
   last open sentences. Claude Haiku only with the owner's OK and a token estimate. The book splitter still keeps
   "P a g e | 99" lines in `mossafer-anat-full` as content.
3. GitHub Actions for year 1 (owner's steps, `docs/handovers/HANDOVER_2026-11-17_CLOUD.md`), then
   `records_cloud: true`. Stage 2 (year 2 lists + site import on the runner) after.
4. Website asks W1-W5, lesson deadlines, the year 1 "old data" note: `docs/spine/WEBSITE_ASKS.md`, for the website
   session. Then: mirror Telegram deletions as drafts (spine/tg/flow.py has the diff and hold rule).
5. Mother agent shadow -> primary (`config.json` "spine": {"mother": "primary"}): only with the owner's word; the
   CLAUDE.md "by hand" rule is the owner's.
6. Year 1: the MSK handout PDF is not here (no handout graph, no placement); 97 records wait for upload (the
   runner will do it); Cocci (ZAG59_physio/58) and ZAG59_bio/34 site ids, biochemistry visibility: owner.
7. Tumrah book: the tumrah-book session exports bundles with READY.jsonl (agreed 2026-11-17); the data side reads
   it once the MSK handouts and the site's lesson deadline exist. Phase 3 (questions) last.

## Numbers so far

- Handout year2-cns: 9,837 rows (9,450 text) -> 6,704 sentences: 4,987 facts, 816 headings, 514 table rows,
  387 figures. 1,765 facts are joined from several rows; 185 sentences were cut out of a shared row.
  6,570 sentences are in a lesson, 134 are front matter.
- Tree: ZU, year 2, 3 subjects, 64 lessons, 4 handout chapters read from the contents pages (pdf p5 to p8):
  C1 Structural principles (L01-L17), C2 Functional principles (L18-L36), C3 Head and Neck Anatomy (L37-L53),
  C4 Special Sense Organs (L54-L64). Anatomy has chapters 1, 3, 4 and Physiology 2, 4: the same numbers as
  the Tumrah book folders. Histology has handout chapters 1 and 4, while the Tumrah book's Histology folders
  are numbered by the units inside chapter 1 (1 to 5, 7) plus 8 for special senses.

- Polls inventory (full table in `docs/spine/POLLS_INVENTORY.md`):
  - Change A (delete Batch58ATM non-CNS Year 2): 26,669 bank questions (22,368 endocrine, 4,301 other Year 2),
    30,264 `polls.db` rows, 28,287 own votes, 26,669 ready questions. 220 more of those questions are also in a
    doctor's quiz, form or MCQ book: they stay and only lose the Batch58ATM sighting.
  - Change B (zagpolls58 to grade 5): 39,954 bank questions move, 48,582 `polls.db` rows. 816 archive
    questions repeated in `ZAG_59_Polls` or in a quiz/form/book stay where they are.
  - Kept untouched: 34,905 bank questions (CNS 21,852; Batch58ATM unlabelled 1,013 and Year-1-labelled 1,091).

- Link trees (2026-11-17): `zagexam59` from 503 (Year 1, MSK): 47 posts, 2 levels deep: 11 lists, 28 forms,
  4 QuizBot quizzes, 4 files; 8 later posts no list links to (3 files, 3 forms, 1 media, 1 text).
  `ZMSUMcqs58` from 2098 (Year 2): 87 posts: 12 lists, 35 forms, 33 files, 4 QuizBot, 2 text, 1 media;
  3 later posts no list links to (1 file, 1 form, 1 text).

- Books (2026-11-17): 9 PDFs, 2 are copies (`ammar-cns-hist-partial` = `ammar-hist-1`, `nagib-cns-phys-partial`
  = `nageb-phys-1`). 7 books -> 8,422 sentences, 7,154 of them content (the rest is page furniture).
- `py -m spine p1 grade-old year2-cns` (7,173 old links): kept with no new read 3,475; one fleet read 3,496;
  redo 202 (code disagrees 87, weak reworded 115); 213 old "extra / not content" blocks are in the handout
  word for word. Tier agreement with the old links: A1 98.8% (2,201), A2 97.7% (44), A3 96.3% (1,218),
  A4 84.8% (99).
- `py -m spine p1 recall year2-cns` (new book sentences): code accepts 4,521 of 7,154 (63%); 646 windows
  remain. Agreement with old links: A1 99.6%, A2 88.9% (18 cases), A3 96.8%, A4 94.3%. Page scope holds the
  old link's lesson for 99.8% same / 98.7% partial / 95.7% reworded. Candidate list holds the old link's
  sentence: same 98.9%, partial 96.8%, reworded 95.9%. **Gate (reworded >= 95%) passes: no embedding stage.**
  Settings that pass: BM25 top 8 in scope + top 3 of the whole handout + neighbours + anchor corridor, cap 80
  (cap 60 gave 93.8 to 94.7%). A window is about 60 candidates and 1,430 tokens; one reader over all books
  is about 0.92M tokens (the old book flow used about 130M).

- Fleet pilot (2026-11-17, 20 windows, 4 jobs, default flash model): 4 of 4 jobs answered; 17 of 20 windows
  clean under the final rules. Against the old links: same 12 of 12, reworded 4 of 4, partial 1 of 2.
  The 3 rejected windows: one skipped a line; two "wrong probes" were bare headings ("Characters:") that the
  reader called X. Lessons applied in code: a probe is now a full sentence (5+ words); H numbers far apart
  are a flag, not a reject (a book table row can cover several handout sentences); the prompt now says a
  heading is teaching content. Cost: 163,870 tokens for 20 windows = 8.2K per window (3.5K in, the rest is
  the model's thinking, which swings 9K to 43K per job). All 646 windows, one reader: about 5.3M free fleet
  tokens (the design guessed 1.7K per window; the old flow used about 130M).

## Questions for the owner

- Polls, before anything is deleted or moved: the inventory matches the plan, with one surprise. 219 questions
  that exist only in `zagpolls58` are labelled CNS by the fleet (and 102 endocrine). Under change B they go to
  grade 5 with the rest of the archive. If some are live on the site as CNS questions, the next question import
  would draft them. Say "go" for A and B as counted, or say what to do with those 219.

- Dr. Khaled Aboelfadl (year 2 physiology, 12 lectures imported): which site doctor? Until then his lessons
  are not on the site.
- Year 1: which site doctors are the 20 list doctors (some are the year 2 doctors, some are new: Eslam Gamal,
  Mahmoud Hisham, Basel Hagag, Ahmed Hamada, Zain, Cocci / Mohamed Ezzat, and the five biochemistry doctors)?
- Dr. Ayman Khorshed (year 2 anatomy): a YouTube playlist, not a list. Import the playlist, or skip?
- Dr. Basel's post 1592 has a second video (Brain meninges & barriers revision) that is no lesson. Add it?

- `modules/year2-cns/graph/chapters.json`: 4 chapters as printed in the handout's contents. One look, please.
  (Other known open items are at the end of `START_HERE.md`.)

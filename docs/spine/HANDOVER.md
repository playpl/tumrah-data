# Spine rebuild: live handover

Updated after every step. A new session reads this file first, then `START_HERE.md` only for background.
Finished items are deleted from "Left to do" and moved to "Done" as one line.

## Prompt for the next session (copy and paste)

```
Read docs/spine/HANDOVER.md in tumrah-data and continue from "Left to do", item 1 (the year 1 records import).
Rules: no Claude sub-agents; work inline; branch spine-rebuild; commit after each step and keep the handover
current; tests stay green (py -m unittest discover tests). Year 1 (ZAG59 channels) is all old data and all of
it is imported; year 2 "Old data" lists are fallback only. Compress every recording before upload (AAC mono
48 kbps), never upload an original. One Telegram reader at a time. Internet is slow: download and upload in
small batches that can be resumed, and report what is left. Do not ask before importing or fixing; report after.
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
  prompt and check, two tries per piece per run). `--via browser` (`spine/records/gemini_browser.py`): Gemini web
  in the owner's four signed-in Chrome profiles `~/.tumrah-chrome/acct1..4`, through tumrah-book's driver
  `flow/images/browser.py` (no cookie files; `py -m flow.images.browser status | login <n> | stop` from
  tumrah-book); the piece is pasted into the prompt box, Flash-Lite, about 36 s a piece, the answer goes through
  `gemini_run.piece_text` and the 450 characters a minute floor; a failed piece moves to another account. Faults
  land in tumrah-book's `flow/live.log` (its `fault()`). `--via gemini` is the old cookie route (gweb, dead on
  2026-11-17 on all 4 slots: `cookie_dead`); do not use it.
- First doctor end to end: Ammar (ZAG59_Histo/41): y1-hist-93 96 MB -> 7.1 MB, uploaded, fleet transcript
  (19 min, 22K characters); his 5 YouTube records have captions. Telegram ran at about 1.2 MB/s.
- Running: a background loop of `records run --max-mb 400` (log `logs/records_y1.log`), up to 40 batches.

## Shadow mode: what is live and what is not

Everything in `spine/` is in shadow mode. "Update data", the Today screen, the control room, `ledger.db`,
`queue.db`, `lectures/`, the hand-written `mother_lists.json` and the website are untouched and work as before.
`config.json` has no `"spine"` block yet (`spine.config()` supplies the defaults: p1, p2, mother = shadow).
`CLAUDE.md` has one new section, "Mother trees" (the owner's rules of 2026-11-17); no spine rule replaces an old
rule yet. Live changes made on 2026-11-17 outside `spine/`: `tg_lists.py` takes a channel, `site_lessons.py`
leaves doctor-less lectures off the site, `site_import.py` (the import chain as one command, also two
buttons in `control.COMMANDS`).
Tests: `py -m unittest discover tests` = 335 tests, all pass.

## Left to do (in order)

1. Year 1 records import: BUILT and RUNNING (2026-11-17, see "Year 1 records machine" below). Left: let the
   batch loop finish (`py -m spine records status` prints what is left), then
   `py -m spine records transcribe` until every Telegram record has a transcript, then
   `py -m spine records download --youtube-audio` for YouTube posts with no captions and transcribe those.
2. Year 1 on the website: the 20 doctors need site doctor ids (`spine/tg/trees.json`, `site: null`); the
   lessons need their module and subjects on the site (biochemistry is new); a note for students that all
   first-year data is old data. Website code goes to the website session; the data importer here, dry run first.
3. Dr. Khaled Aboelfadl (year 2, list 1639): once he has a site doctor (the owner's "Set site doctor" card, or
   `doctors_folder.ALIASES`), add his 12 lectures to `mother_lists.json` from the agent's map and run
   `py site_import.py`. Dr. Ayman Khorshed (1706) is a YouTube playlist: needs a playlist reader, or the
   owner's word to skip him.
4. Mother message: `spine/tg/flow.py` (`MotherFlow`: the dispatcher runs the two readers when a list changes),
   then the switch from shadow to primary (`site_lessons.py` reads the agent's cached map; the hand file stops).
   Until then, after every Update data: `py -m spine mother run --year 2`, add the new lectures to the hand
   file, `py -m spine parity mother` must print 9 of 9.
5. Phase 1 open sentences (470 of 7,154): read `py -m spine p1 audit year2-cns --list <name>` and settle
   `split-vote` (46), `one-reader` (157), `one-no` (35), `no-reader` (13), `jump` (219). Then: the "0" retry
   with the whole lesson listed; a third reader (Gemini web) for split votes; Claude Haiku only for what stays
   flagged, under `spine.config()["claude_budget_tokens"]` (ask the owner with a token estimate first);
   `spine/compat.py` (`aligned_blocks(book)` in the legacy block shape, `ledger_mirror()`);
   `spine/parity/p1.py`; a 200-link random audit per book before it is marked ready (126 links read so far,
   0 wrong). `spine/runners/flows.py` is written but nothing calls `register()` yet. A4 is never accepted
   alone (84.8% agreement on old blocks). The book splitter does not catch "P a g e | 99" lines in
   `mossafer-anat-full` as page furniture.
6. Polls changes, ONLY after the owner has seen the inventory and said go (see "Questions for the owner"):
   write `spine/polls/apply.py` (`--dry` default): A deletes Batch58ATM rows labelled endocrine / other Year 2
   from `polls.db` (+ their `own` votes), `ready/`, `bank/`, keeps a tombstone list of message ids so a
   rescrape does not bring them back; B moves `zagpolls58`-only questions to `polls/grade5/questions.jsonl`
   and its `polls.db` rows to a grade 5 file, sets `harvest: false`; then `engine.CHANNELS`, `config.poll_channels`
   and `engine.seed_old_keys` read `polls/channels.json`. `registry.plan()` already gives the verdict per question.
7. Phase 2 segmentation: `spine/seg/prior.py`, `segment.py`, `flow.py` (transcript paragraphs -> the doctor's
   book sentences, strictly forward), `seg audit`, `parity p2`. Needs Phase 1 edges to reach the handout.
8. Website importer changes W1 to W5 on a branch in the tumrah repo (`Desktop/tumrah`), dry run first.
9. Rewrite `CLAUDE.md` rules as each takes effect (table in `START_HERE.md`). Tumrah book alignment. Phase 3 last.

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

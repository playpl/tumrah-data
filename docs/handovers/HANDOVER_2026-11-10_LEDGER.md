# Handover, 2026-11-10 night: the ledger, the checked placement and the Today screen

For a session with no memory of this work. Read `CLAUDE.md`, then this file, then `HANDOVER_2026-11-10_PLAN.md`
(the goal and the owner's rules: they all still hold). This file replaces section 6 of the plan ("Proposed routes").

The owner stopped this session early for usage limits. The build is about two thirds done. Everything below marked
DONE was run on `year2-cns`; everything marked LEFT is not written or not tested. Nothing is committed. Nothing was
sent to the website. No `lecture.json` was changed (no decision card was answered).

## 0. Update, 2026-11-11 (items 1 to 4 and 9 of section 4 are done)
Still nothing committed, nothing sent to the website, no real `lecture.json` changed, no real card answered.
- **Tests (item 1)**: `tests/test_ledger.py`, 47 tests: `put`, `agree`, `range_ids`, `wilson`, `ready`, `mark`,
  `members`, `pointer_answers`, `bounds_spans`, `_runs`, `decisions.refresh`, `placement.apply` (cut ranges, a revision
  follows what it covers), runner health, the doctor alias rule. Whole suite: 229 pass.
- **Click test (item 2)**: every card kind and both review panels were clicked on a copy (`ledger.DB` and
  `lectures.LECTURES` pointed at a temp copy, `runners.run_ai` and `page.importer` stubbed, port 8772). All worked, no
  console errors: Check again, Set site doctor (empty value refused), Read them now, Later, Open (Polls tab), Edit pages
  (Lectures tab), Keep current pages, Use the reading, Accept all 3, spot check Right / Wrong / Skip / Close, conflict
  pick / Neither. The copy was deleted after.
- **Driver (item 3)**: `update_data.py` ends with the step "ledger and decisions" (`today_cards()`), not in `--dry`.
- **Doctor rule (item 4)**: `doctors_folder.owner_aliases()` reads `ledger.db` `rules` (read only, no import of
  `decisions`, so no cycle) and `ALIASES` takes it at import; `decisions.answer` also sets it in the running page.
- **Bug fixed**: `runners.web()` said "up" while every Google login was dead (gweb keeps `usable: true` with cause
  `cookie_dead`), so the "No AI can work now" card closed itself. The cause now decides.
- **`CLAUDE.md` (item 9)**: section "Today screen and ledger".

Found, not changed (the owner decides):
- **7 revisions do not match what they cover**: cns-025, 056, 057, 058, 059, 060, 061 were placed directly
  (`placed_by` agent), not from `covers`. For four the pages are the same, only joined differently. cns-056 (covers 27
  lectures, has pages 11-39 only), cns-057 (covers cns-044 = pages 90-95, has 11-39, 42-48, 58-70) and cns-058 (covers
  cns-040 and cns-044 = 46-48 and 90-95, has 77-95) differ in substance: either `covers` or the pages are wrong. The first
  accepted placement card of a covered lecture re-derives the revision from `covers` (`lectures._place`), so its pages
  will jump then.
- `cns-006` on "Accept all 3" becomes pages 140-144 (was 141-144), and `cns-005` on "Use the reading" becomes 139-141
  (was 137-141): the trap in section 5, seen on the copy.
- The spot check quota counts every gold row of the day, so answering conflicts shrinks that day's spot check (10 minus
  all answers). Harmless, but the card's count drops.
- The "133 answer-key conflicts" card shows although the owner said to ignore them (CNS only). "Keep held" closes it.
- All 4 Gemini accounts still answer `cookie_dead` (2026-11-11): items 6 to 8 wait for a cookie export.

### 2026-11-11, 10:50: the owner's new target and the first live call (stopped for usage limits)
- **Target (owner): "We need to reach 1% error rate."** `config.json` now holds
  `"ready": {"max_error": 0.01, "min_checked": 100}`. The 1% is the owner's; the 100 is Claude's pick, not confirmed.
  `ledger.passing` compares the measured rate (not the upper bound): 1 wrong of 100 passes, 2 fail. To show at 95% that
  a reader is under 1% takes about 380 checks with none wrong (`ledger.wilson`), so single-reader rows cannot carry the
  target soon. The route that can: every link read by two independent readers, only `agreed` rows go to the site,
  disagreements go to a judge call or the owner, and the spot checks measure the `agreed` class. Not built yet:
  the second reading (item 7, the audit command), and an error figure per state (`ledger.errors` groups by reader only).
- **Gemini login**: the owner exported cookies at 10:35 into `Downloads\Gemini Cookies\`. `gweb wake` did not find
  them there (exit 3); `gweb cookies zero --file "C:/Users/Ahmed/Downloads/Gemini Cookies/gemini.google.com_cookies.json"`
  then `gweb ping` gave 4 of 4 OK, 5-hour usage 0% on all. A Chrome export lives about 2 hours (until about 12:35):
  expect `cookie_dead` again after that.
- **First live call, no answer**: `py gemini_run.py bounds --limit 2` started 10:38:49. The first call (cns-001,
  `-m flash -t`, transcript 41 KB + sections 36 KB) was still running at 10:49 with no answer, no line in
  `jobs/gemini_run.log` and no file in `gemini-web\runs\`. It was killed on the owner's "stop" (all four processes; none
  is left). No web reading is in the ledger. Not known: slow thinking or a hang. Next time run one call by hand first
  (`gweb ask --json --temporary -m flash -t -f jobs/gemini/bounds/cns-001/prompt.txt --attach ...transcript.txt
  --attach ...handout_sections.txt`) and watch the time; the 5-hour usage a call costs is still not measured.
- `gemini_run.heavy_account` no longer picks an account whose cause is `cookie_dead` (same gweb quirk as `runners.web`).
- Tests after these edits: not rerun (229 passed before the `config.json` and `heavy_account` edits).

## 1. Why (measured on year2-cns, counts only)
- Lesson placement is the main error source, not the word-overlap pointers: 961 of 3,503 pointed questions sit in two
  or more lessons of the same doctor; `cns-011` holds 1,392 questions on 54 pages, 26 of them off-subject; 2,628
  questions touch a coarse or multi-topic lesson.
- Word overlap against the 31 fleet pointer jobs (730 rows, 3 lessons): right lesson 42 of 42, same lines 36 of 42,
  found 42 of the 167 the AI found (25%). 77% of the lecture-scoped AI rows answered `other_lecture`.
- Transcripts are in Arabic script (0 to 1 Latin words in most `raw.txt`), so no word-overlap script can place a
  lecture from its transcript. Only an AI reading can. This was tested and dropped.

## 2. The design
1. **One ledger** (`ledger.py`, `ledger.db`): every link to the handout is one row per reader (`runner`: script, fleet,
   web, owner). States: proposed, agreed (two readers share a line), conflict, owner, rejected. Ready for the site =
   agreed or owner, plus the proposed rows of a reader whose spot checks pass `config.json` `ready`
   (default: at most 5% wrong over 30 or more checks; the key is not in `config.json` yet, the default is in code).
2. **Lesson membership is computed, never stored**: a question belongs to a lesson when its lines lie inside the
   lesson's ranges (`ledger.members`). A moved boundary needs no AI rerun.
3. **Handout outline** (`outline.py`, `modules/<m>/outline.json`): handout lecture, then sections cut at headings
   (789 sections for CNS). A lesson is placed as a run of sections; an accepted place is a range marked `cut`
   (`lectures.set_line_ranges`), read line by line. Older ranges stay whole pages.
4. **Placement is checked** (`placement.py`): current pages against a reading of the recording (the web `bounds`
   reading, else the sections the lecture links cover) plus gates (off-subject, same-doctor overlap, coarse, very
   wide). Verdicts now: 3 agree, 11 differ, 42 wait for a reading.
5. **Pointers by handout lecture, not by lesson** (`gemini_run.py pointers`): one call per handout lecture's pages,
   40 questions per call; `other_lecture` goes once more to the next most likely handout lecture (code picks the
   pages, the reader chooses); a second `other_lecture` is final.
6. **The owner's inbox** (`decisions.py`, Today screen): every decision is one card with the suggested answer first.
   Nothing blocks: an undecided thing stays off the site. An answer is kept; a card returns only when its facts
   change. Review answers (conflicts, daily spot check of 10) are gold rows, so the error figure is measured.
7. **Two runners, same checkers** (`runners.py`): fleet and Gemini web. Every row names its runner.

## 3. DONE (run on year2-cns)
| File | State |
|---|---|
| `ledger.py` | `py ledger.py sync` and `status` work: 64 lesson rows, 3,503 script pointers, 167 AI pointers, 5,856 book blocks, 348 lecture parts; 42 agreed, 17 conflict. |
| `outline.py` | `py outline.py year2-cns` works: 64 handout lectures, 789 sections. Headings by geometry only. |
| `placement.py` | `py placement.py` prints the verdicts (read only). `apply()` is untested (no card was answered). |
| `decisions.py` | `py decisions.py` writes 18 open cards. `today()`, `review_items()` return data. `answer()` and `review_answer()` are written, not exercised. |
| `runners.py` | `py runners.py` reports health. The fleet is "up" only by `config.json` `fleet.down` (no live ping). |
| `gemini_run.py` | New commands `bounds` and `pointers`. Dry runs only: 52 lectures wait for a reading; 6,794 questions in 180 calls wait. No live call was possible. |
| `fast_lessons.py` | `labelled()` split out of `build()`; `lesson_lines` reads `ledger.lesson_ids`; `build()` prefers the ledger's ready non-script reading and drops owner-rejected links. Proven: with an empty ledger the old and new `build()` write byte-identical `questions.json` and `fast_points.json`; with the real ledger 42 questions take the better reading. `build()` was only run into a temp folder: the real `site/` files are untouched. |
| `lectures.py` | `set_line_ranges()` and `_place()` added; `set_ranges()` behaves as before. |
| `page.py`, `page.html` | Today screen is the first tab. Routes `/api/today`, `/api/review`, `/api/decide`. Seen once in a browser on port 8771: it renders, no console errors. No button was clicked. |
| Tests | `py -m unittest discover tests`: 182 pass (the old suite). No new tests exist. |

## 4. LEFT, in this order
1. **Tests for the new code** (`tests/test_ledger.py`, one file is enough): `ledger.put` keeps state when lines are
   unchanged and resets it when they change; `agree` (shared line = agreed, none = conflict, owner row untouched);
   `range_ids` for a `cut` range and a whole-page range; `wilson`; `ready` ranking; `gemini_run.pointer_answers`
   and `bounds_spans` with fake answers (missing question, unknown label, more than 12 lines, section outside the
   scope); `decisions.refresh` (an answered card stays answered until its payload changes); `placement._runs`.
   Use a temp `ledger.DB`.
2. **Click-test the Today screen**: `py dm.py page`, then each card kind and the review panel. Before clicking
   "Accept all 3" or "Use the reading", copy `lectures/` somewhere: those clicks rewrite `lecture.json` ranges and
   set `placed_by` to `owner`. Check that `cover_ranges` still follows for revisions.
3. **Wire the driver**: add two steps at the end of `update_data.py` `main()` (not in `--dry`):
   `ledger.sync()` and `decisions.refresh()`, and print "N decisions wait on the Today screen".
4. **Wire the doctor rule**: `decisions.rules("alias:")` is written by the "Set site doctor" card but nothing reads
   it. `doctors_folder.ALIASES` should take those entries (watch for an import cycle: `decisions` imports
   `doctors_folder` inside `cards()`).
5. **Add `"ready": {"max_error": 0.05, "min_checked": 30}` to `config.json`** once the owner agrees to the numbers.
6. **First live Gemini run**, after the owner re-exports the cookies (all 4 accounts answered `cookie_dead` at
   22:30): `py gemini_run.py bounds --limit 2`, read `jobs/gemini_run.log`, then `py placement.py`; then
   `py gemini_run.py pointers --limit 2`, then `py ledger.py status`. Measure the 5-hour usage each call costs
   (`gweb status`) before running the rest: 52 readings and 180 pointer calls.
7. **Book blocks and lecture parts have only one reader**, so none is ready until spot checks pass or a second
   runner re-reads a sample. An audit command that sends a 5% sample to the other runner (`runners.auditor`) is not
   written.
8. **Site export from the ledger**: `fast_lessons.build` already takes the ready pointer readings.
   `tiers.py` still reads `fast_points.json` (fine, it is rebuilt by `build`). Book and lecture-link site files do
   not read the ledger yet.
9. Update `CLAUDE.md` (a short "Today screen and ledger" section) once 1 to 4 are done.

## 5. Known limits and traps
- `placement.py`, verdict `agree`: the accepted span keeps the current first and last line, except on a page shared
  with the same doctor's neighbouring lesson, where it is cut at the reading's section. `cns-006` therefore starts on
  page 140 (its first covered section starts there). Look at it before accepting.
- Lecture links were made inside the old range, so that reading can only shrink a place, never widen it. Only the
  web `bounds` reading (which shows the neighbouring handout lectures) can widen one.
- `ledger.sync` skips `fast_points.json` rows marked `"reader": "ledger"`: those are copies of a better reading, not
  the script's own choice. Do not remove that field.
- The spot check sample is seeded by the date and spread over the (kind, reader) classes. Question text for
  `nagibform:` and `mcqbook:` keys is not in the bank, so those show "(not in the bank)".
- `outline.is_heading` is a heuristic (tall line, short line at the margin ending with a colon, short line in
  capitals). Sections are only places to cut; nothing else depends on them being true headings.
- Claude never reads question text or Arabic: every new file prints counts and ids only. Keep it so.
- A `gemini_run.py links --workers 2 --model flash` process from the earlier session was still alive at 22:30,
  waiting for an account. It runs the old in-memory code; editing files does not affect it.

## 6. Files touched tonight (all uncommitted, on top of the earlier session's uncommitted work)
New: `ledger.py`, `outline.py`, `placement.py`, `decisions.py`, `runners.py`, `ledger.db`,
`modules/year2-cns/outline.json`, this file. Changed: `fast_lessons.py`, `lectures.py`, `gemini_run.py`, `page.py`,
`page.html`. Written by dry runs: `jobs/gemini/bounds/*` (prompt, sections and transcript copies) and
`jobs/gemini/handout-year2-cns-ids.txt`.

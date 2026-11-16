# Tumrah data: complete rebuild (package `spine/`)

## Context

The owner ordered a full rebuild of the data pipeline (2026-11-16). Constitution: the college Handout is the
immutable heart; every book, record and question links to it at atomic-sentence level; each doctor is isolated
(one subject, own chapters, lessons, book); a new record reaches students at once; questions come last.

What exploration found today (4 sub-agents + my own measurements):

- 57 root scripts, 17k lines, ~2,000 job folders. The handout unit is a visual row (9,837 rows), not a sentence.
- Token sinks: every book job ships the whole 2.2 MB handout (0.63M tokens/run, 55 of 207 runs OK, ~130M total);
  transcript linking re-emits the whole transcript (1.2M tokens/run, 69 of 200 OK, ~240M); placement 8 of 65 OK.
- Transcripts are linked to handout pages, not to the doctor's book, and nothing checks monotonic order.
- Mother messages are parsed by regex + a hand-typed `mother_lists.json`; only additions are mirrored; a record
  reaches students only after a hand-run production import.
- Measured on the 7,173 old book links: an exact, unique match by code agrees with the old link 99.0% (2,504
  links); plain BM25 scoped to the handout lesson has the right row in the top 10 for 97% of `same`, 94% of
  `partial`, 81% of `reworded`. 305 old "extra / not content" blocks appear verbatim in the handout (old negatives
  are not trustworthy). Three books have holes (basel 0/12 jobs, elhusseiny 8/11 missing, mossafer 5/21 missing).
- Unique book text is small (~70K words; two "partial" PDFs are byte-identical to the full ones).

Outcome wanted: one clean package, sentence-level graph, code does the matching it can prove, the free fleet
answers tiny closed questions, Claude reads only what stays disputed.

## Owner decisions as I understood them (approving this plan confirms them)

1. New clean package inside this repo. Old scripts keep running until each phase reaches parity, then move to `legacy/`.
2. Fleet (free Gemini) does transcription and all heavy reading, in tiny closed-form tasks checked by code.
   Gemini segments the transcripts. Claude (paid) only verifies what stays flagged, under a hard token cap.
3. A lecture deleted on Telegram = site lesson set to draft with an undo file. Never hard-deleted.
4. Old AI results: graded by code, reused where they pass, redone only where they fail.
5. Polls (this replaces "delete all Year 1 polls" from the pasted plan):
   - `ZAG_59_Polls` = Year 1 backbone. Kept, harvesting continues (MSK).
   - `Batch58ATM` = Year 2 backbone. CNS kept. **Its non-CNS Year 2 polls (endocrine 22,595 + other 4,305) are
     deleted for good, no archive.** The 1,013 unlabelled and 1,097 Year-1-labelled rows in that channel are
     kept (labels are fleet-made; poll titles will place them later).
   - `zagpolls58` = Year 1 archive. Nothing destroyed: its questions leave the live bank and go to a separate
     **grade 5** store, duplicates dropped, to deal with later.
   - Nothing else is deleted. Old backup files are left as they are.
6. Scope now: MSK for Year 1, CNS for Year 2.
7. Question grades: 1 = the doctor's own quizzes (QuizBot, Google Forms, files), shown only to that doctor's
   students; 2 = doctors' MCQ books; 4 = polls backbone; 5 = `zagpolls58` archive. Quiz and file trees:
   `t.me/zagexam59/503` (Year 1), `t.me/ZMSUMcqs58/2098` (Year 2), followed by hyperlinks. A chapter-wide quiz
   is split per lesson. A quiz or file whose lesson/doctor cannot be determined becomes a question to the owner.
   No quiz may end up outside a lecture.
8. Deviation from the pasted plan, for cost: no embedding model in the first build (none is installed; it would
   need a large install). BM25 + anchor corridors + a "not in list" retry are used, and a measured recall gate
   (95% on `reworded`) decides whether an embedding stage is added.

## Architecture

Package `spine/`, run as `py -m spine <cmd>`. Tests `tests/test_spine_*.py` (the existing "Run tests" button picks them up).

| Module | Job |
|---|---|
| `spine/ids.py`, `spine/text.py` | sentence IDs; tokens, Arabic normalisation, transliterated-term restore |
| `spine/graph/handout.py`, `tree.py` | visual rows -> atomic sentences; University/Year/Subject/Chapter/Lesson tree |
| `spine/books/split.py`, `tumrah.py` | book PDF / Tumrah book -> sentences; partial-book dedupe by page hash |
| `spine/align/bm25.py`, `prefilter.py`, `windows.py`, `order.py`, `audit.py`, `old.py` | Phase 1 engine |
| `spine/tg/mother.py`, `tree.py` | mother-message agent, cache, diff; link-tree crawl (quiz/file channels) |
| `spine/records/upload.py`, `transcribe.py` | immediate upload state machine; chunk plan |
| `spine/seg/prior.py`, `segment.py` | transcript -> doctor's book, monotonic |
| `spine/site/export.py`, `apply.py` | site files; calls the website importers |
| `spine/polls/registry.py` | channel registry (university, year, module, grade), inventory |
| `spine/runners/flows.py` | registers new flows in `flows.REGISTRY` (`dispatch.py` untouched) |
| `spine/store.py`, `compat.py` | SQLite index; writers for the legacy file shapes |
| `spine/questions/` | Phase 3, built last |

**Store.** Records are JSONL under `modules/<m>/graph/`; `spine/graph.db` is a rebuildable index
(`nodes, rows, edges, votes, records, mother`). `ledger.db` stays the only home of owner answers; accepted links
are mirrored into `ledger.links` (runners `spine-code | spine-fleet | spine-claude`) so the Today screen and
control room keep working unchanged.

**Sentence ID.** `year2-cns:d30dcde2:p60:s5` (module : handout sha8 : page : first row; `s5a/s5b` when one row
holds two sentences; figures keep `:f<n>`). Each sentence stores its `rows[]` (existing line IDs), so the site's
line-ID contract (`HandoutLine`, `handoutRanges`, `LectureLink.lineIds`) is served by conversion at export.
Book sentence: `bk:<book>:<sha8>:p12:s3`. Tumrah book: content-addressed `tb:<path>:s<sha6>`.

**Tree.** `modules/year2-cns/graph/graph.json`: university `ZU`, year 2, subjects and lessons from
`reference.json` (L01..L64, reuse `outline.reference`), chapters built once from the handout contents pages and
checked against the Tumrah book folders. The 789 `outline.json` sections become a sentence attribute. NU later =
module codes `nu-year1-<name>`; ZU keeps bare codes so today's IDs stay valid.

Reused as-is: `hub.split_handout / word_key / resolve_span`, `outline.build`, `books_merge.page_hashes`,
`titles.Scorer`, `gemini_run.candidate_pages`, `ledger.wilson`, `checks.check_transcript`, `index_tree.links_of`,
`upload_media` + `uploadLessonMedia.ts`, `dispatch.py` + `queue.db`.

## Phase 0: graph, polls, link trees

1. `py -m spine graph build year2-cns` -> `sentences.jsonl`, `graph.json`. Split rules in fixed order: headings
   from the outline; a bullet/number marker starts a unit; a row continues the previous one when that row reaches
   the page's right margin and does not end a sentence; table row = one unit; inner split on sentence punctuation
   with an abbreviation list; each unit carries its heading path as context.
2. `py -m spine polls inventory` (read-only): counts per channel x year x module across `polls.db`, `raw/`,
   `ready/`, `bank/`. Prints exactly what step 3 would touch.
3. Polls changes, after the inventory is shown to the owner:
   - `polls/channels.json` registry replaces `engine.CHANNELS` and `config.poll_channels`: per channel
     `university, batch, year windows -> module, grade, harvest, seed_old`. MSK = new rows only.
   - `Batch58ATM`: delete non-CNS Year 2 rows from `polls.db`, `ready/`, `bank/`; keep a tombstone list of
     message ids (ids only) so a rescrape does not bring them back.
   - `zagpolls58`: move to `polls/grade5/questions.jsonl`, deduped (a question also seen in a backbone channel
     stays there); `harvest: false`; removed from the live bank.
   - `engine.seed_old_keys` reads only channels flagged `seed_old`.
4. `py -m spine tree fetch zagexam59 503` and `... ZMSUMcqs58 2098`: follow hyperlinks, store the link map only
   (node, anchor text, kind: quizbot / form / file / list). No file is downloaded in this pass.

## Phase 1: book -> handout (the main token saving)

1. **Scope by code.** Each book page votes for a handout lesson (IDF), smoothed across pages. Partials folded
   into the full book first.
2. **Accept with no LLM** (measured agreement with old links in brackets): exact and unique in the handout
   (99.0%); exact, unique inside the lesson; fuzzy >= 90 that is also BM25 top-1 and sits between two anchors
   (95.9% before the order check); short lines only when their neighbours pin them. Expected 45-60% of links.
3. **Candidates** for the rest: handout sentences in the corridor between the two nearest anchors, plus BM25
   top-8 per sentence in the lesson and their neighbours; cap 60 per window.
4. **Fleet window.** 12 consecutive book sentences + the numbered candidates, no tools, no subagents. Answer
   lines only: `B7 = H12+H13 S` / `B8 = 0` (not in list) / `B9 = X` (not content). Code checks grammar, overlap,
   and one hidden already-known sentence per window (wrong probe = window rejected). `0` triggers one retry with
   the whole lesson listed. ~1.7K tokens per window, ~3M for all books with two readers (today ~130M).
5. **Readers and order.** Accept at two agreeing votes (code, fleet A, fleet B on shifted windows, old link).
   Order check by dynamic programming: piecewise monotone, backward jumps penalised.
6. **Audit.** Orphan book sentence, orphan handout sentence between linked neighbours, jump, low confidence,
   split vote, page with no verdicts -> third reader (Gemini web). Only what is still flagged goes to Claude
   Haiku: about 200-400 items, cap `spine.claude_budget_tokens = 300000`; beyond the cap = Today card.
7. **Old links.** Lifted to sentence IDs. Kept without a new read when a code tier agrees (~3,300). One fleet
   read for the remaining `same`/`partial`. Full redo: low-overlap `reworded`, jumps, the 305 verbatim
   negatives, every unaligned page.
8. Tumrah book: lesson scope from its `chapter.json`; same window task. Azony's picture-only books are not
   aligned (stored as lecture files); his lectures map straight to handout sentences.
9. Cross-links between books are never stored; they are computed through the shared handout sentence.

## Phase 2: Telegram -> site -> transcript -> book

1. **Mother-message agent.** Code renders the message as numbered lines with link markers and a post table
   (kind, size, caption). Two fleet readers return one JSON line per link: `role` (lecture / mini / revision /
   ignore), `chapter`, `name`, `covers`. Validator (extends `mother_check`): every link once, a PDF or image is
   never a lecture, covers point to the same doctor's lectures, order = message order. Cache by sha of text +
   entities + post metadata: unchanged message = no LLM call. Claude Haiku only when readers disagree twice
   (~1.5K tokens). It writes `mother_lists.json` in today's shape; `link_fixes.json` still applies.
2. **Diff and mirror.** By `(channel, post)`: add, edit, media changed, delete. Delete = draft + undo file,
   applied only after two fetches 10 minutes apart agree; a diff that drafts more than 3 lessons or 20% of a
   doctor is held as a Today card.
3. **Immediate upload.** `py -m spine records watch` (own process): YouTube link -> lesson upsert at once;
   Telegram media -> download, AAC 48k, `uploadLessonMedia.ts`, lesson upsert. Transcription is queued from the
   same download in parallel and never blocks the upload.
4. **Transcription.** Fleet, pieces cut at the earlier of 300 s or 3 MB, snapped to silence. YouTube captions
   give an instant `raw.txt`, replaced by the fleet transcript when done.
5. **Segmentation.** Code picks the doctor's book lesson and computes a zero-token prior path (Arabic-script
   medical terms restored to English for matching). Gemini gets the numbered transcript paragraphs + only that
   book slice (13-37K tokens per lecture; today 1.2M) and answers `P12-P31 = B140-B162` or `NONE`. Code enforces:
   all paragraphs covered, in order, book ranges never go back. Offenders get a bounded re-ask; over 20%
   offending = rerun, then Gemini web, then Claude on bounded windows, then a card. Result:
   `lectures/<id>/segments.jsonl`; `compat` writes `links.jsonl` and `lecture.json ranges` for the Today screen
   and `LectureLink` rows (never imported until now) for the site. `clean.txt` and the placement flow are retired.
6. **Whiteboards.** Uploaded as-is, tied to their lecture, into the site's existing `CourseResource`.

## Phase 3: questions (built last; spec recorded now)

- Grades and sources as in decision 7. Every question links to handout sentences; its lecture is computed from
  the shared handout area, never typed.
- Scope before reading: a poll's section title, or the lecture/chapter a quiz hangs under in the link tree,
  narrows the candidate sentences; then BM25; then the same closed fleet window.
- Files from the trees are classified (doctor, kind, coverage) from tree position, caption and content;
  unclear = Today card. MCQ files: questions extracted, raw file archived.
- Completeness check: every quiz node in the link tree ends attached to a lesson or chapter, or is an open card.
  The count of unattached quizzes must be zero.

## Migration

`config.json "spine": {"p1": "shadow", "p2": "shadow", "mother": "shadow"}`. Shadow run -> `py -m spine parity
<phase>` report -> flag to `primary` -> old scripts `git mv` to `legacy/` with one-line shims at the root.
`control.COMMANDS` gains `spine-status`, `spine-update`. First execution step: commit the 26 uncommitted files as
they are, then rewrite `CLAUDE.md` and memory for the new rules (mother messages by agent, automatic site
upload, grades), replacing the rules they contradict.

## Build order and sub-agents

Fable sub-agents build in parallel on disjoint files; I review and run the checks.

| # | Work | Who | Verify |
|---|---|---|---|
| 1 | Skeleton, `ids`, `text`, `store`; handout sentences + tree | agent A (first, alone) | `py -m spine graph check year2-cns`; I spot-check 100 sentences |
| 2a | Book split, dedupe, BM25, prefilter tiers, old-link grading | agent B | `py -m spine p1 recall`; `p1 grade-old` |
| 2b | Segmentation prior, parser, monotonic repair | agent C | `py -m spine seg audit cns-002` (dry) |
| 2c | Mother render / validate / diff, records state machine | agent D | `py -m spine mother diff --dry`; `parity mother` |
| 2d | Polls registry + inventory, link-tree crawl | agent E | `py -m spine polls inventory` |
| 3 | Window flow, order, audit, compat; fleet pilot of 20 windows before any bulk | agent B | `p1 audit <book>`; `parity p1` |
| 4 | Bulk Phase 1 on the fleet; segmentation of the 95 transcripts | fleet | audit reports |
| 5 | Website importer changes (below), then records watch live | agent W, branch in the tumrah repo | importer dry runs |
| 6 | Polls changes of Phase 0 step 3 (after the inventory is shown) | me | inventory again |
| 7 | Tumrah book alignment; then Phase 3 | later | |

Website repo (`C:\Users\Ahmed\Desktop\tumrah`, on a branch, no production run without a dry run first):
W1 `importHubData lessons` honours per-row `status` and `--only-keys`; W2 `lessons-status --keys --status draft`
with undo file; W3 `resources` kind into `CourseResource`, `uploadLessonMedia.ts` accepts pdf/jpg/png;
W4 `lectures` batch mode keyed by `sourceRef`; W5 `AcademicModule.university` (default `ZU`).

## Verification

- `py -m unittest discover tests`: the 257 existing tests plus `test_spine_*` pass after every step.
- Handout: every text row in at least one sentence; a rebuild gives identical IDs.
- Phase 1: `p1 recall` gate (gold sentence inside the window candidates for >= 95% of `reworded`); `parity p1`
  compares new links with the old 7,173; a 200-link random audit per book before it is marked ready.
- Phase 2: `parity mother` = the agent's output equals the hand-written `mother_lists.json` for all 9 doctors;
  `seg audit` shows zero backward jumps; an upload test proves the lesson is live before its transcript exists
  (on a test lesson, dry run first).
- Token check: fleet logs summed per flow, compared with today's 0.63M and 1.2M per run.

## Risks

- A sentence-joining error spreads to every link: hence the spot check before step 2.
- Automatic publish and automatic draft write production: guarded by the validator, the two-fetch rule, the
  mass-change hold and undo files.
- The fleet's failure rate on closed tasks is unmeasured: 20-window pilot first.
- Doctors who reorder their book heavily will trip the monotonic rule: those lectures surface as cards.

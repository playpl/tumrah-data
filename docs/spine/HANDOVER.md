# Spine rebuild: live handover

Updated after every step. A new session reads this file first, then `START_HERE.md` only for background.
Finished items are deleted from "Left to do" and moved to "Done" as one line.

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

## Left to do (in order)

3. Polls changes, ONLY after the owner has seen the inventory and said go (see "Questions for the owner"):
   write `spine/polls/apply.py` (`--dry` default): A deletes Batch58ATM rows labelled endocrine / other Year 2
   from `polls.db` (+ their `own` votes), `ready/`, `bank/`, keeps a tombstone list of message ids so a
   rescrape does not bring them back; B moves `zagpolls58`-only questions to `polls/grade5/questions.jsonl`
   and its `polls.db` rows to a grade 5 file, sets `harvest: false`; then `engine.CHANNELS`, `config.poll_channels`
   and `engine.seed_old_keys` read `polls/channels.json`.
5. Mother message: `spine/tg/mother.py` (render, parse, validate, diff, cache), `spine/tg/flow.py`,
   `spine/records/` (upload state machine, chunk plan), `spine/parity/mother.py`.
6. Phase 1: `spine/books/split.py` (+ partial dedupe), `spine/align/bm25.py`, `prefilter.py` (tiers A1-A4, N1),
   `old.py`; `py -m spine p1 recall`, `p1 grade-old`. Then `windows.py`, `order.py`, `audit.py`, `flow.py`,
   `compat.py`; pilot 20 fleet windows before any bulk run.
7. Phase 2: `spine/seg/prior.py`, `segment.py`; mother agent to primary only when `parity mother` is exact
   for all nine doctors.
8. Rewrite `CLAUDE.md` rules as each takes effect (table in `START_HERE.md`).
9. Website importer changes W1 to W5 (branch in the tumrah repo). Phase 3 last.

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

## Questions for the owner

- Polls, before anything is deleted or moved: the inventory matches the plan, with one surprise. 219 questions
  that exist only in `zagpolls58` are labelled CNS by the fleet (and 102 endocrine). Under change B they go to
  grade 5 with the rest of the archive. If some are live on the site as CNS questions, the next question import
  would draft them. Say "go" for A and B as counted, or say what to do with those 219.

- `modules/year2-cns/graph/chapters.json`: 4 chapters as printed in the handout's contents. One look, please.
  (Other known open items are at the end of `START_HERE.md`.)

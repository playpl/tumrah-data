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

## Left to do (in order)

3. Polls: `spine/polls/registry.py`, `cli.py`, `polls/channels.json`; read-only `py -m spine polls inventory`.
   Show the counts to the owner. The two changes (delete Batch58ATM non-CNS Year 2; move `zagpolls58` to the
   grade 5 store) wait for his word.
4. Link trees: `spine/linktree/` and `py -m spine tree fetch zagexam59 503`, `... ZMSUMcqs58 2098` (links only).
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

## Questions for the owner

- `modules/year2-cns/graph/chapters.json`: 4 chapters as printed in the handout's contents. One look, please.
  (Other known open items are at the end of `START_HERE.md`.)

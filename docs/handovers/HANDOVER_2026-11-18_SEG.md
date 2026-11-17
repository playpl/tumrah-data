# Handover: segmentation (spine seg), 2026-11-18

## Prompt for the next session (copy and paste)

```
Read docs/handovers/HANDOVER_2026-11-18_SEG.md in tumrah-data. Start with "Where it stands" and "Owner decisions".
Segmentation code is safe-tested (74 seg tests, property fuzz, mutation-checked). The open problem is placement:
the reader is fine when it gets the right book section. Do not change the agent. Do not change lecture-to-placement
links, lecture.json ranges, or thresholds without the owner.
```

## Opus audit 2026-11-18 (supersedes the counts below where they differ)

Verified (read-only script `flow._judge_lecture` over all 93 job folders; nothing written; `seg collect` NOT run):
- **21 accepted / 21 rejected / 3 disputed / 48 waiting**: confirmed, before and after the fixes below (identical
  decisions and problem lines). The rows collect would write equal the 21 `segments.jsonl` files on disk (21 of 21).
- The 21 `segments.jsonl` files are byte-identical to the seg-fix backup taken 2026-11-18 00:03. The handover recorded
  no hashes; they are recorded now in the Opus report (first: cns-001 `68632d3b98ae...`).
- `py -m spine parity p2`: **17 of 21**. The 4 fails are old-placement data, not code: each lecture's transcript
  speaks the content of the pages outside its placement (cns-023 reaches 150-151, placement 152-153, P66 "referred",
  P91 "Reaction"; cns-030 reaches 12, placement 13, P11 "EM", P23 "euchromatin"; cns-047 reaches 407-408, placement
  404-406, P152 "window"; cns-049 reaches 413-414, placement 410-412, P74 "semicircular").
- Tests: `py -m unittest tests.test_spine_seg` = **82 OK**; `py -m unittest discover tests` = **462 OK**.

Rejections, by cause (first problem line in the state; evidence in the Opus report):
- Reader broke the prompt's forward rule by repeating a range (`P59-P70 = B37-B43` after `B37-B43`): cns-021 A/B,
  027 A/B, 028 A, 034 A, 035 A, 036 A/B, 038 A/B, 042 B, 045 B. Reader said NONE for talk with book lines: 035 B.
  Reader went back: 037 A (`P21-P26 = B27-B28` after B33; reader B goes forward there), 045 A (hops back and forth
  inside the 6-line cortex-layers table B44-B49, `P170-P179 = B44-B44` after B49; reader B repeats the whole table).
  Tables (036, 038, 045) are few book lines for a long talk: the content is right, the rule format is not.
- Our rule against our prompt (owner decision 1): cns-005 A, 024 A/B, 026 A, 033 A, 034 B, 051 A/B obey the prompt
  (a long talk on one line written as `P85-P95 = B51`, `P96-P105 = B51`) and are rejected as "re-states" because
  `clip()` flags `c == d == previous d`. If that were not counted: 24 accepted / 15 rejected / 6 disputed
  (cns-024, 033, 051 accepted; 005, 026, 037 disputed). Not changed.
- Doctor really went back (both readers agree; forward-only design, owner): cns-006 (P49 "نرجع لموضوعنا"),
  cns-022 (recap from P70), cns-029 (Golgi taught before Nissl, P43).
- Placement / slice: cns-011 (10 scattered ranges, 1177-line slice, both all NONE); cns-048 (talk runs to handout
  410-411, placement 407-409; readers correctly NONE past the slice end B104).
- Book split: cns-031 (book page 6 "Processes: Axon & Dendrites" is all `not_content`; the lecture is that table;
  both readers' all-NONE is correct).
- Disputed: cns-012 reader A wrong (maps neuron/fibre-type talk P1-P30 to "Sensory Receptors"); cns-015 nested
  ranges (B58-B64 vs B58-B77) count as disagreement under the 5-line midpoint rule, plus a 5-paragraph boundary;
  cns-046 transcript error: P11-P21 repeat P1-P10 (the opening is in raw.txt twice).
- cns-038: the earlier note "transcript on nerve fibres" is wrong; the talk is the receptor table (Meissner,
  Pacinian) and muscle spindles, which match the placement. It fails on repeated ranges (reader).

Bugs fixed (each with a test in `OpusAuditJudgeFixes` / `CollectIsSafe`; real-data decisions unchanged):
- `segment.judge_segs`: `SEG_LIKE` was matched at the line start, so `Segment 2: P6-P8 = B11-B20 (approx)` counted
  as prose and up to 3 paragraphs became NONE silently. Now searched in the line.
- `segment.conflict` (new): two different answers for the same stretch (a draft, then a correction) were read by the
  first one silently (`fill()` drops the later). Now refused above `MAX_HOLE` (3) paragraphs; exact repeats and
  1-paragraph boundary slips still pass.
- `flow._judge_lecture`: `by` was hard-coded `fleetA+fleetB`. Now from the job folder: `reader.json {"by": ...}`,
  else `browser.json` (Gemini web), else fleet. `make_jobs` clears `reader.json` with the old answer.

Reader interface (for a Haiku reader; no runner built): input `jobs/sp_seg/<lecture>/<A|B>/task.txt` (self-contained:
prompt v2, BOOK B1..Bk, TRANSCRIPT P1..Pn; up to 170 KB, cns-041). Send it as one message, no tools; A and B as two
independent calls. Write the reply text to `answer.txt` (UTF-8, lines `P<a>-P<b> = B<c>-B<d>` or `= NONE`) and
`reader.json` `{"by": "haiku"}`. Then `py -m spine seg dry`, then `collect`. Warning: editing `segment.PROMPT`
changes every task fingerprint, so the next collect marks all 93 jobs stale and removes the 21 accepted shadow files;
a new prompt means new jobs and new answers.

Owner decisions added by this audit: (a) restatement rule vs prompt (above); (b) prompt v3 for Haiku: say how to
continue one line (`= B51` again) and forbid repeating an earlier range, and what to do with recaps; (c) agreement on
nested ranges (`AGREE_WITHIN` 5 on midpoints); (d) book split of basel-hist page 6; (e) cns-046 transcript.

## Where it stands (2026-11-18, end of the safety pass)

- Uncommitted changes in the working tree (nothing committed or pushed; the checkout is shared):
  `spine/seg/segment.py`, `spine/seg/flow.py`, `spine/seg/scope.py`, `spine/compat.py`, `tests/test_spine_seg.py`.
- Tests: `py -m unittest tests.test_spine_seg` = 74 OK (was 37). Full suite `py -m unittest discover tests` = 446 OK.
- Real state after the final `py -m spine seg collect` (and `py -m spine seg dry` before it, identical):
  **21 accepted, 21 rejected, 3 disputed, 48 waiting.** 0 stale, 0 errors, 0 no-source.
  The 21 `lectures/<id>/segments.jsonl` files are byte-identical to what the earlier collect wrote.
- `py -m spine parity p2`: **17 of 21 pass.** Fails: cns-023 (57%), cns-030 (64%), cns-047 (71%), cns-049 (70%).
  Unchanged. Owner decision (see below).
- **The bulk run is not running.** PID 15404 is gone (no `spine seg run` process at 2026-11-18 00:40 local; the log
  `logs/seg_bulk.log` ends 17 Nov 19:41; last answer 19:45). Nothing was stopped by this session. 91 of 186 reader
  answers exist; **95 reader answers are missing** (48 lectures waiting). Starting `py -m spine seg run` again costs
  fleet quota: that needs the owner's yes.

## What changed in this pass, and why

Each item was found by a fuzz, an edge case, a mutation, or reading the code. Each one has a test.

Judge rules (`segment.py`):
- **NONE and restatement rules now also run on the repaired answer.** The fuzz found an answer that was 60% NONE after
  repair and still accepted (repair turns out-of-order paragraphs into NONE after the NONE check had run). Real data: no
  change.
- **A segment-looking line that does not parse rejects the answer** (`P5-P9 = B7 approx`). Before, it was dropped, which
  turned up to 3 paragraphs into NONE without a word. Prose lines with P-numbers (`- P2 covers ...`) are still prose.
  Real data: no change (a first version of this rule rejected cns-018; the rule was tightened, and it is back to baseline).
- **Paragraph numbers outside P1..Pn or reversed are refused.** `P0-P5` used to be renumbered silently.
- **Formatting is read, meaning is not changed:** BOM, no-break and zero-width spaces, typographic dashes, Arabic-Indic
  digits, `:` or `→` for `=`, bullets (`- `, `* `, `1. `, `2) `), bold or code wrappers (nested), trailing `.`/`;`,
  CRLF, invalid UTF-8 bytes (replaced, not a crash). Checked by invariance fuzz: the same answer with noise judges the same.
- Zero-paragraph input is refused (it used to divide by zero).

Collect and jobs (`flow.py`):
- **Stale jobs are now detected.** Each job's `meta.json` stores a fingerprint of the exact task text plus the sentence
  ids behind B1..Bk. `collect` checks it against the slice it would use now. If the owner moves a placement, re-splits a
  book, or the transcript changes, that lecture gets state `stale` and writes nothing. Before this, collect would have
  judged old B-numbers against the new slice and written wrong segments. `make_jobs` keeps an answer only when the task
  text and fingerprint both match. Jobs from before fingerprints are adopted only when their `task.txt` equals today's
  render (all 93 do).
- **A lecture that is not accepted loses its shadow files** (`segments.jsonl`, `spine/links.jsonl`, `spine/ranges.json`).
  Before, an old accepted output could outlive a later dispute or rejection.
- **One lecture's failure no longer stops the batch.** `collect` records `error`, `no source`, or `stale` in its
  `state.json` and carries on. Writes after acceptance are inside the same guard.
- **`run --limit 0` used to ask every pending answer** (`todo[:limit] if limit else todo`). Now 0 asks nothing. This
  would have spent fleet quota.
- `scope.lecture()` returns `{}` for a missing record (a `covers` id with no record crashed the slice pick).
- `prepare` refuses an empty slice.
- **Handout-target lectures:** 12 jobs (cns-008, 009, 010, 062–066, 078, 079, 088, 089) read against the handout, and
  their segments point at handout ids, not book ids. The old `compat.lecture_files` and `audit` would have raised
  KeyError `book` on the first accepted one. Fixed in `compat.py` and `flow.audit`; a test runs the real compat writer.
- New command `py -m spine seg dry`: the same decision as `collect`, read-only. Use it before any collect.

## How it was verified (all reproducible)

- **Real data, read-only:** `flow._judge_lecture` over all 93 job folders, before and after each change. Final decisions
  are identical to the morning baseline (21/21/48/3).
- **Judge fuzz:** about 44,000 random answers over several seeds (random ranges, gaps, overlaps, backwards, out-of-slice, over-length, shuffled,
  zero and huge numbers). Invariants on every accepted answer: coverage 1..n, lengths, book ranges inside the slice,
  monotone, NONE and restated and dominant shares within their limits, offending share within 20%. 0 violations.
  The same answer with formatting noise: 25,000 cases, 0 changed decisions.
- **Edge battery** (`spine seg` judge on hand-made answers): empty; prose only; one paragraph (mapped / NONE);
  all NONE; one range over 5 paragraphs (accepted: below the 20-paragraph dominant minimum, by design); one range over 40
  (rejected); overlaps; backwards book range; book range past the slice; segment past n; P0; gaps of 2 (filled as NONE)
  and 4 (refused); 13 paragraphs in one segment (refused); 121 book lines (refused); reversed paragraphs (refused); huge
  numbers; n_paras 0; n_book 0; 5000 paragraphs (0.03 s).
- **Collect end to end** in temp folders (never the real data): agreeing readers accepted and written; moved slice gives
  `stale` and removes old output; remake clears answers; same text with new ids is stale; disagreement is disputed;
  75% agreement is disputed; one broken lecture does not stop the others; no source; non-UTF-8 and BOM; empty answer;
  dry writes nothing; `--limit` 0 and 1; handout-target shadow files.
- **Mutation check:** 16 rule breaks, one at a time, in a scratch copy. The first run missed 4; three were real gaps
  (paragraph-number guard, 90% agreement line, same-text-new-ids staleness) and got tests. Now 14 of 16 are caught.
  The 2 survivors are equivalent: the zero-paragraph guard is unreachable once the range guard is in, and the
  pre-repair share check is covered by the post-repair one (repair only adds NONE and removes offenders, so no rule
  fails only before it).
- **Simulated readers** (`sim2`, not real data): truth segmentation plus independent noise per reader, two readers,
  the same collect rules. Accepted output had < 1% of paragraphs mapped to the wrong place at reader noise 0–10%, and
  2–3% of paragraphs lost to NONE. At noise 0 every accepted answer matched the truth. This shows the agreement rule
  does its job on independent errors. It says nothing about correlated errors (see "Not proven").
- **Timing:** prior on 600 paragraphs x 1500 book sentences: 6 s; 2000 x 3000: 44 s, 103 MB. Judge: 1000 segments in
  0.1 s. Real transcripts run 2–617 paragraphs; slices 60–1444 book lines.

## Owner decisions (not changed here; do not guess)

1. **Restatement rule (`MAX_CLIPPED` 20%)**: the top reason for rejection, 14 reader answers. cns-026 A is a collapse
   (P9–P54 all on B14, 46 paragraphs). cns-033 A is less clear: it sits on single lines B51, B56, B62, B78 for 10–20
   paragraphs at a time. The prompt says a long explanation is several segments in a row, so a long talk on one line is
   not forbidden. Is it legit in this doctor's lectures? If yes, relax the rule; if no, the reader needs a stricter prompt.
2. **Dominant rule (one identical range over 30% of paragraphs, min 20 paragraphs)**: rejects a reader that sits on one
   range. Same question as 1.
3. **Placement** (unchanged; the main failure): cns-038 (title "Receptor part 2", placement pages 37–39, transcript on
   nerve fibres); cns-036 (324-line slice from 8 scattered links); wide slices (cns-061 1444 lines, cns-011 1177, cns-012
   755, cns-039 734, cns-040 697). These are owner decisions: lecture-to-placement links and slice policy.
4. **Disputed (3):** cns-012 (61% agreement; disputed paragraphs 1–30 and 71), cns-015 (86%; 27–30 and 37–41),
   cns-046 (80%; 1–28 and 136). Look at them before collecting more.
5. **Parity fails (4):** cns-023, cns-030, cns-047, cns-049 (see above). cns-030 readers look right; the old placement is
   too narrow (lists page 13; content covers page 12 too). Keep, hold, or fix the placement: owner.
6. **Bulk run:** 95 answers missing. Run them now (fleet quota), or leave until the placement decisions are made?

## Not proven

- Accuracy on real lectures. Only simulation shows what the rules do to independent errors. Real readers may err together.
- **Correlated errors are the real risk.** If both readers are given the same wrong book section (a wrong placement), they
  can agree and the judge accepts the wrong mapping. The judge cannot see this; only the placement can prevent it.
- Midpoint agreement (within 5 book lines) can say "agree" when one reader's range is 120 lines wide and the other's is
  narrow inside it. The output then uses reader A's wide range: less precise, not wrong. Not changed.
- Real reader formats beyond the 91 answers seen. A new variant now shows as a rejection (malformed or unparsed lines),
  not as a silent accept. Expect some rejections on new variants; check them, do not loosen the rules blindly.
- Handout-target acceptance on real data: no handout-target lecture has been accepted yet (their answers are missing).
  The code path is tested with synthetic data only.
- Whether 14 "restated" rejections are collapses or legitimate (decision 1).

## Commands

```bash
py -m unittest tests.test_spine_seg          # 74 tests
py -m unittest discover tests                # full suite, 446 tests
py -m spine seg dry                          # what collect would decide, writes nothing
py -m spine seg collect                      # writes shadow segments for accepted lectures
py -m spine parity p2
py -m spine seg audit <lecture>
py -m spine seg run          # fleet readers, costs quota; check no run is already going first
```

Judge one folder without writing anything: `py -m spine seg dry <lecture ...>`.

## Other open items (not seg)

- Cloud (GitHub Actions, year 1 records): owner must add the 8 repo secrets; then first run; then
  `config.json` `"spine": {"records_cloud": true}`. See `docs/handovers/HANDOVER_2026-11-17_CLOUD.md`.
- `modules/year1-musculoskeletal/` is untracked: owned by the msk session. Not touched here.
- Untracked peer files: `modules/nu-year1-musculoskeletal/` handout hard links (gitignored), nu `lines.jsonl` split.

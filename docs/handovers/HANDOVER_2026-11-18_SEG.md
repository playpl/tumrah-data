# Handover: segmentation (spine seg), 2026-11-18

## Prompt for the next session (copy and paste)

```
Read docs/handovers/HANDOVER_2026-11-18_SEG.md in tumrah-data. Start with "Where it stands". The problem is
segmentation placement: the reader is fine, the book section it gets is wrong for many lectures. Do not change the
agent until the section is fixed. Owner decides placement and titles; ask him before changing them.
```

## Where it stands

- Code: `spine/seg/segment.py` (`judge_segs` holds every acceptance rule), `spine/seg/flow.py` (`judge`, `collect`,
  `run`). Tests: `tests/test_spine_seg.py` (37), full suite 409 OK. Committed and pushed to `main` as `0b7ae3c`.
- Rules now in force (all reject the answer): a range over 12 paragraphs or 120 book lines; a range off the slice;
  paragraphs going back above the last range (repairable up to 20%); over 20% of paragraphs restating earlier book
  lines (`clipped`); one identical book range over 30% of paragraphs (min 20 paragraphs); over 50% NONE.
- Parse accepts `P120 = B28-B34`, `P82-P84 = B40`, `P1 = NONE`.
- Bulk run `py -m spine seg run` (PID 15404) is still going: 91 of 186 reader answers done at 2026-11-18. The log
  `logs/seg_bulk.log` stopped at 19:41, so use the job folders to see progress. Owner has not decided to stop it.
- Last collect (on 91 answers): 21 accepted, 21 rejected, 3 disputed, 48 waiting. Accepted segments are written to
  `lectures/<id>/segments.jsonl` (shadow). `py -m spine parity p2`: 17 of 21 pass.
- Parity fails, not held: cns-023 (57%), cns-030 (64%), cns-047 (71%), cns-049 (70%). cns-030 reader segments are right;
  the old placement is too narrow (lists page 13, content covers page 12 too).

## Why lectures fail (evidence, not the reader)

The reader does well when it gets the right book section (cns-001, 002, 017, 032, 043 pass parity at 100%).
Failures trace to the section (`scope.pick` slice from placement links) or the lecture record:

- cns-038: title "Receptor part 2", placement pages 37-39, but transcript is nervous tissue / nerve fibre. Readers
  collapse onto the last lines. Likely wrong lecture-to-placement link. Owner decides.
- cns-036: slice 0-323 (324 lines) from 8 scattered links (`placement (8 linked)`). Readers map astrocytes correctly
  (B293-B298 table) then collapse. Slice far too wide.
- cns-011: slice 0-1176 (1177 lines), both readers answered NONE for all 117 paragraphs; agreement alone accepted it
  before the NONE rule.
- Wide slices (more than 500 lines): cns-061 (1444), cns-011 (1177), cns-012 (755), cns-039 (734), cns-040 (697),
  cns-041 (576), cns-075 (526), cns-085 (428). Some are legit revisions; some are scattered links.
- `fleet` 503 "no capacity" on some jobs (cns-020/B): retried by `run`, not a reader problem.

## Owner decisions needed (do not guess)

1. Lecture-to-placement links: cns-038 and every rejected lecture whose title does not match its transcript.
2. Slice policy for wide placements: cluster the links (densest window), split the lecture, or hold.
3. The 4 parity fails: hold until placement is checked, or keep.
4. Whether to stop the bulk run now or let it finish.

Do not switch the model (Gemini) on this evidence. Test the reader again only on lectures whose section is verified
right. Owner rule: no Claude sub-agents to build (memory `no-subagents-token-burn`); work inline.

## Commands

```bash
py -m unittest tests.test_spine_seg
py -m spine seg collect
py -m spine parity p2
py -m spine seg audit <lecture>
py -m spine seg run          # fleet readers; check PID before starting a second one
```

Judge a folder without writing anything: `judge_dry.py` in the session scratchpad (loops `segment.judge_segs` over
`jobs/sp_seg`; rebuild it if the scratchpad is gone).

## Other open items (not seg)

- Cloud (GitHub Actions, year 1 records): owner must add the 8 repo secrets; then first run; then
  `config.json` `"spine": {"records_cloud": true}`. Cron on `main` runs every 2 hours and fails until the secrets exist.
  See `docs/handovers/HANDOVER_2026-11-17_CLOUD.md`.
- `modules/year1-musculoskeletal/` is untracked: MSK reference, outline, graph from the spine peer session (paused). Its
  owner is the spine peer; decide before committing.
- Untracked peer files: `modules/nu-year1-musculoskeletal/` handout hard links (gitignored), nu `lines.jsonl` split.

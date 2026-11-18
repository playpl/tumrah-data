# Handover: segmentation (spine seg), 2026-11-18 (Opus audit; replaces the earlier Haiku-written text)

## Follow-up 2026-11-18 (branch claude/seg-followup-3f2305): Gemini reads, not Haiku

Owner, during this session: "Haiku should not work on transcriptions and stuff that use Arabic. This is going to be
Gemini's work. He is going to align the lecture with the book." and "Make it just good enough". So steps 1 and 3 of
the prompt below changed reader: **Gemini web, model 4 Hydrogen**, not Haiku. Nothing here costs Haiku money.

What changed:
- `spine/seg/flow.py`: `ask_gemini` (via `gemini_browser.ask`, model `hydrogen`, prompt in the message, task.txt
  attached) is the only reader. The fleet runner (`ask_fleet`, accounts) and the old Flash-Lite `ask_browser` are
  gone. `py -m spine seg run [lectures] [--limit N] [--workers N]` keeps its name (default 1 chat at a time, max 4).
  An answer writes `answer.txt`, `browser.json` and `reader.json` {"by": "gemini"}; a reply with no segment line goes
  to `reply_failed.txt` and the job stays unanswered. `segments.jsonl` rows say `geminiA+geminiB`.
- `spine/seg/segment.py`: **prompt v3**, `VERSION = 3`. New rules: never write a range twice (Wrong/Right example);
  still on the same line = start the next segment at that line (`P85-P96 = B51`, `P97-P104 = B51-B53`); tables and
  figures = follow the rows, else continue from the last line; the doctor going back (recap, "نرجع") = NONE, then
  continue; write each segment once, no drafts. Thresholds, placements, chapters and titles were NOT changed.
- `spine/runners/flows.py`: the dead `sp_seg` fleet entry is removed (its `SegFlow` never existed).
- `CLAUDE.md` reader lines: Arabic work (incl. segmentation) = Gemini Hydrogen; Haiku only for non-Arabic work.
- Tests: `tests.test_spine_seg` 87 OK (Gemini reader tests, prompt v3 tests; fleet tests gone).
  `py -m unittest discover tests` in this worktree: all pass except 3 that read gitignored data a worktree lacks
  (`test_titles`: `modules/year2-cns/old/.../reference.json`; the handout-target seg test:
  `modules/year2-cns/graph/sentences.jsonl`; `test_chapters` azony: Telegram lists). With the first two files copied in,
  480 ran and only `test_chapters` failed; it passes in the main checkout.

Backup before v3 (v3 makes every v2 job stale): `jobs/sp_seg_backup_v2_2026-11-18/` in the main checkout: all of
`jobs/sp_seg` (answers, state.json) plus the 21 `segments.jsonl` and their `spine/` shadow files;
`segments.sha256` there (cns-001 = `68632d3b98ae430a...`, as above).

Pilot (Gemini, free): the 16 v3 jobs of the 8 pilot lectures (021, 027, 036, 038, 045 + controls 001, 013, 040) are
in `jobs/sp_seg_v3_pilot/` in the main checkout, apart from the v2 jobs in `jobs/sp_seg/` (untouched). They were made
by a scratch script that loads this branch's `segment.py`/`flow.py` over the main checkout's data and sets
`flow.JOBS` to the pilot folder. When this note was written, all 4 Gemini accounts were held by a tumrah-book job
(`py -m flow.images.recheck --fleet 0 --web 1`, PID 6560, since 02:17); the pilot waits for a free account.
PILOT RESULT (Gemini 4 Hydrogen, prompt v3, 16 chats; the accounts freed up and it ran the same day):
**1 accepted, 6 rejected, 1 no answer.** Judged with `flow._judge_lecture` (same as `seg dry`):

| Lecture | Result | First problem (A / B) |
|---|---|---|
| cns-001 (control) | accepted, agree 97% | clean / clean |
| cns-013 (control) | rejected | A usable (4% offending); B `P6-P14 = B25-B25` goes back above B27, `P41-P53` over 12 paragraphs |
| cns-040 (control) | rejected | both `P50-P66` over 12 paragraphs, `P67-P78 = B42` goes back above B45 (A and B identical) |
| cns-021 | rejected | `P14-P22 = B29-B34` goes back above B43 / `P13-P21 = B30-B34` the same |
| cns-027 | rejected | `P77-P87 = B31-B33` goes back above B41 / `P11-P23` over 12 paragraphs |
| cns-038 | rejected | both `P26-P39` over 12 paragraphs |
| cns-045 | rejected | both `P22-P33 = B32` goes back above B36 (A and B identical) |
| cns-036 | no answer | both chats: Gemini said task.txt was not attached (the paste of the file failed) |

What it shows: Hydrogen ignores two prompt rules most: (1) at most 12 paragraphs per segment (an unrepairable
problem in `judge_segs`), and (2) the doctor going back = NONE (it maps the recap to the earlier lines instead, e.g.
cns-021 A `P69-P86 = B44-B49` after `B54`). A and B often answer the same, so two Hydrogen chats are not
independent readers (cns-040, cns-045). Not changed (owner's call): whether to let code split a long segment,
whether going back may be mapped, and whether to retry cns-036 or attach differently (paste the task as text).
Answers: `jobs/sp_seg_v3_pilot/<lecture>/<A|B>/answer.txt`; the script: `seg_pilot_seg.py` in the side-session
notes folder (loads this branch's `segment.py`/`flow.py` over the main checkout's data).

Still the owner's (unchanged): decisions 1-7 below. Rule 1 matters most for v3: the prompt now tells readers to
write `= B51` again to continue one line, and `clip()` still counts that as "re-states" (MAX_CLIPPED 20%).

Next: after the pilot, merge this branch, `py -m spine seg jobs` (all 93 become v3), `py -m spine seg run --workers 2`,
`py -m spine seg dry`, then `collect` (it removes the v2 shadow files of lectures not accepted under v3).

## Prompt for the next session (copy and paste)

```
Read CLAUDE.md, then docs/handovers/HANDOVER_2026-11-18_SEG.md in tumrah-data (branch spine-rebuild, tracks
origin/main). Task: make segmentation work with the new readers. The Antigravity fleet is retired (owner 2026-11-18);
segmentation is read by Haiku. Steps:
1. Build a Haiku reader for jobs/sp_seg (spine/seg): one call per task.txt, no tools, A and B independent calls; write
   answer.txt and reader.json {"by": "haiku"}. Remove the fleet runner from `py -m spine seg run` (keep the command).
2. Write prompt v3 (segment.PROMPT) that fixes what made readers fail: never repeat an earlier range, how to continue
   one book line (`= B51` again), what to do with a recap or a doctor going back, tables (few lines, long talk). Show
   the owner the prompt and the 4 judge-rule decisions below BEFORE any paid run. Changing PROMPT makes all 93 jobs
   stale: back up lectures/*/segments.jsonl and jobs/sp_seg/*/state.json first (`py -m spine seg dry` before collect).
3. Pilot: estimate tokens (section "Cost"), ask the owner, then run Haiku on 5 lectures that failed on reader error
   (cns-021, 027, 036, 038, 045) and 3 accepted ones (cns-001, 013, 040) as a control. Report accept/reject per lecture
   with the first problem line, and the real spend from the transcripts (not subagent_tokens).
4. Only after the owner's yes: the rest. Do not change thresholds, placements, chapters or titles yourself.
Never start fleet work. Tests: py -m unittest tests.test_spine_seg (82) and py -m unittest discover tests (463).
```

## Where it stands (verified 2026-11-18 by command output)

- Pushed to origin/main in `3172657`. Tests: `tests.test_spine_seg` 82 OK; full suite 463 OK.
- `py -m spine seg dry` / `flow._judge_lecture` over all 93 job folders: **21 accepted, 21 rejected, 3 disputed,
  48 waiting** (95 of 186 reader answers missing). The rows collect would write equal the 21 `segments.jsonl` files on
  disk, byte for byte. SHA-256 of the 21 files: first cns-001 `68632d3b98ae430a...`; full list was saved in the audit
  session's scratch folder (recompute with `sha256sum lectures/cns-*/segments.jsonl`).
- `py -m spine parity p2`: **17 of 21**. The 4 fails are old placement data, not code: each transcript talks about the
  pages next to its placement.

| Lecture | Placement pages | Reached pages | Evidence |
|---|---|---|---|
| cns-023 | 152-153 | 150-153 | P66 "referred" |
| cns-030 | 13 | 12-13 | P11 "EM", P23 "euchromatin" |
| cns-047 | 404-406 | 405-408 | P152 "window" |
| cns-049 | 410-412 | 411-414 | P74 "semicircular" |

## Why the 24 failed (rejected 21 + disputed 3)

| Cause | Lectures |
|---|---|
| Reader repeated an earlier range (the prompt forbids it), e.g. `P59-P70 = B37-B43` after `B37-B43` | 021, 027, 028A, 034A, 035A, 036, 038, 042B, 045B |
| Reader other error | 035B NONE where P54 says "pseudo-unipolar" (= B36); 037A and 045A went back; 012A mapped the neuron talk to "Sensory Receptors" |
| Our judge rule against our own prompt: a long talk on one line written `P85-P95 = B51`, `P96-P105 = B51` is flagged "re-states" by `clip()` (`c == d == previous d`) | 005A, 024, 026A, 033A, 034B, 051 |
| Doctor really went back (both readers agree; design is forward only) | 006 (P49 "نرجع لموضوعنا"), 022 (recap from P70), 029 (Golgi before Nissl) |
| Placement / slice | 011 (1177-line slice, both all NONE); 048 (talk runs to handout 410-411, placement 407-409) |
| Book split | 031: book page 6 (axon/dendrite table) is all `not_content`; both readers' NONE is correct |
| Transcript | 046: P11-P21 repeat P1-P10 |
| Agreement metric | 015: nested ranges (B58-B64 vs B58-B77) count as disagreement under the 5-line midpoint rule |

If the restatement rule did not count one-line continuation: 24 accepted / 15 rejected / 6 disputed. Not changed.

## Code bugs fixed in the audit (each with a test that fails without the fix)

- `spine/seg/segment.py` `judge_segs`: `SEG_LIKE.match` became `.search`; `Segment 2: P6-P8 = B11-B20` used to count as
  prose and up to 3 paragraphs became NONE silently.
- `spine/seg/segment.py` `conflict()` (new): the same stretch answered twice with different ranges (draft, then
  correction) used the first silently; now refused above `MAX_HOLE` (3 paragraphs).
- `spine/seg/flow.py`: `by` was hard-coded `fleetA+fleetB`; now from `reader.json`, else `browser.json`, else fleet.
  `make_jobs` clears `reader.json` with the old answer.

Kept from the earlier pass (tested): stale-job fingerprints (a moved placement, re-split book or changed transcript
makes a lecture `stale`, nothing written); a not-accepted lecture loses its shadow files; one lecture's error never
stops collect; `--limit 0` asks nothing; handout-target lectures (cns-008, 009, 010, 062-066, 078, 079, 088, 089)
write handout ids; `py -m spine seg dry` = collect's decision, read only.

## Reader interface (what a Haiku reader must do)

- Input: `jobs/sp_seg/<lecture>/<A|B>/task.txt`, self-contained (prompt, BOOK B1..Bk, TRANSCRIPT P1..Pn), up to 170 KB.
- One message, no tools. A and B are two independent calls (never show one reader the other's answer).
- Output: the reply text to `answer.txt` (UTF-8, lines `P<a>-P<b> = B<c>-B<d>` or `P<a>-P<b> = NONE`) and
  `reader.json` `{"by": "haiku"}` in the same folder. Then `py -m spine seg dry`, then `py -m spine seg collect`.
- Editing `segment.PROMPT` changes every task fingerprint: the next collect marks all 93 jobs stale and removes the 21
  accepted shadow files. A new prompt = new jobs (`make_jobs`) and new answers for every lecture.

## Cost (measure before running; Haiku is paid, ask first)

186 tasks = 13.2 MB of task text; the 95 missing answers = 6.3 MB. Rough input: about 1 token per 3.5 bytes, so
~3.8M input tokens for all 186 calls, ~1.8M for the 95 missing. Output is small (one line per segment). A new prompt
means all 186. Measure the real rate on the pilot from the transcripts before giving the owner the full estimate.

## Owner decisions (do not guess)

1. Restatement rule (`MAX_CLIPPED` 20%) vs the prompt's "a long explanation is several segments in a row".
2. Dominant rule (one range over 30% of paragraphs, min 20).
3. Agreement on nested ranges (`AGREE_WITHIN` 5 on midpoints).
4. Doctor going back (`MAX_OFFEND` 20%; forward-only design).
5. Placements: cns-011, cns-048, and the 4 parity lectures (023, 030, 047, 049).
6. Book split of page 6 (cns-031); the cns-046 transcript.
7. Prompt v3 text, and whether to run all 186 or only the 95 missing.

## Not proven

- Correlated errors: two readers given the same wrong book section can agree; only placement prevents that.
- Midpoint agreement can accept a wide range against a narrow one inside it (less precise, not wrong).
- No handout-target lecture has been accepted yet on real data (synthetic tests only).

## Commands

```bash
py -m unittest tests.test_spine_seg          # 82 tests
py -m unittest discover tests                # 463 tests
py -m spine seg dry [lecture ...]            # what collect would decide, writes nothing
py -m spine seg collect                      # writes shadow segments for accepted lectures
py -m spine parity p2
py -m spine seg audit <lecture>
```

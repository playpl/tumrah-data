# Handover: segmentation (spine seg), 2026-11-18 (Opus audit; replaces the earlier Haiku-written text)

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

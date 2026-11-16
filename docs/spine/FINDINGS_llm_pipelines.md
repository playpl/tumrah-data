Today's LLM spend goes mostly to whole-context reading. Workers get a whole lecture transcript, the whole handout behind search tools, or a 12–20-page handout window. Code never narrows them to a few candidate lines first. Four runners do this work:
- **Antigravity fleet:** headless agy with 4 subagents per job, model `gemini-3.8-flash-medium`, run by `dispatch.py`.
- **Gemini web:** via `gweb` in `gemini_run.py`. Only `flash-lite` (3.5 Flash-Lite) and `flash` (3.8 Flash) are allowed, with `-t` (thinking) for Flash.
- **Claude Haiku subagents:** via `haiku_run.py`.
- **Claude Code control chat:** `claude -p` started from `control.py:221`. It orchestrates and reads no data.

Token figures below come from my read-only sum of the fleet's `jobs/**/.agy-*.ndjson` logs (last `result.usage` per run). They are a floor: only the lead agent's usage is logged, subagents are not, and logs of removed folders are gone. `total_tokens` = input + output; cache reads are listed separately.

## 1. LLM job types: driver code

| Job | Builder / batching | Prompt template | Checker | Merger |
|---|---|---|---|---|
| Book to handout alignment (fleet) | `dm.book_jobs` dm.py:65 (`BOOK_BATCH=10` :49), `common.build` flows/common.py:62 | `BRIEF` flows/books.py:12 + `SUBAGENTS`/`WORKING_RULES` common.py:11,19 | `checks.check_alignment` checks.py:140 | `alignment_import_rows` checks.py:206, gives `jobs/books/<key>/aligned.jsonl`; `ledger.sync` ledger.py:181; `book_export.py` |
| Book alignment (web) | `run_book` gemini_run.py:478, `books` :536 | `BOOK_PROMPT` :352 | same checker, via `book_rows` :387 | same |
| Lesson placement, fleet / Haiku | `PlaceFlow.prepare` flows/place.py:48 | `BRIEF` place.py:14 | `check_place` checks.py:562 | place.py:99-104 calls `lectures.set_ranges`, `placed_by:"agent"` |
| Lesson placement, web | `place` gemini_run.py:292: **all queued lectures in one call** | `PLACE_PROMPT` :274 | same | same |
| Placement "bounds" (web, transcript to outline sections) | `bounds` :751, `bounds_scope` :714 | `BOUNDS_PROMPT` :696 | `bounds_spans` :730 | `ledger.put(kind lesson, runner web)` :788, then `placement.look` placement.py:44. **Never ran live**: log has 156 `dry:` lines and no web lesson rows |
| Transcript to handout ("lecture_links") | `LectureLinkFlow` flows/lecture.py:265; web `run_link` gemini_run.py:597 | `BRIEF` lecture.py:95; `LINK_PROMPT` gemini_run.py:577 | `check_lecture_dir` checks.py:489 (`check_clean` :428, `check_links` :450, `check_link_depth` :513) | lecture.py:290-298 copies to `lectures/<id>/links.jsonl` + `parts.jsonl` + `clean.txt`; ledger.py:191 |
| Transcription | `TranscribeFlow.expand` lecture.py:188 (code only, 300 s pieces); `PieceFlow` :226; web `run_piece` gemini_run.py:173 | `PIECE_PROMPT` lecture.py:150; web `PIECE_PROMPT` gemini_run.py:127 + `piece_text` :136 (code sets the times) | `check_transcript` checks.py:247; web gate 450 chars/min :43 | `merge_pieces` lecture.py:163 writes `raw.txt` |
| Question pointers, old flow (superseded) | `shortlist.send` shortlist.py:145, `titles.jobs` titles.py:135, `dm.pointer_jobs` dm.py:52 (25 per job) | `BRIEF` flows/pointers.py:12 + `LECTURE_SCOPE` :64 / `PAGES_SCOPE` :74 | `check_pointers` checks.py:29 | `pointer_import_rows` checks.py:96 |
| Question pointers, one read (current) | `titles.one_jobs` titles.py:230 (`WINDOW=20` pages :217, 25 questions + 2 decoys) | `INSTRUCTIONS` flows/pointers_one.py:24; `ORCHESTRATOR` :67 (`group=4` :86) | `check_dir` pointers_one.py:151 | `import_rows` :203 writes `pointers.jsonl`; ledger.py:169-180 (runner `fleet-A` / `haiku-A`) |
| Pointers (web) | `pointer_groups` gemini_run.py:826, `run_pointer_call` :876 (40 per call), `escalation_groups` :909 | `POINTER_PROMPT` :798 | `pointer_answers` :844 | `ledger.put` runner `web` |
| Pointer audit (Haiku) | `haiku_audit.build` haiku_audit.py:83 (50 per batch) | `TASK` :24 | `check_dir` :144 | `report` :175 |
| MCQ copy | `mcq.queue_book` mcq.py:48 (`PAGES_PER_JOB=10` :17) | `BRIEF` flows/mcq.py:13 | `check_mcq` checks.py:850 | `mcq.collect` mcq.py:80 writes `modules/year2-cns/mcq/*.jsonl` |
| Labels (Telegram headers / questions) | labels.py (`BATCH=40` :24) | flows/labels.py:21,48 | `check_labels` checks.py:633 | `labels/<stage>/*.jsonl` |
| Highlights + audit (now off: `highlights.auto=false`) | `highlights.job_payload` | flows/highlights.py:19,111 | `check_job_marks` / `check_audit` checks.py:804,820 | `exports/<m>/highlights.jsonl` |
| Cover (duplicate check) | `cover.candidates` cover.py:62 | flows/cover.py:12 | `check_cover` checks.py:533 | cover.py |
| Reference (handout lecture list, one-off) | flows/reference.py:47 | :13 | `check_reference` checks.py:591 | `reference.json` |

These files run jobs but do no reading themselves:
- `dispatch.py:41` `work`, `:88` `work_group`, `:137` `slot`
- `extra_dispatcher.py` (more slots)
- `fleet_pause.py` (suspends the process tree)
- `runners.py:64` `run_ai` (starts web bounds, then pointers)
- `haiku_run.py` `prepare`/`finish`
- `oob_transcribe.py`

`books_merge.py` is fully deterministic: it matches pages by hashing their text and copies the partial book's alignment into the full book.

## 2. Unit of work per job

| Job | Model is given | Returns | Granularity |
|---|---|---|---|
| Books (fleet) | 10 book pages (median 6.6K chars). Plus **the whole handout**: `common.build` copies the full 2.2 MB `lines.jsonl` into every job (common.py:69-71); the worker searches it with `tools/find.py` and `tools/page.py`. 4 subagents. | `out.jsonl`: per page, blocks `{n, text, match: same/reworded/partial/extra/not_content, handout: [{pdf_page, printed_page, verbatim text}]}`. Code turns the text into line IDs. | Book line or block (≤60 words) to handout lines |
| Books (web) | Same pages as numbered blocks + `handout.txt` cut by code to top-5 rare-word pages ±1 per book page (`candidate_pages` :443), 35–104 KB, median 60 KB | `{"page", "blocks": [[n, match, ["48.12", …]]]}` labels | Block to handout line labels |
| Place (fleet / Haiku) | Title, doctor, chapter lessons, other lectures' ranges, whole handout via tools, plus `transcript.txt` (example 76 KB, `jobs/place_haiku/cns-002`) | `place.json {ranges: [{first_page, last_page}], note}` | **Whole pages** |
| Place (web) | **Whole handout** `handout.txt` (462 KB) + every queued lecture at once (46 in one Carbon call) | `{lecture_id: {ranges, note}}` | Pages |
| lecture_links | **Whole `raw.txt`** (median 54 KB, max 134 KB) + the lecture's handout pages. Must re-emit the transcript as `clean.txt` word for word plus `fixes.jsonl`; the web version skips both. | `parts.jsonl {part, sub, title, start, end (s), line_ids}`, at least 1 part per 12 min, ≥75% of the recording linked, ≥3 lines per part on average | Time span (minutes) to a set of handout lines. **Not monotonic and not checked for monotonicity.** |
| piece | One 5-minute audio file | Verbatim text in timed paragraphs | 5 min |
| pointers_one | `read.txt`: 1–20 handout pages (median 12) as `p132:l2 text`, + ~25 questions with the key marked, + 2 decoys. Median 18.8 KB; 614 files total 12.6 MB. Lead orchestrator + 1 subagent per folder (4 folders). | `answers.jsonl {"q", "ids": ["p132:l2"], "because"}` or `{"none": "other_lecture" / "not_in_book"}`; at most 8 IDs | Question to lines |
| pointers (old) | 25 questions + whole handout via tools (optionally scoped to pages) + 4 subagents | Verbatim spans, resolved by `hub.resolve_span` | Question to lines |
| MCQ | 10 PDF pages of styled text (`[b]` / `[c]` marks, `mcq.styled_text` mcq.py:20) | `mcqs.jsonl {page, n, question, options, key, key_from}` | Question |
| Haiku audit | 50 items: question + chosen lines with ±1 neighbour line, or the script's best candidate | `verdicts.jsonl {n, verdict}` | Question |

## 3. Runners, batches, measured cost and errors

**Fleet tokens by flow** (from `.agy-*.ndjson`):

| Flow | Runs | OK | Input + cache read | Output | Per run (input + cache) |
|---|---|---|---|---|---|
| lecture_links | 200 | 69 | 18.0M + 221.9M | 4.93M | 1.2M |
| labels | 80 | 59 | 21.2M + 162.3M | 3.31M | 2.3M |
| books | 207 | 55 (31 with no result) | 21.3M + 109.2M | 1.49M | 0.63M |
| highlights | 36 | 6 | 7.6M + 70.0M | 0.66M | 2.2M |
| pointers (old) | 53 | 44 | 8.2M + 65.0M | 0.87M | 1.38M |
| piece | 233 | 196 | 7.3M + 17.1M | 2.58M | 0.10M |
| mcq | 43 | 15 | 4.2M + 18.8M | 0.49M | 0.53M |
| reference | 2 | 2 | 14.3M total | | 7.2M |
| pointers_one, orchestrator (lead only) | 112 | 94 | 3.1M + 10.1M | 0.5M | 0.12M + subagents not logged |
| pointers_one, direct | 39 | 38 | 1.4M + 4.8M | 0.32M | 0.16M |
| place | 65 | 8 (27 with no result) | 1.6M + 10.8M | 0.15M | 0.19M |

**Fleet slots:** `config.json` `slots`: zero 6, work 4, personal 6, other 6. Lanes: zero = piece/transcribe, work = mcq/pointers_one, personal = books, other = lecture_links/place. Every brief tells the lead to run 4 subagents. Accounts hit "Individual quota reached" (HANDOVER_2026-11-12 line 19).

**Haiku (paid):**
- 2026-11-09: 34.9M tokens for 20 jobs, about 1.7M per job (memory `haiku-cost-rule`).
- Rates in that memory: books ~2.5M per 10 pages, mcq ~0.6M, place ~0.8M, lecture_links 0.9–3M, hl_audit ~0.7M.
- 2026-11-12: about 63M (pointers ×2 batches, 40 MCQ jobs, 11 place jobs).
- 2026-11-14: 173 pointers_one jobs (4,024 questions). The owner stopped launches at about 92% of the 5-hour limit.
- Still waiting: 57 lecture_links estimated at 50–170M; 1,310 MCQ-book pointers estimated at ~115M.

**Gemini web:**
- No token counts exist, only quota percentages.
- About 20 Flash-Lite pieces moved an account's 5-hour usage by ~2%.
- About 10 Carbon calls with the whole 470 KB handout took 3 of 4 accounts to 100% in about 20 minutes.
- `jobs/gemini_run.log` has 220 "heavy call waits" lines (quota).
- 425 pieces passed (median 925 chars/min); 152 tries were rejected as "condensed".
- Books via web: 18 passed, 12 failed. Pointers via web: 80 ledger rows.

**Error and audit results:**
- **Haiku audit of fleet-A**, 200 sampled (`jobs/audit/fleet-A-1114`): 182 correct, 14 partial, 3 wrong, 1 missed. That is 1.5% wrong and 7% partial.
- **Ledger questions:** `fleet-A` 4,447 agreed / 1,298 conflict / 3,106 proposed. `haiku-A` 3,392 / 1,115 / 758. `script` 6,104 / 2,266 / 1,005. Caveat: `agree` (ledger.py:216) means the readers share **any** line, and the IDF script counts as a reader. Reader B was never built, so "agreed" is weak.
- **Word overlap vs AI** (11-10): same lines 36 of 42; found only 25%.
- **Placement** (11-10): 3 agree / 11 differ / 42 wait. `decisions`: bound 13 done / 20 open. `gold` table is empty.
- **Fleet run success:** books 55/207, lecture_links 69/200, place 8/65.
- **Held:** books 21 and lecture_links 27 held as `fleet: other`; 4 lecture_links held for line IDs outside the lecture's pages.

## 4. Where results live (year2-cns counts)

| What | Path / schema | Count |
|---|---|---|
| Ledger | `ledger.db` table `links(module, kind, src, runner, lines JSON, found, reason, scope, model, job, at, state)`, PK `(kind, src, runner)` (ledger.py:35); also `gold`, `decisions`, `rules` | block: fleet 4,540 + web 3,170. lesson: agent 76, covers 29, claude-coarse 16, claude-reading 14, claude 4, owner 3. part: 1,146. question: script 9,375, fleet-A 8,851, haiku-A 5,265, fleet 521, web 80 |
| Book alignment | `jobs/books/<module>-<book>-p<NNNN>/aligned.jsonl` (`book_id, page, page_kind, lecture_id, blocks[{n, text, figure, match, handout[], line_ids[]}]`) | 63 files, 594 pages, 11,451 blocks (same 5,730 · partial 950 · reworded 493 · extra 537 · not_content 3,741) |
| Lesson place | `lectures/<id>/lecture.json` `ranges[{from, to, pages, cut?}]`, `placed_by`, `pdf_pages`, `covers` | 143 folders. placed_by: agent 64, none 28, covers 24, claude-reading 14, claude-coarse 10, owner 3 |
| Transcripts and links | `lectures/<id>/raw.txt`, `clean.txt`, `fixes.jsonl`, `parts.jsonl` = `links.jsonl` | raw 95 (5.5 MB in total); links 62 |
| Pointers | `jobs/pointers_one/<key>/{read.txt, answers.jsonl, pointers.jsonl}` → ledger; `modules/year2-cns/site/fast_points.json` (`word_key → {lecture_id, lines, page, score, homes, by, reader?}`) | 614 pointers_one jobs (fleet-A 441, haiku-A 173; reader B 0); 592 old jobs held; fast_points 9,042 (5,961 from the ledger, 3,081 from the script) |
| MCQ | `modules/year2-cns/mcq/*.jsonl` | 1,925 rows, 1,403 keyed |
| Queue | `queue.db` `jobs(id, flow, key, payload, status, account, pid, tries, note, …)` | piece 581 passed, place 80 passed + 17 queued + 15 running, transcribe 36 queued |

## 5. Deterministic helpers you can reuse for the pre-filter

| Need | Function |
|---|---|
| Handout to visual rows (merges a bullet and its text, or a table row) | `hub._rows` hub.py:46, `split_handout` :96 |
| Normalising key (letters, marks, digits; Unicode-safe) | `hub.word_key` hub.py:37 |
| Verbatim text to line IDs (fuzzy on spacing and punctuation) | `hub.resolve_span` hub.py:123 |
| Sections cut at headings | `outline.is_heading` outline.py:33, `build` :45 (789 sections) |
| Tokenise and stop words | `fast_lessons.words` / `WORD` / `STOP` fast_lessons.py:49,40,35; `checks.TOKEN` checks.py:222, `tokens` :371 |
| IDF line scoring (±1 neighbour line as context) | `fast_lessons.build` fast_lessons.py:142-202 |
| Inverted index + IDF scorer per handout lecture | `titles.Scorer` titles.py:175 (`best` :199) |
| Lecture-specific rare terms; bank ranking | `shortlist.lecture_terms` shortlist.py:50, `rank` :74 |
| Rare-word candidate pages | `gemini_run.candidate_pages` :443, `handout_subset` :466, `escalation_groups` :909 |
| IDF owner matching | `own_questions.py:46`; `cover.candidates` cover.py:62 |
| Range arithmetic | `fast_lessons.merge_ranges` :61, `label_ranges` :72; `ledger.range_ids` :111, `lesson_ids` :127, `members` :277; `lectures.set_ranges` :161, `set_line_ranges` :174, `cover_ranges` :143; `placement._runs` :33 (gap bridging); `titles.windows` :221 |
| Monotonic-style checks | `checks.check_transcript` :247 (time never goes back); `timing_anchors` :277 (anchors must move forward); `check_links` :450 (parts in order, no overlap); `bounds_spans` :730 (runs of sections) |
| Word-exact transcript diff | `checks.check_clean` :428, `expected_tokens` :413 |
| Agreement and error statistics | `ledger.agree` :204, `wilson` :233, `ready` :262 |
| Page fingerprint and offset | `books_merge.page_hashes` :28, `page_offset` :39 |
| Book page to blocks | `gemini_run.book_blocks` :375; `checks.coverage` :124, `squash` :120 |

**Missing:** sentence splitting (handout "lines" are visual rows, not sentences), Arabic normalisation (alef, ya, ta marbuta, diacritics), embeddings, BM25, and any monotonic check on book→handout or transcript→book links. The only normalisation is NFKC, used for titles in `doctors_folder.py:58` and `tg_lists.py:52`.

## 6. How the handout and books are stored now

- **Handout:** `modules/year2-cns/handout.pdf` → `py dm.py lines` (dm.py:36) → `modules/year2-cns/lines.jsonl`. It has 9,837 rows: 9,450 text rows and 387 figures, over 456 pages, 66K words, median 7 words per row.
  - Row fields: `{id, module, hash, page, printed, n, text, figure, bbox}`.
  - ID format is `<module>:<sha8>:p<page>:l<n>` (or `f<n>` for a figure), for example `year2-cns:d30dcde2:p132:l1` (heading "HISTOLOGY OF THE CEREBRUM"), `…:p132:l2`, `…:p132:l3`.
  - l2 and l3 are **one sentence wrapped across two rows**. The atomic unit today is the visual row, not the sentence.
- **Structure:**
  - Handout lectures: 64, from `modules/year2-cns/old/agent-lecture-list-2026-11-08/reference.json` (an LLM `reference` job, 7.2M tokens). Anatomy 32, physiology 24, histology 8; each has `pdf_pages`.
  - Sections: `outline.json`, 789 heading sections `{id: "year2-cns:L01/s2", lecture, subject, title, from, to, page, i0, i1}`.
  - Site chapters come from the hand-written `site/mother_lists.json`, not from the handout.
- **Doctors' books:** `modules/year2-cns/books/<book>.pdf` plus a small `.json` card. Page text comes from fitz `get_text` (`dm.book_pages` :71).
  - 9 PDFs: mossafer 207, basel 119, elhusseiny 104, nageb 100, nagib-partial 100, zahran 84, elsamahy 53, ammar 20, ammar-partial 20 pages.
  - **The partials are aligned twice**: ammar 20 + nagib 100 = 120 of the 594 aligned pages.
- **Tumrah book:** an external repo at `config.book_root` = `C:/Users/Ahmed/Desktop/tumrah-book`. Only `highlights.py:35` reads its `chapter.json` files. I did not open it.
- **Example alignment records:**
  - `aligned.jsonl` block: `{"n":4,"text":"Processes","match":"same","handout":[{"pdf_page":13,"printed_page":3,"text":"2. Processes: There are two types of processes"}],"line_ids":["year2-cns:d30dcde2:p13:l28"]}`
  - ledger row: `kind=block, src="ammar-cns-hist-partial:10:11", runner=fleet, lines=[p23:l13, p23:l14, p23:l15], reason="reworded", job="year2-cns-ammar-cns-hist-partial-p0001", state=proposed`
  - Lesson: `cns-001 ranges [{"from":"…p11:l1","to":"…p13:l30","pages":[11,13],"cut":true}], placed_by "owner"`
- **Transcripts are never linked to a doctor's book.** They link only to handout lines (`parts.jsonl`, minute spans).

## The 5 biggest token sinks today

1. **lecture_links (transcript to handout):** about 240M fleet tokens logged, 1.2M per run, 69 of 200 runs OK. Every job holds the whole transcript in context and re-emits it as `clean.txt` (4.93M output tokens). Haiku is estimated at 0.9–3M per lecture, 50–170M for the 57 waiting; 32 are held. Evidence: flows/lecture.py:95-130, the ndjson sums, HANDOVER_2026-11-12 line 80.
2. **Question pointers, all flows:** old flow 73M (1.38M per run, whole handout searched by 4 subagents); pointers_one 19M logged for the lead only, with 614 × ~5K-token reads plus check reruns not logged; Haiku 173 jobs at about 92% of the 5-hour limit, plus about 63M on 11-12; MCQ-book pointers estimated at 115M. 592 old jobs were dropped as superseded. Evidence: titles.py:230, flows/pointers_one.py:93, the ledger conflict counts.
3. **labels:** about 184M (2.3M per run, 80 runs, 40 headers per job). Probably a one-off, but the largest per-run cost. Evidence: labels.py:24, the ndjson sums.
4. **Book alignment:** about 131M fleet (0.63M per run, 55 of 207 runs OK) plus Gemini web (35–104 KB handout per call) plus Haiku at about 2.5M per 10 pages. Every fleet job carries the full `lines.jsonl` and searches it; 120 duplicated partial pages were aligned twice. Evidence: flows/common.py:69, flows/books.py:64, gemini_run.py:443.
5. **Highlights:** about 78M for only 6 successful runs (13M per success), now switched off. The other close candidate is **placement**: whole handout plus whole transcript per call, 8 of 65 fleet runs OK, and Gemini Carbon with the full 462 KB handout drove 3 of 4 accounts to 100% in about 20 minutes. Evidence: flows/place.py:71-75, gemini_run.py:304, HANDOVER_2026-11-10_PLAN.md line 47.
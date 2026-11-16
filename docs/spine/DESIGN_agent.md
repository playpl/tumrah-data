Plan below. No plan file written: this agent has no write tool, so the plan is returned here only. Nothing was edited, downloaded or sent.

## 0. What I checked today (read-only)

| Finding | Source | Effect on design |
|---|---|---|
| Unique book text is small: 70.6K words, 687 pages. `ammar-cns-hist-partial` = `ammar-hist-1` (2,015 words each); `nagib-cns-phys-partial` = `nageb-phys-1` (16,309 each). | PyMuPDF word count on the 9 PDFs | Dedupe by page hash first. Phase 1 is a ~10K-sentence problem. |
| Old blocks are printed lines, not sentences: 11,451 blocks, 67,453 words, 5.9 words/block. | `jobs/books/*/aligned.jsonl` | Both sides need sentence joining. |
| Code-only match on the 7,173 old links: exact and unique in the whole handout = 2,504 (2,480 agree with the old link, 99.0%). Fuzzy `partial_ratio` >= 90 inside the lecture = 809 more (776 agree, 95.9%). 2,126 linked blocks are under 20 letters. | `hub.word_key` + RapidFuzz | Exact-unique is safe with no LLM. Fuzzy needs the order check. Short blocks need neighbour context. |
| 305 old `not_content`/`extra` blocks (>= 20 letters) appear verbatim in the handout. | same run | Old negatives are not trustworthy. Recheck all of them. |
| Handout right margins vary (523 / 544 / 505 pt). 527 rows hold an inner sentence break. | `lines.jsonl` bbox | Wrap detection needs a per-page margin. My crude fixed-margin test undercounts wraps, so the sentence count is not yet measured. |
| Transcripts: median 32K chars, max 81K; median 122 paragraphs, max 617. Latin-word share median 6.4%; 16 of 95 are under 2% (transliterated captions). | `lectures/*/raw.txt` | Full transcript fits one Gemini call. 16 lectures need term restoring for the code prior. |
| Mother message 1632: 382 chars, 18 posts. | `sources/lists/1632.json` | The mother agent costs about 1-2K tokens per changed message. |
| Tumrah book `chapter.json` = `{lessons:[{dir,name,first,last,start,end}]}`: handout pdf pages plus heading anchors. Chapter folders exist for only some chapters (Anatomy 1,3,4; Histology 1-5,7,8; Physiology 2,4). | `tumrah-book/modules/year2-cns` | Lesson scope for the Tumrah book is free. Chapters need another source. |
| Site already has `CourseResource` (lesson, objectKey, publicationStatus). | `backend/src/models/CourseResource.ts` | Whiteboards have a model; the brief said they did not. |
| `importLectureLinks` exists inside `importHubData.ts` (:158), fed by `lectures --lesson <id> --file links.jsonl --source`. | `importHubData.ts` | LectureLink rows need no new importer, only a run step. |
| No `university` field in any backend model. `AcademicModule.year` enum is `[1,2]`. | grep on `models/` | Website task. |
| Flow protocol is `lane, timeout, prepare(job, job_dir), check(job, job_dir), then(job, job_dir), expand(job)`. | `dispatch.py:42-90`, `flows/lecture.py:226` | New flows plug into `flows.REGISTRY`; `dispatch.py` stays untouched. |

Not checked: handout pages 1-9 (table of contents), the Tumrah book HTML, which scripts read `clean.txt`, which `placed_by` values `decisions.py` accepts.

## A. Package layout

Name: `spine/` (the handout is the spine). Run as `py -m spine <cmd>`. New tests go in `tests/test_spine_*.py` so the "Run tests" button picks them up.

| Module | Job | Key signatures |
|---|---|---|
| `spine/ids.py` | ID build and parse | `sent_id(module, sha8, page, n, sub="")`, `parse(id) -> dict` |
| `spine/text.py` | normalise, tokenise, Arabic normalise, term restore | `tokens(s) -> list[str]`, `ar_norm(s)`, `restore_terms(ar_text, lexicon) -> set[str]` |
| `spine/graph/handout.py` | rows to sentences, graph build | `sentences(lines, outline) -> list[Sentence]`, `build(module)` |
| `spine/graph/tree.py` | University/Year/Subject/Chapter/Lesson | `load(module) -> Tree`, `lesson_of(sent_id)` |
| `spine/books/split.py` | book PDF to sentences | `split(book_id) -> list[BookSentence]`, `dedupe(module) -> dict[alias, canonical]` |
| `spine/books/tumrah.py` | Tumrah book to sentences | `split_lesson(chapter_dir, lesson) -> list[BookSentence]` |
| `spine/align/bm25.py` | pure-python BM25 | `Index(docs, k1=1.4, b=0.6)`, `.top(query_tokens, k, allowed=None)` |
| `spine/align/prefilter.py` | scope, anchors, candidates | `page_lessons(book)`, `anchors(book)`, `candidates(book, i, k=8)` |
| `spine/align/windows.py` | window jobs, prompt, parser | `make_windows(book, w=12, stride=10)`, `render(window) -> str`, `parse(answer, window) -> list[Verdict]` |
| `spine/align/order.py` | Viterbi / LIS | `best_chain(cands, back_pen=2.0)`, `jumps(links)` |
| `spine/align/audit.py` | audit rules, confidence | `audit(book) -> list[Flag]`, `confidence(link) -> float` |
| `spine/align/old.py` | grade the 7,173 old links | `grade(book) -> dict[tier, list]` |
| `spine/tg/mother.py` | mother-message agent, cache, diff | `render(list_json)`, `parse(answer)`, `validate(map, posts)`, `diff(prev, new) -> list[Change]` |
| `spine/records/upload.py` | immediate upload state machine | `on_add(change)`, `watch()` |
| `spine/records/transcribe.py` | chunk plan, checks | `plan_chunks(duration_s, size_bytes, max_s=300, max_bytes=3_000_000)` |
| `spine/seg/prior.py` | code prior path | `prior(transcript, book_slice) -> list[int or None]` |
| `spine/seg/segment.py` | prompt, parser, monotonic repair | `render(lecture)`, `parse(answer)`, `check_monotonic(segs)`, `repair(segs, prior)` |
| `spine/site/export.py` | site files | `lessons(module)`, `lecture_links(lecture_id)`, `resources(module)` |
| `spine/site/apply.py` | calls website CLI | `upsert_lesson(row)`, `set_status(keys, status)` |
| `spine/polls/registry.py` | channel registry, inventory | `channels()`, `inventory()` |
| `spine/runners/flows.py` | registers flows | `register(REGISTRY)` |
| `spine/store.py` | SQLite index | `connect()`, `put_edge(...)`, `edges(src=None, dst=None)` |
| `spine/compat.py` | legacy file writers | `aligned_blocks(book)`, `lecture_files(lecture_id)`, `ledger_mirror()` |
| `spine/questions/__init__.py` | Phase 3 seam, docstring only | none |

**Store decision: new `spine/graph.db`, with JSONL files as the record.**
- Record files: `modules/<m>/graph/*.jsonl` (same pattern as the rest of the repo). `graph.db` is a rebuildable index (`py -m spine store rebuild`).
- `ledger.db` stays the only home of owner answers (`gold`, `decisions`, `rules`). `compat.ledger_mirror()` writes accepted links into `ledger.links` as `kind='block'|'part'`, `runner='spine-code'|'spine-fleet'|'spine-claude'`.
- Reasons: `links` PK `(kind, src, runner)` with a JSON `lines` blob cannot hold sentence IDs, per-edge confidence or 1-many groups. Bulk rebuildable rows would bloat the 20 kept ledger backups. The Today screen keeps reading the shape it knows.

`graph.db` tables:
```
nodes(id PK, kind, module, parent, ord, text, meta)
rows(sent_id, line_id, PRIMARY KEY(sent_id, line_id))
edges(src, dst, rel, grp, conf, by, state, at, PRIMARY KEY(src, dst))
votes(src, reader, answer, at, PRIMARY KEY(src, reader))
records(channel, post, lecture_id, state, detail, at, PRIMARY KEY(channel, post))
mother(list_id, sha, edit_date, map, at, PRIMARY KEY(list_id, sha))
```

**Migration adapters**

| Old consumer | Adapter | Cutover gate |
|---|---|---|
| `dispatch.py`, `queue.db` | `spine.runners.flows.register()` adds flows `sp_align`, `sp_seg`, `sp_mother`; lanes added in `config.json` | none; additive |
| `book_export.py`, `ledger.sync`, site `BookAlignmentPage` | `compat.aligned_blocks(book)` writes legacy block rows `{n,text,match,handout[],line_ids[]}` | `py -m spine parity p1` |
| `page.py`, `decisions.py` | `compat.lecture_files(id)` writes `lecture.json` `ranges`/`placed_by`, `links.jsonl`, `parts.jsonl` | `py -m spine parity p2` |
| `site_lessons.py`, `mother_check.py` | `spine.tg.mother` writes `modules/<m>/site/mother_lists.json` in today's shape | `py -m spine parity mother` |
| `control.COMMANDS` | add keys `spine-status`, `spine-update`; old strings unchanged | none |
| `update_data.py` | `config.json "spine": {"p1":"shadow","p2":"shadow","mother":"shadow"}`; `primary` swaps the step | per phase |

Cutover per phase: shadow run, parity report, owner OK, flag to `primary`, then `git mv` old scripts to `legacy/` and leave one-line re-export shims at the root.

## B. Handout graph and atomic sentence IDs

**ID**: `year2-cns:d30dcde2:p60:s5` = module : handout sha8 : page of first row : `s` + number of the first row. A row with two sentences gives `s5a`, `s5b`. Figures keep their line ID as the unit: `...:p60:f1`.
- The ID is anchored to the first row, so a later change to one join rule moves only the sentences it touches.
- Every sentence stores `rows`; old links re-derive mechanically if the splitter changes (`splitter` version field).

**Two-way map**: `sentences.jsonl` carries `rows[]`; `graph.db.rows` gives row to sentences. Site contract unchanged: every export converts sentence IDs to line IDs (`store.line_ids(sent_ids)`).

**Split rules** (deterministic, in this order):
1. Heading rows come from `outline.json`: `kind:"heading"`, never joined.
2. A row starting with a marker (`•`, `-`, `1.`, `a)`, `(i)`, roman) starts a unit.
3. Continuation: no marker, and the previous row's `x1` is within 12 pt of that page's right margin (95th percentile of `x1` on the page), and the previous row does not end in `. ? ! :`. A hanging indent (`x0` > unit `x0` + 6) also counts.
4. Cross-page continuation: only if rule 3 holds and the next page's first row starts lowercase.
5. Table rows (2+ gaps of 2+ spaces, or same band with 3+ parts): one unit per row, `kind:"table_row"`, header row text in `ctx`.
6. Inner split at `[.?!]\s+(?=[A-Z(])`, with an abbreviation list (`e.g.`, `i.e.`, `Fig.`, `N.B.`, decimals, list labels) and at least 3 words per side.
7. `ctx` = heading path plus the lead-in line of a list ("The motor nuclei are:"). Short list items stay atomic but carry context.

Invariants (tests): every text row belongs to at least one sentence; row order is kept; IDs are unique; a rebuild gives identical output.

**Tree source for year2-cns**
- University `ZU`, Year `2`: `modules/year2-cns/graph/graph.json`, hand-set once.
- Subject, Lesson: `reference.json` (L01..L64, subject, pdf_pages).
- Chapter: `reference.json` has none. Build `graph/chapters.json` once from the handout's contents pages and check it against the Tumrah book folder names. Owner confirms the file. It is about 20 lines.
- The 789 outline sections become a `section` attribute, not a graph level.
- NU later: module codes `nu-year1-<name>`; ZU keeps bare codes so current line IDs stay valid.

**Files** in `modules/year2-cns/graph/`:
```
graph.json     {"university":"ZU","year":2,"module":"year2-cns","handout":{"sha8":"d30dcde2","pages":456},
                "subjects":[{"id":"anatomy","chapters":[{"id":"anatomy/c1","n":1,"title":"...","lessons":["year2-cns:L03"]}]}]}
sentences.jsonl {"id":"year2-cns:d30dcde2:p60:s5","i":1312,"kind":"fact","marker":"•",
                "text":"Its cells form the second order neurons in the pain and temperature pathway from the body.",
                "rows":["year2-cns:d30dcde2:p60:l5","year2-cns:d30dcde2:p60:l6"],"lesson":"year2-cns:L04",
                "section":"year2-cns:L04/s7","ctx":["Nuclei of the posterior horn","a. Substantia gelatinosa of Rolandi (SGR)"],"splitter":1}
```

## C. Phase 1 engine

**Book side**: `modules/<m>/doctors/<doctor_id>/doctor.json` `{doctor_id, university, subject, list_id, books[]}`. Book sentence ID `bk:mossafer-anat-full:6f2a91c0:p12:s3`. Same join rules as the handout. Partial books: `books.dedupe` maps each partial page to the full book's page by `books_merge.page_hashes`; align once.

**Stage 1: scope by code.** Subject from the book card. Per page, IDF votes per handout lesson (as `gemini_run.candidate_pages`), then Viterbi across pages (lesson change penalty 1.0, backward 3.0). Output `book_pages.jsonl {page, lesson, margin, by}`. Margin under 0.2: use the top two lessons.

**Stage 2: accept with no LLM**

| Tier | Rule | Confidence | Measured on old links |
|---|---|---|---|
| A1 | `word_key` >= 20 letters, found exactly once in the whole handout | 0.99 | 2,504 blocks, 99.0% agree |
| A2 | exact, several hits, exactly one in the scoped lesson | 0.98 | 46 blocks, 45 agree |
| A3 | `partial_ratio` >= 90 in the lesson, BM25 top-1 is the same sentence, and it sits on the order chain between two A1/A2 anchors | 0.95 | 809 before the order check, 95.9% agree |
| A4 | under 20 letters, exact match, target lies between the targets of the two neighbours (gap <= 3 sentences) | 0.93 | covers part of the 2,126 short blocks |
| N1 | page under 15 words, or line is only digits / book title / doctor name repeated on 30%+ of pages | `not_content` | none |

Everything else goes to stage 3. Expected code-only share: 45-60% of linked sentences (estimate; `py -m spine p1 recall` measures it before any job is queued).

**Stage 3: candidates.** Pure-python BM25 over handout sentences with `ctx` as a second field (weight 0.3). No new dependency.
- Corridor first: an unresolved run between anchors `h_left` and `h_right` gets every handout sentence in `[h_left-3, h_right+3]` when that span is <= 60.
- Plus the union of BM25 top-8 per book sentence in the lesson, plus each hit's two neighbours. Cap 60 candidates per window.
- Embeddings: not now. No torch here, and the measured gap is in `reworded` (top-10 = 0.807 scoped). The corridor and the retry below close that gap without a model. Gate: if `p1 recall` shows the gold sentence inside the window's candidate set in under 95% of `reworded` cases, add an optional torch-free static-embedding stage. I have not verified any such package installs here.
- Recall escape: answer `0` ("not in list") always triggers one retry with the whole lesson listed (~150 sentences). `extra` is final only after two `0`s.

**Stage 4: fleet window task**
- Window: 12 consecutive book sentences, stride 10. Accepted ones show as `[done=H4]` context. A window with nothing open is skipped.
- Each window hides one already-accepted sentence as a probe. A wrong probe answer rejects the window.
- 10 windows per fleet job. No tools, no subagents.

Prompt skeleton:
```
You match sentences of a doctor's book to sentences of the college handout.
Do not open any file. Do not use tools. Do not start subagents. Reply with the answer lines only.

HANDOUT (lines starting with # are headings, context only)
# Nuclei of the posterior horn
H1 It corresponds to lamina II.
H2 ...

BOOK (consecutive sentences, in book order)
B1 [done=H4] ...
B2 ...

For every B line without [done], write exactly one line:
B<n> = <H numbers joined by +> <S|R|P>
B<n> = 0
B<n> = X
S = same words. R = same fact, other words. P = the book states only part of it, or more than it.
0 = a teaching sentence, but no handout line here states it.
X = not teaching content (title, page number, greeting, picture label).
Use 1 to 4 H numbers. Two B lines may name the same H.
```
Output grammar: `^B(\d+) = (?:(H\d+(?:\+H\d+){0,3}) ([SRP])|0|X)$`.

Code checks: each open B exactly once; H numbers exist; multi-H within 3 sentences of each other; `S` with token overlap under 0.6 becomes `R` and is flagged; `R`/`P` with no shared rare word is flagged.

Tokens: about 1.6K in, 0.1K out per window. Worst case 900 windows = 1.5M; two readers = 3.1M, all on the free fleet. Today: 0.63M x 207 runs = 130M, with 152 runs failed. Fleet per-run overhead is not measured.

**Stage 5: readers and order**
- Votes per sentence: code, fleet A, fleet B (other account, windows shifted by 5), and the old link as reader `old`.
- Accept at two agreeing votes. The old link counts as one vote, so most old links need only one new read.
- Order: Viterbi over the top-K targets per sentence; backward jump penalty 2.0, forward gap 0.02 per skipped sentence (cap 1.0). Piecewise monotone, because doctors reorder at section level.

**Audit rules** (`py -m spine p1 audit <book>`)

| Flag | Rule | Next step |
|---|---|---|
| orphan-book | content sentence with no edge and no `extra` verdict | re-queue |
| orphan-handout | handout fact sentence in a lesson the book covers, linked by no book sentence, while both its neighbours are linked | wide retry on nearby book sentences |
| jump | target more than 40 sentences from the median target of the 5 sentences either side, or in another lesson, while the neighbours agree | third reader |
| low-conf | confidence under 0.9 | third reader; under 0.6 redo |
| split-vote | readers disagree | third reader (Gemini web, stronger model) |
| coverage | page with over 15 words and zero verdicts | re-queue page |

**Claude verification**: only items still flagged after the third reader. One item = book sentence + `ctx` + up to 8 candidates, about 450 tokens; 20 items per call; Haiku. Estimate 200-400 items, 90-180K input tokens in total. Hard cap `config.json "spine": {"claude_budget_tokens": 300000}`; over the cap becomes an owner card.

**Old links (redo only what needs it)**
1. Lift each old link to sentence IDs through `rows`.
2. Keep with no new read: old link agrees with tier A1-A3. From today's numbers that is about 3,300 of 7,173.
3. One fleet read: the remaining `same`/`partial` (old vote + one new vote).
4. Full redo: `reworded` with token overlap under 0.3; jump flags; the 305 verbatim `not_content`/`extra`; every unaligned page (basel 0/12 jobs, elhusseiny 8/11 missing, mossafer 5/21 missing).

**Tumrah book**: scope per lesson from `chapter.json` (`first`, `last`, `start`, `end`). No prefilter; the candidate list is the whole lesson. Sentence IDs are content-addressed (`tb:<module>/<subject>/<chapter>/<dir>:s<sha6 of word_key>`), so a rebuilt HTML keeps the links of unchanged sentences.

**Picture-only books (Azony)**: no sentence alignment. Pages are stored as files tied to the lecture, like whiteboards. Lectures segment straight onto handout sentences (section D). Seam only: `books/ocr.py`, not built.

**Cross-links**: never stored. `store.cross(book_sentence)` joins through the handout sentence at read time, so doctor isolation holds in storage.

## D. Phase 2

**Mother-message agent**
- Runner: Gemini fleet, two readers. Claude Haiku only when the validator fails twice or readers disagree (about 1.5K tokens).
- Input (built by code from Telegram entities, not regex section parsing):
```
MESSAGE 1632 (numbered lines; [k] marks a hyperlink)
L1 DR.AMR MOSAFER
L7 - Spinal cord
L8  > Part 1 [5]   > Part 2 [6]
LINKS
[5] post 1660 youtube caption "Dr/Amr Spinal cord part 1"
[1] post 1661 pdf 7.6MB caption "Dr/Amr First chapter"
```
- Output, one JSON line per link: `{"link":5,"role":"lecture","chapter":"Spinal cord","name":"Spinal cord part 1","covers":[]}`. `role` is one of `lecture|mini|revision|ignore`.
- Validator: each link exactly once; a pdf or image post can never be a lecture (code rule); `mini` covers exactly one lecture; `covers` point to lecture links of the same doctor; names unique per doctor; order = message order; every post exists in the cache (as `mother_check`).
- Cache: `sources/mother/<channel>/<list_id>/<sha12>.json`, sha over text + entities + post metadata; `edit_date` stored. Same sha means no LLM call.
- Hyperlinks: a linked post that is itself a list is followed, depth <= 2.
- Diff by `(channel, post)`: `add`, `edit` (name, chapter, order, kind), `media_changed` (post `edit_date` or size), `delete`.
- Delete = `site.set_status([key], "draft")` + undo file + `lecture.json "state":"drafted"`. Local files stay.
- Safety valve: a diff that would draft more than 3 lessons or over 20% of one doctor's lessons is held as an owner card. A deletion applies only after two fetches 10 minutes apart both show it.

**Immediate upload** (`py -m spine records watch`, own process and lock, 3 workers)

| State | Action | Blocks on |
|---|---|---|
| `seen` | lecture id made, row in `records` | nothing |
| `lesson_upserted` | YouTube: site lesson upsert with `videoUrl` now | website task W1 |
| `downloading` -> `uploaded` | Telegram media: download, AAC 48k, `uploadLessonMedia.ts`, lesson upsert with `r2:<key>` | download only |
| `transcribing` | Opus 16k and chunks queued in parallel from the same download | never blocks upload |

Auto-publish needs the owner's flag `config.json "spine": {"auto_publish_records": true}`. Without it the same step makes a one-click card. `CLAUDE.md` currently says never write the website.

**Website repo tasks**

| # | Task |
|---|---|
| W1 | `importHubData lessons`: honour a per-row `status` (default `published`), add `--only-keys`. |
| W2 | New `lessons-status --keys a,b --status draft --reason telegram-delete`, with undo file. |
| W3 | New `resources` kind: whiteboards into `CourseResource` (lesson by `sourceRef`, `r2:` key); `uploadLessonMedia.ts` `TYPES` gains `.pdf .jpg .png`. |
| W4 | `lectures`: batch mode, one file for many lessons keyed by `sourceRef`. |
| W5 | `AcademicModule.university` (`ZU|NU`, default `ZU`). |
| W6 | Fix comments that name `importLectureLinks.ts` and `importHandoutLines.ts`; neither file exists. |
| W7 | Later, optional: `HandoutSentence` model. The site works on line IDs until then. |

**Transcription chunking**: `plan_chunks` cuts at the earlier of 300 s or 3 MB, snapped to silence within 15 s (ffmpeg `silencedetect`). Offsets go to `chunks.json [{n,start_s,end_s,bytes}]`. Checks: `checks.check_transcript` (450 chars/min), Arabic-script share >= 50%, no 8-word phrase repeated over 5 times. YouTube: captions give an instant `raw.txt` marked `source:"yt-captions"`; the fleet audio transcript replaces it when done.

**Segmentation**
- Slice: lecture -> doctor's book lesson by code. Mother-map name against book headings, plus the code prior. Slice = that lesson's book sentences, trimmed to prior min-30 .. max+30.
- Arabic vs English: Gemini reads both. For the code prior only, `text.restore_terms` maps Arabic-script tokens to handout terms by consonant skeleton + RapidFuzz. 16 of 95 transcripts need it.
- Prior: IDF overlap matrix (paragraph x book sentence), monotone DP with a NONE state. Zero tokens.
- Input: `BOOK` block (`B101 ...` with `## heading` lines) then `TRANSCRIPT` block (`P1 [00:00] ...`). About 13-37K tokens per lecture, against 1.2M today.
- Output grammar: `^P(\d+)-P(\d+) = (B(\d+)-B(\d+)|NONE)$`. Times come from paragraph stamps by code.
- Code checks: first segment starts at P1; each starts at the previous end + 1; last ends at Pn; `c <= d`; each next `c` >= the previous `d`; segment <= 40 paragraphs; range <= 120 sentences.
- Repair: keep the longest monotone chain of segments (weighted by paragraphs). Each offender gets a bounded re-ask: "choose a range inside B<lo>-B<hi>, or NONE". Over 20% of paragraphs offending: reject and rerun on another account; second reject: Gemini web; then Claude on bounded windows only; then owner card.
- Two readers agree when 90% of paragraphs map within 5 sentences. Otherwise re-ask only the disputed spans.
- No usable book (Azony): target = handout sentences of the lesson, in handout order. Same grammar with `H` numbers. Monotonic is a flag here, not a hard reject.
- Record: `lectures/<id>/segments.jsonl {"n":4,"p":[31,52],"start":912,"end":1544,"book":["bk:...:p12:s3","bk:...:p14:s9"],"handout":[...],"by":"fleetA+fleetB","conf":0.94}`.
- Today screen and site: `compat.lecture_files` writes `links.jsonl {part,sub:0,title,start,end,line_ids}` (title = book heading of the first sentence, by code) and `lecture.json ranges` (merged row ranges of the targets, `placed_by:"spine"`). `clean.txt` is no longer produced.

## E. Phase 0

1. `py -m spine graph build year2-cns`, then `graph check`.
2. Polls registry `polls/channels.json`, replacing `engine.CHANNELS` and `config.poll_channels`:
```
{"chat":"Batch58ATM","chat_id":4447068793,"university":"ZU","batch":58,"harvest":true,"seed_old":false,
 "windows":[{"year":2,"module":"year2-endocrine-and-reproductive","to":"2026-11-03"},{"year":2,"module":"year2-cns","from":"2026-11-04"}]}
```
   `polls` table gains `university, year, module`. Ready files move to `polls/ready/<university>/y<year>/<module>/questions.jsonl`. MSK = new registry rows only.
3. Year-1 deletion:
   1. `py -m spine polls inventory` (read-only): counts per channel x year x module in `polls.db`, `raw/`, `ready/`, `bank/`, the two `polls.before-*.db` files, and the outside export folder.
   2. Owner reads the table and confirms the scope in writing.
   3. `polls archive-year1`: copy to `archive/polls-year1-<date>/` with a sha256 manifest, verify, then remove from the live store in one transaction.
   4. Set `seed_old:false`; `engine.seed_old_keys` reads only registry rows with `seed_old:true`.
   5. `polls purge` deletes the archive only after a second owner confirmation.

Scope questions the inventory must answer first: `ZAG_59_Polls` is batch 59's live Year 1 channel and now carries MSK (window from 2026-11-04). Endocrine is Year 2 but not CNS. Year-1 questions already on the website are out of scope unless the owner says otherwise.

## F. Build order

| # | Step | Saves | Verify | Tests |
|---|---|---|---|---|
| 1 | Polls inventory (read-only) | owner wait runs in parallel | `py -m spine polls inventory` | `test_spine_polls.InventoryCounts` |
| 2 | Skeleton, `store`, `ids`, `text` | none | `py -m spine store rebuild` | `test_spine_ids.RoundTrip`, `test_spine_store.RebuildIsIdentical` |
| 3 | Handout sentences + tree | none | `py -m spine graph check year2-cns` | `test_spine_handout.EveryRowCovered`, `.WrapJoined`, `.InnerSplit`, `.ListItemKeepsCtx`, `.IdsStable` |
| 4 | Book split, dedupe, prefilter, tiers A1-A4, old-link grading | replaces 0.63M/run book jobs | `py -m spine p1 recall`; `p1 grade-old` | `test_spine_bm25.RanksExactFirst`, `test_spine_prefilter.ExactUniqueAccepted`, `.ShortNeedsNeighbours`, `test_spine_old.TierCounts` |
| 5 | Window flow, parser, order, audit, compat | finishes Phase 1 | `py -m spine p1 audit <book>`; `parity p1` | `test_spine_windows.GrammarRejectsBadLine`, `.ProbeFailRejects`, `test_spine_order.BackJumpPenalised`, `test_spine_audit.OrphanAndJump`, `test_spine_compat.LegacyBlockShape` |
| 6 | Segmentation: prior, flow, repair, compat | replaces 1.2M/run linking and the placement flow | `py -m spine seg audit <lecture>`; `parity p2` | `test_spine_seg.MonotonicEnforced`, `.RepairBoundedReask`, `.CoverageAllParagraphs`, `test_spine_prior.TranslitAnchors` |
| 7 | Mother agent, diff, records watch (after W1-W3) | ends hand-typed `mother_lists.json` | `py -m spine mother diff --dry`; `parity mother` | `test_spine_mother.PdfNeverLecture`, `.DiffAddEditDelete`, `.MassDeleteHeld`, `test_spine_records.UploadDoesNotWaitForTranscript` |
| 8 | Polls registry, Year-1 archive (after owner OK) | none | `py -m spine polls inventory` again | `test_spine_polls.SeedOnlyFlagged`, `.ArchiveManifestMatches` |
| 9 | Tumrah book alignment | none | `py -m spine p1 audit tumrah` | `test_spine_tumrah.ContentIdsSurviveRebuild` |

After every step: `py -m unittest discover tests` must still pass the 257 old tests.

**Risks**
- Sentence joining errors spread to every link. Step 3 needs an owner spot check of about 100 units before step 4.
- The candidate set caps recall. The `0`-retry and `p1 recall` gate guard it; the gate may still force an embedding stage.
- Fleet per-run overhead and its failure rate on closed-form jobs are unmeasured. Pilot 20 windows first.
- Auto-publish and auto-draft write production. A wrong mother parse reaches students.
- Doctors who reorder heavily will trip the monotonic rule often.

**Five most arguable decisions**
1. New `graph.db` plus a mirror into `ledger.db`, instead of new tables inside `ledger.db`.
2. No embeddings in the first build; corridor + BM25 + `0`-retry instead.
3. The old link counts as one reader vote. Cheaper, but it carries old errors wherever one new reader repeats them.
4. Azony: no book alignment, and monotonic only flagged. This bends "link at sentence level" for his page pictures.
5. Deletion mirroring has a debounce and a mass-delete hold, so it is not instant. Year-1 polls are archived first and purged only on a second confirmation.

### Critical Files for Implementation
- C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data\hub.py
- C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data\dispatch.py
- C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data\flows\lecture.py
- C:\Users\Ahmed\Desktop\Tumrah projects\tumrah-data\ledger.py
- C:\Users\Ahmed\Desktop\tumrah\backend\src\scripts\importHubData.ts
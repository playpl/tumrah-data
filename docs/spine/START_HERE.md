# Rebuild handover, 2026-11-16 (read this first)

The owner ordered a complete rebuild of tumrah-data. A planning session explored the repo with four sub-agents,
asked the owner seven questions, wrote a plan, and the owner approved it. **Nothing is built yet.** This folder
holds everything that session knew. You are the session that builds it.

## Read in this order

1. `docs/spine/OWNER_WORDS.md`: every owner message and answer, verbatim (the pasted master plan is item 3).
   Where any other file disagrees with the owner's words, the owner's words win.
2. `docs/spine/PLAN.md`: the approved plan. Section "Owner decisions as I understood them" is the contract.
3. `docs/spine/DESIGN_agent.md`: the detailed design (module signatures, file formats, split rules, prompt
   skeletons, output grammars, thresholds, test names). **Its section E (Year 1 archive then purge) is
   superseded** by the owner's later answers; use PLAN.md decision 5 instead.
4. `docs/spine/FINDINGS_llm_pipelines.md`, `FINDINGS_telegram_site.md`, `FINDINGS_polls_layout.md`: the full
   exploration reports with file:line (how everything works today, token costs, counts, bugs, dead code).
5. The repo's `CLAUDE.md` and the memory index, knowing that the rules listed under "Rules that change" below
   are being replaced.

## State at handover

- Approved: the plan (owner approved it through the plan-mode dialog on 2026-11-16).
- Built: nothing. `spine/` does not exist. No commit was made. No data file was changed. No Telegram call, no
  fleet call, no website call was made. The only new files are in `docs/spine/`.
- Git: branch `master`; 19 modified and 7 untracked source files from earlier sessions are still uncommitted
  (list in `FINDINGS_polls_layout.md`, end). The approved plan's first step is to commit them as a snapshot,
  then work on a branch for the rebuild.
- Do not commit these four stray files: `polls/polls.before-refresh-2026-11-14.db-shm`, `...db-wal`,
  `polls/polls.before-retire-2026-11-07.db-shm`, `...db-wal`. They appeared when an exploring agent opened the
  backup databases read-only. Add `*.db-shm` and `*.db-wal` to `.gitignore`.
- The memory index has one new entry for this rebuild (`rebuild-constitution`). Older memories that the rebuild
  replaces are named there.

## What I measured myself (re-runnable, read-only)

All on `jobs/books/*/aligned.jsonl` (the old book alignment, 7,173 linked blocks) against
`modules/year2-cns/lines.jsonl`.

1. Coverage per book (jobs with no `aligned.jsonl`): basel-hist-full 12 of 12 missing, elhusseiny-anat-1 8 of 11,
   mossafer-anat-full 5 of 21. All other books complete. Blocks by match: same 5,730, partial 950, reworded 493,
   extra 537, not_content 3,741.
2. Token overlap of a linked block with its handout rows (tokens = `[a-z0-9\u0600-\u06ff]+`, length > 2, NFKC,
   lowercased; overlap = shared / block tokens):
   - `same`: median 1.0 in every book; share below 0.3 is 0% to 9.4% (worst elsamahy 9.4%, ammar-hist-1 6.0%).
   - `partial`: median 0.75 to 1.0; share below 0.3 up to 14%.
   - `reworded`: median 0.0 to 0.69; share below 0.3 from 14% to 73%. Code cannot judge these.
   - No stale line IDs: all 7,173 links point at rows that exist.
3. BM25 recall (pure Python, k1 1.4, b 0.6, one handout row = one document, 11 seconds for everything). Is the
   linked row in the top k?

   | match | scope | top 1 | top 5 | top 10 | top 20 |
   |---|---|---|---|---|---|
   | same | handout lesson | 0.845 | 0.955 | 0.969 | 0.976 |
   | same | whole handout | 0.778 | 0.894 | 0.922 | 0.948 |
   | partial | handout lesson | 0.715 | 0.906 | 0.936 | 0.952 |
   | partial | whole handout | 0.529 | 0.744 | 0.809 | 0.867 |
   | reworded | handout lesson | 0.564 | 0.746 | 0.807 | 0.840 |
   | reworded | whole handout | 0.438 | 0.627 | 0.684 | 0.740 |

   The "gold" here is the old fleet answer, which is itself noisy for `reworded`. Scoping to the lesson is worth
   5 to 13 points. This is the evidence for "no embeddings in the first build, gate at 95%".
4. The design agent added: exact and unique `word_key` match agrees with the old link in 2,480 of 2,504 cases
   (99.0%); fuzzy `partial_ratio` >= 90 inside the lesson agrees in 776 of 809 (95.9%); 2,126 linked blocks are
   under 20 letters; 305 old `extra` / `not_content` blocks appear verbatim in the handout.

Installed Python packages that matter (Python 3.13): `numpy`, `RapidFuzz`, `PyMuPDF`, `Telethon`. Not installed:
torch, sentence-transformers, rank_bm25, any embedding library.

## How I read the owner's less clear answers

The owner approved PLAN.md, which states these readings. Still, the two actions that destroy or move poll data
must be preceded by `py -m spine polls inventory`, and its counts shown to the owner, before they run.

- "https://t.me/zagpolls58 This is the archive for year one. Gather all the questions, set them as grade 5
  questions dealing with it later, except the repeated one. Remove them from here completely." My reading: the
  archive's questions leave the live bank and ready files and go to a separate grade 5 store; duplicates are
  dropped (a question also seen in a backbone channel stays with the backbone); nothing is destroyed; the
  channel is no longer harvested.
- Asked what happens to Batch58ATM's Year 2 polls that are not CNS (endocrine 22,595, other 4,305), the owner
  said: "No. That channel is going to work for year 1 only, not for 2. Delete them all. Do not archive them.
  Delete them. Remember, also, we are working on MSK for year 1 and CNS for year 2." My reading: delete those
  non-CNS Year 2 polls for good, with no archive. The first sentence does not fit the question; if the inventory
  shows anything surprising, ask before deleting. The 1,013 unlabelled and 1,097 Year-1-labelled rows in that
  channel are kept, because module labels were made by the fleet, not by the owner.
- "Wait, did I tell you to delete anything except for the one in the next and the previous question? I did not
  tell you to delete anything. The data is good. Just update it for everything other than the year 2 from the
  previous question." So the pasted plan's "delete all Year 1 polls" is withdrawn. Year 1 data stays and keeps
  updating. Old backup files are left alone.
- Quizzes and files: "Now we will gather them from here, starting from this message onward, and do not read the
  files. Skip the files. Get the links only." and later "the files: you're going to have to figure out what this
  file is ... from the content, you're going to understand it. If you can't, just tell me." My reading: the first
  crawl of `t.me/zagexam59/503` (Year 1) and `t.me/ZMSUMcqs58/2098` (Year 2) follows hyperlinks and stores the
  link map only, with no file download. Files are classified later from tree position and caption first, content
  only when needed, and an unclear one becomes a question to the owner. "From this message onward" = from
  message 503 and 2098.
- "You remember, you're just a planner" was said about designing that file classification, during planning.

## The owner

- Wants speed and wants Fable sub-agents doing the build in parallel ("token burning on you").
- Standing rule: never ask permission for fixes or imports; do, then report. Questions are welcome only when
  something is truly undecidable (which lesson a quiz belongs to, what a file is). He was annoyed when a
  question implied he had ordered deletions he had not.
- Claude is paid: at run time the free Gemini fleet does the reading. "The fleet is stupid": give it tiny closed
  tasks that code can check. No loss of quality is acceptable.
- Reads Arabic and English. Earlier rules about handovers, the Today screen and the control room still hold:
  the Today screen and control room must keep working during the migration.

## Rules that change (rewrite `CLAUDE.md` and memory when each takes effect)

| Old rule | New rule | Takes effect |
|---|---|---|
| Mother messages by hand in `mother_lists.json`; never code or guesses | An LLM agent reads the mother message; code validates; the file is generated in the same shape | when `parity mother` passes |
| Never touch the website; publish only on command | A new record is uploaded and its lesson upserted at once; a Telegram deletion drafts the lesson with an undo file | when the website importer changes W1 to W3 are in and dry-run clean |
| Lecture placed on handout pages, parts linked to handout rows | Transcript segments map to the doctor's book, strictly forward; the handout is reached through the book | Phase 2 cutover |
| Link unit = handout visual row | Link unit = atomic sentence; rows stay as the site contract | Phase 0 |
| Questions: required / doctor / extra tiers | Grades 1, 2, 4, 5 (see PLAN.md decision 7) | Phase 3, last |
| Only the owner adds PDFs; list PDFs are never touched | Still true for mother-message PDFs. New: files in the two quiz/file channels are catalogued and classified | Phase 3 |

Unchanged: keys come only from Telegram's correct flag; our own votes never count; `db.py` only reads;
"Update data" keeps working through the old scripts until each phase is switched to `primary`.

## What I was about to do

1. Snapshot commit of the 26 pending source files on `master`, then a branch for the rebuild.
2. Write the package skeleton myself so the parallel agents share one contract: `spine/__init__.py`,
   `spine/__main__.py` (each subpackage exposes `cli.register(subparsers)`; `__main__` imports a fixed list),
   `spine/ids.py`, `spine/text.py`.
3. Launch build agents in parallel on disjoint files: A (handout sentences, tree, store) first; D (mother
   render / validate / diff, records state machine) and E (polls registry and inventory, link-tree crawl) at the
   same time, since they do not need sentences. B (book engine) and C (segmentation) start when A's
   `sentences.jsonl` exists, because their recall numbers need real sentences.
4. Review A myself: spot-check 100 sentences across anatomy, physiology and histology pages before B starts.
   A sentence-joining mistake spreads to every link.
5. Show the owner the polls inventory, then do the two poll changes.
6. Pilot 20 fleet windows before any bulk alignment.

Contract I intended to give every build agent:

- Allowed imports: standard library, `numpy`, `rapidfuzz`, `fitz`, `telethon`. No new dependency without asking.
- Write only under `spine/`, `tests/test_spine_*.py`, `modules/<module>/graph/`, `docs/spine/`.
- Tests are `unittest`, offline, on small fixtures; `py -m unittest discover tests` must stay green (257 old tests).
- Never run `update_data.py`, the dispatcher, any website importer, any Telegram write or vote. Never edit
  `lectures/`, `ledger.db`, `queue.db`, `polls/`, `bank/`, or the owner's Today-screen answers.
- Reuse, do not copy: `hub.py`, `outline.py`, `books_merge.page_hashes`, `titles.Scorer`,
  `gemini_run.candidate_pages`, `ledger.wilson`, `checks.check_transcript`, `index_tree.links_of`.

## Tool notes

- The Agent tool failed twice with an empty error when `model: "fable"` was passed. Leaving `model` out works
  and the agent inherits Fable.
- Explore and Plan agents cannot write. Use a general agent type for building.
- A sub-agent's final report can be recovered from
  `C:\Users\Ahmed\.claude\projects\C--Users-Ahmed-Desktop-Tumrah-projects-tumrah-data\<session>\subagents\agent-<id>.jsonl`
  (last long assistant message). That is how the files in this folder were written.
- Data folders are gitignored (`lectures/`, `modules/*/site/`, `polls` data, `bank/`, `jobs/`, `sources/`,
  `doctors/`, `ledger.db`). A git worktree would not contain them: work in this checkout.
- SQLite files: open with `file:<path>?mode=ro` for any look that is not a planned write.

## Not verified yet

- Handout pages 1 to 9 (contents pages) as the source of chapters; `reference.json` has lessons and subjects
  but no chapters.
- The number of sentences the splitter will produce (527 rows hold an inner sentence break; right margins vary
  by page: 523, 544, 505 pt).
- The Tumrah book's HTML shape (only `chapter.json` was read; chapter folders exist for Anatomy 1, 3, 4;
  Histology 1 to 5, 7, 8; Physiology 2, 4).
- Which scripts still read `clean.txt`, and which `placed_by` values `decisions.py` accepts.
- Fleet overhead per run and its failure rate on closed-form window tasks.

## Open items for the owner (raise when the work reaches them, not before)

- MSK (Year 1) has no handout PDF in the repo; `doctors/msk/` holds one empty file. Nothing can be linked for
  MSK until the handout is there.
- `chapters.json` for year2-cns (about 20 lines) needs one look from the owner.
- Cocci still has no site doctor id.
- No NU data exists anywhere; the schema only reserves the place.

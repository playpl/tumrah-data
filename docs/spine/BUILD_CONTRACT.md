# Build contract for every agent that builds part of `spine/`

Read first, in this order: `docs/spine/START_HERE.md`, `docs/spine/OWNER_WORDS.md` (wins over everything),
`docs/spine/PLAN.md`, `docs/spine/DESIGN_agent.md` (section E is superseded by PLAN.md decision 5), then the
`FINDINGS_*.md` file(s) named in your brief. Then read the skeleton that is already written and is the shared
contract: `spine/__init__.py` (file layout, row shapes, helpers), `spine/__main__.py`, `spine/ids.py`,
`spine/text.py`, `spine/store.py`, `spine/parity/__init__.py`, `spine/runners/flows.py`, `tests/test_spine_core.py`.

## Rules

1. Branch `spine-rebuild`, this checkout (data folders are gitignored, so no worktree). Never stash, reset, switch
   branches or commit. The lead session commits.
2. Write only the files your brief names as yours, plus your `tests/test_spine_<area>.py`. Other agents work at
   the same time on other files. Do not edit `spine/__init__.py`, `__main__.py`, `ids.py`, `text.py`, `store.py`,
   `parity/__init__.py`, `runners/flows.py`: if you need a change there, say so in your final report.
3. Allowed imports: standard library, `numpy`, `rapidfuzz`, `fitz` (PyMuPDF), `telethon`. No new dependency.
4. Reuse, do not copy: `hub.py` (`word_key`, `resolve_span`, `Line`), `outline.py`, `books_merge.page_hashes`,
   `titles.Scorer`, `gemini_run.candidate_pages`, `ledger.wilson`, `checks.check_transcript`,
   `index_tree.links_of`, `tg_lists.py`. Use `spine.text` for every tokenising, `spine.ids` for every ID.
5. Never run `update_data.py`, the dispatcher, the fleet, any website importer, any Telegram write or vote.
   Never edit `lectures/`, `ledger.db`, `queue.db`, `polls/` data, `bank/`, `sources/lists/`, the hand-written
   `modules/year2-cns/site/mother_lists.json`, or the owner's Today-screen answers. Read SQLite files with
   `file:<path>?mode=ro` (backup databases with `?mode=ro&immutable=1`).
6. Nothing is deleted, anywhere. No file download from Telegram unless your brief says so.
7. Tests: `unittest`, offline, small fixtures built in the test (never the real data files, never the network).
   `py -m unittest discover tests` must stay green (265 old tests + `test_spine_core`). Run it before you finish.
8. Commands: your package has `cli.py` with `register(subparsers)`; a handler is set with
   `parser.set_defaults(run=fn)` and returns an exit code (0 = fine). `spine/__main__.py` already lists it.
   Output goes to stdout as plain text a person can read; every command that could write takes `--dry`.
9. Code style of this repo: small modules, a docstring at the top that says what the file is for and how to run
   it, plain functions, no classes unless state needs one, no speculative options. Comments say why, not what.
   Plain English in every message a person reads.
10. Windows, Python 3.13, run with `py`. Paths through `pathlib`; files read and written as UTF-8.
11. Final report (your last message): what you built (files), the commands and their real output numbers, what
    you could not verify, every change you need in a shared file, and every question only the owner can answer.
    Do not paste long file contents. Large findings go in `docs/spine/NOTES_<your letter>.md`.

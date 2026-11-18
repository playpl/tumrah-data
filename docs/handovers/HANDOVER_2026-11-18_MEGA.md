# MEGA handover: finish the whole data rebuild (2026-11-18, night)

This file is the single starting point for the session that completes everything. It replaces the "Left to do"
lists of older handovers; those stay as detail. Scope = the owner's master prompt (`docs/spine/OWNER_WORDS.md`
message 3) as changed by his later answers (`docs/spine/PLAN.md` decisions, `CLAUDE.md`, memory).
The item-by-item check of that prompt is `docs/spine/COVERAGE_2026-11-18.md` (about half built; read it).

## Prompt for the next session (copy and paste)

```
Read CLAUDE.md, then docs/handovers/HANDOVER_2026-11-18_MEGA.md in tumrah-data (branch spine-rebuild, push to
origin main). Do section 0 first (settle what the two earlier sessions left), then the workstreams in order.
Each workstream ends with tests green (py -m unittest discover tests), a commit, a push and one line in the
"Progress" section of that handover. Readers: Gemini web 4 Hydrogen for all Arabic work (transcription,
segmentation, alignment); Haiku only for non-Arabic work, and only after a token estimate the owner accepts.
Never the fleet. Never Claude sub-agents. No recording download/upload on the PC: GitHub "Records" only.
Do not ask before fixing or importing; ask only the owner decisions listed in section 3.
```

## 0. Settle first (state at hand-off, 00:40 UTC 2026-11-18)

Two sessions started from the records session were still working when this was written:

- **seg** (`claude/seg-followup-3f2305`, worktree `.claude/worktrees/seg-followup-3f2305`): moved segmentation to
  Gemini web (4 Hydrogen), prompt v3 (`f90d953`, `2a455f6`, `2669e24`). NOT merged, NOT pushed. Pilot: 1 of 8
  accepted (cns-001); rejects come from segments over 12 paragraphs and going back up the book; cns-036 got no
  answer (attachment failed). Its branch also rewrites the CLAUDE.md "Readers" section (Arabic = Gemini, Haiku
  non-Arabic only; the memory index already says so). Merge it into `spine-rebuild` (check `git log` and the
  diff first), then push.
  It then committed v4 (`5db2b7c`: per-paragraph answers, no length or order rule), ran its pilot and stopped: the
  account hit its 5-hour limit, then a cache-cost hook dropped "Try again". v4 result (its task output, judged):
  2 of 8 accepted (cns-036 87%, cns-040 87%); rejected cns-013, 021, 027, 038, 045, mostly "N paragraphs not
  answered" (cns-038 B left 229 of 267, NONE for 89%); cns-001 B no answer. Before W1: its worktree is clean;
  merge the branch (v4 is on it), fix the unanswered paragraphs, then pilot again.
- **update-data** (this checkout): DONE, commit `181d321`. Update data with `pc_transfers: false` (nothing moved on
  the PC); 14 new CNS lectures cns-164..177 (Mosafer 1870-1871, Azouny 1877-1879, Wagih 1864-1866, Zahran 1869
  and 1876, Nageb 1872-1875) added BY HAND to `mother_lists.json` (6 new chapters), `mother_check` exact; site
  import: 14 lessons created, 158 changed; year 1 +6 lessons (91 wait for uploads); polls restarted (old log
  ended in "database or disk is full"; disk now 111 GB free; saved as `polls/engine.before-restart-2026-11-18.log`;
  votes needed 643). FLEET INCIDENT: the Update data step "mother messages (agent, add only)" started fleet
  readers (`agy.exe`) despite `fleet.down`; they were killed; `spine/tg/cli._run` and `update_data.py`
  (`fleet_down()`) now skip that step.
  Its Update data pulled the year 2 log before the runner had uploaded, so the 14 had no cloud key; the records
  session ran `cloud.year2.pull()` after (14 rows `cloud: true` in `media.json`) and the site import again.
  Open from it (owner): Wagih list 1631 has two revision items with no real post ("Basal ganglia" -> 1848 gone;
  "limbic system" -> 1847 = the lecture itself); Elsamahy post 1880 "Stretch reflex part 2" is not linked from
  list 1637 yet (it is imported once linked); 26 decisions wait on the Today screen; 6 changed year 2 lists
  (1630, 1631, 1632, 1635, 1637, 1638) have no agent map now that the fleet is gone (W5).
- After every Records run, Update data's step "year 2 records (GitHub)" (`cloud.year2.pull`) must run before the
  site import, or new lessons go up without audio (seen 2026-11-18).
- GitHub "Records" run #5 (`44207708010`) was running: year 1 at 4.9-5.3 MB/s, 3000 MB cap; the cron run at
  02:17 UTC takes the rest. Check with `gh run list --workflow records.yml`.

## 1. Rules (all still in force)

- Owner rules in `CLAUDE.md` and the memory index. The most used: never ask before fixing/importing (report
  after); read every changed Telegram list yourself; `mother_lists.json` by hand + `py mother_check.py` exact;
  keys only from Telegram's correct flag; no biochemistry; Year 1 = all old data;
  Year 2 "Old data" lists = fallback only; never click the owner's Today-screen answers; compress before upload.
- Fleet RETIRED (`config.json` `fleet.down: true`). Code still wired to it must move to Gemini web before it runs:
  `dm.py run`, `runners.py`, `gemini_run.py` model names, `py -m spine p1 run`, `py -m spine mother flow`
  (readers A/B), the `transcribe`/`piece` flows in `queue.db`. Gemini web = `gemini_browser.py` (signed-in Chrome
  profiles, 4 accounts, model 4 Hydrogen; never gweb/cookies, never 3.1 Pro/Carbon/Argon).
- No heavy transfers on the PC: `config.json` `"pc_transfers": false`. Recordings move only in GitHub Actions
  "Records" (`cloud/records.py`, `cloud/year2.py`, `docs/handovers/HANDOVER_2026-11-18_RECORDS.md`).
- One Telegram reader at a time on the PC (Update data, `tg_lists.py fetch`, polls job). The runner has its
  own session.
- Use `gh` for GitHub (start, cancel, status). A running job's log is only in the web page (browser pane);
  `gh` gets it after the job ends. WARP blanks that live log: leave input `warp` false.
- Haiku costs money: estimate tokens, ask the owner first (memory `haiku-cost-rule`).

## 2. Workstreams, in order (each: what, where, done when)

### W1. Segmentation: transcript -> doctor's book, strictly forward (Phase 2 step 5)
- Where: `spine/seg/` (`prior`, `scope`, `segment`, `flow`, `cli`), `docs/handovers/HANDOVER_2026-11-18_SEG.md`.
- Now: main checkout (v2) 21 accepted, 21 rejected, 3 disputed, 48 waiting of 93 (`py -m spine seg dry`).
  Branch v3 on Gemini: pilot 1 of 8.
- Needs the owner's answers (section 3, items 1-2), then: implement them in `segment.judge`/`repair`; retry
  cns-036 with the task pasted as text; pilot the same 8 again (target 7 of 8); then all 93
  (`seg jobs`, `seg run --workers 4`, `seg collect`). Khaled's 12 have no placement and no book: report.
- Then primary: the Today screen and the site's `LectureLink` rows read `lectures/<id>/spine/` files
  (`compat.lecture_files`); retire `clean.txt` and the placement flow (PLAN.md Phase 2 step 5).
- Done when: every lecture with a transcript and a book is accepted or is a Today card; `seg audit` shows zero
  backward jumps; `parity p2` written; site import carries the new links (dry run first).

### W2. Transcription (Gemini web)
- Year 2: 107 of 176 lectures have `raw.txt`. Year 1: 104 Telegram records have none (94 have YouTube/Gemini).
- The runner leaves a 16 kbps Opus copy per record at `ops/tumrah-data/hear/<module>/<id>.16k.ogg` (`hear_key`
  in the records log; year 2: `source.cloud.hear_key` in `lecture.json`). Fetch that small copy (allowed: a few
  MB), transcribe on Gemini web (`py -m spine records transcribe|finish --via browser` exists for year 1; year 2
  uses `flows/lecture.py` via the retired fleet: move it to the browser path).
- Never block uploads on transcription. Done when every recorded lecture has a transcript or a logged failure.

### W3. Phase 1 tail: doctors' books -> handout (CNS)
- `spine/align/`; edges in `modules/year2-cns/graph/edges/` (7,135 rows over 7 books); about 470 sentences open;
  200-link audit per book (126 read, 0 wrong). Readers move to Gemini web (`p1 jobs|run` used the fleet).
- Then `py -m spine p1 accept year2-cns`, `parity p1`, the audits, and the primary switch (`config.json`
  `"spine": {"p1": "primary"}`) so the old `jobs/books/*/aligned.jsonl` flow retires.
- Known: `mossafer-anat-full` keeps "P a g e | 99" lines as content; Ammar's no-ruling tables (splitter limit).

### W4. Year 1 (ZU MSK), then ZNU
- MSK handout graph: 5,918 sentences; `chapters.json` empty: owner picks (section 3 item 3); then `graph build`
  and `graph check` (10 of 10).
- Year 1 books: none split. Find the year 1 doctors' books in `doctors/` (owner-added PDFs only), `py -m spine
  books split`, then W3's engine for `year1-musculoskeletal`. Then year 1 segmentation (W1's flow).
- Year 1 site: 74 old-data lessons live; the rest appear as the runner uploads (site import after each run).
  Cocci (ZAG59_physio/58) and ZAG59_bio/34 site ids: owner. The site needs the "old data" note (website ask).
- ZNU (`modules/nu-year1-musculoskeletal/`: handout PDF + `lines.jsonl` only): build its graph
  (`py -m spine graph build nu-year1-musculoskeletal`, check the splitter on it like the MSK note did);
  doctors, lists, polls and site module wait for the owner's sources (section 3 item 4).

### W5. Mother agent and Telegram sync
- `spine/tg/mother.py` + `flow.py`: exact on 10 of 10 year 2 doctors, but its readers were the fleet: move to
  Gemini web. Shadow -> primary only with the owner's word (section 3 item 6).
- Edits and deletions (draft + undo, two-fetch rule, mass hold): diff exists; needs website W1/W2.

### W6. Website asks (another session, in `C:\Users\Ahmed\Desktop\tumrah`, branch, dry run first)
- `docs/spine/WEBSITE_ASKS.md`: W1 importer honours `status` and `--only-keys`; W2 lessons-status draft + undo;
  W3 `CourseResource` for whiteboards/files (`lesson_files.jsonl` waits for it); W4 `lectures` batch by
  `sourceRef`; W5 `AcademicModule.university`; year 1 "old data" note.

### W7. Tumrah book -> handout
- Waits for the tumrah-book session's export (READY.jsonl bundles, agreed 2026-11-17). Lesson scope from its
  `chapter.json`; same window engine as W3.

### W8. Phase 3: questions (last, as the owner ordered)
- Bank: 35,942 questions (27,731 poll only, 6,425 forms, 1,751 with an MCQ book sighting, 75 QuizBot); grade 5
  archive 39,954 (`polls/grade5/`); doctor tags on 6,669.
- Build: `grade` on every row (1 doctor's quizzes, 2 MCQ books, 4 polls, 5 archive); grade 2 matching of MCQ
  books to polls (code similarity first, then a reader); the link trees (`zagexam59` 503, `ZMSUMcqs58` 2098)
  classified by position/caption, content only when needed, unclear = Today card; MCQ files extracted then the
  raw file archived; every question linked to handout sentences (scope by poll title or tree position, BM25,
  closed window); "no quiz outside a lecture" check = 0.
- The owner said he will add details for this phase: ask him when W1-W5 are done.

## 3. Owner decisions waiting (ask when the work reaches them)

1. Segmentation: may code split Gemini's segments longer than 12 paragraphs?
2. Segmentation: may the doctor go back up the book (today such a range becomes NONE)? And the restatement rule
   (v3 says repeat `= B51`; `clip()` still counts that against MAX_CLIPPED 20%).
3. MSK chapters: (a) the four from `reference.json` or (b) other (`modules/year1-musculoskeletal/graph/NOTE_2026-11-18.md`).
4. ZNU year 1: its Telegram sources (lists, polls, quiz channels) and site module.
5. MSK poll channels (master prompt: "I will provide them later").
6. Mother agent to primary (replaces the by-hand `mother_lists.json` rule).
7. Site doctor ids: Cocci (ZAG59_physio/58), ZAG59_bio/34; Dr. Khaled's year 2 doctor id if still missing.
8. Seg handover's other open decisions (`HANDOVER_2026-11-18_SEG.md`).
9. The mother agent's new reader: Gemini web or Haiku (CLAUDE.md said Haiku for mother maps; the owner later
   said all Arabic work is Gemini's, and the lists are Arabic). Until then Claude reads changed lists by hand.
10. Wagih list 1631: the "Basal ganglia" revision links post 1848 (gone) and "limbic system" links 1847 (the
    lecture itself): what are the real posts? Elsamahy post 1880 waits for the list to link it.

## 4. Where things are

| What | Where |
|---|---|
| Coverage of the master prompt | `docs/spine/COVERAGE_2026-11-18.md` |
| Spine design and plan | `docs/spine/PLAN.md`, `DESIGN_agent.md`, `HANDOVER.md` (numbers, history) |
| Records on GitHub | `cloud/`, `.github/workflows/records.yml`, `docs/handovers/HANDOVER_2026-11-18_RECORDS.md` |
| Segmentation | `spine/seg/`, `docs/handovers/HANDOVER_2026-11-18_SEG.md` |
| Book alignment | `spine/align/`, `spine/books/`, `modules/year2-cns/graph/{books,edges,votes}` |
| Mother messages | `spine/tg/`, `modules/year2-cns/site/mother_lists.json`, `mother_check.py` |
| Polls | `polls/` (engine, `channels.json`, `grade5/`), `docs/spine/POLLS_INVENTORY_AFTER.md` |
| Questions (old system) | `bank/questions.jsonl`, `merge.py`, `fast_lessons.py`, `pointers` flows, `ledger.db` |
| Site import | `py site_import.py` (dry: `--dry`), `site_lessons.py write` |
| Tests | `py -m unittest discover tests` (479 OK at `27f76a1`, before the two sessions' files) |

## Progress (one line per finished workstream)


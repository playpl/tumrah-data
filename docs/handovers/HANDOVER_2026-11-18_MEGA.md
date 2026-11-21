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

- 2026-11-18 04:50 local. Section 0 done: seg branch merged (`bc7734e`), pushed; worktree left (only an untracked
  settings file); cns-164..177 all have `source.cloud.hear_key`. Records runs #5 and the 02:17 cron: success.
- W1 (in progress): the v4 "N paragraphs not answered" was the PARSER, not Gemini: readers name several places per
  paragraph (`P6-P7 = B25, B34`), which `segment.LINE` rejected (`f06a7f9`: lists of ranges; rows add `parts`).
  Re-judged pilot, no new calls: 7 of 8 accepted (013 98%, 021 90%, 027 94%, 036 90%, 038 98%, 040 87%, 045 96%);
  cns-001 B still unanswered. Owner decisions 1 and 2 are moot under v4 (no length or order rule).
  The `Locator.click: Timeout` on all 4 accounts = Hydrogen at its usage cap (the option disappears from the mode
  menu). `gemini_browser` now reads the renewal time, skips capped accounts, `py gemini_browser.py limits`; seg
  `run --wait` sleeps until a renewal (`f9441a5`). All 93 jobs written (171 chats, 8 pilot lectures' answers
  copied in); `py -m spine seg run --workers 4 --wait` running, log `jobs/sp_seg_run_2026-11-18.log`.
- Readers moved off the fleet (`78d4bae`): `py -m spine records hear2` (year 2 transcripts; Hydrogen), year 1
  `records transcribe` defaults to browser + Hydrogen, `p1 run` = Gemini (`--per-job` windows per chat; the fleet
  runner refuses while `fleet.down`), `mother run` readers = two Gemini chats, Update data's mother step on again.
  Decision 9 settled by CLAUDE.md (Arabic = Gemini). Not run yet: Hydrogen is capped and seg goes first.
- 2026-11-20. Student complaints: 54 of 137 live CNS lectures (cns-112..177, all of Khaled's 12) had no ranges, so no
  questions. Placed by title onto handout sections (`placed_by: claude-coarse`, backups
  `backups_pre_update/place54_2026-11-20/`), site import (`logs/site_import_2026-11-20_place54b.log`): 1,692
  questions inserted, live CNS questions 9,043 -> 10,941, every lecture 12..312 questions. The seg run of
  2026-11-18 had stopped (Hydrogen cap; `seg dry` 15 accepted, 78 waiting); only 11 of 172 lessons have LectureLinks.
- 2026-11-20. Owner answers recorded in CLAUDE.md "Owner answers (2026-11-20)" (section 3 items 3, 6, 7, 10 settled;
  Gemini cap fallback = 3.5 Flash-Lite; grade 3 = other doctors' MCQ files). ZU MSK on the site: handout
  (`books/year1-musculoskeletal/handout.pdf`), 7,273 handout lines, Tumrah book 75 pages (second bundle, 421 blocks).
  ZNU Tumrah book NOT uploaded: no site module, no university field (website W5). `page.py` accepts clicks from
  `localhost` as well as `127.0.0.1` (the Today screen gave 403 when opened as localhost).
- 2026-11-20 evening, PAUSED by the owner (session limits). Owner: "work on MSK and CNS; MSK is MORE important".
  Done: Gemini cap fallback (`856ec7f`: capped account -> Flash-Lite until renewal, also in the transcribers);
  Update data (`logs/update_2026-11-20.log`): cns-178..191 imported (10 wait for the Records runner, Khaled's 4 are
  YouTube); `auto_doctors.plan` fix: a second lecture of the same title counts only when the list links both posts
  (Nagib "Internal capsule" 1895 = new; Elsamahy 1807 = re-upload of cns-107's 1793, NOT new). `py auto_doctors.py sync`
  exited 0 but made NO lecture for 1895 (silent): find why (`plan` lists it as new) and import it.
  NEXT, in this order:
  1. MSK first: site import (`py site_import.py`; year 1 said 91 waiting for uploads before the 639-row pull);
     MSK lesson ranges onto the handout graph (L01-L39, `reference.json`) so MSK questions (ZAG_59_Polls 5,018)
     reach MSK lessons; transcribe the 104 year 1 Telegram records (`py -m spine records transcribe --via browser`);
     split and align year 1 doctors' books.
  2. CNS mother lists: agent failed on Zahran 1635 and Nagib 1638 (no agreed map). Add BY HAND to
     `mother_lists.json`: Zahran "Outer fibers layer (eye)" (cns-182, post 1889) as its own chapter; Nagib
     "Internal capsule" (1895, second item of that name), "Speech" (cns-190), "Aphasia" (cns-191) as chapters in
     list order. Mosafer 1632: post 1870 (cns-164) belongs under "Blood supply of brain stem + cerebrum" per the
     list's link; cns-179/180 are revisions. Then `py mother_check.py` exact, then `py site_import.py`.
  3. Place the new CNS lectures (cns-178..191 + 1895) like the 54 (`claude-coarse`), site import.
  4. Restart the polls job (Polls.bat); then `py -m spine seg run --workers 4` (93 lectures; Flash-Lite fallback
     now), `py -m spine records hear2` (year 2 transcripts), P1 tail, Phase 3 grades (CLAUDE.md owner answers).
  Owner still to give: ZNU Telegram sources, MSK poll channels. ZNU Tumrah book waits for website W5.
- 2026-11-20 night. Update data again (`logs/update_2026-11-20_b.log`): post 1895 imported (cns-193; the earlier
  silent miss did not repeat), plus Mosafer "4th ventricle" cns-192 (1913) and Nagib Thalamus/Limbic
  system/Hypothalamus cns-194..196 (1910-1912). `mother_lists.json` by hand: Mosafer cns-164 moved under "Blood supply
  of brain stem + cerebrum" (the list's link; the extra "Blood supply of cerebrum" chapter removed), Zahran "Outer
  fibers layer (eye)" cns-182, Nagib Internal capsule (2nd)/Speech/Aphasia/Thalamus/Limbic system/Hypothalamus as
  chapters; `mother_check` exact. 17 new lectures placed by title (`claude-coarse`, backups
  `backups_pre_update/place17_2026-11-20/`; Khaled "ECG" put on Brain waves/EEG pp. 253-256). Records runs
  44800264347 + 44801289095 uploaded all new CNS audio except cns-178 (post 1888: Telegram timeout twice on 8
  connections; run 44802371341 retries with connections 0). Site import `logs/site_import_2026-11-20_c.log`.
  Polls job restarted (313 new ZAG_59_Polls polls to vote). Seg: 8 stale jobs rewritten, `seg run --workers 4 --wait`
  started (`logs/seg_run_2026-11-20.log`).
  FINDING (owner): the 198 year 1 records are first-term topics (cytology, cytogenetics, epithelium, membrane
  transport, body fluids, ANS, blood, general anatomy: bones/joints/muscles/terms of movement), NOT the ZU MSK
  handout (limbs L01-L20, cartilage/bone/muscle/skin histology L21-L24, skin/nerve/muscle physiology L25-L39). They
  cannot be placed on MSK handout ranges; MSK questions cannot reach them. Asked the owner where they belong.
- 2026-11-21. Owner pasted the MSK lists: `trees.json` `year1` = ZAG59_Anatomy 137-141, ZAG59_physio 241-243,
  ZAG59_Histo 212/214/219/220/221 (old lists kept as `year1_first_term`). MSK maps built on Gemini (13 of 13 agree):
  42 records. The 170 first-term lessons stay on the site until the owner decides. Ammar "Cartilage 2" (232) holds
  the same YouTube as his revision (231): doctor's wrong link.
  QUALITY CHECK (owner: "measure first"; seg run stopped): `docs/spine/quality_2026-11-20/REPORT.md`. Seg on
  accepted lectures 46 of 50 right (2 wrong, 2 unsure); A=B agreement does not catch shared errors. Transcripts:
  20 pieces heard again agree on content in 18 (2 old copies have ~42% repeated text); 13 of 83 heard transcripts
  have 40+ word repeats (cns-010, cns-037 serious); YouTube captions (28) drop English terms. Five pieces wait for
  the owner's ear in `listen_2026-11-20/` (not in git).
  Site import (`logs/site_import_2026-11-20_c.log`): CNS 19 lessons created, 172 changed; 18 MSK lessons created
  (YouTube); 21 MSK Telegram records wait for the runner; tiers: cns-070 timed out once (next import redoes it).
  PAUSED (owner, limits). NEXT, in order:
  1. `py update_data.py` was STOPPED mid-run (`logs/update_2026-11-21.log`): run it again (pushes the MSK to-do for
     the runner), then `gh workflow run records.yml`, then `py site_import.py` after the run.
  2. cns-178 (post 1888) still has no audio: Telegram timeouts on both connection modes; check the next run's log.
  3. Owner: listen to `listen_2026-11-20/` (README inside); decide the 170 first-term lessons on the site.
  4. Fixes from the quality report (REPORT.md "Fixes"): re-hear the 13 repeat transcripts + worst YouTube captions,
     strip `[cite: N]`, a gold-set check besides A=B agreement; then resume `py -m spine seg run --workers 4 --wait`
     (stopped; 25 accepted, 65 waiting).
  5. Ammar "Cartilage 2" (232) wrong video: wait for the doctor. Polls job finished (restart with Polls.bat).

- 2026-11-21 night (session 3). Owner mid-session: "burn the fleet" beside Gemini, Haiku last; "fleet is very stupid"
  (question linking): fleet only on code-checkable work (CLAUDE.md "Fleet back"; `fleet.down` stays true for the old
  flows). Done: Update data (`logs/update_2026-11-21_b.log`): agent added Zahran revisions cns-197/198 "Nervous
  tissue part 1/2" (list 1635, read by hand: covers neuron..receptors, sit in the last covered chapter),
  `mother_check` exact. `[cite: N]` stripped from 55 transcript files (`strip_cite.py`; 46 seg answers kept by
  re-fingerprinting, 186 of 186 jobs current); `gemini_run.piece_text` strips them from now on. MSK lessons now carry
  handout ranges: `modules/year1-musculoskeletal/site/placement.json` (record -> L01..L39, coarse by title / transcript
  words) over the graph's lesson cuts (`spine/records/flow.py` `lesson_spans`, `ranges_of`); 18 live MSK lessons
  changed on the site. `hear2 --via fleet` (zero, work, personal; "other" fails auth: `py C:\Users\Ahmed\agy-fleet\fleet.py
  login other`), model flash, piece check + loop check (40+ repeated words), `cNN.fleet` markers and
  `source.heard_by_fleet`. Six looped pieces (cns-010 c09, 037 c00, 034 c00, 038 c02, 043 c08, 045 c00) moved to
  `backups_pre_update/rehear_loops_2026-11-21/` with their raw.txt: they are re-heard by the fleet run.
  Records runs 44842878852 (cns-198 + 4 MSK uploaded; cns-197 Telegram timeout) and 44846091744 (max_mb 6000, the 17
  MSK left). Seg run on Gemini (`logs/seg_run_2026-11-21.log`). Polls job restarted.
  MSK doctors' books: none in `doctors/msk`; the lists carry them (Elazouny 157-160/172-175, Mosafer 179/184, Nagib
  249 "full book" 16 MB, Mahmoud 213/225, Zahran 240 module book 33 MB, Ammar 228): not fetched (no heavy transfers
  on the PC); W4 books wait for them (owner adds, or a runner step for PDFs).
- 2026-11-21 01:20 UTC. Owner: the PC download rule is for recordings only (PDFs fine); "just run" the MSK questions.
  MSK books: 24 list PDFs in `sources/lists_pdf/<channel>/<post>/` (`py tg_lists.py download -c <channel> ...`); 7 books
  in `modules/year1-musculoskeletal/books/` (Mosafer 179, Nagib 249, Cocci 252, Mahmoud 225 + part 1 213, Zahran 240
  (+229 alias), Ammar 228), split: 5,985 sentences; `p1 code`: 2,883 accepted; 121 Gemini jobs written
  (`py -m spine p1 run year1-musculoskeletal` after the seg run frees the browsers). Elazouny's 8 parts (157-160,
  172-175) are scans with no text layer and no OCR on the PC: Gemini must read them (not done).
  MSK questions: `msk_questions.py` (ZAG_59_Polls since 2026-11-14 under topic headers -> handout lessons -> best line
  -> least loaded live MSK lesson); 388 published on 35 MSK lessons, 296 with handout pointers; ~600 wait because
  their handout lesson has no doctor lecture yet (forearm..lower limb, muscle/skin histology, nerve/muscle physiology);
  `site_import.py` step 8 files them as lessons appear. Spot check 8 of 8 right. Not done: the zagpolls58 archive
  (grade 5) for MSK, doctors' MCQ files for MSK (none in the lists).
  Records: 20 of 21 MSK recordings uploaded, 38 MSK lessons live; cns-197 (84 MB) and y1-hist-245 time out on Telegram
  (8 connections and fallback); a run with connections 0 started.

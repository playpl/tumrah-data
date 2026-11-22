# Progress 2026-11-22 (session 6, after the chain)

- The background chain finished: seg collect 186 accepted / 1 waiting / 8 rejected (cns-194 widened to step 2:
  `py -m spine seg jobs cns-194`); p1 both modules accepted; msk_mcq collect 1059 agreed keyed book questions.
- CNS quizzes: 5 forms had failed on URLError (refetched), and post 2192's caption link had no `https://`, so its
  15 keys never joined (fixed in `msk_quizzes.questions`). Now 66 of 66 posts, 967 keyed, 941 filed into lecture.json
  `required` (230 with the bank's votes kept, 26 wait: no lecture of that doctor on the topic).
- MSK: `msk_questions.py build` with the book keys: 977 site questions (was 821); 936 rows wait for the arm/forearm
  lessons that are not live yet (L08-L39 handout lessons).
- Mother 1638 (Nagib): reader A's 11-20 answer was cut at link 40 and reused every run (moved aside to
  `jobs/sp_mother/1638-5d6bcfc1a7e3-A/result.cut-2026-11-20.json`); the validator refused "Internal capsule" twice,
  which is right: the list holds two items with those words (posts 1821, 1895). `mother.validate` now allows a repeat
  name only for two list items with the same words. Hand names set to the list words: cns-167 "Cerebrum part 2 + lat.
  Ventricle", cns-176 "Cerebral cortex part 2".
- Update data: 12 new (cns-199..210: Mesafer Scalp part 1, Zahran Middle vascular layer, Samahy UMNL-LMNL lesion,
  Spinal cord lesion + 3 revisions, Nagib Reticular formation + 4 revisions); recordings wait for the runner.
  Samahy moved "Extrapyramidal tracts" from empty post 1892 to 1924: cns-185 now points at 1924 (hand file and
  lecture.json; its recording, 52 min, already in the bucket, was kept). Parity mother 10 of 10, mother_check exact.
- YouTube: the WARP run (45047182493) made all 6 hearing copies; `records rehear-youtube` done; hear2 of the 6
  (78 pieces, Hydrogen) done: 78 of 78 heard, 6 transcripts ready (logs/hear2_youtube_2026-11-22.log).
  NEXT: segment the 6 again on the new transcripts (`py -m spine seg run`), then `py site_import.py`.
- Site import run after Update data: logs/site_import_2026-11-22.log.

# Progress 2026-11-22 (session 5, stopped at usage limit)

Done and committed:
- seg: split pair (one reader NONE after retry) -> third reader C; 2 of 3 NONE widens; prior sums no longer depend on
  the hash seed (cns-075 flipped stale). 183 CNS accepted; 8 sent to reader C, 3 waiting.
- MSK questions: `msk_quizzes.py` (56 zagexam59 quiz posts, 569 keyed: forms + QuizBot), `msk_mcq.py` (10 MCQ book
  PDFs in sources/lists_pdf/zagexam59, 90 Gemini jobs written), `msk_questions.py` files them: 821 site questions
  (was 388), grade 1 = 289 with Required lists (msk_required.json), grade 3 = 194, 71 wait (arm/forearm).
  NOT YET IMPORTED: run `py msk_questions.py import` (or `py site_import.py`).
- YouTube re-hear: `cloud/youtube.py` + workflow step; YouTube refuses the runner (bot check). A WARP run
  (45047182493) was in progress. If it fails too, the 6 lectures in cloud/rehear_youtube.json keep captions.
- legacy/: haiku_run.py, haiku_audit.py.
- `cns_quizzes.py`: the ZMSUMcqs58 tree had 51 of 56 CNS doctor quiz forms never keyed. Hand map of 65 posts to CNS
  lectures written. Keys were running (logs/cns_form_keys_2026-11-22.log, sources/cns_quizzes/quizbot/run.out).
  NEXT: `py cns_quizzes.py show`, then `py cns_quizzes.py apply`, then `py site_import.py`.

Running in background at stop (one chain, same Gemini accounts): seg run -> seg collect (logs/seg_run_2026-11-22.log)
-> p1 readers A, B, C both modules + accept (logs/p1_2026-11-22.log) -> mother 1638 re-read
(logs/mother_1638_2026-11-22.log) -> msk_mcq run + collect (logs/msk_mcq_2026-11-22.log).
After the chain: `py msk_questions.py build` again (book questions), then Update data (`py update_data.py`) and the
site import. Seg 148/159 (Azouny, Khaled) are at the top of the ladder: Today cards.

# Progress 2026-11-23 (session 7)

- Parallel Gemini runs used ONE account: every worker of `seg run --workers 4` started on acct1 at the same moment and
  waited on its lock (`take` blocks), so acct2-4 sat idle. `gemini_browser.ask` now takes the first account that is
  free at that moment (`try_take`, never waits on one busy account); test `ParallelAccounts`. Seg run restarted:
  all 4 accounts busy (logs/seg_run_2026-11-23.log; cns-001/002/003/006/124/125/175/194 + 158/159).
- Records workflow cron had skipped since 17:48 UTC; run by hand (45076983272): cns-199..210 uploaded, hear copies
  made; `cloud.year2.pull` put them in lecture.json. Fleet hear2 on zero,work,personal + a second run on `other`
  (signs in again): logs/hear2_fleet_2026-11-23.log, logs/hear2_fleet_other_2026-11-23.log.
- NEXT: when the hearing ends, `py -m spine seg jobs` for cns-199..210, `seg run --workers 4 --wait`, `seg collect`,
  then `py update_data.py` and `py site_import.py`.

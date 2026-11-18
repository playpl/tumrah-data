# Handover: recordings on GitHub for both years, 2026-11-18 (Opus session)

## Owner rules from today (also in memory)
- NO heavy uploads or downloads on the PC anymore (recordings). Recordings move only on the GitHub runner, both years.
- The Antigravity fleet is retired. Readers: Gemini web, model 4 Hydrogen (transcription, linking); Haiku for the rest
  (paid: estimate tokens, ask first). CLAUDE.md "Readers" section and `config.json` `fleet.down: true` say so.
- Owner tip to try: Cloudflare WARP on the runner ("brought a 1 hour download to a minute").

## Prompt for the next session (copy and paste)

```
Read CLAUDE.md, then docs/handovers/HANDOVER_2026-11-18_RECORDS.md in tumrah-data (branch spine-rebuild, tracks
origin/main). Finish the year 2 records flow on GitHub and the runner speed-up, exactly as section "To do" says.
No heavy uploads/downloads on the PC (owner rule). Never use the fleet. Test with py -m unittest discover tests,
commit, push to origin main, then start the "Records" workflow in the browser pane and read its live log.
```

## State at hand-off

- origin/main = `514e8f5`. Pushed today: `3a063a5` runner fix, `3172657` seg fixes, `c0a0d65` outline guard,
  `35f8dc8` MSK cut, `514e8f5` fleet retired + seg handover. Full suite was 463 OK at `514e8f5`.
- UNCOMMITTED, half done: `cloud/state.py` (per-module records logs `log_path(module)`/`log_key(module)`,
  `push_year2_todo` / `pull_year2_todo` with key `ops/tumrah-data/inputs/year2_todo.json`; its `main push` imports
  `cloud.year2`, which does NOT exist yet). Finish it or `git checkout cloud/state.py`.
- GitHub run `44202314916` (Year 1 records #2, fixed code, started 23:47 UTC 2026-11-17): live log works; it showed
  `to fetch: 96 Telegram records, 4610 MB; this run: 3000 MB, 120 min` and `y1-anat-66: downloading 210 MB`. The owner
  says download speed on Actions is slow. Read its log for the `KB/s` lines before changing anything.
  Run `44194530355` (#1, old code) was cancelled by the owner.
- Update data was started on the PC and cut off when the session restarted (log empty). It created:
  `cns-164` 'Blood supply of cerebrum' (Mosafer, post 1870, file downloaded, 3079 s), `cns-165` 'Blood supply of brain'
  (Mosafer, post 1871, file downloaded, 3260 s), `cns-166` '3rd ventricle' (Azouny, post 1877, NO file).
  `media.json` rows for cns-164/165 are pending upload (`upload_media.pending()`); do NOT upload them from the PC.
  `mother_lists.json` was NOT updated for these: do it by hand + `py mother_check.py` (must print "exact").
- `auto_doctors.py plan` (read only, 01:45 local) listed new year 2 lectures: Azouny CSF circulation (1864), Brain
  arterial supply 1/2 (1865, 1866); Zahran Spinal cord 1/2 (1869, 1876); Nageb Properties of reflex 2 (1872),
  Cerebral cortex 1/2/3 (1873-1875); plus 1870, 1871, 1877 seen by the real run. All audio, 13-54 MB each.
- Polls job: not restarted. polls.db integrity ok, 120 polls still need votes. Copy `polls/engine.log` before Start
  (Start opens it with "w"). Polls use Telegram: never at the same time as an Update data Telegram step.

## Done (second session, 2026-11-18)

- Baseline speed (run `44202314916`, old code, no WARP, no cryptg, one 512 KB request after another): a flat
  1180-1240 KB/s on every file (y1-anat-66 210 MB at 1200 KB/s, y1-anat-75 515 MB at 1241 KB/s), plus about 30 s
  per record with the link idle (compress, upload, hear copy ran before the next download started).
- Speed-up: `cryptg==0.5.0.post0` (the only release with a Linux wheel for Python 3.13; 0.6.x needs Rust),
  pieces of 1 MB (`machine.CHUNK`), `machine.parallel_stream` (4 blocks of 4 MB in flight, `--parallel`, input
  `parallel`), compress/upload/hear copy in a worker thread beside the next download (a stopped run still waits for
  them), the original deleted on the runner once uploaded, pip cache, WARP step (input `warp`, default true,
  `continue-on-error`). `spine.LOG_LOCK` guards the records log (rows appended by the download loop while the worker
  pushes it).
- Year 2 flow: `cloud/year2.py` (`todo`, `records`, `pull`), `cloud/records.py --year 2`, workflow "Records"
  (Year 2 30 min, then Year 1 90 min), `upload_media.waiting` skips `cloud` rows, `update_data.py` with
  `config.json` `"pc_transfers": false` and `"spine": {"records_cloud": true}` (step "year 2 records (GitHub)";
  `auto_doctors` with `big_mb=0` never downloads, also when a post's size is unknown). Tests:
  `tests/test_cloud_year2.py`.

## To do (in this order)

1. **Speed on the runner** (`.github/workflows/records.yml`, `cloud/requirements.txt`):
   - Add `cryptg` to `cloud/requirements.txt` (PC has 0.6.0). Without it Telethon decrypts in pure Python: likely the
     main reason for slow downloads.
   - Add a WARP step before the download (workflow_dispatch input `warp`, default true, `continue-on-error: true`):
     ```
     curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
     echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflare-client.list
     sudo apt-get update -qq && sudo apt-get install -y -qq cloudflare-warp
     warp-cli --accept-tos registration new && warp-cli --accept-tos mode warp && warp-cli --accept-tos connect
     for i in $(seq 1 20); do warp-cli --accept-tos status | grep -q Connected && break; sleep 2; done
     curl -s https://www.cloudflare.com/cdn-cgi/trace | grep warp=
     ```
   - Compare KB/s with and without (input `warp=false`) and report numbers.
2. **Year 2 flow** (design agreed in this session):
   - PC side, new `cloud/year2.py`:
     - `todo()`: every lecture (`lectures.all_lectures()`) whose `source.telegram` is a RecordsBatch58ATM post (no
       `/c/`), no `source.youtube`, no `source.cloud`, and either no `source.file` or its `media.json` row is pending
       upload (so cns-164/165 go to the runner too). Row: `{lecture, module, channel: "RecordsBatch58ATM", post,
       title, doctor, subject, size}`.
     - `pull()`: read the year 2 log (`state.pull_log("year2-cns")`); for each `uploaded` row write
       `source.cloud = {key, size, hear_key, duration_s}` and `duration_s` into `lecture.json`, and `media_merge` a row
       `{lecture, file: "", key: "lectures/year2-cns/<id>/recording.48k.m4a", field: "audioUrl", cloud: true,
       uploaded_size}`. No audio is downloaded.
     - `upload_media.pending()` / `run()` must skip rows with `cloud: true` (today `size_of("")` is None, so such a
       row would look pending). `site_lessons.py write` then serves the key.
   - Runner side, `cloud/records.py --year 2`: recs from `state.pull_year2_todo()` as record dicts
     (`id` = lecture id, `module` year2-cns, `channel` RecordsBatch58ATM, `post`, `source` telegram, `subject`,
     `doctor`, `list`, `size`), skip ids already `uploaded` in the year 2 log, then the same
     `machine._download_telegram(..., on_done=finish)` path. `machine.upload_key(rec)` =
     `lectures/year2-cns/<id>/recording.48k.m4a` = the site's key, so the site plays it. Hear copy to
     `ops/tumrah-data/hear/year2-cns/<id>.16k.ogg`. Push the year 2 log after each record (`state.push_log("year2-cns")`).
     Videos become 48k audio too (owner's compress-first rule; say so to the owner).
   - Workflow: rename to "Records"; step "Year 2" (`python -u -m cloud.records --year 2 --max-minutes 30`,
     `continue-on-error: true`) then step "Year 1" (`--year 1 --max-minutes 90`); job timeout 150. Same session secret.
     Unknown: whether the runner's Telegram account can see RecordsBatch58ATM. If not, each post prints
     "not read (...)": tell the owner the account must join the channel.
   - PC flow, `update_data.py` with a config switch `"pc_transfers": false` (add it; set `"spine": {"records_cloud":
     true}` too, see `spine/records/flow.py` `config().get("records_cloud")`):
     `auto_doctors.sync(q, dry, big_mb=0)` (lectures made, nothing downloaded; `finish_interrupted` also stops at 0),
     `waiting_telegram` reports "waits for the GitHub runner" instead of downloading, no `upload_media.start_background`,
     year 1 `flow.update(..., background=False)` (captions only), and a new step that runs `cloud.year2.pull()` then
     `state.push_year2_todo(year2.todo())` and pushes inputs.
   - Tests: `tests/test_cloud.py` and `tests/test_spine_records.py` (35 there now): todo selection (file pending
     upload, cloud done, youtube), pull writes lecture.json + media row, pending() skips cloud rows, runner year 2
     recs and skip of uploaded ids, update_data does not download when `pc_transfers` is false.
3. Run real `py update_data.py` (with transfers off), read every changed list message yourself
   (`py tg_lists.py text <id>`), update `mother_lists.json` by hand, `py mother_check.py` = exact, then the site import
   chain (CLAUDE.md "Questions per lesson"; memory always-push-site).
4. Restart polls (copy engine.log first) when no Telegram step is running.

## Other open owner decisions (from the audit)
- Seg: see `docs/handovers/HANDOVER_2026-11-18_SEG.md`.
- Year 2 mother maps: 6 lists changed since their maps (1630, 1631, 1632, 1635, 1637, 1638); Cocci 1634 has no map.
  `spine.records.machine.plan(2)` no longer crashes (year 2 tree uses `new` and a year-level channel).
- Mossafer "5- CSF test" form not in the bank; Azouny's 8 lecture PDFs have no output place; 3 whiteboard notes have no
  lesson number; `nagib_quiz.json` 79 rows unmatched to lessons.
- MSK `chapters.json` empty (option A from reference.json or B empty).

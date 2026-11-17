# Handover: year 1 records off the PC (GitHub Actions), 2026-11-17

## Prompt for the next session (copy and paste)

```
Read docs/handovers/HANDOVER_2026-11-17_CLOUD.md in tumrah-data and finish the GitHub Actions setup for the
year 1 records. Start with "Where it stands". Help me with the Telegram login and the secrets (I type the phone,
code and secrets myself), run the first workflow, check it, then set config.json "spine": {"records_cloud": true}.
Branch spine-rebuild; the GitHub repo is playpl/tumrah-data (main = spine-rebuild).
```

## Why

Owner, 2026-11-17: internet plan is limited and slow, and the PC is not always on. Chosen: GitHub Actions first
(Oracle free VM second; Claude cloud sessions last). Stage 1 = year 1 records (5.8 GB still on Telegram), the main
bandwidth cost. Stage 2 (later) = year 2 Telegram lists + site import on the runner.

## What exists (all committed on spine-rebuild)

- `.github/workflows/records.yml`: every 2 hours (cron `17 */2 * * *`) and by hand ("Run workflow", input
  `max_mb`, default 3000). `concurrency: telegram-records` (never two Telegram readers). Python 3.13, ffmpeg,
  `pip install -r cloud/requirements.txt` (telethon, boto3), then `python -m cloud.records --max-mb N`.
- `cloud/r2.py`: the site's private bucket (R2, S3 API) via boto3. Credentials from the environment (S3_BUCKET,
  S3_ENDPOINT, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_REGION); on the PC from the backend `.env`
  (`config.json` `backend_env`). Everything not for students lives under `ops/tumrah-data/`.
- `cloud/state.py`: `py -m cloud.state push | pull [--inputs]`. Inputs = the 61 small files `machine.plan(1)` reads
  that git does not hold (`sources/lists/ZAG59_*`, `sources/mother/ZAG59_*`, `sources/mother/fixes.json`), as
  `ops/tumrah-data/inputs/year1.tar.gz`. The records log `modules/year1-musculoskeletal/graph/records.jsonl` is
  shared as `ops/tumrah-data/records/year1-musculoskeletal.jsonl`; merge = union of rows in `at` order, so the PC
  and the runner never overwrite each other.
- `cloud/tg.py`: the runner's own Telegram session (`TG_API_ID`, `TG_API_HASH`, `TG_SESSION` as a StringSession).
  `py -m cloud.tg login` (on the PC, the owner types phone and code) writes
  `%USERPROFILE%\.tumrah-cloud\telegram.txt` with the three values. A separate session because one session used
  from two places at once can be killed by Telegram (AUTH_KEY_DUPLICATED).
- `cloud/records.py`: the runner job: pull inputs + log, download the next Telegram records (first lessons of every
  subject first) up to `--max-mb`, compress (AAC mono 48 kbps) and upload ONLY the compressed file
  (`lectures/year1-musculoskeletal/<id>/recording.48k.m4a`), make a 16 kbps Opus "hear copy" for the fleet
  (`ops/tumrah-data/hear/year1-musculoskeletal/<id>.16k.ogg`, log field `hear_key`), push the log.
  YouTube captions stay on the PC (YouTube often refuses datacenter addresses).
- PC side, active only when `config.json` has `"spine": {"records_cloud": true}` (NOT set yet):
  `spine/records/flow.update` (Update data) pulls the log, pushes the inputs, fetches YouTube captions only (no
  Telegram download); `records finish` pushes the log after transcription; `transcribe.audio_of` fetches the
  hear copy when the 48k file is not on the PC (about 7 MB per hour of lecture instead of the original).
- `upload_media.alive` works on Linux too. `machine._download_telegram` uses `cloud.tg.connect()` when
  `TG_SESSION` is set.
- `cloud/SETUP.md`: the owner's steps. `tests/test_cloud.py`.

Tested on the PC (2026-11-17): state push/pull against the bucket (61 inputs, 249 log rows); `py -m cloud.records
--max-mb 0` end to end with the PC session; `r2.send` upload, skip when the same size is there, delete. NOT tested:
the runner itself (needs the secrets).

## Where it stands

1. DONE: private repo `playpl/tumrah-data`, pushed (`git push -u origin spine-rebuild:main`). Note: local
   `spine-rebuild` now tracks `origin/main`; push later commits with `git push origin spine-rebuild:main` (the
   runner runs what is on `main`). Commits made after the push (this handover, the login prompt fix and later
   work) are NOT on GitHub yet.
2. NOT DONE: `py -m cloud.tg login`. First try failed: `PhoneNumberInvalidError` (the number was typed without the
   country code). The prompt now asks "Phone with country code, for example +201xxxxxxxxx". Egypt: drop the
   leading 0, add +20. Two-step verification asks for its password too. The owner types all of it.
3. NOT DONE: the 8 repo secrets (https://github.com/playpl/tumrah-data/settings/secrets/actions): TG_API_ID,
   TG_API_HASH, TG_SESSION (from telegram.txt, then delete the file), S3_BUCKET, S3_ENDPOINT, S3_ACCESS_KEY_ID,
   S3_SECRET_ACCESS_KEY, S3_REGION (from `C:\Users\Ahmed\Desktop\tumrah\backend\.env`). Claude never types or
   reads a secret value; the owner pastes them.
4. NOT DONE: first run: Actions > "Year 1 records" > Run workflow, max_mb 500. Expect the last line
   `left: N records, M MB still to download from Telegram`. Check with `py -m cloud.state pull` on the PC: new
   `uploaded` rows with `hear_key`.
5. NOT DONE: then set `config.json` `"spine": {"records_cloud": true}` (and commit + push), so Update data stops
   downloading year 1 on the PC. Before that, do NOT run the PC download and the runner at the same time on the
   same records (they would both download; the log merge keeps it consistent, but it wastes the plan).

## Watch for

- GitHub free minutes for a private repo (about 2,000 a month): an idle run is about a minute; every 2 hours is
  about 360 runs a month. If minutes run short, change the cron to every 6 hours.
- A Telegram warning about a new login from a new place is expected (the runner's session). If the runner prints
  "needs a new login", run `py -m cloud.tg login` again and replace `TG_SESSION`.
- Stage 2 ideas: year 2 `auto_doctors` download + `upload_media` on the runner (needs `lectures/` state in the
  bucket), and `site_import.py` on the runner (needs the tumrah backend checkout: a token secret with read access
  to `playpl/tumrah`, and Mongo `MONGODB_URI`).

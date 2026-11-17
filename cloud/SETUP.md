# Year 1 records on GitHub Actions: one-time setup (owner)

What it does: every 2 hours a GitHub machine downloads the next year 1 recordings from Telegram (up to 3 GB a run),
compresses them (AAC mono 48 kbps), uploads them to the site's private storage, and makes a small 16 kbps copy for
transcription. Your PC no longer downloads the originals (5.8 GB left). When the PC is on, Update data only syncs a
small log and fetches the 16 kbps copies (about 7 MB an hour of lecture) for the fleet to transcribe.

## 1. A private GitHub repository

1. Open https://github.com/new, name it `tumrah-data`, choose **Private**, add no README. Create.
2. In a terminal in this folder (first push asks you to sign in to GitHub in the browser):

```bash
git remote add origin https://github.com/<your GitHub name>/tumrah-data.git
```

```bash
git push -u origin spine-rebuild:main
```

Later pushes: `git push origin spine-rebuild:main`. Data folders (lectures, doctors, sources, bank, polls...) are
ignored by git and never leave the PC this way.

## 2. A Telegram session of its own for the runner

The runner must not use the PC's session (one session used from two places at once can be killed by Telegram).
Use the account that is a member of the four ZAG59 channels:

```bash
py -m cloud.tg login
```

Type the phone number and the code Telegram sends. It writes `%USERPROFILE%\.tumrah-cloud\telegram.txt`.

## 3. Secrets

GitHub repo > Settings > Secrets and variables > Actions > New repository secret, one per name:

- `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`: the three lines of `telegram.txt` (then delete that file).
- `S3_BUCKET`, `S3_ENDPOINT`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`: the same names in
  `C:\Users\Ahmed\Desktop\tumrah\backend\.env`.

## 4. First run

GitHub repo > Actions > "Year 1 records" > Run workflow (max_mb 500). It should end green with a line
`left: N records, M MB still to download from Telegram`. Then tell Claude: it sets `"spine": {"records_cloud": true}`
in `config.json`, and from then on Update data stops downloading year 1 on the PC.

Cost: free within GitHub's included minutes for a private repo (about 2,000 a month); an idle run takes about a minute.

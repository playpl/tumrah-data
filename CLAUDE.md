# Tumrah data

Adds all data to the website, linked through the handout. Design and plan live in the tumrah repo:
`docs/superpowers/specs/2026-11-06-data-workflow-design.md`, `docs/superpowers/plans/2026-11-06-data-workflow.md`.

Start here: `HANDOVER_2026-11-06.md`.

- Polls: double-click `Polls.bat`. Start and Stop are on the page. Results land in `polls/ready/`.
- Keys come only from Telegram's correct flag. Our own votes never count (`net()` in `polls/engine.py`).
- Claude never reads question text or Arabic: counts only.
- Tests: `py -m unittest discover tests`.

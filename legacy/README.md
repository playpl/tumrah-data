# legacy

Old fleet-era tools kept for reference (the master prompt: "rebuild, fix, delete legacy"; nothing is deleted).
Nothing imports them and no command runs them. Moved 2026-11-21:

- `fleet_pause.py`: froze the old dispatchers (`dm.py run`, `extra_dispatcher.py`) and their fleet workers.
- `fleet_watch.py`: half-hourly health count of running fleet jobs.
- `oob_transcribe.py`: ran jobs outside the old dispatcher.
- `extra_dispatcher.py`: a second fleet dispatcher for extra lanes (nothing imported it).

Still at the root and still wired to the retired fleet flows (refuse while `config.json` `fleet.down` is true, or
are not run): `dm.py run`, `dispatch.py`, `queue_db.py` (queue.db lanes place,
lecture_links, transcribe), `runners.py`. They are imported by `page.py`, `control.py` and `update_data.py`, so
they move only together with those callers.

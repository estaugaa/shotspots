# ShotSpots

Personal landscape / wildlife / night-sky planner for the Washougal, Columbia Gorge and Portland area.

* `app/` – the phone web app (installed from Safari, published at shotspots-eric.netlify.app)
* `pipeline/` – scheduled data jobs (GitHub Actions) that build `feed/`, which the app reads
* `config/` – spots, landmarks, gauges; `data/` – rolling histories and outing logs
* `inbox/frames/` – drop night photos here (GitHub web or mobile upload) to plate-solve them

Every number in the feed is labelled MEASURED, MODELED or ESTIMATED in `feed/status.json`.

**Where facts live.** `config/` is the source of truth for spot pins and core fields (`spots.json`), alignment
targets (`landmarks.json`) and seasonal road dates (`access_rules.json`). `app/data.js` holds the writing
(tips, alerts, sources) and gets those fields overlaid from `config/` on every publish. After editing `config/`,
run `python tools/sync_data.py` so the checked-in copy matches. The nightly check
(`tests/test_audit.py`) fails if the two drift, if a stored alignment no longer lines up, if a reference is
broken, or if text uses wording that goes stale ("this month") or cites a schedule whose date has passed.


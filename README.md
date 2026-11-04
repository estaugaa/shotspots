# ShotSpots

Personal landscape / wildlife / night-sky planner for the Washougal, Columbia Gorge and Portland area.

* `app/` – the phone web app (installed from Safari, published at shotspots-eric.netlify.app)
* `pipeline/` – scheduled data jobs (GitHub Actions) that build `feed/`, which the app reads
* `config/` – spots, landmarks, gauges; `data/` – rolling histories and outing logs
* `inbox/frames/` – drop night photos here (GitHub web or mobile upload) to plate-solve them

Every number in the feed is labelled MEASURED, MODELED or ESTIMATED in `feed/status.json`.

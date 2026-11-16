# ShotSpots

Free landscape / wildlife / night-sky planner: started around the Columbia Gorge, built to work anywhere in the US.
Live: https://estaugaa.github.io/shotspots/ . Working notes: CLAUDE.md and docs/.

* `app/` – the phone web app (installed from Safari, published on GitHub Pages)
* `pipeline/` – scheduled data jobs (GitHub Actions) that build `feed/`, which the app reads
* `config/` – spots, landmarks, gauges; `data/` – rolling histories and outing logs
* `inbox/frames/` – drop night photos here (GitHub web or mobile upload) to plate-solve them

Every number in the feed is labelled MEASURED, MODELED or ESTIMATED in `feed/status.json`.

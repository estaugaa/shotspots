# ShotSpots: working notes for Claude

Read this first, then docs/STATUS.md. Decisions and their reasons are in docs/DECISIONS.md, tests in docs/TESTING.md.
Keep all four short and current: update them in the same commit as the change they describe.

## What it is
A free photo-planning web app (landscape, wildlife, night sky) by Eric (GitHub estaugaa, Washougal WA).
Live at https://estaugaa.github.io/shotspots/ (GitHub Pages). It must work as well anywhere in the US as around the Gorge.

## Ground rules
- Free tools and data only. No paid APIs or plans.
- The repo is PUBLIC: never commit keys, tokens or personal details. Secrets go in GitHub secrets, which Eric adds himself.
- Do heavy work on GitHub Actions, not in the Claude session (minimise tokens).
- Accuracy over coverage: never state something the data doesn't support; label MEASURED / MODELED / ESTIMATED.
- Eric likes unique, not overdone shots, but famous spots must still rank high when they are the best option.
- Scoring is data driven, not coverage driven: no bonus for being hand-researched; the best spot by the data wins.
- Outside the Wildlife filter, lists lead with views, not birding/wildlife spots.
- Include links when recommending products.

## How it is built
- `app/`: plain classic scripts loaded with `defer`. Behaviour is extended by reassignable wrappers:
  `fitFor` (scoring), `openSpot`, `renderNow`, `render`. Load order is in `app/index.html`; a new script must also be
  listed in `SHELL` in `app/sw.js` (a test checks this).
- `pipeline/`: data jobs (`python -m pipeline <job>`), writing `feed/` (read by the app) and `data/` (state).
- Publishing: pushing a change under `app/` publishes automatically (`.github/workflows/app-publish.yml`); the
  service-worker version is a hash of the app files set at build time. No manual bump or dispatch needed.
  Data jobs publish at the end of their own workflow.
- Workflows share a "pipeline" concurrency queue that holds ONE waiting run: a newer queued run replaces an older one.
- `job.yml` runs one long job by name (`inputs.job`); a job that writes `.more` queues its own next run.
- `diag.yml` runs any script under `tools/` (`inputs.script`) on Actions with a browser; output goes to branch
  `diag-<script name>` (`diag-out` for diag.py).

## Scoring (v2, app/score2.js)
score = conditions (0-100, light/weather fit for what the spot is for) x quality (0.5-1.12 from measured fame, same for every
spot; landmarks x0.75) ; ranking then x (1 - 0.1 x share of the travel range used). Night and the Wildlife filter keep v1.
`localStorage ss2:scorev = "1"` switches back to v1 for comparison.

## Before saying something works
Check it: run the relevant tool (docs/TESTING.md) and read the output. Never report a key, job or feature as working
from memory.

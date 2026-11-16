# Status (update at the end of every work session)

## Running
- Deep research for 300 starter spots in 10 test regions (job.yml, job=deep), started 2026-11-16 ~11:00 PT. Next: publish
  the cards, re-run the 30 situations and scorecmp, compare the test regions, then widen REGIONS in pipeline/deepspots.py.
- Fog chance model in shadow mode (job.yml nightly 7:15 PM PT) until about 2026-12-07; then decide whether to show it.
- Nightly check (regress + expectations) 3:23 AM PT; smoke test every 30 min.

## Waiting on Eric
- Hidden gems review (list near Washougal): mark each gem / dud / unknown.
- Optional: an NPS_API_KEY secret (the NPS feed runs on DEMO_KEY).

## Next
- Widen deep research nationally once the test regions improve.
- Tune the v2 weights against outcomes (ratings from the app's outcome button, or daily sunset-photo counts).
- Finer sampling of the sun-path cloud check (model grid cells of 10-25 km cause neighbouring-spot differences).
- A "view shadows" link to ShadeMap on spot pages (confirm the link format first).

## Known weak spots
- Denver sunset: an old airport control tower ranks first.
- Displayed scores are lower under v2 (unknown spots show about half their light score).

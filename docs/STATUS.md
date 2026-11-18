# Status (update at the end of every work session)

## Running
- 2026-11-17 feed/ and data/ moved to the `data` branch (squashed daily). Phase A: jobs read/write the data branch; main keeps a
  frozen copy so runs that started on the old workflows can't break anything. Phase B: delete feed/ and data/ from main
  (git rm -r --cached feed data; add /feed and /data to .gitignore) once every data job has run once on the new workflows.
- 2026-11-17 Long-term archives (data/archive/, kept indefinitely) replace the 30-120 day history files; each writer moves its old file in on
  its first run. Prediction log nightly (tools/scoretest.py --live); evaluate with diag.yml tools/predeval.py once a few weeks have accrued.
- App publishing is gated: every publish takes app/ from `app-verified`, which only moves when app-publish's checks pass (or scoretest update on main).
- National research (job.yml job=deepnat): terrain/facing for the top 15 spots in each of 1,038 tiles, ~8 min a tile, self-chaining (several days). Walking routes added separately (job=deeproutes, daily 2:40 AM PT, chains). Progress: feed/status/deepnat.json.
- Forecast check (job=skill) daily 12:20 PM PT; feed/calib.json fills over the first week (needs ~200 pairs per region and model before anything is applied).
- Deep research done for 300 starter spots in 10 test regions (terrain horizons, sun times, cards); walking routes fill in
  over the next trails runs (242 left). Next: widen REGIONS in pipeline/deepspots.py nationally.
- Fog chance model in shadow mode (job.yml nightly 7:15 PM PT) until about 2026-12-07; then decide whether to show it.
- Nightly check (regress + expectations) 3:23 AM PT; smoke test every 30 min.

## Waiting on Eric
- Hidden gems review (list near Washougal): mark each gem / dud / unknown.
- Optional: an NPS_API_KEY secret (the NPS feed runs on DEMO_KEY).

## Next
- Check nowcast against outing logs (verify_outcomes) as more come in; Eric's first log (Nov 16, Steamboat Landing): partly cloudy, no colour; forecast said 97% low cloud, KPDX said few low/broken mid.
- Spot research (weekly Sunday 1:23 AM scheduled task) still uses the old Netlify app address in its prompt; harmless but update when convenient.
- Widen deep research nationally once the test regions improve.
- Tune the v2 weights against outcomes (ratings from the app's outcome button, or daily sunset-photo counts); tools/predeval.py is the start (predictions vs webcam and airport truth).
- Finer sampling of the sun-path cloud check (model grid cells of 10-25 km cause neighbouring-spot differences).
- A "view shadows" link to ShadeMap on spot pages (confirm the link format first).

## Known weak spots
- Hood River sunrise: Bonneville Fish Hatchery leads (salmon season event); Cannon Beach: Haystack Rock outside the top 4.
- Denver sunset: an old airport control tower ranks first.
- Displayed scores are lower under v2 (unknown spots show about half their light score).

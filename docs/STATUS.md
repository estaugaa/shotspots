# Status (update at the end of every work session)

## Running
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
- Tune the v2 weights against outcomes (ratings from the app's outcome button, or daily sunset-photo counts).
- Finer sampling of the sun-path cloud check (model grid cells of 10-25 km cause neighbouring-spot differences).
- A "view shadows" link to ShadeMap on spot pages (confirm the link format first).

## Known weak spots
- Hood River sunrise: Bonneville Fish Hatchery leads (salmon season event); Cannon Beach: Haystack Rock outside the top 4.
- Denver sunset: an old airport control tower ranks first.
- Displayed scores are lower under v2 (unknown spots show about half their light score).

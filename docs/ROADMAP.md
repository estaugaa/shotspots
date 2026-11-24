# Roadmap (plan of Nov 23, 2026)

Goal: the best photo spot near you at any moment, forecast as accurately as the data allows, with the area's unique
moments (fog, rainbows, alignments, bird gatherings, aurora, fresh snow...) found and graded automatically.
Rules: free data only; each change is applied by an automatic held-out test, not by review; Eric reads one weekly report.

How to use this file: claim an item before starting (status `doing`, your branch), update it in the same commit as the
work, and mark it `done` only with the measured result. One item per session; items touching the same files wait.
Status: `todo`, `doing (<branch>)`, `done (<date>: <result>)`, `dropped (<reason>)`.

## Phase 0: hygiene
- 0.1 Alert settings KeyError 'aurora_kp' (swallowed each run). done (Nov 23: a key missing from an older form keeps its default)
- 0.2 Forecast check: airport 'M' values logged as errors. done (Nov 23: cover without a height skipped quietly, as before)
- 0.3 App: 26 empty catches -> noteErr() (CLAUDE.md rule). done (Nov 23: 12 that guard work now noteErr; storage/vibrate ones stay silent on purpose; scoring test 6/6)
- 0.4 Smoke test: find the HTTP 429 source (WebKit). doing (Nov 23: smoke.py now logs failed URLs; read diag-smoke next run)
- 0.5 Nightly expectation 'Acadia sunrise: Cadillac near the top' failed Nov 23: weather or regression? done (Nov 23: weather. Nov 24
  sunrise overcast: 'flat light' gives surf beaches 30, summits 16; the failing run predates the 1.1 change. Also: the
  name match hit the eBird hotspot 'Acadia NP: Cadillac Mountain' (rank 16), not the summit (rank 19); see 1.1 issues)
- 0.6 Remove dead Flickr paths (photos, originality: no key exists). deferred (low value: both jobs skip in under a second; touches 5 files)

## Phase 1: national coverage (fixes most ties)
- 1.1 Spot quality for all 75k spots from the Commons dump: distinct photographers within ~350 m, golden-hour share
  (learned light), busiest months; replaces photostats' API crawl and seedpop's Commons part. Metric: share of spots with
  measured quality (19% now); scoring test top 3 sane. done by another session (Nov 23, 0816f544: feed/spotphotos.json,
  22,830 spots published, app/phototime.js). Open issues (Nov 23 check, Cadillac summit): (a) one 12% golden-hour baseline
  for sunrise and sunset, though sunrise shooting is rarer everywhere (Commons: Cadillac 18% of photo days at sunrise vs
  ~5% typical, yet penalised for 1 of 14); (b) 'lift-adjusted' quality compares a spot with its area, so the most famous
  spot inside a famous park reads ordinary (Cadillac summit x0.87). Fix: per-event baselines with a binomial test (only
  act when the evidence is clear), and quality on absolute photographers with area lift as a tie-breaker.
  Found Nov 23, fixed: tz_for() defaulted every state outside 10 western ones to Pacific time, so camera times east of
  the Rockies were read 1-3 h off (spots with 10+ photographers: median sunrise share 2%, sunset 24%). Now the nearest
  airport station's zone (all states, split states correct), fallback table for 51; spotphotos publishes per-event
  baselines and runs daily (job_daily, ~30 s). Next: after the Nov 24 rebuild, re-record the scoring-test data, then
  switch phototime.js to the per-event baseline with shrinkage (tested Nov 23 on the old data: changes small, but the
  old data can't judge it). Lift: an 'urban only' rule (300-1,000 photographers within 5 km) put Crystal Springs
  Rhododendron Garden first at sunrise and sunset, so it was not shipped; to be fitted on data (5.1). todo
- 1.2 Curate spots by data (non-photo places out; birding hotspots to the Wildlife filter only). done Nov 23 (claude/gifted-sanderson-3f3abb):
  of 75,346 starter spots, 19 control towers and 13 park-ride towers dropped, 785 lose fame borrowed from another Wikidata item
  (job=seedclean, monthly); Denver sunset top 8 all views on the same forecast (was a ride tower #1). Birding hotspots unchanged
  (they already score x0.55 outside Wildlife).
- 1.3 National layers: GOES grid for the lower 48, airport reports nationwide, fog model trained per region, eBird
  notable + counts in tiles (needs an EBIRD_KEY secret, Eric). todo
- 1.4 Alerts per area for every user, not per home. todo
- 1.5 Terrain horizons for every spot with photo evidence; light.json split into tiles loaded on demand. todo

## Phase 2: forecast accuracy
- 2.1 Ensemble cloud forecasts: chance of a gap toward the sun and of colour; confidence by lead time. todo
- 2.2 Lead-time grading: nightly day-ahead forecasts at camera and airport points, graded; best model per region/lead. todo
- 2.3 0-3 h satellite nowcast nationwide incl. cloud-top height (cirrus vs low deck). todo
- 2.4 Fog model out of shadow wherever it beats climatology (PNW now: Brier 0.116 vs 0.152). todo

## Phase 3: one data-fitted scoring model
- 3.1 Unified feature model (cloud by level, sun gap, rain/clearing, sun breaks, fog vs height, snow, wind; spot facts as
  inputs), fitted on sun-facing ridge cams + road cams + rated sky photos, held out by day/region; shadow, then switch. todo
- 3.2 Event models with their own truth: rainbows (Commons 'rainbow' photos), fog (airports), fresh snow (SNODAS),
  aurora (OVATION), wildlife gatherings (eBird counts vs normal). todo
- 3.3 Night and Wildlife scoring onto measured truth (v1 today). todo

## Phase 4: moments engine + Moments view
- 4.1 Daily per-tile list of the week's moments with chance, confidence and the source that grades it: alignments behind
  peaks/landmarks, above-the-fog sunrises, bird gatherings, rainbow windows, aurora, meteor showers / Milky Way, fresh
  snow then clearing, fall colour and wildflower peaks. todo
- 4.2 'Moments near you' 7-day timeline in the app; push alerts by area. todo

## Phase 5: self-improvement loop
- 5.1 Weekly tuner: refit weights on rolling truth, held-out test, publish as a data file only if better on 2+ sources
  with the scoring test and expectations passing; changelog line; automatic rollback. todo
- 5.2 Calibration on/off per region and model, extended to mid/high cloud and ensembles. todo
- 5.3 Staleness monitor: re-run or flag jobs whose status is older than expected. todo
- 5.4 Weekly one-page report (accuracy by source, changes, rollbacks): Eric's only review. todo

## Phase 6: UI
- 6.1 Confidence label per pick (lead time, ensemble spread, data depth). todo
- 6.2 Scores calibrated so 80+ means what it says (v2 reads low). todo
- 6.3 Conditions and moments on the map. todo
- 6.4 No API keys for users anywhere. todo

## Baseline (Nov 23) to measure against
Formula vs colour: webcams 0.12, rated sky photos 0.09. Spots with measured quality ~19%. Fog (old check) hit 0.09,
false alarms 0.75. Nightly expectations 14/15. Return-visit picks 1.8-2.2 s (phone profile).

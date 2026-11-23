# Roadmap (plan of Nov 23, 2026)

Goal: the best photo spot near you at any moment, forecast as accurately as the data allows, with the area's unique
moments (fog, rainbows, alignments, bird gatherings, aurora, fresh snow...) found and graded automatically.
Rules: free data only; each change is applied by an automatic held-out test, not by review; Eric reads one weekly report.

How to use this file: claim an item before starting (status `doing`, your branch), update it in the same commit as the
work, and mark it `done` only with the measured result. One item per session; items touching the same files wait.
Status: `todo`, `doing (<branch>)`, `done (<date>: <result>)`, `dropped (<reason>)`.

## Phase 0: hygiene
- 0.1 Alert settings KeyError 'aurora_kp' (swallowed each run). doing (main, Nov 23 session)
- 0.2 Forecast check: airport 'M' values logged as errors. todo
- 0.3 App: 26 empty catches -> noteErr() (CLAUDE.md rule). todo
- 0.4 Smoke test: find the HTTP 429 source (WebKit). todo
- 0.5 Nightly expectation 'Acadia sunrise: Cadillac near the top' failed Nov 23: weather or regression? todo
- 0.6 Remove dead Flickr paths (photos, originality: no key exists). todo

## Phase 1: national coverage (fixes most ties)
- 1.1 Spot quality for all 75k spots from the Commons dump: distinct photographers within ~350 m, golden-hour share
  (learned light), busiest months; replaces photostats' API crawl and seedpop's Commons part. Metric: share of spots with
  measured quality (19% now); scoring test top 3 sane. doing (Nov 23 session)
- 1.2 Curate spots by data (non-photo places out; birding hotspots to the Wildlife filter only). doing (claude/gifted-sanderson-3f3abb)
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

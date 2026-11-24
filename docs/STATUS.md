# Status (update at the end of every work session)

## Running
- 2026-11-23 Starter clean (job.yml job=seedclean; scheduler, every 30 days): drops control towers and amusement-park ride towers from the live tiles and removes fame borrowed from another Wikidata item (measured: 19 + 13 dropped, 785 lose fame). First run after merge; check data/seedclean.json, then the Denver and Hood River expectations. (Nov 16 weak spots: Denver's Stapleton tower; Hood River's hatchery had already left the top 20 under v2.)
- 2026-11-23 Spot photographers (job.yml job=spotphotos, ~20 min, rerun when a new Commons dump is extracted): feed/spotphotos.json drives spot quality and the photo-timing layer.
- 2026-11-20 Commons photo history (job.yml job=commonsphotos; scheduler, every 30 days, chains itself): streams the Commons dumps and writes data/archive/commons/photos_<dump>.csv.gz (US photos: place, capture time, EV, name words) for the validation set. Done Nov 20: 3.08 M photos.
- 2026-11-20 Photo history vs weather (job.yml job=photoweather; scheduler daily): first run re-extracts the photos with uploader numbers (~90 min), then fetches ERA5 weather for ~35 of the busiest cells a day and writes feed/photoweather.json (sky formula vs share of photographers out at sunrise/sunset). Read it after a few days, then decide weight changes.
- 2026-11-20 Image rating (job.yml job=imagerate; scheduler daily 13 UTC): CLIP + LAION aesthetic scores for ~3,000 golden-hour Commons photos a day and the webcam thumbnails -> feed/imagerate.json. Needs the v3 photo file (page ids), which the Nov 21 photo-weather run extracts; first real ratings Nov 21. First run Nov 21 OK (2,999 rated). Nov 21: sky photos only; check whether formula vs vivid rises above the 0.05 of all photos. Nov 23: webcam set grown (ALERTCalifornia sun-facing ridge cameras, numbers only; every road frame thumbnailed and rated). Check camtruth.json sun_facing and imagerate.json webcams.spearman_formula_vivid after ~a week, then fit the cloud-canvas curve on photos + webcams (held-out days).
- 2026-11-23 National sunrise/sunset sky climatology done (job.yml job=climonat): 2,478 airport stations in 51 states/territories, 10 years of IEM reports; now re-checks station lists weekly (scheduler). Output feed/climo/ (1° tiles + index.json). Spot pages show "Clear at sunset this time of year" (MEASURED) wherever a station is within 80 km; the shot list and alignment alerts use it at sunrise/sunset.
- 2026-11-24 Seasonal planner live on the spot page (app/season.js): 52-week strip of clear sky at sunrise and sunset from the nearest airport (80 km, 10 years, ±1 week pooled, weeks under 20 days blank), 3 clearest weeks outlined, fog row (shaded by share of foggy mornings, 25%+ outlined) for waterfalls and above-the-fog viewpoints. MEASURED; not a scoring layer. Check: season-check.yml on branch pushes (or diag.yml tools/seasonprobe.py) -> branch diag-seasonprobe.
- 2026-11-18 feed/ and data/ live only on the `data` branch (squashed daily; first squash 00:43 UTC). main is code and docs.
  Local copies of feed/ and data/ from before the move are stale; see README for viewing the data branch.
- 2026-11-17 Long-term archives (data/archive/, kept indefinitely) replace the 30-120 day history files; each writer moves its old file in on
  its first run. Prediction log nightly (tools/scoretest.py --live), plus the sky model at ~540 webcams from 2026-11-24 (predcams).
  Evaluate with diag.yml tools/predeval.py; first low-cloud weight fit once ~2 weeks of webcam points have accrued.
- 2026-11-17 Cards show data depth (4 dots: terrain, facing, photo record, routed drive) and the spot page says what is measured vs estimated; fog/low-cloud reasons carry the measured day-ahead record (app/depth.js).
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
- Fog: rule changed Nov 19 (visibility only, scored up to 18 h ahead). Re-run tools/fogrule.py in ~2 weeks: the evening snapshot (data/fc_archive_eve.json) then shows how fog does ~12 h ahead, which decides FOG_LEAD_H. Low-cloud calibration turns itself on when the forecast check shows skill (~Nov 24); fog model out of shadow (~Dec 7).
- Check nowcast against outing logs (verify_outcomes) as more come in; Eric's first log (Nov 16, Steamboat Landing): partly cloudy, no colour; forecast said 97% low cloud, KPDX said few low/broken mid.
- Spot research (weekly Sunday 1:23 AM scheduled task) still uses the old Netlify app address in its prompt; harmless but update when convenient.
- Widen deep research nationally once the test regions improve.
- Webcam truth: colour measure v2 from Nov 21 (v1 was fooled by signs and lights); first fair review Nov 25.
- Tune the v2 weights against outcomes (ratings from the app's outcome button, or daily sunset-photo counts); tools/predeval.py is the start (predictions vs webcam and airport truth).
  Nov 24 check: not enough yet, weights unchanged. Webcams (colour measure v2): 1,370 frames from 579 cameras but only 7
  sunrise/sunset events (Nov 21 sunrise to Nov 24 sunset). Frames on one evening share the weather, so they count as one
  test, not hundreds. The in-sample best (canvasFloor 0.6, lowBroken 0.5, lowDeck 0.4) is Spearman 0.13 vs 0.118 for the
  defaults, too small a gain to judge on 7 events. Sun-facing ridge frames: 0, because the camera inventory is rebuilt
  every 7 days (last built Nov 17, before ridge cameras were added); the ALERTCalifornia cameras join at the Nov 24 ~21 UTC
  rebuild, so check camtruth.json sun_facing.n > 0 on Nov 25. Photo history (photoweather.json, 9,724 cell-days): Spearman
  0.005, best 0.013, so the share of photographers out doesn't track sky colour; it is not a target for this fit.
  Image ratings: webcam formula vs vivid 0.081 on 217 frames. Prediction log: 7 days.
  Ready about Dec 8: 30+ v2 events and 300+ sun-facing frames. Fit canvasFloor, lowBroken, lowDeck (camtruth's grid) on
  the events up to a cutoff date and test on the 10+ later events; webcam sky_warm is the main target, with CLIP vivid on
  sun-facing frames as a cross-check. Change the weights only if the held-out Spearman beats the defaults by more than a
  bootstrap over whole events (90%), then judge the ranking change with tools/scorecmp.py on the same forecast.
- Finer sampling of the sun-path cloud check (model grid cells of 10-25 km cause neighbouring-spot differences).
- A "view shadows" link to ShadeMap on spot pages (confirm the link format first).

## Known weak spots
- Cannon Beach: Haystack Rock outside the top 4.
- Starter tiles keep orphan entries for dropped spots in feed/seedpop, feed/deep (harmless: keyed by id).
- Displayed scores are lower under v2 (unknown spots show about half their light score).

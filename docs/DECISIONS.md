# Decisions (newest first)

One line each: what was decided, and why. Add a line when a choice is made; edit a line when it is reversed.

- 2026-11-17 Data jobs install exact versions from requirements.lock (an upstream release can't break a scheduled run); tests.yml also tests the newest allowed versions and publishes their freeze to branch diag-freeze for upgrading.
- 2026-11-17 Recovered errors are counted, not silent: pipeline soft_fail() -> "soft" in feed/status/<module>.json; app noteErr() -> problem reports. Links from data go through safeUrl() (no javascript:/data: links).
- 2026-11-17 Forms rate limit fixed: the 60-per-hour check compared ISO times with SQLite's space format and was really ~60 per UTC day.
- 2026-11-17 Scoring test on frozen data (tools/scoretest.py) blocks publishing when a ranking changes: the live checks only ran nightly on changing weather, so a regression was seen after it shipped. Fixtures are recorded from the live site and replayed against the working copy's app code.
- 2026-11-17 Daytime windows scaled by sun height (below 12° 0.95, 12-25° 0.82, 25-40° 0.72, above 40° 0.62) instead of clock time: winter afternoons have low raking light all day.
- 2026-11-17 Webcam truth (pipeline/camtruth.py, after every satellite run): public road cameras (Oregon, California) photographed at every sunrise/sunset; real sky/land colour vs the sky formula with the forecast of the moment; Spearman and a weight search in feed/camtruth.json. Hundreds of checks a day instead of waiting for outing logs.
- 2026-11-17 Clear golden hours credit warm light on the land (64) and alpenglow (+8): a clear evening was scoring 23-32 because only cloud colour counted. Broken low cloud x0.85 (was 0.7), solid deck x0.4 (was 0.3). All weights in TUNE; #tune opens a testing panel. To be checked against webcam truth.
- 2026-11-17 Every scoring adjustment applies to every spot by what it is (kindOf: map kind, or categories for hand-researched spots); the +3 hand-research bonus is gone. (Eric)
- 2026-11-17 Daily jobs are started by tools/scheduler.py after every GOES run (~30 min), not GitHub cron alone: cron dropped the nightly check and ran job.yml's schedules hours late.
- 2026-11-17 Outside the Wildlife filter wildlife-led spots get x0.85 overall (their sunset sky still counts).
- 2026-11-17 Speed: wildlife-layer facts once per spot per redraw, nearest forecast point memoised (full redraw 7.7 s -> 2.1 s). Forecast requests race Open-Meteo against the forwarder after 2 s. Header no longer wraps while loading.
- 2026-11-17 Forecast check stores its own day-ahead forecasts (Open-Meteo's previous-runs archive has no low/mid cloud); first comparisons Nov 18.
- 2026-11-17 Forecast check (pipeline/skill.py, daily 12:20 PM PT): day-ahead forecast low cloud vs airport reports at every US sunrise/sunset; calibration applied only where a held-out test shows it lowers the error. HRRR replaces the default forecast for the next 18 h only where it measured more accurate. Data decides, not my judgment.
- 2026-11-17 Unknown is not bad: a spot with no photo/Wikipedia record gets the median quality of recorded spots nearby. Settings has "Lesser-known" (fame lowers the score instead).
- 2026-11-17 Mapillary not used for quality: its image counts measure dashcam road coverage, not how photogenic a spot is.
- 2026-11-17 National research (pipeline/deepnat.py): top 15 starter spots per 1-degree tile, most-photographed tiles first, cards in feed/deep/<tile>.json; the app computes terrain sun times from the stored horizon profile (app/terrainsun.js).
- 2026-11-17 Forecast forwarder keeps a 6-hour copy and serves it when Open-Meteo refuses or fails.
- 2026-11-17 Late data (airport reports, HRRR, calibration) applies on the next redraw rather than forcing one, so the list doesn't shift while loading.
- 2026-11-16 Nowcast: for windows in the next 3 hours, nearby airport cloud reports replace the forecast's low/mid cloud (full weight now, 30% at +3 h). The forecast said 100% overcast at Washougal while airports and Eric saw partly cloudy.
- 2026-11-16 Spot quality outside Wildlife counts photos only (Commons, Flickr); iNaturalist sightings measure naturalist activity, not views.
- 2026-11-16 Scoring is data driven, not coverage driven: hand-researched spots get quality from the same measures as every spot (photo and sighting counts, Wikipedia, photographer stands), not a fixed bonus. Outside Wildlife, any spot that is mainly about animals competes on its view. (Eric)
- 2026-11-16 Starter-spot horizons use the highest ground within 30 m and ignore terrain closer than 40 m: rough pins below a rim saw a false 25-degree wall.

- 2026-11-16 Organise context as these docs in the repo, not raw chat logs: the repo is public and logs are noisy; work in one chat per workstream.
- 2026-11-16 Pass/fail expectations (tools/expect.py) run nightly; add a case for every fixed bug.
- 2026-11-16 App publishes on push; service-worker version comes from a hash of the app files (a forgotten manual bump once left phones on old code).
- 2026-11-16 "Deep" research for the best starter spots (pipeline/deepspots.py): terrain horizon, sun times, walk and a generated tip, the same as hand spots get. Started with 10 test regions, 30 spots each.
- 2026-11-16 ShadeMap not embedded: its free tier only works on localhost; a custom domain needs the paid plan. Terrain sun times from our own horizons cover the landscape use.
- 2026-11-16 Distance inside the chosen travel range is only a tie-breaker (max -10%): the user already chose the range.
- 2026-11-16 Scoring v2: conditions x spot quality instead of adding fame points. v1 needed ever more special cases (fame doubled, landmarks capped, coasts floored).
- 2026-11-16 In flat light, big views floor at 25 and coasts at 30: moody light still makes photos; landmarks no longer get a fixed 40 regardless of sky.
- 2026-11-15 Fame from Wikipedia page views (pipeline/wikiviews.py): free and keyless. Turned out weak for most places; kept as one input.
- 2026-11-15 Curated list of classic US photo locations (pipeline/icons.py) resolved to Wikipedia coordinates; unresolved names are logged, never guessed. A first automatic Wikidata version produced junk and was dropped.
- 2026-11 Flickr is not a source: no free API keys are issued any more.
- 2026-11 Fog chance model in shadow mode for 3 weeks before showing it (backtest AUC 0.83 vs 0.58 for the rule).
- 2026-11 Forecast confidence from four weather models (rank correlation 0.73 between model spread and error); shipped.

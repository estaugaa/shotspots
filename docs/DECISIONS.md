# Decisions (newest first)

One line each: what was decided, and why. Add a line when a choice is made; edit a line when it is reversed.

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

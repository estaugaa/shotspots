# Nightly spot research playbook

This is the procedure the nightly scheduled task follows. It is the same method used to build the original
Gorge spots: real sources, verified pins, specific local notes. Quality over quantity.

## 0. Setup
1. `add_repo` estaugaa/shotspots with push access, clone it, `cd` into it.
2. Pull research requests and limits from the app:
   - If the Netlify connector is available: read form submissions for site `a54b42ef-afe7-4c95-922e-7d174dff4e98`
     (forms `research` and `research_settings`), save the list as JSON to `/tmp/subs.json`, then run
     `python3 -m pipeline research_import /tmp/subs.json`.
   - Otherwise skip; the GitHub Actions job syncs them every 3 hours.
3. Run `python3 -m pipeline research_plan` and read its JSON: `settings` (the nightly limits), `targets`
   (what to research tonight, with the spots already known there) and `schema`.
4. If `targets` is empty or settings say paused, stop.

## 1. Limits (hard)
- Stop adding spots at `max_new_spots_per_night`.
- Count every web search and page fetch; stop at `max_web_searches_per_night`.
- Stop working at `max_minutes_per_night`. Record searches and minutes in the output file.

## 2. Find candidates for each target (radius around lat/lon; `focus` if given)
Use several independent routes, like the Gorge build did:
- Photo-location sites: PhotoHound, Locationscout, PIXEO; local photography guides and blogs.
- Official pages: national/state/provincial parks, forest service, land trusts, city parks.
- Map search: TomTom area/POI search for viewpoints, waterfalls, peaks, lakes, beaches, parks, historic sites.
- eBird hotspots and well-known wildlife viewing areas for birds/wildlife.
- Night sky: dark-sky places, high roadside viewpoints away from towns.
Skip anything already in `known_spots` (same place within ~250 m, or same name).
Prefer variety (not eight waterfalls) and places a photographer would actually go.

## 3. Verify every spot before writing it
- Pin: confirm coordinates with TomTom (named POI or trailhead) or an official page. The pin is where you
  stand to shoot (the viewpoint, the falls, the parking for roadside spots). Put trailhead parking in `park`.
- Facts: season, access, permits, closures and hazards from a source you read tonight.
- Mark `confidence`: high (pin from an official/POI source and facts confirmed), medium (pin from a photo
  site or guide), low (not sure; low-confidence spots are rejected, so don't bother writing them).

## 4. Write the notes like a pro, not a brochure
- `tip`: 2–4 sentences: what the shot is, when the light works (sunrise/sunset/overcast/night and why),
  what makes it different, and one practical detail.
- `lens`: for a Fujifilm X-T5 with 16–50 mm, 27 mm and 70–300 mm.
- `months`, `effort` (road/short/hike/hard), `light`, `cats` from the schema list, `region` like
  "Banff · Bow Valley".
- `sources`: every page you relied on, as [title, url].
- Big landmarks visible from several spots (prominent peaks, towers, bridges) can go in `landmarks`
  with elevation in metres, so the alignment planner can use them.

## 5. Save and publish
1. Write `/tmp/research_<YYYY-MM-DD>.json` in the schema's file format. Use the target's `cell` (frontier) or
   `label` (request) as `target`, and include `sub` for requests.
2. `python3 -m pipeline research_add /tmp/research_<date>.json` and read which spots were added or rejected.
3. Commit `data/research` and `feed` with a message like
   "research: <target>: N new spots" and push (pull --rebase first).
4. Trigger the daily job so the new spots get terrain, light and conditions, which then publishes to the app:
   `curl -sS -X POST -H "Accept: application/vnd.github+json" -H "Content-Type: application/json" https://api.github.com/repos/estaugaa/shotspots/actions/workflows/daily.yml/dispatches -d '{"ref":"main"}'`
5. Finish with a short summary: targets, spots added, rejected and why, searches and minutes used.

The research step does not message Eric. The app shows the results under Spots › Explore new areas.

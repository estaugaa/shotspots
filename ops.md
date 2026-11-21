# ShotSpots ops report, 2026-11-21 ~14:40 UTC

**Verdict: needs attention.** Data is fresh and the publish gate is clear, but the nightly check failed, GOES publishes failed 3 times overnight, and the GOES cadence slipped again.

## Problems (newest first)
1. **GOES cadence slipped.** goes.json `at` 13:37:51Z (about 1 h old at 14:33Z). Latest goes.yml run is 585 (13:37Z, success); no 14:07Z run exists in the runs list. The Cloudflare cron skipped a dispatch (cause not checkable here). Same pattern as the 11-20 report. Impact: live fog nowcast up to ~1 h behind. Next: check the cron dispatcher.
2. **Nightly check (regress.yml) run 53 failed** (11:40Z), step "Expectations (pass/fail on real situations)". Impact: a real-situation expectation (ranking) is failing; users may see a bad pick. Not diagnosed: logs need sign-in and no diag output for it. Next: Eric/Claude read the expectations output; no scoring change made by me.
3. **GOES publish failures:** runs 576 (07:37Z), 579 (09:37Z), 580 (10:07Z) failed at step "publish / publish :: Run actions/deploy-pages@v5" (API step detail). Later runs 581 to 585 succeeded, so likely transient GitHub Pages errors. Impact: those fog updates reached the data branch but not the live site until the next success. Also run 553 (11-20 17:37Z) failed.
4. **snow.json ok:false**, "HTTPError: HTTP 503" at 11:21:20Z. Impact: snow data stale until the next daily run. Next: confirm tomorrow; no action.
5. **Recovered errors (soft):**
   - alerts.json (13:38:40Z) and weekend.json (12:14:57Z): "alerts: alert settings: non-numeric value", n=1 each, first `KeyError: 'aurora_kp'` (a missing settings key; unchanged since 11-19).
   - commonsphotos.json and photoweather.json: "commonsphotos: dump status", n=1, first `HTTPError: 404 ... commonswiki/20261101/dumpstatus.json` (the November dump is not published yet; new).
   - skill.json carries no soft field this time; the earlier 'M' problem is not present in this file. Run "job: skill" 126 (11-20 20:11Z) failed; no failed step name returned, and skill.json at 01:57Z is ok.
6. **job: deeproutes run 140 cancelled** (10:10Z); 142 success, 144 in progress (13:33Z). Probably replaced in the queue (queue groups not read).

## Fine
- Freshness: manifest gen 14:07:51Z. light 11:14Z, flow 11:14Z, sentinel 11:19Z, access 11:20Z, nps 11:20Z, verify_obs 11:14Z, skill 01:57Z (within 26 h), fogprob 11:04Z, climonat 06:41Z ("up to date"), deeproutes 13:33Z. All ok:true except snow.
- Data branch: datasquash.json 09:39:38Z ok ("8167 files"); origin/data has 23 commits, all from 09:39Z onward.
- Publish gate: `git diff origin/app-verified origin/main -- app` is empty (app-verified 917a83c); nothing unchecked.
- diag-tests (02:34Z 11-21): 19 passed. diag-scoretest (11-20 21:45Z): "expected.json updated (6 cases)" (a scoretest update commit on main, not by me). diag-smoke (11-20 17:15Z) is stale; its chromium errors list HTTP 429 (Too Many Requests) resource loads, from an old run. Recent smoke.yml runs 615 to 628 all success.
- Not checked: weekly, monthly, seed, trails.yml latest runs (only the 60 newest runs read; trails.json 11-20 21:40Z ok). Workflow HTML pages return 403. Live site not fetched; data branch used.

## Fix branches
None pushed (no clear one-line mechanical cause).

## Forecast check
feed/verify_obs.json gen 11:14:00Z, method: 2 ("forecast made 1 day ahead"; window "airport reports within 45 min of sunrise or sunset, last 30 days").
- Fog: hit rate 0.08 (10 hits, 110 misses), false-alarm ratio 0.74 (29 false alarms), n=1063. 11-20 report: 0.10 / 0.73, n=954.
- Low cloud: n=979, hit 273, miss 284, false alarms 118 (hit rate 0.49, false-alarm ratio 0.30, computed from those counts). 11-20 report: 0.53 / 0.31, n=877.
- low_cloud_bias_pct -13.6 (n_bias 979). 11-20 report: -9.7.

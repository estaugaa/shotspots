# ShotSpots ops report, 2026-11-28 ~14:40 UTC

**Verdict: needs attention.** Data is fresh and the app is current, but the Pages deploy step failed again (3rd day running) and the Nightly check failed again at "Expectations".

## Problems (newest first)
1. **Publish deploy fails intermittently (unfixed, 3rd day).** In the 100 newest runs (02:10Z to 14:07Z): "GOES fog now" failed 5 times (runs 826, 827, 832, 835, 842) and "job: deeproutes" 276 and 272 failed. Checked in detail: GOES 842 (13:37Z) and deeproutes 276: job "run" success, job "publish / publish" failure at step "Run actions/deploy-pages@v5". Log of 842: "Artifact github-pages successfully finalized. Artifact ID 15266095788", then deploy-pages: "Found 0 artifact(s)" and "Fetching artifact metadata failed. Is githubstatus.com reporting issues...". So the upload works but deploy-pages cannot see it in the same run. Effect: data branch is committed, live site can lag until the next successful publish. Not checked: step names of 826/827/832/835/272. Next step: Eric to check githubstatus.com; if it persists, consider a retry of the deploy step or splitting upload and deploy. Not a clear one-line fix, so no branch.
2. **Nightly check run 68 failed** (11:40Z to 12:01Z): job "check", step "Expectations (pass/fail on real situations)". Log shows "17/18 pass" and exit code 1; the failing case name was not in the log tail I read. Same step failed on 11-27 (run 66). Next step: find the one failing case (regress output) and decide if data or expectation is at fault. Scoring is not touched by me.
3. **job: deeproutes 275 cancelled** (10:09Z to 11:33Z), 272 failed 07:17Z-09:24Z (publish step per above for 276; 272 cause not read). Chain is running again: run 279 in_progress since 13:39Z.
4. **diag-tests / diag-scoretest / diag-smoke are stale** (last commits 2026-11-24 17:47Z, 17:49Z, 18:43Z). diag-tests: no readable pytest.txt on the branch root in my check; diag-scoretest: "expected.json updated (6 cases)"; diag-smoke: "SMOKE FAILED" (webkit PAGEERROR on the forms worker /om proxy, chromium ERR_TIMED_OUT) but dated 11-24. The live Smoke test workflow succeeded 24 of 24 in the 100 newest runs.
5. **Recovered errors (soft):** commonsphotos.json "commonsphotos: dump status" n=1, "HTTPError: 404 ... commonswiki/20261101/dumpstatus.json" (old, unchanged). fcsnap_eve.json "fcsnap_eve" n=2, "HTTPError: HTTP 429" (new today, rate limit). photoweather.json "photoweather: weather" n=1, "HTTPError: HTTP 429". All small.

## Fine
- Freshness (at 14:35Z): goes.json at 13:37:56Z (~57 min, just under the limit; GOES run 842 data committed 13:39Z); manifest.json gen 14:12:11Z; light 3.3 h, flow 3.3 h, sentinel 3.2 h, access 3.1 h, nps 3.1 h, snow 3.1 h, verify_obs 3.3 h, skill 11.7 h, fogprob 2.6 h, climonat 7.9 h, deeproutes 0.9 h old; none with ok:false.
- Data branch: datasquash.json at 09:40:22Z ok ("9482 files"); origin/data has 22 commits, newest 14:12:33Z.
- Publish gate: `git diff origin/main origin/app-verified -- app` is empty; nothing unchecked.
- Queues: no run was found queued; one run in progress (deeproutes 279). Not checked: weekly, monthly, trails, seed, tests, scoretest, app-publish (not in the 100 newest runs).

## Fix branches
None pushed.

## Forecast check
verify_obs.json gen 2026-11-28T11:17:22Z, method: 2 ("forecast made 1 day ahead"; window "airport reports within 45 min of sunrise or sunset, last 30 days").
- Fog: hit rate 0.08 (13 hit, 154 miss), false-alarm ratio 0.78 (47 false alarms), n=1877. Previous report (11-27): 0.08 / 0.79, n=1750.
- Low cloud: hit rate 0.56 (574 hit, 446 miss), false-alarm ratio 0.29 (237), n=1730. Previous: 0.54 / 0.30, n=1612.
- low_cloud_bias_pct -8.3 (n_bias 1730). Previous: -9.3.

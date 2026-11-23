# Testing

All of these run on GitHub Actions against the live site. Run one with
`gh api -X POST repos/estaugaa/shotspots/actions/workflows/<file>/dispatches -f ref=main [-f 'inputs[script]=...']`.

| What | How | When |
|---|---|---|
| Consistency (pins, offline cache list) | `pytest tests/test_consistency.py` | every app push, nightly |
| Unit tests (terrain horizon, GOES projection, verification maths, consistency) | `pytest tests/` (tests.yml) | every push touching pipeline/, tests/, config/, requirements |
| Scoring, repeatable: app/ code ranks 6 situations on frozen feeds + forecast at a fixed clock, must match `tests/score/expected.json` | `tools/scoretest.py` (scoretest.yml: mode check / update / capture) | every app push, blocks publishing |
| JavaScript unit tests (safeUrl) | `node tests/js/*.test.js` | every app push (app-publish) |
| Daily ops watcher (cloud routine, claude.ai/code/routines): workflow health, feed freshness, soft errors, publish gate, diag outputs; mechanical fixes on ops/ branches only | report on branch `diag-ops` (ops.md) | daily 6:30 AM PT |
| Fog rules vs airport reports at sunrise (the app's rule and variants, same-day and day-ahead) | `python tools/fogrule.py` (light: Open-Meteo previous runs + data/archive/obs, data/fc_archive.json, data/fc_archive_eve.json) -> ux/fogrule.txt | by hand, before changing the fog rule |
| Load profile on a phone-like connection (slow 4G, CPU x4): what loads when, whether the picks list changes or is pushed (which card grew and what text it gained, or which element above it), what each layout shift moved, CPU hotspots | `tools/loadprofile.py` (loadprofile.yml) -> branch `diag-loadprofile` | after every app publish that deployed (the report names the live build) |
| Regression checks (forecast loads, nothing past the travel limit, no Washougal text elsewhere) | `tools/regress.py` | nightly (regress.yml) |
| Expectations: pass/fail on real situations | `tools/expect.py` | nightly; history in `data/test_history.jsonl` |
| 30 situation walkthroughs (full list text) | diag.yml `tools/diag.py [numbers]` -> branch `diag-out`, `scenarios.txt` | after ranking changes |
| Old vs new scoring, same forecast | diag.yml `tools/scorecmp.py` -> branch `diag-scorecmp` | after scoring changes |
| Why a spot ranks where it does | diag.yml `tools/whyprobe.py <place words>` -> branch `diag-whyprobe` | debugging |
| Smoke (site up, page doesn't jump while loading) | smoke.yml | every 30 min |
| Webcam truth: real sunrise/sunset colour vs the sky formula | camtruth.yml (after every GOES run) -> feed/camtruth.json | continuous |
| Sky climatology aggregation (report nearest sunrise/sunset, week of year, sky classes) | `pytest tests/test_climonat.py` | with the unit tests |
| Forecast vs reality (cloud at sunrise/sunset, nationwide) | job=skill -> feed/calib.json `skill` | daily |
| Prediction log: live site ranks the next sunrise/sunset for 8 places, top 20 + layers archived | `tools/scoretest.py --live` -> data/archive/predictions | nightly (regress.yml) |
| Predictions vs truth (webcam colour, airport low cloud and fog; Spearman, spot and night level) | diag.yml `tools/predeval.py [days]` -> branch `diag-predeval` | weekly, once windows are over |
| Archive (append, de-dup, monthly files, readers' windows, old-file migration) | `pytest tests/test_archive.py` | every pipeline push |
| Starter-spot cleaning (control towers, park rides, borrowed Wikidata fame; clean() in place and idempotent) | `pytest tests/test_seedclean.py` | every pipeline push |

Weights: open the app with `#tune` for sliders (this device only; Reset restores defaults).
Score math: open the app with `#math` at the end of the URL to show the breakdown on every card (again to hide it).
Each spot page has a "Why this score" section.

Rules
- When a bug is fixed, add an expectation for it in `tools/expect.py`.
- Expectations are deliberately loose ("one of these in the top 3") so weather alone doesn't fail them.
- After an intended scoring change the scoring test fails and shows what moved: run scoretest.yml mode=update to accept (it publishes too); mode=capture refreshes the frozen data. On a branch, a commit message containing [scoretest:update] or [scoretest:capture] does the same and saves to that branch.
- Judge ranking changes on the same forecast (scorecmp), not on runs from different days.

## Latest results
- 2026-11-23: starter-spot rules measured on all 75,346 seed spots (data branch tiles + Wikidata): see DECISIONS. Same forecast, live site with the clean applied in the page: Denver sunset (60 min) top 8 all views (was Elitch ride tower #1, a control tower #3); Hood River unchanged (hatchery #31, falls and viewpoints lead).
- 2026-11-19 (night): 10 walkthroughs (Washougal, Cannon Beach, Moab, Boise, Jackson, New York, Miami, Acadia, Smokies, Sedona). Found: depth.js error on load (fixed), Jenny Lake leading Jackson with Teton Park Road closed (fixed), Haystack Rock and Hug Point ranked below an unknown waterfall at Cannon Beach because hand-researched spots' quality is Commons-only (open).
- 2026-11-17 (early): expectations 13/13, smoke test passing on both browsers, full redraw 2.1 s (was 7.7 s).
- 2026-11-16 (evening): expectations 12/12. Top picks now lead with views everywhere tested: Grand Canyon (Mather, Yaki, Powell, Hopi), Smokies (Le Conte, Newfound Gap), Moab (arches), Badlands (overlooks), Washougal (Willamette Falls, fall-colour streets, Multnomah).
- 2026-11-16: 30 situations, hand-scored average about 7.3/10 (from 6.3 on 11-15). Weak: Zion in rain, Cannon Beach (cloud on the sunset path), Bend (low cloud east).

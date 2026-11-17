# Testing

All of these run on GitHub Actions against the live site. Run one with
`gh api -X POST repos/estaugaa/shotspots/actions/workflows/<file>/dispatches -f ref=main [-f 'inputs[script]=...']`.

| What | How | When |
|---|---|---|
| Consistency (pins, offline cache list) | `pytest tests/test_consistency.py` | every app push, nightly |
| Scoring, repeatable: app/ code ranks 6 situations on frozen feeds + forecast at a fixed clock, must match `tests/score/expected.json` | `tools/scoretest.py` (scoretest.yml: mode check / update / capture) | every app push, blocks publishing |
| Regression checks (forecast loads, nothing past the travel limit, no Washougal text elsewhere) | `tools/regress.py` | nightly (regress.yml) |
| Expectations: pass/fail on real situations | `tools/expect.py` | nightly; history in `data/test_history.jsonl` |
| 30 situation walkthroughs (full list text) | diag.yml `tools/diag.py [numbers]` -> branch `diag-out`, `scenarios.txt` | after ranking changes |
| Old vs new scoring, same forecast | diag.yml `tools/scorecmp.py` -> branch `diag-scorecmp` | after scoring changes |
| Why a spot ranks where it does | diag.yml `tools/whyprobe.py <place words>` -> branch `diag-whyprobe` | debugging |
| Smoke (site up, page doesn't jump while loading) | smoke.yml | every 30 min |
| Webcam truth: real sunrise/sunset colour vs the sky formula | camtruth.yml (after every GOES run) -> feed/camtruth.json | continuous |
| Forecast vs reality (cloud at sunrise/sunset, nationwide) | job=skill -> feed/calib.json `skill` | daily |

Weights: open the app with `#tune` for sliders (this device only; Reset restores defaults).
Score math: open the app with `#math` at the end of the URL to show the breakdown on every card (again to hide it).
Each spot page has a "Why this score" section.

Rules
- When a bug is fixed, add an expectation for it in `tools/expect.py`.
- Expectations are deliberately loose ("one of these in the top 3") so weather alone doesn't fail them.
- After an intended scoring change the scoring test fails and shows what moved: run scoretest.yml mode=update to accept (it publishes too); mode=capture refreshes the frozen data.
- Judge ranking changes on the same forecast (scorecmp), not on runs from different days.

## Latest results
- 2026-11-17 (early): expectations 13/13, smoke test passing on both browsers, full redraw 2.1 s (was 7.7 s).
- 2026-11-16 (evening): expectations 12/12. Top picks now lead with views everywhere tested: Grand Canyon (Mather, Yaki, Powell, Hopi), Smokies (Le Conte, Newfound Gap), Moab (arches), Badlands (overlooks), Washougal (Willamette Falls, fall-colour streets, Multnomah).
- 2026-11-16: 30 situations, hand-scored average about 7.3/10 (from 6.3 on 11-15). Weak: Zion in rain, Cannon Beach (cloud on the sunset path), Bend (low cloud east).

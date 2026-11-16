# Testing

All of these run on GitHub Actions against the live site. Run one with
`gh api -X POST repos/estaugaa/shotspots/actions/workflows/<file>/dispatches -f ref=main [-f 'inputs[script]=...']`.

| What | How | When |
|---|---|---|
| Consistency (pins, offline cache list) | `pytest tests/test_consistency.py` | every app push, nightly |
| Regression checks (forecast loads, nothing past the travel limit, no Washougal text elsewhere) | `tools/regress.py` | nightly (regress.yml) |
| Expectations: pass/fail on real situations | `tools/expect.py` | nightly; history in `data/test_history.jsonl` |
| 30 situation walkthroughs (full list text) | diag.yml `tools/diag.py [numbers]` -> branch `diag-out`, `scenarios.txt` | after ranking changes |
| Old vs new scoring, same forecast | diag.yml `tools/scorecmp.py` -> branch `diag-scorecmp` | after scoring changes |
| Why a spot ranks where it does | diag.yml `tools/whyprobe.py <place words>` -> branch `diag-whyprobe` | debugging |
| Smoke (site up) | smoke.yml | every 30 min |

Rules
- When a bug is fixed, add an expectation for it in `tools/expect.py`.
- Expectations are deliberately loose ("one of these in the top 3") so weather alone doesn't fail them.
- Judge ranking changes on the same forecast (scorecmp), not on runs from different days.

## Latest results
- 2026-11-16: 30 situations, hand-scored average about 7.3/10 (from 6.3 on 11-15). Weak: Zion in rain, Cannon Beach (cloud on the sunset path), Bend (low cloud east).

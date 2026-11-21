# Tip ranker — which 5 should a person take? (2026-11-21 14:51 UTC)

2,206 settled tips; 58 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2419 · bookmaker price alone 0.2401 · raw model 0.2461 (lower is better). Mean P(win) 0.473 vs raw model 0.542; realised 0.48.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 55.3% | +8.2% | 2.71 | 3% | 26% | [0.033, 0.12] | [0.012, 0.194] | [0.051, 0.165] | [-0.005, 0.242] |
| SAFEST | 59.7% | +0.0% | 2.98 | 0% | 36% | [0.075, 0.164] | [-0.058, 0.1] | [0.083, 0.21] | [-0.094, 0.167] |
| VALUE | 52.1% | +6.1% | 2.6 | 5% | 22% | [-0.003, 0.089] | [-0.009, 0.174] | [0.014, 0.131] | [-0.02, 0.214] |
| CURRENT | 44.8% | -3.5% | 2.24 | 10% | 17% | [-0.074, 0.015] | [-0.116, 0.088] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 62.8% | +4.5% | 3.14 | 0% | 40% | [0.108, 0.194] | [-0.011, 0.14] | [0.114, 0.245] | [-0.049, 0.212] |
| RANDOM_5 | 47.7% | -2.1% | 2.39 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

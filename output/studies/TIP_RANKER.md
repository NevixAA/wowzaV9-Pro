# Tip ranker — which 5 should a person take? (2026-11-07 13:15 UTC)

2,051 settled tips; 54 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2435 · bookmaker price alone 0.2418 · raw model 0.2481 (lower is better). Mean P(win) 0.472 vs raw model 0.544; realised 0.481.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 55.5% | +8.8% | 2.7 | 4% | 24% | [0.035, 0.121] | [0.011, 0.199] | [0.046, 0.169] | [-0.001, 0.26] |
| SAFEST | 57.8% | -2.9% | 2.89 | 0% | 32% | [0.055, 0.143] | [-0.088, 0.07] | [0.067, 0.193] | [-0.119, 0.144] |
| VALUE | 53.3% | +9.3% | 2.67 | 4% | 18% | [0.013, 0.099] | [0.02, 0.199] | [0.03, 0.141] | [0.017, 0.257] |
| CURRENT | 44.8% | -4.3% | 2.24 | 11% | 18% | [-0.076, 0.022] | [-0.129, 0.084] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 61.5% | +2.9% | 3.07 | 0% | 39% | [0.093, 0.179] | [-0.033, 0.124] | [0.1, 0.23] | [-0.064, 0.212] |
| RANDOM_5 | 47.7% | -1.8% | 2.39 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

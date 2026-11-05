# Tip ranker — which 5 should a person take? (2026-11-05 14:47 UTC)

2,019 settled tips; 53 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2438 · bookmaker price alone 0.2421 · raw model 0.2484 (lower is better). Mean P(win) 0.472 vs raw model 0.545; realised 0.483.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 55.8% | +9.4% | 2.72 | 4% | 24% | [0.037, 0.123] | [0.01, 0.2] | [0.046, 0.167] | [-0.007, 0.253] |
| SAFEST | 57.7% | -2.9% | 2.89 | 0% | 32% | [0.052, 0.145] | [-0.092, 0.065] | [0.057, 0.192] | [-0.134, 0.132] |
| VALUE | 54.0% | +10.5% | 2.7 | 4% | 19% | [0.019, 0.103] | [0.029, 0.21] | [0.03, 0.143] | [0.019, 0.259] |
| CURRENT | 45.3% | -3.1% | 2.26 | 11% | 19% | [-0.076, 0.024] | [-0.123, 0.094] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 61.5% | +3.0% | 3.08 | 0% | 40% | [0.09, 0.181] | [-0.037, 0.125] | [0.094, 0.226] | [-0.078, 0.205] |
| RANDOM_5 | 47.9% | -1.5% | 2.39 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

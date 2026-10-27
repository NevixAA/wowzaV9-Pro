# Tip ranker — which 5 should a person take? (2026-10-27 12:23 UTC)

1,832 settled tips; 45 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2431 · bookmaker price alone 0.2419 · raw model 0.2478 (lower is better). Mean P(win) 0.475 vs raw model 0.545; realised 0.485.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 55.5% | +9.1% | 2.69 | 4% | 22% | [0.026, 0.119] | [-0.001, 0.192] | [0.0, 0.125] | [-0.096, 0.162] |
| SAFEST | 60.0% | +2.0% | 3.0 | 0% | 33% | [0.067, 0.166] | [-0.053, 0.119] | [0.04, 0.173] | [-0.171, 0.11] |
| VALUE | 53.8% | +8.0% | 2.69 | 4% | 22% | [0.007, 0.101] | [-0.009, 0.194] | [-0.013, 0.107] | [-0.102, 0.157] |
| CURRENT | 49.3% | +5.2% | 2.47 | 7% | 22% | [-0.041, 0.059] | [-0.045, 0.169] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 62.7% | +5.6% | 3.13 | 0% | 40% | [0.097, 0.188] | [-0.017, 0.143] | [0.067, 0.2] | [-0.135, 0.138] |
| RANDOM_5 | 48.3% | -1.0% | 2.42 | 4% | 17% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

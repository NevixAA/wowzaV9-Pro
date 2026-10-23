# Tip ranker — which 5 should a person take? (2026-10-23 11:48 UTC)

1,573 settled tips; 40 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2407 · bookmaker price alone 0.241 · raw model 0.2465 (lower is better). Mean P(win) 0.476 vs raw model 0.543; realised 0.495.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 56.6% | +12.4% | 2.77 | 5% | 22% | [0.033, 0.134] | [0.01, 0.225] | [0.004, 0.132] | [-0.052, 0.202] |
| SAFEST | 58.5% | +1.4% | 2.92 | 2% | 30% | [0.051, 0.156] | [-0.077, 0.118] | [0.015, 0.16] | [-0.179, 0.125] |
| VALUE | 56.5% | +14.4% | 2.83 | 5% | 30% | [0.028, 0.143] | [0.025, 0.282] | [-0.0, 0.14] | [-0.049, 0.256] |
| CURRENT | 49.5% | +4.1% | 2.48 | 8% | 22% | [-0.04, 0.068] | [-0.074, 0.166] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 64.0% | +9.7% | 3.2 | 0% | 32% | [0.114, 0.208] | [0.018, 0.19] | [0.08, 0.215] | [-0.083, 0.202] |
| RANDOM_5 | 48.0% | -0.7% | 2.4 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

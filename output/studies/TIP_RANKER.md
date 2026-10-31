# Tip ranker — which 5 should a person take? (2026-10-31 12:44 UTC)

1,880 settled tips; 48 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.243 · bookmaker price alone 0.2418 · raw model 0.2482 (lower is better). Mean P(win) 0.475 vs raw model 0.545; realised 0.483.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 54.5% | +6.7% | 2.65 | 4% | 21% | [0.024, 0.113] | [-0.006, 0.183] | [0.011, 0.133] | [-0.077, 0.184] |
| SAFEST | 59.2% | +0.6% | 2.96 | 0% | 33% | [0.067, 0.163] | [-0.056, 0.111] | [0.05, 0.183] | [-0.15, 0.134] |
| VALUE | 53.7% | +7.8% | 2.69 | 4% | 21% | [0.016, 0.106] | [0.002, 0.198] | [0.004, 0.125] | [-0.061, 0.191] |
| CURRENT | 47.5% | +1.3% | 2.38 | 8% | 21% | [-0.051, 0.047] | [-0.07, 0.144] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 62.1% | +4.7% | 3.1 | 0% | 40% | [0.098, 0.189] | [-0.009, 0.15] | [0.079, 0.212] | [-0.116, 0.176] |
| RANDOM_5 | 47.6% | -2.4% | 2.38 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

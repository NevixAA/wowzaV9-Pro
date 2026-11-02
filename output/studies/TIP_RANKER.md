# Tip ranker — which 5 should a person take? (2026-11-02 16:11 UTC)

1,977 settled tips; 51 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2436 · bookmaker price alone 0.242 · raw model 0.2482 (lower is better). Mean P(win) 0.471 vs raw model 0.545; realised 0.483.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 56.5% | +10.9% | 2.75 | 4% | 26% | [0.042, 0.132] | [0.03, 0.224] | [0.048, 0.174] | [0.004, 0.273] |
| SAFEST | 57.6% | -2.6% | 2.88 | 0% | 33% | [0.052, 0.148] | [-0.087, 0.076] | [0.055, 0.184] | [-0.142, 0.141] |
| VALUE | 54.5% | +11.1% | 2.73 | 4% | 20% | [0.026, 0.11] | [0.043, 0.221] | [0.031, 0.149] | [0.017, 0.272] |
| CURRENT | 45.5% | -3.1% | 2.27 | 12% | 20% | [-0.075, 0.026] | [-0.119, 0.104] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 61.6% | +3.5% | 3.08 | 0% | 41% | [0.093, 0.184] | [-0.027, 0.137] | [0.09, 0.231] | [-0.08, 0.207] |
| RANDOM_5 | 47.7% | -2.1% | 2.39 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

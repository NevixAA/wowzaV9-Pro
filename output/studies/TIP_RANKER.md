# Tip ranker — which 5 should a person take? (2026-10-18 11:19 UTC)

1,483 settled tips; 36 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2411 · bookmaker price alone 0.2417 · raw model 0.2466 (lower is better). Mean P(win) 0.474 vs raw model 0.542; realised 0.492.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 55.1% | +9.4% | 2.69 | 6% | 22% | [0.026, 0.122] | [-0.007, 0.208] | [-0.016, 0.111] | [-0.092, 0.156] |
| SAFEST | 56.7% | -2.5% | 2.83 | 3% | 28% | [0.043, 0.146] | [-0.099, 0.083] | [-0.006, 0.133] | [-0.23, 0.075] |
| VALUE | 55.0% | +11.7% | 2.75 | 6% | 31% | [0.021, 0.135] | [0.004, 0.268] | [-0.022, 0.122] | [-0.088, 0.219] |
| CURRENT | 50.0% | +5.2% | 2.5 | 8% | 25% | [-0.031, 0.086] | [-0.058, 0.199] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 63.3% | +8.8% | 3.17 | 0% | 31% | [0.118, 0.205] | [0.02, 0.192] | [0.067, 0.2] | [-0.112, 0.188] |
| RANDOM_5 | 47.3% | -1.9% | 2.36 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

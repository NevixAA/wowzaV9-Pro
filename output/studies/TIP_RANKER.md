# Tip ranker — which 5 should a person take? (2026-10-24 11:13 UTC)

1,587 settled tips; 41 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2408 · bookmaker price alone 0.241 · raw model 0.2464 (lower is better). Mean P(win) 0.476 vs raw model 0.543; realised 0.495.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 56.2% | +11.4% | 2.76 | 5% | 22% | [0.027, 0.126] | [0.004, 0.211] | [0.007, 0.126] | [-0.056, 0.192] |
| SAFEST | 58.0% | +0.7% | 2.9 | 2% | 29% | [0.048, 0.152] | [-0.084, 0.112] | [0.02, 0.156] | [-0.184, 0.117] |
| VALUE | 56.1% | +13.5% | 2.8 | 5% | 29% | [0.024, 0.139] | [0.02, 0.268] | [0.0, 0.137] | [-0.042, 0.242] |
| CURRENT | 49.3% | +3.6% | 2.46 | 7% | 22% | [-0.042, 0.065] | [-0.069, 0.156] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 63.9% | +9.7% | 3.2 | 0% | 32% | [0.114, 0.202] | [0.019, 0.183] | [0.078, 0.215] | [-0.079, 0.204] |
| RANDOM_5 | 48.1% | -0.5% | 2.4 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

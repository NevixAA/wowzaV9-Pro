# Tip ranker — which 5 should a person take? (2026-11-08 13:36 UTC)

2,104 settled tips; 55 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2431 · bookmaker price alone 0.241 · raw model 0.2474 (lower is better). Mean P(win) 0.472 vs raw model 0.543; realised 0.48.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 54.9% | +7.5% | 2.67 | 4% | 24% | [0.03, 0.116] | [-0.001, 0.184] | [0.042, 0.163] | [-0.01, 0.246] |
| SAFEST | 57.8% | -3.2% | 2.89 | 0% | 31% | [0.057, 0.143] | [-0.09, 0.064] | [0.069, 0.189] | [-0.123, 0.134] |
| VALUE | 52.4% | +7.3% | 2.62 | 6% | 18% | [0.004, 0.09] | [0.001, 0.186] | [0.022, 0.131] | [-0.008, 0.237] |
| CURRENT | 44.7% | -4.2% | 2.24 | 11% | 18% | [-0.078, 0.019] | [-0.126, 0.085] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 61.5% | +2.4% | 3.07 | 0% | 38% | [0.093, 0.18] | [-0.035, 0.122] | [0.102, 0.233] | [-0.072, 0.203] |
| RANDOM_5 | 47.7% | -2.0% | 2.38 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

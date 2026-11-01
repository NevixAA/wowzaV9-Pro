# Tip ranker — which 5 should a person take? (2026-11-01 12:18 UTC)

1,925 settled tips; 49 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2427 · bookmaker price alone 0.2418 · raw model 0.2484 (lower is better). Mean P(win) 0.475 vs raw model 0.544; realised 0.481.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 54.6% | +7.1% | 2.65 | 4% | 20% | [0.029, 0.116] | [0.002, 0.187] | [0.02, 0.145] | [-0.054, 0.212] |
| SAFEST | 59.2% | +0.5% | 2.96 | 0% | 33% | [0.068, 0.165] | [-0.048, 0.115] | [0.057, 0.192] | [-0.13, 0.152] |
| VALUE | 53.9% | +8.2% | 2.69 | 4% | 20% | [0.019, 0.106] | [0.013, 0.205] | [0.012, 0.135] | [-0.042, 0.225] |
| CURRENT | 46.5% | -0.8% | 2.33 | 10% | 20% | [-0.058, 0.039] | [-0.087, 0.127] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 62.4% | +5.3% | 3.12 | 0% | 41% | [0.104, 0.195] | [-0.002, 0.158] | [0.09, 0.229] | [-0.091, 0.206] |
| RANDOM_5 | 47.5% | -2.6% | 2.37 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

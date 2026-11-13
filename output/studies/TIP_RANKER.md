# Tip ranker — which 5 should a person take? (2026-11-13 14:43 UTC)

2,143 settled tips; 56 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2424 · bookmaker price alone 0.2405 · raw model 0.2468 (lower is better). Mean P(win) 0.471 vs raw model 0.542; realised 0.479.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 55.3% | +8.2% | 2.7 | 4% | 25% | [0.034, 0.122] | [0.008, 0.193] | [0.048, 0.166] | [-0.008, 0.254] |
| SAFEST | 58.2% | -2.5% | 2.91 | 0% | 32% | [0.062, 0.149] | [-0.083, 0.076] | [0.075, 0.2] | [-0.118, 0.148] |
| VALUE | 52.9% | +8.0% | 2.64 | 5% | 20% | [0.009, 0.096] | [0.009, 0.193] | [0.029, 0.136] | [0.003, 0.24] |
| CURRENT | 44.6% | -4.2% | 2.23 | 11% | 18% | [-0.079, 0.018] | [-0.126, 0.086] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 61.8% | +3.0% | 3.09 | 0% | 39% | [0.098, 0.184] | [-0.024, 0.125] | [0.107, 0.236] | [-0.062, 0.205] |
| RANDOM_5 | 47.6% | -2.1% | 2.38 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

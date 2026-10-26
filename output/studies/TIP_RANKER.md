# Tip ranker — which 5 should a person take? (2026-10-26 12:34 UTC)

1,819 settled tips; 44 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2433 · bookmaker price alone 0.2419 · raw model 0.2479 (lower is better). Mean P(win) 0.475 vs raw model 0.545; realised 0.484.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 54.9% | +8.0% | 2.66 | 4% | 20% | [0.023, 0.116] | [-0.008, 0.192] | [-0.005, 0.124] | [-0.102, 0.168] |
| SAFEST | 59.5% | +1.2% | 2.98 | 0% | 32% | [0.066, 0.166] | [-0.058, 0.117] | [0.036, 0.173] | [-0.181, 0.112] |
| VALUE | 53.2% | +6.9% | 2.66 | 4% | 20% | [0.004, 0.098] | [-0.021, 0.194] | [-0.018, 0.1] | [-0.108, 0.151] |
| CURRENT | 49.1% | +4.6% | 2.45 | 7% | 23% | [-0.041, 0.063] | [-0.049, 0.176] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 61.8% | +4.0% | 3.09 | 0% | 39% | [0.092, 0.182] | [-0.025, 0.137] | [0.059, 0.191] | [-0.145, 0.131] |
| RANDOM_5 | 48.0% | -1.7% | 2.4 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

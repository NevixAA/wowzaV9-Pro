# Tip ranker — which 5 should a person take? (2026-10-19 09:19 UTC)

1,529 settled tips; 37 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2405 · bookmaker price alone 0.2411 · raw model 0.2462 (lower is better). Mean P(win) 0.474 vs raw model 0.542; realised 0.495.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 55.2% | +9.8% | 2.7 | 5% | 22% | [0.024, 0.119] | [-0.008, 0.202] | [-0.007, 0.12] | [-0.076, 0.173] |
| SAFEST | 57.3% | -1.7% | 2.86 | 3% | 30% | [0.048, 0.147] | [-0.093, 0.082] | [0.005, 0.151] | [-0.211, 0.096] |
| VALUE | 55.1% | +12.0% | 2.76 | 5% | 30% | [0.021, 0.133] | [0.005, 0.262] | [-0.011, 0.13] | [-0.07, 0.241] |
| CURRENT | 49.2% | +3.9% | 2.46 | 8% | 24% | [-0.046, 0.077] | [-0.077, 0.182] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 64.3% | +9.9% | 3.22 | 0% | 32% | [0.121, 0.212] | [0.03, 0.196] | [0.081, 0.222] | [-0.093, 0.212] |
| RANDOM_5 | 47.6% | -1.4% | 2.38 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

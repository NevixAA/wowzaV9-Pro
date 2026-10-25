# Tip ranker — which 5 should a person take? (2026-10-25 11:42 UTC)

1,659 settled tips; 42 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2421 · bookmaker price alone 0.2416 · raw model 0.2472 (lower is better). Mean P(win) 0.476 vs raw model 0.542; realised 0.488.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 55.8% | +10.6% | 2.74 | 5% | 21% | [0.027, 0.124] | [-0.001, 0.207] | [0.006, 0.123] | [-0.075, 0.176] |
| SAFEST | 57.6% | -0.1% | 2.88 | 2% | 29% | [0.046, 0.147] | [-0.085, 0.103] | [0.019, 0.152] | [-0.2, 0.103] |
| VALUE | 55.7% | +12.7% | 2.79 | 5% | 29% | [0.024, 0.136] | [0.019, 0.258] | [-0.0, 0.133] | [-0.062, 0.224] |
| CURRENT | 49.0% | +4.7% | 2.45 | 7% | 21% | [-0.039, 0.064] | [-0.059, 0.174] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 63.3% | +8.7% | 3.17 | 0% | 31% | [0.111, 0.199] | [0.017, 0.177] | [0.081, 0.21] | [-0.098, 0.177] |
| RANDOM_5 | 47.8% | -0.9% | 2.39 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

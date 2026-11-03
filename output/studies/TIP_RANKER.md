# Tip ranker — which 5 should a person take? (2026-11-03 14:28 UTC)

1,996 settled tips; 52 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2439 · bookmaker price alone 0.2422 · raw model 0.2484 (lower is better). Mean P(win) 0.471 vs raw model 0.545; realised 0.484.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 56.1% | +10.0% | 2.73 | 4% | 25% | [0.037, 0.127] | [0.015, 0.212] | [0.051, 0.171] | [0.004, 0.265] |
| SAFEST | 57.7% | -2.7% | 2.88 | 0% | 33% | [0.052, 0.144] | [-0.095, 0.068] | [0.058, 0.192] | [-0.133, 0.138] |
| VALUE | 54.2% | +10.5% | 2.71 | 4% | 19% | [0.022, 0.105] | [0.028, 0.21] | [0.035, 0.15] | [0.018, 0.269] |
| CURRENT | 45.0% | -3.5% | 2.25 | 12% | 19% | [-0.08, 0.021] | [-0.127, 0.093] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 61.5% | +3.3% | 3.08 | 0% | 40% | [0.09, 0.18] | [-0.034, 0.127] | [0.1, 0.235] | [-0.074, 0.209] |
| RANDOM_5 | 47.9% | -1.5% | 2.4 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

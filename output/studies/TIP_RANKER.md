# Tip ranker — which 5 should a person take? (2026-10-20 11:16 UTC)

1,540 settled tips; 38 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.24 · bookmaker price alone 0.2409 · raw model 0.2463 (lower is better). Mean P(win) 0.475 vs raw model 0.542; realised 0.495.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 56.5% | +12.0% | 2.76 | 5% | 24% | [0.036, 0.135] | [0.017, 0.234] | [0.004, 0.139] | [-0.052, 0.213] |
| SAFEST | 58.4% | +0.8% | 2.92 | 3% | 32% | [0.057, 0.159] | [-0.071, 0.121] | [0.021, 0.168] | [-0.182, 0.136] |
| VALUE | 56.3% | +14.1% | 2.82 | 5% | 32% | [0.03, 0.146] | [0.033, 0.291] | [-0.0, 0.147] | [-0.048, 0.27] |
| CURRENT | 48.9% | +2.8% | 2.45 | 8% | 24% | [-0.044, 0.075] | [-0.082, 0.167] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 63.7% | +8.7% | 3.18 | 0% | 32% | [0.117, 0.206] | [0.021, 0.185] | [0.079, 0.216] | [-0.088, 0.202] |
| RANDOM_5 | 47.5% | -1.7% | 2.38 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

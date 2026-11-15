# Tip ranker — which 5 should a person take? (2026-11-15 14:04 UTC)

2,161 settled tips; 57 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2421 · bookmaker price alone 0.2402 · raw model 0.2464 (lower is better). Mean P(win) 0.47 vs raw model 0.542; realised 0.48.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 56.1% | +9.2% | 2.74 | 4% | 26% | [0.038, 0.129] | [0.018, 0.198] | [0.056, 0.177] | [0.009, 0.26] |
| SAFEST | 58.9% | -1.3% | 2.95 | 0% | 33% | [0.068, 0.155] | [-0.071, 0.085] | [0.081, 0.207] | [-0.103, 0.159] |
| VALUE | 53.7% | +9.0% | 2.68 | 5% | 21% | [0.014, 0.104] | [0.019, 0.204] | [0.032, 0.147] | [0.01, 0.253] |
| CURRENT | 44.6% | -4.4% | 2.23 | 10% | 18% | [-0.079, 0.016] | [-0.125, 0.078] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 62.5% | +4.0% | 3.12 | 0% | 40% | [0.104, 0.191] | [-0.016, 0.134] | [0.112, 0.246] | [-0.051, 0.216] |
| RANDOM_5 | 47.7% | -2.1% | 2.39 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

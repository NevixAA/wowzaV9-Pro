# Tip ranker — which 5 should a person take? (2026-10-22 07:50 UTC)

1,566 settled tips; 39 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2407 · bookmaker price alone 0.2411 · raw model 0.2463 (lower is better). Mean P(win) 0.475 vs raw model 0.543; realised 0.496.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 56.5% | +12.1% | 2.77 | 5% | 23% | [0.034, 0.138] | [0.016, 0.235] | [0.004, 0.134] | [-0.053, 0.208] |
| SAFEST | 59.0% | +2.0% | 2.95 | 3% | 31% | [0.059, 0.164] | [-0.058, 0.135] | [0.026, 0.169] | [-0.172, 0.139] |
| VALUE | 56.4% | +14.1% | 2.82 | 5% | 31% | [0.029, 0.15] | [0.03, 0.283] | [-0.0, 0.144] | [-0.049, 0.264] |
| CURRENT | 49.2% | +3.3% | 2.46 | 8% | 23% | [-0.043, 0.073] | [-0.072, 0.164] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 64.6% | +10.5% | 3.23 | 0% | 33% | [0.126, 0.216] | [0.037, 0.202] | [0.082, 0.221] | [-0.077, 0.214] |
| RANDOM_5 | 47.6% | -1.6% | 2.38 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

# Tip ranker — which 5 should a person take? (2026-10-29 13:14 UTC)

1,852 settled tips; 46 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.243 · bookmaker price alone 0.2419 · raw model 0.248 (lower is better). Mean P(win) 0.475 vs raw model 0.545; realised 0.483.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 55.2% | +8.2% | 2.67 | 4% | 22% | [0.03, 0.121] | [0.008, 0.201] | [0.008, 0.135] | [-0.078, 0.184] |
| SAFEST | 59.6% | +1.3% | 2.98 | 0% | 33% | [0.071, 0.168] | [-0.047, 0.124] | [0.048, 0.178] | [-0.157, 0.121] |
| VALUE | 53.5% | +7.2% | 2.67 | 4% | 22% | [0.014, 0.105] | [-0.005, 0.196] | [-0.004, 0.113] | [-0.08, 0.177] |
| CURRENT | 48.3% | +2.9% | 2.41 | 9% | 22% | [-0.044, 0.055] | [-0.055, 0.158] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 62.2% | +4.8% | 3.11 | 0% | 39% | [0.1, 0.189] | [-0.008, 0.148] | [0.074, 0.204] | [-0.122, 0.156] |
| RANDOM_5 | 47.6% | -2.5% | 2.38 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

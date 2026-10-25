# Tip ranker — which 5 should a person take? (2026-10-25 13:31 UTC)

1,781 settled tips; 43 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2435 · bookmaker price alone 0.2424 · raw model 0.248 (lower is better). Mean P(win) 0.474 vs raw model 0.545; realised 0.487.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 56.2% | +10.6% | 2.72 | 2% | 21% | [0.036, 0.123] | [0.013, 0.208] | [-0.0, 0.131] | [-0.088, 0.183] |
| SAFEST | 59.1% | +0.6% | 2.95 | 0% | 30% | [0.059, 0.159] | [-0.069, 0.107] | [0.028, 0.163] | [-0.196, 0.095] |
| VALUE | 54.4% | +9.4% | 2.72 | 2% | 21% | [0.017, 0.107] | [0.006, 0.209] | [-0.014, 0.107] | [-0.094, 0.171] |
| CURRENT | 49.8% | +5.7% | 2.49 | 7% | 23% | [-0.037, 0.066] | [-0.046, 0.179] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 61.4% | +3.6% | 3.07 | 0% | 37% | [0.085, 0.176] | [-0.034, 0.129] | [0.051, 0.181] | [-0.168, 0.121] |
| RANDOM_5 | 48.3% | -1.1% | 2.41 | 4% | 17% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

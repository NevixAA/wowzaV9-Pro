# Tip ranker — which 5 should a person take? (2026-11-20 15:41 UTC)

2,194 settled tips; 57 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2418 · bookmaker price alone 0.24 · raw model 0.246 (lower is better). Mean P(win) 0.473 vs raw model 0.542; realised 0.481.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 55.6% | +8.8% | 2.72 | 4% | 26% | [0.033, 0.12] | [0.009, 0.195] | [0.048, 0.168] | [-0.0, 0.244] |
| SAFEST | 60.0% | +0.5% | 3.0 | 0% | 37% | [0.076, 0.163] | [-0.06, 0.1] | [0.084, 0.218] | [-0.097, 0.17] |
| VALUE | 52.3% | +6.6% | 2.61 | 5% | 23% | [-0.003, 0.09] | [-0.012, 0.175] | [0.014, 0.13] | [-0.028, 0.219] |
| CURRENT | 44.9% | -3.3% | 2.25 | 10% | 18% | [-0.078, 0.017] | [-0.119, 0.085] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 63.2% | +5.1% | 3.16 | 0% | 40% | [0.107, 0.197] | [-0.012, 0.141] | [0.116, 0.249] | [-0.052, 0.218] |
| RANDOM_5 | 48.0% | -1.5% | 2.4 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

# Tip ranker — which 5 should a person take? (2026-10-30 13:06 UTC)

1,862 settled tips; 47 match days with >= 10 tips scored walk-forward (ranker fitted on earlier days only).

Honest P(win): Brier ranker 0.2432 · bookmaker price alone 0.2421 · raw model 0.2483 (lower is better). Mean P(win) 0.475 vs raw model 0.545; realised 0.482.

| List | Hit rate | ROI | Hits/day of 5 | 0/5 days | 4+/5 days | Hit vs random (90% CI) | ROI vs random | Hit vs current | ROI vs current |
|---|---|---|---|---|---|---|---|---|---|
| BEST_BETS | 54.4% | +6.6% | 2.64 | 4% | 21% | [0.025, 0.117] | [0.0, 0.189] | [0.002, 0.126] | [-0.091, 0.167] |
| SAFEST | 58.7% | -0.1% | 2.94 | 0% | 32% | [0.063, 0.163] | [-0.063, 0.113] | [0.038, 0.174] | [-0.169, 0.113] |
| VALUE | 53.6% | +7.8% | 2.68 | 4% | 21% | [0.016, 0.107] | [0.001, 0.2] | [-0.0, 0.115] | [-0.071, 0.177] |
| CURRENT | 48.1% | +2.8% | 2.4 | 8% | 21% | [-0.044, 0.054] | [-0.051, 0.159] | [0.0, 0.0] | [0.0, 0.0] |
| SHORTEST_ODDS | 61.3% | +3.4% | 3.06 | 0% | 38% | [0.092, 0.182] | [-0.021, 0.139] | [0.068, 0.196] | [-0.134, 0.138] |
| RANDOM_5 | 47.5% | -2.6% | 2.37 | 4% | 16% | — | — | — | — |

RANDOM_5 = the exact expectation of 5 random picks from the same day's list. A CI entirely above zero means the list beat that baseline across days, not just on average.

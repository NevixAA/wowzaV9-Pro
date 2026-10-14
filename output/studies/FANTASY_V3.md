# Fantasy (FPL) — v9 projections vs Player V3 (2026-10-14 13:41 UTC)

Population: Premier League squad panel from 2025-07-01 (missed fixtures = 0 points). Scored: appearance + goals + assists (CS, saves, cards, bonus, DC excluded both sides). 42 weeks, 18,981 player-fixtures.

| Variant | MAE | Spearman (per week) | Captain pts | Top-11 pts | MAE Δ 90% CI | Captain Δ CI | Top-11 Δ CI | Verdict |
|---|---|---|---|---|---|---|---|---|
| V9 | 1.2503 | 0.3025 | 4.0 | 33.02 | — | — | — | baseline |
| V9_CAL | 1.2357 | 0.3005 | 4.095 | 33.76 | [-0.016, -0.0132] | [-0.4048, 0.619] | [-0.1905, 1.619] | MORE_ACCURATE_PICKS_NOT_SHOWN |
| V9_MIN | 0.8873 | 0.636 | 4.31 | 39.36 | [-0.3829, -0.3424] | [-0.2857, 1.0] | [4.8095, 7.9762] | BETTER |
| V3_FULL | 0.8919 | 0.6356 | 4.619 | 41.71 | [-0.3788, -0.3376] | [-0.0952, 1.3571] | [6.6429, 10.8333] | BETTER |

## Fair slice — player appeared in his club's previous match (11,941 player-fixtures, 42 weeks)

Live v9 Fantasy also uses FPL injury flags, which have no history; this slice removes the long absences those flags partly catch. **The recommendation rests on this table.**

| Variant | MAE | Spearman | Captain pts | Top-11 pts | MAE Δ CI | Captain Δ CI | Top-11 Δ CI | Verdict |
|---|---|---|---|---|---|---|---|---|
| V9 | 1.2297 | 0.3014 | 4.286 | 39.0 | — | — | — | baseline |
| V9_CAL | 1.2132 | 0.2968 | 4.0 | 38.67 | [-0.0185, -0.0142] | [-0.9524, 0.3571] | [-1.5714, 0.8571] | MORE_ACCURATE_PICKS_NOT_SHOWN |
| V9_MIN | 1.0398 | 0.4386 | 4.381 | 39.69 | [-0.2039, -0.1765] | [-0.2381, 0.4762] | [-0.6917, 1.9286] | MORE_ACCURATE_PICKS_NOT_SHOWN |
| V3_FULL | 1.0473 | 0.4365 | 4.548 | 42.02 | [-0.197, -0.1687] | [-0.1905, 0.7381] | [1.1905, 4.7619] | BETTER |

MAE Δ negative = more accurate; captain / top-11 Δ positive = better picks (actual points, captain not doubled). Rule in the module docstring, fixed before results.

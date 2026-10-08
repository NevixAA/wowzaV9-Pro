# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **56%**.
- Tip period, 74 matches with a clean Bet365 price: BTTS happened 61% while the de-vigged price implied 42% (gap 19.3 points).
- **B, blind YES on every match: +36%** [+16%, +56%], n 74.
- A, matches Wowza picked: +42%; matches it did not pick: +23%. Difference +19% [-18%, +53%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2433 vs 0.2846; residual z 0.39 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (78 fixtures). The whole market is behind, not one book.
- 50 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 923 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 104 | 63% | 53% | 67% | -10.7 | +3.2 |
| UNDER 5-10pp | 189 | 63% | 52% | 60% | -11.2 | -3.8 |
| UNDER 2-5pp | 131 | 59% | 52% | 55% | -6.9 | -3.4 |
| agrees (±2pp) | 231 | 54% | 52% | 52% | -1.8 | -1.8 |
| OVER 2-5pp | 128 | 44% | 51% | 48% | +7.5 | +4.1 |
| OVER 5-10pp | 106 | 46% | 52% | 45% | +5.5 | -1.5 |
| model OVER by >10pp | 34 | 47% | 53% | 41% | +6.2 | -6.0 |

- Share of the model's lean that showed up in results: leaning UNDER -0.254, leaning OVER -0.101 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 923 | 0.24274 | 0.24841 | -0.00054 | [-0.0022, +0.0012] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 497 | 0.24117 | 0.24788 | +0.00064 | [-0.0033, +0.0052] | NO_DETECTABLE_GAIN |
| OU25 | standard | 426 | 0.24457 | 0.24903 | +0.00772 | [+0.0019, +0.0134] | MODEL_HURTS |
| OU35 | all | 251 | 0.23671 | 0.25216 | +0.08672 | [+0.0097, +0.1837] | MODEL_HURTS |
| OU35 | new_format | 203 | 0.23504 | 0.25265 | +0.07214 | [+0.0152, +0.1384] | MODEL_HURTS |
| BTTS | all | 911 | 0.24175 | 0.24404 | +0.01223 | [+0.0012, +0.0241] | MODEL_HURTS |
| BTTS | new_format | 494 | 0.24368 | 0.24275 | +0.00899 | [+0.0026, +0.0154] | MODEL_HURTS |
| BTTS | standard | 417 | 0.23946 | 0.24557 | +0.00745 | [-0.0087, +0.0255] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

18 cells tested (of 28; the rest are too small). Pooled prior +6.2%, between-cell sd 0.19. Reality-check p for the best cell: **0.024**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 73 | +39% | +28% | 0.99 | 0.03 | [-6.5, +2.6] | PAPER (n 73 < 150) |
| Brazil Serie A | ou25 | 13 | +53% | +19% | 0.87 | 0.36 | [-10.2, +5.8] | PAPER (n 13 < 150) |
| Brazil Serie A | btts | 15 | +37% | +15% | 0.83 | 0.57 | [-32.0, +24.4] | PAPER (n 15 < 150) |
| Sweden Allsvenskan | ou25 | 21 | +25% | +12% | 0.77 | 0.67 | [-6.4, +7.4] | PAPER (n 21 < 150) |
| Serie B | ou25 | 19 | +23% | +12% | 0.77 | 0.67 | [-1.7, +13.7] | PAPER (n 19 < 150) |
| Argentina Primera Division | ou25 | 28 | +18% | +10% | 0.72 | 0.79 | [-5.4, +6.4] | PAPER (n 28 < 150) |
| Denmark Superliga | ou25 | 13 | +5% | +6% | 0.64 | 0.89 | [-8.7, +10.5] | PAPER (n 13 < 150) |
| La Liga 2 | ou25 | 29 | +4% | +6% | 0.63 | 0.89 | [-3.7, +4.8] | PAPER (n 29 < 150) |
| Mexico Liga MX | ou25 | 20 | +0% | +4% | 0.60 | 0.89 | [-0.7, +10.8] | PAPER (n 20 < 150) |
| Argentina Primera Division | over15 | 77 | +2% | +4% | 0.63 | 0.89 | [-0.5, +2.8] | PAPER (n 77 < 150) |
| Japan J-League | ou25 | 18 | -4% | +3% | 0.57 | 0.91 | [-9.9, +11.4] | PAPER (n 18 < 150) |
| Ireland Premier Division | ou25 | 10 | -13% | +2% | 0.55 | 0.94 | [-14.6, +5.2] | PAPER (n 10 < 150) |
| China Super League | ou25 | 18 | -29% | -2% | 0.45 | 0.94 | [-14.2, +7.7] | PAPER (n 18 < 150) |
| Austrian Bundesliga | ou25 | 12 | -28% | -3% | 0.44 | 0.94 | [-19.5, +2.0] | PAPER (n 12 < 150) |
| Championship | ou25 | 18 | -20% | -3% | 0.43 | 0.94 | [-10.3, +5.6] | PAPER (n 18 < 150) |
| Bundesliga 2 | ou25 | 11 | -35% | -3% | 0.43 | 0.94 | [-17.9, +10.9] | PAPER (n 11 < 150) |
| League One | ou25 | 14 | -35% | -6% | 0.36 | 0.94 | [-7.6, +6.2] | PAPER (n 14 < 150) |
| Norway Eliteserien | ou25 | 12 | -84% | -17% | 0.16 | 1.00 | [-20.6, +9.6] | PAPER (n 12 < 150) |

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

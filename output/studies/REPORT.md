# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **54%**.
- Tip period, 93 matches with a clean Bet365 price: BTTS happened 57% while the de-vigged price implied 42% (gap 15.0 points).
- **B, blind YES on every match: +26%** [+8%, +46%], n 93.
- A, matches Wowza picked: +39%; matches it did not pick: +9%. Difference +30% [+1%, +59%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2433 vs 0.2816; residual z 0.94 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (91 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1083 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 146 | 61% | 51% | 66% | -9.5 | +5.1 |
| UNDER 5-10pp | 219 | 63% | 52% | 59% | -11.0 | -3.6 |
| UNDER 2-5pp | 149 | 59% | 52% | 55% | -7.3 | -3.9 |
| agrees (±2pp) | 260 | 52% | 52% | 52% | -0.2 | -0.1 |
| OVER 2-5pp | 143 | 45% | 52% | 48% | +6.9 | +3.5 |
| OVER 5-10pp | 125 | 46% | 52% | 45% | +5.6 | -1.4 |
| model OVER by >10pp | 41 | 46% | 53% | 41% | +7.1 | -5.1 |

- Share of the model's lean that showed up in results: leaning UNDER -0.148, leaning OVER -0.062 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1083 | 0.24196 | 0.24753 | +0.00208 | [-0.0006, +0.0048] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 586 | 0.24044 | 0.2462 | +0.00534 | [-0.0001, +0.0112] | NO_DETECTABLE_GAIN |
| OU25 | standard | 497 | 0.24375 | 0.2491 | +0.00513 | [-0.0019, +0.0125] | NO_DETECTABLE_GAIN |
| OU35 | all | 291 | 0.23453 | 0.24947 | +0.06701 | [+0.0218, +0.1272] | MODEL_HURTS |
| OU35 | new_format | 229 | 0.23362 | 0.25061 | +0.06701 | [+0.0241, +0.1223] | MODEL_HURTS |
| BTTS | all | 1075 | 0.24097 | 0.24333 | +0.00927 | [+0.0026, +0.0168] | MODEL_HURTS |
| BTTS | new_format | 587 | 0.24078 | 0.24109 | +0.00908 | [+0.0035, +0.0163] | MODEL_HURTS |
| BTTS | standard | 488 | 0.24119 | 0.24603 | +0.01061 | [-0.0036, +0.0259] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 28; the rest are too small). Pooled prior +5.6%, between-cell sd 0.19. Reality-check p for the best cell: **0.043**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Brazil Serie A | ou25 | 20 | +62% | +27% | 0.96 | 0.05 | [-7.5, +4.9] | PAPER (n 20 < 150) |
| Argentina Primera Division | btts | 81 | +33% | +25% | 0.99 | 0.05 | [-5.9, +2.3] | PAPER (n 81 < 150) |
| Serie B | ou25 | 20 | +27% | +13% | 0.80 | 0.71 | [-1.6, +13.0] | PAPER (n 20 < 150) |
| Brazil Serie A | btts | 18 | +26% | +13% | 0.79 | 0.71 | [-23.0, +19.4] | PAPER (n 18 < 150) |
| Sweden Allsvenskan | ou25 | 26 | +19% | +11% | 0.75 | 0.71 | [-5.7, +5.4] | PAPER (n 26 < 150) |
| Argentina Primera Division | ou25 | 31 | +13% | +8% | 0.69 | 0.71 | [-4.6, +5.8] | PAPER (n 31 < 150) |
| Finland Veikkausliiga | ou25 | 13 | +14% | +8% | 0.68 | 0.71 | [-10.3, +8.4] | PAPER (n 13 < 150) |
| Japan J-League | ou25 | 24 | +9% | +7% | 0.68 | 0.71 | [-6.1, +12.3] | PAPER (n 24 < 150) |
| Denmark Superliga | ou25 | 17 | +10% | +7% | 0.66 | 0.71 | [-6.7, +7.2] | PAPER (n 17 < 150) |
| Mexico Liga MX | ou25 | 24 | +8% | +7% | 0.67 | 0.71 | [-0.2, +9.2] | PAPER (n 24 < 150) |
| La Liga 2 | ou25 | 32 | +1% | +4% | 0.60 | 0.77 | [-3.0, +4.5] | PAPER (n 32 < 150) |
| Argentina Primera Division | over15 | 85 | +2% | +3% | 0.61 | 0.75 | [-0.3, +2.7] | PAPER (n 85 < 150) |
| Austrian Bundesliga | ou25 | 15 | -8% | +2% | 0.55 | 0.87 | [-17.1, +4.3] | PAPER (n 15 < 150) |
| Ireland Premier Division | ou25 | 12 | -28% | -3% | 0.42 | 0.99 | [-16.8, +4.7] | PAPER (n 12 < 150) |
| China Super League | ou25 | 23 | -24% | -4% | 0.39 | 0.99 | [-10.6, +5.0] | PAPER (n 23 < 150) |
| Championship | ou25 | 19 | -25% | -5% | 0.37 | 0.99 | [-9.7, +5.1] | PAPER (n 19 < 150) |
| Bundesliga 2 | ou25 | 12 | -41% | -7% | 0.35 | 1.00 | [-15.9, +10.5] | PAPER (n 12 < 150) |
| League One | ou25 | 17 | -47% | -12% | 0.23 | 1.00 | [-8.0, +5.1] | PAPER (n 17 < 150) |
| Norway Eliteserien | ou25 | 16 | -71% | -19% | 0.12 | 1.00 | [-15.6, +5.2] | PAPER (n 16 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 789 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.6853 | 0.24635 | – | – | – | – | – |
| v9 | 0.69377 | 0.25028 | 170 | 0.759 | -15.32 | -9% | -3.87 |
| Challenger | 0.68648 | 0.24676 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.393, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

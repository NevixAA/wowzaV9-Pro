# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **55%**.
- Tip period, 98 matches with a clean Bet365 price: BTTS happened 58% while the de-vigged price implied 42% (gap 16.1 points).
- **B, blind YES on every match: +28%** [+10%, +48%], n 98.
- A, matches Wowza picked: +39%; matches it did not pick: +16%. Difference +23% [-6%, +50%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2435 vs 0.2812; residual z 0.95 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (94 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1126 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 163 | 60% | 51% | 66% | -8.2 | +6.5 |
| UNDER 5-10pp | 227 | 63% | 52% | 59% | -10.6 | -3.3 |
| UNDER 2-5pp | 151 | 59% | 52% | 55% | -7.2 | -3.7 |
| agrees (±2pp) | 266 | 53% | 52% | 52% | -0.9 | -0.9 |
| OVER 2-5pp | 148 | 45% | 52% | 48% | +6.6 | +3.2 |
| OVER 5-10pp | 128 | 47% | 52% | 45% | +5.2 | -1.9 |
| model OVER by >10pp | 43 | 44% | 54% | 41% | +9.4 | -2.9 |

- Share of the model's lean that showed up in results: leaning UNDER -0.054, leaning OVER -0.052 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1126 | 0.24236 | 0.24738 | +0.00314 | [+0.0004, +0.0060] | MODEL_HURTS |
| OU25 | new_format | 609 | 0.24043 | 0.24511 | +0.00830 | [+0.0021, +0.0155] | MODEL_HURTS |
| OU25 | standard | 517 | 0.24463 | 0.25006 | +0.00410 | [-0.0025, +0.0106] | NO_DETECTABLE_GAIN |
| OU35 | all | 309 | 0.23394 | 0.24812 | +0.04886 | [-0.0005, +0.1106] | NO_DETECTABLE_GAIN |
| OU35 | new_format | 243 | 0.23266 | 0.24905 | +0.06153 | [+0.0204, +0.1098] | MODEL_HURTS |
| BTTS | all | 1118 | 0.24125 | 0.24334 | +0.00951 | [+0.0024, +0.0176] | MODEL_HURTS |
| BTTS | new_format | 610 | 0.24134 | 0.24125 | +0.00903 | [+0.0043, +0.0147] | MODEL_HURTS |
| BTTS | standard | 508 | 0.24114 | 0.24586 | +0.00955 | [-0.0044, +0.0245] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 29; the rest are too small). Pooled prior +4.8%, between-cell sd 0.19. Reality-check p for the best cell: **0.056**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 81 | +33% | +25% | 0.99 | 0.07 | [-5.9, +2.3] | PAPER (n 81 < 150) |
| Brazil Serie A | ou25 | 21 | +54% | +24% | 0.94 | 0.11 | [-7.1, +4.5] | PAPER (n 21 < 150) |
| Serie B | ou25 | 20 | +27% | +13% | 0.79 | 0.61 | [-1.6, +13.0] | PAPER (n 20 < 150) |
| Brazil Serie A | btts | 18 | +26% | +12% | 0.78 | 0.61 | [-23.0, +19.4] | PAPER (n 18 < 150) |
| Sweden Allsvenskan | ou25 | 27 | +23% | +12% | 0.78 | 0.61 | [-5.8, +5.0] | PAPER (n 27 < 150) |
| Argentina Primera Division | ou25 | 31 | +13% | +7% | 0.68 | 0.71 | [-4.6, +5.8] | PAPER (n 31 < 150) |
| Finland Veikkausliiga | ou25 | 13 | +14% | +7% | 0.67 | 0.71 | [-10.3, +8.4] | PAPER (n 13 < 150) |
| Japan J-League | ou25 | 24 | +9% | +7% | 0.67 | 0.71 | [-6.1, +12.3] | PAPER (n 24 < 150) |
| Denmark Superliga | ou25 | 17 | +10% | +6% | 0.65 | 0.71 | [-6.7, +7.2] | PAPER (n 17 < 150) |
| Mexico Liga MX | ou25 | 24 | +8% | +6% | 0.66 | 0.71 | [-0.2, +9.2] | PAPER (n 24 < 150) |
| La Liga 2 | ou25 | 32 | +1% | +4% | 0.59 | 0.77 | [-3.0, +4.5] | PAPER (n 32 < 150) |
| Argentina Primera Division | over15 | 85 | +2% | +3% | 0.60 | 0.75 | [-0.3, +2.7] | PAPER (n 85 < 150) |
| Austrian Bundesliga | ou25 | 16 | -13% | -1% | 0.49 | 0.99 | [-16.2, +3.4] | PAPER (n 16 < 150) |
| Ireland Premier Division | ou25 | 14 | -24% | -4% | 0.41 | 1.00 | [-14.3, +4.3] | PAPER (n 14 < 150) |
| China Super League | ou25 | 23 | -24% | -5% | 0.37 | 1.00 | [-10.6, +5.0] | PAPER (n 23 < 150) |
| Bundesliga 2 | ou25 | 12 | -41% | -7% | 0.34 | 1.00 | [-15.9, +10.5] | PAPER (n 12 < 150) |
| Championship | ou25 | 23 | -26% | -8% | 0.30 | 1.00 | [-7.7, +6.6] | PAPER (n 23 < 150) |
| League One | ou25 | 18 | -50% | -14% | 0.19 | 1.00 | [-7.4, +5.3] | PAPER (n 18 < 150) |
| Norway Eliteserien | ou25 | 16 | -71% | -20% | 0.11 | 1.00 | [-15.6, +5.2] | PAPER (n 16 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 832 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68578 | 0.24653 | – | – | – | – | – |
| v9 | 0.69229 | 0.24957 | 191 | 0.775 | -8.71 | -5% | -3.87 |
| Challenger | 0.6867 | 0.24685 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.217, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

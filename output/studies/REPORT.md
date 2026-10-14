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

- 1090 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 147 | 61% | 51% | 66% | -9.8 | +4.8 |
| UNDER 5-10pp | 220 | 63% | 52% | 59% | -11.2 | -3.8 |
| UNDER 2-5pp | 150 | 59% | 52% | 55% | -7.6 | -4.1 |
| agrees (±2pp) | 261 | 52% | 52% | 52% | -0.3 | -0.3 |
| OVER 2-5pp | 144 | 45% | 52% | 48% | +6.5 | +3.1 |
| OVER 5-10pp | 126 | 46% | 52% | 45% | +6.0 | -1.0 |
| model OVER by >10pp | 42 | 45% | 54% | 41% | +8.4 | -3.8 |

- Share of the model's lean that showed up in results: leaning UNDER -0.176, leaning OVER -0.082 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1090 | 0.24178 | 0.24766 | +0.00200 | [-0.0006, +0.0046] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 586 | 0.24044 | 0.2462 | +0.00534 | [-0.0001, +0.0113] | NO_DETECTABLE_GAIN |
| OU25 | standard | 504 | 0.24334 | 0.24936 | +0.00508 | [-0.0018, +0.0121] | NO_DETECTABLE_GAIN |
| OU35 | all | 292 | 0.23487 | 0.25034 | +0.06664 | [+0.0204, +0.1286] | MODEL_HURTS |
| OU35 | new_format | 229 | 0.23362 | 0.25061 | +0.06701 | [+0.0241, +0.1227] | MODEL_HURTS |
| BTTS | all | 1082 | 0.2409 | 0.24334 | +0.00917 | [+0.0024, +0.0169] | MODEL_HURTS |
| BTTS | new_format | 587 | 0.24078 | 0.24109 | +0.00908 | [+0.0035, +0.0164] | MODEL_HURTS |
| BTTS | standard | 495 | 0.24106 | 0.24601 | +0.01071 | [-0.0032, +0.0261] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 29; the rest are too small). Pooled prior +4.9%, between-cell sd 0.19. Reality-check p for the best cell: **0.047**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 81 | +33% | +24% | 0.99 | 0.07 | [-5.9, +2.3] | PAPER (n 81 < 150) |
| Brazil Serie A | ou25 | 21 | +54% | +24% | 0.94 | 0.10 | [-7.1, +4.5] | PAPER (n 21 < 150) |
| Serie B | ou25 | 20 | +27% | +13% | 0.79 | 0.71 | [-1.6, +13.0] | PAPER (n 20 < 150) |
| Brazil Serie A | btts | 18 | +26% | +12% | 0.78 | 0.71 | [-23.0, +19.4] | PAPER (n 18 < 150) |
| Sweden Allsvenskan | ou25 | 26 | +19% | +10% | 0.74 | 0.71 | [-5.7, +5.4] | PAPER (n 26 < 150) |
| Argentina Primera Division | ou25 | 31 | +13% | +8% | 0.68 | 0.71 | [-4.6, +5.8] | PAPER (n 31 < 150) |
| Finland Veikkausliiga | ou25 | 13 | +14% | +7% | 0.67 | 0.71 | [-10.3, +8.4] | PAPER (n 13 < 150) |
| Japan J-League | ou25 | 24 | +9% | +7% | 0.67 | 0.71 | [-6.1, +12.3] | PAPER (n 24 < 150) |
| Denmark Superliga | ou25 | 17 | +10% | +6% | 0.65 | 0.71 | [-6.7, +7.2] | PAPER (n 17 < 150) |
| Mexico Liga MX | ou25 | 24 | +8% | +6% | 0.66 | 0.71 | [-0.2, +9.2] | PAPER (n 24 < 150) |
| La Liga 2 | ou25 | 32 | +1% | +4% | 0.59 | 0.77 | [-3.0, +4.5] | PAPER (n 32 < 150) |
| Argentina Primera Division | over15 | 85 | +2% | +3% | 0.61 | 0.75 | [-0.3, +2.7] | PAPER (n 85 < 150) |
| Austrian Bundesliga | ou25 | 15 | -8% | +2% | 0.54 | 0.87 | [-17.1, +4.3] | PAPER (n 15 < 150) |
| Ireland Premier Division | ou25 | 12 | -28% | -4% | 0.41 | 1.00 | [-16.8, +4.7] | PAPER (n 12 < 150) |
| China Super League | ou25 | 23 | -24% | -5% | 0.39 | 1.00 | [-10.6, +5.0] | PAPER (n 23 < 150) |
| Bundesliga 2 | ou25 | 12 | -41% | -7% | 0.34 | 1.00 | [-15.9, +10.5] | PAPER (n 12 < 150) |
| Championship | ou25 | 21 | -32% | -9% | 0.28 | 1.00 | [-8.6, +4.4] | PAPER (n 21 < 150) |
| League One | ou25 | 17 | -47% | -12% | 0.22 | 1.00 | [-8.0, +5.1] | PAPER (n 17 < 150) |
| Norway Eliteserien | ou25 | 16 | -71% | -19% | 0.12 | 1.00 | [-15.6, +5.2] | PAPER (n 16 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 796 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68485 | 0.24612 | – | – | – | – | – |
| v9 | 0.69405 | 0.25043 | 171 | 0.76 | -16.32 | -10% | -3.87 |
| Challenger | 0.68602 | 0.24653 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.431, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

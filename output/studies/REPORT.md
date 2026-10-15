# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **54%**.
- Tip period, 94 matches with a clean Bet365 price: BTTS happened 57% while the de-vigged price implied 42% (gap 15.4 points).
- **B, blind YES on every match: +27%** [+8%, +48%], n 94.
- A, matches Wowza picked: +39%; matches it did not pick: +12%. Difference +27% [-1%, +56%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2435 vs 0.2822; residual z 0.81 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (92 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1099 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 150 | 61% | 52% | 66% | -9.8 | +4.8 |
| UNDER 5-10pp | 223 | 63% | 52% | 59% | -11.2 | -3.9 |
| UNDER 2-5pp | 151 | 59% | 52% | 55% | -7.2 | -3.7 |
| agrees (±2pp) | 262 | 53% | 52% | 52% | -0.5 | -0.5 |
| OVER 2-5pp | 144 | 45% | 52% | 48% | +6.5 | +3.1 |
| OVER 5-10pp | 127 | 46% | 52% | 45% | +5.6 | -1.4 |
| model OVER by >10pp | 42 | 45% | 54% | 41% | +8.4 | -3.8 |

- Share of the model's lean that showed up in results: leaning UNDER -0.162, leaning OVER -0.055 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1099 | 0.24163 | 0.24737 | +0.00229 | [-0.0004, +0.0049] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 592 | 0.2399 | 0.2456 | +0.00602 | [+0.0009, +0.0118] | MODEL_HURTS |
| OU25 | standard | 507 | 0.24365 | 0.24944 | +0.00506 | [-0.0018, +0.0120] | NO_DETECTABLE_GAIN |
| OU35 | all | 298 | 0.2344 | 0.24965 | +0.02666 | [+0.0030, +0.0614] | MODEL_HURTS |
| OU35 | new_format | 234 | 0.23338 | 0.2505 | +0.06526 | [+0.0218, +0.1198] | MODEL_HURTS |
| BTTS | all | 1091 | 0.24099 | 0.24333 | +0.00972 | [+0.0023, +0.0179] | MODEL_HURTS |
| BTTS | new_format | 593 | 0.24064 | 0.24093 | +0.00918 | [+0.0037, +0.0160] | MODEL_HURTS |
| BTTS | standard | 498 | 0.24141 | 0.24618 | +0.00949 | [-0.0044, +0.0252] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 29; the rest are too small). Pooled prior +5.1%, between-cell sd 0.18. Reality-check p for the best cell: **0.059**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 81 | +33% | +24% | 0.99 | 0.07 | [-5.9, +2.3] | PAPER (n 81 < 150) |
| Brazil Serie A | ou25 | 21 | +54% | +23% | 0.94 | 0.11 | [-7.1, +4.5] | PAPER (n 21 < 150) |
| Serie B | ou25 | 20 | +27% | +13% | 0.80 | 0.71 | [-1.6, +13.0] | PAPER (n 20 < 150) |
| Brazil Serie A | btts | 18 | +26% | +12% | 0.78 | 0.71 | [-23.0, +19.4] | PAPER (n 18 < 150) |
| Sweden Allsvenskan | ou25 | 26 | +19% | +10% | 0.75 | 0.71 | [-5.7, +5.4] | PAPER (n 26 < 150) |
| Argentina Primera Division | ou25 | 31 | +13% | +8% | 0.68 | 0.71 | [-4.6, +5.8] | PAPER (n 31 < 150) |
| Finland Veikkausliiga | ou25 | 13 | +14% | +7% | 0.68 | 0.71 | [-10.3, +8.4] | PAPER (n 13 < 150) |
| Japan J-League | ou25 | 24 | +9% | +7% | 0.67 | 0.71 | [-6.1, +12.3] | PAPER (n 24 < 150) |
| Denmark Superliga | ou25 | 17 | +10% | +6% | 0.65 | 0.71 | [-6.7, +7.2] | PAPER (n 17 < 150) |
| Mexico Liga MX | ou25 | 24 | +8% | +6% | 0.66 | 0.71 | [-0.2, +9.2] | PAPER (n 24 < 150) |
| La Liga 2 | ou25 | 32 | +1% | +4% | 0.60 | 0.77 | [-3.0, +4.5] | PAPER (n 32 < 150) |
| Argentina Primera Division | over15 | 85 | +2% | +3% | 0.61 | 0.75 | [-0.3, +2.7] | PAPER (n 85 < 150) |
| Austrian Bundesliga | ou25 | 15 | -8% | +2% | 0.54 | 0.87 | [-17.1, +4.3] | PAPER (n 15 < 150) |
| Ireland Premier Division | ou25 | 12 | -28% | -3% | 0.43 | 1.00 | [-16.8, +4.7] | PAPER (n 12 < 150) |
| China Super League | ou25 | 23 | -24% | -4% | 0.40 | 1.00 | [-10.6, +5.0] | PAPER (n 23 < 150) |
| Bundesliga 2 | ou25 | 12 | -41% | -6% | 0.35 | 1.00 | [-15.9, +10.5] | PAPER (n 12 < 150) |
| Championship | ou25 | 23 | -26% | -7% | 0.32 | 1.00 | [-7.7, +6.6] | PAPER (n 23 < 150) |
| League One | ou25 | 17 | -47% | -11% | 0.23 | 1.00 | [-8.0, +5.1] | PAPER (n 17 < 150) |
| Norway Eliteserien | ou25 | 16 | -71% | -18% | 0.13 | 1.00 | [-15.6, +5.2] | PAPER (n 16 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 805 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68432 | 0.24584 | – | – | – | – | – |
| v9 | 0.69256 | 0.24969 | 175 | 0.766 | -14.39 | -8% | -3.77 |
| Challenger | 0.68547 | 0.24625 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.325, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

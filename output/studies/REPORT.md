# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 48%, since 10 Aug **55%**.
- Tip period, 164 matches with a clean Bet365 price: BTTS happened 55% while the de-vigged price implied 43% (gap 12.3 points).
- **B, blind YES on every match: +21%** [+6%, +36%], n 164.
- A, matches Wowza picked: +21%; matches it did not pick: +20%. Difference +1% [-22%, +21%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2508 vs 0.2688; residual z -0.83 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (172 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 2033 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 409 | 65% | 50% | 65% | -15.3 | -0.1 |
| UNDER 5-10pp | 405 | 58% | 52% | 59% | -6.4 | +1.1 |
| UNDER 2-5pp | 274 | 57% | 52% | 55% | -5.8 | -2.3 |
| agrees (±2pp) | 439 | 51% | 52% | 52% | +0.3 | +0.3 |
| OVER 2-5pp | 244 | 48% | 52% | 48% | +4.2 | +0.7 |
| OVER 5-10pp | 193 | 46% | 53% | 46% | +6.8 | -0.3 |
| model OVER by >10pp | 69 | 45% | 55% | 42% | +10.0 | -2.4 |

- Share of the model's lean that showed up in results: leaning UNDER -0.024, leaning OVER 0.013 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 2033 | 0.24072 | 0.24896 | +0.00042 | [-0.0012, +0.0020] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 1138 | 0.23617 | 0.2479 | +0.00391 | [+0.0007, +0.0074] | MODEL_HURTS |
| OU25 | standard | 895 | 0.24652 | 0.25032 | +0.00346 | [-0.0004, +0.0079] | NO_DETECTABLE_GAIN |
| OU15 | all | 280 | 0.19819 | 0.19776 | +0.00373 | [-0.0053, +0.0115] | NO_DETECTABLE_GAIN |
| OU15 | new_format | 174 | 0.19666 | 0.1974 | -0.00495 | [-0.0124, +0.0031] | NO_DETECTABLE_GAIN |
| OU15 | standard | 106 | 0.20068 | 0.19834 | +0.03698 | [+0.0185, +0.0494] | MODEL_HURTS |
| OU35 | all | 748 | 0.22327 | 0.23548 | +0.03705 | [+0.0148, +0.0649] | MODEL_HURTS |
| OU35 | new_format | 525 | 0.22469 | 0.24062 | +0.02763 | [+0.0110, +0.0476] | MODEL_HURTS |
| OU35 | standard | 223 | 0.21991 | 0.22337 | +0.00079 | [-0.0120, +0.0195] | NO_DETECTABLE_GAIN |
| BTTS | all | 2035 | 0.24311 | 0.24459 | +0.00064 | [-0.0008, +0.0021] | NO_DETECTABLE_GAIN |
| BTTS | new_format | 1149 | 0.24211 | 0.24306 | +0.00263 | [-0.0003, +0.0057] | NO_DETECTABLE_GAIN |
| BTTS | standard | 886 | 0.24441 | 0.24656 | +0.00168 | [-0.0037, +0.0076] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 40; the rest are too small). Pooled prior -3.0%, between-cell sd 0.00. Reality-check p for the best cell: **0.608**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 105 | +20% | -3% | 0.24 | 0.97 | [-4.6, +1.9] | PAPER (n 105 < 150) |
| Argentina Primera Division | ou25 | 35 | +14% | -3% | 0.24 | 0.97 | [-3.8, +5.1] | PAPER (n 35 < 150) |
| Argentina Primera Division | over15 | 107 | +7% | -3% | 0.24 | 0.97 | [+0.2, +2.8] | PAPER (n 107 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -3% | 0.24 | 0.97 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| Brazil Serie A | btts | 21 | +28% | -3% | 0.24 | 0.97 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Brazil Serie A | ou25 | 38 | +13% | -3% | 0.24 | 0.97 | [-7.9, +1.9] | PAPER (CLV deterioration alarm) |
| Bundesliga 2 | ou25 | 20 | -24% | -3% | 0.24 | 0.97 | [-9.1, +9.3] | PAPER (n 20 < 150) |
| Championship | ou25 | 31 | -29% | -3% | 0.24 | 0.97 | [-6.0, +4.9] | PAPER (n 31 < 150) |
| China Super League | ou25 | 33 | -18% | -3% | 0.24 | 0.97 | [-9.1, +2.3] | PAPER (n 33 < 150) |
| Denmark Superliga | ou25 | 33 | -14% | -3% | 0.24 | 0.97 | [-3.8, +5.4] | PAPER (n 33 < 150) |
| Finland Veikkausliiga | ou25 | 28 | -10% | -3% | 0.24 | 0.97 | [-7.1, +4.1] | PAPER (CLV deterioration alarm) |
| Ireland Premier Division | ou25 | 24 | -30% | -3% | 0.24 | 0.97 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Japan J-League | btts | 11 | -25% | -3% | 0.24 | 0.97 | – | PAPER (n 11 < 150) |
| Japan J-League | ou25 | 36 | -3% | -3% | 0.24 | 0.97 | [-3.1, +7.5] | PAPER (n 36 < 150) |
| La Liga 2 | btts | 10 | -22% | -3% | 0.24 | 0.97 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| La Liga 2 | ou25 | 39 | -7% | -3% | 0.24 | 0.97 | [-2.3, +3.9] | PAPER (n 39 < 150) |
| League One | ou25 | 26 | -44% | -3% | 0.24 | 0.98 | [-6.8, +2.7] | PAPER (n 26 < 150) |
| League Two | ou25 | 19 | +5% | -3% | 0.24 | 0.97 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| Mexico Liga MX | ou25 | 47 | +3% | -3% | 0.24 | 0.97 | [-1.1, +6.7] | PAPER (CLV deterioration alarm) |
| Norway Eliteserien | ou25 | 30 | -24% | -3% | 0.24 | 0.97 | [-9.2, +3.2] | PAPER (n 30 < 150) |
| Serie B | ou25 | 23 | +19% | -3% | 0.24 | 0.97 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Sweden Allsvenskan | ou25 | 50 | +6% | -3% | 0.24 | 0.97 | [-3.9, +2.3] | PAPER (n 50 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1874 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.67788 | 0.24263 | – | – | – | – | – |
| v9 | 0.69312 | 0.24998 | 539 | 0.844 | -78.67 | -15% | -3.9 |
| Challenger | 0.6795 | 0.24337 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.35, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

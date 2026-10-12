# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **55%**.
- Tip period, 90 matches with a clean Bet365 price: BTTS happened 59% while the de-vigged price implied 42% (gap 16.9 points).
- **B, blind YES on every match: +31%** [+13%, +49%], n 90.
- A, matches Wowza picked: +42%; matches it did not pick: +15%. Difference +27% [-1%, +56%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2433 vs 0.2816; residual z 0.94 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (90 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1066 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 141 | 61% | 52% | 66% | -9.2 | +5.3 |
| UNDER 5-10pp | 216 | 62% | 52% | 59% | -10.4 | -3.0 |
| UNDER 2-5pp | 148 | 59% | 52% | 55% | -7.6 | -4.2 |
| agrees (±2pp) | 255 | 52% | 52% | 52% | +0.0 | +0.0 |
| OVER 2-5pp | 143 | 45% | 52% | 48% | +6.9 | +3.5 |
| OVER 5-10pp | 124 | 47% | 52% | 45% | +5.3 | -1.8 |
| model OVER by >10pp | 39 | 46% | 53% | 41% | +7.2 | -5.0 |

- Share of the model's lean that showed up in results: leaning UNDER -0.128, leaning OVER -0.047 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1066 | 0.2424 | 0.24753 | +0.00147 | [-0.0009, +0.0040] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 574 | 0.24114 | 0.24625 | +0.00558 | [-0.0000, +0.0117] | NO_DETECTABLE_GAIN |
| OU25 | standard | 492 | 0.24386 | 0.24902 | +0.00472 | [-0.0020, +0.0110] | NO_DETECTABLE_GAIN |
| OU35 | all | 288 | 0.23457 | 0.24927 | +0.06845 | [+0.0213, +0.1292] | MODEL_HURTS |
| OU35 | new_format | 226 | 0.23366 | 0.25037 | +0.05335 | [+0.0123, +0.1025] | MODEL_HURTS |
| BTTS | all | 1058 | 0.24113 | 0.24326 | +0.00928 | [+0.0024, +0.0172] | MODEL_HURTS |
| BTTS | new_format | 575 | 0.24106 | 0.24097 | +0.00886 | [+0.0027, +0.0164] | MODEL_HURTS |
| BTTS | standard | 483 | 0.24121 | 0.24599 | +0.00662 | [-0.0070, +0.0211] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 28; the rest are too small). Pooled prior +7.0%, between-cell sd 0.20. Reality-check p for the best cell: **0.028**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 79 | +36% | +28% | 0.99 | 0.03 | [-6.1, +2.2] | PAPER (n 79 < 150) |
| Brazil Serie A | ou25 | 19 | +60% | +27% | 0.95 | 0.08 | [-7.6, +5.5] | PAPER (n 19 < 150) |
| Serie B | ou25 | 20 | +27% | +15% | 0.82 | 0.65 | [-1.6, +13.0] | PAPER (n 20 < 150) |
| Brazil Serie A | btts | 18 | +26% | +14% | 0.80 | 0.65 | [-23.0, +19.4] | PAPER (n 18 < 150) |
| Sweden Allsvenskan | ou25 | 25 | +23% | +13% | 0.80 | 0.65 | [-5.3, +5.9] | PAPER (n 25 < 150) |
| Finland Veikkausliiga | ou25 | 12 | +24% | +12% | 0.75 | 0.65 | [-11.7, +9.2] | PAPER (n 12 < 150) |
| Denmark Superliga | ou25 | 16 | +16% | +10% | 0.71 | 0.65 | [-6.8, +7.9] | PAPER (n 16 < 150) |
| Argentina Primera Division | ou25 | 31 | +13% | +9% | 0.71 | 0.65 | [-4.6, +5.8] | PAPER (n 31 < 150) |
| Japan J-League | ou25 | 24 | +9% | +8% | 0.69 | 0.65 | [-6.1, +12.3] | PAPER (n 24 < 150) |
| Mexico Liga MX | ou25 | 24 | +8% | +7% | 0.68 | 0.65 | [-0.2, +9.2] | PAPER (n 24 < 150) |
| La Liga 2 | ou25 | 30 | +0% | +5% | 0.61 | 0.79 | [-3.5, +4.6] | PAPER (n 30 < 150) |
| Argentina Primera Division | over15 | 82 | +4% | +5% | 0.67 | 0.65 | [-0.5, +2.7] | PAPER (n 82 < 150) |
| Austrian Bundesliga | ou25 | 15 | -8% | +3% | 0.56 | 0.87 | [-17.1, +4.3] | PAPER (n 15 < 150) |
| Ireland Premier Division | ou25 | 12 | -28% | -3% | 0.43 | 0.99 | [-16.8, +4.7] | PAPER (n 12 < 150) |
| China Super League | ou25 | 23 | -24% | -4% | 0.40 | 0.99 | [-10.6, +5.0] | PAPER (n 23 < 150) |
| Championship | ou25 | 19 | -25% | -5% | 0.38 | 0.99 | [-9.7, +5.1] | PAPER (n 19 < 150) |
| Bundesliga 2 | ou25 | 12 | -41% | -6% | 0.36 | 1.00 | [-15.9, +10.5] | PAPER (n 12 < 150) |
| League One | ou25 | 17 | -47% | -12% | 0.23 | 1.00 | [-8.0, +5.1] | PAPER (n 17 < 150) |
| Norway Eliteserien | ou25 | 16 | -71% | -20% | 0.12 | 1.00 | [-15.6, +5.2] | PAPER (n 16 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 772 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68661 | 0.24699 | – | – | – | – | – |
| v9 | 0.69406 | 0.25042 | 164 | 0.756 | -13.53 | -8% | -3.86 |
| Challenger | 0.68759 | 0.24731 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.412, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **56%**.
- Tip period, 115 matches with a clean Bet365 price: BTTS happened 58% while the de-vigged price implied 42% (gap 15.8 points).
- **B, blind YES on every match: +28%** [+12%, +45%], n 115.
- A, matches Wowza picked: +38%; matches it did not pick: +18%. Difference +20% [-8%, +46%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.246 vs 0.2837; residual z -0.03 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (105 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1305 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 205 | 60% | 51% | 66% | -9.9 | +5.2 |
| UNDER 5-10pp | 260 | 61% | 52% | 59% | -9.3 | -1.9 |
| UNDER 2-5pp | 183 | 58% | 52% | 55% | -6.6 | -3.2 |
| agrees (±2pp) | 294 | 52% | 52% | 52% | -0.4 | -0.4 |
| OVER 2-5pp | 170 | 48% | 52% | 48% | +3.6 | +0.2 |
| OVER 5-10pp | 143 | 45% | 52% | 45% | +6.9 | -0.2 |
| model OVER by >10pp | 50 | 44% | 54% | 42% | +10.1 | -2.2 |

- Share of the model's lean that showed up in results: leaning UNDER -0.001, leaning OVER 0.045 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1305 | 0.24316 | 0.24842 | +0.00151 | [-0.0006, +0.0037] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 705 | 0.24194 | 0.24691 | +0.00441 | [-0.0006, +0.0101] | NO_DETECTABLE_GAIN |
| OU25 | standard | 600 | 0.2446 | 0.2502 | +0.00327 | [-0.0020, +0.0087] | NO_DETECTABLE_GAIN |
| OU35 | all | 366 | 0.23468 | 0.24863 | +0.06502 | [+0.0105, +0.1332] | MODEL_HURTS |
| OU35 | new_format | 283 | 0.2338 | 0.24918 | +0.00092 | [-0.0006, +0.0025] | NO_DETECTABLE_GAIN |
| BTTS | all | 1300 | 0.24259 | 0.2446 | +0.01223 | [+0.0052, +0.0194] | MODEL_HURTS |
| BTTS | new_format | 709 | 0.24207 | 0.24258 | +0.00962 | [+0.0051, +0.0145] | MODEL_HURTS |
| BTTS | standard | 591 | 0.24322 | 0.24702 | +0.00566 | [-0.0051, +0.0183] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 30; the rest are too small). Pooled prior +4.2%, between-cell sd 0.17. Reality-check p for the best cell: **0.037**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 86 | +33% | +23% | 0.99 | 0.06 | [-5.6, +2.1] | PAPER (n 86 < 150) |
| Brazil Serie A | ou25 | 25 | +47% | +21% | 0.93 | 0.15 | [-6.5, +3.3] | PAPER (n 25 < 150) |
| Sweden Allsvenskan | ou25 | 31 | +24% | +12% | 0.79 | 0.62 | [-4.7, +4.4] | PAPER (n 31 < 150) |
| Serie B | ou25 | 22 | +25% | +11% | 0.78 | 0.62 | [-1.3, +11.8] | PAPER (n 22 < 150) |
| Brazil Serie A | btts | 20 | +24% | +11% | 0.77 | 0.62 | [-21.0, +17.7] | PAPER (n 20 < 150) |
| Mexico Liga MX | ou25 | 29 | +12% | +7% | 0.70 | 0.67 | [-1.7, +7.7] | PAPER (CLV deterioration alarm) |
| Argentina Primera Division | ou25 | 33 | +15% | +7% | 0.69 | 0.67 | [-4.2, +5.4] | PAPER (n 33 < 150) |
| Finland Veikkausliiga | ou25 | 19 | +11% | +6% | 0.66 | 0.67 | [-6.6, +7.1] | PAPER (n 19 < 150) |
| Japan J-League | ou25 | 28 | +8% | +6% | 0.66 | 0.67 | [-4.3, +10.6] | PAPER (n 28 < 150) |
| Argentina Primera Division | over15 | 93 | +5% | +5% | 0.68 | 0.67 | [-0.1, +2.7] | PAPER (n 93 < 150) |
| La Liga 2 | ou25 | 36 | -4% | +2% | 0.54 | 0.98 | [-2.7, +4.2] | PAPER (n 36 < 150) |
| Denmark Superliga | ou25 | 21 | -11% | -1% | 0.48 | 0.98 | [-4.8, +7.1] | PAPER (n 21 < 150) |
| Austrian Bundesliga | ou25 | 19 | -15% | -2% | 0.46 | 0.98 | [-14.3, +5.0] | PAPER (n 19 < 150) |
| Ireland Premier Division | ou25 | 16 | -20% | -3% | 0.43 | 0.98 | [-12.5, +3.4] | PAPER (n 16 < 150) |
| Bundesliga 2 | ou25 | 15 | -35% | -6% | 0.34 | 0.98 | [-13.2, +9.9] | PAPER (n 15 < 150) |
| Championship | ou25 | 24 | -29% | -8% | 0.28 | 0.98 | [-7.8, +5.9] | PAPER (n 24 < 150) |
| China Super League | ou25 | 26 | -33% | -8% | 0.28 | 0.98 | [-10.6, +4.1] | PAPER (n 26 < 150) |
| League One | ou25 | 22 | -46% | -14% | 0.17 | 0.98 | [-8.1, +3.7] | PAPER (n 22 < 150) |
| Norway Eliteserien | ou25 | 21 | -49% | -14% | 0.17 | 0.98 | [-11.9, +6.6] | PAPER (n 21 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1011 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68699 | 0.24708 | – | – | – | – | – |
| v9 | 0.69464 | 0.25072 | 256 | 0.785 | -16.19 | -6% | -3.87 |
| Challenger | 0.68715 | 0.24706 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.263, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

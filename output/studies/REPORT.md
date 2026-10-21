# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **56%**.
- Tip period, 115 matches with a clean Bet365 price: BTTS happened 58% while the de-vigged price implied 42% (gap 15.8 points).
- **B, blind YES on every match: +28%** [+12%, +45%], n 115.
- A, matches Wowza picked: +38%; matches it did not pick: +18%. Difference +20% [-8%, +46%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.246 vs 0.2837; residual z -0.03 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (105 fixtures). The whole market is behind, not one book.
- 52 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1289 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 201 | 61% | 51% | 66% | -10.0 | +5.1 |
| UNDER 5-10pp | 256 | 62% | 52% | 59% | -9.8 | -2.4 |
| UNDER 2-5pp | 178 | 58% | 52% | 55% | -5.9 | -2.5 |
| agrees (±2pp) | 292 | 52% | 52% | 52% | -0.3 | -0.3 |
| OVER 2-5pp | 170 | 48% | 52% | 48% | +3.6 | +0.2 |
| OVER 5-10pp | 142 | 46% | 52% | 45% | +6.6 | -0.5 |
| model OVER by >10pp | 50 | 44% | 54% | 42% | +10.1 | -2.2 |

- Share of the model's lean that showed up in results: leaning UNDER -0.006, leaning OVER 0.067 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1289 | 0.24284 | 0.24823 | +0.00120 | [-0.0007, +0.0032] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 690 | 0.24147 | 0.24658 | +0.00493 | [+0.0003, +0.0096] | MODEL_HURTS |
| OU25 | standard | 599 | 0.24443 | 0.25013 | +0.00329 | [-0.0020, +0.0086] | NO_DETECTABLE_GAIN |
| OU35 | all | 363 | 0.23452 | 0.24859 | +0.06455 | [+0.0088, +0.1319] | MODEL_HURTS |
| OU35 | new_format | 281 | 0.23331 | 0.24855 | +0.00080 | [-0.0006, +0.0024] | NO_DETECTABLE_GAIN |
| BTTS | all | 1284 | 0.24244 | 0.24443 | +0.00848 | [+0.0026, +0.0151] | MODEL_HURTS |
| BTTS | new_format | 694 | 0.24186 | 0.24228 | +0.00939 | [+0.0048, +0.0146] | MODEL_HURTS |
| BTTS | standard | 590 | 0.24311 | 0.24697 | +0.00571 | [-0.0052, +0.0186] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 30; the rest are too small). Pooled prior +3.7%, between-cell sd 0.17. Reality-check p for the best cell: **0.031**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 86 | +33% | +23% | 0.99 | 0.06 | [-5.6, +2.1] | PAPER (n 86 < 150) |
| Brazil Serie A | ou25 | 25 | +47% | +20% | 0.93 | 0.15 | [-6.5, +3.3] | PAPER (n 25 < 150) |
| Sweden Allsvenskan | ou25 | 31 | +24% | +11% | 0.79 | 0.62 | [-4.7, +4.4] | PAPER (n 31 < 150) |
| Serie B | ou25 | 22 | +25% | +11% | 0.77 | 0.62 | [-1.3, +11.8] | PAPER (n 22 < 150) |
| Brazil Serie A | btts | 20 | +24% | +10% | 0.76 | 0.62 | [-21.0, +17.7] | PAPER (n 20 < 150) |
| Argentina Primera Division | ou25 | 33 | +15% | +7% | 0.68 | 0.74 | [-4.2, +5.4] | PAPER (n 33 < 150) |
| Finland Veikkausliiga | ou25 | 19 | +11% | +6% | 0.65 | 0.74 | [-6.6, +7.1] | PAPER (n 19 < 150) |
| Japan J-League | ou25 | 26 | +8% | +5% | 0.65 | 0.74 | [-4.8, +11.7] | PAPER (n 26 < 150) |
| Argentina Primera Division | over15 | 93 | +5% | +4% | 0.68 | 0.74 | [-0.1, +2.7] | PAPER (n 93 < 150) |
| Mexico Liga MX | ou25 | 27 | +3% | +3% | 0.60 | 0.83 | [-0.5, +8.1] | PAPER (n 27 < 150) |
| La Liga 2 | ou25 | 36 | -4% | +1% | 0.53 | 0.98 | [-2.7, +4.2] | PAPER (n 36 < 150) |
| Denmark Superliga | ou25 | 21 | -11% | -1% | 0.47 | 0.98 | [-4.8, +7.1] | PAPER (n 21 < 150) |
| Austrian Bundesliga | ou25 | 19 | -15% | -2% | 0.45 | 0.98 | [-14.3, +5.0] | PAPER (n 19 < 150) |
| Ireland Premier Division | ou25 | 16 | -20% | -3% | 0.42 | 0.98 | [-12.5, +3.4] | PAPER (n 16 < 150) |
| Bundesliga 2 | ou25 | 15 | -35% | -7% | 0.33 | 0.98 | [-13.2, +9.9] | PAPER (n 15 < 150) |
| Championship | ou25 | 24 | -29% | -9% | 0.27 | 0.98 | [-7.8, +5.9] | PAPER (n 24 < 150) |
| China Super League | ou25 | 26 | -33% | -9% | 0.28 | 0.98 | [-10.6, +4.1] | PAPER (n 26 < 150) |
| League One | ou25 | 22 | -46% | -14% | 0.17 | 0.98 | [-8.1, +3.7] | PAPER (n 22 < 150) |
| Norway Eliteserien | ou25 | 21 | -49% | -14% | 0.17 | 0.98 | [-11.9, +6.6] | PAPER (n 21 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 995 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68621 | 0.2467 | – | – | – | – | – |
| v9 | 0.69439 | 0.2506 | 252 | 0.782 | -18.88 | -7% | -3.86 |
| Challenger | 0.6866 | 0.24679 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.287, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

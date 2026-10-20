# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **56%**.
- Tip period, 115 matches with a clean Bet365 price: BTTS happened 58% while the de-vigged price implied 42% (gap 15.8 points).
- **B, blind YES on every match: +28%** [+12%, +45%], n 115.
- A, matches Wowza picked: +36%; matches it did not pick: +20%. Difference +16% [-12%, +42%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.246 vs 0.2837; residual z -0.03 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (105 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1266 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 199 | 60% | 51% | 66% | -9.7 | +5.4 |
| UNDER 5-10pp | 254 | 61% | 52% | 59% | -9.6 | -2.1 |
| UNDER 2-5pp | 174 | 59% | 52% | 55% | -6.7 | -3.3 |
| agrees (±2pp) | 283 | 52% | 52% | 52% | +0.5 | +0.5 |
| OVER 2-5pp | 168 | 48% | 52% | 49% | +3.7 | +0.3 |
| OVER 5-10pp | 138 | 46% | 52% | 45% | +6.0 | -1.1 |
| model OVER by >10pp | 50 | 44% | 54% | 42% | +10.1 | -2.2 |

- Share of the model's lean that showed up in results: leaning UNDER -0.006, leaning OVER 0.096 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1266 | 0.2433 | 0.24849 | +0.00117 | [-0.0009, +0.0032] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 689 | 0.24165 | 0.24675 | +0.00483 | [+0.0003, +0.0097] | MODEL_HURTS |
| OU25 | standard | 577 | 0.24527 | 0.25057 | +0.00351 | [-0.0019, +0.0091] | NO_DETECTABLE_GAIN |
| OU35 | all | 359 | 0.23372 | 0.2471 | +0.04096 | [+0.0003, +0.0936] | MODEL_HURTS |
| OU35 | new_format | 281 | 0.23331 | 0.24855 | +0.00080 | [-0.0006, +0.0024] | NO_DETECTABLE_GAIN |
| BTTS | all | 1261 | 0.24232 | 0.24426 | +0.00741 | [+0.0014, +0.0145] | MODEL_HURTS |
| BTTS | new_format | 693 | 0.24172 | 0.24223 | +0.00753 | [+0.0025, +0.0130] | MODEL_HURTS |
| BTTS | standard | 568 | 0.24305 | 0.24675 | +0.00712 | [-0.0048, +0.0205] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 30; the rest are too small). Pooled prior +3.7%, between-cell sd 0.16. Reality-check p for the best cell: **0.058**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 85 | +32% | +22% | 0.98 | 0.08 | [-5.7, +2.1] | PAPER (n 85 < 150) |
| Brazil Serie A | ou25 | 25 | +47% | +19% | 0.92 | 0.15 | [-6.5, +3.3] | PAPER (n 25 < 150) |
| Sweden Allsvenskan | ou25 | 31 | +24% | +11% | 0.78 | 0.62 | [-4.7, +4.4] | PAPER (n 31 < 150) |
| Serie B | ou25 | 22 | +25% | +10% | 0.77 | 0.62 | [-1.3, +11.8] | PAPER (n 22 < 150) |
| Brazil Serie A | btts | 20 | +24% | +10% | 0.76 | 0.62 | [-21.0, +17.7] | PAPER (n 20 < 150) |
| Argentina Primera Division | ou25 | 33 | +15% | +7% | 0.68 | 0.75 | [-4.2, +5.4] | PAPER (n 33 < 150) |
| Finland Veikkausliiga | ou25 | 19 | +11% | +6% | 0.66 | 0.75 | [-6.6, +7.1] | PAPER (n 19 < 150) |
| Japan J-League | ou25 | 26 | +8% | +5% | 0.65 | 0.75 | [-4.8, +11.7] | PAPER (n 26 < 150) |
| Argentina Primera Division | over15 | 92 | +4% | +4% | 0.67 | 0.75 | [-0.2, +2.7] | PAPER (n 92 < 150) |
| Mexico Liga MX | ou25 | 27 | +3% | +4% | 0.60 | 0.83 | [-0.5, +8.1] | PAPER (n 27 < 150) |
| La Liga 2 | ou25 | 36 | -4% | +2% | 0.54 | 0.98 | [-2.7, +4.2] | PAPER (n 36 < 150) |
| Denmark Superliga | ou25 | 21 | -11% | -0% | 0.49 | 0.98 | [-4.8, +7.1] | PAPER (n 21 < 150) |
| Austrian Bundesliga | ou25 | 19 | -15% | -1% | 0.47 | 0.98 | [-14.3, +5.0] | PAPER (n 19 < 150) |
| Ireland Premier Division | ou25 | 16 | -20% | -2% | 0.44 | 0.98 | [-12.5, +3.4] | PAPER (n 16 < 150) |
| Bundesliga 2 | ou25 | 15 | -35% | -6% | 0.35 | 0.98 | [-13.2, +9.9] | PAPER (n 15 < 150) |
| Championship | ou25 | 24 | -29% | -7% | 0.29 | 0.98 | [-7.8, +5.9] | PAPER (n 24 < 150) |
| China Super League | ou25 | 26 | -33% | -8% | 0.29 | 0.98 | [-10.6, +4.1] | PAPER (n 26 < 150) |
| League One | ou25 | 20 | -41% | -10% | 0.25 | 0.98 | [-7.5, +4.6] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 21 | -49% | -13% | 0.19 | 0.98 | [-11.9, +6.6] | PAPER (n 21 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 972 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68762 | 0.24739 | – | – | – | – | – |
| v9 | 0.69541 | 0.2511 | 249 | 0.783 | -15.88 | -6% | -3.83 |
| Challenger | 0.6877 | 0.24733 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.324, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

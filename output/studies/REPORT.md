# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **55%**.
- Tip period, 141 matches with a clean Bet365 price: BTTS happened 57% while the de-vigged price implied 43% (gap 13.8 points).
- **B, blind YES on every match: +24%** [+8%, +40%], n 141.
- A, matches Wowza picked: +27%; matches it did not pick: +23%. Difference +4% [-22%, +28%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2488 vs 0.2733; residual z -0.15 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (127 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1642 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 320 | 63% | 50% | 65% | -13.2 | +2.1 |
| UNDER 5-10pp | 333 | 62% | 52% | 59% | -9.9 | -2.5 |
| UNDER 2-5pp | 219 | 58% | 52% | 55% | -6.2 | -2.7 |
| agrees (±2pp) | 353 | 52% | 52% | 52% | +0.1 | +0.1 |
| OVER 2-5pp | 202 | 48% | 52% | 48% | +4.3 | +0.8 |
| OVER 5-10pp | 160 | 44% | 52% | 45% | +7.9 | +0.9 |
| model OVER by >10pp | 55 | 44% | 55% | 42% | +10.9 | -1.5 |

- Share of the model's lean that showed up in results: leaning UNDER -0.095, leaning OVER -0.084 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1642 | 0.24152 | 0.24955 | -0.00010 | [-0.0018, +0.0015] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 892 | 0.23845 | 0.2485 | +0.00515 | [+0.0011, +0.0091] | MODEL_HURTS |
| OU25 | standard | 750 | 0.24516 | 0.2508 | +0.00219 | [-0.0019, +0.0065] | NO_DETECTABLE_GAIN |
| OU35 | all | 499 | 0.23366 | 0.24791 | +0.05511 | [+0.0180, +0.1015] | MODEL_HURTS |
| OU35 | new_format | 374 | 0.23477 | 0.25416 | +0.03968 | [+0.0098, +0.0764] | MODEL_HURTS |
| OU35 | standard | 125 | 0.23034 | 0.22921 | -0.01222 | [-0.0314, +0.0113] | NO_DETECTABLE_GAIN |
| BTTS | all | 1642 | 0.24101 | 0.24421 | +0.00834 | [+0.0032, +0.0140] | MODEL_HURTS |
| BTTS | new_format | 901 | 0.23961 | 0.24248 | +0.00165 | [-0.0002, +0.0036] | NO_DETECTABLE_GAIN |
| BTTS | standard | 741 | 0.24272 | 0.24631 | +0.03246 | [+0.0108, +0.0561] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 39; the rest are too small). Pooled prior -0.1%, between-cell sd 0.10. Reality-check p for the best cell: **0.212**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 95 | +25% | +11% | 0.91 | 0.27 | [-4.9, +2.1] | PAPER (n 95 < 150) |
| Brazil Serie A | ou25 | 31 | +39% | +8% | 0.80 | 0.27 | [-8.6, +2.3] | PAPER (CLV deterioration alarm) |
| Brazil Serie A | btts | 21 | +28% | +4% | 0.66 | 0.90 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Serie B | ou25 | 23 | +19% | +3% | 0.62 | 0.97 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Argentina Primera Division | over15 | 103 | +5% | +3% | 0.62 | 0.97 | [+0.2, +2.8] | PAPER (n 103 < 150) |
| Sweden Allsvenskan | ou25 | 44 | +9% | +2% | 0.58 | 0.97 | [-4.4, +2.5] | PAPER (n 44 < 150) |
| Argentina Primera Division | ou25 | 34 | +11% | +2% | 0.56 | 0.97 | [-4.0, +5.3] | PAPER (n 34 < 150) |
| Finland Veikkausliiga | ou25 | 24 | +5% | +1% | 0.53 | 0.97 | [-5.1, +5.1] | PAPER (n 24 < 150) |
| Japan J-League | ou25 | 34 | +3% | +1% | 0.52 | 0.97 | [-3.3, +8.2] | PAPER (n 34 < 150) |
| League Two | ou25 | 19 | +5% | +0% | 0.51 | 0.97 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| La Liga 2 | ou25 | 38 | -4% | -1% | 0.47 | 0.97 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Mexico Liga MX | ou25 | 43 | -3% | -1% | 0.47 | 0.97 | [-1.6, +6.8] | PAPER (CLV deterioration alarm) |
| Japan J-League | btts | 10 | -18% | -2% | 0.44 | 0.97 | – | PAPER (n 10 < 150) |
| Denmark Superliga | ou25 | 31 | -8% | -2% | 0.44 | 0.97 | [-4.1, +5.4] | PAPER (n 31 < 150) |
| La Liga 2 | btts | 10 | -22% | -2% | 0.43 | 0.97 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Bundesliga 2 | ou25 | 20 | -24% | -3% | 0.38 | 0.97 | [-9.1, +9.3] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 27 | -26% | -4% | 0.37 | 0.97 | [-10.0, +4.1] | PAPER (n 27 < 150) |
| China Super League | ou25 | 32 | -24% | -5% | 0.32 | 0.97 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Ireland Premier Division | ou25 | 24 | -30% | -5% | 0.30 | 0.97 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -6% | 0.29 | 0.97 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| League One | ou25 | 25 | -42% | -8% | 0.23 | 0.97 | [-7.0, +3.1] | PAPER (n 25 < 150) |
| Championship | ou25 | 28 | -40% | -8% | 0.21 | 0.97 | [-6.8, +4.9] | PAPER (n 28 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1348 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68122 | 0.24415 | – | – | – | – | – |
| v9 | 0.69668 | 0.25172 | 397 | 0.829 | -52.1 | -13% | -4.01 |
| Challenger | 0.68194 | 0.24447 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.478, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

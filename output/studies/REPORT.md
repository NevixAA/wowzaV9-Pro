# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **54%**.
- Tip period, 137 matches with a clean Bet365 price: BTTS happened 56% while the de-vigged price implied 43% (gap 13.4 points).
- **B, blind YES on every match: +23%** [+8%, +39%], n 137.
- A, matches Wowza picked: +25%; matches it did not pick: +22%. Difference +3% [-24%, +28%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2485 vs 0.2733; residual z -0.07 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (124 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1598 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 303 | 62% | 50% | 65% | -12.7 | +2.5 |
| UNDER 5-10pp | 327 | 62% | 52% | 59% | -10.2 | -2.8 |
| UNDER 2-5pp | 213 | 58% | 52% | 55% | -6.0 | -2.5 |
| agrees (±2pp) | 348 | 52% | 52% | 52% | +0.0 | +0.0 |
| OVER 2-5pp | 197 | 48% | 52% | 48% | +4.0 | +0.6 |
| OVER 5-10pp | 157 | 44% | 52% | 45% | +8.4 | +1.3 |
| model OVER by >10pp | 53 | 43% | 54% | 42% | +10.7 | -1.8 |

- Share of the model's lean that showed up in results: leaning UNDER -0.088, leaning OVER -0.092 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1598 | 0.24183 | 0.24943 | +0.00021 | [-0.0018, +0.0021] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 860 | 0.23893 | 0.24832 | +0.00543 | [+0.0012, +0.0097] | MODEL_HURTS |
| OU25 | standard | 738 | 0.24522 | 0.25072 | +0.00237 | [-0.0019, +0.0068] | NO_DETECTABLE_GAIN |
| OU35 | all | 468 | 0.23265 | 0.24601 | +0.04759 | [+0.0113, +0.0929] | MODEL_HURTS |
| OU35 | new_format | 349 | 0.23321 | 0.25162 | +0.03326 | [+0.0059, +0.0656] | MODEL_HURTS |
| OU35 | standard | 119 | 0.23099 | 0.22957 | -0.00421 | [-0.0273, +0.0219] | NO_DETECTABLE_GAIN |
| BTTS | all | 1598 | 0.24108 | 0.24419 | +0.00867 | [+0.0033, +0.0141] | MODEL_HURTS |
| BTTS | new_format | 869 | 0.23965 | 0.24247 | +0.00155 | [-0.0003, +0.0035] | NO_DETECTABLE_GAIN |
| BTTS | standard | 729 | 0.24279 | 0.24625 | +0.01503 | [+0.0016, +0.0296] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 39; the rest are too small). Pooled prior -0.1%, between-cell sd 0.11. Reality-check p for the best cell: **0.314**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 94 | +24% | +10% | 0.89 | 0.27 | [-5.1, +1.9] | PAPER (n 94 < 150) |
| Brazil Serie A | ou25 | 31 | +39% | +9% | 0.80 | 0.27 | [-8.6, +2.3] | PAPER (CLV deterioration alarm) |
| Brazil Serie A | btts | 21 | +28% | +4% | 0.66 | 0.90 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Sweden Allsvenskan | ou25 | 41 | +17% | +4% | 0.65 | 0.90 | [-4.4, +2.7] | PAPER (n 41 < 150) |
| Serie B | ou25 | 23 | +19% | +3% | 0.62 | 0.90 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Argentina Primera Division | over15 | 102 | +5% | +2% | 0.61 | 0.97 | [+0.1, +2.8] | PAPER (n 102 < 150) |
| Argentina Primera Division | ou25 | 34 | +11% | +2% | 0.56 | 0.97 | [-4.0, +5.3] | PAPER (n 34 < 150) |
| Japan J-League | ou25 | 33 | +6% | +1% | 0.55 | 0.97 | [-3.4, +8.5] | PAPER (n 33 < 150) |
| Finland Veikkausliiga | ou25 | 24 | +5% | +1% | 0.53 | 0.97 | [-5.1, +5.1] | PAPER (n 24 < 150) |
| League Two | ou25 | 19 | +5% | +0% | 0.51 | 0.97 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| Mexico Liga MX | ou25 | 40 | -2% | -1% | 0.47 | 0.97 | [-2.1, +7.1] | PAPER (CLV deterioration alarm) |
| La Liga 2 | ou25 | 38 | -4% | -1% | 0.47 | 0.97 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Japan J-League | btts | 10 | -18% | -2% | 0.44 | 0.97 | – | PAPER (n 10 < 150) |
| La Liga 2 | btts | 10 | -22% | -2% | 0.43 | 0.97 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Denmark Superliga | ou25 | 27 | -12% | -2% | 0.42 | 0.97 | [-4.9, +5.2] | PAPER (n 27 < 150) |
| Bundesliga 2 | ou25 | 19 | -20% | -3% | 0.41 | 0.97 | [-10.0, +8.6] | PAPER (n 19 < 150) |
| Norway Eliteserien | ou25 | 26 | -32% | -4% | 0.34 | 0.97 | [-10.5, +4.3] | PAPER (n 26 < 150) |
| China Super League | ou25 | 32 | -24% | -5% | 0.31 | 0.97 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Ireland Premier Division | ou25 | 24 | -30% | -6% | 0.30 | 0.97 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -6% | 0.29 | 0.97 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| League One | ou25 | 25 | -42% | -8% | 0.22 | 0.97 | [-7.0, +3.1] | PAPER (n 25 < 150) |
| Championship | ou25 | 28 | -40% | -8% | 0.21 | 0.97 | [-6.8, +4.9] | PAPER (n 28 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1304 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68226 | 0.24466 | – | – | – | – | – |
| v9 | 0.69669 | 0.25173 | 376 | 0.822 | -45.61 | -12% | -4.02 |
| Challenger | 0.68291 | 0.24494 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.451, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

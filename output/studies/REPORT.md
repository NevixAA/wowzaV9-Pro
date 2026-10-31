# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **54%**.
- Tip period, 134 matches with a clean Bet365 price: BTTS happened 56% while the de-vigged price implied 43% (gap 13.2 points).
- **B, blind YES on every match: +23%** [+7%, +39%], n 134.
- A, matches Wowza picked: +25%; matches it did not pick: +21%. Difference +4% [-23%, +29%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2486 vs 0.2735; residual z -0.14 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (121 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1532 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 287 | 62% | 50% | 65% | -12.4 | +2.9 |
| UNDER 5-10pp | 307 | 62% | 52% | 59% | -10.3 | -2.8 |
| UNDER 2-5pp | 201 | 58% | 52% | 55% | -5.8 | -2.4 |
| agrees (±2pp) | 338 | 51% | 52% | 52% | +0.6 | +0.6 |
| OVER 2-5pp | 190 | 47% | 52% | 48% | +5.0 | +1.5 |
| OVER 5-10pp | 156 | 44% | 52% | 45% | +8.2 | +1.1 |
| model OVER by >10pp | 53 | 43% | 54% | 42% | +10.7 | -1.8 |

- Share of the model's lean that showed up in results: leaning UNDER -0.071, leaning OVER -0.148 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1532 | 0.2415 | 0.24879 | +0.00104 | [-0.0011, +0.0031] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 837 | 0.23869 | 0.24742 | +0.00551 | [+0.0013, +0.0098] | MODEL_HURTS |
| OU25 | standard | 695 | 0.24489 | 0.25044 | +0.00867 | [+0.0011, +0.0170] | MODEL_HURTS |
| OU35 | all | 448 | 0.23317 | 0.24792 | +0.05040 | [+0.0124, +0.0998] | MODEL_HURTS |
| OU35 | new_format | 341 | 0.23325 | 0.25208 | +0.04445 | [+0.0102, +0.0894] | MODEL_HURTS |
| OU35 | standard | 107 | 0.2329 | 0.23465 | -0.00718 | [-0.0296, +0.0186] | NO_DETECTABLE_GAIN |
| BTTS | all | 1531 | 0.24056 | 0.24388 | +0.00929 | [+0.0039, +0.0148] | MODEL_HURTS |
| BTTS | new_format | 845 | 0.2387 | 0.24186 | +0.00225 | [+0.0002, +0.0044] | MODEL_HURTS |
| BTTS | standard | 686 | 0.24286 | 0.24637 | +0.01624 | [+0.0016, +0.0319] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

21 cells tested (of 39; the rest are too small). Pooled prior +0.7%, between-cell sd 0.11. Reality-check p for the best cell: **0.226**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 94 | +24% | +11% | 0.90 | 0.26 | [-5.1, +1.9] | PAPER (n 94 < 150) |
| Brazil Serie A | ou25 | 31 | +39% | +9% | 0.82 | 0.26 | [-8.6, +2.3] | PAPER (CLV deterioration alarm) |
| Brazil Serie A | btts | 21 | +28% | +5% | 0.69 | 0.85 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Sweden Allsvenskan | ou25 | 41 | +17% | +5% | 0.67 | 0.85 | [-4.4, +2.7] | PAPER (n 41 < 150) |
| Serie B | ou25 | 23 | +19% | +4% | 0.65 | 0.85 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Japan J-League | ou25 | 32 | +9% | +3% | 0.60 | 0.91 | [-3.5, +8.9] | PAPER (n 32 < 150) |
| Argentina Primera Division | over15 | 101 | +4% | +2% | 0.62 | 0.91 | [+0.1, +2.8] | PAPER (n 101 < 150) |
| Argentina Primera Division | ou25 | 34 | +11% | +2% | 0.59 | 0.91 | [-4.0, +5.3] | PAPER (n 34 < 150) |
| Finland Veikkausliiga | ou25 | 24 | +5% | +1% | 0.55 | 0.93 | [-5.1, +5.1] | PAPER (n 24 < 150) |
| Mexico Liga MX | ou25 | 38 | +3% | +1% | 0.55 | 0.93 | [-2.5, +6.8] | PAPER (CLV deterioration alarm) |
| La Liga 2 | ou25 | 38 | -4% | -0% | 0.50 | 0.98 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Japan J-League | btts | 10 | -18% | -1% | 0.47 | 0.98 | – | PAPER (n 10 < 150) |
| La Liga 2 | btts | 10 | -22% | -1% | 0.46 | 0.98 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Denmark Superliga | ou25 | 27 | -12% | -2% | 0.44 | 0.98 | [-4.9, +5.2] | PAPER (n 27 < 150) |
| Bundesliga 2 | ou25 | 19 | -20% | -2% | 0.43 | 0.98 | [-10.0, +8.6] | PAPER (n 19 < 150) |
| Norway Eliteserien | ou25 | 26 | -32% | -4% | 0.36 | 0.98 | [-10.5, +4.3] | PAPER (n 26 < 150) |
| Austrian Bundesliga | ou25 | 23 | -30% | -4% | 0.34 | 0.98 | [-13.1, +2.5] | PAPER (n 23 < 150) |
| China Super League | ou25 | 32 | -24% | -4% | 0.34 | 0.98 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Ireland Premier Division | ou25 | 24 | -30% | -5% | 0.32 | 0.98 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Championship | ou25 | 25 | -32% | -6% | 0.29 | 0.98 | [-7.8, +5.4] | PAPER (n 25 < 150) |
| League One | ou25 | 23 | -49% | -8% | 0.22 | 0.98 | [-7.7, +3.5] | PAPER (n 23 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1238 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68101 | 0.24409 | – | – | – | – | – |
| v9 | 0.69563 | 0.25121 | 355 | 0.811 | -45.52 | -13% | -4.03 |
| Challenger | 0.68228 | 0.24465 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.4, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

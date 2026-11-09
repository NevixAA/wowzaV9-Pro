# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 48%, since 10 Aug **55%**.
- Tip period, 164 matches with a clean Bet365 price: BTTS happened 55% while the de-vigged price implied 43% (gap 12.3 points).
- **B, blind YES on every match: +21%** [+6%, +36%], n 164.
- A, matches Wowza picked: +26%; matches it did not pick: +17%. Difference +9% [-15%, +30%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.25 vs 0.2716; residual z -0.46 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (150 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1803 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 351 | 64% | 50% | 65% | -13.6 | +1.6 |
| UNDER 5-10pp | 358 | 61% | 52% | 59% | -9.4 | -1.9 |
| UNDER 2-5pp | 244 | 57% | 52% | 55% | -5.5 | -2.1 |
| agrees (±2pp) | 389 | 52% | 52% | 52% | +0.3 | +0.3 |
| OVER 2-5pp | 220 | 46% | 52% | 48% | +5.4 | +1.9 |
| OVER 5-10pp | 177 | 46% | 53% | 46% | +7.0 | -0.1 |
| model OVER by >10pp | 64 | 44% | 55% | 42% | +10.9 | -1.6 |

- Share of the model's lean that showed up in results: leaning UNDER -0.073, leaning OVER -0.112 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1803 | 0.24099 | 0.249 | +0.00056 | [-0.0010, +0.0022] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 991 | 0.23706 | 0.24767 | +0.00413 | [+0.0004, +0.0081] | MODEL_HURTS |
| OU25 | standard | 812 | 0.24579 | 0.25063 | +0.00286 | [-0.0017, +0.0080] | NO_DETECTABLE_GAIN |
| OU15 | all | 220 | 0.19693 | 0.19735 | +0.00332 | [-0.0093, +0.0131] | NO_DETECTABLE_GAIN |
| OU15 | new_format | 147 | 0.19337 | 0.19494 | +0.00186 | [-0.0040, +0.0095] | NO_DETECTABLE_GAIN |
| OU35 | all | 640 | 0.22745 | 0.24003 | +0.07852 | [+0.0321, +0.1366] | MODEL_HURTS |
| OU35 | new_format | 453 | 0.2284 | 0.24626 | +0.04634 | [+0.0185, +0.0807] | MODEL_HURTS |
| OU35 | standard | 187 | 0.22516 | 0.22492 | -0.00756 | [-0.0219, +0.0089] | NO_DETECTABLE_GAIN |
| BTTS | all | 1805 | 0.24159 | 0.24461 | +0.00096 | [-0.0006, +0.0027] | NO_DETECTABLE_GAIN |
| BTTS | new_format | 1002 | 0.2398 | 0.24281 | +0.00184 | [-0.0005, +0.0043] | NO_DETECTABLE_GAIN |
| BTTS | standard | 803 | 0.24383 | 0.24686 | +0.00118 | [-0.0037, +0.0067] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 40; the rest are too small). Pooled prior -2.5%, between-cell sd 0.00. Reality-check p for the best cell: **0.414**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 102 | +21% | -3% | 0.28 | 0.84 | [-4.7, +1.8] | PAPER (n 102 < 150) |
| Argentina Primera Division | ou25 | 35 | +14% | -3% | 0.28 | 0.97 | [-3.8, +5.1] | PAPER (n 35 < 150) |
| Argentina Primera Division | over15 | 105 | +6% | -3% | 0.28 | 0.97 | [+0.2, +2.8] | PAPER (n 105 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -3% | 0.28 | 0.97 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| Brazil Serie A | btts | 21 | +28% | -3% | 0.28 | 0.97 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Brazil Serie A | ou25 | 37 | +16% | -3% | 0.28 | 0.97 | [-8.1, +2.0] | PAPER (CLV deterioration alarm) |
| Bundesliga 2 | ou25 | 20 | -24% | -3% | 0.28 | 0.97 | [-9.1, +9.3] | PAPER (n 20 < 150) |
| Championship | ou25 | 31 | -29% | -3% | 0.28 | 0.97 | [-6.0, +4.9] | PAPER (n 31 < 150) |
| China Super League | ou25 | 33 | -18% | -3% | 0.28 | 0.97 | [-9.1, +2.3] | PAPER (n 33 < 150) |
| Denmark Superliga | ou25 | 33 | -14% | -3% | 0.28 | 0.97 | [-3.8, +5.4] | PAPER (n 33 < 150) |
| Finland Veikkausliiga | ou25 | 28 | -10% | -3% | 0.28 | 0.97 | [-22.3, +33.9] | PAPER (CLV deterioration alarm) |
| Ireland Premier Division | ou25 | 24 | -30% | -3% | 0.28 | 0.97 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Japan J-League | btts | 11 | -25% | -3% | 0.28 | 0.97 | – | PAPER (n 11 < 150) |
| Japan J-League | ou25 | 36 | -3% | -3% | 0.28 | 0.97 | [-3.1, +7.5] | PAPER (n 36 < 150) |
| La Liga 2 | btts | 10 | -22% | -3% | 0.28 | 0.97 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| La Liga 2 | ou25 | 39 | -7% | -3% | 0.28 | 0.97 | [-2.3, +3.9] | PAPER (n 39 < 150) |
| League One | ou25 | 25 | -42% | -3% | 0.28 | 0.97 | [-7.0, +3.1] | PAPER (n 25 < 150) |
| League Two | ou25 | 19 | +5% | -3% | 0.28 | 0.97 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| Mexico Liga MX | ou25 | 46 | +1% | -3% | 0.28 | 0.97 | [-1.1, +6.8] | PAPER (CLV deterioration alarm) |
| Norway Eliteserien | ou25 | 27 | -26% | -3% | 0.28 | 0.97 | [-10.0, +4.1] | PAPER (n 27 < 150) |
| Serie B | ou25 | 23 | +19% | -3% | 0.28 | 0.97 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Sweden Allsvenskan | ou25 | 50 | +6% | -3% | 0.28 | 0.97 | [-3.9, +2.3] | PAPER (n 50 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1510 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.67994 | 0.24354 | – | – | – | – | – |
| v9 | 0.69508 | 0.25094 | 453 | 0.841 | -53.92 | -12% | -3.95 |
| Challenger | 0.68074 | 0.24389 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.415, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

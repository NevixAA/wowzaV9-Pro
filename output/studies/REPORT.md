# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 48%, since 10 Aug **54%**.
- Tip period, 163 matches with a clean Bet365 price: BTTS happened 55% while the de-vigged price implied 43% (gap 12.0 points).
- **B, blind YES on every match: +20%** [+6%, +36%], n 163.
- A, matches Wowza picked: +24%; matches it did not pick: +17%. Difference +8% [-15%, +29%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2497 vs 0.2715; residual z -0.35 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (149 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1753 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 335 | 63% | 50% | 65% | -13.2 | +2.0 |
| UNDER 5-10pp | 353 | 61% | 52% | 59% | -9.5 | -2.0 |
| UNDER 2-5pp | 239 | 58% | 52% | 55% | -5.9 | -2.5 |
| agrees (±2pp) | 380 | 52% | 52% | 52% | +0.1 | +0.1 |
| OVER 2-5pp | 215 | 47% | 52% | 48% | +5.2 | +1.8 |
| OVER 5-10pp | 171 | 46% | 53% | 45% | +7.0 | -0.1 |
| model OVER by >10pp | 60 | 43% | 55% | 42% | +11.2 | -1.3 |

- Share of the model's lean that showed up in results: leaning UNDER -0.075, leaning OVER -0.104 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1753 | 0.24155 | 0.24943 | +0.00049 | [-0.0011, +0.0022] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 949 | 0.23769 | 0.24832 | +0.00337 | [+0.0002, +0.0068] | MODEL_HURTS |
| OU25 | standard | 804 | 0.2461 | 0.25074 | +0.00279 | [-0.0016, +0.0079] | NO_DETECTABLE_GAIN |
| OU15 | all | 195 | 0.19943 | 0.19961 | +0.00319 | [-0.0081, +0.0107] | NO_DETECTABLE_GAIN |
| OU15 | new_format | 130 | 0.19588 | 0.19729 | +0.00143 | [+0.0006, +0.0022] | MODEL_HURTS |
| OU35 | all | 605 | 0.22738 | 0.23972 | +0.08448 | [+0.0348, +0.1444] | MODEL_HURTS |
| OU35 | new_format | 426 | 0.22856 | 0.247 | +0.05014 | [+0.0207, +0.0868] | MODEL_HURTS |
| OU35 | standard | 179 | 0.22459 | 0.22241 | -0.00645 | [-0.0223, +0.0128] | NO_DETECTABLE_GAIN |
| BTTS | all | 1754 | 0.24186 | 0.24463 | +0.00105 | [-0.0006, +0.0028] | NO_DETECTABLE_GAIN |
| BTTS | new_format | 959 | 0.23997 | 0.24274 | +0.00191 | [-0.0005, +0.0045] | NO_DETECTABLE_GAIN |
| BTTS | standard | 795 | 0.24415 | 0.24692 | +0.03249 | [+0.0119, +0.0553] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 40; the rest are too small). Pooled prior -2.5%, between-cell sd 0.00. Reality-check p for the best cell: **0.552**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 101 | +20% | -2% | 0.29 | 0.97 | [-4.7, +1.9] | PAPER (n 101 < 150) |
| Argentina Primera Division | ou25 | 35 | +14% | -2% | 0.29 | 0.97 | [-3.8, +5.1] | PAPER (n 35 < 150) |
| Argentina Primera Division | over15 | 104 | +6% | -2% | 0.29 | 0.97 | [+0.2, +2.8] | PAPER (n 104 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -2% | 0.29 | 0.97 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| Brazil Serie A | btts | 21 | +28% | -2% | 0.29 | 0.97 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Brazil Serie A | ou25 | 37 | +16% | -2% | 0.29 | 0.97 | [-8.1, +2.0] | PAPER (CLV deterioration alarm) |
| Bundesliga 2 | ou25 | 20 | -24% | -2% | 0.29 | 0.97 | [-9.1, +9.3] | PAPER (n 20 < 150) |
| Championship | ou25 | 31 | -29% | -2% | 0.29 | 0.97 | [-6.0, +4.9] | PAPER (n 31 < 150) |
| China Super League | ou25 | 32 | -24% | -2% | 0.29 | 0.97 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Denmark Superliga | ou25 | 32 | -11% | -2% | 0.29 | 0.97 | [-4.2, +5.1] | PAPER (n 32 < 150) |
| Finland Veikkausliiga | ou25 | 26 | -3% | -2% | 0.29 | 0.97 | [-7.2, +4.5] | PAPER (CLV deterioration alarm) |
| Ireland Premier Division | ou25 | 24 | -30% | -2% | 0.29 | 0.97 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Japan J-League | btts | 11 | -25% | -2% | 0.29 | 0.97 | – | PAPER (n 11 < 150) |
| Japan J-League | ou25 | 35 | -0% | -2% | 0.29 | 0.97 | [-3.1, +7.9] | PAPER (n 35 < 150) |
| La Liga 2 | btts | 10 | -22% | -2% | 0.29 | 0.97 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| La Liga 2 | ou25 | 39 | -7% | -2% | 0.29 | 0.97 | [-2.3, +3.9] | PAPER (n 39 < 150) |
| League One | ou25 | 25 | -42% | -2% | 0.29 | 0.97 | [-7.0, +3.1] | PAPER (n 25 < 150) |
| League Two | ou25 | 19 | +5% | -2% | 0.29 | 0.97 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| Mexico Liga MX | ou25 | 45 | +3% | -2% | 0.29 | 0.97 | [-1.3, +6.8] | PAPER (CLV deterioration alarm) |
| Norway Eliteserien | ou25 | 27 | -26% | -2% | 0.29 | 0.97 | [-10.0, +4.1] | PAPER (n 27 < 150) |
| Serie B | ou25 | 23 | +19% | -2% | 0.29 | 0.97 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Sweden Allsvenskan | ou25 | 47 | +8% | -2% | 0.29 | 0.97 | [-4.1, +2.4] | PAPER (n 47 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1465 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68136 | 0.24423 | – | – | – | – | – |
| v9 | 0.69593 | 0.25135 | 435 | 0.837 | -52.42 | -12% | -3.96 |
| Challenger | 0.68207 | 0.24454 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.423, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

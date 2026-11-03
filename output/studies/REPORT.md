# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 48%, since 10 Aug **55%**.
- Tip period, 145 matches with a clean Bet365 price: BTTS happened 57% while the de-vigged price implied 43% (gap 14.2 points).
- **B, blind YES on every match: +25%** [+10%, +41%], n 145.
- A, matches Wowza picked: +27%; matches it did not pick: +24%. Difference +2% [-22%, +27%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2491 vs 0.2724; residual z -0.25 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (131 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1658 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 321 | 63% | 50% | 65% | -13.3 | +1.9 |
| UNDER 5-10pp | 335 | 62% | 52% | 59% | -10.1 | -2.7 |
| UNDER 2-5pp | 220 | 58% | 52% | 55% | -6.3 | -2.8 |
| agrees (±2pp) | 361 | 52% | 52% | 52% | -0.1 | -0.1 |
| OVER 2-5pp | 204 | 47% | 52% | 48% | +4.8 | +1.3 |
| OVER 5-10pp | 161 | 45% | 52% | 45% | +7.7 | +0.6 |
| model OVER by >10pp | 56 | 45% | 55% | 42% | +9.9 | -2.4 |

- Share of the model's lean that showed up in results: leaning UNDER -0.111, leaning OVER -0.089 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1658 | 0.24118 | 0.24924 | -0.00006 | [-0.0017, +0.0015] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 903 | 0.23771 | 0.24797 | +0.00298 | [-0.0004, +0.0063] | NO_DETECTABLE_GAIN |
| OU25 | standard | 755 | 0.24533 | 0.25076 | +0.00213 | [-0.0019, +0.0063] | NO_DETECTABLE_GAIN |
| OU15 | all | 112 | 0.19872 | 0.2027 | -0.00303 | [-0.0134, +0.0068] | NO_DETECTABLE_GAIN |
| OU35 | all | 515 | 0.23427 | 0.2483 | +0.07050 | [+0.0264, +0.1225] | MODEL_HURTS |
| OU35 | new_format | 385 | 0.2337 | 0.25326 | +0.03835 | [+0.0099, +0.0734] | MODEL_HURTS |
| OU35 | standard | 130 | 0.23596 | 0.23361 | +0.00120 | [-0.0247, +0.0337] | NO_DETECTABLE_GAIN |
| BTTS | all | 1658 | 0.24081 | 0.24403 | +0.00912 | [+0.0040, +0.0146] | MODEL_HURTS |
| BTTS | new_format | 912 | 0.23921 | 0.24224 | +0.00156 | [-0.0002, +0.0036] | NO_DETECTABLE_GAIN |
| BTTS | standard | 746 | 0.24277 | 0.2462 | +0.03515 | [+0.0135, +0.0597] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 39; the rest are too small). Pooled prior -0.6%, between-cell sd 0.10. Reality-check p for the best cell: **0.232**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 95 | +25% | +11% | 0.90 | 0.27 | [-4.9, +2.1] | PAPER (n 95 < 150) |
| Brazil Serie A | ou25 | 31 | +39% | +8% | 0.78 | 0.27 | [-8.6, +2.3] | PAPER (CLV deterioration alarm) |
| Brazil Serie A | btts | 21 | +28% | +4% | 0.64 | 0.91 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Serie B | ou25 | 23 | +19% | +3% | 0.60 | 0.97 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Argentina Primera Division | over15 | 103 | +5% | +2% | 0.61 | 0.97 | [+0.2, +2.8] | PAPER (n 103 < 150) |
| Argentina Primera Division | ou25 | 34 | +11% | +1% | 0.54 | 0.97 | [-4.0, +5.3] | PAPER (n 34 < 150) |
| Sweden Allsvenskan | ou25 | 45 | +6% | +1% | 0.54 | 0.97 | [-4.3, +2.3] | PAPER (n 45 < 150) |
| Japan J-League | ou25 | 34 | +3% | +0% | 0.51 | 0.97 | [-3.3, +8.2] | PAPER (n 34 < 150) |
| League Two | ou25 | 19 | +5% | -0% | 0.49 | 0.97 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| Finland Veikkausliiga | ou25 | 26 | -3% | -1% | 0.46 | 0.97 | [-7.2, +4.5] | PAPER (CLV deterioration alarm) |
| La Liga 2 | ou25 | 38 | -4% | -1% | 0.46 | 0.97 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Mexico Liga MX | ou25 | 43 | -3% | -1% | 0.45 | 0.97 | [-1.6, +6.8] | PAPER (CLV deterioration alarm) |
| Japan J-League | btts | 10 | -18% | -2% | 0.43 | 0.97 | – | PAPER (n 10 < 150) |
| Denmark Superliga | ou25 | 31 | -8% | -2% | 0.42 | 0.97 | [-4.1, +5.4] | PAPER (n 31 < 150) |
| La Liga 2 | btts | 10 | -22% | -2% | 0.42 | 0.97 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Bundesliga 2 | ou25 | 20 | -24% | -3% | 0.37 | 0.97 | [-9.1, +9.3] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 27 | -26% | -4% | 0.36 | 0.97 | [-10.0, +4.1] | PAPER (n 27 < 150) |
| China Super League | ou25 | 32 | -24% | -5% | 0.31 | 0.97 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Ireland Premier Division | ou25 | 24 | -30% | -6% | 0.29 | 0.97 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -6% | 0.28 | 0.97 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| League One | ou25 | 25 | -42% | -8% | 0.22 | 0.97 | [-7.0, +3.1] | PAPER (n 25 < 150) |
| Championship | ou25 | 28 | -40% | -8% | 0.21 | 0.97 | [-6.8, +4.9] | PAPER (n 28 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1364 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68049 | 0.2438 | – | – | – | – | – |
| v9 | 0.69624 | 0.25151 | 403 | 0.831 | -55.42 | -14% | -4.02 |
| Challenger | 0.68124 | 0.24413 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.462, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

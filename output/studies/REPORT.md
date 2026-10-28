# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **54%**.
- Tip period, 130 matches with a clean Bet365 price: BTTS happened 55% while the de-vigged price implied 43% (gap 12.7 points).
- **B, blind YES on every match: +21%** [+6%, +38%], n 130.
- A, matches Wowza picked: +27%; matches it did not pick: +16%. Difference +10% [-16%, +35%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2485 vs 0.2754; residual z -0.11 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (118 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1481 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 262 | 61% | 50% | 65% | -11.0 | +4.1 |
| UNDER 5-10pp | 297 | 62% | 52% | 59% | -10.3 | -2.9 |
| UNDER 2-5pp | 195 | 58% | 52% | 55% | -6.0 | -2.6 |
| agrees (±2pp) | 332 | 51% | 52% | 52% | +0.8 | +0.9 |
| OVER 2-5pp | 186 | 47% | 52% | 48% | +4.5 | +1.0 |
| OVER 5-10pp | 156 | 44% | 52% | 45% | +8.2 | +1.1 |
| model OVER by >10pp | 53 | 43% | 54% | 42% | +10.7 | -1.8 |

- Share of the model's lean that showed up in results: leaning UNDER -0.043, leaning OVER -0.11 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1481 | 0.24212 | 0.24845 | +0.00188 | [+0.0000, +0.0037] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 798 | 0.23962 | 0.24654 | +0.01048 | [+0.0055, +0.0159] | MODEL_HURTS |
| OU25 | standard | 683 | 0.24503 | 0.25069 | +0.00600 | [-0.0006, +0.0132] | NO_DETECTABLE_GAIN |
| OU35 | all | 425 | 0.23421 | 0.24715 | +0.05459 | [+0.0144, +0.1072] | MODEL_HURTS |
| OU35 | new_format | 321 | 0.23473 | 0.25077 | +0.04687 | [+0.0094, +0.0945] | MODEL_HURTS |
| OU35 | standard | 104 | 0.23261 | 0.23598 | -0.01669 | [-0.0370, -0.0026] | MODEL_ADDS_INFORMATION |
| BTTS | all | 1479 | 0.24115 | 0.24416 | +0.00988 | [+0.0045, +0.0156] | MODEL_HURTS |
| BTTS | new_format | 805 | 0.23954 | 0.24197 | +0.00591 | [+0.0023, +0.0097] | MODEL_HURTS |
| BTTS | standard | 674 | 0.24307 | 0.24679 | +0.01541 | [+0.0003, +0.0312] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

21 cells tested (of 39; the rest are too small). Pooled prior +1.8%, between-cell sd 0.12. Reality-check p for the best cell: **0.091**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 93 | +25% | +13% | 0.94 | 0.17 | [-5.2, +1.9] | PAPER (n 93 < 150) |
| Brazil Serie A | ou25 | 29 | +48% | +13% | 0.89 | 0.17 | [-7.1, +2.4] | PAPER (n 29 < 150) |
| Brazil Serie A | btts | 21 | +28% | +7% | 0.72 | 0.87 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Serie B | ou25 | 23 | +19% | +5% | 0.68 | 0.92 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Sweden Allsvenskan | ou25 | 37 | +16% | +5% | 0.69 | 0.92 | [-4.7, +3.1] | PAPER (n 37 < 150) |
| Argentina Primera Division | ou25 | 33 | +15% | +4% | 0.64 | 0.93 | [-4.2, +5.4] | PAPER (n 33 < 150) |
| Japan J-League | ou25 | 32 | +9% | +4% | 0.64 | 0.93 | [-3.5, +8.9] | PAPER (n 32 < 150) |
| Argentina Primera Division | over15 | 100 | +4% | +3% | 0.63 | 0.93 | [+0.1, +2.8] | PAPER (n 100 < 150) |
| Finland Veikkausliiga | ou25 | 22 | +4% | +2% | 0.58 | 0.93 | [-5.7, +5.8] | PAPER (n 22 < 150) |
| Mexico Liga MX | ou25 | 38 | +3% | +2% | 0.57 | 0.93 | [-2.5, +6.8] | PAPER (CLV deterioration alarm) |
| La Liga 2 | ou25 | 38 | -4% | +1% | 0.52 | 0.98 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Denmark Superliga | ou25 | 26 | -8% | -0% | 0.49 | 0.98 | [-5.2, +5.4] | PAPER (n 26 < 150) |
| Japan J-League | btts | 10 | -18% | -0% | 0.49 | 0.98 | – | PAPER (n 10 < 150) |
| La Liga 2 | btts | 10 | -22% | -0% | 0.48 | 0.98 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Bundesliga 2 | ou25 | 18 | -15% | -1% | 0.48 | 0.98 | [-10.9, +8.8] | PAPER (n 18 < 150) |
| Ireland Premier Division | ou25 | 20 | -25% | -3% | 0.39 | 0.98 | [-9.7, +2.8] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 26 | -32% | -4% | 0.38 | 0.98 | [-10.5, +4.3] | PAPER (n 26 < 150) |
| Austrian Bundesliga | ou25 | 23 | -30% | -4% | 0.36 | 0.98 | [-13.1, +2.5] | PAPER (n 23 < 150) |
| China Super League | ou25 | 32 | -24% | -4% | 0.35 | 0.98 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Championship | ou25 | 25 | -32% | -6% | 0.30 | 0.98 | [-7.8, +5.4] | PAPER (n 25 < 150) |
| League One | ou25 | 23 | -49% | -9% | 0.22 | 0.98 | [-7.7, +3.5] | PAPER (n 23 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1187 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68309 | 0.24506 | – | – | – | – | – |
| v9 | 0.69543 | 0.25111 | 326 | 0.798 | -32.63 | -10% | -3.97 |
| Challenger | 0.68415 | 0.24555 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.364, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

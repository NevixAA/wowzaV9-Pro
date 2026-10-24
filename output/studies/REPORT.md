# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **55%**.
- Tip period, 118 matches with a clean Bet365 price: BTTS happened 58% while the de-vigged price implied 42% (gap 15.1 points).
- **B, blind YES on every match: +26%** [+10%, +43%], n 118.
- A, matches Wowza picked: +38%; matches it did not pick: +16%. Difference +22% [-5%, +46%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2459 vs 0.2821; residual z 0.16 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (106 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1329 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 220 | 60% | 50% | 65% | -10.1 | +5.0 |
| UNDER 5-10pp | 262 | 61% | 52% | 59% | -9.3 | -1.8 |
| UNDER 2-5pp | 183 | 58% | 52% | 55% | -6.6 | -3.2 |
| agrees (±2pp) | 296 | 52% | 52% | 52% | -0.0 | -0.0 |
| OVER 2-5pp | 173 | 48% | 52% | 48% | +3.9 | +0.5 |
| OVER 5-10pp | 145 | 46% | 52% | 45% | +6.2 | -0.9 |
| model OVER by >10pp | 50 | 44% | 54% | 42% | +10.1 | -2.2 |

- Share of the model's lean that showed up in results: leaning UNDER 0.007, leaning OVER 0.073 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1329 | 0.24336 | 0.24857 | +0.00143 | [-0.0007, +0.0036] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 719 | 0.24169 | 0.24705 | +0.00777 | [+0.0031, +0.0131] | MODEL_HURTS |
| OU25 | standard | 610 | 0.24532 | 0.25037 | +0.00302 | [-0.0016, +0.0080] | NO_DETECTABLE_GAIN |
| OU35 | all | 372 | 0.23519 | 0.25006 | +0.06389 | [+0.0094, +0.1353] | MODEL_HURTS |
| OU35 | new_format | 287 | 0.23426 | 0.25068 | +0.00085 | [-0.0006, +0.0026] | NO_DETECTABLE_GAIN |
| BTTS | all | 1324 | 0.24242 | 0.24438 | +0.01186 | [+0.0047, +0.0187] | MODEL_HURTS |
| BTTS | new_format | 723 | 0.24188 | 0.24227 | +0.00658 | [+0.0023, +0.0111] | MODEL_HURTS |
| BTTS | standard | 601 | 0.24306 | 0.24691 | +0.00567 | [-0.0053, +0.0180] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 30; the rest are too small). Pooled prior +3.4%, between-cell sd 0.18. Reality-check p for the best cell: **0.043**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 86 | +33% | +24% | 0.99 | 0.06 | [-5.6, +2.1] | PAPER (n 86 < 150) |
| Brazil Serie A | ou25 | 26 | +51% | +23% | 0.95 | 0.08 | [-7.7, +3.1] | PAPER (n 26 < 150) |
| Serie B | ou25 | 22 | +25% | +12% | 0.78 | 0.62 | [-1.3, +11.8] | PAPER (n 22 < 150) |
| Sweden Allsvenskan | ou25 | 33 | +22% | +12% | 0.79 | 0.62 | [-4.4, +4.0] | PAPER (n 33 < 150) |
| Brazil Serie A | btts | 20 | +24% | +11% | 0.76 | 0.62 | [-21.0, +17.7] | PAPER (n 20 < 150) |
| Argentina Primera Division | ou25 | 33 | +15% | +7% | 0.68 | 0.74 | [-4.2, +5.4] | PAPER (n 33 < 150) |
| Finland Veikkausliiga | ou25 | 19 | +11% | +6% | 0.65 | 0.74 | [-6.6, +7.1] | PAPER (n 19 < 150) |
| Japan J-League | ou25 | 28 | +8% | +5% | 0.65 | 0.74 | [-4.3, +10.6] | PAPER (n 28 < 150) |
| Argentina Primera Division | over15 | 94 | +5% | +5% | 0.69 | 0.74 | [-0.0, +2.8] | PAPER (n 94 < 150) |
| Mexico Liga MX | ou25 | 32 | +2% | +3% | 0.57 | 0.89 | [-3.8, +7.6] | PAPER (CLV deterioration alarm) |
| La Liga 2 | ou25 | 37 | -2% | +2% | 0.54 | 0.91 | [-2.6, +4.1] | PAPER (n 37 < 150) |
| Austrian Bundesliga | ou25 | 19 | -15% | -3% | 0.44 | 0.98 | [-14.3, +5.0] | PAPER (n 19 < 150) |
| Denmark Superliga | ou25 | 22 | -15% | -3% | 0.42 | 0.98 | [-4.5, +6.6] | PAPER (n 22 < 150) |
| Ireland Premier Division | ou25 | 20 | -25% | -7% | 0.33 | 0.98 | [-9.7, +2.8] | PAPER (n 20 < 150) |
| Bundesliga 2 | ou25 | 15 | -35% | -8% | 0.31 | 0.98 | [-13.2, +9.9] | PAPER (n 15 < 150) |
| China Super League | ou25 | 26 | -33% | -10% | 0.27 | 0.98 | [-10.6, +4.1] | PAPER (n 26 < 150) |
| Championship | ou25 | 25 | -32% | -11% | 0.22 | 0.98 | [-7.8, +5.4] | PAPER (n 25 < 150) |
| League One | ou25 | 22 | -46% | -16% | 0.15 | 0.98 | [-8.1, +3.7] | PAPER (n 22 < 150) |
| Norway Eliteserien | ou25 | 21 | -49% | -16% | 0.15 | 0.98 | [-11.9, +6.6] | PAPER (n 21 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1035 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68708 | 0.24713 | – | – | – | – | – |
| v9 | 0.6947 | 0.25075 | 270 | 0.793 | -17.38 | -6% | -3.93 |
| Challenger | 0.68719 | 0.24708 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.24, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

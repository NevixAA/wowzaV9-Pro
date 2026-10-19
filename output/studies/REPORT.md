# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **55%**.
- Tip period, 112 matches with a clean Bet365 price: BTTS happened 57% while the de-vigged price implied 42% (gap 14.7 points).
- **B, blind YES on every match: +25%** [+9%, +43%], n 112.
- A, matches Wowza picked: +39%; matches it did not pick: +13%. Difference +26% [+0%, +51%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2451 vs 0.2816; residual z 0.38 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (102 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1258 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 196 | 60% | 51% | 66% | -8.9 | +6.1 |
| UNDER 5-10pp | 253 | 61% | 52% | 59% | -9.4 | -2.0 |
| UNDER 2-5pp | 173 | 58% | 52% | 55% | -6.4 | -3.0 |
| agrees (±2pp) | 282 | 51% | 52% | 52% | +0.7 | +0.7 |
| OVER 2-5pp | 167 | 48% | 52% | 49% | +3.5 | +0.0 |
| OVER 5-10pp | 137 | 47% | 52% | 45% | +5.7 | -1.4 |
| model OVER by >10pp | 50 | 44% | 54% | 42% | +10.1 | -2.2 |

- Share of the model's lean that showed up in results: leaning UNDER 0.032, leaning OVER 0.139 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1258 | 0.24353 | 0.2481 | +0.00179 | [-0.0004, +0.0040] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 682 | 0.24194 | 0.24599 | +0.00731 | [+0.0023, +0.0128] | MODEL_HURTS |
| OU25 | standard | 576 | 0.24542 | 0.2506 | +0.00362 | [-0.0017, +0.0094] | NO_DETECTABLE_GAIN |
| OU35 | all | 357 | 0.23352 | 0.24677 | +0.04125 | [-0.0003, +0.0950] | NO_DETECTABLE_GAIN |
| OU35 | new_format | 279 | 0.23305 | 0.24814 | +0.00333 | [+0.0001, +0.0072] | MODEL_HURTS |
| BTTS | all | 1252 | 0.24224 | 0.24423 | +0.00757 | [+0.0014, +0.0149] | MODEL_HURTS |
| BTTS | new_format | 685 | 0.24178 | 0.24218 | +0.00874 | [+0.0041, +0.0138] | MODEL_HURTS |
| BTTS | standard | 567 | 0.2428 | 0.24669 | +0.00902 | [-0.0038, +0.0229] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 29; the rest are too small). Pooled prior +4.8%, between-cell sd 0.16. Reality-check p for the best cell: **0.044**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 84 | +33% | +23% | 0.99 | 0.06 | [-5.8, +2.1] | PAPER (n 84 < 150) |
| Brazil Serie A | ou25 | 22 | +58% | +21% | 0.94 | 0.06 | [-7.6, +4.0] | PAPER (n 22 < 150) |
| Serie B | ou25 | 22 | +25% | +11% | 0.79 | 0.77 | [-1.3, +11.8] | PAPER (n 22 < 150) |
| Sweden Allsvenskan | ou25 | 28 | +19% | +9% | 0.75 | 0.77 | [-5.6, +4.7] | PAPER (n 28 < 150) |
| Brazil Serie A | btts | 19 | +19% | +9% | 0.73 | 0.77 | [-23.0, +19.4] | PAPER (n 19 < 150) |
| Argentina Primera Division | ou25 | 32 | +10% | +6% | 0.67 | 0.77 | [-4.4, +5.6] | PAPER (n 32 < 150) |
| Japan J-League | ou25 | 26 | +8% | +6% | 0.67 | 0.77 | [-4.8, +11.7] | PAPER (n 26 < 150) |
| Denmark Superliga | ou25 | 17 | +10% | +6% | 0.66 | 0.77 | [-6.7, +7.2] | PAPER (n 17 < 150) |
| Mexico Liga MX | ou25 | 26 | +7% | +6% | 0.66 | 0.77 | [-0.3, +8.4] | PAPER (n 26 < 150) |
| Finland Veikkausliiga | ou25 | 18 | +6% | +5% | 0.64 | 0.77 | [-7.3, +7.0] | PAPER (n 18 < 150) |
| La Liga 2 | ou25 | 33 | -2% | +3% | 0.59 | 0.83 | [-2.9, +4.3] | PAPER (n 33 < 150) |
| Argentina Primera Division | over15 | 87 | +1% | +3% | 0.60 | 0.79 | [-0.2, +2.7] | PAPER (n 87 < 150) |
| Ireland Premier Division | ou25 | 15 | -15% | +0% | 0.51 | 0.98 | [-13.4, +3.6] | PAPER (n 15 < 150) |
| Austrian Bundesliga | ou25 | 17 | -18% | -1% | 0.48 | 0.98 | [-15.6, +2.4] | PAPER (n 17 < 150) |
| Bundesliga 2 | ou25 | 14 | -31% | -3% | 0.43 | 0.98 | [-14.4, +9.4] | PAPER (n 14 < 150) |
| China Super League | ou25 | 24 | -27% | -4% | 0.40 | 0.98 | [-11.8, +4.5] | PAPER (n 24 < 150) |
| Championship | ou25 | 24 | -29% | -6% | 0.32 | 0.98 | [-7.8, +5.9] | PAPER (n 24 < 150) |
| League One | ou25 | 20 | -41% | -8% | 0.27 | 0.98 | [-7.5, +4.6] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 18 | -54% | -11% | 0.23 | 0.98 | [-14.2, +8.5] | PAPER (n 18 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 964 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68804 | 0.2476 | – | – | – | – | – |
| v9 | 0.69459 | 0.2507 | 246 | 0.78 | -12.88 | -5% | -3.8 |
| Challenger | 0.68812 | 0.24754 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.263, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **54%**.
- Tip period, 108 matches with a clean Bet365 price: BTTS happened 56% while the de-vigged price implied 42% (gap 14.1 points).
- **B, blind YES on every match: +24%** [+8%, +42%], n 108.
- A, matches Wowza picked: +39%; matches it did not pick: +10%. Difference +29% [+2%, +54%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2435 vs 0.2812; residual z 0.95 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (98 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1210 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 180 | 59% | 51% | 66% | -8.4 | +6.5 |
| UNDER 5-10pp | 244 | 61% | 52% | 59% | -8.9 | -1.5 |
| UNDER 2-5pp | 167 | 59% | 52% | 55% | -7.4 | -4.0 |
| agrees (±2pp) | 276 | 52% | 52% | 52% | +0.3 | +0.3 |
| OVER 2-5pp | 159 | 47% | 52% | 49% | +5.5 | +2.1 |
| OVER 5-10pp | 136 | 46% | 52% | 45% | +6.1 | -1.0 |
| model OVER by >10pp | 48 | 46% | 54% | 42% | +8.4 | -4.0 |

- Share of the model's lean that showed up in results: leaning UNDER 0.028, leaning OVER 0.002 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1210 | 0.2433 | 0.24777 | +0.00349 | [+0.0010, +0.0061] | MODEL_HURTS |
| OU25 | new_format | 645 | 0.24144 | 0.24529 | +0.01043 | [+0.0039, +0.0178] | MODEL_HURTS |
| OU25 | standard | 565 | 0.24542 | 0.25061 | +0.00377 | [-0.0016, +0.0094] | NO_DETECTABLE_GAIN |
| OU35 | all | 334 | 0.23401 | 0.24777 | +0.04464 | [+0.0000, +0.1035] | NO_DETECTABLE_GAIN |
| OU35 | new_format | 259 | 0.23339 | 0.24929 | +0.01054 | [+0.0038, +0.0187] | MODEL_HURTS |
| BTTS | all | 1203 | 0.24212 | 0.24403 | +0.00917 | [+0.0026, +0.0172] | MODEL_HURTS |
| BTTS | new_format | 647 | 0.24203 | 0.24205 | +0.00889 | [+0.0042, +0.0141] | MODEL_HURTS |
| BTTS | standard | 556 | 0.24222 | 0.24633 | +0.00846 | [-0.0038, +0.0222] | NO_DETECTABLE_GAIN |

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

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 916 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.6875 | 0.24734 | – | – | – | – | – |
| v9 | 0.69392 | 0.25036 | 221 | 0.774 | -10.05 | -5% | -3.83 |
| Challenger | 0.68815 | 0.24755 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.241, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

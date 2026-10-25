# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **55%**.
- Tip period, 122 matches with a clean Bet365 price: BTTS happened 57% while the de-vigged price implied 43% (gap 14.8 points).
- **B, blind YES on every match: +26%** [+10%, +42%], n 122.
- A, matches Wowza picked: +33%; matches it did not pick: +19%. Difference +15% [-13%, +41%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2471 vs 0.2787; residual z -0.07 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (110 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1409 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 241 | 61% | 50% | 65% | -10.4 | +4.8 |
| UNDER 5-10pp | 275 | 62% | 52% | 59% | -10.0 | -2.6 |
| UNDER 2-5pp | 192 | 58% | 52% | 55% | -5.9 | -2.5 |
| agrees (±2pp) | 315 | 51% | 52% | 52% | +0.8 | +0.9 |
| OVER 2-5pp | 182 | 47% | 52% | 48% | +4.6 | +1.1 |
| OVER 5-10pp | 152 | 45% | 52% | 45% | +7.0 | -0.0 |
| model OVER by >10pp | 52 | 44% | 54% | 42% | +9.9 | -2.5 |

- Share of the model's lean that showed up in results: leaning UNDER -0.004, leaning OVER -0.031 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1409 | 0.24339 | 0.24897 | +0.00157 | [-0.0002, +0.0035] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 752 | 0.2413 | 0.24735 | +0.00788 | [+0.0033, +0.0133] | MODEL_HURTS |
| OU25 | standard | 657 | 0.24578 | 0.25083 | +0.00588 | [-0.0013, +0.0137] | NO_DETECTABLE_GAIN |
| OU35 | all | 397 | 0.23472 | 0.24922 | +0.05863 | [+0.0089, +0.1233] | MODEL_HURTS |
| OU35 | new_format | 300 | 0.23501 | 0.25286 | +0.04865 | [+0.0083, +0.0982] | MODEL_HURTS |
| BTTS | all | 1405 | 0.24204 | 0.24456 | +0.01119 | [+0.0048, +0.0181] | MODEL_HURTS |
| BTTS | new_format | 757 | 0.24162 | 0.24293 | +0.00822 | [+0.0040, +0.0124] | MODEL_HURTS |
| BTTS | standard | 648 | 0.24252 | 0.24646 | +0.00557 | [-0.0046, +0.0167] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

19 cells tested (of 30; the rest are too small). Pooled prior +3.4%, between-cell sd 0.14. Reality-check p for the best cell: **0.063**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 88 | +30% | +19% | 0.98 | 0.12 | [-5.5, +2.0] | PAPER (n 88 < 150) |
| Brazil Serie A | ou25 | 28 | +47% | +17% | 0.91 | 0.12 | [-7.4, +2.5] | PAPER (n 28 < 150) |
| Serie B | ou25 | 22 | +25% | +9% | 0.76 | 0.70 | [-1.3, +11.8] | PAPER (n 22 < 150) |
| Brazil Serie A | btts | 20 | +24% | +8% | 0.74 | 0.70 | [-21.0, +17.7] | PAPER (n 20 < 150) |
| Sweden Allsvenskan | ou25 | 36 | +12% | +6% | 0.69 | 0.70 | [-4.8, +3.3] | PAPER (n 36 < 150) |
| Argentina Primera Division | ou25 | 33 | +15% | +6% | 0.68 | 0.70 | [-4.2, +5.4] | PAPER (n 33 < 150) |
| Japan J-League | ou25 | 30 | +10% | +5% | 0.67 | 0.70 | [-3.9, +9.6] | PAPER (n 30 < 150) |
| Mexico Liga MX | ou25 | 34 | +9% | +5% | 0.66 | 0.70 | [-3.5, +7.0] | PAPER (CLV deterioration alarm) |
| Finland Veikkausliiga | ou25 | 21 | +9% | +5% | 0.64 | 0.70 | [-6.2, +5.9] | PAPER (n 21 < 150) |
| Argentina Primera Division | over15 | 97 | +4% | +4% | 0.66 | 0.70 | [+0.1, +2.9] | PAPER (n 97 < 150) |
| La Liga 2 | ou25 | 37 | -2% | +2% | 0.57 | 0.91 | [-2.6, +4.1] | PAPER (n 37 < 150) |
| Denmark Superliga | ou25 | 22 | -15% | -1% | 0.47 | 0.98 | [-4.5, +6.6] | PAPER (n 22 < 150) |
| Bundesliga 2 | ou25 | 17 | -24% | -2% | 0.45 | 0.98 | [-11.9, +9.3] | PAPER (n 17 < 150) |
| Austrian Bundesliga | ou25 | 21 | -23% | -3% | 0.41 | 0.98 | [-13.2, +3.9] | PAPER (n 21 < 150) |
| Ireland Premier Division | ou25 | 20 | -25% | -3% | 0.40 | 0.98 | [-9.7, +2.8] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 23 | -33% | -3% | 0.40 | 0.98 | [-12.2, +5.1] | PAPER (n 23 < 150) |
| China Super League | ou25 | 32 | -24% | -5% | 0.34 | 0.98 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Championship | ou25 | 25 | -32% | -7% | 0.30 | 0.98 | [-7.8, +5.4] | PAPER (n 25 < 150) |
| League One | ou25 | 23 | -49% | -11% | 0.20 | 0.98 | [-7.7, +3.5] | PAPER (n 23 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1115 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68686 | 0.2469 | – | – | – | – | – |
| v9 | 0.69655 | 0.25166 | 298 | 0.785 | -24.59 | -8% | -3.98 |
| Challenger | 0.687 | 0.24695 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.369, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

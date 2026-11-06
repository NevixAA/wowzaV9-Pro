# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 48%, since 10 Aug **55%**.
- Tip period, 147 matches with a clean Bet365 price: BTTS happened 57% while the de-vigged price implied 43% (gap 14.0 points).
- **B, blind YES on every match: +25%** [+10%, +39%], n 147.
- A, matches Wowza picked: +27%; matches it did not pick: +23%. Difference +3% [-22%, +27%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2492 vs 0.2717; residual z -0.26 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (132 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1682 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 325 | 63% | 50% | 65% | -13.5 | +1.8 |
| UNDER 5-10pp | 338 | 62% | 52% | 59% | -10.2 | -2.7 |
| UNDER 2-5pp | 227 | 58% | 52% | 55% | -5.9 | -2.4 |
| agrees (±2pp) | 365 | 52% | 52% | 52% | +0.2 | +0.2 |
| OVER 2-5pp | 206 | 47% | 52% | 48% | +5.2 | +1.8 |
| OVER 5-10pp | 164 | 46% | 52% | 45% | +6.7 | -0.4 |
| model OVER by >10pp | 57 | 44% | 55% | 42% | +10.6 | -1.7 |

- Share of the model's lean that showed up in results: leaning UNDER -0.109, leaning OVER -0.078 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1682 | 0.24131 | 0.24943 | +0.00029 | [-0.0014, +0.0021] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 913 | 0.2378 | 0.24837 | +0.00393 | [+0.0008, +0.0075] | MODEL_HURTS |
| OU25 | standard | 769 | 0.24548 | 0.25069 | +0.00217 | [-0.0018, +0.0062] | NO_DETECTABLE_GAIN |
| OU15 | all | 136 | 0.19478 | 0.2002 | -0.00557 | [-0.0153, +0.0026] | NO_DETECTABLE_GAIN |
| OU15 | new_format | 106 | 0.19511 | 0.19741 | +0.00022 | [-0.0005, +0.0010] | NO_DETECTABLE_GAIN |
| OU35 | all | 539 | 0.23293 | 0.24703 | +0.06703 | [+0.0248, +0.1147] | MODEL_HURTS |
| OU35 | new_format | 395 | 0.23332 | 0.25302 | +0.03797 | [+0.0108, +0.0728] | MODEL_HURTS |
| OU35 | standard | 144 | 0.23185 | 0.2306 | +0.00068 | [-0.0209, +0.0286] | NO_DETECTABLE_GAIN |
| BTTS | all | 1682 | 0.24106 | 0.24418 | +0.00896 | [+0.0039, +0.0142] | MODEL_HURTS |
| BTTS | new_format | 922 | 0.23931 | 0.24237 | +0.00206 | [-0.0004, +0.0047] | NO_DETECTABLE_GAIN |
| BTTS | standard | 760 | 0.24319 | 0.24638 | +0.03431 | [+0.0127, +0.0574] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 39; the rest are too small). Pooled prior -1.4%, between-cell sd 0.07. Reality-check p for the best cell: **0.205**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 95 | +25% | +6% | 0.82 | 0.32 | [-4.9, +2.1] | PAPER (n 95 < 150) |
| Brazil Serie A | btts | 21 | +28% | +1% | 0.56 | 0.97 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Argentina Primera Division | over15 | 103 | +5% | +1% | 0.55 | 0.97 | [+0.2, +2.8] | PAPER (n 103 < 150) |
| Brazil Serie A | ou25 | 36 | +20% | +1% | 0.54 | 0.97 | [-8.2, +2.3] | PAPER (CLV deterioration alarm) |
| Serie B | ou25 | 23 | +19% | +1% | 0.53 | 0.97 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Sweden Allsvenskan | ou25 | 46 | +10% | +0% | 0.52 | 0.97 | [-4.1, +2.5] | PAPER (n 46 < 150) |
| Argentina Primera Division | ou25 | 35 | +14% | -0% | 0.50 | 0.97 | [-3.8, +5.1] | PAPER (n 35 < 150) |
| Japan J-League | ou25 | 34 | +3% | -1% | 0.46 | 0.98 | [-3.3, +8.2] | PAPER (n 34 < 150) |
| League Two | ou25 | 19 | +5% | -1% | 0.45 | 0.98 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| Finland Veikkausliiga | ou25 | 26 | -3% | -2% | 0.42 | 0.98 | [-7.2, +4.5] | PAPER (CLV deterioration alarm) |
| La Liga 2 | ou25 | 38 | -4% | -2% | 0.42 | 0.98 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Mexico Liga MX | ou25 | 43 | -3% | -2% | 0.42 | 0.98 | [-1.6, +6.8] | PAPER (CLV deterioration alarm) |
| Denmark Superliga | ou25 | 31 | -8% | -2% | 0.40 | 0.98 | [-4.1, +5.4] | PAPER (n 31 < 150) |
| Japan J-League | btts | 10 | -18% | -2% | 0.40 | 0.98 | – | PAPER (n 10 < 150) |
| La Liga 2 | btts | 10 | -22% | -2% | 0.40 | 0.98 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Bundesliga 2 | ou25 | 20 | -24% | -3% | 0.36 | 0.98 | [-9.1, +9.3] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 27 | -26% | -3% | 0.35 | 0.98 | [-10.0, +4.1] | PAPER (n 27 < 150) |
| China Super League | ou25 | 32 | -24% | -4% | 0.33 | 0.98 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Ireland Premier Division | ou25 | 24 | -30% | -4% | 0.31 | 0.98 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -4% | 0.30 | 0.98 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| League One | ou25 | 25 | -42% | -6% | 0.25 | 0.98 | [-7.0, +3.1] | PAPER (n 25 < 150) |
| Championship | ou25 | 29 | -42% | -6% | 0.23 | 0.98 | [-6.8, +4.5] | PAPER (n 29 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1388 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68086 | 0.24398 | – | – | – | – | – |
| v9 | 0.69684 | 0.2518 | 409 | 0.834 | -56.59 | -14% | -4.04 |
| Challenger | 0.68156 | 0.24428 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.493, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

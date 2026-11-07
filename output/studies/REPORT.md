# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 48%, since 10 Aug **55%**.
- Tip period, 154 matches with a clean Bet365 price: BTTS happened 56% while the de-vigged price implied 43% (gap 12.7 points).
- **B, blind YES on every match: +22%** [+7%, +36%], n 154.
- A, matches Wowza picked: +26%; matches it did not pick: +18%. Difference +8% [-16%, +31%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2496 vs 0.2716; residual z -0.36 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (140 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1699 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 325 | 63% | 50% | 65% | -13.5 | +1.8 |
| UNDER 5-10pp | 343 | 62% | 52% | 59% | -10.4 | -3.0 |
| UNDER 2-5pp | 231 | 58% | 52% | 55% | -5.8 | -2.3 |
| agrees (±2pp) | 368 | 52% | 52% | 52% | +0.3 | +0.3 |
| OVER 2-5pp | 208 | 47% | 52% | 48% | +5.1 | +1.6 |
| OVER 5-10pp | 166 | 46% | 52% | 45% | +6.7 | -0.4 |
| model OVER by >10pp | 58 | 45% | 55% | 42% | +9.7 | -2.7 |

- Share of the model's lean that showed up in results: leaning UNDER -0.118, leaning OVER -0.047 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1699 | 0.24152 | 0.24955 | +0.00065 | [-0.0011, +0.0024] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 920 | 0.2379 | 0.24838 | +0.00350 | [+0.0003, +0.0070] | MODEL_HURTS |
| OU25 | standard | 779 | 0.24579 | 0.25093 | +0.00268 | [-0.0019, +0.0080] | NO_DETECTABLE_GAIN |
| OU15 | all | 154 | 0.19548 | 0.19857 | -0.00575 | [-0.0144, +0.0012] | NO_DETECTABLE_GAIN |
| OU15 | new_format | 114 | 0.19268 | 0.19368 | +0.00129 | [+0.0003, +0.0024] | MODEL_HURTS |
| OU35 | all | 557 | 0.23128 | 0.24568 | +0.06450 | [+0.0243, +0.1099] | MODEL_HURTS |
| OU35 | new_format | 403 | 0.23129 | 0.25153 | +0.04493 | [+0.0160, +0.0832] | MODEL_HURTS |
| OU35 | standard | 154 | 0.23123 | 0.23038 | -0.00581 | [-0.0215, +0.0148] | NO_DETECTABLE_GAIN |
| BTTS | all | 1700 | 0.24134 | 0.24435 | +0.00884 | [+0.0039, +0.0139] | MODEL_HURTS |
| BTTS | new_format | 930 | 0.23949 | 0.2425 | +0.00204 | [-0.0004, +0.0047] | NO_DETECTABLE_GAIN |
| BTTS | standard | 770 | 0.24358 | 0.24658 | +0.03391 | [+0.0128, +0.0580] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 39; the rest are too small). Pooled prior -1.6%, between-cell sd 0.07. Reality-check p for the best cell: **0.2**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 97 | +25% | +6% | 0.80 | 0.31 | [-5.0, +1.9] | PAPER (n 97 < 150) |
| Brazil Serie A | btts | 21 | +28% | +1% | 0.54 | 0.98 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Argentina Primera Division | over15 | 104 | +6% | +1% | 0.54 | 0.98 | [+0.2, +2.8] | PAPER (n 104 < 150) |
| Serie B | ou25 | 23 | +19% | +0% | 0.51 | 0.98 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Brazil Serie A | ou25 | 37 | +16% | -0% | 0.50 | 0.98 | [-8.1, +2.0] | PAPER (CLV deterioration alarm) |
| Sweden Allsvenskan | ou25 | 47 | +8% | -0% | 0.48 | 0.98 | [-4.1, +2.4] | PAPER (n 47 < 150) |
| Argentina Primera Division | ou25 | 35 | +14% | -0% | 0.48 | 0.98 | [-3.8, +5.1] | PAPER (n 35 < 150) |
| Japan J-League | ou25 | 34 | +3% | -1% | 0.45 | 0.98 | [-3.3, +8.2] | PAPER (n 34 < 150) |
| League Two | ou25 | 19 | +5% | -1% | 0.43 | 0.98 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| Finland Veikkausliiga | ou25 | 26 | -3% | -2% | 0.41 | 0.98 | [-7.2, +4.5] | PAPER (CLV deterioration alarm) |
| La Liga 2 | ou25 | 38 | -4% | -2% | 0.41 | 0.98 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Mexico Liga MX | ou25 | 43 | -3% | -2% | 0.41 | 0.98 | [-1.6, +6.8] | PAPER (CLV deterioration alarm) |
| Denmark Superliga | ou25 | 31 | -8% | -2% | 0.39 | 0.98 | [-4.1, +5.4] | PAPER (n 31 < 150) |
| Japan J-League | btts | 10 | -18% | -2% | 0.39 | 0.98 | – | PAPER (n 10 < 150) |
| La Liga 2 | btts | 10 | -22% | -2% | 0.39 | 0.98 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Bundesliga 2 | ou25 | 20 | -24% | -3% | 0.35 | 0.98 | [-9.1, +9.3] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 27 | -26% | -3% | 0.34 | 0.98 | [-10.0, +4.1] | PAPER (n 27 < 150) |
| China Super League | ou25 | 32 | -24% | -4% | 0.31 | 0.98 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Ireland Premier Division | ou25 | 24 | -30% | -4% | 0.30 | 0.98 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -4% | 0.30 | 0.98 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| League One | ou25 | 25 | -42% | -5% | 0.25 | 0.98 | [-7.0, +3.1] | PAPER (n 25 < 150) |
| Championship | ou25 | 29 | -42% | -6% | 0.23 | 0.98 | [-6.8, +4.5] | PAPER (n 29 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1405 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68112 | 0.2441 | – | – | – | – | – |
| v9 | 0.69707 | 0.25192 | 413 | 0.835 | -57.91 | -14% | -4.04 |
| Challenger | 0.68169 | 0.24435 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.509, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

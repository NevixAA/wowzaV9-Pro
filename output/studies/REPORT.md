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

- 1673 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 322 | 63% | 50% | 65% | -13.4 | +1.8 |
| UNDER 5-10pp | 336 | 62% | 52% | 59% | -10.2 | -2.8 |
| UNDER 2-5pp | 227 | 58% | 52% | 55% | -5.9 | -2.4 |
| agrees (±2pp) | 363 | 52% | 52% | 52% | -0.1 | -0.1 |
| OVER 2-5pp | 206 | 47% | 52% | 48% | +5.2 | +1.8 |
| OVER 5-10pp | 163 | 45% | 52% | 45% | +7.0 | -0.1 |
| model OVER by >10pp | 56 | 45% | 55% | 42% | +9.9 | -2.4 |

- Share of the model's lean that showed up in results: leaning UNDER -0.112, leaning OVER -0.083 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1673 | 0.24152 | 0.24951 | -0.00003 | [-0.0016, +0.0016] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 907 | 0.23811 | 0.24849 | +0.00297 | [-0.0003, +0.0066] | NO_DETECTABLE_GAIN |
| OU25 | standard | 766 | 0.24555 | 0.25071 | +0.00216 | [-0.0020, +0.0062] | NO_DETECTABLE_GAIN |
| OU15 | all | 127 | 0.19853 | 0.20258 | +0.00070 | [-0.0104, +0.0114] | NO_DETECTABLE_GAIN |
| OU15 | new_format | 100 | 0.19504 | 0.19558 | +0.00120 | [-0.0032, +0.0076] | NO_DETECTABLE_GAIN |
| OU35 | all | 530 | 0.23353 | 0.24708 | +0.06851 | [+0.0248, +0.1191] | MODEL_HURTS |
| OU35 | new_format | 389 | 0.23356 | 0.25274 | +0.03800 | [+0.0101, +0.0715] | MODEL_HURTS |
| OU35 | standard | 141 | 0.23345 | 0.23146 | +0.00028 | [-0.0222, +0.0284] | NO_DETECTABLE_GAIN |
| BTTS | all | 1673 | 0.24104 | 0.24416 | +0.00897 | [+0.0039, +0.0147] | MODEL_HURTS |
| BTTS | new_format | 916 | 0.23929 | 0.24241 | +0.00201 | [+0.0001, +0.0038] | MODEL_HURTS |
| BTTS | standard | 757 | 0.24315 | 0.24629 | +0.03461 | [+0.0132, +0.0587] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 39; the rest are too small). Pooled prior -0.4%, between-cell sd 0.10. Reality-check p for the best cell: **0.217**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 95 | +25% | +10% | 0.90 | 0.32 | [-4.9, +2.1] | PAPER (n 95 < 150) |
| Brazil Serie A | ou25 | 32 | +34% | +6% | 0.75 | 0.42 | [-8.2, +2.9] | PAPER (CLV deterioration alarm) |
| Brazil Serie A | btts | 21 | +28% | +3% | 0.64 | 0.91 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Serie B | ou25 | 23 | +19% | +3% | 0.60 | 0.97 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Argentina Primera Division | over15 | 103 | +5% | +2% | 0.61 | 0.97 | [+0.2, +2.8] | PAPER (n 103 < 150) |
| Sweden Allsvenskan | ou25 | 46 | +10% | +2% | 0.58 | 0.97 | [-4.1, +2.5] | PAPER (n 46 < 150) |
| Argentina Primera Division | ou25 | 34 | +11% | +1% | 0.54 | 0.97 | [-4.0, +5.3] | PAPER (n 34 < 150) |
| Japan J-League | ou25 | 34 | +3% | +0% | 0.51 | 0.97 | [-3.3, +8.2] | PAPER (n 34 < 150) |
| League Two | ou25 | 19 | +5% | -0% | 0.50 | 0.97 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| Finland Veikkausliiga | ou25 | 26 | -3% | -1% | 0.46 | 0.97 | [-7.2, +4.5] | PAPER (CLV deterioration alarm) |
| La Liga 2 | ou25 | 38 | -4% | -1% | 0.46 | 0.97 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Mexico Liga MX | ou25 | 43 | -3% | -1% | 0.46 | 0.97 | [-1.6, +6.8] | PAPER (CLV deterioration alarm) |
| Japan J-League | btts | 10 | -18% | -2% | 0.44 | 0.97 | – | PAPER (n 10 < 150) |
| Denmark Superliga | ou25 | 31 | -8% | -2% | 0.43 | 0.97 | [-4.1, +5.4] | PAPER (n 31 < 150) |
| La Liga 2 | btts | 10 | -22% | -2% | 0.43 | 0.97 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Bundesliga 2 | ou25 | 20 | -24% | -3% | 0.38 | 0.97 | [-9.1, +9.3] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 27 | -26% | -3% | 0.37 | 0.97 | [-10.0, +4.1] | PAPER (n 27 < 150) |
| China Super League | ou25 | 32 | -24% | -4% | 0.33 | 0.97 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Ireland Premier Division | ou25 | 24 | -30% | -5% | 0.31 | 0.97 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -5% | 0.30 | 0.97 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| League One | ou25 | 25 | -42% | -7% | 0.24 | 0.97 | [-7.0, +3.1] | PAPER (n 25 < 150) |
| Championship | ou25 | 28 | -40% | -7% | 0.23 | 0.97 | [-6.8, +4.9] | PAPER (n 28 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1379 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68128 | 0.24418 | – | – | – | – | – |
| v9 | 0.69669 | 0.25173 | 405 | 0.832 | -54.47 | -13% | -4.01 |
| Challenger | 0.68185 | 0.24442 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.478, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

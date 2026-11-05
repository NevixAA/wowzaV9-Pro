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

- 1679 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 324 | 63% | 50% | 65% | -13.6 | +1.6 |
| UNDER 5-10pp | 337 | 62% | 52% | 59% | -10.1 | -2.6 |
| UNDER 2-5pp | 227 | 58% | 52% | 55% | -5.9 | -2.4 |
| agrees (±2pp) | 365 | 52% | 52% | 52% | +0.2 | +0.2 |
| OVER 2-5pp | 206 | 47% | 52% | 48% | +5.2 | +1.8 |
| OVER 5-10pp | 164 | 46% | 52% | 45% | +6.7 | -0.4 |
| model OVER by >10pp | 56 | 45% | 55% | 42% | +9.9 | -2.4 |

- Share of the model's lean that showed up in results: leaning UNDER -0.111, leaning OVER -0.064 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1679 | 0.24141 | 0.2495 | -0.00004 | [-0.0016, +0.0016] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 910 | 0.23798 | 0.2485 | +0.00310 | [-0.0001, +0.0067] | NO_DETECTABLE_GAIN |
| OU25 | standard | 769 | 0.24548 | 0.25069 | +0.00217 | [-0.0018, +0.0062] | NO_DETECTABLE_GAIN |
| OU15 | all | 133 | 0.19535 | 0.19952 | -0.00246 | [-0.0138, +0.0078] | NO_DETECTABLE_GAIN |
| OU15 | new_format | 103 | 0.19585 | 0.19646 | +0.00188 | [-0.0037, +0.0100] | NO_DETECTABLE_GAIN |
| OU35 | all | 536 | 0.23334 | 0.24729 | +0.06754 | [+0.0248, +0.1172] | MODEL_HURTS |
| OU35 | new_format | 392 | 0.23389 | 0.25342 | +0.03833 | [+0.0112, +0.0725] | MODEL_HURTS |
| OU35 | standard | 144 | 0.23185 | 0.2306 | +0.00068 | [-0.0222, +0.0290] | NO_DETECTABLE_GAIN |
| BTTS | all | 1679 | 0.24106 | 0.24414 | +0.00906 | [+0.0039, +0.0144] | MODEL_HURTS |
| BTTS | new_format | 919 | 0.2393 | 0.24229 | +0.00262 | [+0.0003, +0.0052] | MODEL_HURTS |
| BTTS | standard | 760 | 0.24319 | 0.24638 | +0.03431 | [+0.0130, +0.0578] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 39; the rest are too small). Pooled prior -0.9%, between-cell sd 0.09. Reality-check p for the best cell: **0.234**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 95 | +25% | +9% | 0.87 | 0.32 | [-4.9, +2.1] | PAPER (n 95 < 150) |
| Brazil Serie A | ou25 | 34 | +27% | +4% | 0.68 | 0.87 | [-8.6, +2.6] | PAPER (CLV deterioration alarm) |
| Brazil Serie A | btts | 21 | +28% | +3% | 0.61 | 0.91 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Serie B | ou25 | 23 | +19% | +2% | 0.57 | 0.98 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Argentina Primera Division | over15 | 103 | +5% | +2% | 0.59 | 0.98 | [+0.2, +2.8] | PAPER (n 103 < 150) |
| Sweden Allsvenskan | ou25 | 46 | +10% | +1% | 0.56 | 0.98 | [-4.1, +2.5] | PAPER (n 46 < 150) |
| Argentina Primera Division | ou25 | 34 | +11% | +0% | 0.52 | 0.98 | [-4.0, +5.3] | PAPER (n 34 < 150) |
| Japan J-League | ou25 | 34 | +3% | -0% | 0.49 | 0.98 | [-3.3, +8.2] | PAPER (n 34 < 150) |
| League Two | ou25 | 19 | +5% | -0% | 0.48 | 0.98 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| Finland Veikkausliiga | ou25 | 26 | -3% | -1% | 0.45 | 0.98 | [-7.2, +4.5] | PAPER (CLV deterioration alarm) |
| La Liga 2 | ou25 | 38 | -4% | -1% | 0.45 | 0.98 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Mexico Liga MX | ou25 | 43 | -3% | -1% | 0.44 | 0.98 | [-1.6, +6.8] | PAPER (CLV deterioration alarm) |
| Japan J-League | btts | 10 | -18% | -2% | 0.42 | 0.98 | – | PAPER (n 10 < 150) |
| Denmark Superliga | ou25 | 31 | -8% | -2% | 0.42 | 0.98 | [-4.1, +5.4] | PAPER (n 31 < 150) |
| La Liga 2 | btts | 10 | -22% | -2% | 0.41 | 0.98 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Bundesliga 2 | ou25 | 20 | -24% | -3% | 0.37 | 0.98 | [-9.1, +9.3] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 27 | -26% | -3% | 0.36 | 0.98 | [-10.0, +4.1] | PAPER (n 27 < 150) |
| China Super League | ou25 | 32 | -24% | -4% | 0.33 | 0.98 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Ireland Premier Division | ou25 | 24 | -30% | -5% | 0.31 | 0.98 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -5% | 0.30 | 0.98 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| League One | ou25 | 25 | -42% | -6% | 0.24 | 0.98 | [-7.0, +3.1] | PAPER (n 25 < 150) |
| Championship | ou25 | 29 | -42% | -7% | 0.21 | 0.98 | [-6.8, +4.5] | PAPER (n 29 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1385 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68113 | 0.24411 | – | – | – | – | – |
| v9 | 0.69692 | 0.25184 | 407 | 0.833 | -56.47 | -14% | -4.04 |
| Challenger | 0.68175 | 0.24438 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.497, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

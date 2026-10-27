# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **54%**.
- Tip period, 129 matches with a clean Bet365 price: BTTS happened 56% while the de-vigged price implied 43% (gap 13.2 points).
- **B, blind YES on every match: +22%** [+7%, +39%], n 129.
- A, matches Wowza picked: +29%; matches it did not pick: +16%. Difference +12% [-14%, +39%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2479 vs 0.2761; residual z 0.04 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (117 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1466 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 261 | 61% | 50% | 65% | -10.9 | +4.2 |
| UNDER 5-10pp | 295 | 62% | 52% | 59% | -10.1 | -2.6 |
| UNDER 2-5pp | 193 | 58% | 52% | 55% | -5.6 | -2.2 |
| agrees (±2pp) | 327 | 52% | 52% | 52% | +0.3 | +0.3 |
| OVER 2-5pp | 184 | 47% | 52% | 48% | +4.5 | +1.1 |
| OVER 5-10pp | 153 | 45% | 52% | 45% | +7.3 | +0.2 |
| model OVER by >10pp | 53 | 43% | 54% | 42% | +10.7 | -1.8 |

- Share of the model's lean that showed up in results: leaning UNDER -0.014, leaning OVER -0.056 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1466 | 0.24232 | 0.24839 | +0.00147 | [-0.0003, +0.0033] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 796 | 0.23981 | 0.2466 | +0.00822 | [+0.0038, +0.0134] | MODEL_HURTS |
| OU25 | standard | 670 | 0.2453 | 0.25052 | +0.00640 | [-0.0006, +0.0137] | NO_DETECTABLE_GAIN |
| OU35 | all | 422 | 0.2338 | 0.24636 | +0.04219 | [+0.0049, +0.0892] | MODEL_HURTS |
| OU35 | new_format | 321 | 0.23473 | 0.25077 | +0.04687 | [+0.0093, +0.0927] | MODEL_HURTS |
| OU35 | standard | 101 | 0.23084 | 0.23236 | -0.01603 | [-0.0374, -0.0014] | MODEL_ADDS_INFORMATION |
| BTTS | all | 1463 | 0.24136 | 0.24423 | +0.00936 | [+0.0043, +0.0147] | MODEL_HURTS |
| BTTS | new_format | 802 | 0.23982 | 0.24201 | +0.00604 | [+0.0026, +0.0099] | MODEL_HURTS |
| BTTS | standard | 661 | 0.24324 | 0.24692 | +0.01595 | [+0.0003, +0.0325] | MODEL_HURTS |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

21 cells tested (of 39; the rest are too small). Pooled prior +2.1%, between-cell sd 0.12. Reality-check p for the best cell: **0.109**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 92 | +27% | +15% | 0.95 | 0.14 | [-5.3, +1.8] | PAPER (n 92 < 150) |
| Brazil Serie A | ou25 | 29 | +48% | +14% | 0.90 | 0.14 | [-7.1, +2.4] | PAPER (n 29 < 150) |
| Brazil Serie A | btts | 21 | +28% | +7% | 0.73 | 0.87 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Serie B | ou25 | 23 | +19% | +6% | 0.69 | 0.87 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Sweden Allsvenskan | ou25 | 37 | +16% | +6% | 0.69 | 0.87 | [-4.7, +3.1] | PAPER (n 37 < 150) |
| Argentina Primera Division | ou25 | 33 | +15% | +4% | 0.64 | 0.87 | [-4.2, +5.4] | PAPER (n 33 < 150) |
| Japan J-League | ou25 | 32 | +9% | +4% | 0.64 | 0.87 | [-3.5, +8.9] | PAPER (n 32 < 150) |
| Argentina Primera Division | over15 | 99 | +5% | +4% | 0.66 | 0.87 | [+0.1, +2.9] | PAPER (n 99 < 150) |
| Finland Veikkausliiga | ou25 | 22 | +4% | +2% | 0.58 | 0.93 | [-5.7, +5.8] | PAPER (n 22 < 150) |
| Mexico Liga MX | ou25 | 38 | +3% | +2% | 0.58 | 0.93 | [-2.5, +6.8] | PAPER (CLV deterioration alarm) |
| La Liga 2 | ou25 | 38 | -4% | +1% | 0.53 | 0.98 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Denmark Superliga | ou25 | 26 | -8% | -0% | 0.49 | 0.98 | [-5.2, +5.4] | PAPER (n 26 < 150) |
| Japan J-League | btts | 10 | -18% | -0% | 0.49 | 0.98 | – | PAPER (n 10 < 150) |
| La Liga 2 | btts | 10 | -22% | -0% | 0.49 | 0.98 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Bundesliga 2 | ou25 | 18 | -15% | -1% | 0.48 | 0.98 | [-10.9, +8.8] | PAPER (n 18 < 150) |
| Ireland Premier Division | ou25 | 20 | -25% | -3% | 0.39 | 0.98 | [-9.7, +2.8] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 26 | -32% | -4% | 0.37 | 0.98 | [-10.5, +4.3] | PAPER (n 26 < 150) |
| Austrian Bundesliga | ou25 | 23 | -30% | -4% | 0.35 | 0.98 | [-13.1, +2.5] | PAPER (n 23 < 150) |
| China Super League | ou25 | 32 | -24% | -4% | 0.35 | 0.98 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Championship | ou25 | 25 | -32% | -6% | 0.30 | 0.98 | [-7.8, +5.4] | PAPER (n 25 < 150) |
| League One | ou25 | 23 | -49% | -9% | 0.21 | 0.98 | [-7.7, +3.5] | PAPER (n 23 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1172 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68378 | 0.2454 | – | – | – | – | – |
| v9 | 0.69544 | 0.25112 | 324 | 0.799 | -30.63 | -9% | -3.97 |
| Challenger | 0.68464 | 0.24579 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.343, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

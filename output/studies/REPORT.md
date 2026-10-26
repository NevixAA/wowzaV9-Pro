# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 47%, since 10 Aug **54%**.
- Tip period, 127 matches with a clean Bet365 price: BTTS happened 56% while the de-vigged price implied 43% (gap 13.3 points).
- **B, blind YES on every match: +23%** [+7%, +40%], n 127.
- A, matches Wowza picked: +27%; matches it did not pick: +19%. Difference +8% [-20%, +33%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.2478 vs 0.278; residual z -0.06 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (115 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1453 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 258 | 60% | 50% | 65% | -10.4 | +4.7 |
| UNDER 5-10pp | 289 | 62% | 52% | 59% | -9.9 | -2.4 |
| UNDER 2-5pp | 193 | 58% | 52% | 55% | -5.6 | -2.2 |
| agrees (±2pp) | 323 | 51% | 52% | 52% | +0.7 | +0.7 |
| OVER 2-5pp | 184 | 47% | 52% | 48% | +4.5 | +1.1 |
| OVER 5-10pp | 153 | 45% | 52% | 45% | +7.3 | +0.2 |
| model OVER by >10pp | 53 | 43% | 54% | 42% | +10.7 | -1.8 |

- Share of the model's lean that showed up in results: leaning UNDER 0.013, leaning OVER -0.056 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1453 | 0.24245 | 0.24817 | +0.00152 | [-0.0004, +0.0035] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 787 | 0.23995 | 0.24618 | +0.00836 | [+0.0040, +0.0137] | MODEL_HURTS |
| OU25 | standard | 666 | 0.24542 | 0.25053 | +0.00649 | [-0.0005, +0.0139] | NO_DETECTABLE_GAIN |
| OU35 | all | 418 | 0.23426 | 0.24661 | +0.05593 | [+0.0094, +0.1184] | MODEL_HURTS |
| OU35 | new_format | 317 | 0.23535 | 0.25116 | +0.04768 | [+0.0100, +0.0950] | MODEL_HURTS |
| OU35 | standard | 101 | 0.23084 | 0.23236 | -0.01603 | [-0.0367, -0.0011] | MODEL_ADDS_INFORMATION |
| BTTS | all | 1449 | 0.24161 | 0.24439 | +0.01074 | [+0.0046, +0.0175] | MODEL_HURTS |
| BTTS | new_format | 792 | 0.24008 | 0.24237 | +0.00776 | [+0.0035, +0.0118] | MODEL_HURTS |
| BTTS | standard | 657 | 0.24346 | 0.24684 | +0.00591 | [-0.0040, +0.0175] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

21 cells tested (of 39; the rest are too small). Pooled prior +1.6%, between-cell sd 0.12. Reality-check p for the best cell: **0.107**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 91 | +26% | +13% | 0.93 | 0.17 | [-5.3, +2.0] | PAPER (n 91 < 150) |
| Brazil Serie A | ou25 | 28 | +47% | +12% | 0.87 | 0.17 | [-7.4, +2.5] | PAPER (n 28 < 150) |
| Brazil Serie A | btts | 20 | +24% | +6% | 0.69 | 0.82 | [-21.0, +17.7] | PAPER (n 20 < 150) |
| Serie B | ou25 | 23 | +19% | +5% | 0.68 | 0.82 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Sweden Allsvenskan | ou25 | 37 | +16% | +5% | 0.68 | 0.82 | [-4.7, +3.1] | PAPER (n 37 < 150) |
| Argentina Primera Division | ou25 | 33 | +15% | +4% | 0.63 | 0.82 | [-4.2, +5.4] | PAPER (n 33 < 150) |
| Japan J-League | ou25 | 32 | +9% | +4% | 0.63 | 0.82 | [-3.5, +8.9] | PAPER (n 32 < 150) |
| Mexico Liga MX | ou25 | 36 | +8% | +3% | 0.62 | 0.82 | [-3.1, +6.8] | PAPER (CLV deterioration alarm) |
| Argentina Primera Division | over15 | 98 | +4% | +3% | 0.64 | 0.82 | [+0.2, +2.9] | PAPER (n 98 < 150) |
| Finland Veikkausliiga | ou25 | 22 | +4% | +2% | 0.57 | 0.92 | [-5.7, +5.8] | PAPER (n 22 < 150) |
| La Liga 2 | ou25 | 38 | -4% | +1% | 0.52 | 0.98 | [-2.4, +4.1] | PAPER (n 38 < 150) |
| Japan J-League | btts | 10 | -18% | -0% | 0.49 | 0.98 | – | PAPER (n 10 < 150) |
| Bundesliga 2 | ou25 | 18 | -15% | -1% | 0.48 | 0.98 | [-10.9, +8.8] | PAPER (n 18 < 150) |
| La Liga 2 | btts | 10 | -22% | -1% | 0.47 | 0.98 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| Denmark Superliga | ou25 | 25 | -15% | -2% | 0.44 | 0.98 | [-5.4, +5.7] | PAPER (n 25 < 150) |
| Ireland Premier Division | ou25 | 20 | -25% | -3% | 0.39 | 0.98 | [-9.7, +2.8] | PAPER (n 20 < 150) |
| Norway Eliteserien | ou25 | 26 | -32% | -4% | 0.37 | 0.98 | [-10.5, +4.3] | PAPER (n 26 < 150) |
| Austrian Bundesliga | ou25 | 23 | -30% | -4% | 0.35 | 0.98 | [-13.1, +2.5] | PAPER (n 23 < 150) |
| China Super League | ou25 | 32 | -24% | -4% | 0.35 | 0.98 | [-9.3, +2.6] | PAPER (n 32 < 150) |
| Championship | ou25 | 25 | -32% | -6% | 0.30 | 0.98 | [-7.8, +5.4] | PAPER (n 25 < 150) |
| League One | ou25 | 23 | -49% | -9% | 0.22 | 0.98 | [-7.7, +3.5] | PAPER (n 23 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1159 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68406 | 0.24554 | – | – | – | – | – |
| v9 | 0.69489 | 0.25084 | 319 | 0.796 | -27.49 | -9% | -3.97 |
| Challenger | 0.685 | 0.24597 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.301, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

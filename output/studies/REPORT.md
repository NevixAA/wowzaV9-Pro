# Upgrade studies — October 2026

Research only. Nothing here changes v9, a threshold or a stake.

## 1. Argentina BTTS: model, league, bookmaker, or luck?

- BTTS rate, all Argentina matches: 2025 **38%**, 2026 48%, since 10 Aug **55%**.
- Tip period, 164 matches with a clean Bet365 price: BTTS happened 55% while the de-vigged price implied 43% (gap 12.3 points).
- **B, blind YES on every match: +21%** [+6%, +36%], n 164.
- A, matches Wowza picked: +26%; matches it did not pick: +17%. Difference +9% [-15%, +30%] — **not distinguishable from zero**.
- Model vs market on the same matches: Brier 0.25 vs 0.2716; residual z -0.46 (no fixture-level signal beyond the level).
- C, a cheap bookmaker: no book's YES price ever beat the others' de-vigged consensus (150 fixtures). The whole market is behind, not one book.
- 51 Bet365 price pairs were the FIRST-HALF BTTS market and were dropped (YES 8.00 / NO 1.08 passes a margin check).

**Reading.** The profit is a league scoring regime the market has priced slowly, not model selection. Wowza's contribution is being more bullish on YES than the market. If the league reverts toward 2025's rate, so does the edge. Watch the gap between realised and implied.

## 2. The UNDER problem

- 1829 O/U 2.5 fixtures, every priced one (not only tips).
- The model's P(over) barely moves: it sits around 52% in every band while the market ranges 41–67%. Disagreement therefore comes from the MARKET moving, not the model knowing.

| Model leans | n | Realised over | Model | Market | Model error | Market error |
|---|---|---|---|---|---|---|
| model UNDER by >10pp | 355 | 63% | 50% | 65% | -13.4 | +1.7 |
| UNDER 5-10pp | 365 | 61% | 52% | 59% | -9.0 | -1.6 |
| UNDER 2-5pp | 249 | 57% | 52% | 55% | -4.8 | -1.3 |
| agrees (±2pp) | 394 | 51% | 52% | 52% | +0.7 | +0.7 |
| OVER 2-5pp | 222 | 47% | 52% | 48% | +4.9 | +1.4 |
| OVER 5-10pp | 180 | 46% | 53% | 46% | +6.6 | -0.4 |
| model OVER by >10pp | 64 | 44% | 55% | 42% | +10.9 | -1.6 |

- Share of the model's lean that showed up in results: leaning UNDER -0.032, leaning OVER -0.052 (1 = all of it, 0 = none; negative = the result moved the other way).

**Reading.** UNDER tips come from matches the market rates high-scoring while the model stays near 52%. The market is right. The fix is in the probability: anchor on the market and add the model only as a small, fitted residual — whose fitted weight is currently about zero.

## 3. Does the model add anything once the price is known?

| Market | Track | n | Brier market | Brier model | Out-of-sample Δ log-loss | 90% CI | Verdict |
|---|---|---|---|---|---|---|---|
| OU25 | all | 1829 | 0.24145 | 0.24908 | +0.00105 | [-0.0007, +0.0030] | NO_DETECTABLE_GAIN |
| OU25 | new_format | 996 | 0.23775 | 0.24789 | +0.00726 | [+0.0025, +0.0123] | MODEL_HURTS |
| OU25 | standard | 833 | 0.24587 | 0.25049 | +0.00303 | [-0.0013, +0.0079] | NO_DETECTABLE_GAIN |
| OU15 | all | 246 | 0.1985 | 0.19896 | -0.00151 | [-0.0141, +0.0077] | NO_DETECTABLE_GAIN |
| OU15 | new_format | 152 | 0.1974 | 0.19855 | -0.00321 | [-0.0080, +0.0016] | NO_DETECTABLE_GAIN |
| OU35 | all | 666 | 0.22595 | 0.23772 | +0.07546 | [+0.0315, +0.1288] | MODEL_HURTS |
| OU35 | new_format | 458 | 0.2276 | 0.24469 | +0.04612 | [+0.0189, +0.0795] | MODEL_HURTS |
| OU35 | standard | 208 | 0.22232 | 0.22238 | -0.00093 | [-0.0139, +0.0142] | NO_DETECTABLE_GAIN |
| BTTS | all | 1831 | 0.24208 | 0.24488 | +0.00054 | [-0.0009, +0.0021] | NO_DETECTABLE_GAIN |
| BTTS | new_format | 1007 | 0.24028 | 0.24305 | +0.01058 | [+0.0039, +0.0182] | MODEL_HURTS |
| BTTS | standard | 824 | 0.24428 | 0.24712 | +0.00076 | [-0.0042, +0.0062] | NO_DETECTABLE_GAIN |

Negative Δ = adding the model improved the forecast. No market × track shows an improvement; several are made worse. O/U stays PAPER regardless of short ROI windows.

## 4. Evidence per cell (staked tips since 10 Aug)

22 cells tested (of 40; the rest are too small). Pooled prior -2.7%, between-cell sd 0.00. Reality-check p for the best cell: **0.44**.

| League | Market | n | Raw ROI | Shrunk ROI | P(edge>0) | FDR q | CLV 90% CS | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Argentina Primera Division | btts | 102 | +21% | -3% | 0.27 | 0.84 | [-4.7, +1.8] | PAPER (n 102 < 150) |
| Argentina Primera Division | ou25 | 35 | +14% | -3% | 0.27 | 0.97 | [-3.8, +5.1] | PAPER (n 35 < 150) |
| Argentina Primera Division | over15 | 105 | +6% | -3% | 0.27 | 0.97 | [+0.2, +2.8] | PAPER (n 105 < 150) |
| Austrian Bundesliga | ou25 | 24 | -33% | -3% | 0.27 | 0.97 | [-12.6, +2.1] | PAPER (n 24 < 150) |
| Brazil Serie A | btts | 21 | +28% | -3% | 0.27 | 0.97 | [-21.0, +17.7] | PAPER (n 21 < 150) |
| Brazil Serie A | ou25 | 37 | +16% | -3% | 0.27 | 0.97 | [-8.1, +2.0] | PAPER (CLV deterioration alarm) |
| Bundesliga 2 | ou25 | 20 | -24% | -3% | 0.27 | 0.97 | [-9.1, +9.3] | PAPER (n 20 < 150) |
| Championship | ou25 | 31 | -29% | -3% | 0.27 | 0.97 | [-6.0, +4.9] | PAPER (n 31 < 150) |
| China Super League | ou25 | 33 | -18% | -3% | 0.27 | 0.97 | [-9.1, +2.3] | PAPER (n 33 < 150) |
| Denmark Superliga | ou25 | 33 | -14% | -3% | 0.27 | 0.97 | [-3.8, +5.4] | PAPER (n 33 < 150) |
| Finland Veikkausliiga | ou25 | 28 | -10% | -3% | 0.27 | 0.97 | [-22.3, +33.9] | PAPER (CLV deterioration alarm) |
| Ireland Premier Division | ou25 | 24 | -30% | -3% | 0.27 | 0.97 | [-8.1, +1.9] | PAPER (n 24 < 150) |
| Japan J-League | btts | 11 | -25% | -3% | 0.27 | 0.97 | – | PAPER (n 11 < 150) |
| Japan J-League | ou25 | 36 | -3% | -3% | 0.27 | 0.97 | [-3.1, +7.5] | PAPER (n 36 < 150) |
| La Liga 2 | btts | 10 | -22% | -3% | 0.27 | 0.97 | [-8.4, +5.7] | PAPER (n 10 < 150) |
| La Liga 2 | ou25 | 39 | -7% | -3% | 0.27 | 0.97 | [-2.3, +3.9] | PAPER (n 39 < 150) |
| League One | ou25 | 26 | -44% | -3% | 0.27 | 0.98 | [-6.8, +2.7] | PAPER (n 26 < 150) |
| League Two | ou25 | 19 | +5% | -3% | 0.27 | 0.97 | [-3.0, +6.7] | PAPER (n 19 < 150) |
| Mexico Liga MX | ou25 | 46 | +1% | -3% | 0.27 | 0.97 | [-1.1, +6.8] | PAPER (CLV deterioration alarm) |
| Norway Eliteserien | ou25 | 27 | -26% | -3% | 0.27 | 0.97 | [-10.0, +4.1] | PAPER (n 27 < 150) |
| Serie B | ou25 | 23 | +19% | -3% | 0.27 | 0.97 | [-0.9, +11.5] | PAPER (n 23 < 150) |
| Sweden Allsvenskan | ou25 | 50 | +6% | -3% | 0.27 | 0.97 | [-3.9, +2.3] | PAPER (n 50 < 150) |

## 5. Market-anchored O/U 2.5 challenger

`logit p = a + b·logit(market) + c·logit(v9)`, refitted weekly, c ≥ 0. Decision-time market only (never the close). 1536 out-of-sample fixtures.

| | Log loss | Brier | Tips at 5% edge | UNDER share | Units | ROI | Mean CLV (pp) |
|---|---|---|---|---|---|---|---|
| Market | 0.68058 | 0.24385 | – | – | – | – | – |
| v9 | 0.69486 | 0.25083 | 459 | 0.843 | -50.55 | -11% | -3.98 |
| Challenger | 0.68138 | 0.24421 | 0 | – | – | – | – |

Current weights: c (model) = 0.0 — unconstrained fit -0.387, i.e. given the market, v9's lean points the WRONG way, so it gets no say. Forward record: `output/studies/ou_challenger_forward.csv` (first sight, never revised).

Gates for a TINY_REAL review: n ≥ 150, P(edge>0) ≥ 0.80, FDR q ≤ 0.10, no CLV deterioration alarm. Recommendations only; the execution policy changes by a human-approved commit.

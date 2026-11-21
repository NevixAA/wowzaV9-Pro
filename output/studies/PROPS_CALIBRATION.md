# Props calibration — live v9 model vs what happened (2026-11-21 14:51 UTC)

Settled prop tips to 2026-11-20. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 660 | 20.8% | 20.0% | -0.8% | [-0.0348, 0.018] | CALIBRATED | 8% vs 29% (n 12) |
| cards | 4383 | 17.6% | 20.4% | +2.8% | [0.0184, 0.0384] | UNDER_PREDICTS | 22% vs 27% (n 107) |
| goals | 2183 | 26.7% | 27.0% | +0.3% | [-0.0139, 0.0221] | CALIBRATED | 27% vs 34% (n 1032) |
| goals2 | 1 | 15.1% | 0.0% | -15.1% | [None, None] | INSUFFICIENT | — |
| sot | 7229 | 32.4% | 39.4% | +7.0% | [0.0593, 0.0807] | UNDER_PREDICTS | 39% vs 56% (n 1185) |
| sot2 | 930 | 25.5% | 27.3% | +1.8% | [0.0007, 0.0339] | UNDER_PREDICTS | 24% vs 40% (n 146) |
| sot3 | 22 | 27.9% | 22.7% | -5.1% | [None, None] | INSUFFICIENT | 100% vs 38% (n 1) |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 32 | 22.2% | 21.9% | -0.3% |
| assists | 2026-09 | 73 | 21.1% | 21.9% | +0.8% |
| assists | 2026-10 | 564 | 20.4% | 21.5% | +1.0% |
| assists | 2026-11 | 347 | 21.1% | 19.0% | -2.1% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 295 | 17.2% | 15.9% | -1.3% |
| cards | 2026-09 | 494 | 17.4% | 22.5% | +5.0% |
| cards | 2026-10 | 4264 | 17.5% | 19.8% | +2.3% |
| cards | 2026-11 | 2219 | 17.7% | 20.3% | +2.6% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 244 | 23.9% | 26.6% | +2.7% |
| goals | 2026-09 | 383 | 24.6% | 27.9% | +3.3% |
| goals | 2026-10 | 1777 | 24.9% | 28.2% | +3.3% |
| goals | 2026-11 | 1184 | 27.2% | 25.4% | -1.8% |
| goals2 | 2026-11 | 1 | 15.1% | 0.0% | -15.1% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1349 | 30.2% | 36.6% | +6.4% |
| sot | 2026-09 | 2303 | 30.3% | 40.0% | +9.7% |
| sot | 2026-10 | 7371 | 30.4% | 40.9% | +10.5% |
| sot | 2026-11 | 3765 | 33.0% | 38.4% | +5.4% |
| sot2 | 2026-06 | 2 | 22.4% | 0.0% | -22.4% |
| sot2 | 2026-08 | 70 | 27.0% | 45.7% | +18.7% |
| sot2 | 2026-09 | 175 | 26.8% | 30.3% | +3.5% |
| sot2 | 2026-10 | 683 | 24.7% | 29.9% | +5.1% |
| sot2 | 2026-11 | 532 | 26.0% | 26.5% | +0.5% |
| sot3 | 2026-08 | 1 | 15.5% | 100.0% | +84.5% |
| sot3 | 2026-09 | 1 | 18.8% | 100.0% | +81.2% |
| sot3 | 2026-10 | 16 | 26.4% | 18.8% | -7.7% |
| sot3 | 2026-11 | 11 | 27.7% | 36.4% | +8.7% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

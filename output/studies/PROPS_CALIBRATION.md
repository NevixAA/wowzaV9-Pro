# Props calibration — live v9 model vs what happened (2026-11-14 13:41 UTC)

Settled prop tips to 2026-11-13. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 735 | 20.7% | 21.4% | +0.7% | [-0.0183, 0.0327] | CALIBRATED | 10% vs 30% (n 10) |
| cards | 5033 | 17.6% | 19.4% | +1.8% | [0.0081, 0.0289] | UNDER_PREDICTS | 21% vs 26% (n 152) |
| goals | 2457 | 26.2% | 27.3% | +1.1% | [-0.005, 0.0291] | CALIBRATED | 27% vs 34% (n 1124) |
| goals2 | 1 | 15.1% | 0.0% | -15.1% | [None, None] | INSUFFICIENT | — |
| sot | 8503 | 31.8% | 39.8% | +7.9% | [0.068, 0.0911] | UNDER_PREDICTS | 39% vs 56% (n 1365) |
| sot2 | 984 | 25.3% | 28.4% | +3.0% | [0.0098, 0.049] | UNDER_PREDICTS | 24% vs 40% (n 153) |
| sot3 | 23 | 27.0% | 30.4% | +3.4% | [None, None] | INSUFFICIENT | 100% vs 38% (n 1) |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 32 | 22.2% | 21.9% | -0.3% |
| assists | 2026-09 | 72 | 21.1% | 22.2% | +1.1% |
| assists | 2026-10 | 547 | 20.4% | 21.4% | +0.9% |
| assists | 2026-11 | 279 | 21.1% | 20.4% | -0.6% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 291 | 17.2% | 16.2% | -1.1% |
| cards | 2026-09 | 487 | 17.4% | 22.4% | +4.9% |
| cards | 2026-10 | 4126 | 17.5% | 19.7% | +2.2% |
| cards | 2026-11 | 1765 | 17.6% | 19.9% | +2.2% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 244 | 23.9% | 26.6% | +2.7% |
| goals | 2026-09 | 382 | 24.6% | 28.0% | +3.4% |
| goals | 2026-10 | 1746 | 25.0% | 28.4% | +3.4% |
| goals | 2026-11 | 999 | 27.6% | 25.5% | -2.0% |
| goals2 | 2026-11 | 1 | 15.1% | 0.0% | -15.1% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1349 | 30.2% | 36.6% | +6.4% |
| sot | 2026-09 | 2288 | 30.3% | 40.0% | +9.7% |
| sot | 2026-10 | 7158 | 30.5% | 40.8% | +10.4% |
| sot | 2026-11 | 3179 | 33.4% | 38.4% | +5.0% |
| sot2 | 2026-06 | 2 | 22.4% | 0.0% | -22.4% |
| sot2 | 2026-08 | 70 | 27.0% | 45.7% | +18.7% |
| sot2 | 2026-09 | 174 | 26.8% | 30.5% | +3.7% |
| sot2 | 2026-10 | 673 | 24.8% | 29.7% | +5.0% |
| sot2 | 2026-11 | 442 | 26.2% | 27.4% | +1.2% |
| sot3 | 2026-08 | 1 | 15.5% | 100.0% | +84.5% |
| sot3 | 2026-09 | 1 | 18.8% | 100.0% | +81.2% |
| sot3 | 2026-10 | 16 | 26.4% | 18.8% | -7.7% |
| sot3 | 2026-11 | 9 | 27.3% | 44.4% | +17.1% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

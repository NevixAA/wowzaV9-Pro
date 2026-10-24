# Props calibration — live v9 model vs what happened (2026-10-24 11:13 UTC)

Settled prop tips to 2026-10-23. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 242 | 20.4% | 21.9% | +1.5% | [-0.03, 0.0621] | CALIBRATED | 0% vs 44% (n 1) |
| cards | 1934 | 17.4% | 19.3% | +1.9% | [0.0034, 0.0415] | UNDER_PREDICTS | 14% vs 22% (n 36) |
| goals | 722 | 23.7% | 29.2% | +5.5% | [0.0344, 0.0802] | UNDER_PREDICTS | 30% vs 34% (n 236) |
| sot | 3480 | 29.3% | 42.1% | +12.8% | [0.1166, 0.1458] | UNDER_PREDICTS | 37% vs 55% (n 270) |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 27 | 20.7% | 22.2% | +1.5% |
| assists | 2026-09 | 21 | 19.7% | 23.8% | +4.1% |
| assists | 2026-10 | 232 | 20.3% | 22.0% | +1.7% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 249 | 17.2% | 16.1% | -1.1% |
| cards | 2026-09 | 173 | 17.2% | 23.7% | +6.5% |
| cards | 2026-10 | 1868 | 17.4% | 18.7% | +1.4% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 221 | 24.0% | 27.1% | +3.2% |
| goals | 2026-09 | 122 | 23.7% | 24.6% | +0.9% |
| goals | 2026-10 | 702 | 23.7% | 29.3% | +5.6% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1182 | 30.4% | 36.3% | +5.9% |
| sot | 2026-09 | 794 | 29.4% | 41.1% | +11.7% |
| sot | 2026-10 | 3357 | 29.3% | 41.9% | +12.5% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

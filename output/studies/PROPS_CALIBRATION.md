# Props calibration — live v9 model vs what happened (2026-10-25 11:42 UTC)

Settled prop tips to 2026-10-24. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 324 | 20.4% | 21.9% | +1.5% | [-0.0208, 0.0502] | CALIBRATED | 0% vs 44% (n 1) |
| cards | 2422 | 17.4% | 19.6% | +2.2% | [0.0074, 0.0401] | UNDER_PREDICTS | 17% vs 23% (n 41) |
| goals | 955 | 24.0% | 27.9% | +3.8% | [0.0153, 0.0705] | UNDER_PREDICTS | 27% vs 34% (n 362) |
| sot | 4283 | 29.6% | 41.8% | +12.2% | [0.1112, 0.1391] | UNDER_PREDICTS | 36% vs 55% (n 435) |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 27 | 20.7% | 22.2% | +1.5% |
| assists | 2026-09 | 21 | 19.7% | 23.8% | +4.1% |
| assists | 2026-10 | 314 | 20.4% | 22.0% | +1.6% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 249 | 17.2% | 16.1% | -1.1% |
| cards | 2026-09 | 173 | 17.2% | 23.7% | +6.5% |
| cards | 2026-10 | 2356 | 17.4% | 19.2% | +1.8% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 221 | 24.0% | 27.1% | +3.2% |
| goals | 2026-09 | 122 | 23.7% | 24.6% | +0.9% |
| goals | 2026-10 | 935 | 24.0% | 27.9% | +3.9% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1182 | 30.4% | 36.3% | +5.9% |
| sot | 2026-09 | 794 | 29.4% | 41.1% | +11.7% |
| sot | 2026-10 | 4160 | 29.7% | 41.6% | +11.9% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

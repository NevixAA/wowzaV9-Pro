# Props calibration — live v9 model vs what happened (2026-10-30 13:06 UTC)

Settled prop tips to 2026-10-29. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 410 | 20.5% | 20.7% | +0.2% | [-0.0288, 0.0322] | CALIBRATED | 12% vs 31% (n 8) |
| cards | 2985 | 17.4% | 19.4% | +2.0% | [0.0062, 0.0344] | UNDER_PREDICTS | 20% vs 26% (n 107) |
| goals | 1259 | 24.7% | 28.9% | +4.2% | [0.0209, 0.07] | UNDER_PREDICTS | 29% vs 34% (n 555) |
| sot | 5197 | 30.1% | 41.3% | +11.1% | [0.1, 0.1258] | UNDER_PREDICTS | 38% vs 56% (n 738) |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 27 | 20.7% | 22.2% | +1.5% |
| assists | 2026-09 | 21 | 19.7% | 23.8% | +4.1% |
| assists | 2026-10 | 410 | 20.5% | 20.7% | +0.2% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 249 | 17.2% | 16.1% | -1.1% |
| cards | 2026-09 | 173 | 17.2% | 23.7% | +6.5% |
| cards | 2026-10 | 2984 | 17.4% | 19.4% | +2.0% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 221 | 24.0% | 27.1% | +3.2% |
| goals | 2026-09 | 122 | 23.7% | 24.6% | +0.9% |
| goals | 2026-10 | 1259 | 24.7% | 28.9% | +4.2% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1182 | 30.4% | 36.3% | +5.9% |
| sot | 2026-09 | 794 | 29.4% | 41.1% | +11.7% |
| sot | 2026-10 | 5196 | 30.1% | 41.3% | +11.1% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

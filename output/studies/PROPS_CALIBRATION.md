# Props calibration — live v9 model vs what happened (2026-10-28 11:47 UTC)

Settled prop tips to 2026-10-27. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 385 | 20.5% | 21.0% | +0.6% | [-0.0269, 0.0356] | CALIBRATED | 14% vs 32% (n 7) |
| cards | 2823 | 17.4% | 19.6% | +2.2% | [0.007, 0.036] | UNDER_PREDICTS | 18% vs 26% (n 96) |
| goals | 1175 | 24.5% | 29.0% | +4.6% | [0.0245, 0.0742] | UNDER_PREDICTS | 29% vs 34% (n 518) |
| sot | 4962 | 30.0% | 41.4% | +11.4% | [0.1016, 0.1309] | UNDER_PREDICTS | 38% vs 56% (n 682) |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 27 | 20.7% | 22.2% | +1.5% |
| assists | 2026-09 | 21 | 19.7% | 23.8% | +4.1% |
| assists | 2026-10 | 385 | 20.5% | 21.0% | +0.6% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 249 | 17.2% | 16.1% | -1.1% |
| cards | 2026-09 | 173 | 17.2% | 23.7% | +6.5% |
| cards | 2026-10 | 2817 | 17.4% | 19.5% | +2.1% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 221 | 24.0% | 27.1% | +3.2% |
| goals | 2026-09 | 122 | 23.7% | 24.6% | +0.9% |
| goals | 2026-10 | 1172 | 24.5% | 28.9% | +4.5% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1182 | 30.4% | 36.3% | +5.9% |
| sot | 2026-09 | 794 | 29.4% | 41.1% | +11.7% |
| sot | 2026-10 | 4949 | 30.0% | 41.4% | +11.4% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

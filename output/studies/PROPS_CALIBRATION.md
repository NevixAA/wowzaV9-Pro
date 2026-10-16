# Props calibration — live v9 model vs what happened (2026-10-16 11:34 UTC)

Settled prop tips to 2026-10-15. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 101 | 20.3% | 20.8% | +0.5% | [-0.0545, 0.0881] | CALIBRATED | 33% vs 34% (n 3) |
| cards | 828 | 17.4% | 22.1% | +4.7% | [0.0236, 0.0715] | UNDER_PREDICTS | 11% vs 22% (n 9) |
| goals | 295 | 23.8% | 29.2% | +5.3% | [0.0117, 0.1108] | UNDER_PREDICTS | 32% vs 35% (n 74) |
| sot | 1875 | 29.1% | 41.8% | +12.7% | [0.1077, 0.1542] | UNDER_PREDICTS | 29% vs 54% (n 94) |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 27 | 20.7% | 22.2% | +1.5% |
| assists | 2026-09 | 21 | 19.7% | 23.8% | +4.1% |
| assists | 2026-10 | 87 | 20.2% | 20.7% | +0.5% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 249 | 17.2% | 16.1% | -1.1% |
| cards | 2026-09 | 173 | 17.2% | 23.7% | +6.5% |
| cards | 2026-10 | 723 | 17.4% | 21.4% | +4.0% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 221 | 24.0% | 27.1% | +3.2% |
| goals | 2026-09 | 122 | 23.7% | 24.6% | +0.9% |
| goals | 2026-10 | 242 | 24.1% | 31.4% | +7.3% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1182 | 30.4% | 36.3% | +5.9% |
| sot | 2026-09 | 794 | 29.4% | 41.1% | +11.7% |
| sot | 2026-10 | 1504 | 29.3% | 42.5% | +13.2% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

# Props calibration — live v9 model vs what happened (2026-10-23 11:48 UTC)

Settled prop tips to 2026-10-22. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 227 | 20.4% | 22.0% | +1.6% | [-0.0312, 0.0666] | CALIBRATED | 0% vs 44% (n 1) |
| cards | 1784 | 17.4% | 19.6% | +2.2% | [0.0054, 0.0461] | UNDER_PREDICTS | 15% vs 22% (n 34) |
| goals | 667 | 23.6% | 29.4% | +5.8% | [0.0361, 0.0849] | UNDER_PREDICTS | 30% vs 34% (n 216) |
| sot | 3276 | 29.2% | 42.3% | +13.1% | [0.1205, 0.15] | UNDER_PREDICTS | 37% vs 56% (n 238) |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 27 | 20.7% | 22.2% | +1.5% |
| assists | 2026-09 | 21 | 19.7% | 23.8% | +4.1% |
| assists | 2026-10 | 217 | 20.3% | 22.1% | +1.8% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 249 | 17.2% | 16.1% | -1.1% |
| cards | 2026-09 | 173 | 17.2% | 23.7% | +6.5% |
| cards | 2026-10 | 1718 | 17.4% | 19.0% | +1.6% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 221 | 24.0% | 27.1% | +3.2% |
| goals | 2026-09 | 122 | 23.7% | 24.6% | +0.9% |
| goals | 2026-10 | 647 | 23.7% | 29.5% | +5.8% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1182 | 30.4% | 36.3% | +5.9% |
| sot | 2026-09 | 794 | 29.4% | 41.1% | +11.7% |
| sot | 2026-10 | 3153 | 29.3% | 42.1% | +12.8% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

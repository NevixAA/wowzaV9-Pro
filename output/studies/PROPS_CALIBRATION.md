# Props calibration — live v9 model vs what happened (2026-10-15 08:04 UTC)

Settled prop tips to 2026-10-14. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 93 | 20.2% | 18.3% | -1.9% | [-0.0715, 0.0524] | INSUFFICIENT | 33% vs 34% (n 3) |
| cards | 787 | 17.4% | 22.2% | +4.9% | [0.0236, 0.0749] | UNDER_PREDICTS | 11% vs 22% (n 9) |
| goals | 282 | 24.1% | 28.0% | +3.9% | [0.0001, 0.0832] | UNDER_PREDICTS | 28% vs 34% (n 67) |
| sot | 1796 | 29.2% | 42.0% | +12.8% | [0.1071, 0.1592] | UNDER_PREDICTS | 31% vs 54% (n 87) |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 27 | 20.7% | 22.2% | +1.5% |
| assists | 2026-09 | 21 | 19.7% | 23.8% | +4.1% |
| assists | 2026-10 | 79 | 20.1% | 17.7% | -2.4% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 249 | 17.2% | 16.1% | -1.1% |
| cards | 2026-09 | 173 | 17.2% | 23.7% | +6.5% |
| cards | 2026-10 | 681 | 17.4% | 21.6% | +4.2% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 221 | 24.0% | 27.1% | +3.2% |
| goals | 2026-09 | 122 | 23.7% | 24.6% | +0.9% |
| goals | 2026-10 | 225 | 24.3% | 29.8% | +5.5% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1182 | 30.4% | 36.3% | +5.9% |
| sot | 2026-09 | 794 | 29.4% | 41.1% | +11.7% |
| sot | 2026-10 | 1411 | 29.4% | 42.6% | +13.2% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

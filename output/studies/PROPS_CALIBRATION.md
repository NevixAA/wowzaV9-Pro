# Props calibration — live v9 model vs what happened (2026-11-01 15:48 UTC)

Settled prop tips to 2026-10-31. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 484 | 20.5% | 21.5% | +1.0% | [-0.0174, 0.038] | CALIBRATED | 12% vs 31% (n 8) |
| cards | 3514 | 17.5% | 19.6% | +2.1% | [0.0092, 0.0327] | UNDER_PREDICTS | 20% vs 26% (n 107) |
| goals | 1491 | 25.0% | 29.0% | +4.0% | [0.0227, 0.0625] | UNDER_PREDICTS | 28% vs 34% (n 644) |
| sot | 6018 | 30.4% | 41.1% | +10.7% | [0.0933, 0.1222] | UNDER_PREDICTS | 38% vs 56% (n 817) |
| sot2 | 357 | 24.8% | 30.5% | +5.7% | [0.0349, 0.082] | UNDER_PREDICTS | 26% vs 40% (n 54) |
| sot3 | 9 | 26.7% | 22.2% | -4.4% | [None, None] | INSUFFICIENT | — |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 27 | 20.7% | 22.2% | +1.5% |
| assists | 2026-09 | 21 | 19.7% | 23.8% | +4.1% |
| assists | 2026-10 | 484 | 20.5% | 21.5% | +1.0% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 249 | 17.2% | 16.1% | -1.1% |
| cards | 2026-09 | 173 | 17.2% | 23.7% | +6.5% |
| cards | 2026-10 | 3514 | 17.5% | 19.6% | +2.1% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 221 | 24.0% | 27.1% | +3.2% |
| goals | 2026-09 | 122 | 23.7% | 24.6% | +0.9% |
| goals | 2026-10 | 1491 | 25.0% | 29.0% | +4.0% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1182 | 30.4% | 36.3% | +5.9% |
| sot | 2026-09 | 797 | 29.3% | 40.9% | +11.6% |
| sot | 2026-10 | 6018 | 30.4% | 41.1% | +10.7% |
| sot2 | 2026-06 | 2 | 22.4% | 0.0% | -22.4% |
| sot2 | 2026-08 | 33 | 27.1% | 51.5% | +24.4% |
| sot2 | 2026-09 | 37 | 30.0% | 29.7% | -0.3% |
| sot2 | 2026-10 | 357 | 24.8% | 30.5% | +5.7% |
| sot3 | 2026-08 | 1 | 15.5% | 100.0% | +84.5% |
| sot3 | 2026-09 | 1 | 18.8% | 100.0% | +81.2% |
| sot3 | 2026-10 | 9 | 26.7% | 22.2% | -4.4% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

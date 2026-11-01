# Props calibration — live v9 model vs what happened (2026-11-01 18:19 UTC)

Settled prop tips to 2026-10-31. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 534 | 20.5% | 21.2% | +0.7% | [-0.0209, 0.0347] | CALIBRATED | 10% vs 30% (n 10) |
| cards | 4022 | 17.5% | 19.8% | +2.3% | [0.011, 0.0355] | UNDER_PREDICTS | 20% vs 26% (n 151) |
| goals | 1691 | 24.9% | 28.5% | +3.6% | [0.0205, 0.0555] | UNDER_PREDICTS | 28% vs 34% (n 785) |
| sot | 6971 | 30.4% | 40.9% | +10.5% | [0.0941, 0.1193] | UNDER_PREDICTS | 39% vs 56% (n 962) |
| sot2 | 647 | 24.8% | 30.3% | +5.5% | [0.0368, 0.076] | UNDER_PREDICTS | 25% vs 41% (n 96) |
| sot3 | 16 | 26.4% | 18.8% | -7.7% | [None, None] | INSUFFICIENT | — |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 32 | 22.2% | 21.9% | -0.3% |
| assists | 2026-09 | 65 | 21.2% | 18.5% | -2.7% |
| assists | 2026-10 | 534 | 20.5% | 21.2% | +0.7% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 289 | 17.2% | 15.9% | -1.3% |
| cards | 2026-09 | 474 | 17.5% | 23.0% | +5.5% |
| cards | 2026-10 | 4022 | 17.5% | 19.8% | +2.3% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 242 | 24.0% | 26.9% | +2.9% |
| goals | 2026-09 | 353 | 24.5% | 27.8% | +3.3% |
| goals | 2026-10 | 1691 | 24.9% | 28.5% | +3.6% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1340 | 30.2% | 36.7% | +6.5% |
| sot | 2026-09 | 2180 | 30.2% | 40.2% | +10.0% |
| sot | 2026-10 | 6971 | 30.4% | 40.9% | +10.5% |
| sot2 | 2026-06 | 2 | 22.4% | 0.0% | -22.4% |
| sot2 | 2026-08 | 65 | 27.3% | 46.2% | +18.9% |
| sot2 | 2026-09 | 157 | 26.8% | 29.9% | +3.2% |
| sot2 | 2026-10 | 647 | 24.8% | 30.3% | +5.5% |
| sot3 | 2026-08 | 1 | 15.5% | 100.0% | +84.5% |
| sot3 | 2026-09 | 1 | 18.8% | 100.0% | +81.2% |
| sot3 | 2026-10 | 16 | 26.4% | 18.8% | -7.7% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

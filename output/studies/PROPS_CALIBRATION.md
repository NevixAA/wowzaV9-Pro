# Props calibration — live v9 model vs what happened (2026-11-02 16:11 UTC)

Settled prop tips to 2026-11-01. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 601 | 20.4% | 20.8% | +0.4% | [-0.025, 0.0322] | CALIBRATED | 10% vs 30% (n 10) |
| cards | 4442 | 17.5% | 19.6% | +2.1% | [0.0091, 0.0322] | UNDER_PREDICTS | 20% vs 26% (n 157) |
| goals | 1926 | 25.2% | 28.2% | +3.1% | [0.0182, 0.0457] | UNDER_PREDICTS | 28% vs 34% (n 878) |
| sot | 7711 | 30.7% | 40.5% | +9.8% | [0.0865, 0.1114] | UNDER_PREDICTS | 39% vs 56% (n 1058) |
| sot2 | 750 | 24.9% | 28.9% | +4.1% | [0.0203, 0.0628] | UNDER_PREDICTS | 24% vs 40% (n 106) |
| sot3 | 17 | 25.9% | 17.6% | -8.2% | [None, None] | INSUFFICIENT | — |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 32 | 22.2% | 21.9% | -0.3% |
| assists | 2026-09 | 72 | 21.1% | 22.2% | +1.1% |
| assists | 2026-10 | 547 | 20.4% | 21.4% | +0.9% |
| assists | 2026-11 | 57 | 20.3% | 14.0% | -6.3% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 291 | 17.2% | 16.2% | -1.1% |
| cards | 2026-09 | 487 | 17.4% | 22.4% | +4.9% |
| cards | 2026-10 | 4126 | 17.5% | 19.7% | +2.2% |
| cards | 2026-11 | 328 | 17.7% | 17.4% | -0.3% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 244 | 23.9% | 26.6% | +2.7% |
| goals | 2026-09 | 382 | 24.6% | 28.0% | +3.4% |
| goals | 2026-10 | 1746 | 25.0% | 28.4% | +3.4% |
| goals | 2026-11 | 183 | 27.3% | 28.4% | +1.2% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1349 | 30.2% | 36.6% | +6.4% |
| sot | 2026-09 | 2288 | 30.3% | 40.0% | +9.7% |
| sot | 2026-10 | 7158 | 30.5% | 40.8% | +10.4% |
| sot | 2026-11 | 588 | 33.1% | 37.6% | +4.5% |
| sot2 | 2026-06 | 2 | 22.4% | 0.0% | -22.4% |
| sot2 | 2026-08 | 70 | 27.0% | 45.7% | +18.7% |
| sot2 | 2026-09 | 174 | 26.8% | 30.5% | +3.7% |
| sot2 | 2026-10 | 673 | 24.8% | 29.7% | +5.0% |
| sot2 | 2026-11 | 78 | 25.5% | 23.1% | -2.4% |
| sot3 | 2026-08 | 1 | 15.5% | 100.0% | +84.5% |
| sot3 | 2026-09 | 1 | 18.8% | 100.0% | +81.2% |
| sot3 | 2026-10 | 16 | 26.4% | 18.8% | -7.7% |
| sot3 | 2026-11 | 1 | 17.7% | 0.0% | -17.7% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

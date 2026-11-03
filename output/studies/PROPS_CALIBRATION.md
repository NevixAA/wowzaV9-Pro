# Props calibration — live v9 model vs what happened (2026-11-03 14:28 UTC)

Settled prop tips to 2026-11-02. Gap = realised hit rate minus the model's probability (positive = the model under-predicts). 90% CI by match day.

## Last 30 days

| Market | Tips | Predicted | Happened | Gap | 90% CI | Status | Priced: hit vs bookmaker |
|---|---|---|---|---|---|---|---|
| assists | 616 | 20.4% | 21.1% | +0.7% | [-0.02, 0.0361] | CALIBRATED | 10% vs 30% (n 10) |
| cards | 4513 | 17.5% | 19.9% | +2.3% | [0.0112, 0.0362] | UNDER_PREDICTS | 20% vs 25% (n 162) |
| goals | 1979 | 25.3% | 28.4% | +3.1% | [0.0194, 0.0452] | UNDER_PREDICTS | 28% vs 34% (n 902) |
| sot | 7856 | 30.8% | 40.4% | +9.6% | [0.0844, 0.1096] | UNDER_PREDICTS | 39% vs 56% (n 1103) |
| sot2 | 778 | 25.0% | 28.9% | +4.0% | [0.0196, 0.0613] | UNDER_PREDICTS | 24% vs 40% (n 114) |
| sot3 | 18 | 27.0% | 16.7% | -10.3% | [None, None] | INSUFFICIENT | — |

## By month

| Market | Month | Tips | Predicted | Happened | Gap |
|---|---|---|---|---|---|
| assists | 2026-08 | 32 | 22.2% | 21.9% | -0.3% |
| assists | 2026-09 | 72 | 21.1% | 22.2% | +1.1% |
| assists | 2026-10 | 547 | 20.4% | 21.4% | +0.9% |
| assists | 2026-11 | 73 | 20.1% | 17.8% | -2.3% |
| cards | 2026-06 | 93 | 36.9% | 7.5% | -29.4% |
| cards | 2026-07 | 46 | 38.4% | 10.9% | -27.6% |
| cards | 2026-08 | 291 | 17.2% | 16.2% | -1.1% |
| cards | 2026-09 | 487 | 17.4% | 22.4% | +4.9% |
| cards | 2026-10 | 4126 | 17.5% | 19.7% | +2.2% |
| cards | 2026-11 | 459 | 17.7% | 20.3% | +2.6% |
| goals | 2026-06 | 204 | 47.4% | 15.2% | -32.2% |
| goals | 2026-07 | 70 | 41.2% | 11.4% | -29.8% |
| goals | 2026-08 | 244 | 23.9% | 26.6% | +2.7% |
| goals | 2026-09 | 382 | 24.6% | 28.0% | +3.4% |
| goals | 2026-10 | 1746 | 25.0% | 28.4% | +3.4% |
| goals | 2026-11 | 239 | 27.4% | 29.7% | +2.3% |
| sot | 2026-06 | 93 | 57.4% | 29.0% | -28.4% |
| sot | 2026-07 | 1 | 64.1% | 100.0% | +35.9% |
| sot | 2026-08 | 1349 | 30.2% | 36.6% | +6.4% |
| sot | 2026-09 | 2288 | 30.3% | 40.0% | +9.7% |
| sot | 2026-10 | 7158 | 30.5% | 40.8% | +10.4% |
| sot | 2026-11 | 800 | 32.7% | 38.1% | +5.4% |
| sot2 | 2026-06 | 2 | 22.4% | 0.0% | -22.4% |
| sot2 | 2026-08 | 70 | 27.0% | 45.7% | +18.7% |
| sot2 | 2026-09 | 174 | 26.8% | 30.5% | +3.7% |
| sot2 | 2026-10 | 673 | 24.8% | 29.7% | +5.0% |
| sot2 | 2026-11 | 106 | 26.1% | 24.5% | -1.6% |
| sot3 | 2026-08 | 1 | 15.5% | 100.0% | +84.5% |
| sot3 | 2026-09 | 1 | 18.8% | 100.0% | +81.2% |
| sot3 | 2026-10 | 16 | 26.4% | 18.8% | -7.7% |
| sot3 | 2026-11 | 2 | 31.7% | 0.0% | -31.7% |

A rising hit rate with a positive gap is the model being too cautious about the starters it tips, not the model improving. Fixes under test: log-odds calibration (v9 PR calibration-logit-shadow) and Player V3's expected-minutes model. Props stay paper: priced tips still hit below the bookmaker's implied probability.

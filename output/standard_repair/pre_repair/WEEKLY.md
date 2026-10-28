# Standard repair - weekly (2026-10-26 12:40 UTC)

Production change: **NONE - research only; nothing here is read by v9**

New first-sight observations: 2499; new settlements: 0.

## Served model vs market (first sight, forward)

| market | n settled | weeks | dLL (v9 - market) | CI95 | CLV lean side | CLV coverage |
|---|---|---|---|---|---|---|
| BTTS | 430 | 8 | 0.002419 | [-0.013112, 0.012513] | -0.003 | 0.902 |
| OU15 | 2 | 2 | None | None | -0.0117 | 0.006 |
| OU25 | 443 | 9 | 0.01205 | [0.001424, 0.021738] | 0.0004 | 0.927 |

## Tracks

| track | diagnosis | forward n | forward dLL | next |
|---|---|---|---|---|
| STD-REPAIR-CHAMP-OU25-OVER | REGIME_DRIFT, NO_EDGE_YET | 42 | -0.00926 | Test a shorter recency window / league-environment reset at season start on the next untouched block. |
| STD-REPAIR-CHAMP-OU25-UNDER | CALIBRATION_FAILURE, NO_EDGE_YET | 38 | 0.013368 | Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage. |
| STD-REPAIR-CHAMP-BTTS-YES | NO_EDGE_YET | 20 | 0.009327 | Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout. |
| STD-REPAIR-CHAMP-BTTS-NO | MODEL_BELOW_MARKET, CALIBRATION_FAILURE, NO_EDGE_YET | 60 | 0.01643 | Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage. |
| STD-REPAIR-CHAMP-OU15-OVER | PRICE_QUALITY_PROBLEM, NO_EDGE_YET | 0 | None | Accumulate two-sided first-sight quotes (forward capture) before any model work; re-test residual on real quotes at n>=150. |
| STD-REPAIR-LEAGUE1-OU25-OVER | CALIBRATION_FAILURE, MODEL_ABOVE_MARKET_SELECTION_BAD, ODDS_BAND_DEPENDENCE, NO_EDGE_YET | 27 | 0.032085 | Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage. |
| STD-REPAIR-LEAGUE1-OU25-UNDER | MODEL_BELOW_MARKET, CALIBRATION_FAILURE, NO_EDGE_YET | 45 | 0.013097 | Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage. |
| STD-REPAIR-LEAGUE1-BTTS-YES | NO_EDGE_YET | 15 | 0.009676 | Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout. |
| STD-REPAIR-LEAGUE1-BTTS-NO | MODEL_BELOW_MARKET, CALIBRATION_FAILURE, NO_EDGE_YET | 57 | 0.01007 | Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage. |
| STD-REPAIR-LEAGUE1-OU15-OVER | PRICE_QUALITY_PROBLEM, SIDE_SPECIFIC_EDGE | 0 | None | Accumulate two-sided first-sight quotes (forward capture) before any model work; re-test residual on real quotes at n>=150. |
| STD-REPAIR-LEAGUE2-OU25-OVER | CALIBRATION_FAILURE, NO_EDGE_YET | 40 | 0.025191 | Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage. |
| STD-REPAIR-LEAGUE2-OU25-UNDER | INSUFFICIENT_SAMPLE, NO_EDGE_YET | 42 | 0.004819 | Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout. |
| STD-REPAIR-LEAGUE2-BTTS-YES | NO_EDGE_YET | 38 | 0.00747 | Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout. |
| STD-REPAIR-LEAGUE2-BTTS-NO | NO_EDGE_YET | 44 | 0.008798 | Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout. |
| STD-REPAIR-LEAGUE2-OU15-OVER | PRICE_QUALITY_PROBLEM, CALIBRATION_FAILURE, NO_EDGE_YET | 0 | None | Accumulate two-sided first-sight quotes (forward capture) before any model work; re-test residual on real quotes at n>=150. |
| STD-REPAIR-BUNDES2-OU25-OVER | INSUFFICIENT_SAMPLE, NO_EDGE_YET | 9 | 0.021703 | Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout. |
| STD-REPAIR-BUNDES2-OU25-UNDER | CALIBRATION_FAILURE, NO_EDGE_YET | 36 | 0.054131 | Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage. |
| STD-REPAIR-BUNDES2-BTTS-YES | INSUFFICIENT_SAMPLE, NO_EDGE_YET | 0 | None | Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout. |
| STD-REPAIR-BUNDES2-BTTS-NO | CALIBRATION_FAILURE, NO_EDGE_YET | 43 | 0.008636 | Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage. |
| STD-REPAIR-BUNDES2-OU15-OVER | INSUFFICIENT_SAMPLE, PRICE_QUALITY_PROBLEM, NO_EDGE_YET | 0 | None | Accumulate two-sided first-sight quotes (forward capture) before any model work; re-test residual on real quotes at n>=150. |
| STD-REPAIR-LALIGA2-OU25-OVER | MODEL_ABOVE_MARKET_SELECTION_BAD, NO_EDGE_YET | 47 | -0.004012 | Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout. |
| STD-REPAIR-LALIGA2-OU25-UNDER | INSUFFICIENT_SAMPLE, CALIBRATION_FAILURE, REGIME_DRIFT, NO_EDGE_YET | 18 | -0.000162 | Test a shorter recency window / league-environment reset at season start on the next untouched block. |
| STD-REPAIR-LALIGA2-BTTS-YES | SIDE_SPECIFIC_EDGE | 43 | -0.00866 | Pre-register this side as a forward shadow only if the pooled rule passes; otherwise re-test on next quarter's untouched block. |
| STD-REPAIR-LALIGA2-BTTS-NO | INSUFFICIENT_SAMPLE, MODEL_BELOW_MARKET, CALIBRATION_FAILURE, REGIME_DRIFT, NO_EDGE_YET | 22 | -0.021485 | Test a shorter recency window / league-environment reset at season start on the next untouched block. |
| STD-REPAIR-LALIGA2-OU15-OVER | PRICE_QUALITY_PROBLEM, SIDE_SPECIFIC_EDGE | 2 | 0.037623 | Accumulate two-sided first-sight quotes (forward capture) before any model work; re-test residual on real quotes at n>=150. |
| STD-REPAIR-LIGUE2-OU25-OVER | CALIBRATION_FAILURE, REGIME_DRIFT, NO_EDGE_YET | 27 | 0.04166 | Test a shorter recency window / league-environment reset at season start on the next untouched block. |
| STD-REPAIR-LIGUE2-OU25-UNDER | INSUFFICIENT_SAMPLE, SIDE_SPECIFIC_EDGE | 21 | -0.008688 | Pre-register this side as a forward shadow only if the pooled rule passes; otherwise re-test on next quarter's untouched block. |
| STD-REPAIR-LIGUE2-BTTS-YES | INSUFFICIENT_SAMPLE, REGIME_DRIFT, NO_EDGE_YET | 16 | -0.025203 | Test a shorter recency window / league-environment reset at season start on the next untouched block. |
| STD-REPAIR-LIGUE2-BTTS-NO | INSUFFICIENT_SAMPLE, REGIME_DRIFT, NO_EDGE_YET | 22 | 0.009344 | Test a shorter recency window / league-environment reset at season start on the next untouched block. |
| STD-REPAIR-LIGUE2-OU15-OVER | INSUFFICIENT_SAMPLE, PRICE_QUALITY_PROBLEM, CALIBRATION_FAILURE, NO_EDGE_YET | 0 | None | Accumulate two-sided first-sight quotes (forward capture) before any model work; re-test residual on real quotes at n>=150. |
| STD-REPAIR-SERIEB-OU25-OVER | NO_EDGE_YET | 42 | -0.012333 | Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout. |
| STD-REPAIR-SERIEB-OU25-UNDER | INSUFFICIENT_SAMPLE, CALIBRATION_FAILURE, NO_EDGE_YET | 9 | 0.019603 | Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage. |
| STD-REPAIR-SERIEB-BTTS-YES | NO_EDGE_YET | 41 | -0.021414 | Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout. |
| STD-REPAIR-SERIEB-BTTS-NO | INSUFFICIENT_SAMPLE, CALIBRATION_FAILURE, NO_EDGE_YET | 9 | 0.003005 | Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage. |
| STD-REPAIR-SERIEB-OU15-OVER | PRICE_QUALITY_PROBLEM, NO_EDGE_YET | 0 | None | Accumulate two-sided first-sight quotes (forward capture) before any model work; re-test residual on real quotes at n>=150. |

## State changes

- none

## Next actions

- No forward registration: keep collecting first-sight quotes; re-run the benchmark when 2026-Q4 completes and score the frozen validation-selected arms on it as a fresh holdout (no re-tuning).
- 7 tracks lack usable two-sided prices (BTTS/OU15 history; OU15 forward): price capture is the binding constraint, not modelling.
- Never change v9 thresholds or enable anything from these numbers.

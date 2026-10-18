# Model lineage — champion high-water mark

Generated 2026-10-18 09:54:07 UTC. Read-only against v9.

Weekly realised results swing with football. What must not regress is the validated quality of the model in production. One week never demotes a champion (`WEEKLY_RESULT_VARIANCE_HIGH`).

## Current champions

| model_type | current_champion | champion_since | challenger_status | champion_health | next_action |
|---|---|---|---|---|---|
| btts | btts_20261005T101905Z_238e3419 | 2026-10-05T10:19:05Z | LEGACY_BLOCKED | HEALTHY | first CHAMPION_GATE retrain pending (next Sunday) |
| ht_over05 | ht_over05_20261018T080423Z_359b491a | 2026-10-18T08:04:23Z | LEGACY_PROMOTED | HEALTHY | first CHAMPION_GATE retrain pending (next Sunday) |
| ht_over15 | ht_over15_20261004T093828Z_6f370f63 | 2026-10-04T09:38:28Z | LEGACY_BLOCKED | HEALTHY | first CHAMPION_GATE retrain pending (next Sunday) |
| newformat | newformat_20261018T080423Z_9eb6b4b4 | 2026-10-18T08:04:23Z | LEGACY_PROMOTED | HEALTHY | first CHAMPION_GATE retrain pending (next Sunday) |
| over15 | over15_20261018T080423Z_da4743a2 | 2026-10-18T08:04:23Z | LEGACY_PROMOTED | HEALTHY | first CHAMPION_GATE retrain pending (next Sunday) |
| over35 | over35_20261005T101905Z_f546ce72 | 2026-10-05T10:19:05Z | LEGACY_BLOCKED | HEALTHY | first CHAMPION_GATE retrain pending (next Sunday) |
| standard | standard_20261018T080423Z_64313878 | 2026-10-18T08:04:23Z | LEGACY_PROMOTED | HEALTHY | first CHAMPION_GATE retrain pending (next Sunday) |

## Retrain decisions

- attempts analysed: **112**, promotions **98**, kept/blocked **14**, shadow **0**, churn rate **0.875**
- best proven champion improvement: NONE — no promotion so far was backed by a same-holdout CI excluding zero; strongest CI-backed gain was newformat 2026-10-11 -0.00313 (CI hi -0.00111), NOT promoted by the old rule

| model_type | regime | retrain_attempts | promotions | MODEL_CHURN_RATE | promoted_while_worse | MEDIAN_CHAMPION_LIFETIME_DAYS |
|---|---|---|---|---|---|---|
| btts | LEGACY_RULE | 16 | 14 | 0.875 | 3 | 1.017 |
| ht_over05 | LEGACY_RULE | 16 | 14 | 0.875 | 3 | 1.019 |
| ht_over15 | LEGACY_RULE | 16 | 13 | 0.812 | 4 | 1.016 |
| newformat | LEGACY_RULE | 16 | 14 | 0.875 | 7 | 1.01 |
| over15 | LEGACY_RULE | 16 | 16 | 1.0 | 5 | 1.017 |
| over35 | LEGACY_RULE | 16 | 14 | 0.875 | 3 | 1.017 |
| standard | LEGACY_RULE | 16 | 13 | 0.812 | 4 | 1.019 |

## Retrain → future results (latest 21)

| iso_week | decided_at | model_type | challenger_version | verdict | decision | ll_delta_at_decision | future_N | future_accuracy | future_logloss_bets | future_roi | future_clv | champion_after | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-W40 | 2026-10-03 09:05 | over35 | over35_20261003T090508Z_fb1b8293 | LEGACY_PROMOTED | PROMOTED (old rule) | 0.0001 | 0 |  |  |  |  |  | CLOSED |
| 2026-W40 | 2026-10-04 09:38 | over35 | over35_20261004T093828Z_945d3220 | LEGACY_PROMOTED | PROMOTED (old rule) | -0.0001 | 0 |  |  |  |  |  | CLOSED |
| 2026-W41 | 2026-10-05 10:19 | over35 | over35_20261005T101905Z_f546ce72 | LEGACY_PROMOTED | PROMOTED (old rule) | -0.0003 | 1 | 1.0 | 0.5893 | 0.84 | -0.0108 |  | CLOSED |
| 2026-W41 | 2026-10-11 10:01 | over35 | UNKNOWN_LEGACY | LEGACY_BLOCKED | BLOCKED (old rule) | 0.0001 | 0 |  |  |  |  |  | CLOSED |
| 2026-W42 | 2026-10-18 08:04 | over35 | UNKNOWN_LEGACY | LEGACY_BLOCKED | BLOCKED (old rule) | 0.0003 | 0 |  |  |  |  |  | OPEN |
| 2026-W39 | 2026-09-22 11:09 | standard | standard_20260922T111451Z_07dd44fc | LEGACY_PROMOTED | PROMOTED (old rule) | -0.0013 | 1 | 1.0 | 0.5855 | 1.0 | -0.0244 |  | CLOSED |
| 2026-W39 | 2026-09-23 08:26 | standard | standard_20260923T083350Z_4f72335d | LEGACY_PROMOTED | PROMOTED (old rule) | -0.0482 | 9 | 0.3333 | 0.9268 | -0.3867 | -0.002 |  | CLOSED |
| 2026-W39 | 2026-09-24 08:18 | standard | UNKNOWN_LEGACY | LEGACY_BLOCKED | BLOCKED (old rule) | 0.0053 | 3 | 0.3333 | 0.7049 | -0.3467 | -0.0037 |  | CLOSED |
| 2026-W39 | 2026-09-25 08:41 | standard | standard_20260925T084541Z_252bfbcc | LEGACY_PROMOTED | PROMOTED (old rule) | -0.019 | 1 | 1.0 | 0.5735 | 1.2 | -0.0435 |  | CLOSED |
| 2026-W39 | 2026-09-26 08:27 | standard | standard_20260926T083219Z_e98d0817 | LEGACY_PROMOTED | PROMOTED (old rule) | 0.0003 | 1 | 0.0 | 0.724 | -1.0 | 0.0722 |  | CLOSED |
| 2026-W39 | 2026-09-27 09:06 | standard | standard_20260927T091201Z_1b2284ad | LEGACY_PROMOTED | PROMOTED (old rule) | 0.0002 | 3 | 0.6667 | 0.6572 | 0.3467 | 0.0001 |  | CLOSED |
| 2026-W40 | 2026-09-28 09:34 | standard | standard_20260928T093914Z_3699469c | LEGACY_PROMOTED | PROMOTED (old rule) | -0.001 | 2 | 0.5 | 0.8039 | 0.34 | 0.014 |  | CLOSED |
| 2026-W40 | 2026-09-29 09:38 | standard | standard_20260929T094351Z_8f4d75ab | LEGACY_PROMOTED | PROMOTED (old rule) | 0.0 | 0 |  |  |  |  |  | CLOSED |
| 2026-W40 | 2026-09-30 09:30 | standard | standard_20260930T093542Z_ead5b968 | LEGACY_PROMOTED | PROMOTED (old rule) | 0.0011 | 0 |  |  |  |  |  | CLOSED |
| 2026-W40 | 2026-10-01 09:58 | standard | standard_20261001T100334Z_1274379a | LEGACY_PROMOTED | PROMOTED (old rule) | -0.0001 | 0 |  |  |  |  |  | CLOSED |
| 2026-W40 | 2026-10-02 09:33 | standard | standard_20261002T093839Z_2432ce8f | LEGACY_PROMOTED | PROMOTED (old rule) | -0.0008 | 4 | 0.5 | 0.7599 | 0.1325 | -0.0014 |  | CLOSED |
| 2026-W40 | 2026-10-03 09:01 | standard | standard_20261003T090508Z_14d33ff8 | LEGACY_PROMOTED | PROMOTED (old rule) | -0.0001 | 14 | 0.3571 | 0.6798 | -0.2643 | -0.0112 |  | CLOSED |
| 2026-W40 | 2026-10-04 09:33 | standard | standard_20261004T093828Z_5263a16f | LEGACY_PROMOTED | PROMOTED (old rule) | -0.0001 | 10 | 0.4 | 0.6984 | -0.168 | 0.0024 |  | CLOSED |
| 2026-W41 | 2026-10-05 10:13 | standard | UNKNOWN_LEGACY | LEGACY_BLOCKED | BLOCKED (old rule) | 0.001 | 46 | 0.4348 | 0.7095 | -0.0433 | 0.0082 |  | CLOSED |
| 2026-W41 | 2026-10-11 09:56 | standard | UNKNOWN_LEGACY | LEGACY_BLOCKED | BLOCKED (old rule) | 0.0004 | 9 | 0.6667 | 0.6595 | 0.3911 | -0.015 |  | CLOSED |
| 2026-W42 | 2026-10-18 07:59 | standard | standard_20261018T080423Z_64313878 | LEGACY_PROMOTED | PROMOTED (old rule) | -0.0002 | 0 |  |  |  |  |  | OPEN |

## Bet attribution

{"RECONSTRUCTED_BY_TIME": 1189, "UNKNOWN_LEGACY": 435, "AMBIGUOUS_BOUNDARY": 1}

Legacy rows are attributed by timestamp to git-reconstructed champion eras. Rows within 60 minutes after an era started are AMBIGUOUS_BOUNDARY and excluded.

## Head-to-head shadow

0 logged rows, 0 graded. The log started 2026-10-18.

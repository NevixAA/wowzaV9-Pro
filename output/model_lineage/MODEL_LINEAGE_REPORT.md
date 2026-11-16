# Model lineage — champion high-water mark

Generated 2026-11-16 13:59:25 UTC. Read-only against v9.

Weekly realised results swing with football. What must not regress is the validated quality of the model in production. One week never demotes a champion (`WEEKLY_RESULT_VARIANCE_HIGH`).

## Current champions

| model_type | current_champion | champion_since | challenger_status | champion_health | next_action |
|---|---|---|---|---|---|
| btts | btts_20261005T101905Z_238e3419 | 2026-10-05T10:19:05Z | KEEP_CHAMPION | WATCH | keep champion; next retrain tries again |
| ht_over05 | ht_over05_20261018T080423Z_359b491a | 2026-10-18T08:04:23Z | KEEP_CHAMPION | HEALTHY | keep champion; next retrain tries again |
| ht_over15 | ht_over15_20261004T093828Z_6f370f63 | 2026-10-04T09:38:28Z | KEEP_CHAMPION | HEALTHY | keep champion; next retrain tries again |
| newformat | newformat_20261018T080423Z_9eb6b4b4 | 2026-10-25T08:46:05Z | SHADOW_MORE | DEGRADED | owner review: champion health DEGRADED |
| over15 | over15_20261018T080423Z_da4743a2 | 2026-10-18T08:04:23Z | KEEP_CHAMPION | DEGRADED | owner review: champion health DEGRADED |
| over35 | over35_20261005T101905Z_f546ce72 | 2026-10-05T10:19:05Z | KEEP_CHAMPION | DEGRADED | owner review: champion health DEGRADED |
| standard | standard_20261018T080423Z_64313878 | 2026-10-18T08:04:23Z | SHADOW_MORE | HEALTHY | shadow: collect graded head-to-head fixtures |
| standard_repaired | standard_repaired_20261028T123040Z_1f5805e6 | 2026-10-28T12:37:37Z |  | WATCH | first CHAMPION_GATE retrain pending (next Sunday) |

## Retrain decisions

- attempts analysed: **154**, promotions **99**, kept/blocked **41**, shadow **14**, churn rate **0.643**
- best proven champion improvement: NONE — no promotion so far was backed by a same-holdout CI excluding zero; strongest CI-backed gain was newformat 2026-10-11 -0.00313 (CI hi -0.00111), NOT promoted by the old rule

| model_type | regime | retrain_attempts | promotions | MODEL_CHURN_RATE | promoted_while_worse | MEDIAN_CHAMPION_LIFETIME_DAYS |
|---|---|---|---|---|---|---|
| btts | CHAMPION_GATE | 6 | 0 | 0.0 | 0 | 1.017 |
| btts | LEGACY_RULE | 16 | 14 | 0.875 | 3 | 1.017 |
| ht_over05 | CHAMPION_GATE | 6 | 0 | 0.0 | 0 | 1.021 |
| ht_over05 | LEGACY_RULE | 16 | 14 | 0.875 | 3 | 1.021 |
| ht_over15 | CHAMPION_GATE | 6 | 0 | 0.0 | 0 | 1.016 |
| ht_over15 | LEGACY_RULE | 16 | 13 | 0.812 | 4 | 1.016 |
| newformat | CHAMPION_GATE | 6 | 1 | 0.167 | 0 | 1.017 |
| newformat | LEGACY_RULE | 16 | 14 | 0.875 | 7 | 1.017 |
| over15 | CHAMPION_GATE | 6 | 0 | 0.0 | 0 | 1.019 |
| over15 | LEGACY_RULE | 16 | 16 | 1.0 | 5 | 1.019 |
| over35 | CHAMPION_GATE | 6 | 0 | 0.0 | 0 | 1.017 |
| over35 | LEGACY_RULE | 16 | 14 | 0.875 | 3 | 1.017 |
| standard | CHAMPION_GATE | 6 | 0 | 0.0 | 0 | 1.019 |
| standard | LEGACY_RULE | 16 | 13 | 0.812 | 4 | 1.019 |

## Retrain → future results (latest 21)

| iso_week | decided_at | model_type | challenger_version | verdict | decision | ll_delta_at_decision | future_N | future_accuracy | future_logloss_bets | future_roi | future_clv | champion_after | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
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
| 2026-W41 | 2026-10-11 09:56 | standard | UNKNOWN_LEGACY | LEGACY_BLOCKED | BLOCKED (old rule) | 0.0004 | 47 | 0.4681 | 0.7005 | 0.0066 | 0.009 |  | CLOSED |
| 2026-W42 | 2026-10-18 07:59 | standard | standard_20261018T080423Z_64313878 | LEGACY_PROMOTED | PROMOTED (old rule) | -0.0002 | 37 | 0.3784 | 0.6759 | -0.1457 | 0.0165 |  | CLOSED |
| 2026-W43 | 2026-10-25 08:20 | standard | standard_20261025T082022Z_3a405c51 | SHADOW_MORE | SHADOW | -0.0009 | 28 | 0.4643 | 0.6818 | 0.0568 | 0.0271 | standard_20261018T080423Z_64313878 | CLOSED |
| 2026-W44 | 2026-11-01 11:18 | standard | standard_20261101T111837Z_3562424e | SHADOW_MORE | SHADOW | -0.0009 | 2 | 0.0 | 0.6313 | -1.0 | 0.053 | standard_20261018T080423Z_64313878 | CLOSED |
| 2026-W44 | 2026-11-01 15:39 | standard | standard_20261101T153917Z_a47c133e | SHADOW_MORE | SHADOW | -0.0007 | 0 |  |  |  |  | standard_20261018T080423Z_64313878 | CLOSED |
| 2026-W44 | 2026-11-01 16:34 | standard | standard_20261101T163453Z_9e71c179 | SHADOW_MORE | SHADOW | -0.0006 | 0 |  |  |  |  | standard_20261018T080423Z_64313878 | CLOSED |
| 2026-W44 | 2026-11-01 16:44 | standard | standard_20261101T164419Z_9eab496f | SHADOW_MORE | SHADOW | -0.0017 | 1 | 1.0 | 0.732 | 1.25 | 0.0465 | standard_20261018T080423Z_64313878 | CLOSED |
| 2026-W44 | 2026-11-01 17:08 | standard | standard_20261101T170844Z_279e2947 | SHADOW_MORE | SHADOW | -0.0016 | 16 | 0.1875 | 0.663 | -0.5825 | 0.0178 | standard_20261018T080423Z_64313878 | OPEN |

## Bet attribution

{"RECONSTRUCTED_BY_TIME": 1472, "RECORDED": 449, "UNKNOWN_LEGACY": 442, "AMBIGUOUS_BOUNDARY": 1}

Legacy rows are attributed by timestamp to git-reconstructed champion eras. Rows within 60 minutes after an era started are AMBIGUOUS_BOUNDARY and excluded.

## Head-to-head shadow

5502 logged rows, 3702 graded. The log started 2026-10-18.

| model_type | challenger_version | champion_version | fixtures_logged | graded_n | ll_champion | ll_challenger | delta_logloss | delta_ci_lo | delta_ci_hi | delta_brier | calib_gap_champion | calib_gap_challenger | delta_roi_sim | verdict_so_far |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| btts | btts_20261101T112201Z_bf9b956c | btts_20261005T101905Z_238e3419 | 415 | 237 | 0.69506 | 0.69503 | -3e-05 | -0.00645 | 0.00473 | 1e-05 | 0.01342 | 0.01629 | NOT_AVAILABLE: h2h rows carry no price | UNRESOLVED |
| newformat | newformat_20261025T082056Z_cfa68e5c | newformat_20261018T080423Z_9eb6b4b4 | 343 | 252 | 0.69037 | 0.67249 | -0.01788 | -0.03216 | -0.00344 | -0.00871 | -0.08828 | -0.04497 | NOT_AVAILABLE: h2h rows carry no price | CHALLENGER_AHEAD |
| newformat | pro_hgb_newformat_20261022T110238Z_8e11e6cf | newformat_20261018T080423Z_9eb6b4b4 | 416 | 320 | 0.69141 | 0.67472 | -0.01669 | -0.03172 | -0.00371 | -0.00817 | -0.08184 | -0.03591 | NOT_AVAILABLE: h2h rows carry no price | CHALLENGER_AHEAD |
| over15 | over15_20261101T112303Z_e3e5d0aa | over15_20261018T080423Z_da4743a2 | 171 | 154 | 0.54847 | 0.54647 | -0.00199 | -0.00869 | 0.00307 | -0.00061 | -0.00886 | -0.00584 | NOT_AVAILABLE: h2h rows carry no price | UNRESOLVED |
| over15 | over15_20261101T154342Z_bcbad302 | over15_20261018T080423Z_da4743a2 | 397 | 220 | 0.54741 | 0.54778 | 0.00037 | -0.00391 | 0.00502 | -8e-05 | -0.00583 | -0.00645 | NOT_AVAILABLE: h2h rows carry no price | UNRESOLVED |
| standard | pro_hgb_standard_20261022T110238Z_e4191ad5 | standard_20261018T080423Z_64313878 | 345 | 245 | 0.69326 | 0.70351 | 0.01025 | 0.00269 | 0.0161 | 0.00506 | 8e-05 | -0.01075 | NOT_AVAILABLE: h2h rows carry no price | CHAMPION_AHEAD |
| standard | standard_20261025T082022Z_3a405c51 | standard_20261018T080423Z_64313878 | 115 | 110 | 0.687 | 0.69307 | 0.00606 | -0.00538 | 0.01085 | 0.00298 | -0.04135 | -0.02769 | NOT_AVAILABLE: h2h rows carry no price | UNRESOLVED |

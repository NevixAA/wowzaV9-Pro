# WORKFLOW DUPLICATION AUDIT

33 workflows across three repositories.

**Declared cadence is not delivered cadence.** GitHub's dispatcher ignores the minute field and drops most high-frequency slots — measured here across 1,367 runs: ~13% of slots delivered at 57/day, ~100% at once-daily but 4-5 hours late. The numbers below are what the cron ASKS FOR. They are the right basis for reasoning about dependency order (a daily consumer of an hourly producer is safe; the reverse is not) and the wrong basis for reasoning about when anything actually happens.

## By repo and what a failure costs

| repo | COLLECT | DERIVE | REPORT | TIPS |
|---|---|---|---|---|
| pro | 2 | 0 | 1 | 7 |
| v11 | 1 | 0 | 0 | 0 |
| v9 | 6 | 2 | 3 | 11 |


`COLLECT` means a miss is PERMANENT — odds cannot be backfilled, established across six seasons and ~830 calls. That single fact decides most of this document: a COLLECT workflow is essentially never a consolidation candidate, however much it appears to overlap with another.

## Every workflow

| repo | workflow | crons | declared_runs_per_day | production_impact | scripts | uses_external_api | timeout_minutes | n_staged |
|---|---|---|---|---|---|---|---|---|
| pro | pro_collect.yml | 40 */2 * * *; 15 6 * * * | 13.0 | COLLECT | src.combo.canonical; src.market.clv_schema; src.monitoring.manifest; src.monitoring.scheduler; src.pipelines.data_quality; src.pipelines.news_impact | False | 20 | 2 |
| pro | pro_live_odds.yml | 9 11-23 * * * | 13.0 | TIPS | src.pipelines.live_odds | True | 15 | 1 |
| pro | pro_team_news.yml | 15 */3 * * * | 8.0 | TIPS | src.pipelines.team_news | True | 12 | 0 |
| pro | pro_backfill_results.yml | 25 */6 * * * | 4.0 | COLLECT | src.pipelines.backfill_history; src.pipelines.shadow | False | 30 | 0 |
| pro | pro_team_stats.yml | 35 4 * * *; 35 16 * * * | 2.0 | TIPS | src.pipelines.team_stats | True | 30 | 0 |
| pro | pro_bet_builder.yml | 17 9,15,20 * * 5,6,0; 17 15 * * 1-4 | 1.86 | TIPS | src.combo.tests; src.pipelines.bet_builder | False | 30 | 0 |
| pro | pro_paper_1x2.yml | 41 7 * * * | 1.0 | TIPS | src.pipelines.paper_1x2 | False | 20 | 1 |
| pro | pro_research.yml | 40 5 * * * | 1.0 | TIPS | src.monitoring.ml_learning_health; src.pipelines.train_mixed; src.validation.calibration_study; src.validation.cross_model; src.validation.pick_accuracy; src.validation.threshold_curves | False | 30 | 0 |
| pro | pro_prediction_lab.yml | 40 2 * * 1 | 0.14 | TIPS | pip; src.prediction_lab.cross_market; src.prediction_lab.data; src.prediction_lab.goal_dist; src.prediction_lab.leakage; src.prediction_lab.player_goals | False | 330 | 0 |
| pro | pro_weekly_audit.yml | 15 6 * * 1 | 0.14 | REPORT | src.monitoring.weekly_audit | False | 20 | 0 |
| v11 | v11_collect.yml | 25 8-23 * * * | 16.0 | COLLECT | scripts/v11_fit_evidence.py; scripts/v11_grade.py; scripts/v11_market_movement.py; scripts/v11_microstructure.py; scripts/v11_momentum_control.py; scripts/v11_residual.py | False | 15 | 0 |
| v9 | predict.yml | 9-59/15 8-23 * * 5,6,0; 9-59/30 0-7 * * 5,6,0; 9-59/30 8-23 * * 1-4; 9 0-7 * * 1-4 | 24.0 | TIPS | pipeline.py; telegram_bot/notifier.py | True | 25 | 1 |
| v9 | live_scanner.yml | 4 8-23 * * * | 16.0 | TIPS | src/live_scanner.py | True | 5 | 0 |
| v9 | player_props.yml | 2 */2 * * 5,6,0; 2 */6 * * 1-4; 30 23 * * *; 0 5 * * 0; 0 5 * * 1-6 | 9.43 | TIPS | player_model.pipeline | True | 120 | 0 |
| v9 | update_results.yml | 30 7,9,11,13,15,17,19,21,23 * * * | 9.0 | COLLECT | update_results.py | True | 10 | 0 |
| v9 | nf_odds_capture.yml | 35 1,7,13,19 * * *; 20,50 0-3,9-23 * * * | 8.0 | COLLECT | scripts/capture_nf_odds_forward.py | True | 55 | 1 |
| v9 | sharp_tracker.yml | 0 8,10,12,14,16,18,20,22 * * * | 8.0 | TIPS | src/sharp_tracker.py | True | 10 | 1 |
| v9 | std_odds_capture.yml | 5 0,6,12,18 * * *; 23,52 0-3,9-23 * * * | 8.0 | COLLECT | scripts/capture_std_sidemarket_odds_forward.py | True | 65 | 1 |
| v9 | prop_odds_snapshot.yml | 20 */4 * * * | 6.0 | COLLECT | scripts/snapshot_prop_odds.py | True | 20 | 2 |
| v9 | daily_summary.yml | 0 1 * * *; 0 3 * * *; 0 5 * * *; 0 7 * * *; 0 9 * * * | 5.0 | REPORT | update_results.py | True | 10 | 0 |
| v9 | af_usage_monitor.yml | 51 1,7,13,19 * * * | 4.0 | REPORT | scripts/af_usage_log.py | True | 5 | 1 |
| v9 | sharp_move_alert.yml | 0 7,13,19 * * * | 3.0 | TIPS |  | False | 10 | 1 |
| v9 | af_history_extend.yml | 0 6 * * * | 1.0 | COLLECT | scripts/backfill_af_history.py | True | 60 | 1 |
| v9 | fantasy_refresh.yml | 30 6 * * * | 1.0 | DERIVE |  | True | 20 | 0 |
| v9 | injury_refresh.yml | 0 4 * * * | 1.0 | TIPS | player_model.pipeline | True | 30 | 1 |
| v9 | player_history_extend.yml | 40 3 * * * | 1.0 | COLLECT | player_model.pipeline | True | 100 | 0 |
| v9 | retrain.yml | 0 3 * * * | 1.0 | TIPS | pipeline.py | True | 240 | 0 |
| v9 | warm_nf_shot_cache.yml | 0 3 * * * | 1.0 | DERIVE | scripts/warm_nf_shot_cache.py | True | 45 | 0 |
| v9 | weekly_summary.yml | 0 9 * * 1 | 0.14 | REPORT |  | True | 5 | 0 |
| v9 | backtest_matrix.yml | 0 3 1 * * | 0.03 | TIPS | pipeline.py | True | 120 | 2 |
| v9 | preseason_retrain.yml | 0 2 1 8 * | 0.03 | TIPS | pipeline.py | True | 120 | 0 |
| v9 | backtest.yml |  | 0.0 | TIPS | pipeline.py | True | 300 | 1 |
| v9 | worldcup.yml |  | 0.0 | TIPS | worldcup/tracker.py | True | 10 | 0 |


## Files written by more than one workflow

| file | written_by | n_writers |
|---|---|---|
| output/sharp_history/ | v9:predict.yml; v9:sharp_tracker.yml | 2 |


`output/sharp_history/` is written by both `predict.yml` (24 declared runs/day) and `sharp_tracker.yml` (8/day). Two writers on one path is the shape that produces lost updates when both commit in the same window. Worth confirming they write disjoint keys; NOT worth consolidating, because they run on different cadences for different reasons.

## Consolidation candidates

The objective is not fewer workflows. It is fewer inconsistent paths to the same truth. On that test almost nothing here qualifies:

| repo | impact | n | workflows |
|---|---|---|---|
| v9 | REPORT | 3 | af_usage_monitor.yml; daily_summary.yml; weekly_summary.yml |
| v9 | DERIVE | 2 | fantasy_refresh.yml; warm_nf_shot_cache.yml |


| candidate | overlap | why both exist | recommendation |
|---|---|---|---|
| `std_odds_capture` + `nf_odds_capture` | same shape, different league sets | invariant 1 keeps standard and new-format apart end to end, and they have different API costs and timeouts (65 vs 55 min) | **KEEP BOTH** — merging couples two tracks the estate deliberately isolates |
| `predict` + `live_scanner` | both write tip-bearing output | pre-match vs in-play; invariant 5 forbids live odds reaching the pre-match path | **KEEP BOTH** — merging would reintroduce the false-SNIPER bug |
| `pro_collect` + v9's collectors | Pro imports what v9 captures | Pro is downstream by design today | **KEEP BOTH** until the season boundary, then migrate one at a time with both running in parallel |
| `af_usage_monitor` + `daily_summary` | both REPORT, both v9 | different audiences and different cadences (4/day vs 5/day) | **DEFER** — consolidation saves a runner minute and risks a reporting blind spot |

**Recommendation for this section: combine nothing yet.** Every apparent duplicate traced back to a deliberate separation. `SAFE_TO_COMBINE_ANY_WORKFLOWS=NO`.

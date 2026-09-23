# DATA LINEAGE AUDIT

359 logical data stores across three repositories. A partitioned directory of 2,615 parquet files is one table here, and a cache of 45,753 provider responses is one cache — counting them file by file would bury the dozen tables that matter.

## By repo and layer

| repo | CACHE | CANONICAL | DERIVED | RAW | REPORT | UNKNOWN |
|---|---|---|---|---|---|---|
| pro | 7 | 28 | 55 | 4 | 27 | 98 |
| v11 | 0 | 0 | 0 | 1 | 4 | 17 |
| v9 | 13 | 13 | 42 | 7 | 7 | 36 |


## Largest tables

| repo | path | layer | rows | cols | first | last | n_producers | n_consumers | n_workflows |
|---|---|---|---|---|---|---|---|---|---|
| v9 | player_history.parquet | CANONICAL | 316157.0 | 212.0 | 2022-08-12 00:00:00 | 2026-09-20 00:00:00 | 6 | 19 | 3 |
| pro | output/pure_prediction/scoreline_oof.parquet | UNKNOWN | 314220.0 | 14.0 | 2023-12-04 00:00:00 | 2026-03-17 00:00:00 | 1 | 0 | 0 |
| pro | player_history.parquet | CANONICAL | 230216.0 | 211.0 | 2022-08-12 00:00:00 | 2026-07-04 00:00:00 | 6 | 19 | 3 |
| pro | output/pure_prediction/oof_probabilities.parquet | UNKNOWN | 209480.0 | 11.0 | 2023-12-04 00:00:00 | 2026-03-17 00:00:00 | 1 | 3 | 0 |
| v9 | output/player_prop_odds_history.csv | RAW | 200000.0 | 10.0 | 2026-06-28 00:00:00 | 2026-09-19 00:00:00 | 4 | 8 | 2 |
| v9 | output/book_odds_snapshots.csv | RAW | 200000.0 | 9.0 | 2026-08-19 00:00:00 | 2026-09-26 00:00:00 | 3 | 2 | 1 |
| pro | joined_bets.parquet | DERIVED | 101241.0 | 6.0 | 2025-04-01 00:00:00 | 2026-06-24 00:00:00 | 0 | 0 | 0 |
| v9 | joined_bets.parquet | DERIVED | 101241.0 | 6.0 | 2025-04-01 00:00:00 | 2026-06-24 00:00:00 | 0 | 0 | 0 |
| pro | oddsband_bets.parquet | DERIVED | 99448.0 | 10.0 | 2025-08-22 00:00:00 | 2026-06-24 00:00:00 | 0 | 0 | 0 |
| pro | team_analyst_bets.parquet | DERIVED | 99448.0 | 20.0 | 2025-08-22 00:00:00 | 2026-06-24 00:00:00 | 0 | 0 | 0 |
| v9 | arch_bets.parquet | DERIVED | 99448.0 | 27.0 | 2025-08-22 00:00:00 | 2026-06-24 00:00:00 | 0 | 0 | 0 |
| pro | arch_bets.parquet | DERIVED | 99448.0 | 27.0 | 2025-08-22 00:00:00 | 2026-06-24 00:00:00 | 0 | 0 | 0 |
| v9 | oddsband_bets.parquet | DERIVED | 99448.0 | 10.0 | 2025-08-22 00:00:00 | 2026-06-24 00:00:00 | 0 | 0 | 0 |
| v9 | team_analyst_bets.parquet | DERIVED | 99448.0 | 20.0 | 2025-08-22 00:00:00 | 2026-06-24 00:00:00 | 0 | 0 | 0 |
| pro | output/architecture/canonical_match_history.parquet | CANONICAL | 80868.0 | 48.0 | 2019-02-15 00:00:00 | 2026-09-22 00:00:00 | 1 | 0 | 0 |
| v11 | output/v11_shadow_snapshots.csv | RAW | 59859.0 | 37.0 | 2026-08-10 00:00:00 | 2026-09-28 00:00:00 | 3 | 5 | 1 |
| v11 | output/v11_market_movement_detail.csv | UNKNOWN | 58234.0 | 37.0 |  |  | 1 | 2 | 1 |
| v11 | output/v11_market_microstructure.csv | UNKNOWN | 58234.0 | 68.0 | 2026-09-22 01:39:59 | 2026-09-22 01:39:59 | 2 | 0 | 1 |
| v9 | output/fd_history.parquet | CANONICAL | 58156.0 | 23.0 | 2019-02-15 00:00:00 | 2026-09-22 00:00:00 | 3 | 2 | 2 |
| pro | output/pure_prediction/feature_matrix.parquet | UNKNOWN | 58155.0 | 194.0 | 2019-02-15 00:00:00 | 2026-09-22 00:00:00 | 0 | 1 | 0 |
| pro | output/clv_enriched.csv | UNKNOWN | 47771.0 | 18.0 | 2026-08-17 00:00:00 | 2026-09-26 00:00:00 | 2 | 0 | 1 |
| v9 | output/newformat_odds_history.csv | RAW | 44582.0 | 8.0 | 2025-06-23 00:00:00 | 2026-10-12 00:00:00 | 3 | 4 | 1 |
| pro | output/backtest_all_leagues.csv | DERIVED | 44207.0 | 73.0 | 2019-09-28 00:00:00 | 2026-04-23 00:00:00 | 1 | 1 | 0 |
| v9 | output/backtest_all_leagues.csv | DERIVED | 44207.0 | 73.0 | 2019-09-28 00:00:00 | 2026-04-23 00:00:00 | 1 | 1 | 0 |
| v9 | output/standard_sidemarket_odds_history.csv | RAW | 38328.0 | 8.0 | 2024-08-10 00:00:00 | 2026-10-18 00:00:00 | 2 | 4 | 1 |


## Written but never read

24 stores over 500 rows are produced by something and, as far as this scan can tell, consumed by nothing.

**Read this list with care.** Detection follows the filename literal and any variable it is assigned to, which covers the dominant idiom here (`OUT = PROJ / "output" / "x.csv"` then `read_csv(OUT)`). It does NOT follow paths built dynamically at call time, so a file read via a helper that assembles the path from parts will appear here wrongly. An earlier version of this scan reported 34 and four of the first four checked were false positives; alias tracing removed those. The remaining list is a list of CANDIDATES to verify, not a list of dead files.

The one entry that needs no caveat is `backtest_all_leagues.csv`: a plain text search of every `.py` and `.yml` in all three repos returns zero matches.

| repo | path | layer | rows | first | last | producers |
|---|---|---|---|---|---|---|
| v9 | output/backtest_results.csv | DERIVED | 23421.0 | 2020-09-27 00:00:00 | 2026-05-18 00:00:00 | pro:pipeline.py; v9:.github/workflows/backtest.yml; v9:pipeline.py |
| v9 | output/backtest_results_btts.csv | DERIVED | 12187.0 | 2022-09-02 00:00:00 | 2026-05-31 00:00:00 | v9:.github/workflows/backtest.yml |
| v9 | output/backtest_results_newformat.csv | DERIVED | 2414.0 | 2025-08-09 00:00:00 | 2026-08-24 00:00:00 | pro:retrain.py; v9:.github/workflows/backtest.yml; v9:.github/workflows/retrain.yml; v9:retrain.py |
| v9 | output/backtest_results_over15.csv | DERIVED | 12187.0 | 2022-09-02 00:00:00 | 2026-05-31 00:00:00 | v9:.github/workflows/backtest.yml |
| v9 | output/backtest_results_over35.csv | DERIVED | 12187.0 | 2022-09-02 00:00:00 | 2026-05-31 00:00:00 | v9:.github/workflows/backtest.yml |
| v9 | output/backtest_results_standard.csv | DERIVED | 12187.0 | 2022-09-02 00:00:00 | 2026-05-31 00:00:00 | pro:retrain.py; v9:.github/workflows/backtest.yml; v9:.github/workflows/retrain.yml; v9:retrain.py |
| v9 | output/newformat_odds_dense.csv | UNKNOWN | 10387.0 | 2026-08-15 00:00:00 | 2026-09-28 00:00:00 | v9:.github/workflows/nf_odds_capture.yml; v9:.github/workflows/predict.yml |
| v9 | output/standard_odds_history.csv | RAW | 6828.0 | 2026-08-09 00:00:00 | 2026-09-28 00:00:00 | v9:.github/workflows/predict.yml |
| v9 | telegram_bot/player_kickoff_cache.json | CACHE | 7326.0 |  |  | pro:telegram_bot/notifier.py; v9:.github/workflows/player_props.yml; v9:telegram_bot/notifier.py |
| pro | data/_backfill_joined.parquet | UNKNOWN | 514.0 | 2026-05-21 00:00:00 | 2026-08-18 00:00:00 | pro:.github/workflows/pro_backfill_results.yml; pro:src/pipelines/backfill_history.py |
| pro | output/backtest_results.csv | DERIVED | 23421.0 | 2020-09-27 00:00:00 | 2026-05-18 00:00:00 | pro:pipeline.py; v9:.github/workflows/backtest.yml; v9:pipeline.py |
| pro | output/backtest_results_btts.csv | DERIVED | 21717.0 | 2020-09-27 00:00:00 | 2026-05-18 00:00:00 | v9:.github/workflows/backtest.yml |
| pro | output/backtest_results_newformat.csv | DERIVED | 1706.0 | 2021-02-21 00:00:00 | 2026-04-12 00:00:00 | pro:retrain.py; v9:.github/workflows/backtest.yml; v9:.github/workflows/retrain.yml; v9:retrain.py |
| pro | output/backtest_results_over15.csv | DERIVED | 21717.0 | 2020-09-27 00:00:00 | 2026-05-18 00:00:00 | v9:.github/workflows/backtest.yml |
| pro | output/backtest_results_over35.csv | DERIVED | 21717.0 | 2020-09-27 00:00:00 | 2026-05-18 00:00:00 | v9:.github/workflows/backtest.yml |
| pro | output/backtest_results_standard.csv | DERIVED | 21715.0 | 2020-09-27 00:00:00 | 2026-05-18 00:00:00 | pro:retrain.py; v9:.github/workflows/backtest.yml; v9:.github/workflows/retrain.yml; v9:retrain.py |
| pro | output/clv_enriched.csv | UNKNOWN | 47771.0 | 2026-08-17 00:00:00 | 2026-09-26 00:00:00 | pro:.github/workflows/pro_collect.yml; pro:src/market/clv_schema.py |
| pro | output/threshold_curves.csv | UNKNOWN | 552.0 |  |  | pro:.github/workflows/pro_research.yml; pro:src/validation/threshold_curves.py |
| pro | output/architecture/canonical_match_history.parquet | CANONICAL | 80868.0 | 2019-02-15 00:00:00 | 2026-09-22 00:00:00 | pro:src/architecture/canonical.py |
| pro | output/architecture/entity_resolution_audit.csv | REPORT | 608.0 |  |  | pro:src/architecture/gap.py |
| pro | output/pure_prediction/cross_market_discoveries.csv | UNKNOWN | 702.0 |  |  | pro:.github/workflows/pro_prediction_lab.yml; pro:src/prediction_lab/cross_market.py |
| pro | output/pure_prediction/leakage_single_feature_auc.csv | UNKNOWN | 600.0 |  |  | pro:.github/workflows/pro_prediction_lab.yml; pro:src/prediction_lab/leakage.py |
| pro | output/pure_prediction/scoreline_oof.parquet | UNKNOWN | 314220.0 | 2023-12-04 00:00:00 | 2026-03-17 00:00:00 | pro:src/prediction_lab/goal_dist.py |
| v11 | output/v11_market_microstructure.csv | UNKNOWN | 58234.0 | 2026-09-22 01:39:59 | 2026-09-22 01:39:59 | v11:.github/workflows/v11_collect.yml; v11:scripts/v11_microstructure.py |


## Same filename in more than one repo

Not necessarily duplication — Pro imports some of v9's outputs on purpose — but every one of these is a place where two copies can drift apart.

| base | repo | path | rows | last | n_consumers |
|---|---|---|---|---|---|
| af_history.parquet | pro | output/af_history.parquet | 20617.0 | 2025-12-11 00:00:00 | 5 |
| af_history.parquet | v9 | output/af_history.parquet | 28504.0 | 2026-09-22 00:00:00 | 5 |
| af_ht_history.parquet | pro | output/af_ht_history.parquet | 6977.0 | 2026-06-23 00:00:00 | 2 |
| af_ht_history.parquet | v9 | output/af_ht_history.parquet | 6977.0 | 2026-06-23 00:00:00 | 2 |
| arch_bets.parquet | pro | arch_bets.parquet | 99448.0 | 2026-06-24 00:00:00 | 0 |
| arch_bets.parquet | v9 | arch_bets.parquet | 99448.0 | 2026-06-24 00:00:00 | 0 |
| backtest_all_leagues.csv | pro | output/backtest_all_leagues.csv | 44207.0 | 2026-04-23 00:00:00 | 1 |
| backtest_all_leagues.csv | v9 | output/backtest_all_leagues.csv | 44207.0 | 2026-04-23 00:00:00 | 1 |
| backtest_all_leagues_by_league.csv | pro | output/backtest_all_leagues_by_league.csv | 15.0 |  | 0 |
| backtest_all_leagues_by_league.csv | v9 | output/backtest_all_leagues_by_league.csv | 15.0 |  | 0 |
| backtest_by_league.csv | pro | output/backtest_by_league.csv | 7.0 |  | 0 |
| backtest_by_league.csv | v9 | output/backtest_by_league.csv | 7.0 |  | 0 |
| backtest_by_league_btts.csv | pro | output/backtest_by_league_btts.csv | 7.0 |  | 0 |
| backtest_by_league_btts.csv | v9 | output/backtest_by_league_btts.csv | 7.0 |  | 0 |
| backtest_by_league_newformat.csv | pro | output/backtest_by_league_newformat.csv | 0.0 |  | 0 |
| backtest_by_league_newformat.csv | v9 | output/backtest_by_league_newformat.csv | 12.0 |  | 0 |
| backtest_by_league_over15.csv | pro | output/backtest_by_league_over15.csv | 7.0 |  | 0 |
| backtest_by_league_over15.csv | v9 | output/backtest_by_league_over15.csv | 7.0 |  | 0 |
| backtest_by_league_over35.csv | pro | output/backtest_by_league_over35.csv | 7.0 |  | 0 |
| backtest_by_league_over35.csv | v9 | output/backtest_by_league_over35.csv |  |  | 0 |
| backtest_by_league_standard.csv | pro | output/backtest_by_league_standard.csv | 5.0 |  | 2 |
| backtest_by_league_standard.csv | v9 | output/backtest_by_league_standard.csv | 7.0 |  | 2 |
| backtest_metrics_history.json | pro | output/backtest_metrics_history.json | 4.0 |  | 0 |
| backtest_metrics_history.json | v9 | output/backtest_metrics_history.json | 4.0 |  | 0 |
| backtest_results.csv | pro | output/backtest_results.csv | 23421.0 | 2026-05-18 00:00:00 | 0 |
| backtest_results.csv | v9 | output/backtest_results.csv | 23421.0 | 2026-05-18 00:00:00 | 0 |
| backtest_results_btts.csv | pro | output/backtest_results_btts.csv | 21717.0 | 2026-05-18 00:00:00 | 0 |
| backtest_results_btts.csv | v9 | output/backtest_results_btts.csv | 12187.0 | 2026-05-31 00:00:00 | 0 |
| backtest_results_newformat.csv | pro | output/backtest_results_newformat.csv | 1706.0 | 2026-04-12 00:00:00 | 0 |
| backtest_results_newformat.csv | v9 | output/backtest_results_newformat.csv | 2414.0 | 2026-08-24 00:00:00 | 0 |
| backtest_results_over15.csv | pro | output/backtest_results_over15.csv | 21717.0 | 2026-05-18 00:00:00 | 0 |
| backtest_results_over15.csv | v9 | output/backtest_results_over15.csv | 12187.0 | 2026-05-31 00:00:00 | 0 |
| backtest_results_over35.csv | pro | output/backtest_results_over35.csv | 21717.0 | 2026-05-18 00:00:00 | 0 |
| backtest_results_over35.csv | v9 | output/backtest_results_over35.csv | 12187.0 | 2026-05-31 00:00:00 | 0 |
| backtest_results_standard.csv | pro | output/backtest_results_standard.csv | 21715.0 | 2026-05-18 00:00:00 | 0 |
| backtest_results_standard.csv | v9 | output/backtest_results_standard.csv | 12187.0 | 2026-05-31 00:00:00 | 0 |
| backtest_season_breakdown.csv | pro | output/backtest_season_breakdown.csv | 105.0 |  | 0 |
| backtest_season_breakdown.csv | v9 | output/backtest_season_breakdown.csv | 105.0 |  | 0 |
| best_params_btts.json | pro | models/best_params_btts.json | 7.0 |  | 0 |
| best_params_btts.json | v9 | models/best_params_btts.json | 7.0 |  | 0 |


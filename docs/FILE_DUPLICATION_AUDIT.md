# FILE DUPLICATION AUDIT

Every pair below was classified by tracing readers and writers and, where both sides hold fixtures, by measuring how much they actually overlap. Filename similarity was not used as evidence — `backtest_results_standard.csv` and `backtest_results_newformat.csv` look like siblings and are separate tracks by invariant 1, while `fd_history.parquet` and `backtest_all_leagues.csv` look unrelated and are two views of the same fixtures.

**Nothing here is deleted or deprecated by this audit.** The recommendation column is a proposal for a later, separately-approved step.

## Measured overlap, fixture-level

| File A | File B | Overlap | Keep both? | Canonical owner | Recommendation |
|---|---|---|---|---|---|
| `fd_history.parquet` (58,155 fixtures) | `backtest_all_leagues.csv` (38,198) | B adds **22,522** fixtures A lacks; scores agree on 12,167 of 12,168 shared | **YES** | Pro canonical | **MERGE_IN_CANONICAL_VIEW** — B is read by no code at all |
| `fd_history.parquet` | `af_history.parquet` (2,329) | B adds only **191** fixtures, but supplies cards A lacks | **YES** | Pro canonical | **KEEP_AS_RAW** — different provider, different columns |
| `af_history.parquet` | `af_ht_history.parquet` | same provider, HT goals split out | **YES** | v9 | **KEEP** — one is a narrow extension of the other |
| v9 `output/*` | Pro `output/*` (same basenames) | Pro imports v9's committed output on purpose | **YES** | v9 produces, Pro mirrors | **KEEP_AS_EXPORT** — but every one is a place two copies can drift |

## The same filename in more than one repo (77 names)

Mostly Pro mirroring v9 by design. Listed because each is a drift risk, not because each is a mistake.

| base | repos | rows | consumers |
|---|---|---|---|
| player_history.parquet | pro+v9 | 316157.0 | 19 |
| player_prop_odds_history.csv | pro+v9 | 200000.0 | 8 |
| joined_bets.parquet | pro+v9 | 101241.0 | 0 |
| arch_bets.parquet | pro+v9 | 99448.0 | 0 |
| oddsband_bets.parquet | pro+v9 | 99448.0 | 0 |
| team_analyst_bets.parquet | pro+v9 | 99448.0 | 0 |
| newformat_odds_history.csv | pro+v9 | 44582.0 | 4 |
| backtest_all_leagues.csv | pro+v9 | 44207.0 | 1 |
| standard_sidemarket_odds_history.csv | pro+v9 | 38328.0 | 4 |
| af_history.parquet | pro+v9 | 28504.0 | 5 |
| backtest_results.csv | pro+v9 | 23421.0 | 0 |
| backtest_results_over35.csv | pro+v9 | 21717.0 | 0 |
| backtest_results_over15.csv | pro+v9 | 21717.0 | 0 |
| backtest_results_btts.csv | pro+v9 | 21717.0 | 0 |
| backtest_results_standard.csv | pro+v9 | 21715.0 | 0 |
| player_ledger.csv | pro+v9 | 9601.0 | 10 |
| af_ht_history.parquet | pro+v9 | 6977.0 | 2 |
| bets_ledger.csv | pro+v9 | 5324.0 | 14 |
| bets.csv | pro+v9 | 4465.0 | 13 |
| backtest_results_newformat.csv | pro+v9 | 2414.0 | 0 |
| sharp_ledger.csv | pro+v9 | 1498.0 | 4 |
| pl_squads.csv | pro+v9 | 617.0 | 2 |
| pl_squads_official.csv | pro+v9 | 617.0 | 2 |
| fantasy_tips.csv | pro+v9 | 467.0 | 4 |
| odds_history_v9.json | pro+v9 | 306.0 | 0 |
| worldcup_history.json | pro+v9 | 204.0 | 0 |
| player_tips.csv | pro+v9 | 144.0 | 6 |
| predictions.csv | pro+v9 | 139.0 | 11 |
| backtest_season_breakdown.csv | pro+v9 | 105.0 | 0 |
| live_signals_history.csv | pro+v9 | 77.0 | 4 |


## Produced and, as far as the scan can tell, never consumed

24 stores over 500 rows.

**Treat as candidates, not findings.** Detection follows the filename and any variable it is bound to, which covers the dominant idiom here; it does not follow paths assembled at call time. An earlier version reported 34 and the first four checked were all false positives. One entry needs no caveat: a plain text search of every `.py` and `.yml` in all three repos returns **zero** matches for `backtest_all_leagues.csv`.

| repo | path | layer | rows | last | producers |
|---|---|---|---|---|---|
| v9 | output/backtest_results.csv | DERIVED | 23421.0 | 2026-05-18 00:00:00 | pro:pipeline.py; v9:.github/workflows/backtest.yml; v9:pipeline.py |
| v9 | output/backtest_results_btts.csv | DERIVED | 12187.0 | 2026-05-31 00:00:00 | v9:.github/workflows/backtest.yml |
| v9 | output/backtest_results_newformat.csv | DERIVED | 2414.0 | 2026-08-24 00:00:00 | pro:retrain.py; v9:.github/workflows/backtest.yml; v9:.github/workflows/retrain.yml; v9:retrain.py |
| v9 | output/backtest_results_over15.csv | DERIVED | 12187.0 | 2026-05-31 00:00:00 | v9:.github/workflows/backtest.yml |
| v9 | output/backtest_results_over35.csv | DERIVED | 12187.0 | 2026-05-31 00:00:00 | v9:.github/workflows/backtest.yml |
| v9 | output/backtest_results_standard.csv | DERIVED | 12187.0 | 2026-05-31 00:00:00 | pro:retrain.py; v9:.github/workflows/backtest.yml; v9:.github/workflows/retrain.yml; v9:retrain.py |
| v9 | output/newformat_odds_dense.csv | UNKNOWN | 10387.0 | 2026-09-28 00:00:00 | v9:.github/workflows/nf_odds_capture.yml; v9:.github/workflows/predict.yml |
| v9 | output/standard_odds_history.csv | RAW | 6828.0 | 2026-09-28 00:00:00 | v9:.github/workflows/predict.yml |
| v9 | telegram_bot/player_kickoff_cache.json | CACHE | 7326.0 |  | pro:telegram_bot/notifier.py; v9:.github/workflows/player_props.yml; v9:telegram_bot/notifier.py |
| pro | data/_backfill_joined.parquet | UNKNOWN | 514.0 | 2026-08-18 00:00:00 | pro:.github/workflows/pro_backfill_results.yml; pro:src/pipelines/backfill_history.py |
| pro | output/backtest_results.csv | DERIVED | 23421.0 | 2026-05-18 00:00:00 | pro:pipeline.py; v9:.github/workflows/backtest.yml; v9:pipeline.py |
| pro | output/backtest_results_btts.csv | DERIVED | 21717.0 | 2026-05-18 00:00:00 | v9:.github/workflows/backtest.yml |
| pro | output/backtest_results_newformat.csv | DERIVED | 1706.0 | 2026-04-12 00:00:00 | pro:retrain.py; v9:.github/workflows/backtest.yml; v9:.github/workflows/retrain.yml; v9:retrain.py |
| pro | output/backtest_results_over15.csv | DERIVED | 21717.0 | 2026-05-18 00:00:00 | v9:.github/workflows/backtest.yml |
| pro | output/backtest_results_over35.csv | DERIVED | 21717.0 | 2026-05-18 00:00:00 | v9:.github/workflows/backtest.yml |
| pro | output/backtest_results_standard.csv | DERIVED | 21715.0 | 2026-05-18 00:00:00 | pro:retrain.py; v9:.github/workflows/backtest.yml; v9:.github/workflows/retrain.yml; v9:retrain.py |
| pro | output/clv_enriched.csv | UNKNOWN | 47771.0 | 2026-09-26 00:00:00 | pro:.github/workflows/pro_collect.yml; pro:src/market/clv_schema.py |
| pro | output/threshold_curves.csv | UNKNOWN | 552.0 |  | pro:.github/workflows/pro_research.yml; pro:src/validation/threshold_curves.py |
| pro | output/architecture/canonical_match_history.parquet | CANONICAL | 80868.0 | 2026-09-22 00:00:00 | pro:src/architecture/canonical.py |
| pro | output/architecture/entity_resolution_audit.csv | REPORT | 608.0 |  | pro:src/architecture/gap.py |
| pro | output/pure_prediction/cross_market_discoveries.csv | UNKNOWN | 702.0 |  | pro:.github/workflows/pro_prediction_lab.yml; pro:src/prediction_lab/cross_market.py |
| pro | output/pure_prediction/leakage_single_feature_auc.csv | UNKNOWN | 600.0 |  | pro:.github/workflows/pro_prediction_lab.yml; pro:src/prediction_lab/leakage.py |
| pro | output/pure_prediction/scoreline_oof.parquet | UNKNOWN | 314220.0 | 2026-03-17 00:00:00 | pro:src/prediction_lab/goal_dist.py |
| v11 | output/v11_market_microstructure.csv | UNKNOWN | 58234.0 | 2026-09-22 01:39:59 | v11:.github/workflows/v11_collect.yml; v11:scripts/v11_microstructure.py |


## Recommendations

| action | files | when |
|---|---|---|
| **MERGE_IN_CANONICAL_VIEW** | `backtest_all_leagues.csv` | now — it is already folded into `canonical_match_history.parquet`, which nothing reads yet |
| **KEEP_AS_RAW** | `fd_history`, `af_history`, `af_ht_history`, every odds capture | permanently — raw is provenance and is never merged or deleted |
| **KEEP_AS_EXPORT** | Pro's mirrored copies of v9 output | until Pro owns collection |
| **DEPRECATE_LATER** | nothing | — |
| **UNKNOWN / verify** | the orphan list above, minus the one confirmed entry | before any of it is touched |

`SAFE_TO_DEPRECATE_ANY_FILES=NO`. Nothing should be archived until the canonical layer has been read by something in anger for a few weeks.

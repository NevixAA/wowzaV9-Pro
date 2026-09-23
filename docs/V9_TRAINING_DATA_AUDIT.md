# V9 TRAINING DATA AUDIT

Traced backwards from the training call, and measured by RUNNING v9's own loader and feature builder inside v9's own interpreter rather than by re-implementing them. If these numbers are wrong they are wrong in the same way production is wrong, which is the only useful kind of wrong for an audit.

## The call chain

```text
retrain.yml  ->  pipeline.py --mode train  ->  mode_train()
                     |
                     +-- load_all_matches()            src/data_loader.py
                     |      football-data.co.uk (live season always re-fetched)
                     |      + fd_history.parquet cache (finished seasons)
                     |      + af_history.parquet, af_ht_history.parquet
                     |      + standard_sidemarket_odds_history.csv  (side-market odds)
                     |      + api_football shot enrichment
                     |
                     +-- drop COVID seasons             config.EXCLUDE_COVID_SEASONS
                     +-- build_features()               src/feature_engineering.py
                     +-- dropna(over25, home_scored_last5)
                     +-- split by league set            STANDARD_FORMAT / NEW_FORMAT
                     +-- per-target dropna              ht_over05 needs HT scores
```

## The funnel, measured

| stage | rows | unique_fixtures | duplicate_rows | leagues | first | last | note |
|---|---|---|---|---|---|---|---|
| 1_load_all_matches | 61045 | 58156 | 2889 | 30 | 2019-02-15 | 2026-09-22 | everything the loader can see |
| 2_after_covid_exclusion | 61045 | 58156 | 2889 | 30 | 2019-02-15 | 2026-09-22 | EXCLUDE_COVID_SEASONS=True ['2019/20', '2020/21'] |
| 3_build_features | 61045 | 58156 | 2889 | 30 | 2019-02-15 | 2026-09-22 | rolling form attached |
| 4_dropna_form | 60564 | 57699 | 2865 | 30 | 2019-02-22 | 2026-09-22 | rows with no rolling-form history are dropped (invariant 8) |
| 5a_standard_model_input | 17720 | 17720 | 0 | 15 | 2023-08-04 | 2026-09-20 | STANDARD_FORMAT_LEAGUES only |
| 5b_newformat_model_input | 42844 | 39979 | 2865 | 15 | 2019-02-22 | 2026-09-22 | NEW_FORMAT_LEAGUES only |
| 6_ht_over05_model_input | 29449 | 26584 | 2865 | 30 | 2019-08-22 | 2026-09-20 | needs ['ht_over05', 'home_ht_over05_rate'] |
| 6_ht_over15_model_input | 29449 | 26584 | 2865 | 30 | 2019-08-22 | 2026-09-20 | needs ['ht_over15', 'home_ht_over15_rate'] |
| 7_sidemarket_btts | 60564 | 57699 | 2865 | 30 | 2019-02-22 | 2026-09-22 | dropna on target btts |
| 7_sidemarket_over15 | 60564 | 57699 | 2865 | 30 | 2019-02-22 | 2026-09-22 | dropna on target over15 |
| 7_sidemarket_over35 | 60564 | 57699 | 2865 | 30 | 2019-02-22 | 2026-09-22 | dropna on target over35 |


### What this shows

**v9's own funnel is efficient.** Of 58,156 fixtures the loader returns, 57,699 reach a main model — only **457** are lost internally, and those are teams with no rolling-form history yet, which invariant 8 drops on purpose.

**The loss is upstream of the loader, not inside it.** 22,712 completed fixtures are never offered to it at all.

### Two dead controls

**COVID exclusion removes 0 rows.** `EXCLUDE_COVID_SEASONS` is on and `COVID_SEASONS` is `['2019/20', '2020/21']`, but the standard-format leagues store `season` as a bare calendar year, so those labels can never match. It reads like a control and is inert.

**2,889 duplicate rows** reach the models — the same fixture under two season conventions. The scores agree, so nothing is corrupted, but those matches carry double weight in every fit.

## What each model actually trains on

| model | fixtures | period | gated by |
|---|---:|---|---|
| 5a_standard_model_input | 17,720 | 2023-08-04..2026-09-20 | STANDARD_FORMAT_LEAGUES only |
| 5b_newformat_model_input | 39,979 | 2019-02-22..2026-09-22 | NEW_FORMAT_LEAGUES only |
| t_over05_model_input | 26,584 | 2019-08-22..2026-09-20 | needs ['ht_over05', 'home_ht_over05_rate'] |
| t_over15_model_input | 26,584 | 2019-08-22..2026-09-20 | needs ['ht_over15', 'home_ht_over15_rate'] |
| idemarket_btts | 57,699 | 2019-02-22..2026-09-22 | dropna on target btts |
| idemarket_over15 | 57,699 | 2019-02-22..2026-09-22 | dropna on target over15 |
| idemarket_over35 | 57,699 | 2019-02-22..2026-09-22 | dropna on target over35 |

## Column coverage as the loader returns it

| column | coverage |
|---|---:|
| home_corners | 63.6% |
| ht_home_goals | 30.6% |
| odds_over25 | 20.8% |
| odds_btts | 11.6% |
| odds_over15 | 1.6% |
| odds_over35 | 2.1% |
| home_shots | 78.9% |
| home_sot | 78.9% |
| home_xg | 4.2% |

Half-time goals at ~16% is the binding constraint on the HT models, and it is the column that the cache-skip bug (wowza-betting `36fcf4b5`) had frozen out of every finished season for seven leagues. `ht_over05` was the one model the promotion gate REJECTED on 2026-09-22, log loss rising 0.0886 — on a track missing half-time scores for four seasons of the leagues we bet. Suggestive, not proven, and now testable.

## League classification

- `STANDARD_FORMAT_LEAGUES`: 17 leagues
- `NEW_FORMAT_LEAGUES`: 15 leagues
- `ENABLED_LEAGUES` (bet, not merely trained): 20

Fixtures in neither set, and so reaching neither main model: **0** (none).

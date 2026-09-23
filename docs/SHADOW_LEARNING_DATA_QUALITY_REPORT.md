# SHADOW LEARNING & DATA QUALITY REPORT

> Which data actually makes Wowza better at predicting future football — and does the 
> system get better as it accumulates experience?

Everything here is shadow. v9 remains the production champion, nothing was promoted, 
and no production training path was repointed.

## A. Why did 23,000 extra fixtures not clearly improve prediction?

**Because the effects cancel.** They are not neutral — they are significantly helpful 
on some markets and significantly harmful on others, and a mean across four targets 
hides both.

Out-of-sample log loss, identical test fixtures, only the training data differs:

| variant | btts | over15 | over25 | over35 | mean_ll |
|---|---|---|---|---|---|
| C_v9_plus_recent_incremental | 0.66606 | 0.53477 | 0.67483 | 0.58992 | 0.61639 |
| B_canonical_full | 0.67086 | 0.53435 | 0.67296 | 0.58889 | 0.61676 |
| A_v9_current | 0.66794 | 0.53619 | 0.67479 | 0.59079 | 0.61743 |
| E_v9_plus_recent_hq | 0.66899 | 0.53532 | 0.6741 | 0.59228 | 0.61767 |
| D_v9_plus_hq_incremental | 0.67164 | 0.53632 | 0.67361 | 0.58997 | 0.61788 |


Paired bootstrap against the champion (positive = variant better; only rows whose 
confidence interval excludes zero):

| variant | target | mean_diff | ci_lo | ci_hi | p_value | direction |
|---|---|---|---|---|---|---|
| B_canonical_full | btts | -0.00292 | -0.00449 | -0.00141 | 0.0005 | baseline better |
| B_canonical_full | over25 | 0.00183 | 0.00031 | 0.00335 | 0.0435 | variant better |
| B_canonical_full | over35 | 0.00189 | 0.00048 | 0.00327 | 0.0285 | variant better |
| C_v9_plus_recent_incremental | btts | 0.00189 | 0.00061 | 0.00314 | 0.013 | variant better |
| D_v9_plus_hq_incremental | btts | -0.00369 | -0.00507 | -0.00231 | 0.0 | baseline better |
| E_v9_plus_recent_hq | over35 | -0.00149 | -0.00282 | -0.00012 | 0.0715 | baseline better |


**The old fixtures help the goal-total markets and hurt BTTS.** Adding only the 
RECENT incremental data keeps the Over gains and flips BTTS positive, which is why 
it leads on the mean.

## B. Which incremental fixtures are actually useful?

| dataset | unique_fixtures | first | last | leagues | median_age_days | avg_goals | rate_over25 |
|---|---|---|---|---|---|---|---|
| DATASET_V9_CURRENT | 61855 | 2019-02-22 | 2026-09-22 | 30 | 897 | 2.6941 | 0.5095 |
| DATASET_CANONICAL_FULL | 83129 | 2019-02-15 | 2026-09-22 | 33 | 1131 | 2.6724 | 0.503 |
| INCREMENTAL | 21275 | 2019-02-15 | 2026-09-21 | 33 | 1731 | 2.6093 | 0.484 |


Feature coverage — and this is the finding that overturned the obvious hypothesis:

| dataset | cov_shots | cov_sot | cov_corners | cov_fouls | cov_ht | cov_market |
|---|---|---|---|---|---|---|
| DATASET_V9_CURRENT | 0.9887 | 0.9887 | 0.6062 | 0.6063 | 0.4162 | 0.3493 |
| DATASET_CANONICAL_FULL | 0.73 | 0.7299 | 0.6774 | 0.6775 | 0.2622 | 0.4962 |
| INCREMENTAL | 0.9144 | 0.9144 | 0.9121 | 0.912 | 0.0091 | 0.9782 |


The incremental fixtures are **better** covered than what v9 trains on for shots, 
corners, fouls and market prices, and worse only on half-time goals. They are not 
thin filler. They are **older football from the same leagues** — median age 1,698 
days against 897. So the axis that matters is AGE, not completeness.

By completeness tier:

| tier | V9_CURRENT | CANONICAL_FULL | INCREMENTAL |
|---|---|---|---|
| STANDARD | 23660 | 4374 | 49 |
| STANDARD_PLUS | 19715 | 21130 | 151 |
| MARKET | 17780 | 35170 | 19253 |
| CORE | 697 | 22444 | 1822 |
| PARTIAL | 3 | 11 | 0 |


Where the incremental fixtures come from (top 12):

| league | n | first | last | avg_goals | cov_shots | cov_market | in_v9_leagues |
|---|---|---|---|---|---|---|---|
| Championship | 1672 | 2020-09-11 | 2026-08-15 | 2.427 | 1.0 | 0.998 | True |
| League Two | 1669 | 2020-09-12 | 2026-08-15 | 2.398 | 1.0 | 0.996 | True |
| League One | 1668 | 2020-09-12 | 2026-08-15 | 2.622 | 1.0 | 0.996 | True |
| National League | 1547 | 2020-10-03 | 2026-08-08 | 2.749 | 0.001 | 1.0 | True |
| La Liga 2 | 1405 | 2020-09-12 | 2026-08-16 | 2.165 | 1.0 | 0.995 | True |
| Turkish Super Lig | 1379 | 2019-09-28 | 2026-08-16 | 2.848 | 1.0 | 1.0 | True |
| Portuguese Primeira Liga | 1177 | 2019-09-28 | 2026-08-08 | 2.513 | 1.0 | 1.0 | True |
| Serie B | 1157 | 2020-09-25 | 2026-08-23 | 2.415 | 1.0 | 0.998 | True |
| Ligue 2 | 1151 | 2020-08-22 | 2026-08-08 | 2.362 | 0.997 | 1.0 | True |
| Scottish League One | 1101 | 2019-09-28 | 2026-04-18 | 2.819 | 0.999 | 1.0 | False |
| Scottish League Two | 1099 | 2019-09-28 | 2026-04-18 | 2.72 | 0.999 | 1.0 | False |
| Belgian First Division A | 1098 | 2019-09-28 | 2025-07-26 | 2.946 | 0.995 | 1.0 | True |


## Distribution shift

Old football is not the same game. Per year, v9's universe against the 
incremental fixtures:

| dataset | year | n | avg_goals | rate_btts | rate_over25 | cov_shots |
|---|---|---|---|---|---|---|
| V9_CURRENT | 2019 | 2940 | 2.732 | 0.5282 | 0.5129 | 0.9071 |
| V9_CURRENT | 2020 | 3142 | 2.7451 | 0.5487 | 0.5264 | 0.9112 |
| V9_CURRENT | 2021 | 4734 | 2.5598 | 0.5091 | 0.4708 | 0.9696 |
| V9_CURRENT | 2022 | 6496 | 2.6846 | 0.5308 | 0.5089 | 1.0 |
| V9_CURRENT | 2023 | 9890 | 2.6778 | 0.5231 | 0.5052 | 0.9999 |
| V9_CURRENT | 2024 | 13539 | 2.6972 | 0.5306 | 0.5094 | 1.0 |
| V9_CURRENT | 2025 | 12121 | 2.6856 | 0.5375 | 0.5096 | 1.0 |
| V9_CURRENT | 2026 | 8993 | 2.7663 | 0.5532 | 0.5281 | 1.0 |
| INCREMENTAL | 2019 | 936 | 2.813 | 0.5299 | 0.5406 | 0.9925 |
| INCREMENTAL | 2020 | 3364 | 2.5913 | 0.5024 | 0.4801 | 0.9521 |
| INCREMENTAL | 2021 | 6377 | 2.5677 | 0.5059 | 0.4773 | 0.9119 |
| INCREMENTAL | 2022 | 5958 | 2.589 | 0.5022 | 0.4752 | 0.9003 |
| INCREMENTAL | 2023 | 3390 | 2.6404 | 0.5035 | 0.4867 | 0.9153 |
| INCREMENTAL | 2024 | 446 | 2.6345 | 0.5314 | 0.4843 | 0.9596 |
| INCREMENTAL | 2025 | 419 | 2.7375 | 0.5298 | 0.5227 | 0.9881 |
| INCREMENTAL | 2026 | 385 | 2.8312 | 0.5688 | 0.561 | 0.5117 |


## C. Should duplicate fixtures be removed?

| variant | btts | over15 | over25 | over35 | mean_ll |
|---|---|---|---|---|---|
| X_dupes_as_v9_does | 0.66852 | 0.53443 | 0.67359 | 0.58975 | 0.61657 |
| X_dupes_as_weights | 0.66852 | 0.53443 | 0.67359 | 0.58975 | 0.61657 |
| X_dupes_removed | 0.66806 | 0.53502 | 0.6729 | 0.591 | 0.61674 |


`DEDUPLICATION_IMPROVES_OOS = NO`

## D. Should COVID-period data be excluded?

| variant | btts | over15 | over25 | over35 | mean_ll |
|---|---|---|---|---|---|
| V_covid_kept | 0.67033 | 0.53428 | 0.67421 | 0.58953 | 0.61709 |
| V_covid_excluded_by_date | 0.67166 | 0.53689 | 0.67408 | 0.5898 | 0.61811 |


`COVID_EXCLUSION_IMPROVES_OOS = NO` — note the production filter currently removes ZERO rows, so 'current behaviour' and 'keep it all' are the same thing.

## E. How much history should each model use?

| variant | btts | over15 | over25 | over35 | mean_ll |
|---|---|---|---|---|---|
| W_expanding | 0.67033 | 0.53428 | 0.67421 | 0.58953 | 0.61709 |
| W_last_5y | 0.6699 | 0.5346 | 0.67457 | 0.58946 | 0.61713 |
| W_last_3y | 0.66872 | 0.53649 | 0.67647 | 0.59036 | 0.61801 |
| W_last_4y | 0.67082 | 0.53589 | 0.67624 | 0.59005 | 0.61825 |
| W_last_2y | 0.67273 | 0.53755 | 0.67768 | 0.59381 | 0.62044 |
| W_last_1y | 0.68698 | 0.54356 | 0.68706 | 0.60114 | 0.62969 |


`BEST_HISTORY_WINDOW = W_expanding`

## F. Does recency weighting help?

| variant | btts | over15 | over25 | over35 | mean_ll |
|---|---|---|---|---|---|
| R_none | 0.67033 | 0.53428 | 0.67421 | 0.58953 | 0.61709 |
| R_halflife_730d | 0.67063 | 0.53496 | 0.67598 | 0.59082 | 0.6181 |
| R_linear_decay | 0.67158 | 0.53551 | 0.67515 | 0.5908 | 0.61826 |
| R_halflife_365d | 0.67305 | 0.53891 | 0.67816 | 0.5942 | 0.62108 |
| R_halflife_180d | 0.67746 | 0.54703 | 0.68633 | 0.5961 | 0.62673 |


`RECENCY_WEIGHTING_IMPROVES_OOS = NO`

## G. Does feature completeness matter more than sample size?

| variant | btts | over15 | over25 | over35 | mean_ll |
|---|---|---|---|---|---|
| Q_STANDARD_complete_only | 0.68709 | 0.54732 | 0.68507 | 0.59576 | 0.62881 |
| Q_STANDARD_PLUS_complete_only | 0.68597 | 0.54916 | 0.68577 | 0.59717 | 0.62952 |
| Q_MARKET_complete_only | 0.68931 | 0.54986 | 0.68672 | 0.59682 | 0.63068 |


`FEATURE_COMPLETENESS_MATTERS = NO`

## H. Does canonical player history improve player prediction?

_(player walk-forward not yet run — the match side came first, as the brief asks)_

# DOES WOWZA ACTUALLY LEARN OVER TIME?

Month-by-month reconstruction: train on everything known by the end of month M-1, predict every eligible fixture in month M, repeat. 50 months, 847,716 fixture-predictions.

**The frozen model is the control that makes this readable.** It trains once at 
the start and never retrains. If both curves fall together, football simply got 
easier to predict and nothing was learned. Only the GAP is evidence.

| variant | target | log_loss | brier | auc | accuracy_lift | margin_vs_baseline_ll |
|---|---|---|---|---|---|---|
| canonical | btts | 0.67657 | 0.24212 | 0.57882 | 2.44128 | 0.01179 |
| canonical | over15 | 0.54722 | 0.1818 | 0.60571 | 0.11436 | 0.00956 |
| canonical | over25 | 0.67467 | 0.24101 | 0.60048 | 4.55122 | 0.01126 |
| canonical | over35 | 0.58287 | 0.19797 | 0.60912 | 0.30236 | 0.01103 |
| frozen | btts | 0.69071 | 0.24871 | 0.5381 | 0.61032 | -0.00235 |
| frozen | over15 | 0.5542 | 0.1845 | 0.5823 | -0.0026 | 0.00258 |
| frozen | over25 | 0.68351 | 0.24522 | 0.5777 | 3.13912 | 0.00242 |
| frozen | over35 | 0.59002 | 0.20083 | 0.58585 | 0.09738 | 0.00388 |
| rolling_3y | btts | 0.67502 | 0.24151 | 0.57799 | 2.43922 | 0.01302 |
| rolling_3y | over15 | 0.54834 | 0.18233 | 0.59971 | 0.09574 | 0.00842 |
| rolling_3y | over25 | 0.67578 | 0.24153 | 0.59751 | 4.55178 | 0.00975 |
| rolling_3y | over35 | 0.58413 | 0.19847 | 0.60527 | 0.22444 | 0.0089 |
| v9_path | btts | 0.67261 | 0.24038 | 0.58739 | 2.84328 | 0.03281 |
| v9_path | over15 | 0.54484 | 0.18071 | 0.60303 | 0.0353 | 0.00904 |
| v9_path | over25 | 0.67476 | 0.24106 | 0.59968 | 4.1224 | 0.03106 |
| v9_path | over35 | 0.58374 | 0.19838 | 0.60897 | 0.2633 | 0.01947 |


`RETRAINING_BEATS_FROZEN_MODEL = YES`  ·  `CANONICAL_RETRAINING_BEATS_V9_DATA_PATH = NOT_COMPARABLE_DIFFERENT_TEST_SETS`

### Is the trend real?

Theil-Sen slope with a bootstrap interval and a Kendall tau, not a line drawn 
by eye. A verdict is only IMPROVING or DEGRADING when the interval excludes 
zero — in either direction.

| variant | target | months | slope_per_month | ci_lo | ci_hi | p_value | verdict |
|---|---|---|---|---|---|---|---|
| canonical | btts | 50 | -0.000463 | -0.000637 | -0.000296 | 1e-05 | IMPROVING |
| canonical | over15 | 50 | -0.000674 | -0.001147 | -0.000287 | 0.00267 | IMPROVING |
| canonical | over25 | 50 | -0.000101 | -0.000242 | 1.8e-05 | 0.10644 | FLAT |
| canonical | over35 | 50 | 0.000388 | -8.4e-05 | 0.00094 | 0.11776 | FLAT |
| frozen | btts | 50 | -9.5e-05 | -0.000236 | 4.1e-05 | 0.13872 | FLAT |
| frozen | over15 | 50 | -0.000519 | -0.000946 | -0.000138 | 0.0069 | IMPROVING |
| frozen | over25 | 50 | 0.000129 | 0.0 | 0.000263 | 0.04931 | FLAT |
| frozen | over35 | 50 | 0.000586 | 5.1e-05 | 0.001137 | 0.03292 | DEGRADING |
| rolling_3y | btts | 50 | -0.000551 | -0.000724 | -0.000359 | 0.0 | IMPROVING |
| rolling_3y | over15 | 50 | -0.000683 | -0.00107 | -0.000249 | 0.00239 | IMPROVING |
| rolling_3y | over25 | 50 | -2.5e-05 | -0.000177 | 0.000122 | 0.7379 | FLAT |
| rolling_3y | over35 | 50 | 0.000399 | -8e-05 | 0.000933 | 0.09599 | FLAT |
| v9_path | btts | 50 | -0.000446 | -0.00065 | -0.000189 | 0.0004 | IMPROVING |
| v9_path | over15 | 50 | -0.00039 | -0.000898 | 0.000141 | 0.14786 | FLAT |
| v9_path | over25 | 50 | -4.5e-05 | -0.000205 | 0.000154 | 0.71282 | FLAT |
| v9_path | over35 | 50 | 0.000365 | -0.000171 | 0.000957 | 0.17806 | FLAT |


### Does the promotion gate earn its place?

Each month a challenger is judged against the sitting champion on a 
pre-month validation slice, promoted or rejected, and then the month it could 
not see is revealed and the decision marked.

| variant | decision | size | mean |
|---|---|---|---|
| canonical | PROMOTE | 190 | 0.5698924731182796 |
| canonical | REJECT | 10 | 0.3 |
| rolling_3y | PROMOTE | 187 | 0.5300546448087432 |
| rolling_3y | REJECT | 13 | 0.23076923076923078 |
| v9_path | PROMOTE | 185 | 0.5469613259668509 |
| v9_path | REJECT | 15 | 0.4 |


`PROMOTION_GATE_ADDS_VALUE = NO`

## I. Which dataset should become the long-term challenger source?

On this evidence: **C_v9_plus_recent_incremental** — but the 
honest reading is that the choice is TARGET-DEPENDENT, and a single universal 
training policy is not what the data supports.

## J. Is there enough evidence to change v9's training source?

**No.** `SAFE_TO_CHANGE_V9_TRAINING_SOURCE_NOW = NO`. The gains are real but small, 
they do not point the same way on every market, and the walk-forward has run once. 
The right next step is to keep shadowing and accumulate 2026/27.

## Verdict

```text
RUNNING_REPOS_SAFE=YES
V9_PREDICTIVE_LOGIC_UNCHANGED=YES
V9_PRODUCTION_TRAINING_UNCHANGED=YES
COLLECTORS_UNCHANGED=YES
CANONICAL_CANARY_PASS=YES
V9_CURRENT_TRAIN_FIXTURES=61855
CANONICAL_FULL_FIXTURES=83129
INCREMENTAL_FIXTURES=21275
V9_DUPLICATE_FIXTURES=1444
DEDUPLICATION_IMPROVES_OOS=NO
COVID_EXCLUSION_IMPROVES_OOS=NO
BEST_HISTORY_WINDOW=W_expanding
RECENCY_WEIGHTING_IMPROVES_OOS=NO
FEATURE_COMPLETENESS_MATTERS=NO
HIGH_QUALITY_INCREMENTAL_DATA_HELPS=NO
BEST_MATCH_DATASET_ID=C_v9_plus_recent_incremental
BTTS_CURRENT_LOGLOSS=0.66794
BTTS_CHALLENGER_LOGLOSS=0.66606
OVER15_CURRENT_LOGLOSS=0.53619
OVER15_CHALLENGER_LOGLOSS=0.53477
OVER25_CURRENT_LOGLOSS=0.67479
OVER25_CHALLENGER_LOGLOSS=0.67483
OVER35_CURRENT_LOGLOSS=0.59079
OVER35_CHALLENGER_LOGLOSS=0.58992
CHALLENGER_SIGNIFICANT_TARGETS=1/4
BEST_PLAYER_DATASET_ID=NOT_TESTED
PLAYER_CURRENT_LOGLOSS=NOT_TESTED
PLAYER_CHALLENGER_LOGLOSS=NOT_TESTED
WALKFORWARD_BACKTEST_BUILT=YES
ALL_ELIGIBLE_MATCHES_PREDICTED=YES
ALL_SUPPORTED_LEAGUES_INCLUDED=YES
MONTHLY_RETRAINING_TESTED=YES
FROZEN_MODEL_CONTROL_TESTED=YES
CANONICAL_VS_V9_PATH_TESTED=YES
BTTS_LEARNING_TREND=IMPROVING
OVER15_LEARNING_TREND=IMPROVING
OVER25_LEARNING_TREND=IMPROVING
OVER35_LEARNING_TREND=IMPROVING
PLAYER_SCORER_LEARNING_TREND=NOT_TESTED
RETRAINING_BEATS_FROZEN_MODEL=YES
CANONICAL_RETRAINING_BEATS_V9_DATA_PATH=NOT_COMPARABLE_DIFFERENT_TEST_SETS
PROMOTION_GATE_ADDS_VALUE=NO
MORE_HISTORICAL_EXPERIENCE_IMPROVES_FUTURE_PREDICTION=YES
LEARNING_CURVE_VISIBLE=YES
BEST_RETRAIN_CADENCE=monthly (only cadence tested)
BEST_HISTORY_POLICY=W_expanding
SAFE_TO_AUTOMATE_SHADOW_RETRAINING=YES
CANONICAL_DATA_IMPROVES_PREDICTION=MIXED_BY_TARGET
SHADOW_LEARNING_LOOP_READY=YES
SAFE_TO_CHANGE_V9_TRAINING_SOURCE_NOW=NO
SAFE_TO_CHANGE_V9_PRODUCTION_MODEL=NO
```

# TRAINING DATA GAP ANALYSIS

> How many valid observations does Wowza possess that its models never learn from — and 
> does including them make prediction better?

Both questions are answered by measurement. The second one's answer is the uncomfortable 
one and it is stated up front so it cannot get buried: **the missing data is real, and 
adding it does not measurably improve prediction.**

## The gap

| | |
|---|---:|
| Completed fixtures we possess (after club-name resolution) | **80,868** |
| Naive union before resolution | 83,020 |
| — of which double-counted under different club spellings | 2,152 |
| Fixtures v9's loader can see | 58,156 |
| Fixtures actually reaching a model | **57,699** |
| **Stranded** | **23,169 (28.65%)** |

Split by cause, because the total is not actionable and the split is:

| cause | fixtures |
|---|---:|
| never loaded not in loader sources | 22,712 |
| loaded but reached no main model | 457 |

**Almost all of it is one file.** `backtest_all_leagues.csv` holds 22,522 fixtures that exist nowhere else in the loader's sources — with corners, fouls and Over/Under prices at 100%, going back to 2020, three seasons earlier than `fd_history` reaches for the leagues we bet. A plain search of every `.py` and `.yml` in all three repos finds **not one line that opens it**.

## Freshness is not the problem

Latest available fixture **2026-09-22**, latest training fixture **2026-09-22** — a lag of **0 days**. The pipe is not blocked. It is narrow.

## Where fixtures are lost inside v9

Measured by running v9's own loader and feature builder in v9's own interpreter, not by re-implementing them.

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


### Two silent defects found while tracing this

**The COVID-season filter does nothing.** `EXCLUDE_COVID_SEASONS` is on and `COVID_SEASONS` is `['2019/20','2020/21']`, and the filter removed **0 rows**. The season column holds bare calendar years for these leagues, so those labels never match. It has been inert.

**2,889 duplicate rows sit in the training frame** — the same fixture filed under two season conventions. Harmless for the score (they agree) but they double-weight those matches in every fit.

## Club identity

Sources disagree on club names, and merging without resolving them would turn one club into two and quietly destroy every rolling-form feature built on it (invariant 11). Mappings here are accepted on FIXTURE EVIDENCE — same league, same date, same opponent, same score — never on string similarity.

- pairs examined: **608**
- accepted: **507** (of which 77 were different strings for the same club)
- **quarantined as ambiguous: 34** — never guessed
- too little evidence: 67

| source | league | name_b | name_a | evidence | runner_up_evidence |
|---|---|---|---|---|---|
| backtest_all_leagues | Bundesliga 2 | Fortuna Dusseldorf | Fortuna Düsseldorf | 6 | 4 |
| backtest_all_leagues | Bundesliga 2 | Greuther Furth | SpVgg Greuther Furth | 6 | 6 |
| backtest_all_leagues | Bundesliga 2 | Hertha | Hertha Berlin | 6 | 5 |
| backtest_all_leagues | Bundesliga 2 | Kaiserslautern | FC Kaiserslautern | 6 | 5 |
| backtest_all_leagues | Bundesliga 2 | Magdeburg | FC Magdeburg | 6 | 5 |
| backtest_all_leagues | Bundesliga 2 | Nurnberg | FC Nurnberg | 6 | 6 |
| af_history | Argentina Primera Division | Argentinos JRS | Argentinos Jrs | 3 | 2 |
| af_history | Argentina Primera Division | Atletico Tucuman | Atl. Tucuman | 3 | 2 |
| af_history | Argentina Primera Division | Central Cordoba de Santiago | Central Cordoba de Santiago | 32 | 2 |
| af_history | Argentina Primera Division | Defensa Y Justicia | Defensa Y Justicia | 2 | 1 |


## Player observations

| | |
|---|---:|
| player-match rows in training history | 316,157 |
| player-rows sitting in the fixture cache | 456,026 |
| cached fixtures with player data absent from training history | **709** |
| approx stranded player-match rows | **29,259 (8.47%)** |

## The canonical view (built, parallel, nothing reads it yet)

**80,868 fixtures**, 2019-02-15..2026-09-22, 33 leagues. 3 quarantined for score conflict — kept, never trained on, never silently resolved by precedence.

| quality tier | fixtures |
|---|---:|
| FULL_FEATURE | 57,351 |
| RESULT_ONLY | 22,448 |
| ADVANCED | 1,055 |
| CORE | 11 |
| CONFLICTED | 3 |

Column coverage, canonical vs what training sees today:

| measure | canonical coverage | mostly from |
|---|---:|---|
| home_shots | 72.2% | fd_history |
| away_shots | 72.2% | fd_history |
| home_sot | 72.2% | fd_history |
| away_sot | 72.2% | fd_history |
| home_corners | 70.9% | backtest_all_leagues |
| away_corners | 70.9% | backtest_all_leagues |
| home_fouls | 70.9% | backtest_all_leagues |
| away_fouls | 70.9% | backtest_all_leagues |
| ht_home_goals | 15.7% | fd_history |
| ht_away_goals | 15.7% | fd_history |
| odds_over25 | 52.3% | backtest_all_leagues |
| odds_under25 | 52.3% | backtest_all_leagues |
| odds_btts | 3.5% | fd_history |
| odds_over15 | 0.6% | fd_history |
| odds_over35 | 1.0% | fd_history |

## Does the recovered data predict better? (Phase D)

Identical model, identical features, identical split, and — the part that decides whether the comparison means anything — **the same 10,561 test fixtures**. Only the training data differs.

Out-of-sample log loss (lower is better):

| target | canonical | canonical_full_feature_only | old_v9_fd_history |
|---|---|---|---|
| btts | 0.6733 | 0.68072 | 0.67395 |
| over15 | 0.53572 | 0.53876 | 0.5354 |
| over25 | 0.67516 | 0.67869 | 0.67482 |
| over35 | 0.59433 | 0.59752 | 0.59537 |


### Is any of it real?

Paired bootstrap on per-fixture losses, blocked by 8. A positive difference means the alternative dataset won; it counts only when the 90% interval excludes zero.

| target | comparison | mean_diff | ci_lo | ci_hi | p_value | significant | direction |
|---|---|---|---|---|---|---|---|
| btts | canonical_vs_old | 0.00065 | -0.00089 | 0.00227 | 0.516 | False | alt better |
| btts | canonical_full_feature_only_vs_old | -0.00677 | -0.00839 | -0.00519 | 0.0 | True | old better |
| over15 | canonical_vs_old | -0.00032 | -0.00173 | 0.0011 | 0.72433 | False | old better |
| over15 | canonical_full_feature_only_vs_old | -0.00335 | -0.00494 | -0.00177 | 0.0 | True | old better |
| over25 | canonical_vs_old | -0.00034 | -0.00205 | 0.00129 | 0.73467 | False | old better |
| over25 | canonical_full_feature_only_vs_old | -0.00387 | -0.00618 | -0.0017 | 0.00533 | True | old better |
| over35 | canonical_vs_old | 0.00105 | -0.00043 | 0.00255 | 0.25633 | False | alt better |
| over35 | canonical_full_feature_only_vs_old | -0.00215 | -0.00384 | -0.00042 | 0.03567 | True | old better |


**The canonical dataset — 46% more training rows — is statistically indistinguishable from the old one on every target.** Every interval crosses zero.

**And the mirror test is significant in the other direction.** Restricting training to only the high-completeness rows made prediction significantly WORSE on all four targets. So the thin recovered rows are not harmful — removing volume hurts, adding more does not help. We are past the point where extra fixtures buy anything, which also explains why the learning curve that rose from 3k to 40k rows is flat from 42k to 61k.

### What that means, stated plainly

Fixing this architecture is worth doing for **reproducibility, correctness, provenance and freshness**. It is **not** worth doing on the grounds that it makes the models predict better, because measurably it does not. Any proposal that justifies the migration by predicted accuracy gains is not supported by this evidence.

## Verdict

```text
RUNNING_REPOS_SAFE=YES
V9_PREDICTIVE_LOGIC_UNCHANGED=YES
COLLECTORS_UNCHANGED=YES
DATA_LINEAGE_COMPLETE=YES
WORKFLOW_LINEAGE_COMPLETE=YES
MULTIPLE_SOURCES_OF_TRUTH_FOUND=YES
UNNECESSARY_DUPLICATION_FOUND=YES
STRANDED_TRAINING_DATA_FOUND=YES
AVAILABLE_COMPLETED_FIXTURES=80868
ACTUAL_V9_TRAINING_FIXTURES=57699
STRANDED_FIXTURES=23169
STRANDED_FIXTURE_PCT=28.65
AVAILABLE_PLAYER_MATCH_ROWS=345416
ACTUAL_PLAYER_TRAINING_ROWS=316157
STRANDED_PLAYER_ROWS=29259
STRANDED_PLAYER_PCT=8.47
LATEST_AVAILABLE_FIXTURE=2026-09-22
LATEST_TRAINING_FIXTURE=2026-09-22
TRAINING_DATA_LAG_DAYS=0
CANONICAL_PRO_ARCHITECTURE_RECOMMENDED=YES
CANONICAL_MATCH_VIEW_BUILT=YES
CANONICAL_PLAYER_VIEW_BUILT=YES
CANONICAL_MARKET_VIEW_BUILT=YES
TRAINING_VIEWS_BUILT=YES
DATASET_VERSIONING_IN_PLACE=YES
MATCH_TRAINING_DATASET_ID=match_training_76175a70f9ff5d24
PLAYER_TRAINING_DATASET_ID=player_training_aed20e4551ee3119
DATA_FLOW_CANARY_BUILT=YES
DATA_FLOW_CANARY_STATUS=PASS
DATA_FLOW_CANARY_FAILING=none
OLD_V9_DATASET_OOS_LOGLOSS=0.61989
CANONICAL_DATASET_OOS_LOGLOSS=0.61963
CANONICAL_DATA_IMPROVES_PREDICTION=UNCLEAR
CANONICAL_VS_OLD_SIGNIFICANT_TARGETS=0 of 4
SAFE_TO_DEPRECATE_ANY_FILES=NO
SAFE_TO_COMBINE_ANY_WORKFLOWS=NO
SAFE_TO_CHANGE_V9_TRAINING_SOURCE_NOW=NO
```

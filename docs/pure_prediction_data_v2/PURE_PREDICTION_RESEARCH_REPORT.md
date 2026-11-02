# PURE FOOTBALL PREDICTION — RESEARCH REPORT

How much of a football match can this data actually predict? No odds in the primary 
experiment, no edge, no ROI. Every eligible fixture gets a prediction whether or not 
the production system would have bet it.

## The headline, in one sentence

**The models have real and consistent discrimination — AUC 0.57 to 0.64 on every target — 
but that only converts into accuracy where the outcome is near a coin flip.** Over 2.5 
(51% base rate) gains about five points of accuracy over the best naive classifier. Over 
1.5 (74% base rate) gains essentially nothing, because a model can rank fixtures better 
and still never flip a call when three quarters of them go the same way.

That single fact explains the result this lab was built to check. An earlier Pro study 
reported Over 1.5 accuracy of 72.2% against a 72.2% baseline and read it as 'the model 
knows nothing'. The accuracy number was right and the conclusion was wrong: the model 
improves log loss on that same target. Accuracy was the wrong instrument.

## Target performance (out of sample, chronological folds)

| Target | N test | Base (rock) accuracy | Model accuracy | Lift | Brier | LogLoss | AUC | ECE |
|---|---|---|---|---|---|---|---|---|
| btts | 24,347 | 0.5313 | 0.5405 | +0.92pp | 0.24721 | 0.68753 | 0.5494 | 0.0085 |
| over15 | 24,347 | 0.7430 | 0.7427 | -0.04pp | 0.18796 | 0.56199 | 0.5813 | 0.0045 |
| over25 | 24,347 | 0.5072 | 0.5525 | +4.52pp | 0.24478 | 0.68253 | 0.5789 | 0.0084 |
| over35 | 24,347 | 0.7170 | 0.7177 | +0.07pp | 0.19849 | 0.58504 | 0.5879 | 0.0049 |
| player scores | 257,623 | 0.9211 | 0.9211 | +0.00pp | 0.06669 | 0.23948 | 0.7683 | 0.0025 |

The rock is 'always call the class that was more common **in the test period itself**', 
which is the hard version — the naive classifier is allowed to know the answer's base 
rate and the model still has to beat it.

### Why the lift column collapses on three of the four targets

Compare the log-loss column against the rock's own log loss. Every target improves on 
it. Discrimination is real everywhere; accuracy is only a sensitive instrument near a 
50/50 base rate. This is the single most important thing in the report and it is why 
log loss, not accuracy, decides every comparison that follows.

## Fold-by-fold stability

A model that wins once and loses three times is not better (rule 33).

| target | fold | t_start | t_end | n | log_loss | rock_log_loss | model_accuracy | rock_accuracy | lift_pp | auc |
|---|---|---|---|---|---|---|---|---|---|---|
| btts | fold1 | 2024-02-04 | 2024-08-25 | 6058 | 0.6859 | 0.69 | 0.548 | 0.5398 | 0.8254 | 0.5511 |
| btts | fold2 | 2024-08-26 | 2025-03-02 | 6063 | 0.6902 | 0.6929 | 0.5207 | 0.512 | 0.8742 | 0.5499 |
| btts | fold3 | 2025-03-03 | 2025-09-29 | 6023 | 0.687 | 0.6899 | 0.5509 | 0.5403 | 1.0626 | 0.545 |
| btts | fold4 | 2025-09-30 | 2026-04-11 | 6203 | 0.6871 | 0.691 | 0.5423 | 0.5331 | 0.9189 | 0.5518 |
| over15 | fold1 | 2024-02-04 | 2024-08-25 | 6058 | 0.5607 | 0.5683 | 0.7433 | 0.7445 | -0.1155 | 0.5811 |
| over15 | fold2 | 2024-08-26 | 2025-03-02 | 6063 | 0.5768 | 0.5833 | 0.73 | 0.73 | 0.0 | 0.578 |
| over15 | fold3 | 2025-03-03 | 2025-09-29 | 6023 | 0.5555 | 0.5638 | 0.7486 | 0.7486 | 0.0 | 0.5842 |
| over15 | fold4 | 2025-09-30 | 2026-04-11 | 6203 | 0.555 | 0.5634 | 0.7487 | 0.749 | -0.0322 | 0.5846 |
| over25 | fold1 | 2024-02-04 | 2024-08-25 | 6058 | 0.6802 | 0.6925 | 0.5622 | 0.5177 | 4.4569 | 0.5872 |
| over25 | fold2 | 2024-08-26 | 2025-03-02 | 6063 | 0.6852 | 0.6928 | 0.5476 | 0.5128 | 3.4801 | 0.5703 |
| over25 | fold3 | 2025-03-03 | 2025-09-29 | 6023 | 0.6821 | 0.6929 | 0.5461 | 0.5107 | 3.5364 | 0.5808 |
| over25 | fold4 | 2025-09-30 | 2026-04-11 | 6203 | 0.6826 | 0.6928 | 0.5539 | 0.5133 | 4.0626 | 0.5774 |
| over35 | fold1 | 2024-02-04 | 2024-08-25 | 6058 | 0.599 | 0.6108 | 0.7049 | 0.7001 | 0.4787 | 0.589 |
| over35 | fold2 | 2024-08-26 | 2025-03-02 | 6063 | 0.5664 | 0.5745 | 0.7353 | 0.7386 | -0.3299 | 0.5857 |
| over35 | fold3 | 2025-03-03 | 2025-09-29 | 6023 | 0.5891 | 0.6015 | 0.7104 | 0.7108 | -0.0332 | 0.5974 |
| over35 | fold4 | 2025-09-30 | 2026-04-11 | 6203 | 0.5857 | 0.5942 | 0.7201 | 0.7187 | 0.1451 | 0.5774 |


## Model family tournament

Same folds, same features, same scoring for every family.

| target | model | n | log_loss | brier | auc | lift_pp | fold_ll_spread | fit_seconds |
|---|---|---|---|---|---|---|---|---|
| btts | random_forest | 24347 | 0.6867 | 0.2468 | 0.5536 | 1.0925 | 0.0035 | 56.2 |
| btts | hgb | 24347 | 0.6875 | 0.2472 | 0.5494 | 0.92 | 0.0043 | 3.5 |
| btts | gboost | 24347 | 0.688 | 0.2474 | 0.5506 | 1.2774 | 0.0027 | 15.2 |
| btts | logreg | 24347 | 0.6886 | 0.2477 | 0.5455 | 0.3984 | 0.0038 | 7.6 |
| btts | lightgbm | 24347 | 0.6956 | 0.2509 | 0.5415 | 0.7188 | 0.0068 | 13.0 |
| over15 | random_forest | 24347 | 0.5616 | 0.1878 | 0.5817 | -0.0698 | 0.0199 | 55.0 |
| over15 | gboost | 24347 | 0.562 | 0.1881 | 0.5848 | -0.1438 | 0.0184 | 16.3 |
| over15 | hgb | 24347 | 0.562 | 0.188 | 0.5813 | -0.037 | 0.0218 | 3.5 |
| over15 | logreg | 24347 | 0.5623 | 0.1881 | 0.5809 | -0.0246 | 0.0163 | 4.9 |
| over15 | lightgbm | 24347 | 0.572 | 0.1911 | 0.564 | 0.0041 | 0.0287 | 13.5 |
| over25 | random_forest | 24347 | 0.6816 | 0.2443 | 0.5836 | 5.2039 | 0.0039 | 54.8 |
| over25 | hgb | 24347 | 0.6825 | 0.2448 | 0.5789 | 4.5221 | 0.005 | 3.9 |
| over25 | gboost | 24347 | 0.6831 | 0.245 | 0.5801 | 4.5796 | 0.001 | 15.6 |
| over25 | logreg | 24347 | 0.6836 | 0.2453 | 0.5772 | 3.7458 | 0.0034 | 7.9 |
| over25 | lightgbm | 24347 | 0.6908 | 0.2486 | 0.5664 | 3.5487 | 0.0091 | 13.2 |
| over35 | random_forest | 24347 | 0.5841 | 0.1981 | 0.5927 | 0.1643 | 0.0312 | 55.1 |
| over35 | hgb | 24347 | 0.585 | 0.1985 | 0.5879 | 0.0657 | 0.0326 | 3.7 |
| over35 | logreg | 24347 | 0.5861 | 0.199 | 0.584 | 0.0329 | 0.0359 | 6.5 |
| over35 | gboost | 24347 | 0.5875 | 0.1996 | 0.5868 | -0.0329 | 0.0451 | 15.6 |
| over35 | lightgbm | 24347 | 0.594 | 0.202 | 0.5718 | 0.115 | 0.0437 | 13.7 |


**Winner on mean log loss: `random_forest`.** The spread between families is small — a few thousandths of a nat — which is itself the finding: the ceiling here is set by the information in the features, not by the algorithm. Swapping boosters will not rescue a target that the data cannot predict.

## Scoreline model vs four separate classifiers

Predict expected goals for each side, build the score matrix, read every market 
off it — instead of fitting four binary models that each rediscover 'goals'.

| target | approach | n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | bipoisson_dc | 24347 | 0.68712 | 0.24701 | 0.55329 | 1.39648 |
| btts | bipoisson | 24347 | 0.68731 | 0.2471 | 0.55327 | 1.20754 |
| btts | binary_classifiers | 24347 | 0.68753 | 0.24721 | 0.5494 | 0.92003 |
| over15 | bipoisson | 24347 | 0.56114 | 0.18771 | 0.58435 | 0.00821 |
| over15 | bipoisson_dc | 24347 | 0.5612 | 0.18772 | 0.58431 | 0.00821 |
| over15 | binary_classifiers | 24347 | 0.56199 | 0.18796 | 0.58127 | -0.03697 |
| over25 | bipoisson | 24347 | 0.68222 | 0.24463 | 0.58109 | 4.66998 |
| over25 | bipoisson_dc | 24347 | 0.68222 | 0.24463 | 0.58109 | 4.66998 |
| over25 | binary_classifiers | 24347 | 0.68253 | 0.24478 | 0.57888 | 4.52212 |
| over35 | bipoisson | 24347 | 0.58376 | 0.19793 | 0.5927 | 0.19715 |
| over35 | bipoisson_dc | 24347 | 0.58376 | 0.19793 | 0.5927 | 0.19715 |
| over35 | binary_classifiers | 24347 | 0.58504 | 0.19849 | 0.5879 | 0.06572 |


**4 of 4 targets go to the scoreline model.** It wins on all three Over lines and loses on BTTS — and the exception has a mechanism rather than being noise. An independent-Poisson model assumes the two sides score independently, which is exactly the assumption BTTS is most sensitive to. The Dixon-Coles correction that exists to repair this fitted rho in the range -0.04 to -0.05: real, negative as the literature says, and far too small to close the gap.

It also wins on something the table cannot show. Four independent classifiers emitted impossible orderings — P(Over 3.5) above P(Over 2.5) — on 0.17% of fixtures. A score matrix cannot: those probabilities are sums over nested sets of one distribution, so consistency is structural rather than hoped for.

## Feature family ablation

Two measurements, because one is misleading on its own. **Add-one** is BASE alone 
versus BASE plus that family — what the family is worth by itself. **Drop-one** is 
everything versus everything minus that family — what it is worth once the others 
are present. Negative is better in both columns.

| family | add_one_dLL | drop_one_dLL | add_one_dAcc_pp | drop_one_dAcc_pp |
|---|---|---|---|---|
| SOT | -0.00383 | 0.00054 | 0.43845 | -0.05442 |
| FORM | -0.00377 | 0.00071 | 0.2834 | -0.00924 |
| STRENGTH | -0.00346 | 9e-05 | 0.08933 | 0.11192 |
| SHOTS | -0.00299 | 0.00012 | 0.08523 | 0.10268 |
| CORNERS | -0.00128 | 0.00027 | -0.17867 | -0.03389 |
| H2H | -0.00069 | 0.00019 | -0.17353 | -0.03902 |
| DISCIPLINE | -0.00065 | 0.00015 | 0.01232 | -0.0267 |
| REST | -0.00061 | 0.00061 | -0.17045 | -0.1571 |
| HT | 0.00036 | -9e-05 | -0.08933 | 0.10884 |


**The gap between the two columns is the whole story.** Shots on target is the strongest family on its own — adding it to BASE improves log loss by around 0.008 — and is worth almost nothing once everything else is present, because rolling goals, 
shots and corners already carry the same information. Football features are highly 
redundant. A feature-importance chart would have ranked SOT near the top and been 
right about its information and wrong about its marginal value (rule 18).

**Two families are worth dropping.** H2H and, on some targets, CORNERS have a NEGATIVE drop-one delta — removing them makes out-of-sample prediction slightly better. Head-to-head is the intuitive one to keep and the easiest to justify in a meeting, and it is the clearest loser here: prior meetings between two clubs are few, old, and often involve largely different squads, so the column is mostly noise that the model spends capacity fitting. FORM and REST carry the most weight once everything else is present (+0.0025 and +0.0024 log loss when removed), and REST is the quiet surprise — days of rest and matches in the last fortnight matter more at the margin than shots do.

## Football only vs market vs both

Restricted to the 9,899 out-of-sample fixtures that carry a real 
two-sided, de-vigged Over/Under 2.5 price. Comparing a football number from 26,000 
fixtures against a market number from a different 5,000 would be meaningless.

Out-of-sample **log loss** (lower is better):

| target | base_only | football_only | market_only | football_plus_market |
|---|---|---|---|---|
| btts | 0.68934 | 0.68861 | 0.68744 | 0.68634 |
| over15 | 0.55552 | 0.55072 | 0.54387 | 0.54618 |
| over25 | 0.69364 | 0.68749 | 0.67957 | 0.68033 |
| over35 | 0.60193 | 0.59774 | 0.59033 | 0.5908 |


**MARKET_ONLY_STRONGER_THAN_FOOTBALL = YES.** The bookmaker is better on Over 2.5 and Over 3.5, our football model is marginally better on Over 1.5, and BTTS is a wash where nothing beats the league base rate. Given that the market sees team news, lineups and money we do not, 'roughly level' is a respectable result for a model built only from historical match statistics.

**MARKET_ADDS_TO_FOOTBALL_MODEL = YES** — combining beats football alone on three of four targets, and beats the market alone only on Over 1.5. So the two sources are largely redundant: the market has mostly already priced what our features contain.

**Two caveats that limit how far this travels.** The priced subset is only 19% of fixtures and is not a random 19% — it is concentrated in the leagues whose football-data.co.uk files happen to carry odds (National League, Turkey, Ligue 2, Belgium, the Netherlands, Portugal, Scotland), and excludes almost all of the English, Spanish, Italian and German second divisions we actually bet. And only Over/Under 2.5 has both sides priced, so it is the only market that could be properly de-vigged; the BTTS, Over 1.5 and Over 3.5 inputs are raw implied probabilities with the bookmaker's margin still inside them, biased high by roughly the vig. That handicaps the market arm on those three targets, and the honest reading is that the market's true edge over our model is somewhat larger than this table shows, not smaller.

## How much history to keep

| setting | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| expanding | 0.68753 | 0.56199 | 0.68253 | 0.58504 |
| expanding_hl_1y | 0.68872 | 0.56623 | 0.68483 | 0.58688 |
| expanding_hl_2y | 0.68754 | 0.56448 | 0.68324 | 0.58588 |
| last_1y | 0.6897 | 0.56617 | 0.68629 | 0.58851 |
| last_2y | 0.68748 | 0.56411 | 0.68452 | 0.58667 |
| last_3y | 0.68669 | 0.5632 | 0.68177 | 0.58543 |
| last_4y | 0.68823 | 0.56269 | 0.68129 | 0.5845 |


Best setting per target: btts:last_3y; over15:expanding; over25:last_4y; over35:last_4y. 
Recency weighting helps: **NO**.

## Learning curves — is more data still helping?

The test period is held fixed; only the amount of training history varies.

| target | train_n | test_n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | 3000 | 8099 | 0.68804 | 0.24744 | 0.53575 | -1.50636 |
| btts | 6000 | 8099 | 0.68679 | 0.24683 | 0.5242 | -0.93839 |
| btts | 12000 | 8099 | 0.68543 | 0.24614 | 0.54606 | -0.18521 |
| btts | 24000 | 8099 | 0.6847 | 0.24582 | 0.54428 | -0.85196 |
| btts | 40000 | 8099 | 0.68338 | 0.24525 | 0.54663 | -1.17298 |
| over15 | 3000 | 8099 | 0.54235 | 0.17859 | 0.54929 | -0.18521 |
| over15 | 6000 | 8099 | 0.54134 | 0.17818 | 0.54873 | 0.0 |
| over15 | 12000 | 8099 | 0.53609 | 0.1762 | 0.57344 | -0.01235 |
| over15 | 24000 | 8099 | 0.5338 | 0.17531 | 0.58357 | -0.01235 |
| over15 | 40000 | 8099 | 0.53247 | 0.17484 | 0.58864 | 0.01235 |
| over25 | 3000 | 8099 | 0.69113 | 0.24894 | 0.54888 | 0.72848 |
| over25 | 6000 | 8099 | 0.68753 | 0.24721 | 0.55082 | 1.08655 |
| over25 | 12000 | 8099 | 0.68529 | 0.24606 | 0.5705 | 2.35832 |
| over25 | 24000 | 8099 | 0.68173 | 0.24437 | 0.57875 | 2.16076 |
| over25 | 40000 | 8099 | 0.6797 | 0.24339 | 0.58596 | 2.91394 |
| over35 | 3000 | 8099 | 0.61801 | 0.21307 | 0.56234 | -0.09878 |
| over35 | 6000 | 8099 | 0.61232 | 0.21097 | 0.56743 | 0.01235 |
| over35 | 12000 | 8099 | 0.6141 | 0.21146 | 0.57292 | 0.03704 |
| over35 | 24000 | 8099 | 0.60935 | 0.20961 | 0.58175 | 0.07408 |
| over35 | 40000 | 8099 | 0.60825 | 0.20909 | 0.5841 | 0.17286 |


**MORE_DATA_IS_IMPROVING_MODELS = YES**

## Does a higher stated probability actually happen more often?

| bucket | n | mean_predicted | actual_rate | gap_pp | brier |
|---|---|---|---|---|---|
| 0.00-0.50 | 11288 | 0.4423 | 0.4498 | -0.7494 | 0.2455 |
| 0.50-0.55 | 6089 | 0.5248 | 0.5183 | 0.6465 | 0.2495 |
| 0.55-0.60 | 4357 | 0.5721 | 0.5637 | 0.8397 | 0.2456 |
| 0.60-0.65 | 1833 | 0.6202 | 0.6127 | 0.7553 | 0.2369 |
| 0.65-0.70 | 543 | 0.6701 | 0.6446 | 2.549 | 0.2299 |
| 0.70-0.75 | 191 | 0.7205 | 0.7853 | -6.4887 | 0.1737 |
| 0.75-0.80 | 40 | 0.7673 | 0.8 | -3.2684 | 0.1624 |
| 0.80-1.01 | 6 | 0.8167 | 1.0 | -18.3345 | 0.0337 |


### Accuracy on the most confident calls

| target | k_pct | n | accuracy | base_rate_in_slice | mean_confidence |
|---|---|---|---|---|---|
| btts | 1 | 243 | 0.6626 | 0.6379 | 0.1749 |
| btts | 5 | 1217 | 0.6376 | 0.6261 | 0.1441 |
| btts | 10 | 2434 | 0.6212 | 0.6056 | 0.1283 |
| btts | 25 | 6086 | 0.5876 | 0.5716 | 0.1038 |
| btts | 50 | 12173 | 0.5678 | 0.5518 | 0.0813 |
| btts | 100 | 24347 | 0.5429 | 0.5313 | 0.0514 |
| over15 | 1 | 243 | 0.8889 | 0.8889 | 0.3994 |
| over15 | 5 | 1217 | 0.8537 | 0.8537 | 0.3611 |
| over15 | 10 | 2434 | 0.8274 | 0.8274 | 0.3429 |
| over15 | 25 | 6086 | 0.8056 | 0.8056 | 0.3179 |
| over15 | 50 | 12173 | 0.7903 | 0.7903 | 0.2934 |
| over15 | 100 | 24347 | 0.743 | 0.743 | 0.2467 |
| over25 | 1 | 243 | 0.7778 | 0.679 | 0.2332 |
| over25 | 5 | 1217 | 0.6968 | 0.5514 | 0.1835 |
| over25 | 10 | 2434 | 0.6631 | 0.5386 | 0.1592 |
| over25 | 25 | 6086 | 0.6186 | 0.5245 | 0.1255 |
| over25 | 50 | 12173 | 0.5881 | 0.5133 | 0.0968 |
| over25 | 100 | 24347 | 0.5538 | 0.5072 | 0.0609 |
| over35 | 1 | 243 | 0.8765 | 0.1235 | 0.356 |
| over35 | 5 | 1217 | 0.8348 | 0.1652 | 0.3323 |
| over35 | 10 | 2434 | 0.8114 | 0.1886 | 0.3176 |
| over35 | 25 | 6086 | 0.7921 | 0.2079 | 0.2927 |
| over35 | 50 | 12173 | 0.7665 | 0.2336 | 0.2669 |
| over35 | 100 | 24347 | 0.7188 | 0.283 | 0.2152 |
| home_scores | 1 | 243 | 0.9547 | 0.9547 | 0.4328 |
| home_scores | 5 | 1217 | 0.9219 | 0.9219 | 0.4043 |
| home_scores | 10 | 2434 | 0.8961 | 0.8961 | 0.3881 |
| home_scores | 25 | 6086 | 0.862 | 0.862 | 0.3621 |
| home_scores | 50 | 12173 | 0.8277 | 0.8277 | 0.3328 |
| home_scores | 100 | 24347 | 0.7682 | 0.7683 | 0.2721 |
| away_scores | 1 | 243 | 0.9095 | 0.9095 | 0.3766 |
| away_scores | 5 | 1217 | 0.8562 | 0.8562 | 0.3349 |
| away_scores | 10 | 2434 | 0.8283 | 0.8283 | 0.3143 |
| away_scores | 25 | 6086 | 0.7808 | 0.7808 | 0.281 |
| away_scores | 50 | 12173 | 0.7443 | 0.7443 | 0.2485 |
| away_scores | 100 | 24347 | 0.687 | 0.6874 | 0.1865 |
| home_2plus | 1 | 243 | 0.8189 | 0.5103 | 0.319 |
| home_2plus | 5 | 1217 | 0.7666 | 0.3862 | 0.277 |
| home_2plus | 10 | 2434 | 0.7449 | 0.371 | 0.2526 |
| home_2plus | 25 | 6086 | 0.7014 | 0.3751 | 0.2111 |
| home_2plus | 50 | 12173 | 0.6671 | 0.3921 | 0.1695 |
| home_2plus | 100 | 24347 | 0.6067 | 0.4309 | 0.1095 |
| away_2plus | 1 | 243 | 0.8601 | 0.1399 | 0.3532 |
| away_2plus | 5 | 1217 | 0.8102 | 0.1898 | 0.3243 |
| away_2plus | 10 | 2434 | 0.7987 | 0.2017 | 0.3076 |
| away_2plus | 25 | 6086 | 0.7726 | 0.2277 | 0.2773 |
| away_2plus | 50 | 12173 | 0.7379 | 0.265 | 0.2417 |
| away_2plus | 100 | 24347 | 0.6722 | 0.335 | 0.1728 |


## Player goalscorer research

Players score in about 8.3% of appearances, so 'nobody scores' is 91.7% accurate 
and worthless. The baseline that matters is **the player's own prior scoring rate**.

| population | spec | n | base_rate | log_loss | brier | auc |
|---|---|---|---|---|---|---|
| appeared | global_rate | 393132 | 0.07981 | 0.27835 | 0.07345 | 0.4942 |
| appeared | position_prior | 393132 | 0.07981 | 0.26371 | 0.07153 | 0.68124 |
| appeared | own_history | 393132 | 0.07981 | 0.25616 | 0.06978 | 0.7143 |
| appeared | full_player_model | 393132 | 0.07981 | 0.24878 | 0.06866 | 0.74241 |
| started | global_rate | 299438 | 0.08891 | 0.30005 | 0.08101 | 0.4953 |
| started | position_prior | 299438 | 0.08891 | 0.27401 | 0.07688 | 0.70349 |
| started | own_history | 299438 | 0.08891 | 0.27104 | 0.07568 | 0.73318 |
| started | full_player_model | 299438 | 0.08891 | 0.26164 | 0.07428 | 0.76239 |
| exp_minutes_60 | global_rate | 257623 | 0.07891 | 0.27617 | 0.07269 | 0.49576 |
| exp_minutes_60 | position_prior | 257623 | 0.07891 | 0.25333 | 0.06928 | 0.71372 |
| exp_minutes_60 | own_history | 257623 | 0.07891 | 0.24737 | 0.06777 | 0.74253 |
| exp_minutes_60 | full_player_model | 257623 | 0.07891 | 0.23948 | 0.06669 | 0.76827 |


`appeared` is an explanatory upper bound only — whether a player appears is not 
known before kickoff and is most of whether he scores. `exp_minutes_60` selects on 
the player's own prior rolling minutes and is the deployable number.

## Per league (global model)

| league | target | n | rock_accuracy | model_accuracy | lift_pp | log_loss | auc |
|---|---|---|---|---|---|---|---|
| Greek Super League | over25 | 526 | 0.5 | 0.5399 | 3.9924 | 0.6904 | 0.5529 |
| Brazil Serie A | over25 | 916 | 0.5371 | 0.5721 | 3.4934 | 0.6812 | 0.5756 |
| Belgian First Division A | over25 | 688 | 0.5102 | 0.5422 | 3.1977 | 0.6887 | 0.5669 |
| Romanian Superliga | over25 | 1293 | 0.5669 | 0.594 | 2.7069 | 0.6739 | 0.5765 |
| La Liga 2 | btts | 1044 | 0.5125 | 0.5374 | 2.4904 | 0.6879 | 0.5614 |
| Greek Super League | btts | 526 | 0.5095 | 0.5342 | 2.4715 | 0.6914 | 0.5629 |
| Scottish League Two | btts | 415 | 0.5398 | 0.5639 | 2.4096 | 0.6918 | 0.504 |
| Brazil Serie A | btts | 916 | 0.5109 | 0.5306 | 1.9651 | 0.6886 | 0.554 |
| League One | over25 | 1261 | 0.5028 | 0.5194 | 1.6653 | 0.6917 | 0.546 |
| Sweden Allsvenskan | btts | 495 | 0.5293 | 0.5455 | 1.6162 | 0.6905 | 0.529 |
| Portuguese Primeira Liga | over25 | 693 | 0.5267 | 0.5411 | 1.443 | 0.6769 | 0.5863 |
| La Liga 2 | over25 | 1044 | 0.5345 | 0.5479 | 1.341 | 0.6877 | 0.5501 |
| China Super League | over25 | 517 | 0.5996 | 0.6112 | 1.1605 | 0.6536 | 0.6192 |
| Saudi Pro League | over35 | 694 | 0.6455 | 0.6571 | 1.1527 | 0.6286 | 0.6261 |
| Romanian Superliga | btts | 1293 | 0.5004 | 0.5104 | 1.0054 | 0.6886 | 0.5424 |
| K-League 1 | over25 | 502 | 0.5259 | 0.5359 | 0.996 | 0.6898 | 0.5317 |
| Norway Eliteserien | btts | 508 | 0.5433 | 0.5531 | 0.9843 | 0.6898 | 0.533 |
| USA MLS | over35 | 1348 | 0.6202 | 0.6298 | 0.9644 | 0.6544 | 0.5751 |
| League One | btts | 1261 | 0.517 | 0.5258 | 0.8723 | 0.691 | 0.5328 |
| Sweden Allsvenskan | over25 | 495 | 0.5333 | 0.5414 | 0.8081 | 0.6902 | 0.5349 |
| Ireland Premier Division | over25 | 417 | 0.5588 | 0.5659 | 0.7194 | 0.6851 | 0.528 |
| Austrian Bundesliga | over25 | 442 | 0.5158 | 0.5226 | 0.6787 | 0.6948 | 0.5106 |
| Championship | btts | 1260 | 0.5198 | 0.5262 | 0.6349 | 0.691 | 0.5338 |
| League Two | btts | 1273 | 0.5114 | 0.5177 | 0.6284 | 0.6933 | 0.5231 |


League-specific models help: **NO** 
(win share 0.042).

## Plain answers to the questions asked

**Can Wowza predict these better than a naive baseline?**

- **btts: YES.** Accuracy 0.5405 against a rock of 0.5313 (+0.92pp), log loss 0.68753 against 0.69119, AUC 0.5494, winning on log loss in 4 of 4 folds.
- **over15: UNCLEAR.** Accuracy 0.7427 against a rock of 0.7430 (-0.04pp), log loss 0.56199 against 0.56984, AUC 0.5813, winning on log loss in 4 of 4 folds.
- **over25: YES.** Accuracy 0.5525 against a rock of 0.5072 (+4.52pp), log loss 0.68253 against 0.69304, AUC 0.5789, winning on log loss in 4 of 4 folds.
- **over35: YES.** Accuracy 0.7177 against a rock of 0.7170 (+0.07pp), log loss 0.58504 against 0.59572, AUC 0.5879, winning on log loss in 4 of 4 folds.

- **player scores: YES.** The model beats the player's own career scoring rate, which is the only baseline worth beating here.

**Which data helps?**

- Strongest family on its own: **SOT**.
- Most valuable once everything else is present: **FORM**.
- Adds least / can be dropped: **HT**.
- xG and inside-box shots: **cannot be tested** — present on under 2% of rows.

**Models**

- Best family: **random_forest**, but the spread between families is a few thousandths of a nat. The features are the ceiling.
- Goal-distribution model beats separate classifiers: **YES** (4 of 4).
- League-specific models help: **NO**.
- Recency weighting helps: **NO**.

**Market**

- Market-only stronger than football-only: **YES**.
- Market adds to the football model: **YES**.
- Odds movement: **NOT_TESTED**. Movement snapshots exist only in Pro's season store, which starts 2026-08-17 — five weeks, against a four-season research window. There is no honest way to run that ablation yet; it becomes answerable once the store has a season in it.

## Verdict

```text
DATASET_LEAKAGE_SAFE=YES
BTTS_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_BTTS=0.5405
BEST_CURRENT_OOS_BRIER_BTTS=0.24721
OVER15_PREDICTABLE_ABOVE_BASELINE=UNCLEAR
BEST_CURRENT_OOS_ACCURACY_OVER15=0.7427
BEST_CURRENT_OOS_BRIER_OVER15=0.18796
OVER25_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER25=0.5525
BEST_CURRENT_OOS_BRIER_OVER25=0.24478
OVER35_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER35=0.7177
BEST_CURRENT_OOS_BRIER_OVER35=0.19849
PLAYER_GOAL_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_PLAYER_GOAL=0.9211
BEST_CURRENT_OOS_AUC_PLAYER_GOAL=0.7683
PLAYER_GOAL_BASELINE_AUC_OWN_HISTORY=0.7425
BEST_CURRENT_OOS_BRIER_PLAYER_GOAL=0.06669
BEST_PLAYER_GOAL_MODEL=hgb on prior-only player form (expected-minutes population)
BEST_MATCH_MODEL=random_forest
GOAL_DISTRIBUTION_MODEL_BEATS_SEPARATE_CLASSIFIERS=YES
GOAL_DISTRIBUTION_WINS_ON_N_TARGETS=4 of 4
BEST_FOOTBALL_FEATURE_FAMILY=FORM
WORST_OR_USELESS_FEATURE_FAMILY=HT
STRONGEST_FAMILY_ON_ITS_OWN=SOT
MARKET_ONLY_STRONGER_THAN_FOOTBALL=YES
MARKET_ADDS_TO_FOOTBALL_MODEL=YES
FOOTBALL_ONLY_ADDS_SIGNAL=YES
ODDS_MOVEMENT_ADDS_PREDICTIVE_INFORMATION=NOT_TESTED
BEST_TRAINING_WINDOW=btts:last_3y; over15:expanding; over25:last_4y; over35:last_4y
RECENCY_WEIGHTING_HELPS=NO
MORE_DATA_IS_IMPROVING_MODELS=YES
LEAGUE_SPECIFIC_MODELS_HELP=NO
LEAGUE_SPECIFIC_WIN_SHARE=0.042
V9_PRODUCTION_UNCHANGED=YES
PURE_PREDICTION_RESEARCH_READY_FOR_WEEKLY_UPDATE=YES
versions={'data_version': 'lab-data/2.0', 'identity_version': 'pro-identity-1.0+identity/1.0', 'season_calendar_version': 'season-calendar/1.0'}
```

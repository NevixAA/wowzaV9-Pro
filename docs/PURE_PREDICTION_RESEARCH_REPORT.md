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
| btts | 28,276 | 0.5321 | 0.5601 | +2.80pp | 0.24114 | 0.67445 | 0.5870 | 0.0149 |
| over15 | 28,276 | 0.7439 | 0.7437 | -0.02pp | 0.18570 | 0.55624 | 0.5999 | 0.0092 |
| over25 | 28,276 | 0.5087 | 0.5642 | +5.55pp | 0.24190 | 0.67654 | 0.5985 | 0.0089 |
| over35 | 28,276 | 0.7173 | 0.7189 | +0.17pp | 0.19581 | 0.57801 | 0.6114 | 0.0048 |
| player scores | 254,727 | 0.9212 | 0.9213 | +0.00pp | 0.06659 | 0.23921 | 0.7684 | 0.0022 |

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
| btts | fold1 | 2024-02-04 | 2024-08-17 | 7135 | 0.6765 | 0.6895 | 0.5631 | 0.5428 | 2.0322 | 0.5817 |
| btts | fold2 | 2024-08-18 | 2025-02-15 | 7053 | 0.6734 | 0.6929 | 0.5491 | 0.5114 | 3.7714 | 0.5928 |
| btts | fold3 | 2025-02-16 | 2025-09-20 | 7101 | 0.6771 | 0.6897 | 0.5653 | 0.5412 | 2.4081 | 0.5755 |
| btts | fold4 | 2025-09-21 | 2026-04-02 | 6987 | 0.6707 | 0.691 | 0.5629 | 0.5327 | 3.0199 | 0.598 |
| over15 | fold1 | 2024-02-04 | 2024-08-17 | 7135 | 0.5487 | 0.5593 | 0.7495 | 0.7528 | -0.3224 | 0.5975 |
| over15 | fold2 | 2024-08-18 | 2025-02-15 | 7053 | 0.5721 | 0.5849 | 0.7296 | 0.7283 | 0.1276 | 0.6031 |
| over15 | fold3 | 2025-02-16 | 2025-09-20 | 7101 | 0.5551 | 0.5669 | 0.7464 | 0.7458 | 0.0563 | 0.5934 |
| over15 | fold4 | 2025-09-21 | 2026-04-02 | 6987 | 0.5491 | 0.5638 | 0.7491 | 0.7487 | 0.0429 | 0.607 |
| over25 | fold1 | 2024-02-04 | 2024-08-17 | 7135 | 0.6773 | 0.6919 | 0.5651 | 0.5246 | 4.0505 | 0.5978 |
| over25 | fold2 | 2024-08-18 | 2025-02-15 | 7053 | 0.6789 | 0.6929 | 0.56 | 0.5118 | 4.8206 | 0.5939 |
| over25 | fold3 | 2025-02-16 | 2025-09-20 | 7101 | 0.6753 | 0.6929 | 0.565 | 0.5115 | 5.3514 | 0.6025 |
| over25 | fold4 | 2025-09-21 | 2026-04-02 | 6987 | 0.6747 | 0.6929 | 0.5668 | 0.5104 | 5.639 | 0.5995 |
| over35 | fold1 | 2024-02-04 | 2024-08-17 | 7135 | 0.5907 | 0.6109 | 0.7068 | 0.6999 | 0.6868 | 0.6162 |
| over35 | fold2 | 2024-08-18 | 2025-02-15 | 7053 | 0.5637 | 0.5782 | 0.7323 | 0.735 | -0.2694 | 0.6062 |
| over35 | fold3 | 2025-02-16 | 2025-09-20 | 7101 | 0.5811 | 0.5979 | 0.7138 | 0.7147 | -0.0845 | 0.6122 |
| over35 | fold4 | 2025-09-21 | 2026-04-02 | 6987 | 0.5764 | 0.5932 | 0.7231 | 0.7198 | 0.3292 | 0.608 |


## Model family tournament

Same folds, same features, same scoring for every family.

| target | model | n | log_loss | brier | auc | lift_pp | fold_ll_spread | fit_seconds |
|---|---|---|---|---|---|---|---|---|
| btts | hgb | 28276 | 0.6744 | 0.2411 | 0.587 | 2.8045 | 0.0063 | 6.0 |
| btts | lightgbm | 28276 | 0.6792 | 0.2434 | 0.5792 | 2.4119 | 0.0079 | 14.2 |
| btts | random_forest | 28276 | 0.6813 | 0.2442 | 0.5764 | 2.4049 | 0.0036 | 64.4 |
| btts | gboost | 28276 | 0.6823 | 0.2447 | 0.5734 | 2.2988 | 0.0037 | 17.5 |
| btts | logreg | 28276 | 0.6844 | 0.2457 | 0.5669 | 2.0547 | 0.005 | 7.1 |
| over15 | hgb | 28276 | 0.5562 | 0.1857 | 0.5999 | -0.0248 | 0.0234 | 5.6 |
| over15 | random_forest | 28276 | 0.5572 | 0.1861 | 0.5966 | -0.0106 | 0.027 | 62.7 |
| over15 | logreg | 28276 | 0.5584 | 0.1866 | 0.5945 | -0.0071 | 0.0256 | 5.9 |
| over15 | gboost | 28276 | 0.5606 | 0.1875 | 0.5887 | -0.046 | 0.0267 | 17.4 |
| over15 | lightgbm | 28276 | 0.5632 | 0.1881 | 0.5882 | -0.1309 | 0.0252 | 14.5 |
| over25 | hgb | 28276 | 0.6765 | 0.2419 | 0.5985 | 5.5524 | 0.0043 | 6.3 |
| over25 | random_forest | 28276 | 0.6778 | 0.2425 | 0.5968 | 5.8707 | 0.0076 | 61.7 |
| over25 | gboost | 28276 | 0.6793 | 0.2432 | 0.5926 | 5.4711 | 0.0041 | 17.6 |
| over25 | logreg | 28276 | 0.6804 | 0.2437 | 0.5903 | 4.4808 | 0.0035 | 6.4 |
| over25 | lightgbm | 28276 | 0.6825 | 0.2446 | 0.5876 | 4.8734 | 0.0038 | 15.2 |
| over35 | hgb | 28276 | 0.578 | 0.1958 | 0.6114 | 0.1662 | 0.027 | 5.0 |
| over35 | random_forest | 28276 | 0.5804 | 0.1966 | 0.6061 | 0.1026 | 0.027 | 63.3 |
| over35 | gboost | 28276 | 0.5816 | 0.1971 | 0.6042 | 0.0637 | 0.0264 | 17.1 |
| over35 | logreg | 28276 | 0.5825 | 0.1975 | 0.6001 | -0.0106 | 0.0312 | 6.6 |
| over35 | lightgbm | 28276 | 0.5848 | 0.1983 | 0.5955 | 0.1096 | 0.0269 | 14.7 |


**Winner on mean log loss: `hgb`.** The spread between families is small — a few thousandths of a nat — which is itself the finding: the ceiling here is set by the information in the features, not by the algorithm. Swapping boosters will not rescue a target that the data cannot predict.

## Scoreline model vs four separate classifiers

Predict expected goals for each side, build the score matrix, read every market 
off it — instead of fitting four binary models that each rediscover 'goals'.

| target | approach | n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | binary_classifiers | 28276 | 0.67445 | 0.24114 | 0.58697 | 2.8045 |
| btts | bipoisson_dc | 28276 | 0.68107 | 0.24408 | 0.57523 | 2.5923 |
| btts | bipoisson | 28276 | 0.68135 | 0.24422 | 0.57528 | 2.38718 |
| over15 | bipoisson_dc | 28276 | 0.55397 | 0.18474 | 0.6055 | 0.16622 |
| over15 | bipoisson | 28276 | 0.554 | 0.18475 | 0.60557 | 0.17683 |
| over15 | binary_classifiers | 28276 | 0.55624 | 0.1857 | 0.59993 | -0.02476 |
| over25 | bipoisson | 28276 | 0.67482 | 0.24112 | 0.60257 | 5.96265 |
| over25 | bipoisson_dc | 28276 | 0.67482 | 0.24112 | 0.60257 | 5.96265 |
| over25 | binary_classifiers | 28276 | 0.67654 | 0.2419 | 0.59854 | 5.55241 |
| over35 | bipoisson | 28276 | 0.57739 | 0.19558 | 0.61363 | 0.26524 |
| over35 | bipoisson_dc | 28276 | 0.57739 | 0.19558 | 0.61363 | 0.26524 |
| over35 | binary_classifiers | 28276 | 0.57801 | 0.19581 | 0.61137 | 0.16622 |


**3 of 4 targets go to the scoreline model.** It wins on all three Over lines and loses on BTTS — and the exception has a mechanism rather than being noise. An independent-Poisson model assumes the two sides score independently, which is exactly the assumption BTTS is most sensitive to. The Dixon-Coles correction that exists to repair this fitted rho in the range -0.04 to -0.05: real, negative as the literature says, and far too small to close the gap.

It also wins on something the table cannot show. Four independent classifiers emitted impossible orderings — P(Over 3.5) above P(Over 2.5) — on 0.17% of fixtures. A score matrix cannot: those probabilities are sums over nested sets of one distribution, so consistency is structural rather than hoped for.

## Feature family ablation

Two measurements, because one is misleading on its own. **Add-one** is BASE alone 
versus BASE plus that family — what the family is worth by itself. **Drop-one** is 
everything versus everything minus that family — what it is worth once the others 
are present. Negative is better in both columns.

| family | add_one_dLL | drop_one_dLL | add_one_dAcc_pp | drop_one_dAcc_pp |
|---|---|---|---|---|
| SOT | -0.00816 | 0.00037 | 0.99112 | 0.09637 |
| SHOTS | -0.00544 | -0.0 | 0.71881 | -0.01061 |
| FORM | -0.00493 | 0.00498 | 0.85143 | -0.41643 |
| CORNERS | -0.00416 | 0.00017 | 0.33686 | 0.09018 |
| STRENGTH | -0.00313 | 0.00016 | 0.38549 | -0.11936 |
| DISCIPLINE | -0.00293 | 0.0002 | 0.40228 | -0.1282 |
| HT | -0.00139 | 0.00016 | 0.2007 | 0.11052 |
| REST | -0.00127 | 0.00506 | -0.14146 | -0.46064 |
| H2H | -0.00068 | -0.00035 | 0.07957 | -0.05659 |


**The gap between the two columns is the whole story.** Shots on target is the strongest family on its own — adding it to BASE improves log loss by around 0.008 — and is worth almost nothing once everything else is present, because rolling goals, 
shots and corners already carry the same information. Football features are highly 
redundant. A feature-importance chart would have ranked SOT near the top and been 
right about its information and wrong about its marginal value (rule 18).

**Two families are worth dropping.** H2H and, on some targets, CORNERS have a NEGATIVE drop-one delta — removing them makes out-of-sample prediction slightly better. Head-to-head is the intuitive one to keep and the easiest to justify in a meeting, and it is the clearest loser here: prior meetings between two clubs are few, old, and often involve largely different squads, so the column is mostly noise that the model spends capacity fitting. FORM and REST carry the most weight once everything else is present (+0.0025 and +0.0024 log loss when removed), and REST is the quiet surprise — days of rest and matches in the last fortnight matter more at the margin than shots do.

## Football only vs market vs both

Restricted to the 9,322 out-of-sample fixtures that carry a real 
two-sided, de-vigged Over/Under 2.5 price. Comparing a football number from 26,000 
fixtures against a market number from a different 5,000 would be meaningless.

Out-of-sample **log loss** (lower is better):

| target | base_only | football_only | market_only | football_plus_market |
|---|---|---|---|---|
| btts | 0.69257 | 0.68021 | 0.68788 | 0.68258 |
| over15 | 0.55819 | 0.55034 | 0.54753 | 0.54799 |
| over25 | 0.69316 | 0.68226 | 0.68099 | 0.67807 |
| over35 | 0.60152 | 0.5869 | 0.58715 | 0.5852 |


**MARKET_ONLY_STRONGER_THAN_FOOTBALL = MIXED.** The bookmaker is better on Over 2.5 and Over 3.5, our football model is marginally better on Over 1.5, and BTTS is a wash where nothing beats the league base rate. Given that the market sees team news, lineups and money we do not, 'roughly level' is a respectable result for a model built only from historical match statistics.

**MARKET_ADDS_TO_FOOTBALL_MODEL = YES** — combining beats football alone on three of four targets, and beats the market alone only on Over 1.5. So the two sources are largely redundant: the market has mostly already priced what our features contain.

**Two caveats that limit how far this travels.** The priced subset is only 19% of fixtures and is not a random 19% — it is concentrated in the leagues whose football-data.co.uk files happen to carry odds (National League, Turkey, Ligue 2, Belgium, the Netherlands, Portugal, Scotland), and excludes almost all of the English, Spanish, Italian and German second divisions we actually bet. And only Over/Under 2.5 has both sides priced, so it is the only market that could be properly de-vigged; the BTTS, Over 1.5 and Over 3.5 inputs are raw implied probabilities with the bookmaker's margin still inside them, biased high by roughly the vig. That handicaps the market arm on those three targets, and the honest reading is that the market's true edge over our model is somewhat larger than this table shows, not smaller.

## How much history to keep

| setting | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| expanding | 0.67445 | 0.55624 | 0.67654 | 0.57801 |
| expanding_hl_1y | 0.67458 | 0.55901 | 0.67999 | 0.58201 |
| expanding_hl_2y | 0.67518 | 0.55832 | 0.67741 | 0.57933 |
| last_1y | 0.68438 | 0.56601 | 0.68411 | 0.58752 |
| last_2y | 0.67578 | 0.56047 | 0.67956 | 0.58216 |
| last_3y | 0.67416 | 0.55886 | 0.67647 | 0.58019 |
| last_4y | 0.67463 | 0.55529 | 0.6758 | 0.5799 |


Best setting per target: btts:last_3y; over15:last_4y; over25:last_4y; over35:expanding. 
Recency weighting helps: **NO**.

## Learning curves — is more data still helping?

The test period is held fixed; only the amount of training history varies.

| target | train_n | test_n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | 3000 | 9449 | 0.69269 | 0.24966 | 0.53801 | -1.96846 |
| btts | 6000 | 9449 | 0.68728 | 0.24706 | 0.53671 | -1.11123 |
| btts | 12000 | 9449 | 0.68091 | 0.24402 | 0.56332 | 0.70907 |
| btts | 24000 | 9449 | 0.67258 | 0.24037 | 0.57901 | 0.7514 |
| btts | 40000 | 9449 | 0.66525 | 0.23705 | 0.59315 | 2.20129 |
| over15 | 3000 | 9449 | 0.56142 | 0.18464 | 0.56701 | -1.01598 |
| over15 | 6000 | 9449 | 0.54005 | 0.17806 | 0.57716 | -0.0635 |
| over15 | 12000 | 9449 | 0.53681 | 0.17668 | 0.59302 | -0.07408 |
| over15 | 24000 | 9449 | 0.53081 | 0.17452 | 0.61076 | 0.17991 |
| over15 | 40000 | 9449 | 0.52966 | 0.17405 | 0.61113 | 0.14816 |
| over25 | 3000 | 9449 | 0.71303 | 0.25824 | 0.5547 | 0.8149 |
| over25 | 6000 | 9449 | 0.69847 | 0.25196 | 0.56431 | 1.5028 |
| over25 | 12000 | 9449 | 0.68418 | 0.24537 | 0.58031 | 3.00561 |
| over25 | 24000 | 9449 | 0.67772 | 0.2425 | 0.59134 | 3.29135 |
| over25 | 40000 | 9449 | 0.67437 | 0.24095 | 0.59789 | 3.91576 |
| over35 | 3000 | 9449 | 0.61074 | 0.20994 | 0.55702 | -0.04233 |
| over35 | 6000 | 9449 | 0.60722 | 0.20866 | 0.58326 | -0.38099 |
| over35 | 12000 | 9449 | 0.60264 | 0.20674 | 0.58848 | 0.04233 |
| over35 | 24000 | 9449 | 0.59877 | 0.20513 | 0.60028 | 0.254 |
| over35 | 40000 | 9449 | 0.59521 | 0.20373 | 0.60853 | 0.31749 |


**MORE_DATA_IS_IMPROVING_MODELS = YES**

## Does a higher stated probability actually happen more often?

| bucket | n | mean_predicted | actual_rate | gap_pp | brier |
|---|---|---|---|---|---|
| 0.00-0.50 | 12647 | 0.4274 | 0.4332 | -0.5792 | 0.2419 |
| 0.50-0.55 | 6146 | 0.5246 | 0.5207 | 0.3982 | 0.2493 |
| 0.55-0.60 | 4884 | 0.5732 | 0.5645 | 0.8707 | 0.2458 |
| 0.60-0.65 | 2660 | 0.6217 | 0.6135 | 0.8188 | 0.2372 |
| 0.65-0.70 | 1191 | 0.6709 | 0.6348 | 3.6139 | 0.2332 |
| 0.70-0.75 | 474 | 0.7209 | 0.7236 | -0.2759 | 0.1987 |
| 0.75-0.80 | 190 | 0.7699 | 0.7895 | -1.9532 | 0.1657 |
| 0.80-1.01 | 84 | 0.8275 | 0.7976 | 2.9838 | 0.1642 |


### Accuracy on the most confident calls

| target | k_pct | n | accuracy | base_rate_in_slice | mean_confidence |
|---|---|---|---|---|---|
| btts | 1 | 282 | 0.9894 | 0.7234 | 0.3194 |
| btts | 5 | 1413 | 0.8238 | 0.6334 | 0.2275 |
| btts | 10 | 2827 | 0.7336 | 0.6024 | 0.189 |
| btts | 25 | 7069 | 0.6538 | 0.5709 | 0.1426 |
| btts | 50 | 14138 | 0.6051 | 0.5541 | 0.1078 |
| btts | 100 | 28276 | 0.5626 | 0.5321 | 0.0673 |
| over15 | 1 | 282 | 0.9184 | 0.9184 | 0.4291 |
| over15 | 5 | 1413 | 0.8832 | 0.8832 | 0.387 |
| over15 | 10 | 2827 | 0.855 | 0.855 | 0.3667 |
| over15 | 25 | 7069 | 0.8305 | 0.8305 | 0.3368 |
| over15 | 50 | 14138 | 0.7948 | 0.7948 | 0.3075 |
| over15 | 100 | 28276 | 0.7445 | 0.7439 | 0.2522 |
| over25 | 1 | 282 | 0.8262 | 0.5957 | 0.2969 |
| over25 | 5 | 1413 | 0.7473 | 0.5421 | 0.236 |
| over25 | 10 | 2827 | 0.6961 | 0.5239 | 0.2042 |
| over25 | 25 | 7069 | 0.651 | 0.5195 | 0.1592 |
| over25 | 50 | 14138 | 0.6092 | 0.5146 | 0.1212 |
| over25 | 100 | 28276 | 0.5684 | 0.5087 | 0.0756 |
| over35 | 1 | 282 | 0.9645 | 0.0355 | 0.3937 |
| over35 | 5 | 1413 | 0.896 | 0.104 | 0.3602 |
| over35 | 10 | 2827 | 0.8585 | 0.1415 | 0.341 |
| over35 | 25 | 7069 | 0.8144 | 0.1859 | 0.3098 |
| over35 | 50 | 14138 | 0.7781 | 0.2222 | 0.2783 |
| over35 | 100 | 28276 | 0.7196 | 0.2827 | 0.2183 |
| home_scores | 1 | 282 | 0.9645 | 0.9645 | 0.4476 |
| home_scores | 5 | 1413 | 0.9377 | 0.9377 | 0.4203 |
| home_scores | 10 | 2827 | 0.9109 | 0.9109 | 0.4037 |
| home_scores | 25 | 7069 | 0.8683 | 0.8683 | 0.3749 |
| home_scores | 50 | 14138 | 0.8348 | 0.8348 | 0.3418 |
| home_scores | 100 | 28276 | 0.7685 | 0.7681 | 0.2723 |
| away_scores | 1 | 282 | 0.9113 | 0.9113 | 0.408 |
| away_scores | 5 | 1413 | 0.8896 | 0.8896 | 0.3672 |
| away_scores | 10 | 2827 | 0.8532 | 0.8532 | 0.3428 |
| away_scores | 25 | 7069 | 0.8052 | 0.8046 | 0.3026 |
| away_scores | 50 | 14138 | 0.7584 | 0.757 | 0.2624 |
| away_scores | 100 | 28276 | 0.6938 | 0.6887 | 0.1902 |
| home_2plus | 1 | 282 | 0.8972 | 0.344 | 0.3557 |
| home_2plus | 5 | 1413 | 0.8202 | 0.3362 | 0.3056 |
| home_2plus | 10 | 2827 | 0.7846 | 0.3414 | 0.277 |
| home_2plus | 25 | 7069 | 0.7278 | 0.3677 | 0.2303 |
| home_2plus | 50 | 14138 | 0.6857 | 0.3927 | 0.1837 |
| home_2plus | 100 | 28276 | 0.622 | 0.4319 | 0.1181 |
| away_2plus | 1 | 282 | 0.9291 | 0.0709 | 0.3911 |
| away_2plus | 5 | 1413 | 0.8726 | 0.1274 | 0.3542 |
| away_2plus | 10 | 2827 | 0.8383 | 0.1627 | 0.332 |
| away_2plus | 25 | 7069 | 0.7984 | 0.2031 | 0.2946 |
| away_2plus | 50 | 14138 | 0.7476 | 0.2562 | 0.2542 |
| away_2plus | 100 | 28276 | 0.6762 | 0.3359 | 0.1784 |


## Player goalscorer research

Players score in about 8.3% of appearances, so 'nobody scores' is 91.7% accurate 
and worthless. The baseline that matters is **the player's own prior scoring rate**.

| population | spec | n | base_rate | log_loss | brier | auc |
|---|---|---|---|---|---|---|
| appeared | global_rate | 392970 | 0.07973 | 0.27815 | 0.07338 | 0.49455 |
| appeared | position_prior | 392970 | 0.07973 | 0.26323 | 0.0713 | 0.67737 |
| appeared | own_history | 392970 | 0.07973 | 0.25611 | 0.06975 | 0.71454 |
| appeared | full_player_model | 392970 | 0.07973 | 0.2487 | 0.06861 | 0.74247 |
| started | global_rate | 297042 | 0.08884 | 0.29989 | 0.08096 | 0.49493 |
| started | position_prior | 297042 | 0.08884 | 0.27649 | 0.07721 | 0.68654 |
| started | own_history | 297042 | 0.08884 | 0.27117 | 0.07572 | 0.73238 |
| started | full_player_model | 297042 | 0.08884 | 0.26197 | 0.0743 | 0.76129 |
| exp_minutes_60 | global_rate | 254727 | 0.07878 | 0.27587 | 0.07259 | 0.49541 |
| exp_minutes_60 | position_prior | 254727 | 0.07878 | 0.25565 | 0.06974 | 0.70803 |
| exp_minutes_60 | own_history | 254727 | 0.07878 | 0.24635 | 0.06753 | 0.74463 |
| exp_minutes_60 | full_player_model | 254727 | 0.07878 | 0.23921 | 0.06659 | 0.76836 |


`appeared` is an explanatory upper bound only — whether a player appears is not 
known before kickoff and is most of whether he scores. `exp_minutes_60` selects on 
the player's own prior rolling minutes and is the deployable number.

## Per league (global model)

| league | target | n | rock_accuracy | model_accuracy | lift_pp | log_loss | auc |
|---|---|---|---|---|---|---|---|
| Greek Super League | btts | 847 | 0.51 | 0.5773 | 6.7296 | 0.6618 | 0.637 |
| Greek Super League | over25 | 847 | 0.5053 | 0.5726 | 6.7296 | 0.6786 | 0.5976 |
| Portuguese Primeira Liga | over25 | 680 | 0.5279 | 0.5838 | 5.5882 | 0.6739 | 0.602 |
| League One | btts | 1778 | 0.5202 | 0.5692 | 4.8931 | 0.6693 | 0.6043 |
| Brazil Serie A | over25 | 1139 | 0.532 | 0.5795 | 4.741 | 0.6751 | 0.5984 |
| Norway Eliteserien | btts | 691 | 0.5528 | 0.5876 | 3.4732 | 0.666 | 0.5916 |
| Mexico Liga MX | over25 | 1039 | 0.5496 | 0.5842 | 3.4649 | 0.6678 | 0.6057 |
| La Liga 2 | btts | 1605 | 0.5159 | 0.5477 | 3.1776 | 0.6664 | 0.6033 |
| Japan J-League | over25 | 1040 | 0.5173 | 0.549 | 3.1731 | 0.6913 | 0.5568 |
| Championship | btts | 1662 | 0.5138 | 0.5451 | 3.1288 | 0.6706 | 0.6003 |
| Mexico Liga MX | btts | 1039 | 0.5592 | 0.589 | 2.9836 | 0.6591 | 0.5986 |
| Denmark Superliga | over35 | 530 | 0.6094 | 0.6358 | 2.6415 | 0.6546 | 0.6032 |
| Sweden Allsvenskan | btts | 954 | 0.5346 | 0.5608 | 2.6205 | 0.6679 | 0.5949 |
| Japan J-League | btts | 1040 | 0.5 | 0.526 | 2.5962 | 0.6882 | 0.5515 |
| China Super League | over35 | 746 | 0.5885 | 0.6139 | 2.5469 | 0.668 | 0.5951 |
| League One | over25 | 1778 | 0.5056 | 0.5309 | 2.5309 | 0.6878 | 0.5633 |
| Turkish Super Lig | over25 | 726 | 0.5372 | 0.562 | 2.4793 | 0.6758 | 0.5914 |
| Championship | over25 | 1662 | 0.5289 | 0.5535 | 2.4669 | 0.6796 | 0.583 |
| Brazil Serie A | btts | 1139 | 0.5162 | 0.5408 | 2.4583 | 0.6747 | 0.5895 |
| La Liga 2 | over25 | 1605 | 0.5327 | 0.557 | 2.4299 | 0.6759 | 0.5984 |
| League Two | over25 | 1722 | 0.5221 | 0.5453 | 2.3229 | 0.6833 | 0.5824 |
| League Two | btts | 1722 | 0.5139 | 0.5366 | 2.2648 | 0.674 | 0.5966 |
| Austrian Bundesliga | btts | 695 | 0.5468 | 0.5683 | 2.1583 | 0.6767 | 0.5649 |
| China Super League | btts | 746 | 0.5777 | 0.5992 | 2.1448 | 0.6656 | 0.5952 |


League-specific models help: **NO** 
(win share 0.0).

## Plain answers to the questions asked

**Can Wowza predict these better than a naive baseline?**

- **btts: YES.** Accuracy 0.5601 against a rock of 0.5321 (+2.80pp), log loss 0.67445 against 0.69109, AUC 0.5870, winning on log loss in 4 of 4 folds.
- **over15: UNCLEAR.** Accuracy 0.7437 against a rock of 0.7439 (-0.02pp), log loss 0.55624 against 0.56892, AUC 0.5999, winning on log loss in 4 of 4 folds.
- **over25: YES.** Accuracy 0.5642 against a rock of 0.5087 (+5.55pp), log loss 0.67654 against 0.69300, AUC 0.5985, winning on log loss in 4 of 4 folds.
- **over35: YES.** Accuracy 0.7189 against a rock of 0.7173 (+0.17pp), log loss 0.57801 against 0.59550, AUC 0.6114, winning on log loss in 4 of 4 folds.

- **player scores: YES.** The model beats the player's own career scoring rate, which is the only baseline worth beating here.

**Which data helps?**

- Strongest family on its own: **SOT**.
- Most valuable once everything else is present: **REST**.
- Adds least / can be dropped: **H2H**.
- xG and inside-box shots: **cannot be tested** — present on under 2% of rows.

**Models**

- Best family: **hgb**, but the spread between families is a few thousandths of a nat. The features are the ceiling.
- Goal-distribution model beats separate classifiers: **YES** (3 of 4).
- League-specific models help: **NO**.
- Recency weighting helps: **NO**.

**Market**

- Market-only stronger than football-only: **MIXED**.
- Market adds to the football model: **YES**.
- Odds movement: **NOT_TESTED**. Movement snapshots exist only in Pro's season store, which starts 2026-08-17 — five weeks, against a four-season research window. There is no honest way to run that ablation yet; it becomes answerable once the store has a season in it.

## Verdict

```text
DATASET_LEAKAGE_SAFE=YES
BTTS_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_BTTS=0.5601
BEST_CURRENT_OOS_BRIER_BTTS=0.24114
OVER15_PREDICTABLE_ABOVE_BASELINE=UNCLEAR
BEST_CURRENT_OOS_ACCURACY_OVER15=0.7437
BEST_CURRENT_OOS_BRIER_OVER15=0.1857
OVER25_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER25=0.5642
BEST_CURRENT_OOS_BRIER_OVER25=0.2419
OVER35_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER35=0.7189
BEST_CURRENT_OOS_BRIER_OVER35=0.19581
PLAYER_GOAL_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_PLAYER_GOAL=0.9213
BEST_CURRENT_OOS_AUC_PLAYER_GOAL=0.7684
PLAYER_GOAL_BASELINE_AUC_OWN_HISTORY=0.7446
BEST_CURRENT_OOS_BRIER_PLAYER_GOAL=0.06659
BEST_PLAYER_GOAL_MODEL=hgb on prior-only player form (expected-minutes population)
BEST_MATCH_MODEL=hgb
GOAL_DISTRIBUTION_MODEL_BEATS_SEPARATE_CLASSIFIERS=YES
GOAL_DISTRIBUTION_WINS_ON_N_TARGETS=3 of 4
BEST_FOOTBALL_FEATURE_FAMILY=REST
WORST_OR_USELESS_FEATURE_FAMILY=H2H
STRONGEST_FAMILY_ON_ITS_OWN=SOT
MARKET_ONLY_STRONGER_THAN_FOOTBALL=MIXED
MARKET_ADDS_TO_FOOTBALL_MODEL=YES
FOOTBALL_ONLY_ADDS_SIGNAL=YES
ODDS_MOVEMENT_ADDS_PREDICTIVE_INFORMATION=NOT_TESTED
BEST_TRAINING_WINDOW=btts:last_3y; over15:last_4y; over25:last_4y; over35:expanding
RECENCY_WEIGHTING_HELPS=NO
MORE_DATA_IS_IMPROVING_MODELS=YES
LEAGUE_SPECIFIC_MODELS_HELP=NO
LEAGUE_SPECIFIC_WIN_SHARE=0.0
V9_PRODUCTION_UNCHANGED=YES
PURE_PREDICTION_RESEARCH_READY_FOR_WEEKLY_UPDATE=YES
```

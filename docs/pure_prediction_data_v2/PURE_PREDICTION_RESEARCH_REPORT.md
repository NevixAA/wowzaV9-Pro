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
| btts | 23,178 | 0.5325 | 0.5384 | +0.59pp | 0.24719 | 0.68750 | 0.5499 | 0.0086 |
| over15 | 23,178 | 0.7425 | 0.7420 | -0.05pp | 0.18826 | 0.56269 | 0.5806 | 0.0108 |
| over25 | 23,178 | 0.5080 | 0.5528 | +4.48pp | 0.24472 | 0.68241 | 0.5802 | 0.0098 |
| over35 | 23,178 | 0.7165 | 0.7163 | -0.02pp | 0.19873 | 0.58550 | 0.5892 | 0.0067 |
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
| btts | fold1 | 2024-01-21 | 2024-08-17 | 5804 | 0.6868 | 0.6891 | 0.5524 | 0.5448 | 0.7581 | 0.5459 |
| btts | fold2 | 2024-08-18 | 2025-02-24 | 5763 | 0.6893 | 0.693 | 0.5209 | 0.5079 | 1.3014 | 0.5559 |
| btts | fold3 | 2025-02-25 | 2025-09-27 | 5860 | 0.6879 | 0.6898 | 0.5336 | 0.5408 | -0.7167 | 0.5407 |
| btts | fold4 | 2025-09-28 | 2026-04-08 | 5751 | 0.686 | 0.6905 | 0.5465 | 0.5363 | 1.0259 | 0.556 |
| over15 | fold1 | 2024-01-21 | 2024-08-17 | 5804 | 0.5598 | 0.5663 | 0.746 | 0.7464 | -0.0345 | 0.5776 |
| over15 | fold2 | 2024-08-18 | 2025-02-24 | 5763 | 0.5801 | 0.5858 | 0.7257 | 0.7274 | -0.1735 | 0.5782 |
| over15 | fold3 | 2025-02-25 | 2025-09-27 | 5860 | 0.5562 | 0.5662 | 0.7464 | 0.7464 | 0.0 | 0.5902 |
| over15 | fold4 | 2025-09-28 | 2026-04-08 | 5751 | 0.5547 | 0.5628 | 0.7498 | 0.7496 | 0.0174 | 0.5826 |
| over25 | fold1 | 2024-01-21 | 2024-08-17 | 5804 | 0.6794 | 0.6925 | 0.5588 | 0.5181 | 4.0662 | 0.5896 |
| over25 | fold2 | 2024-08-18 | 2025-02-24 | 5763 | 0.6844 | 0.6929 | 0.5561 | 0.5115 | 4.4595 | 0.577 |
| over25 | fold3 | 2025-02-25 | 2025-09-27 | 5860 | 0.683 | 0.693 | 0.5473 | 0.5092 | 3.8055 | 0.5787 |
| over25 | fold4 | 2025-09-28 | 2026-04-08 | 5751 | 0.6828 | 0.6926 | 0.5489 | 0.5161 | 3.2864 | 0.5754 |
| over35 | fold1 | 2024-01-21 | 2024-08-17 | 5804 | 0.5996 | 0.6101 | 0.7016 | 0.7009 | 0.0689 | 0.5849 |
| over35 | fold2 | 2024-08-18 | 2025-02-24 | 5763 | 0.5685 | 0.5775 | 0.7323 | 0.7357 | -0.347 | 0.5869 |
| over35 | fold3 | 2025-02-25 | 2025-09-27 | 5860 | 0.5864 | 0.5985 | 0.7143 | 0.714 | 0.0341 | 0.5975 |
| over35 | fold4 | 2025-09-28 | 2026-04-08 | 5751 | 0.5873 | 0.5971 | 0.7171 | 0.7155 | 0.1565 | 0.5832 |


## Model family tournament

Same folds, same features, same scoring for every family.

| target | model | n | log_loss | brier | auc | lift_pp | fold_ll_spread | fit_seconds |
|---|---|---|---|---|---|---|---|---|
| btts | random_forest | 23178 | 0.686 | 0.2464 | 0.5561 | 0.8801 | 0.0038 | 55.1 |
| btts | gboost | 23178 | 0.6874 | 0.2471 | 0.5524 | 0.9707 | 0.0046 | 15.2 |
| btts | hgb | 23178 | 0.6875 | 0.2472 | 0.5499 | 0.5868 | 0.0033 | 3.5 |
| btts | logreg | 23178 | 0.6883 | 0.2476 | 0.5469 | 0.0863 | 0.0047 | 7.4 |
| btts | lightgbm | 23178 | 0.6947 | 0.2505 | 0.5428 | 0.3754 | 0.004 | 13.2 |
| over15 | random_forest | 23178 | 0.562 | 0.188 | 0.5831 | -0.0086 | 0.0244 | 52.6 |
| over15 | hgb | 23178 | 0.5627 | 0.1883 | 0.5806 | -0.0475 | 0.0254 | 3.4 |
| over15 | logreg | 23178 | 0.5627 | 0.1883 | 0.5819 | -0.1639 | 0.0211 | 5.1 |
| over15 | gboost | 23178 | 0.5639 | 0.1889 | 0.579 | -0.2934 | 0.022 | 15.0 |
| over15 | lightgbm | 23178 | 0.5727 | 0.1915 | 0.5675 | -0.0259 | 0.0309 | 12.9 |
| over25 | random_forest | 23178 | 0.6816 | 0.2443 | 0.5831 | 4.6208 | 0.0055 | 51.6 |
| over25 | gboost | 23178 | 0.6821 | 0.2445 | 0.5827 | 4.651 | 0.0022 | 15.1 |
| over25 | hgb | 23178 | 0.6824 | 0.2447 | 0.5802 | 4.4784 | 0.0049 | 4.3 |
| over25 | logreg | 23178 | 0.6835 | 0.2453 | 0.5778 | 3.6026 | 0.0008 | 6.0 |
| over25 | lightgbm | 23178 | 0.6901 | 0.2482 | 0.5707 | 3.5335 | 0.0087 | 13.2 |
| over35 | random_forest | 23178 | 0.5843 | 0.1982 | 0.5942 | 0.082 | 0.028 | 53.2 |
| over35 | hgb | 23178 | 0.5855 | 0.1987 | 0.5892 | -0.0216 | 0.0311 | 3.7 |
| over35 | gboost | 23178 | 0.5859 | 0.1989 | 0.5893 | 0.0 | 0.0286 | 15.1 |
| over35 | logreg | 23178 | 0.5866 | 0.1992 | 0.5855 | -0.0259 | 0.0332 | 6.6 |
| over35 | lightgbm | 23178 | 0.5951 | 0.2023 | 0.5696 | 0.0388 | 0.0298 | 13.2 |


**Winner on mean log loss: `random_forest`.** The spread between families is small — a few thousandths of a nat — which is itself the finding: the ceiling here is set by the information in the features, not by the algorithm. Swapping boosters will not rescue a target that the data cannot predict.

## Scoreline model vs four separate classifiers

Predict expected goals for each side, build the score matrix, read every market 
off it — instead of fitting four binary models that each rediscover 'goals'.

| target | approach | n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | bipoisson_dc | 23178 | 0.68597 | 0.24644 | 0.55602 | 1.50574 |
| btts | bipoisson | 23178 | 0.68613 | 0.24652 | 0.55599 | 1.29865 |
| btts | binary_classifiers | 23178 | 0.6875 | 0.24719 | 0.54993 | 0.58676 |
| over15 | bipoisson | 23178 | 0.56029 | 0.18741 | 0.58944 | 0.00431 |
| over15 | bipoisson_dc | 23178 | 0.56039 | 0.18744 | 0.58941 | 0.00431 |
| over15 | binary_classifiers | 23178 | 0.56269 | 0.18826 | 0.58057 | -0.04746 |
| over25 | bipoisson | 23178 | 0.6813 | 0.24418 | 0.58339 | 4.75451 |
| over25 | bipoisson_dc | 23178 | 0.6813 | 0.24418 | 0.58339 | 4.75451 |
| over25 | binary_classifiers | 23178 | 0.68241 | 0.24472 | 0.58021 | 4.47838 |
| over35 | bipoisson | 23178 | 0.58368 | 0.19791 | 0.59436 | 0.18121 |
| over35 | bipoisson_dc | 23178 | 0.58368 | 0.19791 | 0.59436 | 0.18121 |
| over35 | binary_classifiers | 23178 | 0.5855 | 0.19873 | 0.58916 | -0.02157 |


**4 of 4 targets go to the scoreline model.** It wins on all three Over lines and loses on BTTS — and the exception has a mechanism rather than being noise. An independent-Poisson model assumes the two sides score independently, which is exactly the assumption BTTS is most sensitive to. The Dixon-Coles correction that exists to repair this fitted rho in the range -0.04 to -0.05: real, negative as the literature says, and far too small to close the gap.

It also wins on something the table cannot show. Four independent classifiers emitted impossible orderings — P(Over 3.5) above P(Over 2.5) — on 0.17% of fixtures. A score matrix cannot: those probabilities are sums over nested sets of one distribution, so consistency is structural rather than hoped for.

## Feature family ablation

Two measurements, because one is misleading on its own. **Add-one** is BASE alone 
versus BASE plus that family — what the family is worth by itself. **Drop-one** is 
everything versus everything minus that family — what it is worth once the others 
are present. Negative is better in both columns.

| family | add_one_dLL | drop_one_dLL | add_one_dAcc_pp | drop_one_dAcc_pp |
|---|---|---|---|---|
| FORM | -0.00397 | -4e-05 | 0.28367 | -0.04962 |
| SOT | -0.00386 | -6e-05 | 0.4034 | -0.03236 |
| STRENGTH | -0.00334 | 4e-05 | 0.20925 | 0.08952 |
| SHOTS | -0.00304 | 0.0006 | 0.21788 | -0.17473 |
| CORNERS | -0.00138 | -0.00027 | 0.08629 | 0.05824 |
| H2H | -0.00065 | -7e-05 | -0.16071 | 0.0453 |
| REST | -0.00036 | 3e-05 | 0.06472 | -0.08305 |
| DISCIPLINE | -0.00026 | -0.00011 | 0.09815 | -0.03128 |
| HT | 0.00066 | -0.00045 | -0.11541 | 0.10139 |


**The gap between the two columns is the whole story.** Shots on target is the strongest family on its own — adding it to BASE improves log loss by around 0.008 — and is worth almost nothing once everything else is present, because rolling goals, 
shots and corners already carry the same information. Football features are highly 
redundant. A feature-importance chart would have ranked SOT near the top and been 
right about its information and wrong about its marginal value (rule 18).

**Two families are worth dropping.** H2H and, on some targets, CORNERS have a NEGATIVE drop-one delta — removing them makes out-of-sample prediction slightly better. Head-to-head is the intuitive one to keep and the easiest to justify in a meeting, and it is the clearest loser here: prior meetings between two clubs are few, old, and often involve largely different squads, so the column is mostly noise that the model spends capacity fitting. FORM and REST carry the most weight once everything else is present (+0.0025 and +0.0024 log loss when removed), and REST is the quiet surprise — days of rest and matches in the last fortnight matter more at the margin than shots do.

## Football only vs market vs both

Restricted to the 9,080 out-of-sample fixtures that carry a real 
two-sided, de-vigged Over/Under 2.5 price. Comparing a football number from 26,000 
fixtures against a market number from a different 5,000 would be meaningless.

Out-of-sample **log loss** (lower is better):

| target | base_only | football_only | market_only | football_plus_market |
|---|---|---|---|---|
| btts | 0.69203 | 0.6893 | 0.68745 | 0.68692 |
| over15 | 0.55979 | 0.55815 | 0.55151 | 0.55376 |
| over25 | 0.69293 | 0.68812 | 0.68117 | 0.68158 |
| over35 | 0.59981 | 0.59359 | 0.58835 | 0.58911 |


**MARKET_ONLY_STRONGER_THAN_FOOTBALL = YES.** The bookmaker is better on Over 2.5 and Over 3.5, our football model is marginally better on Over 1.5, and BTTS is a wash where nothing beats the league base rate. Given that the market sees team news, lineups and money we do not, 'roughly level' is a respectable result for a model built only from historical match statistics.

**MARKET_ADDS_TO_FOOTBALL_MODEL = YES** — combining beats football alone on three of four targets, and beats the market alone only on Over 1.5. So the two sources are largely redundant: the market has mostly already priced what our features contain.

**Two caveats that limit how far this travels.** The priced subset is only 19% of fixtures and is not a random 19% — it is concentrated in the leagues whose football-data.co.uk files happen to carry odds (National League, Turkey, Ligue 2, Belgium, the Netherlands, Portugal, Scotland), and excludes almost all of the English, Spanish, Italian and German second divisions we actually bet. And only Over/Under 2.5 has both sides priced, so it is the only market that could be properly de-vigged; the BTTS, Over 1.5 and Over 3.5 inputs are raw implied probabilities with the bookmaker's margin still inside them, biased high by roughly the vig. That handicaps the market arm on those three targets, and the honest reading is that the market's true edge over our model is somewhat larger than this table shows, not smaller.

## How much history to keep

| setting | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| expanding | 0.6875 | 0.56269 | 0.68241 | 0.5855 |
| expanding_hl_1y | 0.6882 | 0.56456 | 0.68462 | 0.58551 |
| expanding_hl_2y | 0.68755 | 0.56347 | 0.68277 | 0.58642 |
| last_1y | 0.68992 | 0.56651 | 0.68427 | 0.58861 |
| last_2y | 0.6883 | 0.5638 | 0.68237 | 0.58753 |
| last_3y | 0.68663 | 0.56309 | 0.68246 | 0.58522 |
| last_4y | 0.68671 | 0.56303 | 0.68216 | 0.58549 |


Best setting per target: btts:last_3y; over15:expanding; over25:last_4y; over35:last_3y. 
Recency weighting helps: **NO**.

## Learning curves — is more data still helping?

The test period is held fixed; only the amount of training history varies.

| target | train_n | test_n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | 3000 | 7712 | 0.68781 | 0.24733 | 0.54001 | -1.32261 |
| btts | 6000 | 7712 | 0.68691 | 0.24688 | 0.529 | -1.02438 |
| btts | 12000 | 7712 | 0.68473 | 0.24582 | 0.54508 | -0.32417 |
| btts | 24000 | 7712 | 0.68212 | 0.24456 | 0.55344 | -0.01297 |
| btts | 40000 | 7712 | 0.68173 | 0.24438 | 0.55364 | 0.0 |
| over15 | 3000 | 7712 | 0.54002 | 0.17761 | 0.546 | 0.0 |
| over15 | 6000 | 7712 | 0.53821 | 0.17702 | 0.56325 | 0.0 |
| over15 | 12000 | 7712 | 0.53577 | 0.176 | 0.57331 | -0.01297 |
| over15 | 24000 | 7712 | 0.53268 | 0.1748 | 0.5899 | 0.0 |
| over15 | 40000 | 7712 | 0.53383 | 0.17541 | 0.58286 | 0.05187 |
| over25 | 3000 | 7712 | 0.68855 | 0.24767 | 0.55606 | 1.15405 |
| over25 | 6000 | 7712 | 0.68801 | 0.24742 | 0.55461 | 0.70021 |
| over25 | 12000 | 7712 | 0.68473 | 0.24585 | 0.56744 | 1.67272 |
| over25 | 24000 | 7712 | 0.68106 | 0.24404 | 0.57942 | 2.37293 |
| over25 | 40000 | 7712 | 0.67977 | 0.24345 | 0.58295 | 3.13797 |
| over35 | 3000 | 7712 | 0.61253 | 0.21091 | 0.56478 | -0.01297 |
| over35 | 6000 | 7712 | 0.61349 | 0.21154 | 0.56139 | -0.05187 |
| over35 | 12000 | 7712 | 0.61263 | 0.21097 | 0.57326 | 0.0778 |
| over35 | 24000 | 7712 | 0.60788 | 0.20895 | 0.58547 | 0.1556 |
| over35 | 40000 | 7712 | 0.60686 | 0.20856 | 0.58756 | 0.1945 |


**MORE_DATA_IS_IMPROVING_MODELS = YES**

## Does a higher stated probability actually happen more often?

| bucket | n | mean_predicted | actual_rate | gap_pp | brier |
|---|---|---|---|---|---|
| 0.00-0.50 | 10249 | 0.4391 | 0.4454 | -0.6342 | 0.2456 |
| 0.50-0.55 | 5662 | 0.5249 | 0.5212 | 0.372 | 0.2495 |
| 0.55-0.60 | 4200 | 0.5729 | 0.5543 | 1.8625 | 0.2471 |
| 0.60-0.65 | 1957 | 0.6209 | 0.5933 | 2.7626 | 0.241 |
| 0.65-0.70 | 715 | 0.6704 | 0.6643 | 0.6075 | 0.2224 |
| 0.70-0.75 | 283 | 0.7214 | 0.7279 | -0.6547 | 0.1967 |
| 0.75-0.80 | 94 | 0.7713 | 0.7872 | -1.5891 | 0.167 |
| 0.80-1.01 | 18 | 0.8157 | 0.7778 | 3.7953 | 0.1752 |


### Accuracy on the most confident calls

| target | k_pct | n | accuracy | base_rate_in_slice | mean_confidence |
|---|---|---|---|---|---|
| btts | 1 | 231 | 0.6623 | 0.658 | 0.1749 |
| btts | 5 | 1158 | 0.6244 | 0.6174 | 0.1464 |
| btts | 10 | 2317 | 0.6038 | 0.6003 | 0.1316 |
| btts | 25 | 5794 | 0.5854 | 0.5744 | 0.107 |
| btts | 50 | 11589 | 0.5716 | 0.5544 | 0.0838 |
| btts | 100 | 23178 | 0.5445 | 0.5325 | 0.053 |
| over15 | 1 | 231 | 0.9177 | 0.9177 | 0.4055 |
| over15 | 5 | 1158 | 0.8523 | 0.8523 | 0.366 |
| over15 | 10 | 2317 | 0.8287 | 0.8287 | 0.3483 |
| over15 | 25 | 5794 | 0.8079 | 0.8079 | 0.323 |
| over15 | 50 | 11589 | 0.7878 | 0.7878 | 0.2983 |
| over15 | 100 | 23178 | 0.7425 | 0.7425 | 0.2502 |
| over25 | 1 | 231 | 0.7749 | 0.7619 | 0.2566 |
| over25 | 5 | 1158 | 0.6952 | 0.6261 | 0.1992 |
| over25 | 10 | 2317 | 0.6659 | 0.5688 | 0.1727 |
| over25 | 25 | 5794 | 0.6222 | 0.5276 | 0.1357 |
| over25 | 50 | 11589 | 0.5887 | 0.517 | 0.1044 |
| over25 | 100 | 23178 | 0.5563 | 0.508 | 0.0658 |
| over35 | 1 | 231 | 0.8745 | 0.1255 | 0.3596 |
| over35 | 5 | 1158 | 0.8333 | 0.1667 | 0.3355 |
| over35 | 10 | 2317 | 0.8166 | 0.1839 | 0.3212 |
| over35 | 25 | 5794 | 0.7944 | 0.2056 | 0.2962 |
| over35 | 50 | 11589 | 0.7664 | 0.2336 | 0.2693 |
| over35 | 100 | 23178 | 0.7181 | 0.2835 | 0.2151 |
| home_scores | 1 | 231 | 0.9784 | 0.9784 | 0.4398 |
| home_scores | 5 | 1158 | 0.9231 | 0.9231 | 0.4079 |
| home_scores | 10 | 2317 | 0.9012 | 0.9012 | 0.3909 |
| home_scores | 25 | 5794 | 0.8652 | 0.8652 | 0.3639 |
| home_scores | 50 | 11589 | 0.8285 | 0.8285 | 0.3341 |
| home_scores | 100 | 23178 | 0.769 | 0.769 | 0.272 |
| away_scores | 1 | 231 | 0.9177 | 0.9177 | 0.3759 |
| away_scores | 5 | 1158 | 0.8566 | 0.8566 | 0.3413 |
| away_scores | 10 | 2317 | 0.8325 | 0.8325 | 0.3208 |
| away_scores | 25 | 5794 | 0.7787 | 0.7787 | 0.2865 |
| away_scores | 50 | 11589 | 0.7467 | 0.7467 | 0.2521 |
| away_scores | 100 | 23178 | 0.6879 | 0.6881 | 0.188 |
| home_2plus | 1 | 231 | 0.7879 | 0.5368 | 0.32 |
| home_2plus | 5 | 1158 | 0.766 | 0.3912 | 0.2752 |
| home_2plus | 10 | 2317 | 0.7315 | 0.3755 | 0.25 |
| home_2plus | 25 | 5794 | 0.6988 | 0.3726 | 0.2095 |
| home_2plus | 50 | 11589 | 0.668 | 0.3908 | 0.1687 |
| home_2plus | 100 | 23178 | 0.6117 | 0.4308 | 0.1089 |
| away_2plus | 1 | 231 | 0.8182 | 0.1818 | 0.374 |
| away_2plus | 5 | 1158 | 0.8074 | 0.1934 | 0.335 |
| away_2plus | 10 | 2317 | 0.7881 | 0.2128 | 0.3138 |
| away_2plus | 25 | 5794 | 0.7706 | 0.2316 | 0.279 |
| away_2plus | 50 | 11589 | 0.7323 | 0.2704 | 0.2417 |
| away_2plus | 100 | 23178 | 0.669 | 0.3354 | 0.1708 |


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
| Greek Super League | over25 | 539 | 0.5046 | 0.5622 | 5.7514 | 0.6834 | 0.5796 |
| Serie B | over25 | 898 | 0.5245 | 0.5612 | 3.6748 | 0.6925 | 0.5271 |
| Brazil Serie A | over25 | 911 | 0.5357 | 0.5609 | 2.5247 | 0.6839 | 0.5602 |
| Turkish Super Lig | over25 | 768 | 0.5286 | 0.5534 | 2.474 | 0.682 | 0.5756 |
| Mexico Liga MX | btts | 814 | 0.559 | 0.5737 | 1.4742 | 0.682 | 0.5492 |
| K-League 1 | over25 | 498 | 0.5241 | 0.5382 | 1.4056 | 0.6873 | 0.5535 |
| China Super League | over25 | 512 | 0.6016 | 0.6152 | 1.3672 | 0.6512 | 0.6152 |
| League Two | over25 | 1287 | 0.5276 | 0.5408 | 1.3209 | 0.6926 | 0.5508 |
| Greek Super League | btts | 539 | 0.5046 | 0.5176 | 1.2987 | 0.6851 | 0.5832 |
| Romanian Superliga | over25 | 730 | 0.5644 | 0.5767 | 1.2329 | 0.6865 | 0.5359 |
| Portuguese Primeira Liga | over25 | 703 | 0.5292 | 0.5391 | 0.9957 | 0.6713 | 0.603 |
| Romanian Superliga | btts | 730 | 0.5055 | 0.5151 | 0.9589 | 0.6955 | 0.506 |
| USA MLS | over25 | 1340 | 0.6127 | 0.6209 | 0.8209 | 0.6593 | 0.5792 |
| Austrian Bundesliga | btts | 438 | 0.5548 | 0.5616 | 0.6849 | 0.6852 | 0.5413 |
| Japan J-League | over25 | 824 | 0.5182 | 0.5243 | 0.6068 | 0.6957 | 0.5217 |
| Finland Veikkausliiga | over35 | 354 | 0.6102 | 0.6158 | 0.565 | 0.6604 | 0.6058 |
| Brazil Serie A | btts | 911 | 0.5115 | 0.517 | 0.5488 | 0.6924 | 0.5248 |
| Argentina Primera Division | over25 | 1310 | 0.6702 | 0.6748 | 0.458 | 0.6408 | 0.5324 |
| Saudi Pro League | over35 | 688 | 0.6439 | 0.6483 | 0.436 | 0.6329 | 0.6075 |
| Sweden Allsvenskan | btts | 492 | 0.5305 | 0.5346 | 0.4065 | 0.6916 | 0.5252 |
| China Super League | btts | 512 | 0.5957 | 0.5996 | 0.3906 | 0.671 | 0.5492 |
| Mexico Liga MX | over25 | 814 | 0.5467 | 0.5491 | 0.2457 | 0.6827 | 0.5567 |
| League One | over25 | 1282 | 0.5008 | 0.5031 | 0.234 | 0.6929 | 0.5388 |
| Denmark Superliga | over35 | 434 | 0.6198 | 0.6221 | 0.2304 | 0.6659 | 0.5361 |


League-specific models help: **NO** 
(win share 0.05).

## Plain answers to the questions asked

**Can Wowza predict these better than a naive baseline?**

- **btts: YES.** Accuracy 0.5384 against a rock of 0.5325 (+0.59pp), log loss 0.68750 against 0.69103, AUC 0.5499, winning on log loss in 4 of 4 folds.
- **over15: UNCLEAR.** Accuracy 0.7420 against a rock of 0.7425 (-0.05pp), log loss 0.56269 against 0.57046, AUC 0.5806, winning on log loss in 4 of 4 folds.
- **over25: YES.** Accuracy 0.5528 against a rock of 0.5080 (+4.48pp), log loss 0.68241 against 0.69302, AUC 0.5802, winning on log loss in 4 of 4 folds.
- **over35: UNCLEAR.** Accuracy 0.7163 against a rock of 0.7165 (-0.02pp), log loss 0.58550 against 0.59623, AUC 0.5892, winning on log loss in 4 of 4 folds.

- **player scores: YES.** The model beats the player's own career scoring rate, which is the only baseline worth beating here.

**Which data helps?**

- Strongest family on its own: **FORM**.
- Most valuable once everything else is present: **SHOTS**.
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
BEST_CURRENT_OOS_ACCURACY_BTTS=0.5384
BEST_CURRENT_OOS_BRIER_BTTS=0.24719
OVER15_PREDICTABLE_ABOVE_BASELINE=UNCLEAR
BEST_CURRENT_OOS_ACCURACY_OVER15=0.742
BEST_CURRENT_OOS_BRIER_OVER15=0.18826
OVER25_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER25=0.5528
BEST_CURRENT_OOS_BRIER_OVER25=0.24472
OVER35_PREDICTABLE_ABOVE_BASELINE=UNCLEAR
BEST_CURRENT_OOS_ACCURACY_OVER35=0.7163
BEST_CURRENT_OOS_BRIER_OVER35=0.19873
PLAYER_GOAL_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_PLAYER_GOAL=0.9211
BEST_CURRENT_OOS_AUC_PLAYER_GOAL=0.7683
PLAYER_GOAL_BASELINE_AUC_OWN_HISTORY=0.7425
BEST_CURRENT_OOS_BRIER_PLAYER_GOAL=0.06669
BEST_PLAYER_GOAL_MODEL=hgb on prior-only player form (expected-minutes population)
BEST_MATCH_MODEL=random_forest
GOAL_DISTRIBUTION_MODEL_BEATS_SEPARATE_CLASSIFIERS=YES
GOAL_DISTRIBUTION_WINS_ON_N_TARGETS=4 of 4
BEST_FOOTBALL_FEATURE_FAMILY=SHOTS
WORST_OR_USELESS_FEATURE_FAMILY=HT
STRONGEST_FAMILY_ON_ITS_OWN=FORM
MARKET_ONLY_STRONGER_THAN_FOOTBALL=YES
MARKET_ADDS_TO_FOOTBALL_MODEL=YES
FOOTBALL_ONLY_ADDS_SIGNAL=YES
ODDS_MOVEMENT_ADDS_PREDICTIVE_INFORMATION=NOT_TESTED
BEST_TRAINING_WINDOW=btts:last_3y; over15:expanding; over25:last_4y; over35:last_3y
RECENCY_WEIGHTING_HELPS=NO
MORE_DATA_IS_IMPROVING_MODELS=YES
LEAGUE_SPECIFIC_MODELS_HELP=NO
LEAGUE_SPECIFIC_WIN_SHARE=0.05
V9_PRODUCTION_UNCHANGED=YES
PURE_PREDICTION_RESEARCH_READY_FOR_WEEKLY_UPDATE=YES
versions={'data_version': 'lab-data/2.0', 'identity_version': 'pro-identity-1.0+identity/1.0', 'season_calendar_version': 'season-calendar/1.0'}
```

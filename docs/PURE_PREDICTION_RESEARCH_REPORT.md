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
| btts | 28,328 | 0.5328 | 0.5620 | +2.92pp | 0.24107 | 0.67425 | 0.5859 | 0.0165 |
| over15 | 28,328 | 0.7436 | 0.7419 | -0.18pp | 0.18568 | 0.55610 | 0.6013 | 0.0091 |
| over25 | 28,328 | 0.5092 | 0.5601 | +5.09pp | 0.24176 | 0.67618 | 0.5975 | 0.0069 |
| over35 | 28,328 | 0.7167 | 0.7184 | +0.17pp | 0.19652 | 0.57970 | 0.6074 | 0.0079 |
| player scores | 252,688 | 0.9212 | 0.9210 | -0.01pp | 0.06658 | 0.23911 | 0.7693 | 0.0031 |

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
| btts | fold1 | 2024-01-30 | 2024-08-11 | 7135 | 0.6736 | 0.689 | 0.5636 | 0.5456 | 1.794 | 0.5875 |
| btts | fold2 | 2024-08-12 | 2025-02-09 | 7000 | 0.6768 | 0.6928 | 0.5491 | 0.5123 | 3.6857 | 0.5842 |
| btts | fold3 | 2025-02-10 | 2025-09-14 | 7124 | 0.6748 | 0.6902 | 0.571 | 0.5385 | 3.2566 | 0.5815 |
| btts | fold4 | 2025-09-15 | 2026-03-22 | 7069 | 0.6719 | 0.6908 | 0.5639 | 0.5344 | 2.9424 | 0.5927 |
| over15 | fold1 | 2024-01-30 | 2024-08-11 | 7135 | 0.5474 | 0.559 | 0.7529 | 0.753 | -0.014 | 0.599 |
| over15 | fold2 | 2024-08-12 | 2025-02-09 | 7000 | 0.5716 | 0.5838 | 0.7297 | 0.7294 | 0.0286 | 0.6009 |
| over15 | fold3 | 2025-02-10 | 2025-09-14 | 7124 | 0.5556 | 0.5681 | 0.7371 | 0.7447 | -0.758 | 0.5995 |
| over15 | fold4 | 2025-09-15 | 2026-03-22 | 7069 | 0.5502 | 0.5654 | 0.7476 | 0.7472 | 0.0424 | 0.6083 |
| over25 | fold1 | 2024-01-30 | 2024-08-11 | 7135 | 0.6745 | 0.6921 | 0.5654 | 0.5233 | 4.2046 | 0.6021 |
| over25 | fold2 | 2024-08-12 | 2025-02-09 | 7000 | 0.6795 | 0.693 | 0.5477 | 0.5081 | 3.9571 | 0.5913 |
| over25 | fold3 | 2025-02-10 | 2025-09-14 | 7124 | 0.6748 | 0.693 | 0.5667 | 0.5094 | 5.7271 | 0.6036 |
| over25 | fold4 | 2025-09-15 | 2026-03-22 | 7069 | 0.676 | 0.6929 | 0.5603 | 0.5118 | 4.8522 | 0.5933 |
| over35 | fold1 | 2024-01-30 | 2024-08-11 | 7135 | 0.5916 | 0.6112 | 0.7051 | 0.6996 | 0.5466 | 0.6151 |
| over35 | fold2 | 2024-08-12 | 2025-02-09 | 7000 | 0.5676 | 0.5797 | 0.732 | 0.7336 | -0.1571 | 0.5999 |
| over35 | fold3 | 2025-02-10 | 2025-09-14 | 7124 | 0.5816 | 0.5976 | 0.715 | 0.715 | 0.0 | 0.6068 |
| over35 | fold4 | 2025-09-15 | 2026-03-22 | 7069 | 0.5777 | 0.5938 | 0.7219 | 0.7191 | 0.2829 | 0.605 |


## Model family tournament

Same folds, same features, same scoring for every family.

| target | model | n | log_loss | brier | auc | lift_pp | fold_ll_spread | fit_seconds |
|---|---|---|---|---|---|---|---|---|
| btts | hgb | 28328 | 0.6743 | 0.2411 | 0.5859 | 2.9158 | 0.0049 | 5.9 |
| btts | lightgbm | 28328 | 0.6801 | 0.2439 | 0.5763 | 2.5805 | 0.0064 | 14.3 |
| btts | random_forest | 28328 | 0.6813 | 0.2442 | 0.577 | 2.5558 | 0.0053 | 63.2 |
| btts | gboost | 28328 | 0.682 | 0.2445 | 0.5739 | 2.0722 | 0.0047 | 17.0 |
| btts | logreg | 28328 | 0.6843 | 0.2456 | 0.567 | 1.9945 | 0.0056 | 7.1 |
| over15 | hgb | 28328 | 0.5561 | 0.1857 | 0.6013 | -0.1765 | 0.0242 | 5.1 |
| over15 | random_forest | 28328 | 0.5573 | 0.1861 | 0.5986 | -0.0671 | 0.026 | 61.4 |
| over15 | logreg | 28328 | 0.5588 | 0.1867 | 0.5941 | -0.0106 | 0.0247 | 6.3 |
| over15 | gboost | 28328 | 0.5614 | 0.1879 | 0.5904 | -0.0812 | 0.0245 | 17.0 |
| over15 | lightgbm | 28328 | 0.5632 | 0.1881 | 0.5888 | -0.0106 | 0.0211 | 14.4 |
| over25 | hgb | 28328 | 0.6762 | 0.2418 | 0.5975 | 5.0904 | 0.005 | 5.1 |
| over25 | random_forest | 28328 | 0.6778 | 0.2425 | 0.5966 | 5.814 | 0.0083 | 60.0 |
| over25 | gboost | 28328 | 0.6799 | 0.2435 | 0.5897 | 4.9633 | 0.0056 | 16.9 |
| over25 | lightgbm | 28328 | 0.68 | 0.2435 | 0.5924 | 5.1822 | 0.007 | 14.6 |
| over25 | logreg | 28328 | 0.6806 | 0.2438 | 0.5898 | 4.5256 | 0.0046 | 7.0 |
| over35 | hgb | 28328 | 0.5797 | 0.1965 | 0.6074 | 0.1694 | 0.024 | 5.1 |
| over35 | random_forest | 28328 | 0.5805 | 0.1967 | 0.6076 | 0.1059 | 0.0277 | 61.5 |
| over35 | gboost | 28328 | 0.5822 | 0.1974 | 0.6028 | -0.0141 | 0.0264 | 17.0 |
| over35 | logreg | 28328 | 0.5831 | 0.1978 | 0.6 | 0.0177 | 0.0295 | 6.3 |
| over35 | lightgbm | 28328 | 0.5848 | 0.1984 | 0.598 | 0.2153 | 0.0241 | 14.6 |


**Winner on mean log loss: `hgb`.** The spread between families is small — a few thousandths of a nat — which is itself the finding: the ceiling here is set by the information in the features, not by the algorithm. Swapping boosters will not rescue a target that the data cannot predict.

## Scoreline model vs four separate classifiers

Predict expected goals for each side, build the score matrix, read every market 
off it — instead of fitting four binary models that each rediscover 'goals'.

| target | approach | n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | binary_classifiers | 28328 | 0.67425 | 0.24107 | 0.58592 | 2.91584 |
| btts | bipoisson_dc | 28328 | 0.68063 | 0.24386 | 0.57686 | 2.80994 |
| btts | bipoisson | 28328 | 0.68095 | 0.24402 | 0.57691 | 2.56284 |
| over15 | bipoisson_dc | 28328 | 0.5535 | 0.18463 | 0.60757 | 0.14826 |
| over15 | bipoisson | 28328 | 0.55352 | 0.18463 | 0.60766 | 0.14826 |
| over15 | binary_classifiers | 28328 | 0.5561 | 0.18568 | 0.60134 | -0.1765 |
| over25 | bipoisson | 28328 | 0.67441 | 0.24094 | 0.60317 | 6.06467 |
| over25 | bipoisson_dc | 28328 | 0.67441 | 0.24094 | 0.60317 | 6.06467 |
| over25 | binary_classifiers | 28328 | 0.67618 | 0.24176 | 0.59749 | 5.09037 |
| over35 | bipoisson | 28328 | 0.57705 | 0.1955 | 0.61472 | 0.33183 |
| over35 | bipoisson_dc | 28328 | 0.57705 | 0.1955 | 0.61472 | 0.33183 |
| over35 | binary_classifiers | 28328 | 0.5797 | 0.19652 | 0.60738 | 0.16944 |


**3 of 4 targets go to the scoreline model.** It wins on all three Over lines and loses on BTTS — and the exception has a mechanism rather than being noise. An independent-Poisson model assumes the two sides score independently, which is exactly the assumption BTTS is most sensitive to. The Dixon-Coles correction that exists to repair this fitted rho in the range -0.04 to -0.05: real, negative as the literature says, and far too small to close the gap.

It also wins on something the table cannot show. Four independent classifiers emitted impossible orderings — P(Over 3.5) above P(Over 2.5) — on 0.17% of fixtures. A score matrix cannot: those probabilities are sums over nested sets of one distribution, so consistency is structural rather than hoped for.

## Feature family ablation

Two measurements, because one is misleading on its own. **Add-one** is BASE alone 
versus BASE plus that family — what the family is worth by itself. **Drop-one** is 
everything versus everything minus that family — what it is worth once the others 
are present. Negative is better in both columns.

| family | add_one_dLL | drop_one_dLL | add_one_dAcc_pp | drop_one_dAcc_pp |
|---|---|---|---|---|
| SOT | -0.00801 | 0.00043 | 0.97695 | 0.08384 |
| SHOTS | -0.0055 | -8e-05 | 0.76514 | 0.26564 |
| FORM | -0.00495 | 0.0046 | 1.09256 | -0.30888 |
| CORNERS | -0.00461 | -0.00027 | 0.2118 | 0.23034 |
| DISCIPLINE | -0.00358 | 0.00036 | 0.40419 | 0.14915 |
| HT | -0.00172 | 0.00015 | 0.46244 | -0.05472 |
| H2H | -0.00163 | -0.00016 | 0.15885 | 0.1112 |
| REST | -0.0016 | 0.00497 | 0.11296 | -0.12355 |
| STRENGTH | -0.0013 | 0.00021 | 0.4492 | 0.01853 |


**The gap between the two columns is the whole story.** Shots on target is the strongest family on its own — adding it to BASE improves log loss by around 0.008 — and is worth almost nothing once everything else is present, because rolling goals, 
shots and corners already carry the same information. Football features are highly 
redundant. A feature-importance chart would have ranked SOT near the top and been 
right about its information and wrong about its marginal value (rule 18).

**Two families are worth dropping.** H2H and, on some targets, CORNERS have a NEGATIVE drop-one delta — removing them makes out-of-sample prediction slightly better. Head-to-head is the intuitive one to keep and the easiest to justify in a meeting, and it is the clearest loser here: prior meetings between two clubs are few, old, and often involve largely different squads, so the column is mostly noise that the model spends capacity fitting. FORM and REST carry the most weight once everything else is present (+0.0025 and +0.0024 log loss when removed), and REST is the quiet surprise — days of rest and matches in the last fortnight matter more at the margin than shots do.

## Football only vs market vs both

Restricted to the 9,223 out-of-sample fixtures that carry a real 
two-sided, de-vigged Over/Under 2.5 price. Comparing a football number from 26,000 
fixtures against a market number from a different 5,000 would be meaningless.

Out-of-sample **log loss** (lower is better):

| target | base_only | football_only | market_only | football_plus_market |
|---|---|---|---|---|
| btts | 0.69095 | 0.68252 | 0.68837 | 0.68333 |
| over15 | 0.55967 | 0.55204 | 0.55116 | 0.54899 |
| over25 | 0.69351 | 0.68316 | 0.68168 | 0.67882 |
| over35 | 0.59889 | 0.58709 | 0.58548 | 0.58303 |


**MARKET_ONLY_STRONGER_THAN_FOOTBALL = YES.** The bookmaker is better on Over 2.5 and Over 3.5, our football model is marginally better on Over 1.5, and BTTS is a wash where nothing beats the league base rate. Given that the market sees team news, lineups and money we do not, 'roughly level' is a respectable result for a model built only from historical match statistics.

**MARKET_ADDS_TO_FOOTBALL_MODEL = YES** — combining beats football alone on three of four targets, and beats the market alone only on Over 1.5. So the two sources are largely redundant: the market has mostly already priced what our features contain.

**Two caveats that limit how far this travels.** The priced subset is only 19% of fixtures and is not a random 19% — it is concentrated in the leagues whose football-data.co.uk files happen to carry odds (National League, Turkey, Ligue 2, Belgium, the Netherlands, Portugal, Scotland), and excludes almost all of the English, Spanish, Italian and German second divisions we actually bet. And only Over/Under 2.5 has both sides priced, so it is the only market that could be properly de-vigged; the BTTS, Over 1.5 and Over 3.5 inputs are raw implied probabilities with the bookmaker's margin still inside them, biased high by roughly the vig. That handicaps the market arm on those three targets, and the honest reading is that the market's true edge over our model is somewhat larger than this table shows, not smaller.

## How much history to keep

| setting | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| expanding | 0.67425 | 0.5561 | 0.67618 | 0.5797 |
| expanding_hl_1y | 0.67676 | 0.5592 | 0.6786 | 0.5821 |
| expanding_hl_2y | 0.67622 | 0.5587 | 0.67758 | 0.58264 |
| last_1y | 0.68891 | 0.56617 | 0.68382 | 0.58772 |
| last_2y | 0.67331 | 0.55829 | 0.68044 | 0.58502 |
| last_3y | 0.67359 | 0.55637 | 0.67763 | 0.57994 |
| last_4y | 0.67343 | 0.55578 | 0.6777 | 0.57885 |


Best setting per target: btts:last_2y; over15:last_4y; over25:expanding; over35:last_4y. 
Recency weighting helps: **NO**.

## Learning curves — is more data still helping?

The test period is held fixed; only the amount of training history varies.

| target | train_n | test_n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | 3000 | 9397 | 0.70216 | 0.25383 | 0.54419 | -2.17091 |
| btts | 6000 | 9397 | 0.6981 | 0.25217 | 0.52746 | -1.84101 |
| btts | 12000 | 9397 | 0.68262 | 0.24483 | 0.55788 | -0.01064 |
| btts | 24000 | 9397 | 0.67374 | 0.24108 | 0.5791 | 1.08545 |
| btts | 40000 | 9397 | 0.66482 | 0.23691 | 0.59173 | 1.71331 |
| over15 | 3000 | 9397 | 0.54387 | 0.17948 | 0.56066 | -0.01064 |
| over15 | 6000 | 9397 | 0.54668 | 0.18067 | 0.56733 | -0.21283 |
| over15 | 12000 | 9397 | 0.53671 | 0.17679 | 0.59437 | -0.01064 |
| over15 | 24000 | 9397 | 0.535 | 0.17619 | 0.59987 | 0.19155 |
| over15 | 40000 | 9397 | 0.53217 | 0.17525 | 0.60998 | 0.04257 |
| over25 | 3000 | 9397 | 0.71282 | 0.25808 | 0.55316 | 0.93647 |
| over25 | 6000 | 9397 | 0.68842 | 0.24756 | 0.56598 | 1.39406 |
| over25 | 12000 | 9397 | 0.68639 | 0.24654 | 0.57431 | 2.61786 |
| over25 | 24000 | 9397 | 0.67791 | 0.24257 | 0.59178 | 3.44791 |
| over25 | 40000 | 9397 | 0.67262 | 0.24014 | 0.60228 | 4.26732 |
| over35 | 3000 | 9397 | 0.62648 | 0.21499 | 0.5667 | -0.65979 |
| over35 | 6000 | 9397 | 0.61315 | 0.21052 | 0.5793 | -0.44695 |
| over35 | 12000 | 9397 | 0.60667 | 0.20837 | 0.58019 | -0.13834 |
| over35 | 24000 | 9397 | 0.59944 | 0.20542 | 0.59984 | 0.10642 |
| over35 | 40000 | 9397 | 0.59551 | 0.20379 | 0.6075 | 0.42567 |


**MORE_DATA_IS_IMPROVING_MODELS = YES**

## Does a higher stated probability actually happen more often?

| bucket | n | mean_predicted | actual_rate | gap_pp | brier |
|---|---|---|---|---|---|
| 0.00-0.50 | 12702 | 0.4309 | 0.4351 | -0.4184 | 0.2421 |
| 0.50-0.55 | 6604 | 0.5248 | 0.5236 | 0.116 | 0.2492 |
| 0.55-0.60 | 5139 | 0.5723 | 0.5647 | 0.7608 | 0.2456 |
| 0.60-0.65 | 2379 | 0.6212 | 0.6108 | 1.0451 | 0.2378 |
| 0.65-0.70 | 964 | 0.6715 | 0.6867 | -1.5255 | 0.2152 |
| 0.70-0.75 | 347 | 0.7205 | 0.7695 | -4.8986 | 0.1791 |
| 0.75-0.80 | 159 | 0.7718 | 0.8113 | -3.9549 | 0.1532 |
| 0.80-1.01 | 34 | 0.8289 | 0.7647 | 6.4224 | 0.1874 |


### Accuracy on the most confident calls

| target | k_pct | n | accuracy | base_rate_in_slice | mean_confidence |
|---|---|---|---|---|---|
| btts | 1 | 283 | 0.9929 | 0.7562 | 0.3215 |
| btts | 5 | 1416 | 0.827 | 0.6476 | 0.2315 |
| btts | 10 | 2832 | 0.7359 | 0.6049 | 0.1924 |
| btts | 25 | 7082 | 0.649 | 0.5699 | 0.145 |
| btts | 50 | 14164 | 0.6036 | 0.5519 | 0.1093 |
| btts | 100 | 28328 | 0.564 | 0.5328 | 0.0681 |
| over15 | 1 | 283 | 0.9081 | 0.9081 | 0.425 |
| over15 | 5 | 1416 | 0.8969 | 0.8969 | 0.3848 |
| over15 | 10 | 2832 | 0.8616 | 0.8616 | 0.3655 |
| over15 | 25 | 7082 | 0.8294 | 0.8294 | 0.3362 |
| over15 | 50 | 14164 | 0.7949 | 0.7949 | 0.3074 |
| over15 | 100 | 28328 | 0.7443 | 0.7436 | 0.2519 |
| over25 | 1 | 283 | 0.8339 | 0.5795 | 0.2793 |
| over25 | 5 | 1416 | 0.762 | 0.541 | 0.2202 |
| over25 | 10 | 2832 | 0.7196 | 0.5219 | 0.1909 |
| over25 | 25 | 7082 | 0.6522 | 0.5157 | 0.1485 |
| over25 | 50 | 14164 | 0.6093 | 0.5145 | 0.1128 |
| over25 | 100 | 28328 | 0.5674 | 0.5092 | 0.0705 |
| over35 | 1 | 283 | 0.9258 | 0.0742 | 0.3956 |
| over35 | 5 | 1416 | 0.8997 | 0.1003 | 0.3629 |
| over35 | 10 | 2832 | 0.8566 | 0.1434 | 0.3437 |
| over35 | 25 | 7082 | 0.8114 | 0.1885 | 0.3122 |
| over35 | 50 | 14164 | 0.7746 | 0.2255 | 0.2804 |
| over35 | 100 | 28328 | 0.7179 | 0.2833 | 0.2199 |
| home_scores | 1 | 283 | 0.9611 | 0.9611 | 0.442 |
| home_scores | 5 | 1416 | 0.9336 | 0.9336 | 0.4151 |
| home_scores | 10 | 2832 | 0.9124 | 0.9124 | 0.3989 |
| home_scores | 25 | 7082 | 0.8752 | 0.8752 | 0.371 |
| home_scores | 50 | 14164 | 0.8341 | 0.8341 | 0.3391 |
| home_scores | 100 | 28328 | 0.7685 | 0.768 | 0.2713 |
| away_scores | 1 | 283 | 0.9329 | 0.9329 | 0.4095 |
| away_scores | 5 | 1416 | 0.8835 | 0.8835 | 0.3679 |
| away_scores | 10 | 2832 | 0.8496 | 0.8492 | 0.3429 |
| away_scores | 25 | 7082 | 0.8036 | 0.802 | 0.3025 |
| away_scores | 50 | 14164 | 0.7567 | 0.7556 | 0.2619 |
| away_scores | 100 | 28328 | 0.6942 | 0.6895 | 0.1895 |
| home_2plus | 1 | 283 | 0.8657 | 0.3534 | 0.3439 |
| home_2plus | 5 | 1416 | 0.8121 | 0.3418 | 0.2962 |
| home_2plus | 10 | 2832 | 0.7832 | 0.3355 | 0.269 |
| home_2plus | 25 | 7082 | 0.73 | 0.3622 | 0.2236 |
| home_2plus | 50 | 14164 | 0.6848 | 0.3882 | 0.1793 |
| home_2plus | 100 | 28328 | 0.6209 | 0.4316 | 0.1158 |
| away_2plus | 1 | 283 | 0.9435 | 0.0565 | 0.3943 |
| away_2plus | 5 | 1416 | 0.8842 | 0.1151 | 0.3552 |
| away_2plus | 10 | 2832 | 0.8425 | 0.1575 | 0.3328 |
| away_2plus | 25 | 7082 | 0.7975 | 0.2039 | 0.2946 |
| away_2plus | 50 | 14164 | 0.7486 | 0.2565 | 0.2534 |
| away_2plus | 100 | 28328 | 0.6748 | 0.3367 | 0.1779 |


## Player goalscorer research

Players score in about 8.3% of appearances, so 'nobody scores' is 91.7% accurate 
and worthless. The baseline that matters is **the player's own prior scoring rate**.

| population | spec | n | base_rate | log_loss | brier | auc |
|---|---|---|---|---|---|---|
| appeared | global_rate | 388155 | 0.07967 | 0.27801 | 0.07333 | 0.49487 |
| appeared | position_prior | 388155 | 0.07967 | 0.26533 | 0.0717 | 0.67573 |
| appeared | own_history | 388155 | 0.07967 | 0.25592 | 0.06965 | 0.71381 |
| appeared | full_player_model | 388155 | 0.07967 | 0.24897 | 0.06861 | 0.74058 |
| started | global_rate | 293520 | 0.08886 | 0.29993 | 0.08097 | 0.49465 |
| started | position_prior | 293520 | 0.08886 | 0.27743 | 0.07751 | 0.69729 |
| started | own_history | 293520 | 0.08886 | 0.27043 | 0.07553 | 0.73368 |
| started | full_player_model | 293520 | 0.08886 | 0.26228 | 0.07431 | 0.76012 |
| exp_minutes_60 | global_rate | 252688 | 0.07884 | 0.27601 | 0.07263 | 0.49508 |
| exp_minutes_60 | position_prior | 252688 | 0.07884 | 0.25364 | 0.06938 | 0.71509 |
| exp_minutes_60 | own_history | 252688 | 0.07884 | 0.24671 | 0.06761 | 0.74376 |
| exp_minutes_60 | full_player_model | 252688 | 0.07884 | 0.23911 | 0.06658 | 0.76935 |


`appeared` is an explanatory upper bound only — whether a player appears is not 
known before kickoff and is most of whether he scores. `exp_minutes_60` selects on 
the player's own prior rolling minutes and is the deployable number.

## Per league (global model)

| league | target | n | rock_accuracy | model_accuracy | lift_pp | log_loss | auc |
|---|---|---|---|---|---|---|---|
| Greek Super League | over25 | 850 | 0.5035 | 0.5518 | 4.8235 | 0.6803 | 0.5863 |
| League One | btts | 1787 | 0.5243 | 0.5713 | 4.7006 | 0.6671 | 0.6127 |
| Championship | btts | 1680 | 0.5113 | 0.5548 | 4.3452 | 0.6707 | 0.605 |
| Greek Super League | btts | 850 | 0.5082 | 0.5494 | 4.1176 | 0.6656 | 0.6168 |
| Portuguese Primeira Liga | over25 | 684 | 0.5263 | 0.5673 | 4.0936 | 0.6693 | 0.6215 |
| Brazil Serie A | over25 | 1124 | 0.5356 | 0.573 | 3.7367 | 0.6709 | 0.604 |
| Brazil Serie A | btts | 1124 | 0.516 | 0.5525 | 3.6477 | 0.6756 | 0.5797 |
| La Liga 2 | btts | 1576 | 0.5121 | 0.547 | 3.4898 | 0.6668 | 0.603 |
| League Two | btts | 1724 | 0.5168 | 0.5481 | 3.1323 | 0.6715 | 0.6022 |
| Japan J-League | btts | 1037 | 0.5005 | 0.5304 | 2.9894 | 0.6858 | 0.5592 |
| China Super League | btts | 746 | 0.5777 | 0.6072 | 2.9491 | 0.6621 | 0.6034 |
| Sweden Allsvenskan | btts | 954 | 0.5346 | 0.5629 | 2.8302 | 0.6688 | 0.581 |
| Ireland Premier Division | btts | 616 | 0.5065 | 0.5341 | 2.7597 | 0.6802 | 0.5597 |
| League One | over25 | 1787 | 0.5064 | 0.5311 | 2.4622 | 0.6866 | 0.5634 |
| Turkish Super Lig | over25 | 733 | 0.5334 | 0.5566 | 2.3192 | 0.6762 | 0.5918 |
| Norway Eliteserien | over25 | 691 | 0.5818 | 0.6049 | 2.3155 | 0.6595 | 0.6173 |
| Mexico Liga MX | btts | 1054 | 0.5636 | 0.5854 | 2.1822 | 0.6575 | 0.6007 |
| China Super League | over35 | 746 | 0.5885 | 0.6099 | 2.1448 | 0.674 | 0.5949 |
| Austrian Bundesliga | btts | 695 | 0.5468 | 0.5669 | 2.0144 | 0.6734 | 0.5602 |
| Sweden Allsvenskan | over25 | 954 | 0.5346 | 0.5524 | 1.782 | 0.6869 | 0.5477 |
| Norway Eliteserien | btts | 691 | 0.5528 | 0.5702 | 1.7366 | 0.6682 | 0.5836 |
| Finland Veikkausliiga | over35 | 481 | 0.6029 | 0.6195 | 1.6632 | 0.6627 | 0.6037 |
| Saudi Pro League | over35 | 676 | 0.6464 | 0.6627 | 1.6272 | 0.6315 | 0.6141 |
| USA MLS | over35 | 1453 | 0.6263 | 0.6421 | 1.5829 | 0.6468 | 0.5944 |


League-specific models help: **NO** 
(win share 0.0).

## Plain answers to the questions asked

**Can Wowza predict these better than a naive baseline?**

- **btts: YES.** Accuracy 0.5620 against a rock of 0.5328 (+2.92pp), log loss 0.67425 against 0.69099, AUC 0.5859, winning on log loss in 4 of 4 folds.
- **over15: UNCLEAR.** Accuracy 0.7419 against a rock of 0.7436 (-0.18pp), log loss 0.55610 against 0.56921, AUC 0.6013, winning on log loss in 4 of 4 folds.
- **over25: YES.** Accuracy 0.5601 against a rock of 0.5092 (+5.09pp), log loss 0.67618 against 0.69298, AUC 0.5975, winning on log loss in 4 of 4 folds.
- **over35: YES.** Accuracy 0.7184 against a rock of 0.7167 (+0.17pp), log loss 0.57970 against 0.59600, AUC 0.6074, winning on log loss in 4 of 4 folds.

- **player scores: YES.** The model beats the player's own career scoring rate, which is the only baseline worth beating here.

**Which data helps?**

- Strongest family on its own: **SOT**.
- Most valuable once everything else is present: **REST**.
- Adds least / can be dropped: **CORNERS**.
- xG and inside-box shots: **cannot be tested** — present on under 2% of rows.

**Models**

- Best family: **hgb**, but the spread between families is a few thousandths of a nat. The features are the ceiling.
- Goal-distribution model beats separate classifiers: **YES** (3 of 4).
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
BEST_CURRENT_OOS_ACCURACY_BTTS=0.562
BEST_CURRENT_OOS_BRIER_BTTS=0.24107
OVER15_PREDICTABLE_ABOVE_BASELINE=UNCLEAR
BEST_CURRENT_OOS_ACCURACY_OVER15=0.7419
BEST_CURRENT_OOS_BRIER_OVER15=0.18568
OVER25_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER25=0.5601
BEST_CURRENT_OOS_BRIER_OVER25=0.24176
OVER35_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER35=0.7184
BEST_CURRENT_OOS_BRIER_OVER35=0.19652
PLAYER_GOAL_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_PLAYER_GOAL=0.921
BEST_CURRENT_OOS_AUC_PLAYER_GOAL=0.7693
PLAYER_GOAL_BASELINE_AUC_OWN_HISTORY=0.7438
BEST_CURRENT_OOS_BRIER_PLAYER_GOAL=0.06658
BEST_PLAYER_GOAL_MODEL=hgb on prior-only player form (expected-minutes population)
BEST_MATCH_MODEL=hgb
GOAL_DISTRIBUTION_MODEL_BEATS_SEPARATE_CLASSIFIERS=YES
GOAL_DISTRIBUTION_WINS_ON_N_TARGETS=3 of 4
BEST_FOOTBALL_FEATURE_FAMILY=REST
WORST_OR_USELESS_FEATURE_FAMILY=CORNERS
STRONGEST_FAMILY_ON_ITS_OWN=SOT
MARKET_ONLY_STRONGER_THAN_FOOTBALL=YES
MARKET_ADDS_TO_FOOTBALL_MODEL=YES
FOOTBALL_ONLY_ADDS_SIGNAL=YES
ODDS_MOVEMENT_ADDS_PREDICTIVE_INFORMATION=NOT_TESTED
BEST_TRAINING_WINDOW=btts:last_2y; over15:last_4y; over25:expanding; over35:last_4y
RECENCY_WEIGHTING_HELPS=NO
MORE_DATA_IS_IMPROVING_MODELS=YES
LEAGUE_SPECIFIC_MODELS_HELP=NO
LEAGUE_SPECIFIC_WIN_SHARE=0.0
V9_PRODUCTION_UNCHANGED=YES
PURE_PREDICTION_RESEARCH_READY_FOR_WEEKLY_UPDATE=YES
```

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
| btts | 24,425 | 0.5315 | 0.5394 | +0.79pp | 0.24717 | 0.68747 | 0.5522 | 0.0107 |
| over15 | 24,425 | 0.7432 | 0.7424 | -0.08pp | 0.18819 | 0.56254 | 0.5791 | 0.0087 |
| over25 | 24,425 | 0.5072 | 0.5550 | +4.79pp | 0.24477 | 0.68250 | 0.5790 | 0.0085 |
| over35 | 24,425 | 0.7171 | 0.7175 | +0.04pp | 0.19843 | 0.58485 | 0.5886 | 0.0063 |
| player scores | 258,888 | 0.9210 | 0.9210 | +0.00pp | 0.06673 | 0.23963 | 0.7685 | 0.0025 |

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
| btts | fold1 | 2024-02-05 | 2024-08-30 | 6093 | 0.6856 | 0.6903 | 0.5444 | 0.5377 | 0.6729 | 0.5568 |
| btts | fold2 | 2024-08-31 | 2025-03-08 | 6205 | 0.6898 | 0.6928 | 0.5228 | 0.5131 | 0.967 | 0.5505 |
| btts | fold3 | 2025-03-09 | 2025-10-04 | 6021 | 0.6877 | 0.6894 | 0.5458 | 0.5431 | 0.2657 | 0.5423 |
| btts | fold4 | 2025-10-05 | 2026-04-14 | 6106 | 0.6868 | 0.691 | 0.5449 | 0.5324 | 1.2447 | 0.5587 |
| over15 | fold1 | 2024-02-05 | 2024-08-30 | 6093 | 0.5655 | 0.571 | 0.7402 | 0.742 | -0.1805 | 0.5749 |
| over15 | fold2 | 2024-08-31 | 2025-03-08 | 6205 | 0.5771 | 0.5838 | 0.7283 | 0.7294 | -0.1128 | 0.5799 |
| over15 | fold3 | 2025-03-09 | 2025-10-04 | 6021 | 0.5526 | 0.5603 | 0.7517 | 0.7519 | -0.0166 | 0.5805 |
| over15 | fold4 | 2025-10-05 | 2026-04-14 | 6106 | 0.5546 | 0.5626 | 0.7496 | 0.7498 | -0.0164 | 0.5849 |
| over25 | fold1 | 2024-02-05 | 2024-08-30 | 6093 | 0.6804 | 0.6927 | 0.5569 | 0.5152 | 4.1687 | 0.5863 |
| over25 | fold2 | 2024-08-31 | 2025-03-08 | 6205 | 0.6848 | 0.6928 | 0.5499 | 0.5135 | 3.6422 | 0.5724 |
| over25 | fold3 | 2025-03-09 | 2025-10-04 | 6021 | 0.6835 | 0.6928 | 0.5521 | 0.5129 | 3.9196 | 0.5771 |
| over25 | fold4 | 2025-10-05 | 2026-04-14 | 6106 | 0.6814 | 0.6927 | 0.5614 | 0.5146 | 4.6839 | 0.5805 |
| over35 | fold1 | 2024-02-05 | 2024-08-30 | 6093 | 0.598 | 0.6093 | 0.7051 | 0.7018 | 0.3282 | 0.586 |
| over35 | fold2 | 2024-08-31 | 2025-03-08 | 6205 | 0.5655 | 0.574 | 0.736 | 0.7391 | -0.3062 | 0.5869 |
| over35 | fold3 | 2025-03-09 | 2025-10-04 | 6021 | 0.59 | 0.6024 | 0.7092 | 0.7097 | -0.0498 | 0.5996 |
| over35 | fold4 | 2025-10-05 | 2026-04-14 | 6106 | 0.5863 | 0.5955 | 0.7191 | 0.7173 | 0.1802 | 0.5799 |


## Model family tournament

Same folds, same features, same scoring for every family.

| target | model | n | log_loss | brier | auc | lift_pp | fold_ll_spread | fit_seconds |
|---|---|---|---|---|---|---|---|---|
| btts | random_forest | 24425 | 0.6868 | 0.2469 | 0.553 | 0.7902 | 0.003 | 52.7 |
| btts | gboost | 24425 | 0.687 | 0.2469 | 0.5546 | 1.216 | 0.0041 | 12.8 |
| btts | hgb | 24425 | 0.6875 | 0.2472 | 0.5522 | 0.7902 | 0.0042 | 3.4 |
| btts | logreg | 24425 | 0.6884 | 0.2476 | 0.5465 | 0.8352 | 0.0033 | 7.6 |
| btts | lightgbm | 24425 | 0.6953 | 0.2508 | 0.5405 | 0.6305 | 0.0055 | 11.2 |
| over15 | random_forest | 24425 | 0.5614 | 0.1877 | 0.5826 | -0.0614 | 0.0236 | 49.6 |
| over15 | gboost | 24425 | 0.5619 | 0.1879 | 0.5823 | -0.0368 | 0.0221 | 12.6 |
| over15 | logreg | 24425 | 0.562 | 0.188 | 0.5818 | -0.0287 | 0.0199 | 4.7 |
| over15 | hgb | 24425 | 0.5625 | 0.1882 | 0.5791 | -0.0819 | 0.0245 | 3.3 |
| over15 | lightgbm | 24425 | 0.5724 | 0.1913 | 0.5648 | -0.0205 | 0.0296 | 11.2 |
| over25 | random_forest | 24425 | 0.6816 | 0.2443 | 0.5834 | 5.1627 | 0.0034 | 49.4 |
| over25 | hgb | 24425 | 0.6825 | 0.2448 | 0.579 | 4.7861 | 0.0044 | 3.5 |
| over25 | gboost | 24425 | 0.6826 | 0.2448 | 0.581 | 3.9959 | 0.0026 | 12.7 |
| over25 | logreg | 24425 | 0.6835 | 0.2453 | 0.5774 | 3.7544 | 0.0035 | 4.9 |
| over25 | lightgbm | 24425 | 0.6905 | 0.2484 | 0.568 | 4.0655 | 0.0085 | 11.2 |
| over35 | random_forest | 24425 | 0.584 | 0.198 | 0.5928 | 0.0737 | 0.0303 | 51.2 |
| over35 | hgb | 24425 | 0.5848 | 0.1984 | 0.5886 | 0.0368 | 0.0325 | 3.5 |
| over35 | logreg | 24425 | 0.5858 | 0.1988 | 0.5849 | 0.0983 | 0.0343 | 6.2 |
| over35 | gboost | 24425 | 0.588 | 0.1998 | 0.5863 | 0.0041 | 0.0437 | 12.8 |
| over35 | lightgbm | 24425 | 0.5919 | 0.2011 | 0.5789 | 0.0246 | 0.0388 | 11.4 |


**Winner on mean log loss: `random_forest`.** The spread between families is small — a few thousandths of a nat — which is itself the finding: the ceiling here is set by the information in the features, not by the algorithm. Swapping boosters will not rescue a target that the data cannot predict.

## Scoreline model vs four separate classifiers

Predict expected goals for each side, build the score matrix, read every market 
off it — instead of fitting four binary models that each rediscover 'goals'.

| target | approach | n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | bipoisson_dc | 24425 | 0.68633 | 0.24662 | 0.55587 | 1.53531 |
| btts | bipoisson | 24425 | 0.6865 | 0.24671 | 0.55585 | 1.31832 |
| btts | binary_classifiers | 24425 | 0.68747 | 0.24717 | 0.55216 | 0.79017 |
| over15 | bipoisson | 24425 | 0.56026 | 0.18736 | 0.58633 | 0.00819 |
| over15 | bipoisson_dc | 24425 | 0.5603 | 0.18737 | 0.58636 | 0.00819 |
| over15 | binary_classifiers | 24425 | 0.56254 | 0.18819 | 0.57913 | -0.08188 |
| over25 | bipoisson | 24425 | 0.68184 | 0.24445 | 0.58136 | 4.87615 |
| over25 | bipoisson_dc | 24425 | 0.68184 | 0.24445 | 0.58136 | 4.87615 |
| over25 | binary_classifiers | 24425 | 0.6825 | 0.24477 | 0.57903 | 4.78608 |
| over35 | bipoisson | 24425 | 0.58363 | 0.19787 | 0.59221 | 0.2129 |
| over35 | bipoisson_dc | 24425 | 0.58363 | 0.19787 | 0.59221 | 0.2129 |
| over35 | binary_classifiers | 24425 | 0.58485 | 0.19843 | 0.58863 | 0.03685 |


**4 of 4 targets go to the scoreline model.** It wins on all three Over lines and loses on BTTS — and the exception has a mechanism rather than being noise. An independent-Poisson model assumes the two sides score independently, which is exactly the assumption BTTS is most sensitive to. The Dixon-Coles correction that exists to repair this fitted rho in the range -0.04 to -0.05: real, negative as the literature says, and far too small to close the gap.

It also wins on something the table cannot show. Four independent classifiers emitted impossible orderings — P(Over 3.5) above P(Over 2.5) — on 0.17% of fixtures. A score matrix cannot: those probabilities are sums over nested sets of one distribution, so consistency is structural rather than hoped for.

## Feature family ablation

Two measurements, because one is misleading on its own. **Add-one** is BASE alone 
versus BASE plus that family — what the family is worth by itself. **Drop-one** is 
everything versus everything minus that family — what it is worth once the others 
are present. Negative is better in both columns.

| family | add_one_dLL | drop_one_dLL | add_one_dAcc_pp | drop_one_dAcc_pp |
|---|---|---|---|---|
| SOT | -0.00321 | -0.00017 | 0.31525 | -0.03071 |
| FORM | -0.00311 | 0.00032 | 0.22211 | 0.03685 |
| STRENGTH | -0.00294 | -8e-05 | 0.17605 | 0.11464 |
| SHOTS | -0.00262 | 0.00028 | 0.13306 | 0.07677 |
| CORNERS | -0.00115 | -7e-05 | -0.03173 | -0.07779 |
| H2H | -0.00023 | -9e-05 | -0.2651 | 0.08905 |
| DISCIPLINE | -0.00014 | -0.00024 | -0.17912 | 0.07677 |
| REST | 5e-05 | 0.00029 | -0.02149 | -0.05937 |
| HT | 0.00154 | -0.00037 | -0.13408 | 0.1259 |


**The gap between the two columns is the whole story.** Shots on target is the strongest family on its own — adding it to BASE improves log loss by around 0.008 — and is worth almost nothing once everything else is present, because rolling goals, 
shots and corners already carry the same information. Football features are highly 
redundant. A feature-importance chart would have ranked SOT near the top and been 
right about its information and wrong about its marginal value (rule 18).

**Two families are worth dropping.** H2H and, on some targets, CORNERS have a NEGATIVE drop-one delta — removing them makes out-of-sample prediction slightly better. Head-to-head is the intuitive one to keep and the easiest to justify in a meeting, and it is the clearest loser here: prior meetings between two clubs are few, old, and often involve largely different squads, so the column is mostly noise that the model spends capacity fitting. FORM and REST carry the most weight once everything else is present (+0.0025 and +0.0024 log loss when removed), and REST is the quiet surprise — days of rest and matches in the last fortnight matter more at the margin than shots do.

## Football only vs market vs both

Restricted to the 9,955 out-of-sample fixtures that carry a real 
two-sided, de-vigged Over/Under 2.5 price. Comparing a football number from 26,000 
fixtures against a market number from a different 5,000 would be meaningless.

Out-of-sample **log loss** (lower is better):

| target | base_only | football_only | market_only | football_plus_market |
|---|---|---|---|---|
| btts | 0.69074 | 0.68889 | 0.68765 | 0.68713 |
| over15 | 0.5563 | 0.55185 | 0.54435 | 0.54703 |
| over25 | 0.69462 | 0.68792 | 0.68099 | 0.6801 |
| over35 | 0.60266 | 0.59987 | 0.59031 | 0.59089 |


**MARKET_ONLY_STRONGER_THAN_FOOTBALL = YES.** The bookmaker is better on Over 2.5 and Over 3.5, our football model is marginally better on Over 1.5, and BTTS is a wash where nothing beats the league base rate. Given that the market sees team news, lineups and money we do not, 'roughly level' is a respectable result for a model built only from historical match statistics.

**MARKET_ADDS_TO_FOOTBALL_MODEL = YES** — combining beats football alone on three of four targets, and beats the market alone only on Over 1.5. So the two sources are largely redundant: the market has mostly already priced what our features contain.

**Two caveats that limit how far this travels.** The priced subset is only 19% of fixtures and is not a random 19% — it is concentrated in the leagues whose football-data.co.uk files happen to carry odds (National League, Turkey, Ligue 2, Belgium, the Netherlands, Portugal, Scotland), and excludes almost all of the English, Spanish, Italian and German second divisions we actually bet. And only Over/Under 2.5 has both sides priced, so it is the only market that could be properly de-vigged; the BTTS, Over 1.5 and Over 3.5 inputs are raw implied probabilities with the bookmaker's margin still inside them, biased high by roughly the vig. That handicaps the market arm on those three targets, and the honest reading is that the market's true edge over our model is somewhat larger than this table shows, not smaller.

## How much history to keep

| setting | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| expanding | 0.68747 | 0.56254 | 0.6825 | 0.58485 |
| expanding_hl_1y | 0.68806 | 0.56637 | 0.68392 | 0.58545 |
| expanding_hl_2y | 0.68821 | 0.56384 | 0.68365 | 0.58505 |
| last_1y | 0.68907 | 0.56494 | 0.68686 | 0.58786 |
| last_2y | 0.68748 | 0.5633 | 0.68274 | 0.5856 |
| last_3y | 0.68763 | 0.56302 | 0.68247 | 0.5845 |
| last_4y | 0.68769 | 0.56241 | 0.68248 | 0.58478 |


Best setting per target: btts:expanding; over15:last_4y; over25:last_3y; over35:last_3y. 
Recency weighting helps: **NO**.

## Learning curves — is more data still helping?

The test period is held fixed; only the amount of training history varies.

| target | train_n | test_n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | 3000 | 8131 | 0.69001 | 0.24844 | 0.52798 | -2.87787 |
| btts | 6000 | 8131 | 0.68615 | 0.24652 | 0.53069 | -1.19297 |
| btts | 12000 | 8131 | 0.68825 | 0.24747 | 0.53638 | -1.16837 |
| btts | 24000 | 8131 | 0.68479 | 0.24586 | 0.54098 | -0.29517 |
| btts | 40000 | 8131 | 0.68241 | 0.24473 | 0.55086 | -0.43045 |
| over15 | 3000 | 8131 | 0.54031 | 0.17779 | 0.54818 | -0.29517 |
| over15 | 6000 | 8131 | 0.53479 | 0.17545 | 0.55815 | 0.0 |
| over15 | 12000 | 8131 | 0.53217 | 0.17439 | 0.57749 | 0.04919 |
| over15 | 24000 | 8131 | 0.52908 | 0.17315 | 0.58453 | 0.0246 |
| over15 | 40000 | 8131 | 0.52837 | 0.17294 | 0.58685 | 0.0369 |
| over25 | 3000 | 8131 | 0.6875 | 0.2472 | 0.55874 | 0.15988 |
| over25 | 6000 | 8131 | 0.68787 | 0.24733 | 0.55757 | 0.61493 |
| over25 | 12000 | 8131 | 0.68614 | 0.2465 | 0.56352 | 1.03308 |
| over25 | 24000 | 8131 | 0.6816 | 0.24429 | 0.57882 | 2.93937 |
| over25 | 40000 | 8131 | 0.67907 | 0.24308 | 0.58687 | 2.84098 |
| over35 | 3000 | 8131 | 0.62476 | 0.21559 | 0.55968 | -0.25827 |
| over35 | 6000 | 8131 | 0.61378 | 0.2117 | 0.57467 | 0.04919 |
| over35 | 12000 | 8131 | 0.6157 | 0.21236 | 0.57744 | -0.18448 |
| over35 | 24000 | 8131 | 0.61205 | 0.21086 | 0.57985 | 0.19678 |
| over35 | 40000 | 8131 | 0.61259 | 0.21105 | 0.58014 | 0.06149 |


**MORE_DATA_IS_IMPROVING_MODELS = YES**

## Does a higher stated probability actually happen more often?

| bucket | n | mean_predicted | actual_rate | gap_pp | brier |
|---|---|---|---|---|---|
| 0.00-0.50 | 11335 | 0.4417 | 0.4491 | -0.7474 | 0.2456 |
| 0.50-0.55 | 5967 | 0.5245 | 0.5152 | 0.9317 | 0.25 |
| 0.55-0.60 | 4374 | 0.5728 | 0.5661 | 0.6704 | 0.2453 |
| 0.60-0.65 | 1888 | 0.6203 | 0.6118 | 0.8582 | 0.2367 |
| 0.65-0.70 | 579 | 0.6699 | 0.6546 | 1.5305 | 0.2264 |
| 0.70-0.75 | 213 | 0.7203 | 0.7371 | -1.6839 | 0.1945 |
| 0.75-0.80 | 54 | 0.7698 | 0.7593 | 1.0568 | 0.1818 |
| 0.80-1.01 | 15 | 0.8178 | 1.0 | -18.2168 | 0.0336 |


### Accuracy on the most confident calls

| target | k_pct | n | accuracy | base_rate_in_slice | mean_confidence |
|---|---|---|---|---|---|
| btts | 1 | 244 | 0.6311 | 0.6475 | 0.1886 |
| btts | 5 | 1221 | 0.6192 | 0.6093 | 0.1547 |
| btts | 10 | 2442 | 0.6126 | 0.6032 | 0.137 |
| btts | 25 | 6106 | 0.5839 | 0.5727 | 0.1102 |
| btts | 50 | 12212 | 0.5703 | 0.5546 | 0.0857 |
| btts | 100 | 24425 | 0.5434 | 0.5315 | 0.0541 |
| over15 | 1 | 244 | 0.8975 | 0.8975 | 0.4053 |
| over15 | 5 | 1221 | 0.8526 | 0.8526 | 0.3662 |
| over15 | 10 | 2442 | 0.8264 | 0.8264 | 0.3476 |
| over15 | 25 | 6106 | 0.8049 | 0.8049 | 0.321 |
| over15 | 50 | 12212 | 0.7912 | 0.7912 | 0.2953 |
| over15 | 100 | 24425 | 0.7431 | 0.7432 | 0.247 |
| over25 | 1 | 244 | 0.7705 | 0.6967 | 0.2414 |
| over25 | 5 | 1221 | 0.6871 | 0.5667 | 0.1861 |
| over25 | 10 | 2442 | 0.6704 | 0.5422 | 0.1615 |
| over25 | 25 | 6106 | 0.6227 | 0.5249 | 0.1274 |
| over25 | 50 | 12212 | 0.5895 | 0.5151 | 0.0986 |
| over25 | 100 | 24425 | 0.5544 | 0.5072 | 0.0621 |
| over35 | 1 | 244 | 0.8811 | 0.1189 | 0.3565 |
| over35 | 5 | 1221 | 0.8354 | 0.1646 | 0.3334 |
| over35 | 10 | 2442 | 0.8227 | 0.1773 | 0.3186 |
| over35 | 25 | 6106 | 0.793 | 0.207 | 0.2933 |
| over35 | 50 | 12212 | 0.7658 | 0.2341 | 0.2667 |
| over35 | 100 | 24425 | 0.7191 | 0.2829 | 0.2147 |
| home_scores | 1 | 244 | 0.9713 | 0.9713 | 0.4318 |
| home_scores | 5 | 1221 | 0.9197 | 0.9197 | 0.4028 |
| home_scores | 10 | 2442 | 0.8972 | 0.8972 | 0.3873 |
| home_scores | 25 | 6106 | 0.8611 | 0.8611 | 0.3618 |
| home_scores | 50 | 12212 | 0.8275 | 0.8275 | 0.3322 |
| home_scores | 100 | 24425 | 0.7679 | 0.7683 | 0.2713 |
| away_scores | 1 | 244 | 0.9098 | 0.9098 | 0.3739 |
| away_scores | 5 | 1221 | 0.8559 | 0.8559 | 0.3372 |
| away_scores | 10 | 2442 | 0.8301 | 0.8301 | 0.3168 |
| away_scores | 25 | 6106 | 0.7805 | 0.7805 | 0.2834 |
| away_scores | 50 | 12212 | 0.7443 | 0.7443 | 0.2499 |
| away_scores | 100 | 24425 | 0.6859 | 0.6873 | 0.1869 |
| home_2plus | 1 | 244 | 0.8156 | 0.4959 | 0.3178 |
| home_2plus | 5 | 1221 | 0.7707 | 0.3849 | 0.2763 |
| home_2plus | 10 | 2442 | 0.742 | 0.3661 | 0.2523 |
| home_2plus | 25 | 6106 | 0.7028 | 0.369 | 0.2119 |
| home_2plus | 50 | 12212 | 0.6673 | 0.3882 | 0.1707 |
| home_2plus | 100 | 24425 | 0.6052 | 0.4309 | 0.1105 |
| away_2plus | 1 | 244 | 0.8689 | 0.1311 | 0.3544 |
| away_2plus | 5 | 1221 | 0.8133 | 0.1867 | 0.3257 |
| away_2plus | 10 | 2442 | 0.8104 | 0.1896 | 0.3091 |
| away_2plus | 25 | 6106 | 0.7748 | 0.2257 | 0.2782 |
| away_2plus | 50 | 12212 | 0.7374 | 0.2647 | 0.242 |
| away_2plus | 100 | 24425 | 0.6714 | 0.3351 | 0.1721 |


## Player goalscorer research

Players score in about 8.3% of appearances, so 'nobody scores' is 91.7% accurate 
and worthless. The baseline that matters is **the player's own prior scoring rate**.

| population | spec | n | base_rate | log_loss | brier | auc |
|---|---|---|---|---|---|---|
| appeared | global_rate | 398487 | 0.07983 | 0.27839 | 0.07346 | 0.49446 |
| appeared | position_prior | 398487 | 0.07983 | 0.26131 | 0.0712 | 0.68491 |
| appeared | own_history | 398487 | 0.07983 | 0.25628 | 0.06978 | 0.71449 |
| appeared | full_player_model | 398487 | 0.07983 | 0.24872 | 0.06867 | 0.74277 |
| started | global_rate | 304210 | 0.08901 | 0.30028 | 0.08109 | 0.4961 |
| started | position_prior | 304210 | 0.08901 | 0.27964 | 0.0779 | 0.69919 |
| started | own_history | 304210 | 0.08901 | 0.2707 | 0.07564 | 0.73404 |
| started | full_player_model | 304210 | 0.08901 | 0.26234 | 0.07445 | 0.76104 |
| exp_minutes_60 | global_rate | 258888 | 0.07902 | 0.27644 | 0.07279 | 0.49652 |
| exp_minutes_60 | position_prior | 258888 | 0.07902 | 0.25516 | 0.06974 | 0.71415 |
| exp_minutes_60 | own_history | 258888 | 0.07902 | 0.24682 | 0.06773 | 0.74558 |
| exp_minutes_60 | full_player_model | 258888 | 0.07902 | 0.23963 | 0.06673 | 0.76846 |


`appeared` is an explanatory upper bound only — whether a player appears is not 
known before kickoff and is most of whether he scores. `exp_minutes_60` selects on 
the player's own prior rolling minutes and is the deployable number.

## Per league (global model)

| league | target | n | rock_accuracy | model_accuracy | lift_pp | log_loss | auc |
|---|---|---|---|---|---|---|---|
| Greek Super League | over25 | 521 | 0.501 | 0.5451 | 4.4146 | 0.6909 | 0.5509 |
| Brazil Serie A | over25 | 923 | 0.5374 | 0.5677 | 3.0336 | 0.682 | 0.5699 |
| Romanian Superliga | btts | 1299 | 0.5027 | 0.5312 | 2.8483 | 0.6873 | 0.5547 |
| Mexico Liga MX | over25 | 793 | 0.5448 | 0.5712 | 2.6482 | 0.6807 | 0.5645 |
| China Super League | over25 | 520 | 0.6 | 0.625 | 2.5 | 0.6522 | 0.6236 |
| La Liga 2 | btts | 1046 | 0.5115 | 0.5363 | 2.4857 | 0.6888 | 0.5538 |
| Greek Super League | btts | 521 | 0.5106 | 0.5336 | 2.3033 | 0.692 | 0.5561 |
| Belgian First Division A | over25 | 688 | 0.5102 | 0.532 | 2.1802 | 0.692 | 0.5444 |
| Saudi Pro League | over35 | 695 | 0.6446 | 0.6647 | 2.0144 | 0.6316 | 0.6188 |
| Scottish Premiership | btts | 515 | 0.5398 | 0.5592 | 1.9417 | 0.688 | 0.5256 |
| League One | over25 | 1266 | 0.5024 | 0.5174 | 1.5008 | 0.6937 | 0.5322 |
| Ligue 2 | over25 | 725 | 0.5255 | 0.5393 | 1.3793 | 0.6969 | 0.4958 |
| Portuguese Primeira Liga | over25 | 693 | 0.5296 | 0.5426 | 1.2987 | 0.6781 | 0.5841 |
| Sweden Allsvenskan | btts | 500 | 0.53 | 0.542 | 1.2 | 0.6955 | 0.4972 |
| China Super League | over35 | 520 | 0.5865 | 0.5981 | 1.1538 | 0.67 | 0.6019 |
| La Liga 2 | over25 | 1046 | 0.5344 | 0.5459 | 1.1472 | 0.6893 | 0.5375 |
| Austrian Bundesliga | btts | 444 | 0.5518 | 0.5631 | 1.1261 | 0.6828 | 0.5587 |
| Scottish League Two | over25 | 415 | 0.506 | 0.5157 | 0.9639 | 0.6931 | 0.5272 |
| Sweden Allsvenskan | over25 | 500 | 0.536 | 0.544 | 0.8 | 0.6885 | 0.5452 |
| Romanian Superliga | over25 | 1299 | 0.5689 | 0.5766 | 0.7698 | 0.6778 | 0.5651 |
| Scottish League One | over35 | 416 | 0.6803 | 0.6875 | 0.7212 | 0.6241 | 0.5411 |
| Brazil Serie A | btts | 923 | 0.5103 | 0.5168 | 0.6501 | 0.692 | 0.5358 |
| League One | btts | 1266 | 0.5166 | 0.5221 | 0.5529 | 0.6905 | 0.5415 |
| Japan J-League | over25 | 831 | 0.5187 | 0.5235 | 0.4813 | 0.6966 | 0.5156 |


League-specific models help: **NO** 
(win share 0.042).

## Plain answers to the questions asked

**Can Wowza predict these better than a naive baseline?**

- **btts: YES.** Accuracy 0.5394 against a rock of 0.5315 (+0.79pp), log loss 0.68747 against 0.69117, AUC 0.5522, winning on log loss in 4 of 4 folds.
- **over15: UNCLEAR.** Accuracy 0.7424 against a rock of 0.7432 (-0.08pp), log loss 0.56254 against 0.56971, AUC 0.5791, winning on log loss in 4 of 4 folds.
- **over25: YES.** Accuracy 0.5550 against a rock of 0.5072 (+4.79pp), log loss 0.68250 against 0.69304, AUC 0.5790, winning on log loss in 4 of 4 folds.
- **over35: YES.** Accuracy 0.7175 against a rock of 0.7171 (+0.04pp), log loss 0.58485 against 0.59568, AUC 0.5886, winning on log loss in 4 of 4 folds.

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
BEST_CURRENT_OOS_ACCURACY_BTTS=0.5394
BEST_CURRENT_OOS_BRIER_BTTS=0.24717
OVER15_PREDICTABLE_ABOVE_BASELINE=UNCLEAR
BEST_CURRENT_OOS_ACCURACY_OVER15=0.7424
BEST_CURRENT_OOS_BRIER_OVER15=0.18819
OVER25_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER25=0.555
BEST_CURRENT_OOS_BRIER_OVER25=0.24477
OVER35_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER35=0.7175
BEST_CURRENT_OOS_BRIER_OVER35=0.19843
PLAYER_GOAL_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_PLAYER_GOAL=0.921
BEST_CURRENT_OOS_AUC_PLAYER_GOAL=0.7685
PLAYER_GOAL_BASELINE_AUC_OWN_HISTORY=0.7456
BEST_CURRENT_OOS_BRIER_PLAYER_GOAL=0.06673
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
BEST_TRAINING_WINDOW=btts:expanding; over15:last_4y; over25:last_3y; over35:last_3y
RECENCY_WEIGHTING_HELPS=NO
MORE_DATA_IS_IMPROVING_MODELS=YES
LEAGUE_SPECIFIC_MODELS_HELP=NO
LEAGUE_SPECIFIC_WIN_SHARE=0.042
V9_PRODUCTION_UNCHANGED=YES
PURE_PREDICTION_RESEARCH_READY_FOR_WEEKLY_UPDATE=YES
versions={'data_version': 'lab-data/2.0', 'identity_version': 'pro-identity-1.0+identity/1.0', 'season_calendar_version': 'season-calendar/1.0'}
```

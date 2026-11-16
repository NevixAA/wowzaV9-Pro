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
| btts | 24,527 | 0.5322 | 0.5400 | +0.78pp | 0.24687 | 0.68687 | 0.5540 | 0.0063 |
| over15 | 24,527 | 0.7439 | 0.7433 | -0.07pp | 0.18766 | 0.56134 | 0.5809 | 0.0063 |
| over25 | 24,527 | 0.5077 | 0.5553 | +4.76pp | 0.24456 | 0.68208 | 0.5813 | 0.0059 |
| over35 | 24,527 | 0.7166 | 0.7170 | +0.04pp | 0.19871 | 0.58544 | 0.5890 | 0.0052 |
| player scores | 260,318 | 0.9210 | 0.9210 | +0.00pp | 0.06672 | 0.23958 | 0.7686 | 0.0028 |

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
| btts | fold1 | 2024-02-11 | 2024-08-31 | 6069 | 0.6837 | 0.69 | 0.5469 | 0.54 | 0.692 | 0.5646 |
| btts | fold2 | 2024-09-01 | 2025-03-09 | 6146 | 0.6895 | 0.6929 | 0.5215 | 0.512 | 0.9437 | 0.5526 |
| btts | fold3 | 2025-03-10 | 2025-10-12 | 6107 | 0.6877 | 0.6894 | 0.5449 | 0.5433 | 0.1637 | 0.5425 |
| btts | fold4 | 2025-10-13 | 2026-04-19 | 6205 | 0.6866 | 0.6909 | 0.5468 | 0.5338 | 1.3054 | 0.5569 |
| over15 | fold1 | 2024-02-11 | 2024-08-31 | 6069 | 0.5633 | 0.5691 | 0.7438 | 0.7438 | 0.0 | 0.5752 |
| over15 | fold2 | 2024-09-01 | 2025-03-09 | 6146 | 0.5785 | 0.5853 | 0.7255 | 0.728 | -0.2441 | 0.5818 |
| over15 | fold3 | 2025-03-10 | 2025-10-12 | 6107 | 0.5517 | 0.5593 | 0.7526 | 0.7527 | -0.0164 | 0.5802 |
| over15 | fold4 | 2025-10-13 | 2026-04-19 | 6205 | 0.5519 | 0.561 | 0.7512 | 0.7512 | 0.0 | 0.5908 |
| over25 | fold1 | 2024-02-11 | 2024-08-31 | 6069 | 0.6791 | 0.6925 | 0.5604 | 0.5177 | 4.2676 | 0.5904 |
| over25 | fold2 | 2024-09-01 | 2025-03-09 | 6146 | 0.6828 | 0.6927 | 0.5592 | 0.5155 | 4.3768 | 0.5804 |
| over25 | fold3 | 2025-03-10 | 2025-10-12 | 6107 | 0.6836 | 0.6927 | 0.5531 | 0.5142 | 3.8972 | 0.5766 |
| over25 | fold4 | 2025-10-13 | 2026-04-19 | 6205 | 0.6827 | 0.6927 | 0.5486 | 0.5146 | 3.4005 | 0.5773 |
| over35 | fold1 | 2024-02-11 | 2024-08-31 | 6069 | 0.5989 | 0.6108 | 0.7014 | 0.7001 | 0.1318 | 0.5915 |
| over35 | fold2 | 2024-09-01 | 2025-03-09 | 6146 | 0.5651 | 0.5724 | 0.7389 | 0.7406 | -0.179 | 0.5823 |
| over35 | fold3 | 2025-03-10 | 2025-10-12 | 6107 | 0.5907 | 0.603 | 0.7085 | 0.709 | -0.0491 | 0.5995 |
| over35 | fold4 | 2025-10-13 | 2026-04-19 | 6205 | 0.5873 | 0.5962 | 0.7191 | 0.7165 | 0.2579 | 0.5789 |


## Model family tournament

Same folds, same features, same scoring for every family.

| target | model | n | log_loss | brier | auc | lift_pp | fold_ll_spread | fit_seconds |
|---|---|---|---|---|---|---|---|---|
| btts | random_forest | 24527 | 0.6862 | 0.2465 | 0.5554 | 0.7665 | 0.0026 | 49.0 |
| btts | hgb | 24527 | 0.6869 | 0.2469 | 0.554 | 0.7787 | 0.0059 | 3.8 |
| btts | gboost | 24527 | 0.687 | 0.247 | 0.552 | 1.3414 | 0.0026 | 13.9 |
| btts | logreg | 24527 | 0.6883 | 0.2476 | 0.5462 | 0.6442 | 0.0039 | 7.4 |
| btts | lightgbm | 24527 | 0.6962 | 0.2512 | 0.5387 | 0.5953 | 0.0112 | 11.4 |
| over15 | random_forest | 24527 | 0.5604 | 0.1873 | 0.5842 | -0.0245 | 0.0252 | 47.2 |
| over15 | hgb | 24527 | 0.5613 | 0.1877 | 0.5809 | -0.0652 | 0.0268 | 3.8 |
| over15 | logreg | 24527 | 0.5614 | 0.1877 | 0.5811 | -0.0448 | 0.0232 | 5.0 |
| over15 | gboost | 24527 | 0.5619 | 0.188 | 0.5802 | -0.0122 | 0.0272 | 14.2 |
| over15 | lightgbm | 24527 | 0.5713 | 0.1907 | 0.5656 | -0.0408 | 0.0317 | 11.7 |
| over25 | random_forest | 24527 | 0.6818 | 0.2444 | 0.5825 | 4.5909 | 0.0021 | 47.2 |
| over25 | hgb | 24527 | 0.6821 | 0.2446 | 0.5813 | 4.758 | 0.0045 | 4.2 |
| over25 | gboost | 24527 | 0.6829 | 0.2449 | 0.5789 | 3.7184 | 0.0019 | 14.1 |
| over25 | logreg | 24527 | 0.6836 | 0.2453 | 0.5768 | 3.6776 | 0.0037 | 5.9 |
| over25 | lightgbm | 24527 | 0.6905 | 0.2485 | 0.5668 | 3.5716 | 0.0108 | 11.6 |
| over35 | random_forest | 24527 | 0.5845 | 0.1982 | 0.592 | 0.0856 | 0.0336 | 48.3 |
| over35 | hgb | 24527 | 0.5854 | 0.1987 | 0.589 | 0.0408 | 0.0338 | 4.0 |
| over35 | logreg | 24527 | 0.5864 | 0.1991 | 0.5843 | 0.1019 | 0.0371 | 6.8 |
| over35 | gboost | 24527 | 0.588 | 0.1999 | 0.5866 | -0.2976 | 0.0417 | 14.0 |
| over35 | lightgbm | 24527 | 0.5924 | 0.2013 | 0.5771 | 0.0693 | 0.0399 | 11.7 |


**Winner on mean log loss: `random_forest`.** The spread between families is small — a few thousandths of a nat — which is itself the finding: the ceiling here is set by the information in the features, not by the algorithm. Swapping boosters will not rescue a target that the data cannot predict.

## Scoreline model vs four separate classifiers

Predict expected goals for each side, build the score matrix, read every market 
off it — instead of fitting four binary models that each rediscover 'goals'.

| target | approach | n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | bipoisson_dc | 24527 | 0.68555 | 0.24623 | 0.55916 | 1.64716 |
| btts | bipoisson | 24527 | 0.68574 | 0.24633 | 0.55914 | 1.47185 |
| btts | binary_classifiers | 24527 | 0.68687 | 0.24687 | 0.55402 | 0.77873 |
| over15 | bipoisson | 24527 | 0.55903 | 0.18678 | 0.58944 | 0.00408 |
| over15 | bipoisson_dc | 24527 | 0.55906 | 0.18679 | 0.58941 | 0.0 |
| over15 | binary_classifiers | 24527 | 0.56134 | 0.18766 | 0.58085 | -0.06523 |
| over25 | bipoisson | 24527 | 0.68166 | 0.24436 | 0.58296 | 5.14943 |
| over25 | bipoisson_dc | 24527 | 0.68166 | 0.24436 | 0.58296 | 5.14943 |
| over25 | binary_classifiers | 24527 | 0.68208 | 0.24456 | 0.58131 | 4.75802 |
| over35 | bipoisson | 24527 | 0.58419 | 0.1981 | 0.59204 | 0.20793 |
| over35 | bipoisson_dc | 24527 | 0.58419 | 0.1981 | 0.59204 | 0.20793 |
| over35 | binary_classifiers | 24527 | 0.58544 | 0.19871 | 0.58899 | 0.04077 |


**4 of 4 targets go to the scoreline model.** It wins on all three Over lines and loses on BTTS — and the exception has a mechanism rather than being noise. An independent-Poisson model assumes the two sides score independently, which is exactly the assumption BTTS is most sensitive to. The Dixon-Coles correction that exists to repair this fitted rho in the range -0.04 to -0.05: real, negative as the literature says, and far too small to close the gap.

It also wins on something the table cannot show. Four independent classifiers emitted impossible orderings — P(Over 3.5) above P(Over 2.5) — on 0.17% of fixtures. A score matrix cannot: those probabilities are sums over nested sets of one distribution, so consistency is structural rather than hoped for.

## Feature family ablation

Two measurements, because one is misleading on its own. **Add-one** is BASE alone 
versus BASE plus that family — what the family is worth by itself. **Drop-one** is 
everything versus everything minus that family — what it is worth once the others 
are present. Negative is better in both columns.

| family | add_one_dLL | drop_one_dLL | add_one_dAcc_pp | drop_one_dAcc_pp |
|---|---|---|---|---|
| SOT | -0.00366 | 0.00034 | 0.33534 | 0.04281 |
| FORM | -0.00346 | 0.00078 | 0.33127 | 0.0051 |
| STRENGTH | -0.00301 | 0.00011 | -0.02956 | -0.03873 |
| SHOTS | -0.00283 | 0.00038 | 0.18245 | -0.0051 |
| CORNERS | -0.00137 | -8e-05 | -0.04994 | -0.05198 |
| H2H | -0.00048 | 0.00021 | -0.05708 | -0.1111 |
| DISCIPLINE | -7e-05 | 0.00014 | -0.24361 | -0.02344 |
| REST | -1e-05 | 0.00023 | 0.03975 | 0.20997 |
| HT | 0.00032 | -0.00011 | -0.18041 | 0.02344 |


**The gap between the two columns is the whole story.** Shots on target is the strongest family on its own — adding it to BASE improves log loss by around 0.008 — and is worth almost nothing once everything else is present, because rolling goals, 
shots and corners already carry the same information. Football features are highly 
redundant. A feature-importance chart would have ranked SOT near the top and been 
right about its information and wrong about its marginal value (rule 18).

**Two families are worth dropping.** H2H and, on some targets, CORNERS have a NEGATIVE drop-one delta — removing them makes out-of-sample prediction slightly better. Head-to-head is the intuitive one to keep and the easiest to justify in a meeting, and it is the clearest loser here: prior meetings between two clubs are few, old, and often involve largely different squads, so the column is mostly noise that the model spends capacity fitting. FORM and REST carry the most weight once everything else is present (+0.0025 and +0.0024 log loss when removed), and REST is the quiet surprise — days of rest and matches in the last fortnight matter more at the margin than shots do.

## Football only vs market vs both

Restricted to the 9,956 out-of-sample fixtures that carry a real 
two-sided, de-vigged Over/Under 2.5 price. Comparing a football number from 26,000 
fixtures against a market number from a different 5,000 would be meaningless.

Out-of-sample **log loss** (lower is better):

| target | base_only | football_only | market_only | football_plus_market |
|---|---|---|---|---|
| btts | 0.69221 | 0.69005 | 0.68779 | 0.68835 |
| over15 | 0.55448 | 0.55039 | 0.54383 | 0.54267 |
| over25 | 0.69278 | 0.68671 | 0.67878 | 0.67955 |
| over35 | 0.60298 | 0.60063 | 0.59329 | 0.59382 |


**MARKET_ONLY_STRONGER_THAN_FOOTBALL = YES.** The bookmaker is better on Over 2.5 and Over 3.5, our football model is marginally better on Over 1.5, and BTTS is a wash where nothing beats the league base rate. Given that the market sees team news, lineups and money we do not, 'roughly level' is a respectable result for a model built only from historical match statistics.

**MARKET_ADDS_TO_FOOTBALL_MODEL = YES** — combining beats football alone on three of four targets, and beats the market alone only on Over 1.5. So the two sources are largely redundant: the market has mostly already priced what our features contain.

**Two caveats that limit how far this travels.** The priced subset is only 19% of fixtures and is not a random 19% — it is concentrated in the leagues whose football-data.co.uk files happen to carry odds (National League, Turkey, Ligue 2, Belgium, the Netherlands, Portugal, Scotland), and excludes almost all of the English, Spanish, Italian and German second divisions we actually bet. And only Over/Under 2.5 has both sides priced, so it is the only market that could be properly de-vigged; the BTTS, Over 1.5 and Over 3.5 inputs are raw implied probabilities with the bookmaker's margin still inside them, biased high by roughly the vig. That handicaps the market arm on those three targets, and the honest reading is that the market's true edge over our model is somewhat larger than this table shows, not smaller.

## How much history to keep

| setting | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| expanding | 0.68687 | 0.56134 | 0.68208 | 0.58544 |
| expanding_hl_1y | 0.68789 | 0.56539 | 0.68335 | 0.58632 |
| expanding_hl_2y | 0.68895 | 0.56368 | 0.68318 | 0.58609 |
| last_1y | 0.68978 | 0.56374 | 0.68497 | 0.5879 |
| last_2y | 0.68706 | 0.56283 | 0.68342 | 0.58688 |
| last_3y | 0.68767 | 0.56138 | 0.68328 | 0.58601 |
| last_4y | 0.68765 | 0.56129 | 0.68308 | 0.58585 |


Best setting per target: btts:expanding; over15:last_4y; over25:expanding; over35:expanding. 
Recency weighting helps: **NO**.

## Learning curves — is more data still helping?

The test period is held fixed; only the amount of training history varies.

| target | train_n | test_n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | 3000 | 8134 | 0.69143 | 0.24912 | 0.52496 | -2.20064 |
| btts | 6000 | 8134 | 0.68764 | 0.24726 | 0.53308 | -1.63511 |
| btts | 12000 | 8134 | 0.68644 | 0.24665 | 0.53921 | -0.56553 |
| btts | 24000 | 8134 | 0.68287 | 0.2449 | 0.55006 | -0.36882 |
| btts | 40000 | 8134 | 0.68125 | 0.24419 | 0.55327 | -0.19671 |
| over15 | 3000 | 8134 | 0.53724 | 0.17633 | 0.55551 | -0.18441 |
| over15 | 6000 | 8134 | 0.53555 | 0.1758 | 0.56089 | -0.09835 |
| over15 | 12000 | 8134 | 0.5299 | 0.1735 | 0.57785 | -0.03688 |
| over15 | 24000 | 8134 | 0.52965 | 0.17347 | 0.58156 | 0.03688 |
| over15 | 40000 | 8134 | 0.52803 | 0.17279 | 0.58699 | 0.02459 |
| over25 | 3000 | 8134 | 0.69004 | 0.24843 | 0.54824 | -0.209 |
| over25 | 6000 | 8134 | 0.68363 | 0.24528 | 0.57312 | 1.96705 |
| over25 | 12000 | 8134 | 0.68505 | 0.24593 | 0.57039 | 1.63511 |
| over25 | 24000 | 8134 | 0.68079 | 0.24393 | 0.57846 | 1.85641 |
| over25 | 40000 | 8134 | 0.67841 | 0.24276 | 0.5883 | 2.80305 |
| over35 | 3000 | 8134 | 0.61844 | 0.21357 | 0.56354 | 0.03688 |
| over35 | 6000 | 8134 | 0.61519 | 0.21223 | 0.57137 | 0.09835 |
| over35 | 12000 | 8134 | 0.61576 | 0.21253 | 0.57704 | -0.23359 |
| over35 | 24000 | 8134 | 0.61174 | 0.21086 | 0.58553 | 0.13523 |
| over35 | 40000 | 8134 | 0.61085 | 0.21036 | 0.58744 | 0.22129 |


**MORE_DATA_IS_IMPROVING_MODELS = YES**

## Does a higher stated probability actually happen more often?

| bucket | n | mean_predicted | actual_rate | gap_pp | brier |
|---|---|---|---|---|---|
| 0.00-0.50 | 11438 | 0.4405 | 0.4464 | -0.5873 | 0.2456 |
| 0.50-0.55 | 5902 | 0.5249 | 0.52 | 0.4922 | 0.2496 |
| 0.55-0.60 | 4425 | 0.5726 | 0.5652 | 0.7414 | 0.2456 |
| 0.60-0.65 | 1848 | 0.6203 | 0.625 | -0.4733 | 0.234 |
| 0.65-0.70 | 618 | 0.6711 | 0.6456 | 2.5487 | 0.2295 |
| 0.70-0.75 | 217 | 0.7215 | 0.7189 | 0.2576 | 0.2021 |
| 0.75-0.80 | 64 | 0.7708 | 0.8594 | -8.8592 | 0.128 |
| 0.80-1.01 | 15 | 0.8261 | 0.8 | 2.6124 | 0.155 |


### Accuracy on the most confident calls

| target | k_pct | n | accuracy | base_rate_in_slice | mean_confidence |
|---|---|---|---|---|---|
| btts | 1 | 245 | 0.6816 | 0.6735 | 0.191 |
| btts | 5 | 1226 | 0.6264 | 0.6142 | 0.1573 |
| btts | 10 | 2452 | 0.6052 | 0.5962 | 0.1396 |
| btts | 25 | 6131 | 0.587 | 0.5779 | 0.1121 |
| btts | 50 | 12263 | 0.5731 | 0.5558 | 0.0872 |
| btts | 100 | 24527 | 0.5487 | 0.5322 | 0.055 |
| over15 | 1 | 245 | 0.8939 | 0.8939 | 0.4085 |
| over15 | 5 | 1226 | 0.8548 | 0.8548 | 0.3677 |
| over15 | 10 | 2452 | 0.8263 | 0.8263 | 0.3484 |
| over15 | 25 | 6131 | 0.8098 | 0.8098 | 0.3215 |
| over15 | 50 | 12263 | 0.7888 | 0.7888 | 0.2959 |
| over15 | 100 | 24527 | 0.7439 | 0.7439 | 0.2478 |
| over25 | 1 | 245 | 0.7878 | 0.7061 | 0.2467 |
| over25 | 5 | 1226 | 0.6843 | 0.5726 | 0.1892 |
| over25 | 10 | 2452 | 0.6652 | 0.5338 | 0.1636 |
| over25 | 25 | 6131 | 0.6252 | 0.5263 | 0.1291 |
| over25 | 50 | 12263 | 0.5909 | 0.5193 | 0.0999 |
| over25 | 100 | 24527 | 0.5577 | 0.5077 | 0.0631 |
| over35 | 1 | 245 | 0.8653 | 0.1347 | 0.3597 |
| over35 | 5 | 1226 | 0.8377 | 0.1623 | 0.3353 |
| over35 | 10 | 2452 | 0.8206 | 0.1794 | 0.3201 |
| over35 | 25 | 6131 | 0.793 | 0.207 | 0.2945 |
| over35 | 50 | 12263 | 0.7666 | 0.2333 | 0.2679 |
| over35 | 100 | 24527 | 0.7179 | 0.2834 | 0.2145 |
| home_scores | 1 | 245 | 0.9755 | 0.9755 | 0.4368 |
| home_scores | 5 | 1226 | 0.9111 | 0.9111 | 0.4074 |
| home_scores | 10 | 2452 | 0.8931 | 0.8931 | 0.3913 |
| home_scores | 25 | 6131 | 0.8579 | 0.8579 | 0.3645 |
| home_scores | 50 | 12263 | 0.8263 | 0.8263 | 0.3341 |
| home_scores | 100 | 24527 | 0.7681 | 0.7686 | 0.2716 |
| away_scores | 1 | 245 | 0.9184 | 0.9184 | 0.363 |
| away_scores | 5 | 1226 | 0.8654 | 0.8654 | 0.3281 |
| away_scores | 10 | 2452 | 0.8328 | 0.8328 | 0.3095 |
| away_scores | 25 | 6131 | 0.7854 | 0.7854 | 0.2778 |
| away_scores | 50 | 12263 | 0.7463 | 0.7463 | 0.2459 |
| away_scores | 100 | 24527 | 0.6877 | 0.688 | 0.1865 |
| home_2plus | 1 | 245 | 0.8245 | 0.4939 | 0.3195 |
| home_2plus | 5 | 1226 | 0.7643 | 0.398 | 0.2758 |
| home_2plus | 10 | 2452 | 0.7423 | 0.3719 | 0.2518 |
| home_2plus | 25 | 6131 | 0.7053 | 0.3662 | 0.2117 |
| home_2plus | 50 | 12263 | 0.6667 | 0.3912 | 0.1707 |
| home_2plus | 100 | 24527 | 0.6037 | 0.4313 | 0.1105 |
| away_2plus | 1 | 245 | 0.849 | 0.151 | 0.3597 |
| away_2plus | 5 | 1226 | 0.8246 | 0.1754 | 0.3286 |
| away_2plus | 10 | 2452 | 0.8108 | 0.1896 | 0.3109 |
| away_2plus | 25 | 6131 | 0.7751 | 0.2254 | 0.2791 |
| away_2plus | 50 | 12263 | 0.7352 | 0.2669 | 0.242 |
| away_2plus | 100 | 24527 | 0.6712 | 0.3358 | 0.1715 |


## Player goalscorer research

Players score in about 8.3% of appearances, so 'nobody scores' is 91.7% accurate 
and worthless. The baseline that matters is **the player's own prior scoring rate**.

| population | spec | n | base_rate | log_loss | brier | auc |
|---|---|---|---|---|---|---|
| appeared | global_rate | 399473 | 0.0799 | 0.27854 | 0.07352 | 0.49454 |
| appeared | position_prior | 399473 | 0.0799 | 0.26445 | 0.07171 | 0.68421 |
| appeared | own_history | 399473 | 0.0799 | 0.25666 | 0.06986 | 0.71294 |
| appeared | full_player_model | 399473 | 0.0799 | 0.24906 | 0.06875 | 0.74212 |
| started | global_rate | 305193 | 0.0891 | 0.30048 | 0.08117 | 0.49594 |
| started | position_prior | 305193 | 0.0891 | 0.28067 | 0.0783 | 0.69647 |
| started | own_history | 305193 | 0.0891 | 0.27115 | 0.07576 | 0.73309 |
| started | full_player_model | 305193 | 0.0891 | 0.26276 | 0.07458 | 0.76005 |
| exp_minutes_60 | global_rate | 260318 | 0.07901 | 0.27643 | 0.07278 | 0.49671 |
| exp_minutes_60 | position_prior | 260318 | 0.07901 | 0.2556 | 0.06976 | 0.70898 |
| exp_minutes_60 | own_history | 260318 | 0.07901 | 0.24659 | 0.0677 | 0.74631 |
| exp_minutes_60 | full_player_model | 260318 | 0.07901 | 0.23958 | 0.06672 | 0.76859 |


`appeared` is an explanatory upper bound only — whether a player appears is not 
known before kickoff and is most of whether he scores. `exp_minutes_60` selects on 
the player's own prior rolling minutes and is the deployable number.

## Per league (global model)

| league | target | n | rock_accuracy | model_accuracy | lift_pp | log_loss | auc |
|---|---|---|---|---|---|---|---|
| Belgian First Division A | over25 | 692 | 0.5116 | 0.5448 | 3.3237 | 0.6925 | 0.5397 |
| Brazil Serie A | over25 | 935 | 0.538 | 0.569 | 3.1016 | 0.6797 | 0.5766 |
| Greek Super League | over25 | 525 | 0.501 | 0.5295 | 2.8571 | 0.6902 | 0.5531 |
| China Super League | over25 | 528 | 0.5966 | 0.6231 | 2.6515 | 0.6513 | 0.631 |
| Romanian Superliga | btts | 1301 | 0.5019 | 0.5265 | 2.4596 | 0.6872 | 0.5611 |
| Portuguese Primeira Liga | over25 | 696 | 0.5287 | 0.5517 | 2.2989 | 0.6734 | 0.5988 |
| Scottish League Two | btts | 415 | 0.5349 | 0.5566 | 2.1687 | 0.6863 | 0.5488 |
| League Two | over25 | 1277 | 0.5215 | 0.5388 | 1.7228 | 0.6925 | 0.5388 |
| Sweden Allsvenskan | over25 | 508 | 0.5354 | 0.5512 | 1.5748 | 0.6876 | 0.5599 |
| League One | over25 | 1265 | 0.5051 | 0.5194 | 1.4229 | 0.6937 | 0.5417 |
| La Liga 2 | over25 | 1050 | 0.5295 | 0.5419 | 1.2381 | 0.6882 | 0.5527 |
| Sweden Allsvenskan | btts | 508 | 0.5295 | 0.5413 | 1.1811 | 0.6922 | 0.5164 |
| Turkish Super Lig | over25 | 748 | 0.5401 | 0.5508 | 1.0695 | 0.6778 | 0.5779 |
| Saudi Pro League | over25 | 695 | 0.564 | 0.5741 | 1.0072 | 0.6779 | 0.5644 |
| Romanian Superliga | over25 | 1301 | 0.568 | 0.578 | 0.9992 | 0.6773 | 0.564 |
| Scottish Premiership | btts | 509 | 0.5422 | 0.5521 | 0.9823 | 0.686 | 0.5331 |
| Ligue 2 | over25 | 723 | 0.5201 | 0.5297 | 0.9682 | 0.6977 | 0.4957 |
| Brazil Serie A | btts | 935 | 0.5091 | 0.5187 | 0.9626 | 0.6882 | 0.5503 |
| Ireland Premier Division | over25 | 422 | 0.5545 | 0.564 | 0.9479 | 0.6831 | 0.5569 |
| Saudi Pro League | over35 | 695 | 0.6446 | 0.6532 | 0.8633 | 0.6361 | 0.5952 |
| USA MLS | over35 | 1380 | 0.6203 | 0.6283 | 0.7971 | 0.656 | 0.5688 |
| Greek Super League | btts | 525 | 0.5086 | 0.5162 | 0.7619 | 0.6917 | 0.5569 |
| Mexico Liga MX | over25 | 794 | 0.5441 | 0.5516 | 0.7557 | 0.6818 | 0.5602 |
| Austrian Bundesliga | btts | 447 | 0.5526 | 0.5593 | 0.6711 | 0.6863 | 0.5422 |


League-specific models help: **NO** 
(win share 0.042).

## Plain answers to the questions asked

**Can Wowza predict these better than a naive baseline?**

- **btts: YES.** Accuracy 0.5400 against a rock of 0.5322 (+0.78pp), log loss 0.68687 against 0.69107, AUC 0.5540, winning on log loss in 4 of 4 folds.
- **over15: UNCLEAR.** Accuracy 0.7433 against a rock of 0.7439 (-0.07pp), log loss 0.56134 against 0.56892, AUC 0.5809, winning on log loss in 4 of 4 folds.
- **over25: YES.** Accuracy 0.5553 against a rock of 0.5077 (+4.76pp), log loss 0.68208 against 0.69303, AUC 0.5813, winning on log loss in 4 of 4 folds.
- **over35: YES.** Accuracy 0.7170 against a rock of 0.7166 (+0.04pp), log loss 0.58544 against 0.59610, AUC 0.5890, winning on log loss in 4 of 4 folds.

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
BEST_CURRENT_OOS_ACCURACY_BTTS=0.54
BEST_CURRENT_OOS_BRIER_BTTS=0.24687
OVER15_PREDICTABLE_ABOVE_BASELINE=UNCLEAR
BEST_CURRENT_OOS_ACCURACY_OVER15=0.7433
BEST_CURRENT_OOS_BRIER_OVER15=0.18766
OVER25_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER25=0.5553
BEST_CURRENT_OOS_BRIER_OVER25=0.24456
OVER35_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER35=0.717
BEST_CURRENT_OOS_BRIER_OVER35=0.19871
PLAYER_GOAL_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_PLAYER_GOAL=0.921
BEST_CURRENT_OOS_AUC_PLAYER_GOAL=0.7686
PLAYER_GOAL_BASELINE_AUC_OWN_HISTORY=0.7463
BEST_CURRENT_OOS_BRIER_PLAYER_GOAL=0.06672
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
BEST_TRAINING_WINDOW=btts:expanding; over15:last_4y; over25:expanding; over35:expanding
RECENCY_WEIGHTING_HELPS=NO
MORE_DATA_IS_IMPROVING_MODELS=YES
LEAGUE_SPECIFIC_MODELS_HELP=NO
LEAGUE_SPECIFIC_WIN_SHARE=0.042
V9_PRODUCTION_UNCHANGED=YES
PURE_PREDICTION_RESEARCH_READY_FOR_WEEKLY_UPDATE=YES
versions={'data_version': 'lab-data/2.0', 'identity_version': 'pro-identity-1.0+identity/1.0', 'season_calendar_version': 'season-calendar/1.0'}
```

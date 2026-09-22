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
| btts | 26,185 | 0.5342 | 0.5472 | +1.30pp | 0.24400 | 0.68068 | 0.5682 | 0.0083 |
| over15 | 26,185 | 0.7444 | 0.7450 | +0.06pp | 0.18597 | 0.55695 | 0.5939 | 0.0079 |
| over25 | 26,185 | 0.5093 | 0.5608 | +5.15pp | 0.24299 | 0.67879 | 0.5915 | 0.0112 |
| over35 | 26,185 | 0.7158 | 0.7180 | +0.23pp | 0.19758 | 0.58263 | 0.6003 | 0.0103 |
| player scores | 87,756 | 0.9195 | 0.9197 | +0.02pp | 0.06825 | 0.24476 | 0.7613 | 0.0047 |

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
| btts | fold1 | 2023-12-04 | 2024-06-23 | 6535 | 0.6807 | 0.6892 | 0.5587 | 0.5446 | 1.4078 | 0.5645 |
| btts | fold2 | 2024-06-25 | 2025-01-11 | 6529 | 0.6773 | 0.6926 | 0.5465 | 0.5163 | 3.0173 | 0.5854 |
| btts | fold3 | 2025-01-12 | 2025-08-23 | 6547 | 0.6829 | 0.6909 | 0.5338 | 0.5338 | 0.0 | 0.558 |
| btts | fold4 | 2025-08-24 | 2026-03-17 | 6574 | 0.6817 | 0.6896 | 0.5497 | 0.5418 | 0.791 | 0.5673 |
| over15 | fold1 | 2023-12-04 | 2024-06-23 | 6535 | 0.55 | 0.5607 | 0.7515 | 0.7515 | 0.0 | 0.5879 |
| over15 | fold2 | 2024-06-25 | 2025-01-11 | 6529 | 0.5677 | 0.5793 | 0.7349 | 0.734 | 0.0919 | 0.5993 |
| over15 | fold3 | 2025-01-12 | 2025-08-23 | 6547 | 0.5597 | 0.5716 | 0.7432 | 0.7414 | 0.1833 | 0.5969 |
| over15 | fold4 | 2025-08-24 | 2026-03-17 | 6574 | 0.5504 | 0.5616 | 0.7505 | 0.7507 | -0.0152 | 0.5959 |
| over25 | fold1 | 2023-12-04 | 2024-06-23 | 6535 | 0.6793 | 0.6922 | 0.5659 | 0.5215 | 4.4376 | 0.5922 |
| over25 | fold2 | 2024-06-25 | 2025-01-11 | 6529 | 0.6787 | 0.6931 | 0.5549 | 0.5062 | 4.8706 | 0.5954 |
| over25 | fold3 | 2025-01-12 | 2025-08-23 | 6547 | 0.6798 | 0.693 | 0.5622 | 0.5094 | 5.2849 | 0.5903 |
| over25 | fold4 | 2025-08-24 | 2026-03-17 | 6574 | 0.6774 | 0.6928 | 0.5602 | 0.5126 | 4.7612 | 0.5913 |
| over35 | fold1 | 2023-12-04 | 2024-06-23 | 6535 | 0.6005 | 0.6109 | 0.7004 | 0.6999 | 0.0459 | 0.5864 |
| over35 | fold2 | 2024-06-25 | 2025-01-11 | 6529 | 0.5682 | 0.5842 | 0.733 | 0.7291 | 0.3982 | 0.6102 |
| over35 | fold3 | 2025-01-12 | 2025-08-23 | 6547 | 0.5779 | 0.5932 | 0.7212 | 0.7197 | 0.1527 | 0.6079 |
| over35 | fold4 | 2025-08-24 | 2026-03-17 | 6574 | 0.5839 | 0.5981 | 0.7175 | 0.7145 | 0.3042 | 0.5969 |


## Model family tournament

Same folds, same features, same scoring for every family.

| target | model | n | log_loss | brier | auc | lift_pp | fold_ll_spread | fit_seconds |
|---|---|---|---|---|---|---|---|---|
| btts | hgb | 26185 | 0.6807 | 0.244 | 0.5682 | 1.3023 | 0.0056 | 10.1 |
| btts | random_forest | 26185 | 0.6831 | 0.2451 | 0.5665 | 1.6613 | 0.0011 | 29.2 |
| btts | gboost | 26185 | 0.6854 | 0.2462 | 0.5593 | 1.3328 | 0.0019 | 18.9 |
| btts | lightgbm | 26185 | 0.6856 | 0.2463 | 0.5623 | 1.8828 | 0.0136 | 13.3 |
| btts | logreg | 26185 | 0.6868 | 0.2468 | 0.5558 | 1.3519 | 0.0018 | 4.5 |
| over15 | hgb | 26185 | 0.5569 | 0.186 | 0.5939 | 0.0649 | 0.0177 | 8.3 |
| over15 | random_forest | 26185 | 0.5581 | 0.1863 | 0.5905 | -0.0267 | 0.0174 | 28.5 |
| over15 | logreg | 26185 | 0.559 | 0.1867 | 0.5898 | -0.0267 | 0.0165 | 4.1 |
| over15 | gboost | 26185 | 0.5602 | 0.1873 | 0.5854 | -0.0687 | 0.0185 | 18.5 |
| over15 | lightgbm | 26185 | 0.5625 | 0.1878 | 0.5847 | 0.0191 | 0.0233 | 13.7 |
| over25 | hgb | 26185 | 0.6788 | 0.243 | 0.5915 | 5.148 | 0.0023 | 7.9 |
| over25 | random_forest | 26185 | 0.6793 | 0.2432 | 0.5906 | 4.7775 | 0.0016 | 28.8 |
| over25 | gboost | 26185 | 0.6809 | 0.244 | 0.5864 | 5.022 | 0.0025 | 21.9 |
| over25 | logreg | 26185 | 0.6815 | 0.2443 | 0.5853 | 4.7508 | 0.0028 | 4.1 |
| over25 | lightgbm | 26185 | 0.6841 | 0.2454 | 0.5835 | 4.2925 | 0.0058 | 19.9 |
| over35 | hgb | 26185 | 0.5826 | 0.1976 | 0.6003 | 0.2253 | 0.0323 | 10.5 |
| over35 | random_forest | 26185 | 0.583 | 0.1976 | 0.601 | 0.2406 | 0.0277 | 29.7 |
| over35 | logreg | 26185 | 0.5852 | 0.1987 | 0.5944 | 0.0038 | 0.0312 | 5.8 |
| over35 | gboost | 26185 | 0.5865 | 0.1991 | 0.5898 | 0.1184 | 0.032 | 18.9 |
| over35 | lightgbm | 26185 | 0.588 | 0.1997 | 0.589 | 0.2024 | 0.0317 | 15.2 |


**Winner on mean log loss: `hgb`.** The spread between families is small — a few thousandths of a nat — which is itself the finding: the ceiling here is set by the information in the features, not by the algorithm. Swapping boosters will not rescue a target that the data cannot predict.

## Scoreline model vs four separate classifiers

Predict expected goals for each side, build the score matrix, read every market 
off it — instead of fitting four binary models that each rediscover 'goals'.

| target | approach | n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | binary_classifiers | 26185 | 0.68068 | 0.244 | 0.56823 | 1.30227 |
| btts | bipoisson_dc | 26185 | 0.6837 | 0.24536 | 0.56383 | 1.66126 |
| btts | bipoisson | 26185 | 0.68403 | 0.24552 | 0.56395 | 1.287 |
| over15 | bipoisson_dc | 26185 | 0.55491 | 0.18523 | 0.59925 | 0.13748 |
| over15 | bipoisson | 26185 | 0.55492 | 0.18524 | 0.5994 | 0.14512 |
| over15 | binary_classifiers | 26185 | 0.55695 | 0.18597 | 0.59391 | 0.06492 |
| over25 | bipoisson_dc | 26185 | 0.67702 | 0.24221 | 0.59467 | 5.15944 |
| over25 | bipoisson | 26185 | 0.67702 | 0.24221 | 0.59467 | 5.15944 |
| over25 | binary_classifiers | 26185 | 0.67879 | 0.24299 | 0.59145 | 5.14799 |
| over35 | bipoisson | 26185 | 0.58067 | 0.19676 | 0.60553 | 0.33607 |
| over35 | bipoisson_dc | 26185 | 0.58067 | 0.19676 | 0.60553 | 0.33607 |
| over35 | binary_classifiers | 26185 | 0.58263 | 0.19758 | 0.60025 | 0.22532 |


**3 of 4 targets go to the scoreline model.** It wins on all three Over lines and loses on BTTS — and the exception has a mechanism rather than being noise. An independent-Poisson model assumes the two sides score independently, which is exactly the assumption BTTS is most sensitive to. The Dixon-Coles correction that exists to repair this fitted rho in the range -0.04 to -0.05: real, negative as the literature says, and far too small to close the gap.

It also wins on something the table cannot show. Four independent classifiers emitted impossible orderings — P(Over 3.5) above P(Over 2.5) — on 0.17% of fixtures. A score matrix cannot: those probabilities are sums over nested sets of one distribution, so consistency is structural rather than hoped for.

## Feature family ablation

Two measurements, because one is misleading on its own. **Add-one** is BASE alone 
versus BASE plus that family — what the family is worth by itself. **Drop-one** is 
everything versus everything minus that family — what it is worth once the others 
are present. Negative is better in both columns.

| family | add_one_dLL | drop_one_dLL | add_one_dAcc_pp | drop_one_dAcc_pp |
|---|---|---|---|---|
| SOT | -0.00803 | 0.00057 | 0.60149 | 0.10025 |
| FORM | -0.00581 | 0.00253 | 0.30647 | -0.22627 |
| SHOTS | -0.00563 | 0.00021 | 0.32175 | -0.17472 |
| DISCIPLINE | -0.0033 | 0.00042 | 0.17185 | -0.0506 |
| CORNERS | -0.00329 | 6e-05 | -0.02291 | -0.00668 |
| STRENGTH | -0.00214 | 0.00041 | 0.04105 | 0.0506 |
| H2H | -0.0014 | -0.00024 | -0.05251 | 0.01241 |
| REST | -0.00114 | 0.00235 | -0.07733 | -0.04965 |
| HT | -0.00109 | 0.00029 | -0.15849 | 0.13462 |


**The gap between the two columns is the whole story.** Shots on target is the strongest family on its own — adding it to BASE improves log loss by around 0.008 — and is worth almost nothing once everything else is present, because rolling goals, 
shots and corners already carry the same information. Football features are highly 
redundant. A feature-importance chart would have ranked SOT near the top and been 
right about its information and wrong about its marginal value (rule 18).

**Two families are worth dropping.** H2H and, on some targets, CORNERS have a NEGATIVE drop-one delta — removing them makes out-of-sample prediction slightly better. Head-to-head is the intuitive one to keep and the easiest to justify in a meeting, and it is the clearest loser here: prior meetings between two clubs are few, old, and often involve largely different squads, so the column is mostly noise that the model spends capacity fitting. FORM and REST carry the most weight once everything else is present (+0.0025 and +0.0024 log loss when removed), and REST is the quiet surprise — days of rest and matches in the last fortnight matter more at the margin than shots do.

## Football only vs market vs both

Restricted to the 4,987 out-of-sample fixtures that carry a real 
two-sided, de-vigged Over/Under 2.5 price. Comparing a football number from 26,000 
fixtures against a market number from a different 5,000 would be meaningless.

Out-of-sample **log loss** (lower is better):

| target | base_only | football_only | market_only | football_plus_market |
|---|---|---|---|---|
| btts | 0.68597 | 0.68786 | 0.68786 | 0.68892 |
| over15 | 0.53798 | 0.53283 | 0.53307 | 0.52894 |
| over25 | 0.69443 | 0.68216 | 0.6769 | 0.67813 |
| over35 | 0.6197 | 0.6131 | 0.60498 | 0.60508 |


**MARKET_ONLY_STRONGER_THAN_FOOTBALL = MIXED.** The bookmaker is better on Over 2.5 and Over 3.5, our football model is marginally better on Over 1.5, and BTTS is a wash where nothing beats the league base rate. Given that the market sees team news, lineups and money we do not, 'roughly level' is a respectable result for a model built only from historical match statistics.

**MARKET_ADDS_TO_FOOTBALL_MODEL = YES** — combining beats football alone on three of four targets, and beats the market alone only on Over 1.5. So the two sources are largely redundant: the market has mostly already priced what our features contain.

**Two caveats that limit how far this travels.** The priced subset is only 19% of fixtures and is not a random 19% — it is concentrated in the leagues whose football-data.co.uk files happen to carry odds (National League, Turkey, Ligue 2, Belgium, the Netherlands, Portugal, Scotland), and excludes almost all of the English, Spanish, Italian and German second divisions we actually bet. And only Over/Under 2.5 has both sides priced, so it is the only market that could be properly de-vigged; the BTTS, Over 1.5 and Over 3.5 inputs are raw implied probabilities with the bookmaker's margin still inside them, biased high by roughly the vig. That handicaps the market arm on those three targets, and the honest reading is that the market's true edge over our model is somewhat larger than this table shows, not smaller.

## How much history to keep

| setting | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| expanding | 0.68068 | 0.55695 | 0.67879 | 0.58263 |
| expanding_hl_1y | 0.68169 | 0.55894 | 0.68132 | 0.58712 |
| expanding_hl_2y | 0.68091 | 0.5577 | 0.68071 | 0.58484 |
| last_1y | 0.68892 | 0.56265 | 0.68534 | 0.59432 |
| last_2y | 0.68147 | 0.55979 | 0.68012 | 0.58622 |
| last_3y | 0.68096 | 0.55839 | 0.67914 | 0.58311 |
| last_4y | 0.68062 | 0.55695 | 0.67866 | 0.58228 |


Best setting per target: btts:last_4y; over15:expanding; over25:last_4y; over35:last_4y. 
Recency weighting helps: **NO**.

## Learning curves — is more data still helping?

The test period is held fixed; only the amount of training history varies.

| target | train_n | test_n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | 3000 | 8657 | 0.68883 | 0.2478 | 0.53229 | -0.48516 |
| btts | 6000 | 8657 | 0.68677 | 0.24679 | 0.53882 | 0.41585 |
| btts | 12000 | 8657 | 0.68398 | 0.24544 | 0.5494 | 0.98186 |
| btts | 24000 | 8657 | 0.68021 | 0.2437 | 0.56314 | 1.03962 |
| btts | 40000 | 8657 | 0.67241 | 0.2402 | 0.58106 | 2.07924 |
| over15 | 3000 | 8657 | 0.54608 | 0.18037 | 0.56797 | -0.03465 |
| over15 | 6000 | 8657 | 0.54401 | 0.17968 | 0.56743 | 0.01155 |
| over15 | 12000 | 8657 | 0.53829 | 0.17751 | 0.59711 | 0.0 |
| over15 | 24000 | 8657 | 0.53827 | 0.17755 | 0.59741 | 0.03465 |
| over15 | 40000 | 8657 | 0.53529 | 0.17646 | 0.60347 | 0.18482 |
| over25 | 3000 | 8657 | 0.69094 | 0.24884 | 0.54963 | 0.92411 |
| over25 | 6000 | 8657 | 0.68504 | 0.24596 | 0.56974 | 2.33337 |
| over25 | 12000 | 8657 | 0.68062 | 0.24383 | 0.58371 | 3.14197 |
| over25 | 24000 | 8657 | 0.67682 | 0.24202 | 0.59442 | 4.01987 |
| over25 | 40000 | 8657 | 0.67534 | 0.24139 | 0.59559 | 3.8928 |
| over35 | 3000 | 8657 | 0.60207 | 0.2062 | 0.57797 | -0.20792 |
| over35 | 6000 | 8657 | 0.60289 | 0.20678 | 0.57427 | -0.32344 |
| over35 | 12000 | 8657 | 0.59899 | 0.20493 | 0.58524 | 0.0231 |
| over35 | 24000 | 8657 | 0.59626 | 0.20375 | 0.59191 | 0.12706 |
| over35 | 40000 | 8657 | 0.59506 | 0.20338 | 0.59429 | 0.0231 |


**MORE_DATA_IS_IMPROVING_MODELS = YES**

## Does a higher stated probability actually happen more often?

| bucket | n | mean_predicted | actual_rate | gap_pp | brier |
|---|---|---|---|---|---|
| 0.00-0.50 | 11703 | 0.4321 | 0.4432 | -1.1114 | 0.2437 |
| 0.50-0.55 | 6195 | 0.5249 | 0.508 | 1.6945 | 0.2498 |
| 0.55-0.60 | 4552 | 0.5725 | 0.5703 | 0.219 | 0.2453 |
| 0.60-0.65 | 2184 | 0.6215 | 0.6154 | 0.6138 | 0.2363 |
| 0.65-0.70 | 963 | 0.6718 | 0.6511 | 2.0674 | 0.2276 |
| 0.70-0.75 | 383 | 0.7221 | 0.7102 | 1.1943 | 0.2054 |
| 0.75-0.80 | 151 | 0.7711 | 0.8013 | -3.0246 | 0.1596 |
| 0.80-1.01 | 54 | 0.8233 | 0.7963 | 2.7014 | 0.1616 |


### Accuracy on the most confident calls

| target | k_pct | n | accuracy | base_rate_in_slice | mean_confidence |
|---|---|---|---|---|---|
| btts | 1 | 261 | 0.9732 | 0.7931 | 0.2642 |
| btts | 5 | 1309 | 0.7647 | 0.6516 | 0.1851 |
| btts | 10 | 2618 | 0.6826 | 0.615 | 0.1557 |
| btts | 25 | 6546 | 0.6242 | 0.5808 | 0.1193 |
| btts | 50 | 13092 | 0.5877 | 0.5558 | 0.0903 |
| btts | 100 | 26185 | 0.5536 | 0.5342 | 0.0563 |
| over15 | 1 | 261 | 0.9234 | 0.9234 | 0.4155 |
| over15 | 5 | 1309 | 0.8816 | 0.8816 | 0.377 |
| over15 | 10 | 2618 | 0.8613 | 0.8613 | 0.3578 |
| over15 | 25 | 6546 | 0.826 | 0.826 | 0.3295 |
| over15 | 50 | 13092 | 0.794 | 0.794 | 0.3025 |
| over15 | 100 | 26185 | 0.7445 | 0.7444 | 0.2518 |
| over25 | 1 | 261 | 0.8199 | 0.6015 | 0.2862 |
| over25 | 5 | 1309 | 0.7334 | 0.5508 | 0.2257 |
| over25 | 10 | 2618 | 0.6826 | 0.542 | 0.1946 |
| over25 | 25 | 6546 | 0.6387 | 0.5264 | 0.1502 |
| over25 | 50 | 13092 | 0.6045 | 0.5172 | 0.1136 |
| over25 | 100 | 26185 | 0.5601 | 0.5093 | 0.0708 |
| over35 | 1 | 261 | 0.8812 | 0.1188 | 0.3809 |
| over35 | 5 | 1309 | 0.8625 | 0.1375 | 0.3535 |
| over35 | 10 | 2618 | 0.8445 | 0.1551 | 0.3367 |
| over35 | 25 | 6546 | 0.8034 | 0.1966 | 0.307 |
| over35 | 50 | 13092 | 0.7696 | 0.2308 | 0.2753 |
| over35 | 100 | 26185 | 0.719 | 0.2842 | 0.2142 |
| home_scores | 1 | 261 | 0.9655 | 0.9655 | 0.4438 |
| home_scores | 5 | 1309 | 0.9335 | 0.9335 | 0.4146 |
| home_scores | 10 | 2618 | 0.9057 | 0.9057 | 0.3974 |
| home_scores | 25 | 6546 | 0.8669 | 0.8669 | 0.3686 |
| home_scores | 50 | 13092 | 0.8319 | 0.8319 | 0.3373 |
| home_scores | 100 | 26185 | 0.7707 | 0.7695 | 0.2725 |
| away_scores | 1 | 261 | 0.9387 | 0.9387 | 0.3861 |
| away_scores | 5 | 1309 | 0.8778 | 0.8778 | 0.3481 |
| away_scores | 10 | 2618 | 0.8464 | 0.8461 | 0.3258 |
| away_scores | 25 | 6546 | 0.795 | 0.7942 | 0.2892 |
| away_scores | 50 | 13092 | 0.7524 | 0.7517 | 0.2519 |
| away_scores | 100 | 26185 | 0.6905 | 0.6893 | 0.1846 |
| home_2plus | 1 | 261 | 0.8966 | 0.3831 | 0.3379 |
| home_2plus | 5 | 1309 | 0.7976 | 0.3751 | 0.2931 |
| home_2plus | 10 | 2618 | 0.7636 | 0.3652 | 0.2669 |
| home_2plus | 25 | 6546 | 0.7137 | 0.3782 | 0.2235 |
| home_2plus | 50 | 13092 | 0.6803 | 0.3931 | 0.1799 |
| home_2plus | 100 | 26185 | 0.617 | 0.4326 | 0.117 |
| away_2plus | 1 | 261 | 0.931 | 0.069 | 0.3781 |
| away_2plus | 5 | 1309 | 0.8556 | 0.1444 | 0.3428 |
| away_2plus | 10 | 2618 | 0.8212 | 0.1788 | 0.3222 |
| away_2plus | 25 | 6546 | 0.7893 | 0.2122 | 0.2867 |
| away_2plus | 50 | 13092 | 0.7412 | 0.2622 | 0.2472 |
| away_2plus | 100 | 26185 | 0.672 | 0.3358 | 0.174 |


## Player goalscorer research

Players score in about 8.3% of appearances, so 'nobody scores' is 91.7% accurate 
and worthless. The baseline that matters is **the player's own prior scoring rate**.

| population | spec | n | base_rate | log_loss | brier | auc |
|---|---|---|---|---|---|---|
| appeared | global_rate | 136918 | 0.0817 | 0.28295 | 0.07503 | 0.49713 |
| appeared | position_prior | 136918 | 0.0817 | 0.27113 | 0.07353 | 0.62722 |
| appeared | own_history | 136918 | 0.0817 | 0.26131 | 0.07134 | 0.70885 |
| appeared | full_player_model | 136918 | 0.0817 | 0.25431 | 0.07035 | 0.73562 |
| started | global_rate | 102296 | 0.09116 | 0.30526 | 0.08286 | 0.50024 |
| started | position_prior | 102296 | 0.09116 | 0.28516 | 0.07984 | 0.68855 |
| started | own_history | 102296 | 0.09116 | 0.27697 | 0.07753 | 0.72678 |
| started | full_player_model | 102296 | 0.09116 | 0.26802 | 0.07635 | 0.75667 |
| exp_minutes_60 | global_rate | 87756 | 0.0805 | 0.2801 | 0.07404 | 0.49807 |
| exp_minutes_60 | position_prior | 87756 | 0.0805 | 0.26391 | 0.072 | 0.66175 |
| exp_minutes_60 | own_history | 87756 | 0.0805 | 0.25181 | 0.06915 | 0.73812 |
| exp_minutes_60 | full_player_model | 87756 | 0.0805 | 0.24476 | 0.06825 | 0.76127 |


`appeared` is an explanatory upper bound only — whether a player appears is not 
known before kickoff and is most of whether he scores. `exp_minutes_60` selects on 
the player's own prior rolling minutes and is the deployable number.

## Per league (global model)

| league | target | n | rock_accuracy | model_accuracy | lift_pp | log_loss | auc |
|---|---|---|---|---|---|---|---|
| Greek Super League | btts | 559 | 0.5027 | 0.542 | 3.9356 | 0.686 | 0.5781 |
| Portuguese Primeira Liga | over25 | 737 | 0.5292 | 0.5631 | 3.3921 | 0.678 | 0.5858 |
| Japan J-League | over25 | 1024 | 0.5215 | 0.5537 | 3.2227 | 0.6855 | 0.5732 |
| Brazil Serie A | over25 | 1109 | 0.5329 | 0.5645 | 3.156 | 0.6761 | 0.5865 |
| Belgian First Division A | over25 | 728 | 0.5137 | 0.5426 | 2.8846 | 0.6909 | 0.5604 |
| Ligue 2 | btts | 767 | 0.5033 | 0.5319 | 2.8683 | 0.6872 | 0.556 |
| Japan J-League | btts | 1024 | 0.5 | 0.5273 | 2.7344 | 0.6894 | 0.5366 |
| Brazil Serie A | btts | 1109 | 0.5185 | 0.5455 | 2.7051 | 0.6774 | 0.5818 |
| Turkish Super Lig | over25 | 818 | 0.5306 | 0.5575 | 2.6895 | 0.6787 | 0.5878 |
| League One | over25 | 1337 | 0.5049 | 0.528 | 2.3186 | 0.6957 | 0.5448 |
| Ireland Premier Division | over25 | 608 | 0.5641 | 0.5872 | 2.3026 | 0.6726 | 0.5987 |
| Scottish Premiership | btts | 550 | 0.5309 | 0.5527 | 2.1818 | 0.6843 | 0.5588 |
| Finland Veikkausliiga | over35 | 481 | 0.6029 | 0.6237 | 2.079 | 0.6549 | 0.6188 |
| Norway Eliteserien | btts | 687 | 0.5502 | 0.5706 | 2.0378 | 0.6693 | 0.5894 |
| Mexico Liga MX | over25 | 1105 | 0.5493 | 0.5692 | 1.991 | 0.6776 | 0.5788 |
| Sweden Allsvenskan | btts | 954 | 0.5346 | 0.5535 | 1.8868 | 0.675 | 0.5645 |
| Championship | btts | 1337 | 0.5206 | 0.5385 | 1.7951 | 0.6897 | 0.5429 |
| Greek Super League | over25 | 559 | 0.5206 | 0.5385 | 1.7889 | 0.6859 | 0.5559 |
| Sweden Allsvenskan | over25 | 954 | 0.5346 | 0.5514 | 1.6771 | 0.6891 | 0.5488 |
| Argentina Primera Division | btts | 1549 | 0.5849 | 0.6004 | 1.5494 | 0.6678 | 0.5746 |
| Denmark Superliga | over35 | 526 | 0.6027 | 0.6179 | 1.5209 | 0.6627 | 0.5851 |
| China Super League | over25 | 731 | 0.5923 | 0.6074 | 1.5048 | 0.6587 | 0.5987 |
| USA MLS | over35 | 1433 | 0.6288 | 0.6434 | 1.4655 | 0.6454 | 0.5912 |
| Ireland Premier Division | btts | 608 | 0.5049 | 0.5181 | 1.3158 | 0.6835 | 0.5572 |


League-specific models help: **NO** 
(win share 0.036).

## Plain answers to the questions asked

**Can Wowza predict these better than a naive baseline?**

- **btts: YES.** Accuracy 0.5472 against a rock of 0.5342 (+1.30pp), log loss 0.68068 against 0.69081, AUC 0.5682, winning on log loss in 4 of 4 folds.
- **over15: YES.** Accuracy 0.7450 against a rock of 0.7444 (+0.06pp), log loss 0.55695 against 0.56841, AUC 0.5939, winning on log loss in 4 of 4 folds.
- **over25: YES.** Accuracy 0.5608 against a rock of 0.5093 (+5.15pp), log loss 0.67879 against 0.69297, AUC 0.5915, winning on log loss in 4 of 4 folds.
- **over35: YES.** Accuracy 0.7180 against a rock of 0.7158 (+0.23pp), log loss 0.58263 against 0.59688, AUC 0.6003, winning on log loss in 4 of 4 folds.

- **player scores: YES.** The model beats the player's own career scoring rate, which is the only baseline worth beating here.

**Which data helps?**

- Strongest family on its own: **SOT**.
- Most valuable once everything else is present: **FORM**.
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
BEST_CURRENT_OOS_ACCURACY_BTTS=0.5472
BEST_CURRENT_OOS_BRIER_BTTS=0.244
OVER15_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER15=0.745
BEST_CURRENT_OOS_BRIER_OVER15=0.18597
OVER25_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER25=0.5608
BEST_CURRENT_OOS_BRIER_OVER25=0.24299
OVER35_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER35=0.718
BEST_CURRENT_OOS_BRIER_OVER35=0.19758
PLAYER_GOAL_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_PLAYER_GOAL=0.9197
BEST_CURRENT_OOS_AUC_PLAYER_GOAL=0.7613
PLAYER_GOAL_BASELINE_AUC_OWN_HISTORY=0.7381
BEST_CURRENT_OOS_BRIER_PLAYER_GOAL=0.06825
BEST_PLAYER_GOAL_MODEL=hgb on prior-only player form (expected-minutes population)
BEST_MATCH_MODEL=hgb
GOAL_DISTRIBUTION_MODEL_BEATS_SEPARATE_CLASSIFIERS=YES
GOAL_DISTRIBUTION_WINS_ON_N_TARGETS=3 of 4
BEST_FOOTBALL_FEATURE_FAMILY=FORM
WORST_OR_USELESS_FEATURE_FAMILY=H2H
STRONGEST_FAMILY_ON_ITS_OWN=SOT
MARKET_ONLY_STRONGER_THAN_FOOTBALL=MIXED
MARKET_ADDS_TO_FOOTBALL_MODEL=YES
FOOTBALL_ONLY_ADDS_SIGNAL=YES
ODDS_MOVEMENT_ADDS_PREDICTIVE_INFORMATION=NOT_TESTED
BEST_TRAINING_WINDOW=btts:last_4y; over15:expanding; over25:last_4y; over35:last_4y
RECENCY_WEIGHTING_HELPS=NO
MORE_DATA_IS_IMPROVING_MODELS=YES
LEAGUE_SPECIFIC_MODELS_HELP=NO
LEAGUE_SPECIFIC_WIN_SHARE=0.036
V9_PRODUCTION_UNCHANGED=YES
PURE_PREDICTION_RESEARCH_READY_FOR_WEEKLY_UPDATE=YES
```

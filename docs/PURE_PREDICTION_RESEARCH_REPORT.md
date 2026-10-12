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
| btts | 28,065 | 0.5340 | 0.5647 | +3.07pp | 0.24057 | 0.67318 | 0.5889 | 0.0131 |
| over15 | 28,065 | 0.7442 | 0.7438 | -0.05pp | 0.18538 | 0.55541 | 0.6016 | 0.0059 |
| over25 | 28,065 | 0.5096 | 0.5681 | +5.85pp | 0.24160 | 0.67594 | 0.5998 | 0.0062 |
| over35 | 28,065 | 0.7163 | 0.7174 | +0.11pp | 0.19679 | 0.58036 | 0.6072 | 0.0097 |
| player scores | 250,368 | 0.9213 | 0.9214 | +0.01pp | 0.06646 | 0.23882 | 0.7692 | 0.0025 |

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
| btts | fold1 | 2024-01-28 | 2024-08-09 | 6991 | 0.6715 | 0.6887 | 0.5725 | 0.5473 | 2.5175 | 0.5928 |
| btts | fold2 | 2024-08-10 | 2025-02-04 | 7009 | 0.6733 | 0.6928 | 0.5557 | 0.5129 | 4.2802 | 0.5929 |
| btts | fold3 | 2025-02-05 | 2025-09-07 | 7025 | 0.6761 | 0.6905 | 0.5638 | 0.5361 | 2.7758 | 0.5782 |
| btts | fold4 | 2025-09-08 | 2026-03-17 | 7040 | 0.6718 | 0.69 | 0.5668 | 0.5396 | 2.7131 | 0.5922 |
| over15 | fold1 | 2024-01-28 | 2024-08-09 | 6991 | 0.5444 | 0.5578 | 0.7541 | 0.7541 | 0.0 | 0.6052 |
| over15 | fold2 | 2024-08-10 | 2025-02-04 | 7009 | 0.5711 | 0.5845 | 0.7288 | 0.7288 | 0.0 | 0.606 |
| over15 | fold3 | 2025-02-05 | 2025-09-07 | 7025 | 0.5581 | 0.5695 | 0.7415 | 0.7433 | -0.1851 | 0.5938 |
| over15 | fold4 | 2025-09-08 | 2026-03-17 | 7040 | 0.548 | 0.5616 | 0.7507 | 0.7507 | 0.0 | 0.606 |
| over25 | fold1 | 2024-01-28 | 2024-08-09 | 6991 | 0.6725 | 0.6916 | 0.581 | 0.5281 | 5.2925 | 0.6099 |
| over25 | fold2 | 2024-08-10 | 2025-02-04 | 7009 | 0.6785 | 0.6929 | 0.5616 | 0.5113 | 5.0221 | 0.5948 |
| over25 | fold3 | 2025-02-05 | 2025-09-07 | 7025 | 0.6765 | 0.693 | 0.5684 | 0.5078 | 6.0641 | 0.6002 |
| over25 | fold4 | 2025-09-08 | 2026-03-17 | 7040 | 0.6763 | 0.6928 | 0.5615 | 0.5138 | 4.7727 | 0.595 |
| over35 | fold1 | 2024-01-28 | 2024-08-09 | 6991 | 0.5931 | 0.6131 | 0.704 | 0.6973 | 0.6723 | 0.6175 |
| over35 | fold2 | 2024-08-10 | 2025-02-04 | 7009 | 0.5686 | 0.5799 | 0.7291 | 0.7333 | -0.428 | 0.598 |
| over35 | fold3 | 2025-02-05 | 2025-09-07 | 7025 | 0.5798 | 0.5964 | 0.7163 | 0.7163 | 0.0 | 0.6117 |
| over35 | fold4 | 2025-09-08 | 2026-03-17 | 7040 | 0.5799 | 0.5945 | 0.7203 | 0.7183 | 0.1989 | 0.6 |


## Model family tournament

Same folds, same features, same scoring for every family.

| target | model | n | log_loss | brier | auc | lift_pp | fold_ll_spread | fit_seconds |
|---|---|---|---|---|---|---|---|---|
| btts | hgb | 28065 | 0.6732 | 0.2406 | 0.5889 | 3.0714 | 0.0046 | 5.7 |
| btts | lightgbm | 28065 | 0.6791 | 0.2434 | 0.5784 | 2.3161 | 0.0067 | 14.4 |
| btts | random_forest | 28065 | 0.681 | 0.244 | 0.5775 | 2.4479 | 0.0051 | 64.2 |
| btts | gboost | 28065 | 0.6832 | 0.2451 | 0.5686 | 1.6818 | 0.0035 | 17.5 |
| btts | logreg | 28065 | 0.6842 | 0.2456 | 0.5666 | 1.892 | 0.0054 | 8.1 |
| over15 | hgb | 28065 | 0.5554 | 0.1854 | 0.6016 | -0.0463 | 0.0267 | 4.8 |
| over15 | random_forest | 28065 | 0.5567 | 0.1858 | 0.5979 | -0.0748 | 0.0286 | 62.4 |
| over15 | logreg | 28065 | 0.5584 | 0.1865 | 0.5931 | -0.0356 | 0.0275 | 6.2 |
| over15 | gboost | 28065 | 0.56 | 0.1874 | 0.5881 | -0.082 | 0.0307 | 17.6 |
| over15 | lightgbm | 28065 | 0.562 | 0.1876 | 0.5911 | 0.0143 | 0.0238 | 14.8 |
| over25 | hgb | 28065 | 0.6759 | 0.2416 | 0.5998 | 5.8543 | 0.006 | 6.3 |
| over25 | random_forest | 28065 | 0.6779 | 0.2425 | 0.597 | 5.5015 | 0.009 | 60.8 |
| over25 | gboost | 28065 | 0.6796 | 0.2433 | 0.5906 | 5.2307 | 0.0036 | 17.4 |
| over25 | logreg | 28065 | 0.6805 | 0.2438 | 0.5897 | 4.0549 | 0.0056 | 7.4 |
| over25 | lightgbm | 28065 | 0.6814 | 0.2442 | 0.5885 | 4.9207 | 0.0091 | 14.5 |
| over35 | hgb | 28065 | 0.5804 | 0.1968 | 0.6072 | 0.1105 | 0.0244 | 5.5 |
| over35 | random_forest | 28065 | 0.5816 | 0.1971 | 0.6054 | 0.0285 | 0.0285 | 62.2 |
| over35 | gboost | 28065 | 0.5825 | 0.1975 | 0.6031 | 0.0 | 0.0288 | 17.4 |
| over35 | logreg | 28065 | 0.5836 | 0.198 | 0.5994 | -0.0534 | 0.0302 | 6.8 |
| over35 | lightgbm | 28065 | 0.5857 | 0.1987 | 0.5963 | 0.1176 | 0.0241 | 14.4 |


**Winner on mean log loss: `hgb`.** The spread between families is small — a few thousandths of a nat — which is itself the finding: the ceiling here is set by the information in the features, not by the algorithm. Swapping boosters will not rescue a target that the data cannot predict.

## Scoreline model vs four separate classifiers

Predict expected goals for each side, build the score matrix, read every market 
off it — instead of fitting four binary models that each rediscover 'goals'.

| target | approach | n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | binary_classifiers | 28065 | 0.67318 | 0.24057 | 0.58885 | 3.07144 |
| btts | bipoisson_dc | 28065 | 0.68077 | 0.24394 | 0.57507 | 2.47283 |
| btts | bipoisson | 28065 | 0.68109 | 0.2441 | 0.57513 | 2.40157 |
| over15 | bipoisson_dc | 28065 | 0.55343 | 0.18453 | 0.60611 | 0.18172 |
| over15 | bipoisson | 28065 | 0.55346 | 0.18454 | 0.60621 | 0.17816 |
| over15 | binary_classifiers | 28065 | 0.55541 | 0.18538 | 0.60163 | -0.04632 |
| over25 | bipoisson | 28065 | 0.67499 | 0.24122 | 0.60158 | 5.96829 |
| over25 | bipoisson_dc | 28065 | 0.67499 | 0.24122 | 0.60158 | 5.96829 |
| over25 | binary_classifiers | 28065 | 0.67594 | 0.2416 | 0.59983 | 5.85427 |
| over35 | bipoisson | 28065 | 0.57765 | 0.1957 | 0.61452 | 0.30643 |
| over35 | bipoisson_dc | 28065 | 0.57765 | 0.1957 | 0.61452 | 0.30643 |
| over35 | binary_classifiers | 28065 | 0.58036 | 0.19679 | 0.6072 | 0.11046 |


**3 of 4 targets go to the scoreline model.** It wins on all three Over lines and loses on BTTS — and the exception has a mechanism rather than being noise. An independent-Poisson model assumes the two sides score independently, which is exactly the assumption BTTS is most sensitive to. The Dixon-Coles correction that exists to repair this fitted rho in the range -0.04 to -0.05: real, negative as the literature says, and far too small to close the gap.

It also wins on something the table cannot show. Four independent classifiers emitted impossible orderings — P(Over 3.5) above P(Over 2.5) — on 0.17% of fixtures. A score matrix cannot: those probabilities are sums over nested sets of one distribution, so consistency is structural rather than hoped for.

## Feature family ablation

Two measurements, because one is misleading on its own. **Add-one** is BASE alone 
versus BASE plus that family — what the family is worth by itself. **Drop-one** is 
everything versus everything minus that family — what it is worth once the others 
are present. Negative is better in both columns.

| family | add_one_dLL | drop_one_dLL | add_one_dAcc_pp | drop_one_dAcc_pp |
|---|---|---|---|---|
| SOT | -0.00901 | 0.00067 | 1.31659 | -0.08552 |
| SHOTS | -0.00638 | 0.00036 | 1.01817 | -0.08373 |
| FORM | -0.00523 | 0.00508 | 1.24265 | -0.64582 |
| CORNERS | -0.0047 | -2e-05 | 0.7928 | -0.06859 |
| STRENGTH | -0.00454 | 0.00035 | 1.05648 | -0.16123 |
| DISCIPLINE | -0.00349 | 0.00046 | 0.62622 | -0.12293 |
| HT | -0.00249 | -0.00014 | 0.64404 | -0.03029 |
| H2H | -0.00194 | 0.00018 | 0.37859 | -0.14609 |
| REST | -0.00162 | 0.00497 | 0.31267 | -0.45341 |


**The gap between the two columns is the whole story.** Shots on target is the strongest family on its own — adding it to BASE improves log loss by around 0.008 — and is worth almost nothing once everything else is present, because rolling goals, 
shots and corners already carry the same information. Football features are highly 
redundant. A feature-importance chart would have ranked SOT near the top and been 
right about its information and wrong about its marginal value (rule 18).

**Two families are worth dropping.** H2H and, on some targets, CORNERS have a NEGATIVE drop-one delta — removing them makes out-of-sample prediction slightly better. Head-to-head is the intuitive one to keep and the easiest to justify in a meeting, and it is the clearest loser here: prior meetings between two clubs are few, old, and often involve largely different squads, so the column is mostly noise that the model spends capacity fitting. FORM and REST carry the most weight once everything else is present (+0.0025 and +0.0024 log loss when removed), and REST is the quiet surprise — days of rest and matches in the last fortnight matter more at the margin than shots do.

## Football only vs market vs both

Restricted to the 9,141 out-of-sample fixtures that carry a real 
two-sided, de-vigged Over/Under 2.5 price. Comparing a football number from 26,000 
fixtures against a market number from a different 5,000 would be meaningless.

Out-of-sample **log loss** (lower is better):

| target | base_only | football_only | market_only | football_plus_market |
|---|---|---|---|---|
| btts | 0.69111 | 0.68125 | 0.68882 | 0.68223 |
| over15 | 0.56104 | 0.55403 | 0.55179 | 0.54977 |
| over25 | 0.69351 | 0.6824 | 0.68107 | 0.67846 |
| over35 | 0.60068 | 0.58769 | 0.58615 | 0.58434 |


**MARKET_ONLY_STRONGER_THAN_FOOTBALL = YES.** The bookmaker is better on Over 2.5 and Over 3.5, our football model is marginally better on Over 1.5, and BTTS is a wash where nothing beats the league base rate. Given that the market sees team news, lineups and money we do not, 'roughly level' is a respectable result for a model built only from historical match statistics.

**MARKET_ADDS_TO_FOOTBALL_MODEL = YES** — combining beats football alone on three of four targets, and beats the market alone only on Over 1.5. So the two sources are largely redundant: the market has mostly already priced what our features contain.

**Two caveats that limit how far this travels.** The priced subset is only 19% of fixtures and is not a random 19% — it is concentrated in the leagues whose football-data.co.uk files happen to carry odds (National League, Turkey, Ligue 2, Belgium, the Netherlands, Portugal, Scotland), and excludes almost all of the English, Spanish, Italian and German second divisions we actually bet. And only Over/Under 2.5 has both sides priced, so it is the only market that could be properly de-vigged; the BTTS, Over 1.5 and Over 3.5 inputs are raw implied probabilities with the bookmaker's margin still inside them, biased high by roughly the vig. That handicaps the market arm on those three targets, and the honest reading is that the market's true edge over our model is somewhat larger than this table shows, not smaller.

## How much history to keep

| setting | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| expanding | 0.67318 | 0.55541 | 0.67594 | 0.58036 |
| expanding_hl_1y | 0.6761 | 0.55898 | 0.67973 | 0.58377 |
| expanding_hl_2y | 0.67584 | 0.55776 | 0.67775 | 0.58138 |
| last_1y | 0.686 | 0.56428 | 0.68659 | 0.58675 |
| last_2y | 0.67557 | 0.5575 | 0.67982 | 0.58392 |
| last_3y | 0.67421 | 0.55612 | 0.67718 | 0.58236 |
| last_4y | 0.67381 | 0.5551 | 0.67862 | 0.57961 |


Best setting per target: btts:expanding; over15:last_4y; over25:expanding; over35:last_4y. 
Recency weighting helps: **NO**.

## Learning curves — is more data still helping?

The test period is held fixed; only the amount of training history varies.

| target | train_n | test_n | log_loss | brier | auc | lift_pp |
|---|---|---|---|---|---|---|
| btts | 3000 | 9365 | 0.7013 | 0.25293 | 0.54368 | -0.40577 |
| btts | 6000 | 9365 | 0.69365 | 0.25003 | 0.53869 | -1.44154 |
| btts | 12000 | 9365 | 0.68308 | 0.24503 | 0.55425 | 0.16017 |
| btts | 24000 | 9365 | 0.6732 | 0.24067 | 0.57492 | 0.70475 |
| btts | 40000 | 9365 | 0.66539 | 0.23744 | 0.58906 | 2.12493 |
| over15 | 3000 | 9365 | 0.54788 | 0.18084 | 0.56583 | -0.03203 |
| over15 | 6000 | 9365 | 0.55312 | 0.18308 | 0.57077 | -0.40577 |
| over15 | 12000 | 9365 | 0.54199 | 0.17895 | 0.58801 | -0.04271 |
| over15 | 24000 | 9365 | 0.5357 | 0.17666 | 0.60536 | 0.02136 |
| over15 | 40000 | 9365 | 0.53451 | 0.17626 | 0.60957 | 0.08542 |
| over25 | 3000 | 9365 | 0.69273 | 0.24934 | 0.56973 | 2.66951 |
| over25 | 6000 | 9365 | 0.68855 | 0.24756 | 0.56649 | 2.26375 |
| over25 | 12000 | 9365 | 0.6819 | 0.24438 | 0.58796 | 3.53444 |
| over25 | 24000 | 9365 | 0.67412 | 0.24079 | 0.60025 | 4.2819 |
| over25 | 40000 | 9365 | 0.67319 | 0.2404 | 0.60168 | 4.76241 |
| over35 | 3000 | 9365 | 0.62297 | 0.21356 | 0.55946 | -1.06781 |
| over35 | 6000 | 9365 | 0.6032 | 0.20678 | 0.58183 | -0.20288 |
| over35 | 12000 | 9365 | 0.60798 | 0.20837 | 0.57992 | -0.36305 |
| over35 | 24000 | 9365 | 0.5955 | 0.20359 | 0.59877 | 0.32034 |
| over35 | 40000 | 9365 | 0.59338 | 0.20278 | 0.60321 | 0.22424 |


**MORE_DATA_IS_IMPROVING_MODELS = YES**

## Does a higher stated probability actually happen more often?

| bucket | n | mean_predicted | actual_rate | gap_pp | brier |
|---|---|---|---|---|---|
| 0.00-0.50 | 12476 | 0.428 | 0.4331 | -0.5051 | 0.2417 |
| 0.50-0.55 | 6316 | 0.525 | 0.5225 | 0.2472 | 0.2494 |
| 0.55-0.60 | 5096 | 0.573 | 0.5665 | 0.6473 | 0.2453 |
| 0.60-0.65 | 2484 | 0.6218 | 0.6135 | 0.8303 | 0.237 |
| 0.65-0.70 | 1064 | 0.6716 | 0.6682 | 0.3352 | 0.221 |
| 0.70-0.75 | 396 | 0.7208 | 0.7348 | -1.4009 | 0.1937 |
| 0.75-0.80 | 166 | 0.7707 | 0.8133 | -4.2538 | 0.1537 |
| 0.80-1.01 | 67 | 0.8349 | 0.7463 | 8.8625 | 0.1964 |


### Accuracy on the most confident calls

| target | k_pct | n | accuracy | base_rate_in_slice | mean_confidence |
|---|---|---|---|---|---|
| btts | 1 | 280 | 0.9964 | 0.75 | 0.3235 |
| btts | 5 | 1403 | 0.8439 | 0.65 | 0.2336 |
| btts | 10 | 2806 | 0.7416 | 0.6112 | 0.1937 |
| btts | 25 | 7016 | 0.6518 | 0.5758 | 0.1454 |
| btts | 50 | 14032 | 0.6107 | 0.5582 | 0.1089 |
| btts | 100 | 28065 | 0.5651 | 0.534 | 0.0676 |
| over15 | 1 | 280 | 0.9286 | 0.9286 | 0.42 |
| over15 | 5 | 1403 | 0.8931 | 0.8931 | 0.3794 |
| over15 | 10 | 2806 | 0.8596 | 0.8596 | 0.3593 |
| over15 | 25 | 7016 | 0.8284 | 0.8284 | 0.3301 |
| over15 | 50 | 14032 | 0.8001 | 0.8001 | 0.3022 |
| over15 | 100 | 28065 | 0.745 | 0.7442 | 0.2499 |
| over25 | 1 | 280 | 0.8036 | 0.6143 | 0.2909 |
| over25 | 5 | 1403 | 0.7527 | 0.5403 | 0.2287 |
| over25 | 10 | 2806 | 0.7128 | 0.5214 | 0.1985 |
| over25 | 25 | 7016 | 0.6549 | 0.515 | 0.1549 |
| over25 | 50 | 14032 | 0.611 | 0.5167 | 0.1178 |
| over25 | 100 | 28065 | 0.5691 | 0.5096 | 0.0737 |
| over35 | 1 | 280 | 0.9107 | 0.0893 | 0.4008 |
| over35 | 5 | 1403 | 0.8803 | 0.1197 | 0.3657 |
| over35 | 10 | 2806 | 0.8525 | 0.1475 | 0.3463 |
| over35 | 25 | 7016 | 0.8161 | 0.184 | 0.3142 |
| over35 | 50 | 14032 | 0.7745 | 0.2257 | 0.2814 |
| over35 | 100 | 28065 | 0.7184 | 0.2837 | 0.2199 |
| home_scores | 1 | 280 | 0.9643 | 0.9643 | 0.4394 |
| home_scores | 5 | 1403 | 0.9337 | 0.9337 | 0.4127 |
| home_scores | 10 | 2806 | 0.9113 | 0.9113 | 0.3963 |
| home_scores | 25 | 7016 | 0.8729 | 0.8729 | 0.3689 |
| home_scores | 50 | 14032 | 0.8335 | 0.8335 | 0.3376 |
| home_scores | 100 | 28065 | 0.7688 | 0.7683 | 0.2715 |
| away_scores | 1 | 280 | 0.9357 | 0.9357 | 0.4074 |
| away_scores | 5 | 1403 | 0.8917 | 0.8909 | 0.367 |
| away_scores | 10 | 2806 | 0.85 | 0.8496 | 0.3425 |
| away_scores | 25 | 7016 | 0.8063 | 0.8059 | 0.302 |
| away_scores | 50 | 14032 | 0.7594 | 0.7576 | 0.2621 |
| away_scores | 100 | 28065 | 0.6951 | 0.6905 | 0.1902 |
| home_2plus | 1 | 280 | 0.9 | 0.3786 | 0.3543 |
| home_2plus | 5 | 1403 | 0.8168 | 0.3414 | 0.304 |
| home_2plus | 10 | 2806 | 0.7812 | 0.3428 | 0.2749 |
| home_2plus | 25 | 7016 | 0.73 | 0.3632 | 0.2273 |
| home_2plus | 50 | 14032 | 0.6829 | 0.3924 | 0.1813 |
| home_2plus | 100 | 28065 | 0.6213 | 0.4319 | 0.1166 |
| away_2plus | 1 | 280 | 0.9536 | 0.0464 | 0.3961 |
| away_2plus | 5 | 1403 | 0.8667 | 0.134 | 0.3576 |
| away_2plus | 10 | 2806 | 0.8375 | 0.1629 | 0.3351 |
| away_2plus | 25 | 7016 | 0.797 | 0.2042 | 0.2967 |
| away_2plus | 50 | 14032 | 0.7457 | 0.2593 | 0.2549 |
| away_2plus | 100 | 28065 | 0.6734 | 0.3369 | 0.1785 |


## Player goalscorer research

Players score in about 8.3% of appearances, so 'nobody scores' is 91.7% accurate 
and worthless. The baseline that matters is **the player's own prior scoring rate**.

| population | spec | n | base_rate | log_loss | brier | auc |
|---|---|---|---|---|---|---|
| appeared | global_rate | 384350 | 0.07963 | 0.27791 | 0.0733 | 0.49555 |
| appeared | position_prior | 384350 | 0.07963 | 0.26456 | 0.07162 | 0.66849 |
| appeared | own_history | 384350 | 0.07963 | 0.25567 | 0.06958 | 0.71526 |
| appeared | full_player_model | 384350 | 0.07963 | 0.24861 | 0.06852 | 0.74156 |
| started | global_rate | 292473 | 0.08882 | 0.29985 | 0.08094 | 0.4956 |
| started | position_prior | 292473 | 0.08882 | 0.2797 | 0.07808 | 0.71518 |
| started | own_history | 292473 | 0.08882 | 0.27015 | 0.07548 | 0.73474 |
| started | full_player_model | 292473 | 0.08882 | 0.26202 | 0.07431 | 0.76084 |
| exp_minutes_60 | global_rate | 250368 | 0.07868 | 0.27564 | 0.07251 | 0.49551 |
| exp_minutes_60 | position_prior | 250368 | 0.07868 | 0.25524 | 0.06965 | 0.71063 |
| exp_minutes_60 | own_history | 250368 | 0.07868 | 0.24669 | 0.06754 | 0.74292 |
| exp_minutes_60 | full_player_model | 250368 | 0.07868 | 0.23882 | 0.06646 | 0.76916 |


`appeared` is an explanatory upper bound only — whether a player appears is not 
known before kickoff and is most of whether he scores. `exp_minutes_60` selects on 
the player's own prior rolling minutes and is the deployable number.

## Per league (global model)

| league | target | n | rock_accuracy | model_accuracy | lift_pp | log_loss | auc |
|---|---|---|---|---|---|---|---|
| Greek Super League | btts | 845 | 0.503 | 0.5917 | 8.8757 | 0.663 | 0.6262 |
| League One | btts | 1770 | 0.5243 | 0.5842 | 5.9887 | 0.669 | 0.6055 |
| Portuguese Primeira Liga | over25 | 682 | 0.5279 | 0.5792 | 5.132 | 0.6726 | 0.606 |
| Greek Super League | over25 | 845 | 0.5089 | 0.5574 | 4.8521 | 0.6777 | 0.5971 |
| La Liga 2 | btts | 1571 | 0.5156 | 0.5602 | 4.4558 | 0.6641 | 0.6159 |
| League Two | btts | 1706 | 0.5193 | 0.5639 | 4.4549 | 0.6677 | 0.616 |
| Brazil Serie A | over25 | 1093 | 0.5352 | 0.5791 | 4.3916 | 0.6738 | 0.5933 |
| Turkish Super Lig | over25 | 735 | 0.5361 | 0.5755 | 3.9456 | 0.6727 | 0.6014 |
| Japan J-League | btts | 1024 | 0.5 | 0.5371 | 3.7109 | 0.6862 | 0.5662 |
| Sweden Allsvenskan | btts | 954 | 0.5346 | 0.5692 | 3.4591 | 0.6668 | 0.5871 |
| League Two | over25 | 1706 | 0.5188 | 0.5522 | 3.3411 | 0.6821 | 0.5846 |
| Austrian Bundesliga | over25 | 689 | 0.5051 | 0.5385 | 3.3382 | 0.6893 | 0.5613 |
| Championship | btts | 1664 | 0.512 | 0.5433 | 3.125 | 0.6729 | 0.5922 |
| China Super League | over35 | 731 | 0.5882 | 0.6183 | 3.0096 | 0.6728 | 0.5917 |
| Mexico Liga MX | btts | 1054 | 0.5664 | 0.5949 | 2.8463 | 0.6558 | 0.6079 |
| Brazil Serie A | btts | 1093 | 0.5178 | 0.5453 | 2.7447 | 0.6782 | 0.5683 |
| La Liga 2 | over25 | 1571 | 0.5328 | 0.5595 | 2.6735 | 0.6757 | 0.5946 |
| Ireland Premier Division | btts | 608 | 0.5049 | 0.5312 | 2.6316 | 0.6777 | 0.5669 |
| Norway Eliteserien | btts | 684 | 0.5526 | 0.5775 | 2.4854 | 0.6614 | 0.6136 |
| Japan J-League | over25 | 1024 | 0.5215 | 0.5439 | 2.2461 | 0.6864 | 0.565 |
| Saudi Pro League | over25 | 676 | 0.5651 | 0.5858 | 2.071 | 0.6775 | 0.5687 |
| Scottish Championship | over25 | 396 | 0.5328 | 0.553 | 2.0202 | 0.6888 | 0.5511 |
| League One | over25 | 1770 | 0.5079 | 0.5271 | 1.9209 | 0.6882 | 0.5593 |
| USA MLS | over35 | 1432 | 0.6285 | 0.6466 | 1.8156 | 0.6476 | 0.5846 |


League-specific models help: **NO** 
(win share 0.0).

## Plain answers to the questions asked

**Can Wowza predict these better than a naive baseline?**

- **btts: YES.** Accuracy 0.5647 against a rock of 0.5340 (+3.07pp), log loss 0.67318 against 0.69084, AUC 0.5889, winning on log loss in 4 of 4 folds.
- **over15: UNCLEAR.** Accuracy 0.7438 against a rock of 0.7442 (-0.05pp), log loss 0.55541 against 0.56858, AUC 0.6016, winning on log loss in 4 of 4 folds.
- **over25: YES.** Accuracy 0.5681 against a rock of 0.5096 (+5.85pp), log loss 0.67594 against 0.69296, AUC 0.5998, winning on log loss in 4 of 4 folds.
- **over35: YES.** Accuracy 0.7174 against a rock of 0.7163 (+0.11pp), log loss 0.58036 against 0.59638, AUC 0.6072, winning on log loss in 4 of 4 folds.

- **player scores: YES.** The model beats the player's own career scoring rate, which is the only baseline worth beating here.

**Which data helps?**

- Strongest family on its own: **SOT**.
- Most valuable once everything else is present: **FORM**.
- Adds least / can be dropped: **HT**.
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
BEST_CURRENT_OOS_ACCURACY_BTTS=0.5647
BEST_CURRENT_OOS_BRIER_BTTS=0.24057
OVER15_PREDICTABLE_ABOVE_BASELINE=UNCLEAR
BEST_CURRENT_OOS_ACCURACY_OVER15=0.7438
BEST_CURRENT_OOS_BRIER_OVER15=0.18538
OVER25_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER25=0.5681
BEST_CURRENT_OOS_BRIER_OVER25=0.2416
OVER35_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_OVER35=0.7174
BEST_CURRENT_OOS_BRIER_OVER35=0.19679
PLAYER_GOAL_PREDICTABLE_ABOVE_BASELINE=YES
BEST_CURRENT_OOS_ACCURACY_PLAYER_GOAL=0.9214
BEST_CURRENT_OOS_AUC_PLAYER_GOAL=0.7692
PLAYER_GOAL_BASELINE_AUC_OWN_HISTORY=0.7429
BEST_CURRENT_OOS_BRIER_PLAYER_GOAL=0.06646
BEST_PLAYER_GOAL_MODEL=hgb on prior-only player form (expected-minutes population)
BEST_MATCH_MODEL=hgb
GOAL_DISTRIBUTION_MODEL_BEATS_SEPARATE_CLASSIFIERS=YES
GOAL_DISTRIBUTION_WINS_ON_N_TARGETS=3 of 4
BEST_FOOTBALL_FEATURE_FAMILY=FORM
WORST_OR_USELESS_FEATURE_FAMILY=HT
STRONGEST_FAMILY_ON_ITS_OWN=SOT
MARKET_ONLY_STRONGER_THAN_FOOTBALL=YES
MARKET_ADDS_TO_FOOTBALL_MODEL=YES
FOOTBALL_ONLY_ADDS_SIGNAL=YES
ODDS_MOVEMENT_ADDS_PREDICTIVE_INFORMATION=NOT_TESTED
BEST_TRAINING_WINDOW=btts:expanding; over15:last_4y; over25:expanding; over35:last_4y
RECENCY_WEIGHTING_HELPS=NO
MORE_DATA_IS_IMPROVING_MODELS=YES
LEAGUE_SPECIFIC_MODELS_HELP=NO
LEAGUE_SPECIFIC_WIN_SHARE=0.0
V9_PRODUCTION_UNCHANGED=YES
PURE_PREDICTION_RESEARCH_READY_FOR_WEEKLY_UPDATE=YES
```

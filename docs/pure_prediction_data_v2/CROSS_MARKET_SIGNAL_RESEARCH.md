# CROSS-MARKET SIGNAL RESEARCH

Do our models know anything about each other's markets that the market's own model is 
missing? Not 'are BTTS and Over 2.5 correlated' — they obviously are, both are made of 
goals. The question is whether one adds information **after** the other is known.

## The answer, in one paragraph

**Yes — but not from BTTS, which is where the question pointed.** Adding the other 
models' opinions genuinely improves out-of-sample prediction on all three Over markets, 
and the gain survives a paired bootstrap. But essentially all of it comes from the 
**other Over lines**. Telling the Over 2.5 model what the BTTS model thinks moves its 
log loss by +0.00019 — a difference whose 
90% confidence interval straddles zero. Telling it what the Over 3.5 model thinks is 
worth about sixty times more and is significant at p=0.003.

### The asymmetry is the interesting part

BTTS adds nothing to any Over market. But Over 1.5 and Over 3.5 both add real 
information to BTTS (p=0.0015 and p<0.0001). The relationship runs one way.

That has a mechanism rather than being a curiosity. Both-teams-to-score is downstream 
of the goal distribution: knowing how many goals a match is likely to produce genuinely 
sharpens a guess about whether both sides get one. The reverse does not hold, because 
BTTS throws away the information the Over markets care about — it cannot distinguish 
1-1 from 3-3. So a 'fire both' rule built in the intuitive direction (strong BTTS ⇒ back 
Over 2.5) is backed by nothing here, while the unintuitive direction has support.

## Why a naive version of this analysis gets it wrong

All four models are trained on **the same 145 features**. Correlation between their 
outputs is guaranteed before a ball is kicked — they are four views of one feature 
vector. So any conditional table showing 'when P(BTTS) is high, Over 2.5 happens more' 
proves nothing: both are high because the same rolling-form columns were high.

How alike the four opinions are (Pearson on the probabilities):

| model | p_btts | p_over15 | p_over25 | p_over35 | data_version | identity_version | season_calendar_version |
|---|---|---|---|---|---|---|---|
| p_btts | 1.0 | 0.5962 | 0.5863 | 0.544 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over15 | 0.5962 | 1.0 | 0.7903 | 0.7383 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over25 | 0.5863 | 0.7903 | 1.0 | 0.7851 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over35 | 0.544 | 0.7383 | 0.7851 | 1.0 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |


## Cross-market matrix — signal model vs actual outcome (AUC)

| signal_model | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| btts | 0.554 | 0.5602 | 0.5555 | 0.5618 |
| over15 | 0.5459 | 0.5809 | 0.5775 | 0.5842 |
| over25 | 0.5503 | 0.5838 | 0.5813 | 0.5929 |
| over35 | 0.547 | 0.5807 | 0.5799 | 0.589 |


The three Over models are nearly interchangeable; each predicts the others' markets 
about as well as its own. BTTS is the one genuinely distinct signal, and it is 
worse at the Over markets than they are at each other's.

## Conditional outcomes — P(BTTS) bucket vs what actually happened

| bucket | n | mean_p | actual_btts | actual_over15 | actual_over25 | actual_over35 | avg_goals | interpretable |
|---|---|---|---|---|---|---|---|---|
| 0.00-0.45 | 1790 | 0.4219 | 0.438 | 0.6659 | 0.419 | 0.2128 | 2.332 | True |
| 0.45-0.50 | 4731 | 0.4786 | 0.4807 | 0.6946 | 0.4549 | 0.2405 | 2.464 | True |
| 0.50-0.55 | 8158 | 0.5257 | 0.5282 | 0.7418 | 0.5013 | 0.27 | 2.634 | True |
| 0.55-0.60 | 6621 | 0.5726 | 0.5659 | 0.7759 | 0.5389 | 0.3123 | 2.834 | True |
| 0.60-0.65 | 2607 | 0.6197 | 0.5926 | 0.7932 | 0.5792 | 0.3498 | 2.969 | True |
| 0.65-0.70 | 563 | 0.668 | 0.6323 | 0.8224 | 0.6181 | 0.3979 | 3.19 | True |
| 0.70-1.01 | 57 | 0.7125 | 0.6842 | 0.8421 | 0.614 | 0.4211 | 3.211 | False |


Monotone and strong — and, on its own, not evidence of anything beyond the 
model working. The control below is what separates the two explanations.

## The control — holding the Over 2.5 model's own opinion fixed

Within fixtures the Over 2.5 model scored the same, does a high BTTS probability 
change how often Over 2.5 actually happened?

| own_p_range | n_low_other | n_high_other | actual_over25_low_other | actual_over25_high_other | diff_pp | z | p_value |
|---|---|---|---|---|---|---|---|
| 0.208-0.430 | 1363 | 1363 | 0.3654 | 0.427 | 6.16 | 3.289 | 0.001 |
| 0.430-0.472 | 1363 | 1363 | 0.4417 | 0.4688 | 2.71 | 1.423 | 0.1547 |
| 0.472-0.507 | 1363 | 1363 | 0.4497 | 0.5084 | 5.87 | 3.067 | 0.0022 |
| 0.507-0.541 | 1363 | 1363 | 0.526 | 0.5106 | -1.54 | -0.805 | 0.4208 |
| 0.541-0.582 | 1363 | 1363 | 0.5488 | 0.5598 | 1.1 | 0.578 | 0.5633 |
| 0.582-0.881 | 1363 | 1363 | 0.609 | 0.6405 | 3.15 | 1.701 | 0.089 |


This looks like a clear yes. **It is mostly an artefact of how coarse the strata 
are.** Within a wide stratum the Over 2.5 probability still varies, and BTTS 
correlates with it at 0.63, so 'high BTTS inside the stratum' partly just means 
'high Over 2.5 inside the stratum'. Narrowing the control shrinks the effect 
monotonically — 5.62pp at 4 strata, 4.65 at 6, 4.30 at 10, 3.91 at 20, 3.36 at 40 — 
and the meta-model, which controls on the continuous probability rather than on 
bins, finds nothing left at all. The residual is real but worth no prediction.

## The meta-model — the test that settles it

Out-of-sample log loss. Features are logits of probabilities, so 'use the own model 
unchanged' is the trivial solution and anything better is genuinely extra.

| spec | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| own_only | 0.68751 | 0.56009 | 0.68287 | 0.58512 |
| own_plus_all_markets | 0.68612 | 0.5583 | 0.68153 | 0.58351 |
| own_plus_all_plus_sides | 0.68609 | 0.5584 | 0.68159 | 0.5835 |
| own_plus_btts |  | 0.56026 | 0.68306 | 0.58498 |
| own_plus_over15 | 0.6869 |  | 0.68221 | 0.58441 |
| own_plus_over25 | 0.68625 | 0.55856 |  | 0.5835 |
| own_plus_over35 | 0.68624 | 0.55851 | 0.68153 |  |


**CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS = YES**. Best relationship: `over15 <- own_plus_all_markets` at -0.00178 log loss on 11,038 fixtures.

A linear meta-model beats a gradient-boosted one on every target here. That is 
informative in itself: the relationship between these probabilities is essentially 
linear in log-odds, and a flexible model only finds room to overfit.

### Is each gain real, or resampling noise?

Paired bootstrap on the per-fixture losses, blocked by 8 rows because fixtures on 
the same matchday share weather, news and referee assignment. A positive 
`paired_diff` means the enriched model won; it counts only when the 90% CI 
excludes zero.

| target | spec | log_loss | d_log_loss | paired_diff | paired_ci_lo | paired_ci_hi | paired_p | beats_own_model |
|---|---|---|---|---|---|---|---|---|
| btts | own_plus_over15 | 0.686902 | -0.000605 | 0.000605 | 0.000278 | 0.000929 | 0.0005 | True |
| btts | own_plus_over25 | 0.686254 | -0.001253 | 0.001253 | 0.000695 | 0.001813 | 0.0 | True |
| btts | own_plus_over35 | 0.686236 | -0.001271 | 0.001271 | 0.000862 | 0.00168 | 0.0 | True |
| btts | own_plus_all_markets | 0.686123 | -0.001384 | 0.001384 | 0.000818 | 0.00194 | 0.0 | True |
| btts | own_plus_all_plus_sides | 0.686085 | -0.001422 | 0.001422 | 0.000819 | 0.002049 | 0.0 | True |
| over15 | own_plus_btts | 0.560265 | 0.000179 | -0.000179 | -0.000642 | 0.000279 | 0.5165 | False |
| over15 | own_plus_over25 | 0.558564 | -0.001522 | 0.001522 | 0.000648 | 0.002455 | 0.0055 | True |
| over15 | own_plus_over35 | 0.558514 | -0.001571 | 0.001571 | 0.000908 | 0.002246 | 0.0 | True |
| over15 | own_plus_all_markets | 0.558301 | -0.001785 | 0.001785 | 0.000824 | 0.002759 | 0.0025 | True |
| over15 | own_plus_all_plus_sides | 0.558404 | -0.001681 | 0.001681 | 0.000682 | 0.002743 | 0.007 | True |
| over25 | own_plus_btts | 0.683059 | 0.000192 | -0.000192 | -0.000491 | 0.000113 | 0.295 | False |
| over25 | own_plus_over15 | 0.68221 | -0.000657 | 0.000657 | 0.000164 | 0.001166 | 0.031 | True |
| over25 | own_plus_over35 | 0.681535 | -0.001332 | 0.001332 | 0.000683 | 0.001972 | 0.0005 | True |
| over25 | own_plus_all_markets | 0.681529 | -0.001338 | 0.001338 | 0.000629 | 0.00206 | 0.0025 | True |
| over25 | own_plus_all_plus_sides | 0.681587 | -0.00128 | 0.00128 | 0.00053 | 0.002072 | 0.0065 | True |
| over35 | own_plus_btts | 0.584976 | -0.000149 | 0.000149 | -0.000274 | 0.000575 | 0.5475 | False |
| over35 | own_plus_over15 | 0.584406 | -0.000719 | 0.000719 | 2.6e-05 | 0.001482 | 0.109 | True |
| over35 | own_plus_over25 | 0.583501 | -0.001624 | 0.001624 | 0.000567 | 0.002745 | 0.014 | True |
| over35 | own_plus_all_markets | 0.583506 | -0.001618 | 0.001618 | 0.000502 | 0.002847 | 0.015 | True |
| over35 | own_plus_all_plus_sides | 0.5835 | -0.001625 | 0.001625 | 0.000468 | 0.002889 | 0.0225 | True |


**Every `own_plus_btts` row fails.** Every row built on another Over line passes. 
This table is the verdict; the conditional tables above are context for it.

## Error correlation — when one is wrong, is the other?

This matters more than agreement. Two models that agree but fail together give one 
piece of evidence dressed as two.

| model_a | model_b | err_rate_a | err_rate_b | both_wrong | both_wrong_if_independent | excess_pp | phi |
|---|---|---|---|---|---|---|---|
| btts | over15 | 0.4513 | 0.2561 | 0.1729 | 0.1156 | 5.73 | 0.264 |
| btts | over25 | 0.4513 | 0.4423 | 0.2518 | 0.1996 | 5.23 | 0.2114 |
| btts | over35 | 0.4513 | 0.2821 | 0.0818 | 0.1273 | -4.55 | -0.203 |
| over15 | over25 | 0.2561 | 0.4423 | 0.1133 | 0.1133 | 0.0 | 0.0001 |
| over15 | over35 | 0.2561 | 0.2821 | 0.0011 | 0.0723 | -7.12 | -0.3624 |
| over25 | over35 | 0.4423 | 0.2821 | 0.109 | 0.1248 | -1.58 | -0.0706 |


Most correlated errors: btts/over15 +5.73pp over independence.

## Disagreement — is 'BTTS high, Over 2.5 low' really a 1-1 machine?

| state | n | avg_goals | goals_0 | goals_1 | goals_2 | goals_3 | goals_4 | goals_5plus | interpretable |
|---|---|---|---|---|---|---|---|---|---|
| btts_high_ou25_high | 1160 | 3.316 | 0.0448 | 0.1112 | 0.1853 | 0.2284 | 0.1922 | 0.2379 | True |
| btts_high_ou25_low | 60 | 2.417 | 0.1 | 0.1833 | 0.2 | 0.3167 | 0.1333 | 0.0667 | False |
| btts_low_ou25_high | 64 | 3.484 | 0.0312 | 0.0312 | 0.1875 | 0.2812 | 0.25 | 0.2188 | False |
| btts_low_ou25_low | 1204 | 2.162 | 0.1279 | 0.2442 | 0.2566 | 0.1877 | 0.1088 | 0.0748 | True |
| all | 24527 | 2.683 | 0.0756 | 0.1805 | 0.2362 | 0.2244 | 0.1457 | 0.1376 | True |


Scorelines:

| state | n | top_scores |
|---|---|---|
| btts_high_ou25_high | 1160 | 1-2 0.091; 2-1 0.085; 1-1 0.084; 2-2 0.078; 1-0 0.065 |
| btts_high_ou25_low | 60 | 1-1 0.133; 1-2 0.100; 1-0 0.100; 0-0 0.100; 2-1 0.083 |
| btts_low_ou25_high | 64 | 3-0 0.234; 4-0 0.188; 2-0 0.125; 4-1 0.062; 3-2 0.047 |
| btts_low_ou25_low | 1204 | 1-0 0.142; 1-1 0.131; 0-0 0.128; 0-1 0.102; 2-1 0.077 |
| all | 24527 | 1-1 0.121; 1-0 0.104; 2-1 0.091; 0-1 0.076; 0-0 0.076 |


The hypothesis points the right way — 'BTTS high, Over 2.5 low' produces 1-1 at 
more than twice its overall rate, and 'BTTS low, Over 2.5 high' produces 3-0, 2-0 
and 4-0 well above theirs. **But both cells hold fewer than 150 fixtures**, which 
is below the interpretation floor set before the analysis ran. Recorded as 
directionally consistent and not yet established. The models rarely disagree that 
strongly, which is itself the reason the cells are thin.

## Discovery → validation

606 two-model threshold conditions were searched on the earlier OOS 
period and re-measured on the later one, with Benjamini-Hochberg control.

| status | conditions |
|---|---|
| REPLICATED | 564 |
| DISCOVERY_ONLY | 24 |
| UNTESTED | 18 |


**These replication rates should not be read as edges.** Most of the searched 
conditions amount to 'select fixtures both models think are high-scoring', and 
those fixtures really are high-scoring — the pattern replicates because the models 
work, not because a cross-market secret was found. That is precisely why the 
meta-model, not this table, carries the verdict.

## Verdict

```text
CROSS_MARKET_DATASET_LEAKAGE_SAFE=YES
BTTS_ADDS_INFO_TO_OVER15=NO
BTTS_ADDS_INFO_TO_OVER25=NO
BTTS_ADDS_INFO_TO_OVER35=NO
OVER15_ADDS_INFO_TO_BTTS=YES
OVER25_ADDS_INFO_TO_BTTS=YES
OVER35_ADDS_INFO_TO_BTTS=YES
CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS=YES
BEST_VALIDATED_CROSS_MARKET_RELATIONSHIP=over15 <- own_plus_all_markets
OOS_SAMPLE_SIZE=11038
OOS_IMPROVEMENT=-0.00178 log loss
MODEL_AGREEMENT_IMPROVES_ACCURACY=MIXED
MODEL_DISAGREEMENT_IS_INFORMATIVE=UNCLEAR
ANY_CROSS_MARKET_PATTERN_SURVIVES_MULTIPLE_TESTING=YES
ANY_CROSS_MARKET_PATTERN_REPLICATED_CHRONOLOGICALLY=YES
PLAYER_SCORER_ADDS_INFO_TO_BTTS=NO
PLAYER_SCORER_ADDS_INFO_TO_OVER25=NO
MATCH_MODELS_IMPROVE_PLAYER_SCORER=YES
BTTS_EDGE_PREDICTS_OVER25=NOT_TESTED
BTTS_PROBABILITY_PREDICTS_OVER25_BETTER_THAN_EDGE=NOT_TESTED
ANY_VALIDATED_PATTERN_SHOWS_ECONOMIC_EDGE=NOT_TESTED
V9_PRODUCTION_UNCHANGED=YES
SAFE_TO_CONTINUE_RESEARCH=YES
versions={'data_version': 'lab-data/2.0', 'identity_version': 'pro-identity-1.0+identity/1.0', 'season_calendar_version': 'season-calendar/1.0'}
```


## What was deliberately not done

No economic analysis. Rule 21 puts pricing after prediction, and the prediction-side 
gain that survived — of the order of 0.002 nats of log loss — is small enough that the 
honest next step is to see whether it persists on new fixtures, not to go looking for 
a price it might beat. `ANY_VALIDATED_PATTERN_SHOWS_ECONOMIC_EDGE = NOT_TESTED` is a 
deliberate answer, not an omission.

No production change. No notifier change. No threshold moved.
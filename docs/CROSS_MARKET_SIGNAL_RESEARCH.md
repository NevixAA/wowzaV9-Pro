# CROSS-MARKET SIGNAL RESEARCH

Do our models know anything about each other's markets that the market's own model is 
missing? Not 'are BTTS and Over 2.5 correlated' — they obviously are, both are made of 
goals. The question is whether one adds information **after** the other is known.

## The answer, in one paragraph

**Yes — but not from BTTS, which is where the question pointed.** Adding the other 
models' opinions genuinely improves out-of-sample prediction on all three Over markets, 
and the gain survives a paired bootstrap. But essentially all of it comes from the 
**other Over lines**. Telling the Over 2.5 model what the BTTS model thinks moves its 
log loss by -0.00002 — a difference whose 
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

| model | p_btts | p_over15 | p_over25 | p_over35 |
|---|---|---|---|---|
| p_btts | 1.0 | 0.6287 | 0.6273 | 0.6068 |
| p_over15 | 0.6287 | 1.0 | 0.7972 | 0.7431 |
| p_over25 | 0.6273 | 0.7972 | 1.0 | 0.8078 |
| p_over35 | 0.6068 | 0.7431 | 0.8078 | 1.0 |


## Cross-market matrix — signal model vs actual outcome (AUC)

| signal_model | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| btts | 0.5682 | 0.5764 | 0.5706 | 0.5734 |
| over15 | 0.5558 | 0.5939 | 0.5896 | 0.5991 |
| over25 | 0.5544 | 0.5945 | 0.5915 | 0.599 |
| over35 | 0.5564 | 0.592 | 0.591 | 0.6003 |


The three Over models are nearly interchangeable; each predicts the others' markets 
about as well as its own. BTTS is the one genuinely distinct signal, and it is 
worse at the Over markets than they are at each other's.

## Conditional outcomes — P(BTTS) bucket vs what actually happened

| bucket | n | mean_p | actual_btts | actual_over15 | actual_over25 | actual_over35 | avg_goals | interpretable |
|---|---|---|---|---|---|---|---|---|
| 0.00-0.45 | 2274 | 0.4078 | 0.4099 | 0.6341 | 0.3764 | 0.179 | 2.189 | True |
| 0.45-0.50 | 5016 | 0.479 | 0.4902 | 0.7055 | 0.4689 | 0.2442 | 2.496 | True |
| 0.50-0.55 | 9002 | 0.5256 | 0.5275 | 0.7414 | 0.4994 | 0.2778 | 2.653 | True |
| 0.55-0.60 | 6617 | 0.572 | 0.5608 | 0.7732 | 0.543 | 0.3075 | 2.828 | True |
| 0.60-0.65 | 2484 | 0.6193 | 0.6091 | 0.8056 | 0.5954 | 0.37 | 3.052 | True |
| 0.65-0.70 | 526 | 0.6683 | 0.6996 | 0.8726 | 0.6521 | 0.4278 | 3.325 | True |
| 0.70-1.01 | 266 | 0.7533 | 0.9586 | 0.9812 | 0.8195 | 0.4887 | 3.737 | True |


Monotone and strong — and, on its own, not evidence of anything beyond the 
model working. The control below is what separates the two explanations.

## The control — holding the Over 2.5 model's own opinion fixed

Within fixtures the Over 2.5 model scored the same, does a high BTTS probability 
change how often Over 2.5 actually happened?

| own_p_range | n_low_other | n_high_other | actual_over25_low_other | actual_over25_high_other | diff_pp | z | p_value |
|---|---|---|---|---|---|---|---|
| 0.152-0.426 | 1455 | 1455 | 0.3354 | 0.4254 | 9.0 | 5.002 | 0.0 |
| 0.426-0.474 | 1455 | 1455 | 0.4495 | 0.4983 | 4.88 | 2.636 | 0.0084 |
| 0.474-0.511 | 1455 | 1455 | 0.5017 | 0.4948 | -0.69 | -0.371 | 0.7108 |
| 0.511-0.546 | 1455 | 1455 | 0.4756 | 0.5381 | 6.25 | 3.374 | 0.0007 |
| 0.546-0.590 | 1455 | 1455 | 0.5711 | 0.5883 | 1.72 | 0.939 | 0.3478 |
| 0.590-0.889 | 1455 | 1455 | 0.6117 | 0.679 | 6.74 | 3.797 | 0.0001 |


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
| own_only | 0.68293 | 0.55528 | 0.67983 | 0.58136 |
| own_plus_all_markets | 0.68268 | 0.55421 | 0.67815 | 0.57931 |
| own_plus_all_plus_sides | 0.68291 | 0.5544 | 0.67789 | 0.57973 |
| own_plus_btts |  | 0.55505 | 0.67981 | 0.58115 |
| own_plus_over15 | 0.68267 |  | 0.67866 | 0.57954 |
| own_plus_over25 | 0.68295 | 0.55458 |  | 0.58 |
| own_plus_over35 | 0.68258 | 0.55437 | 0.67851 |  |


**CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS = YES**. Best relationship: `over35 <- own_plus_all_markets` at -0.00205 log loss on 11,782 fixtures.

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
| btts | own_plus_over15 | 0.682675 | -0.000254 | 0.000254 | 0.000125 | 0.000392 | 0.0015 | True |
| btts | own_plus_over25 | 0.682947 | 1.8e-05 | -1.8e-05 | -6.1e-05 | 2.1e-05 | 0.4725 | False |
| btts | own_plus_over35 | 0.682585 | -0.000344 | 0.000344 | 0.000214 | 0.000477 | 0.0 | True |
| btts | own_plus_all_markets | 0.68268 | -0.000249 | 0.000249 | 3.6e-05 | 0.000474 | 0.064 | True |
| btts | own_plus_all_plus_sides | 0.68291 | -1.9e-05 | 1.9e-05 | -0.000485 | 0.000504 | 0.9465 | False |
| over15 | own_plus_btts | 0.555045 | -0.000238 | 0.000238 | -0.000497 | 0.000922 | 0.562 | False |
| over15 | own_plus_over25 | 0.554584 | -0.0007 | 0.0007 | 0.000121 | 0.001284 | 0.052 | True |
| over15 | own_plus_over35 | 0.55437 | -0.000913 | 0.000913 | 0.000279 | 0.001537 | 0.011 | True |
| over15 | own_plus_all_markets | 0.55421 | -0.001074 | 0.001074 | 0.000235 | 0.001871 | 0.028 | True |
| over15 | own_plus_all_plus_sides | 0.554399 | -0.000885 | 0.000885 | -0.000172 | 0.001848 | 0.1505 | False |
| over25 | own_plus_btts | 0.679811 | -2.2e-05 | 2.2e-05 | -0.000786 | 0.000805 | 0.963 | False |
| over25 | own_plus_over15 | 0.67866 | -0.001172 | 0.001172 | 0.000309 | 0.002061 | 0.033 | True |
| over25 | own_plus_over35 | 0.678514 | -0.001318 | 0.001318 | 0.000567 | 0.002068 | 0.003 | True |
| over25 | own_plus_all_markets | 0.678153 | -0.001679 | 0.001679 | 0.00058 | 0.002816 | 0.015 | True |
| over25 | own_plus_all_plus_sides | 0.677891 | -0.001941 | 0.001941 | 0.000684 | 0.003148 | 0.013 | True |
| over35 | own_plus_btts | 0.58115 | -0.00021 | 0.00021 | -0.000205 | 0.000605 | 0.3885 | False |
| over35 | own_plus_over15 | 0.579543 | -0.001817 | 0.001817 | 0.001032 | 0.002637 | 0.0 | True |
| over35 | own_plus_over25 | 0.580003 | -0.001358 | 0.001358 | 0.000893 | 0.001797 | 0.0 | True |
| over35 | own_plus_all_markets | 0.579311 | -0.002049 | 0.002049 | 0.001238 | 0.002869 | 0.0 | True |
| over35 | own_plus_all_plus_sides | 0.579729 | -0.001631 | 0.001631 | 0.000461 | 0.002751 | 0.0225 | True |


**Every `own_plus_btts` row fails.** Every row built on another Over line passes. 
This table is the verdict; the conditional tables above are context for it.

## Error correlation — when one is wrong, is the other?

This matters more than agreement. Two models that agree but fail together give one 
piece of evidence dressed as two.

| model_a | model_b | err_rate_a | err_rate_b | both_wrong | both_wrong_if_independent | excess_pp | phi |
|---|---|---|---|---|---|---|---|
| btts | over15 | 0.4464 | 0.2555 | 0.1681 | 0.1141 | 5.41 | 0.2494 |
| btts | over25 | 0.4464 | 0.4399 | 0.2576 | 0.1964 | 6.12 | 0.2479 |
| btts | over35 | 0.4464 | 0.281 | 0.0828 | 0.1254 | -4.26 | -0.1907 |
| over15 | over25 | 0.2555 | 0.4399 | 0.1174 | 0.1124 | 0.5 | 0.023 |
| over15 | over35 | 0.2555 | 0.281 | 0.0017 | 0.0718 | -7.01 | -0.3575 |
| over25 | over35 | 0.4399 | 0.281 | 0.1043 | 0.1236 | -1.93 | -0.0866 |


Most correlated errors: btts/over25 +6.12pp over independence.

## Disagreement — is 'BTTS high, Over 2.5 low' really a 1-1 machine?

| state | n | avg_goals | goals_0 | goals_1 | goals_2 | goals_3 | goals_4 | goals_5plus | interpretable |
|---|---|---|---|---|---|---|---|---|---|
| btts_high_ou25_high | 1541 | 3.421 | 0.0357 | 0.0954 | 0.1921 | 0.2304 | 0.1862 | 0.2602 | True |
| btts_high_ou25_low | 78 | 2.423 | 0.0641 | 0.1667 | 0.3333 | 0.2564 | 0.1282 | 0.0513 | False |
| btts_low_ou25_high | 79 | 3.291 | 0.0253 | 0.1392 | 0.1646 | 0.2532 | 0.1899 | 0.2278 | False |
| btts_low_ou25_low | 1672 | 2.046 | 0.1441 | 0.2572 | 0.2578 | 0.1872 | 0.0831 | 0.0706 | True |
| all | 26185 | 2.689 | 0.0754 | 0.1802 | 0.2351 | 0.2251 | 0.1458 | 0.1384 | True |


Scorelines:

| state | n | top_scores |
|---|---|---|
| btts_high_ou25_high | 1541 | 2-1 0.113; 1-1 0.101; 1-2 0.074; 2-2 0.070; 2-0 0.061 |
| btts_high_ou25_low | 78 | 1-1 0.244; 2-1 0.154; 1-0 0.115; 0-0 0.064; 2-2 0.064 |
| btts_low_ou25_high | 79 | 3-0 0.139; 2-0 0.114; 2-1 0.101; 1-0 0.101; 4-0 0.089 |
| btts_low_ou25_low | 1672 | 1-0 0.162; 0-0 0.144; 1-1 0.133; 0-1 0.095; 2-0 0.080 |
| all | 26185 | 1-1 0.121; 1-0 0.103; 2-1 0.092; 0-1 0.077; 0-0 0.075 |


The hypothesis points the right way — 'BTTS high, Over 2.5 low' produces 1-1 at 
more than twice its overall rate, and 'BTTS low, Over 2.5 high' produces 3-0, 2-0 
and 4-0 well above theirs. **But both cells hold fewer than 150 fixtures**, which 
is below the interpretation floor set before the analysis ran. Recorded as 
directionally consistent and not yet established. The models rarely disagree that 
strongly, which is itself the reason the cells are thin.

## Discovery → validation

702 two-model threshold conditions were searched on the earlier OOS 
period and re-measured on the later one, with Benjamini-Hochberg control.

| status | conditions |
|---|---|
| REPLICATED | 624 |
| UNTESTED | 78 |


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
OVER25_ADDS_INFO_TO_BTTS=NO
OVER35_ADDS_INFO_TO_BTTS=YES
CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS=YES
BEST_VALIDATED_CROSS_MARKET_RELATIONSHIP=over35 <- own_plus_all_markets
OOS_SAMPLE_SIZE=11782
OOS_IMPROVEMENT=-0.00205 log loss
MODEL_AGREEMENT_IMPROVES_ACCURACY=NO
MODEL_DISAGREEMENT_IS_INFORMATIVE=UNCLEAR
ANY_CROSS_MARKET_PATTERN_SURVIVES_MULTIPLE_TESTING=YES
ANY_CROSS_MARKET_PATTERN_REPLICATED_CHRONOLOGICALLY=YES
PLAYER_SCORER_ADDS_INFO_TO_BTTS=UNCLEAR
PLAYER_SCORER_ADDS_INFO_TO_OVER25=UNCLEAR
MATCH_MODELS_IMPROVE_PLAYER_SCORER=YES
BTTS_EDGE_PREDICTS_OVER25=NOT_TESTED
BTTS_PROBABILITY_PREDICTS_OVER25_BETTER_THAN_EDGE=NOT_TESTED
ANY_VALIDATED_PATTERN_SHOWS_ECONOMIC_EDGE=NOT_TESTED
V9_PRODUCTION_UNCHANGED=YES
SAFE_TO_CONTINUE_RESEARCH=YES
```


## What was deliberately not done

No economic analysis. Rule 21 puts pricing after prediction, and the prediction-side 
gain that survived — of the order of 0.002 nats of log loss — is small enough that the 
honest next step is to see whether it persists on new fixtures, not to go looking for 
a price it might beat. `ANY_VALIDATED_PATTERN_SHOWS_ECONOMIC_EDGE = NOT_TESTED` is a 
deliberate answer, not an omission.

No production change. No notifier change. No threshold moved.
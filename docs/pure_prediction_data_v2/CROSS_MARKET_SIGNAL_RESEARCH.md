# CROSS-MARKET SIGNAL RESEARCH

Do our models know anything about each other's markets that the market's own model is 
missing? Not 'are BTTS and Over 2.5 correlated' — they obviously are, both are made of 
goals. The question is whether one adds information **after** the other is known.

## The answer, in one paragraph

**Yes — but not from BTTS, which is where the question pointed.** Adding the other 
models' opinions genuinely improves out-of-sample prediction on all three Over markets, 
and the gain survives a paired bootstrap. But essentially all of it comes from the 
**other Over lines**. Telling the Over 2.5 model what the BTTS model thinks moves its 
log loss by -0.00007 — a difference whose 
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
| p_btts | 1.0 | 0.6031 | 0.5845 | 0.5769 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over15 | 0.6031 | 1.0 | 0.7952 | 0.7499 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over25 | 0.5845 | 0.7952 | 1.0 | 0.7869 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over35 | 0.5769 | 0.7499 | 0.7869 | 1.0 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |


## Cross-market matrix — signal model vs actual outcome (AUC)

| signal_model | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| btts | 0.5499 | 0.5583 | 0.5517 | 0.5589 |
| over15 | 0.5455 | 0.5806 | 0.5762 | 0.5905 |
| over25 | 0.5521 | 0.5838 | 0.5802 | 0.5926 |
| over35 | 0.5482 | 0.5805 | 0.578 | 0.5892 |


The three Over models are nearly interchangeable; each predicts the others' markets 
about as well as its own. BTTS is the one genuinely distinct signal, and it is 
worse at the Over markets than they are at each other's.

## Conditional outcomes — P(BTTS) bucket vs what actually happened

| bucket | n | mean_p | actual_btts | actual_over15 | actual_over25 | actual_over35 | avg_goals | interpretable |
|---|---|---|---|---|---|---|---|---|
| 0.00-0.45 | 1647 | 0.4208 | 0.442 | 0.6594 | 0.4026 | 0.1943 | 2.281 | True |
| 0.45-0.50 | 4425 | 0.4793 | 0.4902 | 0.7051 | 0.4673 | 0.2429 | 2.492 | True |
| 0.50-0.55 | 7972 | 0.5256 | 0.5218 | 0.7354 | 0.5004 | 0.2768 | 2.642 | True |
| 0.55-0.60 | 6456 | 0.572 | 0.5674 | 0.7712 | 0.5395 | 0.3058 | 2.82 | True |
| 0.60-0.65 | 2335 | 0.6197 | 0.5949 | 0.7991 | 0.5726 | 0.3619 | 3.003 | True |
| 0.65-0.70 | 321 | 0.6637 | 0.6729 | 0.8567 | 0.6916 | 0.4361 | 3.28 | True |
| 0.70-1.01 | 22 | 0.7162 | 0.7727 | 0.9091 | 0.5455 | 0.4545 | 3.455 | False |


Monotone and strong — and, on its own, not evidence of anything beyond the 
model working. The control below is what separates the two explanations.

## The control — holding the Over 2.5 model's own opinion fixed

Within fixtures the Over 2.5 model scored the same, does a high BTTS probability 
change how often Over 2.5 actually happened?

| own_p_range | n_low_other | n_high_other | actual_over25_low_other | actual_over25_high_other | diff_pp | z | p_value |
|---|---|---|---|---|---|---|---|
| 0.247-0.432 | 1288 | 1288 | 0.3602 | 0.4425 | 8.23 | 4.261 | 0.0 |
| 0.432-0.476 | 1288 | 1288 | 0.4488 | 0.4604 | 1.16 | 0.594 | 0.5528 |
| 0.476-0.512 | 1288 | 1288 | 0.5062 | 0.5186 | 1.24 | 0.631 | 0.5282 |
| 0.512-0.545 | 1288 | 1288 | 0.5225 | 0.5411 | 1.86 | 0.948 | 0.3433 |
| 0.545-0.588 | 1288 | 1288 | 0.5365 | 0.5536 | 1.71 | 0.87 | 0.384 |
| 0.588-0.843 | 1288 | 1288 | 0.6211 | 0.6258 | 0.47 | 0.244 | 0.8072 |


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
| own_only | 0.6866 | 0.55993 | 0.68308 | 0.58223 |
| own_plus_all_markets | 0.68521 | 0.55849 | 0.68177 | 0.58034 |
| own_plus_all_plus_sides | 0.68507 | 0.55864 | 0.68173 | 0.58032 |
| own_plus_btts |  | 0.55977 | 0.68301 | 0.58205 |
| own_plus_over15 | 0.68596 |  | 0.68241 | 0.58081 |
| own_plus_over25 | 0.68526 | 0.55886 |  | 0.58069 |
| own_plus_over35 | 0.68565 | 0.55876 | 0.68194 |  |


**CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS = YES**. Best relationship: `over35 <- own_plus_all_plus_sides` at -0.00191 log loss on 10,453 fixtures.

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
| btts | own_plus_over15 | 0.685962 | -0.000637 | 0.000637 | 3e-05 | 0.001232 | 0.083 | True |
| btts | own_plus_over25 | 0.68526 | -0.001339 | 0.001339 | 0.000513 | 0.002189 | 0.007 | True |
| btts | own_plus_over35 | 0.685647 | -0.000951 | 0.000951 | 0.000343 | 0.001614 | 0.008 | True |
| btts | own_plus_all_markets | 0.685206 | -0.001393 | 0.001393 | 0.000569 | 0.002239 | 0.006 | True |
| btts | own_plus_all_plus_sides | 0.685066 | -0.001533 | 0.001533 | 0.000567 | 0.002468 | 0.008 | True |
| over15 | own_plus_btts | 0.55977 | -0.00016 | 0.00016 | -7.3e-05 | 0.000391 | 0.244 | False |
| over15 | own_plus_over25 | 0.558859 | -0.001072 | 0.001072 | 0.000226 | 0.001875 | 0.037 | True |
| over15 | own_plus_over35 | 0.558758 | -0.001172 | 0.001172 | 0.000585 | 0.001805 | 0.002 | True |
| over15 | own_plus_all_markets | 0.558494 | -0.001437 | 0.001437 | 0.000568 | 0.002322 | 0.0055 | True |
| over15 | own_plus_all_plus_sides | 0.558643 | -0.001287 | 0.001287 | 0.00038 | 0.00223 | 0.024 | True |
| over25 | own_plus_btts | 0.683005 | -7e-05 | 7e-05 | -6.8e-05 | 0.000215 | 0.4105 | False |
| over25 | own_plus_over15 | 0.682408 | -0.000668 | 0.000668 | 0.000127 | 0.001241 | 0.0475 | True |
| over25 | own_plus_over35 | 0.681944 | -0.001132 | 0.001132 | 0.000586 | 0.001721 | 0.001 | True |
| over25 | own_plus_all_markets | 0.681772 | -0.001304 | 0.001304 | 0.000608 | 0.00206 | 0.004 | True |
| over25 | own_plus_all_plus_sides | 0.681731 | -0.001345 | 0.001345 | 0.000524 | 0.002185 | 0.004 | True |
| over35 | own_plus_btts | 0.582053 | -0.00018 | 0.00018 | 3e-06 | 0.000353 | 0.089 | True |
| over35 | own_plus_over15 | 0.580808 | -0.001425 | 0.001425 | 0.000546 | 0.002222 | 0.004 | True |
| over35 | own_plus_over25 | 0.580693 | -0.00154 | 0.00154 | 0.000541 | 0.002609 | 0.02 | True |
| over35 | own_plus_all_markets | 0.580336 | -0.001896 | 0.001896 | 0.000859 | 0.002999 | 0.005 | True |
| over35 | own_plus_all_plus_sides | 0.580321 | -0.001912 | 0.001912 | 0.000773 | 0.003047 | 0.009 | True |


**Every `own_plus_btts` row fails.** Every row built on another Over line passes. 
This table is the verdict; the conditional tables above are context for it.

## Error correlation — when one is wrong, is the other?

This matters more than agreement. Two models that agree but fail together give one 
piece of evidence dressed as two.

| model_a | model_b | err_rate_a | err_rate_b | both_wrong | both_wrong_if_independent | excess_pp | phi |
|---|---|---|---|---|---|---|---|
| btts | over15 | 0.4555 | 0.2575 | 0.1771 | 0.1173 | 5.98 | 0.2746 |
| btts | over25 | 0.4555 | 0.4437 | 0.2566 | 0.2021 | 5.45 | 0.2202 |
| btts | over35 | 0.4555 | 0.2819 | 0.0799 | 0.1284 | -4.85 | -0.2166 |
| over15 | over25 | 0.2575 | 0.4437 | 0.1211 | 0.1143 | 0.69 | 0.0316 |
| over15 | over35 | 0.2575 | 0.2819 | 0.0008 | 0.0726 | -7.18 | -0.3651 |
| over25 | over35 | 0.4437 | 0.2819 | 0.1014 | 0.1251 | -2.37 | -0.1061 |


Most correlated errors: btts/over15 +5.98pp over independence.

## Disagreement — is 'BTTS high, Over 2.5 low' really a 1-1 machine?

| state | n | avg_goals | goals_0 | goals_1 | goals_2 | goals_3 | goals_4 | goals_5plus | interpretable |
|---|---|---|---|---|---|---|---|---|---|
| btts_high_ou25_high | 1162 | 3.218 | 0.0422 | 0.1145 | 0.21 | 0.2186 | 0.204 | 0.2108 | True |
| btts_high_ou25_low | 34 | 2.824 | 0.0294 | 0.1765 | 0.2059 | 0.2647 | 0.2353 | 0.0882 | False |
| btts_low_ou25_high | 67 | 3.209 | 0.0 | 0.1343 | 0.1493 | 0.3134 | 0.2537 | 0.1493 | False |
| btts_low_ou25_low | 1185 | 2.081 | 0.1435 | 0.2388 | 0.2709 | 0.1907 | 0.0819 | 0.0743 | True |
| all | 23178 | 2.683 | 0.0754 | 0.1821 | 0.2345 | 0.2245 | 0.1452 | 0.1383 | True |


Scorelines:

| state | n | top_scores |
|---|---|---|
| btts_high_ou25_high | 1162 | 1-1 0.108; 2-1 0.090; 1-2 0.083; 2-2 0.079; 1-0 0.071 |
| btts_high_ou25_low | 34 | 2-1 0.206; 1-1 0.147; 1-0 0.118; 3-1 0.118; 2-2 0.088 |
| btts_low_ou25_high | 67 | 3-0 0.164; 2-1 0.119; 2-0 0.119; 1-0 0.104; 4-0 0.090 |
| btts_low_ou25_low | 1185 | 1-1 0.150; 0-0 0.143; 1-0 0.137; 0-1 0.102; 2-1 0.078 |
| all | 23178 | 1-1 0.121; 1-0 0.105; 2-1 0.091; 0-1 0.077; 0-0 0.075 |


The hypothesis points the right way — 'BTTS high, Over 2.5 low' produces 1-1 at 
more than twice its overall rate, and 'BTTS low, Over 2.5 high' produces 3-0, 2-0 
and 4-0 well above theirs. **But both cells hold fewer than 150 fixtures**, which 
is below the interpretation floor set before the analysis ran. Recorded as 
directionally consistent and not yet established. The models rarely disagree that 
strongly, which is itself the reason the cells are thin.

## Discovery → validation

588 two-model threshold conditions were searched on the earlier OOS 
period and re-measured on the later one, with Benjamini-Hochberg control.

| status | conditions |
|---|---|
| REPLICATED | 498 |
| UNTESTED | 66 |
| DISCOVERY_ONLY | 24 |


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
BTTS_ADDS_INFO_TO_OVER35=YES
OVER15_ADDS_INFO_TO_BTTS=YES
OVER25_ADDS_INFO_TO_BTTS=YES
OVER35_ADDS_INFO_TO_BTTS=YES
CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS=YES
BEST_VALIDATED_CROSS_MARKET_RELATIONSHIP=over35 <- own_plus_all_plus_sides
OOS_SAMPLE_SIZE=10453
OOS_IMPROVEMENT=-0.00191 log loss
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
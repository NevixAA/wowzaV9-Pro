# CROSS-MARKET SIGNAL RESEARCH

Do our models know anything about each other's markets that the market's own model is 
missing? Not 'are BTTS and Over 2.5 correlated' — they obviously are, both are made of 
goals. The question is whether one adds information **after** the other is known.

## The answer, in one paragraph

**Yes — but not from BTTS, which is where the question pointed.** Adding the other 
models' opinions genuinely improves out-of-sample prediction on all three Over markets, 
and the gain survives a paired bootstrap. But essentially all of it comes from the 
**other Over lines**. Telling the Over 2.5 model what the BTTS model thinks moves its 
log loss by +0.00046 — a difference whose 
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
| p_btts | 1.0 | 0.6093 | 0.6027 | 0.5858 |
| p_over15 | 0.6093 | 1.0 | 0.7751 | 0.7322 |
| p_over25 | 0.6027 | 0.7751 | 1.0 | 0.7962 |
| p_over35 | 0.5858 | 0.7322 | 0.7962 | 1.0 |


## Cross-market matrix — signal model vs actual outcome (AUC)

| signal_model | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| btts | 0.587 | 0.5889 | 0.581 | 0.5818 |
| over15 | 0.5638 | 0.5999 | 0.5943 | 0.6062 |
| over25 | 0.5637 | 0.6021 | 0.5985 | 0.6085 |
| over35 | 0.562 | 0.6001 | 0.5984 | 0.6114 |


The three Over models are nearly interchangeable; each predicts the others' markets 
about as well as its own. BTTS is the one genuinely distinct signal, and it is 
worse at the Over markets than they are at each other's.

## Conditional outcomes — P(BTTS) bucket vs what actually happened

| bucket | n | mean_p | actual_btts | actual_over15 | actual_over25 | actual_over35 | avg_goals | interpretable |
|---|---|---|---|---|---|---|---|---|
| 0.00-0.45 | 3466 | 0.3959 | 0.3935 | 0.6368 | 0.3832 | 0.1809 | 2.21 | True |
| 0.45-0.50 | 4809 | 0.4778 | 0.487 | 0.7041 | 0.4589 | 0.2439 | 2.491 | True |
| 0.50-0.55 | 8212 | 0.5259 | 0.5223 | 0.7354 | 0.5027 | 0.272 | 2.642 | True |
| 0.55-0.60 | 6983 | 0.5731 | 0.5604 | 0.7697 | 0.5342 | 0.3087 | 2.806 | True |
| 0.60-0.65 | 3225 | 0.6208 | 0.6016 | 0.8136 | 0.5919 | 0.3557 | 3.018 | True |
| 0.65-0.70 | 1006 | 0.6701 | 0.6759 | 0.8489 | 0.6441 | 0.3917 | 3.2 | True |
| 0.70-1.01 | 575 | 0.7622 | 0.8991 | 0.9565 | 0.7548 | 0.4574 | 3.591 | True |


Monotone and strong — and, on its own, not evidence of anything beyond the 
model working. The control below is what separates the two explanations.

## The control — holding the Over 2.5 model's own opinion fixed

Within fixtures the Over 2.5 model scored the same, does a high BTTS probability 
change how often Over 2.5 actually happened?

| own_p_range | n_low_other | n_high_other | actual_over25_low_other | actual_over25_high_other | diff_pp | z | p_value |
|---|---|---|---|---|---|---|---|
| 0.140-0.421 | 1571 | 1571 | 0.296 | 0.4373 | 14.13 | 8.219 | 0.0 |
| 0.421-0.472 | 1571 | 1571 | 0.4392 | 0.4749 | 3.56 | 2.006 | 0.0449 |
| 0.472-0.512 | 1571 | 1571 | 0.4895 | 0.5105 | 2.1 | 1.177 | 0.239 |
| 0.512-0.551 | 1571 | 1571 | 0.4971 | 0.5544 | 5.73 | 3.215 | 0.0013 |
| 0.551-0.599 | 1571 | 1571 | 0.5487 | 0.5888 | 4.01 | 2.269 | 0.0232 |
| 0.599-0.905 | 1571 | 1571 | 0.6098 | 0.6945 | 8.47 | 4.982 | 0.0 |


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
| own_only | 0.67503 | 0.55542 | 0.67682 | 0.578 |
| own_plus_all_markets | 0.67502 | 0.55193 | 0.67612 | 0.57587 |
| own_plus_all_plus_sides | 0.67488 | 0.55183 | 0.67597 | 0.57617 |
| own_plus_btts |  | 0.55372 | 0.67729 | 0.57741 |
| own_plus_over15 | 0.67495 |  | 0.67605 | 0.57643 |
| own_plus_over25 | 0.67495 | 0.55271 |  | 0.57643 |
| own_plus_over35 | 0.67496 | 0.5533 | 0.67618 |  |


**CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS = YES**. Best relationship: `over15 <- own_plus_all_plus_sides` at -0.00359 log loss on 12,709 fixtures.

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
| btts | own_plus_over15 | 0.674954 | -7.7e-05 | 7.7e-05 | -2.1e-05 | 0.000176 | 0.1935 | False |
| btts | own_plus_over25 | 0.674952 | -7.9e-05 | 7.9e-05 | -8e-06 | 0.000172 | 0.1475 | False |
| btts | own_plus_over35 | 0.674958 | -7.2e-05 | 7.2e-05 | -0.000136 | 0.00028 | 0.5805 | False |
| btts | own_plus_all_markets | 0.67502 | -1.1e-05 | 1.1e-05 | -0.0002 | 0.000225 | 0.925 | False |
| btts | own_plus_all_plus_sides | 0.674876 | -0.000154 | 0.000154 | -0.000309 | 0.000607 | 0.595 | False |
| over15 | own_plus_btts | 0.553717 | -0.001706 | 0.001706 | 0.000728 | 0.002688 | 0.004 | True |
| over15 | own_plus_over25 | 0.552713 | -0.00271 | 0.00271 | 0.001979 | 0.003456 | 0.0 | True |
| over15 | own_plus_over35 | 0.553297 | -0.002126 | 0.002126 | 0.001094 | 0.003253 | 0.0015 | True |
| over15 | own_plus_all_markets | 0.551926 | -0.003497 | 0.003497 | 0.002242 | 0.004804 | 0.0 | True |
| over15 | own_plus_all_plus_sides | 0.551834 | -0.003589 | 0.003589 | 0.002233 | 0.00505 | 0.0 | True |
| over25 | own_plus_btts | 0.677286 | 0.000463 | -0.000463 | -0.001695 | 0.000766 | 0.5485 | False |
| over25 | own_plus_over15 | 0.676052 | -0.000771 | 0.000771 | -5.5e-05 | 0.001582 | 0.1245 | False |
| over25 | own_plus_over35 | 0.67618 | -0.000644 | 0.000644 | -0.00061 | 0.0019 | 0.3925 | False |
| over25 | own_plus_all_markets | 0.676124 | -0.000699 | 0.000699 | -0.000898 | 0.002193 | 0.456 | False |
| over25 | own_plus_all_plus_sides | 0.675966 | -0.000857 | 0.000857 | -0.000813 | 0.002456 | 0.3965 | False |
| over35 | own_plus_btts | 0.577409 | -0.000594 | 0.000594 | 7.3e-05 | 0.001119 | 0.0585 | True |
| over35 | own_plus_over15 | 0.57643 | -0.001572 | 0.001572 | 0.000875 | 0.002305 | 0.0005 | True |
| over35 | own_plus_over25 | 0.576429 | -0.001573 | 0.001573 | 0.001125 | 0.002022 | 0.0 | True |
| over35 | own_plus_all_markets | 0.575868 | -0.002134 | 0.002134 | 0.00135 | 0.002936 | 0.0 | True |
| over35 | own_plus_all_plus_sides | 0.576168 | -0.001834 | 0.001834 | 0.000626 | 0.003004 | 0.009 | True |


**Every `own_plus_btts` row fails.** Every row built on another Over line passes. 
This table is the verdict; the conditional tables above are context for it.

## Error correlation — when one is wrong, is the other?

This matters more than agreement. Two models that agree but fail together give one 
piece of evidence dressed as two.

| model_a | model_b | err_rate_a | err_rate_b | both_wrong | both_wrong_if_independent | excess_pp | phi |
|---|---|---|---|---|---|---|---|
| btts | over15 | 0.4374 | 0.2555 | 0.1619 | 0.1118 | 5.01 | 0.2317 |
| btts | over25 | 0.4374 | 0.4316 | 0.2478 | 0.1888 | 5.9 | 0.2401 |
| btts | over35 | 0.4374 | 0.2804 | 0.0824 | 0.1226 | -4.03 | -0.1807 |
| over15 | over25 | 0.2555 | 0.4316 | 0.1149 | 0.1103 | 0.46 | 0.0213 |
| over15 | over35 | 0.2555 | 0.2804 | 0.0017 | 0.0716 | -7.0 | -0.3572 |
| over25 | over35 | 0.4316 | 0.2804 | 0.0998 | 0.121 | -2.12 | -0.0951 |


Most correlated errors: btts/over25 +5.90pp over independence.

## Disagreement — is 'BTTS high, Over 2.5 low' really a 1-1 machine?

| state | n | avg_goals | goals_0 | goals_1 | goals_2 | goals_3 | goals_4 | goals_5plus | interpretable |
|---|---|---|---|---|---|---|---|---|---|
| btts_high_ou25_high | 2217 | 3.352 | 0.037 | 0.0925 | 0.1967 | 0.2418 | 0.1926 | 0.2395 | True |
| btts_high_ou25_low | 171 | 2.614 | 0.0292 | 0.0994 | 0.3801 | 0.3099 | 0.1287 | 0.0526 | True |
| btts_low_ou25_high | 140 | 3.186 | 0.0357 | 0.1357 | 0.1571 | 0.2714 | 0.1857 | 0.2143 | False |
| btts_low_ou25_low | 2460 | 2.039 | 0.1362 | 0.2646 | 0.2622 | 0.1898 | 0.0858 | 0.0614 | True |
| all | 28276 | 2.686 | 0.0752 | 0.1809 | 0.2352 | 0.226 | 0.1453 | 0.1374 | True |


Scorelines:

| state | n | top_scores |
|---|---|---|
| btts_high_ou25_high | 2217 | 2-1 0.110; 1-1 0.102; 2-2 0.075; 1-2 0.074; 2-0 0.065 |
| btts_high_ou25_low | 171 | 1-1 0.251; 1-2 0.140; 2-1 0.140; 0-2 0.076; 1-3 0.058 |
| btts_low_ou25_high | 140 | 3-0 0.171; 2-0 0.129; 1-0 0.093; 2-1 0.086; 4-0 0.071 |
| btts_low_ou25_low | 2460 | 1-0 0.162; 0-0 0.136; 1-1 0.124; 0-1 0.103; 2-0 0.083 |
| all | 28276 | 1-1 0.120; 1-0 0.104; 2-1 0.093; 0-1 0.077; 0-0 0.075 |


The hypothesis points the right way — 'BTTS high, Over 2.5 low' produces 1-1 at 
more than twice its overall rate, and 'BTTS low, Over 2.5 high' produces 3-0, 2-0 
and 4-0 well above theirs. **But both cells hold fewer than 150 fixtures**, which 
is below the interpretation floor set before the analysis ran. Recorded as 
directionally consistent and not yet established. The models rarely disagree that 
strongly, which is itself the reason the cells are thin.

## Discovery → validation

624 two-model threshold conditions were searched on the earlier OOS 
period and re-measured on the later one, with Benjamini-Hochberg control.

| status | conditions |
|---|---|
| REPLICATED | 624 |


**These replication rates should not be read as edges.** Most of the searched 
conditions amount to 'select fixtures both models think are high-scoring', and 
those fixtures really are high-scoring — the pattern replicates because the models 
work, not because a cross-market secret was found. That is precisely why the 
meta-model, not this table, carries the verdict.

## Verdict

```text
CROSS_MARKET_DATASET_LEAKAGE_SAFE=YES
BTTS_ADDS_INFO_TO_OVER15=YES
BTTS_ADDS_INFO_TO_OVER25=NO
BTTS_ADDS_INFO_TO_OVER35=YES
OVER15_ADDS_INFO_TO_BTTS=NO
OVER25_ADDS_INFO_TO_BTTS=NO
OVER35_ADDS_INFO_TO_BTTS=NO
CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS=YES
BEST_VALIDATED_CROSS_MARKET_RELATIONSHIP=over15 <- own_plus_all_plus_sides
OOS_SAMPLE_SIZE=12709
OOS_IMPROVEMENT=-0.00359 log loss
MODEL_AGREEMENT_IMPROVES_ACCURACY=NO
MODEL_DISAGREEMENT_IS_INFORMATIVE=MIXED
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
```


## What was deliberately not done

No economic analysis. Rule 21 puts pricing after prediction, and the prediction-side 
gain that survived — of the order of 0.002 nats of log loss — is small enough that the 
honest next step is to see whether it persists on new fixtures, not to go looking for 
a price it might beat. `ANY_VALIDATED_PATTERN_SHOWS_ECONOMIC_EDGE = NOT_TESTED` is a 
deliberate answer, not an omission.

No production change. No notifier change. No threshold moved.
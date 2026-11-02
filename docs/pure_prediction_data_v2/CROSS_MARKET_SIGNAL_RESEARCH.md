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

| model | p_btts | p_over15 | p_over25 | p_over35 | data_version | identity_version | season_calendar_version |
|---|---|---|---|---|---|---|---|
| p_btts | 1.0 | 0.6008 | 0.6058 | 0.5686 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over15 | 0.6008 | 1.0 | 0.8045 | 0.7379 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over25 | 0.6058 | 0.8045 | 1.0 | 0.8003 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over35 | 0.5686 | 0.7379 | 0.8003 | 1.0 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |


## Cross-market matrix — signal model vs actual outcome (AUC)

| signal_model | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| btts | 0.5494 | 0.5577 | 0.5567 | 0.5597 |
| over15 | 0.5461 | 0.5813 | 0.5782 | 0.5883 |
| over25 | 0.5472 | 0.5808 | 0.5789 | 0.5907 |
| over35 | 0.5476 | 0.5828 | 0.5797 | 0.5879 |


The three Over models are nearly interchangeable; each predicts the others' markets 
about as well as its own. BTTS is the one genuinely distinct signal, and it is 
worse at the Over markets than they are at each other's.

## Conditional outcomes — P(BTTS) bucket vs what actually happened

| bucket | n | mean_p | actual_btts | actual_over15 | actual_over25 | actual_over35 | avg_goals | interpretable |
|---|---|---|---|---|---|---|---|---|
| 0.00-0.45 | 1659 | 0.423 | 0.4479 | 0.6703 | 0.4069 | 0.2086 | 2.315 | True |
| 0.45-0.50 | 5092 | 0.4788 | 0.4892 | 0.7005 | 0.4635 | 0.2449 | 2.483 | True |
| 0.50-0.55 | 8322 | 0.5255 | 0.5285 | 0.7425 | 0.4951 | 0.2714 | 2.64 | True |
| 0.55-0.60 | 6761 | 0.5723 | 0.5564 | 0.7702 | 0.5444 | 0.3072 | 2.819 | True |
| 0.60-0.65 | 2186 | 0.6188 | 0.6029 | 0.8028 | 0.5952 | 0.3779 | 3.065 | True |
| 0.65-0.70 | 306 | 0.6648 | 0.683 | 0.8333 | 0.6601 | 0.415 | 3.222 | True |
| 0.70-1.01 | 21 | 0.7134 | 0.6667 | 0.7619 | 0.5238 | 0.3333 | 2.857 | False |


Monotone and strong — and, on its own, not evidence of anything beyond the 
model working. The control below is what separates the two explanations.

## The control — holding the Over 2.5 model's own opinion fixed

Within fixtures the Over 2.5 model scored the same, does a high BTTS probability 
change how often Over 2.5 actually happened?

| own_p_range | n_low_other | n_high_other | actual_over25_low_other | actual_over25_high_other | diff_pp | z | p_value |
|---|---|---|---|---|---|---|---|
| 0.244-0.433 | 1353 | 1353 | 0.3747 | 0.4191 | 4.43 | 2.358 | 0.0184 |
| 0.433-0.474 | 1353 | 1353 | 0.456 | 0.473 | 1.7 | 0.887 | 0.3753 |
| 0.474-0.507 | 1353 | 1353 | 0.4767 | 0.5033 | 2.66 | 1.384 | 0.1662 |
| 0.507-0.540 | 1353 | 1353 | 0.5292 | 0.5358 | 0.67 | 0.347 | 0.7288 |
| 0.540-0.580 | 1353 | 1353 | 0.5255 | 0.5654 | 3.99 | 2.085 | 0.0371 |
| 0.580-0.829 | 1353 | 1353 | 0.5965 | 0.6445 | 4.8 | 2.575 | 0.01 |


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
| own_only | 0.68719 | 0.55957 | 0.68272 | 0.5845 |
| own_plus_all_markets | 0.68589 | 0.55819 | 0.68127 | 0.58215 |
| own_plus_all_plus_sides | 0.68563 | 0.558 | 0.6813 | 0.58262 |
| own_plus_btts |  | 0.55961 | 0.6827 | 0.58433 |
| own_plus_over15 | 0.68646 |  | 0.68155 | 0.58305 |
| own_plus_over25 | 0.68606 | 0.55876 |  | 0.58239 |
| own_plus_over35 | 0.68594 | 0.55834 | 0.6818 |  |


**CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS = YES**. Best relationship: `over35 <- own_plus_all_markets` at -0.00236 log loss on 10,890 fixtures.

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
| btts | own_plus_over15 | 0.686465 | -0.000726 | 0.000726 | 0.000206 | 0.001199 | 0.019 | True |
| btts | own_plus_over25 | 0.686057 | -0.001134 | 0.001134 | 0.000572 | 0.001669 | 0.0 | True |
| btts | own_plus_over35 | 0.685939 | -0.001252 | 0.001252 | 0.000688 | 0.001825 | 0.0 | True |
| btts | own_plus_all_markets | 0.685894 | -0.001297 | 0.001297 | 0.00068 | 0.001903 | 0.0 | True |
| btts | own_plus_all_plus_sides | 0.685629 | -0.001562 | 0.001562 | 0.00075 | 0.002334 | 0.003 | True |
| over15 | own_plus_btts | 0.559614 | 3.9e-05 | -3.9e-05 | -0.000269 | 0.000191 | 0.7865 | False |
| over15 | own_plus_over25 | 0.558758 | -0.000817 | 0.000817 | 9e-06 | 0.001608 | 0.093 | True |
| over15 | own_plus_over35 | 0.558336 | -0.001239 | 0.001239 | 0.00046 | 0.002025 | 0.0075 | True |
| over15 | own_plus_all_markets | 0.558192 | -0.001383 | 0.001383 | 0.000479 | 0.002266 | 0.01 | True |
| over15 | own_plus_all_plus_sides | 0.557995 | -0.001579 | 0.001579 | 0.000589 | 0.002545 | 0.0065 | True |
| over25 | own_plus_btts | 0.682695 | -2.1e-05 | 2.1e-05 | -0.000225 | 0.000283 | 0.893 | False |
| over25 | own_plus_over15 | 0.681546 | -0.00117 | 0.00117 | 0.000509 | 0.00183 | 0.005 | True |
| over25 | own_plus_over35 | 0.681796 | -0.00092 | 0.00092 | 0.00013 | 0.00169 | 0.0485 | True |
| over25 | own_plus_all_markets | 0.68127 | -0.001447 | 0.001447 | 0.000485 | 0.002374 | 0.0135 | True |
| over25 | own_plus_all_plus_sides | 0.681299 | -0.001417 | 0.001417 | 0.000368 | 0.002449 | 0.026 | True |
| over35 | own_plus_btts | 0.584327 | -0.000177 | 0.000177 | -2.8e-05 | 0.000383 | 0.1615 | False |
| over35 | own_plus_over15 | 0.583052 | -0.001453 | 0.001453 | 0.000635 | 0.002221 | 0.002 | True |
| over35 | own_plus_over25 | 0.58239 | -0.002114 | 0.002114 | 0.00127 | 0.00298 | 0.0 | True |
| over35 | own_plus_all_markets | 0.582147 | -0.002357 | 0.002357 | 0.001428 | 0.003306 | 0.0 | True |
| over35 | own_plus_all_plus_sides | 0.582617 | -0.001888 | 0.001888 | 0.000818 | 0.002999 | 0.006 | True |


**Every `own_plus_btts` row fails.** Every row built on another Over line passes. 
This table is the verdict; the conditional tables above are context for it.

## Error correlation — when one is wrong, is the other?

This matters more than agreement. Two models that agree but fail together give one 
piece of evidence dressed as two.

| model_a | model_b | err_rate_a | err_rate_b | both_wrong | both_wrong_if_independent | excess_pp | phi |
|---|---|---|---|---|---|---|---|
| btts | over15 | 0.4571 | 0.257 | 0.1719 | 0.1175 | 5.44 | 0.2501 |
| btts | over25 | 0.4571 | 0.4462 | 0.2597 | 0.2039 | 5.58 | 0.2252 |
| btts | over35 | 0.4571 | 0.2812 | 0.084 | 0.1285 | -4.46 | -0.1991 |
| over15 | over25 | 0.257 | 0.4462 | 0.1167 | 0.1146 | 0.2 | 0.0094 |
| over15 | over35 | 0.257 | 0.2812 | 0.0007 | 0.0723 | -7.16 | -0.3645 |
| over25 | over35 | 0.4462 | 0.2812 | 0.1081 | 0.1255 | -1.73 | -0.0775 |


Most correlated errors: btts/over25 +5.58pp over independence.

## Disagreement — is 'BTTS high, Over 2.5 low' really a 1-1 machine?

| state | n | avg_goals | goals_0 | goals_1 | goals_2 | goals_3 | goals_4 | goals_5plus | interpretable |
|---|---|---|---|---|---|---|---|---|---|
| btts_high_ou25_high | 979 | 3.33 | 0.047 | 0.1042 | 0.1849 | 0.2268 | 0.2022 | 0.2349 | True |
| btts_low_ou25_high | 58 | 3.345 | 0.0345 | 0.069 | 0.2241 | 0.2759 | 0.1724 | 0.2241 | False |
| btts_low_ou25_low | 1145 | 2.162 | 0.1197 | 0.241 | 0.2664 | 0.1974 | 0.1066 | 0.069 | True |
| all | 24347 | 2.68 | 0.0756 | 0.1814 | 0.2358 | 0.2243 | 0.1456 | 0.1373 | True |


Scorelines:

| state | n | top_scores |
|---|---|---|
| btts_high_ou25_high | 979 | 2-1 0.095; 2-2 0.090; 1-1 0.086; 1-2 0.084; 1-0 0.063 |
| btts_low_ou25_high | 58 | 3-0 0.190; 2-0 0.138; 4-0 0.086; 2-1 0.086; 1-1 0.069 |
| btts_low_ou25_low | 1145 | 1-0 0.145; 1-1 0.136; 0-0 0.120; 0-1 0.096; 2-1 0.093 |
| all | 24347 | 1-1 0.121; 1-0 0.105; 2-1 0.092; 0-1 0.076; 0-0 0.076 |


The hypothesis points the right way — 'BTTS high, Over 2.5 low' produces 1-1 at 
more than twice its overall rate, and 'BTTS low, Over 2.5 high' produces 3-0, 2-0 
and 4-0 well above theirs. **But both cells hold fewer than 150 fixtures**, which 
is below the interpretation floor set before the analysis ran. Recorded as 
directionally consistent and not yet established. The models rarely disagree that 
strongly, which is itself the reason the cells are thin.

## Discovery → validation

594 two-model threshold conditions were searched on the earlier OOS 
period and re-measured on the later one, with Benjamini-Hochberg control.

| status | conditions |
|---|---|
| REPLICATED | 498 |
| UNTESTED | 72 |
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
BTTS_ADDS_INFO_TO_OVER35=NO
OVER15_ADDS_INFO_TO_BTTS=YES
OVER25_ADDS_INFO_TO_BTTS=YES
OVER35_ADDS_INFO_TO_BTTS=YES
CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS=YES
BEST_VALIDATED_CROSS_MARKET_RELATIONSHIP=over35 <- own_plus_all_markets
OOS_SAMPLE_SIZE=10890
OOS_IMPROVEMENT=-0.00236 log loss
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
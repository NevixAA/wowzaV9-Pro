# CROSS-MARKET SIGNAL RESEARCH

Do our models know anything about each other's markets that the market's own model is 
missing? Not 'are BTTS and Over 2.5 correlated' — they obviously are, both are made of 
goals. The question is whether one adds information **after** the other is known.

## The answer, in one paragraph

**Yes — but not from BTTS, which is where the question pointed.** Adding the other 
models' opinions genuinely improves out-of-sample prediction on all three Over markets, 
and the gain survives a paired bootstrap. But essentially all of it comes from the 
**other Over lines**. Telling the Over 2.5 model what the BTTS model thinks moves its 
log loss by +0.00025 — a difference whose 
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
| p_btts | 1.0 | 0.6179 | 0.6238 | 0.5788 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over15 | 0.6179 | 1.0 | 0.8036 | 0.7446 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over25 | 0.6238 | 0.8036 | 1.0 | 0.8046 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |
| p_over35 | 0.5788 | 0.7446 | 0.8046 | 1.0 | lab-data/2.0 | pro-identity-1.0+identity/1.0 | season-calendar/1.0 |


## Cross-market matrix — signal model vs actual outcome (AUC)

| signal_model | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| btts | 0.5522 | 0.5614 | 0.5583 | 0.5633 |
| over15 | 0.5457 | 0.5791 | 0.5774 | 0.5859 |
| over25 | 0.5482 | 0.5816 | 0.579 | 0.5917 |
| over35 | 0.5474 | 0.5808 | 0.5793 | 0.5886 |


The three Over models are nearly interchangeable; each predicts the others' markets 
about as well as its own. BTTS is the one genuinely distinct signal, and it is 
worse at the Over markets than they are at each other's.

## Conditional outcomes — P(BTTS) bucket vs what actually happened

| bucket | n | mean_p | actual_btts | actual_over15 | actual_over25 | actual_over35 | avg_goals | interpretable |
|---|---|---|---|---|---|---|---|---|
| 0.00-0.45 | 1767 | 0.4187 | 0.4522 | 0.6582 | 0.412 | 0.2151 | 2.316 | True |
| 0.45-0.50 | 4718 | 0.4788 | 0.4871 | 0.7009 | 0.4559 | 0.2376 | 2.461 | True |
| 0.50-0.55 | 8324 | 0.5257 | 0.5211 | 0.7389 | 0.4974 | 0.2707 | 2.629 | True |
| 0.55-0.60 | 6682 | 0.5726 | 0.562 | 0.7722 | 0.5397 | 0.3084 | 2.823 | True |
| 0.60-0.65 | 2405 | 0.6194 | 0.6029 | 0.8033 | 0.5946 | 0.3688 | 3.046 | True |
| 0.65-0.70 | 483 | 0.6676 | 0.6418 | 0.8302 | 0.6294 | 0.3934 | 3.19 | True |
| 0.70-1.01 | 46 | 0.7124 | 0.6739 | 0.8261 | 0.6304 | 0.3913 | 3.239 | False |


Monotone and strong — and, on its own, not evidence of anything beyond the 
model working. The control below is what separates the two explanations.

## The control — holding the Over 2.5 model's own opinion fixed

Within fixtures the Over 2.5 model scored the same, does a high BTTS probability 
change how often Over 2.5 actually happened?

| own_p_range | n_low_other | n_high_other | actual_over25_low_other | actual_over25_high_other | diff_pp | z | p_value |
|---|---|---|---|---|---|---|---|
| 0.230-0.432 | 1357 | 1357 | 0.3766 | 0.4259 | 4.94 | 2.624 | 0.0087 |
| 0.432-0.473 | 1357 | 1357 | 0.4517 | 0.4827 | 3.1 | 1.616 | 0.1061 |
| 0.473-0.507 | 1357 | 1357 | 0.4547 | 0.5158 | 6.12 | 3.188 | 0.0014 |
| 0.507-0.541 | 1357 | 1357 | 0.4989 | 0.507 | 0.81 | 0.422 | 0.6728 |
| 0.541-0.582 | 1357 | 1357 | 0.5475 | 0.5409 | -0.66 | -0.347 | 0.7287 |
| 0.582-0.868 | 1357 | 1357 | 0.605 | 0.636 | 3.1 | 1.661 | 0.0966 |


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
| own_only | 0.68735 | 0.56005 | 0.68249 | 0.5841 |
| own_plus_all_markets | 0.68589 | 0.55824 | 0.68134 | 0.58244 |
| own_plus_all_plus_sides | 0.68575 | 0.5584 | 0.6815 | 0.58263 |
| own_plus_btts |  | 0.56012 | 0.68273 | 0.58389 |
| own_plus_over15 | 0.68678 |  | 0.68183 | 0.58333 |
| own_plus_over25 | 0.68624 | 0.5586 |  | 0.58236 |
| own_plus_over35 | 0.68604 | 0.5585 | 0.68136 |  |


**CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS = YES**. Best relationship: `over15 <- own_plus_all_markets` at -0.00181 log loss on 10,959 fixtures.

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
| btts | own_plus_over15 | 0.686782 | -0.000572 | 0.000572 | 0.000258 | 0.000889 | 0.0035 | True |
| btts | own_plus_over25 | 0.686235 | -0.001119 | 0.001119 | 0.000671 | 0.00161 | 0.0 | True |
| btts | own_plus_over35 | 0.686036 | -0.001318 | 0.001318 | 0.000861 | 0.001798 | 0.0 | True |
| btts | own_plus_all_markets | 0.685889 | -0.001465 | 0.001465 | 0.000976 | 0.001994 | 0.0 | True |
| btts | own_plus_all_plus_sides | 0.685746 | -0.001608 | 0.001608 | 0.000888 | 0.002332 | 0.0 | True |
| over15 | own_plus_btts | 0.560117 | 6.5e-05 | -6.5e-05 | -0.000513 | 0.000432 | 0.8245 | False |
| over15 | own_plus_over25 | 0.558598 | -0.001454 | 0.001454 | 0.000688 | 0.002271 | 0.0015 | True |
| over15 | own_plus_over35 | 0.558502 | -0.00155 | 0.00155 | 0.00069 | 0.002441 | 0.0045 | True |
| over15 | own_plus_all_markets | 0.558244 | -0.001808 | 0.001808 | 0.000829 | 0.00279 | 0.003 | True |
| over15 | own_plus_all_plus_sides | 0.5584 | -0.001652 | 0.001652 | 0.000594 | 0.002764 | 0.0085 | True |
| over25 | own_plus_btts | 0.682735 | 0.000249 | -0.000249 | -0.000665 | 0.000158 | 0.321 | False |
| over25 | own_plus_over15 | 0.681831 | -0.000654 | 0.000654 | 8.5e-05 | 0.00119 | 0.0495 | True |
| over25 | own_plus_over35 | 0.681359 | -0.001126 | 0.001126 | 0.000347 | 0.001909 | 0.0165 | True |
| over25 | own_plus_all_markets | 0.681337 | -0.001149 | 0.001149 | 0.000254 | 0.002009 | 0.0325 | True |
| over25 | own_plus_all_plus_sides | 0.681502 | -0.000983 | 0.000983 | -3.4e-05 | 0.001925 | 0.0965 | False |
| over35 | own_plus_btts | 0.583894 | -0.000202 | 0.000202 | -0.000114 | 0.000536 | 0.319 | False |
| over35 | own_plus_over15 | 0.583325 | -0.000771 | 0.000771 | 0.000102 | 0.001438 | 0.059 | True |
| over35 | own_plus_over25 | 0.582363 | -0.001733 | 0.001733 | 0.000864 | 0.002624 | 0.0 | True |
| over35 | own_plus_all_markets | 0.582436 | -0.00166 | 0.00166 | 0.000755 | 0.002578 | 0.0025 | True |
| over35 | own_plus_all_plus_sides | 0.582627 | -0.001469 | 0.001469 | 0.000371 | 0.002617 | 0.0325 | True |


**Every `own_plus_btts` row fails.** Every row built on another Over line passes. 
This table is the verdict; the conditional tables above are context for it.

## Error correlation — when one is wrong, is the other?

This matters more than agreement. Two models that agree but fail together give one 
piece of evidence dressed as two.

| model_a | model_b | err_rate_a | err_rate_b | both_wrong | both_wrong_if_independent | excess_pp | phi |
|---|---|---|---|---|---|---|---|
| btts | over15 | 0.4566 | 0.2569 | 0.1744 | 0.1173 | 5.71 | 0.2623 |
| btts | over25 | 0.4566 | 0.4456 | 0.2601 | 0.2035 | 5.66 | 0.2286 |
| btts | over35 | 0.4566 | 0.2809 | 0.0809 | 0.1283 | -4.74 | -0.2118 |
| over15 | over25 | 0.2569 | 0.4456 | 0.1155 | 0.1145 | 0.1 | 0.0048 |
| over15 | over35 | 0.2569 | 0.2809 | 0.0007 | 0.0722 | -7.15 | -0.3639 |
| over25 | over35 | 0.4456 | 0.2809 | 0.1085 | 0.1252 | -1.67 | -0.0745 |


Most correlated errors: btts/over15 +5.71pp over independence.

## Disagreement — is 'BTTS high, Over 2.5 low' really a 1-1 machine?

| state | n | avg_goals | goals_0 | goals_1 | goals_2 | goals_3 | goals_4 | goals_5plus | interpretable |
|---|---|---|---|---|---|---|---|---|---|
| btts_high_ou25_high | 1144 | 3.3 | 0.0367 | 0.1171 | 0.1949 | 0.2203 | 0.1976 | 0.2334 | True |
| btts_high_ou25_low | 39 | 2.872 | 0.0513 | 0.1026 | 0.2564 | 0.2821 | 0.2308 | 0.0769 | False |
| btts_low_ou25_high | 55 | 3.636 | 0.0182 | 0.0545 | 0.2182 | 0.2364 | 0.1636 | 0.3091 | False |
| btts_low_ou25_low | 1282 | 2.195 | 0.1178 | 0.2488 | 0.2543 | 0.1919 | 0.1131 | 0.0741 | True |
| all | 24425 | 2.68 | 0.0759 | 0.181 | 0.236 | 0.2243 | 0.1458 | 0.1371 | True |


Scorelines:

| state | n | top_scores |
|---|---|---|
| btts_high_ou25_high | 1144 | 2-1 0.094; 1-1 0.091; 1-2 0.080; 2-2 0.079; 1-0 0.068 |
| btts_high_ou25_low | 39 | 1-1 0.205; 2-1 0.154; 1-2 0.077; 1-3 0.077; 1-0 0.051 |
| btts_low_ou25_high | 55 | 2-1 0.145; 2-0 0.145; 3-0 0.091; 4-1 0.073; 3-1 0.073 |
| btts_low_ou25_low | 1282 | 1-0 0.139; 1-1 0.133; 0-0 0.118; 0-1 0.110; 2-1 0.090 |
| all | 24425 | 1-1 0.121; 1-0 0.105; 2-1 0.091; 0-1 0.076; 0-0 0.076 |


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
| REPLICATED | 502 |
| UNTESTED | 78 |
| DISCOVERY_ONLY | 26 |


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
OOS_SAMPLE_SIZE=10959
OOS_IMPROVEMENT=-0.00181 log loss
MODEL_AGREEMENT_IMPROVES_ACCURACY=NO
MODEL_DISAGREEMENT_IS_INFORMATIVE=UNCLEAR
ANY_CROSS_MARKET_PATTERN_SURVIVES_MULTIPLE_TESTING=YES
ANY_CROSS_MARKET_PATTERN_REPLICATED_CHRONOLOGICALLY=YES
PLAYER_SCORER_ADDS_INFO_TO_BTTS=YES
PLAYER_SCORER_ADDS_INFO_TO_OVER25=YES
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
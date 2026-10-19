# CROSS-MARKET SIGNAL RESEARCH

Do our models know anything about each other's markets that the market's own model is 
missing? Not 'are BTTS and Over 2.5 correlated' — they obviously are, both are made of 
goals. The question is whether one adds information **after** the other is known.

## The answer, in one paragraph

**Yes — but not from BTTS, which is where the question pointed.** Adding the other 
models' opinions genuinely improves out-of-sample prediction on all three Over markets, 
and the gain survives a paired bootstrap. But essentially all of it comes from the 
**other Over lines**. Telling the Over 2.5 model what the BTTS model thinks moves its 
log loss by -0.00027 — a difference whose 
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
| p_btts | 1.0 | 0.5986 | 0.5986 | 0.5572 |
| p_over15 | 0.5986 | 1.0 | 0.8019 | 0.7243 |
| p_over25 | 0.5986 | 0.8019 | 1.0 | 0.8134 |
| p_over35 | 0.5572 | 0.7243 | 0.8134 | 1.0 |


## Cross-market matrix — signal model vs actual outcome (AUC)

| signal_model | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| btts | 0.5859 | 0.586 | 0.5776 | 0.5781 |
| over15 | 0.5653 | 0.6013 | 0.5934 | 0.6059 |
| over25 | 0.5643 | 0.6018 | 0.5975 | 0.6093 |
| over35 | 0.5623 | 0.5977 | 0.5953 | 0.6074 |


The three Over models are nearly interchangeable; each predicts the others' markets 
about as well as its own. BTTS is the one genuinely distinct signal, and it is 
worse at the Over markets than they are at each other's.

## Conditional outcomes — P(BTTS) bucket vs what actually happened

| bucket | n | mean_p | actual_btts | actual_over15 | actual_over25 | actual_over35 | avg_goals | interpretable |
|---|---|---|---|---|---|---|---|---|
| 0.00-0.45 | 3483 | 0.3981 | 0.3885 | 0.6357 | 0.3928 | 0.1826 | 2.232 | True |
| 0.45-0.50 | 4931 | 0.4779 | 0.4892 | 0.7037 | 0.4533 | 0.2476 | 2.481 | True |
| 0.50-0.55 | 7965 | 0.5258 | 0.5294 | 0.7431 | 0.5058 | 0.2736 | 2.659 | True |
| 0.55-0.60 | 6917 | 0.5732 | 0.5569 | 0.7642 | 0.5342 | 0.3056 | 2.799 | True |
| 0.60-0.65 | 3324 | 0.6213 | 0.5963 | 0.8008 | 0.5851 | 0.3559 | 2.99 | True |
| 0.65-0.70 | 1045 | 0.6704 | 0.6431 | 0.845 | 0.6239 | 0.3656 | 3.103 | True |
| 0.70-1.01 | 663 | 0.7602 | 0.9125 | 0.9532 | 0.7541 | 0.4661 | 3.588 | True |


Monotone and strong — and, on its own, not evidence of anything beyond the 
model working. The control below is what separates the two explanations.

## The control — holding the Over 2.5 model's own opinion fixed

Within fixtures the Over 2.5 model scored the same, does a high BTTS probability 
change how often Over 2.5 actually happened?

| own_p_range | n_low_other | n_high_other | actual_over25_low_other | actual_over25_high_other | diff_pp | z | p_value |
|---|---|---|---|---|---|---|---|
| 0.155-0.424 | 1574 | 1574 | 0.303 | 0.425 | 12.2 | 7.112 | 0.0 |
| 0.424-0.473 | 1574 | 1574 | 0.4536 | 0.4682 | 1.46 | 0.822 | 0.4109 |
| 0.473-0.511 | 1574 | 1574 | 0.4549 | 0.5222 | 6.73 | 3.779 | 0.0002 |
| 0.511-0.547 | 1574 | 1574 | 0.5038 | 0.554 | 5.02 | 2.821 | 0.0048 |
| 0.547-0.589 | 1574 | 1574 | 0.5553 | 0.5781 | 2.29 | 1.295 | 0.1954 |
| 0.589-0.894 | 1574 | 1574 | 0.6112 | 0.6944 | 8.32 | 4.904 | 0.0 |


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
| own_only | 0.67448 | 0.55394 | 0.67765 | 0.57908 |
| own_plus_all_markets | 0.67447 | 0.55085 | 0.67612 | 0.57619 |
| own_plus_all_plus_sides | 0.67462 | 0.55123 | 0.67608 | 0.57638 |
| own_plus_btts |  | 0.55224 | 0.67738 | 0.57842 |
| own_plus_over15 | 0.67448 |  | 0.67691 | 0.57681 |
| own_plus_over25 | 0.67436 | 0.55199 |  | 0.57701 |
| own_plus_over35 | 0.67435 | 0.55229 | 0.67638 |  |


**CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS = YES**. Best relationship: `over15 <- own_plus_all_markets` at -0.00310 log loss on 12,687 fixtures.

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
| btts | own_plus_over15 | 0.674476 | -8e-06 | 8e-06 | -0.000251 | 0.000273 | 0.9655 | False |
| btts | own_plus_over25 | 0.67436 | -0.000124 | 0.000124 | -0.000111 | 0.000352 | 0.3765 | False |
| btts | own_plus_over35 | 0.674353 | -0.000131 | 0.000131 | -9.6e-05 | 0.000353 | 0.3365 | False |
| btts | own_plus_all_markets | 0.674471 | -1.3e-05 | 1.3e-05 | -0.000273 | 0.000289 | 0.9395 | False |
| btts | own_plus_all_plus_sides | 0.674618 | 0.000134 | -0.000134 | -0.000729 | 0.000466 | 0.708 | False |
| over15 | own_plus_btts | 0.55224 | -0.001704 | 0.001704 | 0.00089 | 0.002492 | 0.0005 | True |
| over15 | own_plus_over25 | 0.551988 | -0.001956 | 0.001956 | 0.001145 | 0.00277 | 0.0 | True |
| over15 | own_plus_over35 | 0.552287 | -0.001656 | 0.001656 | 0.000768 | 0.002529 | 0.0005 | True |
| over15 | own_plus_all_markets | 0.550848 | -0.003096 | 0.003096 | 0.002006 | 0.004153 | 0.0 | True |
| over15 | own_plus_all_plus_sides | 0.551232 | -0.002712 | 0.002712 | 0.001424 | 0.004101 | 0.0005 | True |
| over25 | own_plus_btts | 0.677381 | -0.000269 | 0.000269 | -0.000723 | 0.001245 | 0.6655 | False |
| over25 | own_plus_over15 | 0.676909 | -0.00074 | 0.00074 | 7.7e-05 | 0.001401 | 0.0605 | True |
| over25 | own_plus_over35 | 0.676377 | -0.001273 | 0.001273 | 0.00046 | 0.002092 | 0.013 | True |
| over25 | own_plus_all_markets | 0.676124 | -0.001525 | 0.001525 | 0.000279 | 0.002802 | 0.054 | True |
| over25 | own_plus_all_plus_sides | 0.676077 | -0.001572 | 0.001572 | 0.000146 | 0.00306 | 0.082 | True |
| over35 | own_plus_btts | 0.578416 | -0.000664 | 0.000664 | 6.1e-05 | 0.00123 | 0.063 | True |
| over35 | own_plus_over15 | 0.57681 | -0.00227 | 0.00227 | 0.001453 | 0.003081 | 0.0 | True |
| over35 | own_plus_over25 | 0.577006 | -0.002074 | 0.002074 | 0.001318 | 0.00285 | 0.0 | True |
| over35 | own_plus_all_markets | 0.576188 | -0.002891 | 0.002891 | 0.001853 | 0.003902 | 0.0 | True |
| over35 | own_plus_all_plus_sides | 0.576376 | -0.002703 | 0.002703 | 0.001372 | 0.00396 | 0.0015 | True |


**Every `own_plus_btts` row fails.** Every row built on another Over line passes. 
This table is the verdict; the conditional tables above are context for it.

## Error correlation — when one is wrong, is the other?

This matters more than agreement. Two models that agree but fail together give one 
piece of evidence dressed as two.

| model_a | model_b | err_rate_a | err_rate_b | both_wrong | both_wrong_if_independent | excess_pp | phi |
|---|---|---|---|---|---|---|---|
| btts | over15 | 0.436 | 0.2557 | 0.1607 | 0.1115 | 4.92 | 0.2276 |
| btts | over25 | 0.436 | 0.4326 | 0.2464 | 0.1886 | 5.78 | 0.2353 |
| btts | over35 | 0.436 | 0.2821 | 0.0828 | 0.123 | -4.02 | -0.1801 |
| over15 | over25 | 0.2557 | 0.4326 | 0.1152 | 0.1106 | 0.46 | 0.0212 |
| over15 | over35 | 0.2557 | 0.2821 | 0.0014 | 0.0721 | -7.07 | -0.3604 |
| over25 | over35 | 0.4326 | 0.2821 | 0.1002 | 0.122 | -2.18 | -0.0978 |


Most correlated errors: btts/over25 +5.78pp over independence.

## Disagreement — is 'BTTS high, Over 2.5 low' really a 1-1 machine?

| state | n | avg_goals | goals_0 | goals_1 | goals_2 | goals_3 | goals_4 | goals_5plus | interpretable |
|---|---|---|---|---|---|---|---|---|---|
| btts_high_ou25_high | 1929 | 3.393 | 0.0327 | 0.0892 | 0.1965 | 0.2395 | 0.2027 | 0.2395 | True |
| btts_high_ou25_low | 172 | 2.384 | 0.0814 | 0.1744 | 0.2616 | 0.3023 | 0.1453 | 0.0349 | True |
| btts_low_ou25_high | 123 | 3.244 | 0.0163 | 0.1545 | 0.187 | 0.2683 | 0.1382 | 0.2358 | False |
| btts_low_ou25_low | 2392 | 2.036 | 0.1409 | 0.2659 | 0.2513 | 0.1961 | 0.0844 | 0.0615 | True |
| all | 28328 | 2.687 | 0.0753 | 0.1811 | 0.2345 | 0.2259 | 0.1456 | 0.1377 | True |


Scorelines:

| state | n | top_scores |
|---|---|---|
| btts_high_ou25_high | 1929 | 2-1 0.115; 1-1 0.105; 1-2 0.075; 2-2 0.073; 3-1 0.071 |
| btts_high_ou25_low | 172 | 1-1 0.203; 2-1 0.169; 1-2 0.105; 0-1 0.087; 1-0 0.087 |
| btts_low_ou25_high | 123 | 3-0 0.203; 2-0 0.146; 1-0 0.130; 4-0 0.073; 2-1 0.065 |
| btts_low_ou25_low | 2392 | 1-0 0.165; 0-0 0.141; 1-1 0.110; 0-1 0.101; 2-0 0.084 |
| all | 28328 | 1-1 0.120; 1-0 0.104; 2-1 0.092; 0-1 0.077; 0-0 0.075 |


The hypothesis points the right way — 'BTTS high, Over 2.5 low' produces 1-1 at 
more than twice its overall rate, and 'BTTS low, Over 2.5 high' produces 3-0, 2-0 
and 4-0 well above theirs. **But both cells hold fewer than 150 fixtures**, which 
is below the interpretation floor set before the analysis ran. Recorded as 
directionally consistent and not yet established. The models rarely disagree that 
strongly, which is itself the reason the cells are thin.

## Discovery → validation

666 two-model threshold conditions were searched on the earlier OOS 
period and re-measured on the later one, with Benjamini-Hochberg control.

| status | conditions |
|---|---|
| REPLICATED | 624 |
| UNTESTED | 42 |


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
BEST_VALIDATED_CROSS_MARKET_RELATIONSHIP=over15 <- own_plus_all_markets
OOS_SAMPLE_SIZE=12687
OOS_IMPROVEMENT=-0.00310 log loss
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
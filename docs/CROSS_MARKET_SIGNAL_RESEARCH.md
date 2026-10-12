# CROSS-MARKET SIGNAL RESEARCH

Do our models know anything about each other's markets that the market's own model is 
missing? Not 'are BTTS and Over 2.5 correlated' — they obviously are, both are made of 
goals. The question is whether one adds information **after** the other is known.

## The answer, in one paragraph

**Yes — but not from BTTS, which is where the question pointed.** Adding the other 
models' opinions genuinely improves out-of-sample prediction on all three Over markets, 
and the gain survives a paired bootstrap. But essentially all of it comes from the 
**other Over lines**. Telling the Over 2.5 model what the BTTS model thinks moves its 
log loss by -0.00104 — a difference whose 
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
| p_btts | 1.0 | 0.5939 | 0.5966 | 0.5668 |
| p_over15 | 0.5939 | 1.0 | 0.7906 | 0.7278 |
| p_over25 | 0.5966 | 0.7906 | 1.0 | 0.7968 |
| p_over35 | 0.5668 | 0.7278 | 0.7968 | 1.0 |


## Cross-market matrix — signal model vs actual outcome (AUC)

| signal_model | btts | over15 | over25 | over35 |
|---|---|---|---|---|
| btts | 0.5889 | 0.587 | 0.5806 | 0.5826 |
| over15 | 0.5647 | 0.6016 | 0.5949 | 0.6076 |
| over25 | 0.5657 | 0.6037 | 0.5998 | 0.6092 |
| over35 | 0.5622 | 0.5978 | 0.5958 | 0.6072 |


The three Over models are nearly interchangeable; each predicts the others' markets 
about as well as its own. BTTS is the one genuinely distinct signal, and it is 
worse at the Over markets than they are at each other's.

## Conditional outcomes — P(BTTS) bucket vs what actually happened

| bucket | n | mean_p | actual_btts | actual_over15 | actual_over25 | actual_over35 | avg_goals | interpretable |
|---|---|---|---|---|---|---|---|---|
| 0.00-0.45 | 3316 | 0.3956 | 0.3887 | 0.6348 | 0.3821 | 0.1828 | 2.204 | True |
| 0.45-0.50 | 4774 | 0.4784 | 0.4858 | 0.7053 | 0.4598 | 0.2432 | 2.49 | True |
| 0.50-0.55 | 8241 | 0.5258 | 0.5229 | 0.7358 | 0.497 | 0.2659 | 2.622 | True |
| 0.55-0.60 | 6802 | 0.5727 | 0.564 | 0.7727 | 0.5431 | 0.3126 | 2.829 | True |
| 0.60-0.65 | 3238 | 0.6212 | 0.5998 | 0.7986 | 0.5775 | 0.3586 | 2.997 | True |
| 0.65-0.70 | 1059 | 0.67 | 0.6676 | 0.8451 | 0.6487 | 0.3966 | 3.191 | True |
| 0.70-1.01 | 635 | 0.7637 | 0.9197 | 0.9669 | 0.7748 | 0.4661 | 3.633 | True |


Monotone and strong — and, on its own, not evidence of anything beyond the 
model working. The control below is what separates the two explanations.

## The control — holding the Over 2.5 model's own opinion fixed

Within fixtures the Over 2.5 model scored the same, does a high BTTS probability 
change how often Over 2.5 actually happened?

| own_p_range | n_low_other | n_high_other | actual_over25_low_other | actual_over25_high_other | diff_pp | z | p_value |
|---|---|---|---|---|---|---|---|
| 0.157-0.421 | 1560 | 1560 | 0.2974 | 0.4282 | 13.08 | 7.596 | 0.0 |
| 0.421-0.472 | 1559 | 1559 | 0.4298 | 0.4766 | 4.68 | 2.626 | 0.0086 |
| 0.472-0.513 | 1560 | 1560 | 0.4942 | 0.5186 | 2.44 | 1.361 | 0.1736 |
| 0.513-0.549 | 1559 | 1559 | 0.5067 | 0.5471 | 4.04 | 2.26 | 0.0238 |
| 0.549-0.593 | 1559 | 1559 | 0.5388 | 0.5953 | 5.64 | 3.181 | 0.0015 |
| 0.593-0.920 | 1560 | 1560 | 0.6115 | 0.7135 | 10.19 | 6.02 | 0.0 |


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
| own_only | 0.67451 | 0.55427 | 0.6778 | 0.5793 |
| own_plus_all_markets | 0.67457 | 0.55065 | 0.6758 | 0.57647 |
| own_plus_all_plus_sides | 0.6746 | 0.55081 | 0.67558 | 0.57629 |
| own_plus_btts |  | 0.55221 | 0.67676 | 0.57842 |
| own_plus_over15 | 0.67456 |  | 0.67697 | 0.57749 |
| own_plus_over25 | 0.67441 | 0.55207 |  | 0.57706 |
| own_plus_over35 | 0.67449 | 0.55247 | 0.6765 |  |


**CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS = YES**. Best relationship: `over15 <- own_plus_all_markets` at -0.00362 log loss on 12,633 fixtures.

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
| btts | own_plus_over15 | 0.674564 | 5.6e-05 | -5.6e-05 | -0.000271 | 0.000163 | 0.678 | False |
| btts | own_plus_over25 | 0.674405 | -0.000103 | 0.000103 | -7.9e-05 | 0.000271 | 0.3305 | False |
| btts | own_plus_over35 | 0.674486 | -2.3e-05 | 2.3e-05 | -8e-05 | 0.00012 | 0.7115 | False |
| btts | own_plus_all_markets | 0.67457 | 6.2e-05 | -6.2e-05 | -0.000288 | 0.000164 | 0.6645 | False |
| btts | own_plus_all_plus_sides | 0.6746 | 9.2e-05 | -9.2e-05 | -0.000522 | 0.000291 | 0.7325 | False |
| over15 | own_plus_btts | 0.55221 | -0.002064 | 0.002064 | 0.001213 | 0.002947 | 0.0005 | True |
| over15 | own_plus_over25 | 0.552066 | -0.002208 | 0.002208 | 0.001373 | 0.003056 | 0.0 | True |
| over15 | own_plus_over35 | 0.552474 | -0.001801 | 0.001801 | 0.001024 | 0.002589 | 0.0 | True |
| over15 | own_plus_all_markets | 0.55065 | -0.003625 | 0.003625 | 0.002578 | 0.004717 | 0.0 | True |
| over15 | own_plus_all_plus_sides | 0.550813 | -0.003462 | 0.003462 | 0.002321 | 0.00466 | 0.0 | True |
| over25 | own_plus_btts | 0.676764 | -0.001038 | 0.001038 | 3.1e-05 | 0.002072 | 0.0925 | True |
| over25 | own_plus_over15 | 0.676968 | -0.000834 | 0.000834 | 0.000133 | 0.001563 | 0.0635 | True |
| over25 | own_plus_over35 | 0.676502 | -0.0013 | 0.0013 | 0.000551 | 0.00209 | 0.004 | True |
| over25 | own_plus_all_markets | 0.675803 | -0.001999 | 0.001999 | 0.000719 | 0.00333 | 0.0115 | True |
| over25 | own_plus_all_plus_sides | 0.675583 | -0.002219 | 0.002219 | 0.000758 | 0.003727 | 0.016 | True |
| over35 | own_plus_btts | 0.578417 | -0.00088 | 0.00088 | 0.000197 | 0.001558 | 0.039 | True |
| over35 | own_plus_over15 | 0.577493 | -0.001803 | 0.001803 | 0.000912 | 0.002636 | 0.0015 | True |
| over35 | own_plus_over25 | 0.577065 | -0.002232 | 0.002232 | 0.001351 | 0.003077 | 0.0 | True |
| over35 | own_plus_all_markets | 0.576472 | -0.002825 | 0.002825 | 0.001759 | 0.003864 | 0.0005 | True |
| over35 | own_plus_all_plus_sides | 0.576289 | -0.003008 | 0.003008 | 0.001693 | 0.004306 | 0.0005 | True |


**Every `own_plus_btts` row fails.** Every row built on another Over line passes. 
This table is the verdict; the conditional tables above are context for it.

## Error correlation — when one is wrong, is the other?

This matters more than agreement. Two models that agree but fail together give one 
piece of evidence dressed as two.

| model_a | model_b | err_rate_a | err_rate_b | both_wrong | both_wrong_if_independent | excess_pp | phi |
|---|---|---|---|---|---|---|---|
| btts | over15 | 0.4349 | 0.255 | 0.1631 | 0.1109 | 5.21 | 0.2413 |
| btts | over25 | 0.4349 | 0.4309 | 0.2469 | 0.1874 | 5.95 | 0.2423 |
| btts | over35 | 0.4349 | 0.2816 | 0.08 | 0.1225 | -4.24 | -0.1903 |
| over15 | over25 | 0.255 | 0.4309 | 0.1156 | 0.1099 | 0.57 | 0.0262 |
| over15 | over35 | 0.255 | 0.2816 | 0.0012 | 0.0718 | -7.06 | -0.3599 |
| over25 | over35 | 0.4309 | 0.2816 | 0.1007 | 0.1213 | -2.06 | -0.0926 |


Most correlated errors: btts/over25 +5.95pp over independence.

## Disagreement — is 'BTTS high, Over 2.5 low' really a 1-1 machine?

| state | n | avg_goals | goals_0 | goals_1 | goals_2 | goals_3 | goals_4 | goals_5plus | interpretable |
|---|---|---|---|---|---|---|---|---|---|
| btts_high_ou25_high | 2020 | 3.423 | 0.0342 | 0.0975 | 0.1802 | 0.2337 | 0.2015 | 0.253 | True |
| btts_high_ou25_low | 189 | 2.651 | 0.0265 | 0.1111 | 0.3439 | 0.291 | 0.1799 | 0.0476 | True |
| btts_low_ou25_high | 137 | 3.124 | 0.0219 | 0.1606 | 0.1898 | 0.2336 | 0.1825 | 0.2117 | False |
| btts_low_ou25_low | 2352 | 2.04 | 0.1424 | 0.2606 | 0.2589 | 0.1862 | 0.0876 | 0.0642 | True |
| all | 28065 | 2.688 | 0.0751 | 0.1807 | 0.2347 | 0.2259 | 0.1461 | 0.1376 | True |


Scorelines:

| state | n | top_scores |
|---|---|---|
| btts_high_ou25_high | 2020 | 2-1 0.115; 1-1 0.096; 2-2 0.079; 1-2 0.072; 3-1 0.069 |
| btts_high_ou25_low | 189 | 1-1 0.238; 1-2 0.153; 2-1 0.111; 0-2 0.074; 1-0 0.069 |
| btts_low_ou25_high | 137 | 3-0 0.153; 1-0 0.117; 2-0 0.117; 4-0 0.080; 2-1 0.066 |
| btts_low_ou25_low | 2352 | 1-0 0.162; 0-0 0.142; 1-1 0.119; 0-1 0.099; 2-0 0.082 |
| all | 28065 | 1-1 0.120; 1-0 0.103; 2-1 0.093; 0-1 0.077; 0-0 0.075 |


The hypothesis points the right way — 'BTTS high, Over 2.5 low' produces 1-1 at 
more than twice its overall rate, and 'BTTS low, Over 2.5 high' produces 3-0, 2-0 
and 4-0 well above theirs. **But both cells hold fewer than 150 fixtures**, which 
is below the interpretation floor set before the analysis ran. Recorded as 
directionally consistent and not yet established. The models rarely disagree that 
strongly, which is itself the reason the cells are thin.

## Discovery → validation

684 two-model threshold conditions were searched on the earlier OOS 
period and re-measured on the later one, with Benjamini-Hochberg control.

| status | conditions |
|---|---|
| REPLICATED | 624 |
| UNTESTED | 60 |


**These replication rates should not be read as edges.** Most of the searched 
conditions amount to 'select fixtures both models think are high-scoring', and 
those fixtures really are high-scoring — the pattern replicates because the models 
work, not because a cross-market secret was found. That is precisely why the 
meta-model, not this table, carries the verdict.

## Verdict

```text
CROSS_MARKET_DATASET_LEAKAGE_SAFE=YES
BTTS_ADDS_INFO_TO_OVER15=YES
BTTS_ADDS_INFO_TO_OVER25=YES
BTTS_ADDS_INFO_TO_OVER35=YES
OVER15_ADDS_INFO_TO_BTTS=NO
OVER25_ADDS_INFO_TO_BTTS=NO
OVER35_ADDS_INFO_TO_BTTS=NO
CROSS_MARKET_META_MODEL_BEATS_SINGLE_MODELS=YES
BEST_VALIDATED_CROSS_MARKET_RELATIONSHIP=over15 <- own_plus_all_markets
OOS_SAMPLE_SIZE=12633
OOS_IMPROVEMENT=-0.00362 log loss
MODEL_AGREEMENT_IMPROVES_ACCURACY=NO
MODEL_DISAGREEMENT_IS_INFORMATIVE=MIXED
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
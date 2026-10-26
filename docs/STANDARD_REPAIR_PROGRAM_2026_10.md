# Standard Format Repair programme — October 2026

Owner brief 2026-10-26 part B, extended the same day into a continuous per-league × market × side loop.
**Research only. Nothing here changes v9, its thresholds, its tips or its dashboard.** New Format is untouched.

## Verdict in plain English

**No model we can build today adds reliable information to the Standard-league market price.**
We tested 18 model designs per market (54 in all, plus one ablation-selected model per market), chronologically,
against a strong de-vigged market baseline. None beats the market on the untouched holdout under the rule frozen
before the holdout was run. **Nothing is pre-registered for forward testing,** because the brief allows that only for
a candidate that beats the market on holdout.

A worked example of the size of the effect: the best O/U 2.5 challenger lowers average log loss by 0.0007, from
0.6774 to 0.6767. That is about 1/1000th of the loss, and the 95% interval runs from a 0.0018 gain to a 0.0004
*loss*. Across 3,927 holdout matches, that is about one extra correct "lean" in every 1,400 matches. You cannot
separate it from luck, and it would not survive the bookmaker margin.

What the programme *did* establish:

| market | verdict | v9 (current model) vs market | best challenger on holdout |
|---|---|---|---|
| O/U 2.5 | **No incremental signal.** The market wins. | **worse**: +0.0114 log loss, 95% CI [+0.0069, +0.0160] | LGBM residual −0.0007 [−0.0018, +0.0004], q 0.64 |
| BTTS | **No incremental signal** over a market-implied BTTS (no real historical BTTS prices) | **worse**: +0.0045 [+0.0017, +0.0074] | market + goal features (recency) −0.0006 [−0.0014, +0.0003], q 0.64 |
| Over 1.5 | **Not proven.** One arm's CI excludes zero, but it lost on validation and fails multiplicity. The baseline is synthetic. | **worse**: +0.0096 [+0.0059, +0.0135] | LGBM residual (full) −0.0013 [−0.0023, −0.0003], **q 0.26**, validation **+0.0010** |

1. **v9's Standard model is worse than the market on every market** (holdout and forward). On first-sight rows since
   2026-08-17, the *served* model also loses on O/U 2.5: +0.0120 log loss [+0.0014, +0.0217], n=443, 9 weeks. Its
   probabilities are squeezed: their spread is about 0.02, against about 0.085 for the market. Its calibration slope is about 2. **Recalibrating v9
   does not help** (V9_CAL is worse still), because recalibration cannot add information the model does not have.
2. **Absolute-probability models lose to the price whatever the learner** (HGB, logistic, v9's ensemble). Every
   model that is not anchored on the market is significantly worse than it.
3. **Market-anchored residual models land within ±0.001 of the market.** Market-anchored means
   logit(p) = a + b·logit(market) + f(features). That is the honest ceiling of what team-form data adds after the price today.
4. **Feature ablation:** shots, shot quality, xG, corners/fouls, half-time stats, rest/congestion, book dispersion,
   odds band, interactions and **v9's own residual** all *hurt or do nothing* after the market. They are unstable
   across the four validation quarters. Only the **league scoring environment**, a rolling as-of measure of how the
   league has scored relative to what the market implied, survives on all three markets. Team goal form also survives
   for O/U 1.5 and BTTS. None of these survivors passes on holdout after multiplicity.
5. **Information that arrives late is worth 3–4 times more than any model.** The closing price beats the pre-match
   price by 0.0025 log loss (O/U 2.5, all Standard leagues). That gain is larger than any residual model's. Whatever
   moves the line between Friday and kickoff (team news) is where incremental information lives. The Oct-19 lineups
   study found no effect from lineups as model inputs, so this is a pointer, not a promise.

## Most repairable vs no incremental signal

* **Most repairable: none passes, but the most structured residual is the per-league market miscalibration on O/U 2.5.**
  The market is *under-confident* in **League One** (calibration slope 1.33 on validation, 1.19 on holdout) and
  **Ligue 2** (1.53 / 1.22). It is consistent in both periods. A League One / Ligue 2 market-stretch is a clean,
  prespecifiable next experiment. The pooled per-league-slope arm (ridge partial pooling) did not beat the market
  overall, and per-league slopes elsewhere flip sign between periods (League Two 1.17 → 0.44; Bundesliga 2 1.55 → 0.53).
  This hypothesis therefore has to be scored on an **untouched** block (2026-Q4), never re-fitted on this holdout.
* **Over 1.5 (all leagues)** is the only market where the residual models are on the right side on holdout as a family.
  But there is **no real historical O/U 1.5 price**: the baseline is the market's goal expectation inverted from
  1X2 + O/U 2.5. Real first-sight quotes cover only 0.6% of fixtures, so price capture, not modelling, is the
  constraint.
* **No incremental signal yet:** O/U 2.5 and BTTS pooled. Per track, v9 is significantly below the market on
  Championship BTTS NO, League One O/U 2.5 UNDER and BTTS NO, and La Liga 2 BTTS NO.

## Design (frozen before the holdout was scored)

* **Data.** v9's own Standard training frame (alias-deduplicated, 18,571 matches 2023-08 → 2026-10), joined to
  football-data **pre-match** prices (16,906 matches). The pre-match prices are the columns without the closing "C"
  infix: Bet365, Pinnacle (missing in 2026/27), Betfair exchange (from 2024/25) and the book average. They are
  recorded Friday/Tuesday before kickoff. Audit: pre-match equals closing on only 7.1% of rows, so these are genuinely
  different prices. **The frame's own `odds_over25` is the closing price on 99.8% of rows.** It and every odds-derived
  column are excluded from challenger features. v9's reproduction keeps them, because v9 trains on them; that can only
  flatter v9.
* **Splits.** train 2023-08 → 2024-12; **validation 2025** (4 quarterly blocks); **holdout 2026-01 → 2026-10-14**
  (n=3,927, 34 matchday-weeks). Every block is scored by a model fitted strictly before it (expanding walk-forward,
  no same-block fit/score). Grids, the market baseline variant and feature selection use validation only.
* **Market baseline.** The best market-only variant on validation, chosen from book-average power/proportional,
  Bet365, per-book median consensus, and consensus with walk-forward Platt recalibration. The winner was
  **MARKET_CAL** (consensus, Platt-recalibrated) for all three markets. This is a deliberately strong baseline.
  BTTS / O/U 1.5 have **no historical two-sided quotes** in Standard leagues: odds_btts is one-sided on 15% of rows,
  and O/U 1.5 appears on fewer than 1%. Their market is the bookmakers' goal expectation, inverted from de-vigged
  1X2 + O/U 2.5 under independent Poisson and then recalibrated.
* **v9 arm.** v9's own `train()` (LogReg + GB + meta-stack), v9's 42 champion columns, season decay weights, quarterly
  walk-forward, Standard rows only (`src/studies/standard_repair/v9_probe.py`, run inside the v9 checkout, read-only).
* **Rule.** An arm beats the market if it is validation-selected **and** holdout paired ΔLL < 0 **and** the 95%
  matchday-week block-bootstrap CI upper bound < 0 **and** the Benjamini-Hochberg q ≤ 0.05. BH runs across all
  57 tests: 18 model arms × 3 markets, plus the ablation-selected model for each market. Betting metrics are reported afterwards and select nothing.

## Benchmark tables (holdout; ΔLL = arm − market; negative = better than market)

### O/U 2.5 — baseline MARKET_CAL, holdout n=3,927 (34 weeks), validation n=5,375

| arm | validation ΔLL | holdout LL | holdout ΔLL | 95% CI | BH q | cal. slope | ECE |
|---|---|---|---|---|---|---|---|
| **MARKET_CAL** (baseline) | – | 0.67735 | – | – | – | 1.004 | 0.026 |
| LGBM_RESID_SIMPLE | +0.00033 | 0.67665 | −0.00070 | [−0.00179, +0.00039] | 0.64 | 1.012 | 0.028 |
| MKT_NO_NOISY | +0.00015 | 0.67678 | −0.00057 | [−0.00147, +0.00029] | 0.64 | 1.011 | 0.016 |
| MKT_SIMPLE | −0.00029 | 0.67692 | −0.00043 | [−0.00132, +0.00042] | 0.64 | 1.007 | 0.024 |
| MKT_KITCHEN | −0.00043 | 0.67698 | −0.00037 | [−0.00173, +0.00088] | 0.73 | 1.001 | 0.018 |
| MKT_SIMPLE_RECENCY | −0.00037 | 0.67706 | −0.00029 | [−0.00166, +0.00110] | 0.75 | 0.986 | 0.019 |
| LGBM_RESID_FULL | +0.00043 | 0.67710 | −0.00024 | [−0.00139, +0.00080] | 0.75 | 0.997 | 0.018 |
| MKT_POISSON | +0.00005 | 0.67731 | −0.00004 | [−0.00017, +0.00010] | 0.73 | 1.004 | 0.026 |
| MKT_V9_RESID (lightweight Wowza residual) | −0.00001 | 0.67745 | +0.00010 | [−0.00007, +0.00027] | 1.0 | 1.009 | 0.025 |
| MKT_V9_BANDS (disagreement bands as features) | +0.00011 | 0.67745 | +0.00010 | [−0.00008, +0.00029] | 1.0 | 0.999 | 0.025 |
| MKT_FULL | +0.00159 | 0.67746 | +0.00011 | [−0.00110, +0.00115] | 1.0 | 0.977 | 0.021 |
| MKT_LEAGUE_SLOPE (per-league calibration, pooled) | −0.00053 | 0.67768 | +0.00033 | [−0.00048, +0.00119] | 1.0 | 0.965 | 0.025 |
| MKT_ENV (validation-selected challenger) | −0.00088 | 0.67779 | +0.00044 | [−0.00087, +0.00161] | 1.0 | 0.964 | 0.020 |
| MKT_LEAGUE | −0.00061 | 0.67808 | +0.00073 | [−0.00062, +0.00213] | 1.0 | 0.926 | 0.028 |
| HGB_ANCHOR_CAL | +0.00277 | 0.67852 | +0.00117 | [−0.00036, +0.00271] | 1.0 | 1.054 | 0.021 |
| LR_ABS_SIMPLE (no market) | +0.01035 | 0.68518 | +0.00783 | [+0.00378, +0.01200] | 1.0 | 1.663 | 0.032 |
| HGB_ABS_CAL (no market) | +0.01022 | 0.68529 | +0.00794 | [+0.00399, +0.01195] | 1.0 | 1.360 | 0.028 |
| **V9** | +0.01206 | 0.68876 | **+0.01141** | [+0.00690, +0.01597] | 1.0 | 2.018 | 0.025 |
| V9_CAL | +0.01390 | 0.69096 | +0.01361 | [+0.00886, +0.01854] | 1.0 | 3.947 | 0.036 |
| ABLATION_SELECTED (league env) | – | – | −0.00006 | [−0.00075, +0.00062] | 0.94 | – | – |

Market-only variants (holdout ΔLL vs MARKET_CAL): book-average power +0.00037, consensus power +0.00045,
proportional +0.00062, Bet365 +0.00067.

### BTTS — baseline MARKET_CAL (market-implied BTTS), same rows

| arm | validation ΔLL | holdout ΔLL | 95% CI | BH q | cal. slope |
|---|---|---|---|---|---|
| MKT_SIMPLE_RECENCY | +0.00000 | −0.00055 | [−0.00135, +0.00029] | 0.64 | 0.982 |
| MKT_SIMPLE | −0.00002 | −0.00045 | [−0.00090, +0.00004] | 0.64 | 0.975 |
| MKT_KITCHEN | −0.00016 | −0.00039 | [−0.00129, +0.00057] | 0.64 | 0.951 |
| MKT_LEAGUE_SLOPE | −0.00007 | −0.00035 | [−0.00128, +0.00054] | 0.65 | 0.938 |
| MKT_NO_NOISY | +0.00057 | −0.00033 | [−0.00086, +0.00020] | 0.64 | 0.956 |
| MKT_LEAGUE | −0.00006 | −0.00010 | [−0.00030, +0.00010] | 0.64 | 0.957 |
| LGBM_RESID_FULL | −0.00026 | −0.00003 | [−0.00136, +0.00113] | 1.0 | 0.858 |
| MKT_V9_RESID | +0.00023 | +0.00002 | [−0.00003, +0.00008] | 1.0 | 0.966 |
| MKT_V9_BANDS | +0.00026 | +0.00003 | [−0.00004, +0.00011] | 1.0 | 0.966 |
| MKT_FULL | +0.00118 | +0.00003 | [−0.00086, +0.00102] | 1.0 | 0.915 |
| LGBM_RESID_SIMPLE | +0.00026 | +0.00013 | [−0.00096, +0.00121] | 1.0 | 0.849 |
| MKT_ENV (validation-selected) | −0.00034 | +0.00017 | [−0.00032, +0.00068] | 1.0 | 0.927 |
| MKT_POISSON | −0.00002 | +0.00019 | [−0.00028, +0.00064] | 1.0 | 0.938 |
| HGB_ANCHOR_CAL | +0.00234 | +0.00141 | [−0.00011, +0.00301] | 1.0 | 1.059 |
| LR_ABS_SIMPLE | +0.00377 | +0.00327 | [+0.00088, +0.00594] | 1.0 | 1.446 |
| HGB_ABS_CAL | +0.00396 | +0.00358 | [+0.00125, +0.00584] | 1.0 | 0.869 |
| **V9** | +0.00443 | **+0.00453** | [+0.00174, +0.00744] | 1.0 | 2.073 |
| V9_CAL | +0.00460 | +0.00505 | [+0.00223, +0.00800] | 1.0 | 3.125 |
| ABLATION_SELECTED | – | +0.00012 | [−0.00057, +0.00083] | 1.0 | – |

### Over 1.5 — baseline MARKET_CAL (market-implied O/U 1.5), same rows

| arm | validation ΔLL | holdout ΔLL | 95% CI | BH q | cal. slope |
|---|---|---|---|---|---|
| LGBM_RESID_FULL | **+0.00101** | −0.00128 | [−0.00230, −0.00034] | 0.26 | 1.082 |
| LGBM_RESID_SIMPLE | +0.00032 | −0.00073 | [−0.00179, +0.00029] | 0.64 | 1.043 |
| MKT_ENV (validation-selected) | −0.00057 | −0.00068 | [−0.00179, +0.00040] | 0.64 | 0.990 |
| MKT_SIMPLE_RECENCY | +0.00017 | −0.00057 | [−0.00126, +0.00012] | 0.64 | 1.004 |
| MKT_KITCHEN | +0.00044 | −0.00044 | [−0.00128, +0.00037] | 0.64 | 1.015 |
| MKT_LEAGUE_SLOPE | −0.00019 | −0.00042 | [−0.00133, +0.00060] | 0.64 | 0.992 |
| MKT_FULL | +0.00179 | −0.00039 | [−0.00126, +0.00044] | 0.64 | 1.014 |
| MKT_LEAGUE | −0.00027 | −0.00036 | [−0.00103, +0.00039] | 0.64 | 1.006 |
| MKT_SIMPLE | −0.00003 | −0.00029 | [−0.00089, +0.00037] | 0.64 | 1.018 |
| HGB_ANCHOR_CAL | +0.00459 | −0.00026 | [−0.00163, +0.00128] | 0.86 | 1.073 |
| MKT_NO_NOISY | +0.00114 | −0.00024 | [−0.00083, +0.00036] | 0.64 | 1.012 |
| MKT_V9_BANDS / MKT_V9_RESID / MKT_POISSON | ≈0 | +0.00001 … +0.00004 | straddle 0 | 1.0 | ≈1.0 |
| LR_ABS_SIMPLE / HGB_ABS_CAL | +0.007 / +0.010 | +0.0066 / +0.0069 | above 0 | 1.0 | 1.08 |
| **V9** / V9_CAL | +0.011 | **+0.0096** / +0.0099 | [+0.0059, +0.0135] | 1.0 | 1.57 |
| ABLATION_SELECTED (rolling goals + league env) | – | −0.00061 | [−0.00114, −0.00008] | 0.34 | – |

## Feature ablation (validation only; `output/standard_repair/ablation.json`)

Market-residual logistic, fixed ridge. A group is **kept** only if adding it to the market improves validation log loss
**and** the gain has the same sign in at least 3 of the 4 validation quarters.

| group | O/U 2.5 | BTTS | O/U 1.5 |
|---|---|---|---|
| league scoring environment (as-of realised vs market-implied) | **KEEP** (3/4) | **KEEP** (4/4) | **KEEP** (3/4) |
| rolling goals / conceded | remove | remove | **KEEP** |
| season home/away strength | remove | **KEEP** | remove |
| home advantage | remove | **KEEP** | remove |
| attack/defence strength, Poisson-vs-market, interactions | remove | remove | remove |
| shots & shot quality, xG, corners/fouls, half-time, rest/congestion, book dispersion, odds band, v9 residual | remove (most *hurt*, CI above 0) | remove | remove |

**Removed** (noise or unstable after the price): shots/SOT ratio, inside-box, xG, corners, fouls, all half-time
features, rest days, book dispersion, odds-band dummies, attack×defence interactions, v9's residual.
**Added and kept:** the as-of league scoring environment (new in this programme).
Market movement could not be tested historically without using the closing price, which is post-entry information.

## Per-league market-efficiency profile (O/U 2.5, holdout)

| league | market LL | market Brier | market cal. slope | v9 − market ΔLL | close − pre-match ΔLL | book dispersion | CLV availability |
|---|---|---|---|---|---|---|---|
| Championship | 0.6839 | 0.2453 | 1.06 | +0.0054 | −0.0006 | 0.0045 | 1.00 |
| League One | 0.6800 | 0.2434 | 1.19 | +0.0133 | −0.0016 | 0.0043 | 1.00 |
| League Two | 0.6940 | 0.2504 | 0.44 | +0.0035 | −0.0009 | 0.0048 | 1.00 |
| Bundesliga 2 | 0.6754 | 0.2413 | 0.53 | +0.0100 | −0.0016 | 0.0053 | 1.00 |
| La Liga 2 | 0.6825 | 0.2447 | 1.06 | +0.0077 | +0.0012 | 0.0048 | 1.00 |
| Ligue 2 | 0.6804 | 0.2437 | 1.22 | +0.0090 | +0.0004 | 0.0045 | 1.00 |
| Serie B | 0.6850 | 0.2460 | 1.18 | +0.0091 | +0.0021 | 0.0043 | 1.00 |

## Repair scorecard (35 tracks; full detail in `output/standard_repair/scorecard.json`)

ΔLL is on the rows where the model leans to that side, relative to the market. ROI is flat 1u at the 3% VALUABLE floor
and the pre-match book-average price. CLV is that price divided by the closing book-average price, minus 1. ROI and
CLV are diagnostic only. BTTS / O/U 1.5 have no historical price, so their ROI and CLV are n/a. "Forward" means the
served v9 at first sight vs real quotes, 2026-08-17 onwards.

| track | v9 lean n | v9 ΔLL | v9 ROI @3% | v9 CLV | challenger ΔLL (MKT_ENV) | forward n | forward ΔLL | diagnosis |
|---|---|---|---|---|---|---|---|---|
| Championship OU25 OVER | 202 | +0.0030 | +0.004 | +0.001 | +0.0011 | 42 | −0.0093 | REGIME_DRIFT, NO_EDGE_YET |
| Championship OU25 UNDER | 175 | +0.0082 | −0.129 | −0.007 | +0.0017 | 38 | +0.0134 | CALIBRATION_FAILURE, NO_EDGE_YET |
| Championship BTTS YES | 200 | +0.0020 | n/a | n/a | −0.0003 | 20 | +0.0093 | NO_EDGE_YET |
| Championship BTTS NO | 177 | +0.0149 | n/a | n/a | +0.0006 | 60 | +0.0164 | MODEL_BELOW_MARKET, CALIBRATION_FAILURE |
| Championship OU15 OVER | 170 | +0.0026 | n/a | n/a | +0.0019 | 0 | – | PRICE_QUALITY_PROBLEM |
| League One OU25 OVER | 194 | +0.0068 | −0.246 | +0.007 | −0.0017 | 27 | +0.0321 | CALIBRATION_FAILURE, MODEL_ABOVE_MARKET_SELECTION_BAD, ODDS_BAND_DEPENDENCE |
| League One OU25 UNDER | 183 | +0.0202 | −0.063 | −0.017 | +0.0003 | 45 | +0.0131 | MODEL_BELOW_MARKET, CALIBRATION_FAILURE |
| League One BTTS YES | 169 | +0.0055 | n/a | n/a | −0.0007 | 15 | +0.0097 | NO_EDGE_YET |
| League One BTTS NO | 208 | +0.0118 | n/a | n/a | +0.0004 | 57 | +0.0101 | MODEL_BELOW_MARKET, CALIBRATION_FAILURE |
| League One OU15 OVER | 176 | +0.0095 | n/a | n/a | −0.0010 | 0 | – | PRICE_QUALITY_PROBLEM, SIDE_SPECIFIC_EDGE* |
| League Two OU25 OVER | 232 | +0.0064 | −0.213 | +0.000 | +0.0019 | 40 | +0.0252 | CALIBRATION_FAILURE |
| League Two OU25 UNDER | 149 | −0.0010 | −0.128 | +0.007 | −0.0008 | 42 | +0.0048 | INSUFFICIENT_SAMPLE |
| League Two BTTS YES | 202 | +0.0027 | n/a | n/a | +0.0007 | 38 | +0.0075 | NO_EDGE_YET |
| League Two BTTS NO | 179 | −0.0001 | n/a | n/a | +0.0003 | 44 | +0.0088 | NO_EDGE_YET |
| League Two OU15 OVER | 215 | +0.0059 | n/a | n/a | +0.0035 | 0 | – | PRICE_QUALITY_PROBLEM, CALIBRATION_FAILURE |
| Bundesliga 2 OU25 OVER | 9 | −0.0168 | n/a | −0.000 | −0.0007 | 9 | +0.0217 | INSUFFICIENT_SAMPLE |
| Bundesliga 2 OU25 UNDER | 188 | +0.0113 | −0.012 | +0.007 | +0.0009 | 36 | +0.0541 | CALIBRATION_FAILURE |
| Bundesliga 2 BTTS YES | 8 | −0.0178 | n/a | n/a | +0.0003 | 0 | – | INSUFFICIENT_SAMPLE |
| Bundesliga 2 BTTS NO | 189 | +0.0078 | n/a | n/a | +0.0020 | 43 | +0.0086 | CALIBRATION_FAILURE |
| Bundesliga 2 OU15 OVER | 7 | −0.0244 | n/a | n/a | −0.0007 | 0 | – | INSUFFICIENT_SAMPLE, PRICE_QUALITY_PROBLEM |
| La Liga 2 OU25 OVER | 218 | +0.0103 | −0.075 | +0.001 | −0.0026 | 47 | −0.0040 | MODEL_ABOVE_MARKET_SELECTION_BAD |
| La Liga 2 OU25 UNDER | 128 | +0.0031 | +0.194 | −0.004 | −0.0028 | 18 | −0.0002 | INSUFFICIENT_SAMPLE, CALIBRATION_FAILURE, REGIME_DRIFT |
| La Liga 2 BTTS YES | 220 | +0.0045 | n/a | n/a | −0.0022 | 43 | −0.0087 | SIDE_SPECIFIC_EDGE* |
| La Liga 2 BTTS NO | 126 | +0.0211 | n/a | n/a | −0.0028 | 22 | −0.0215 | INSUFFICIENT_SAMPLE, MODEL_BELOW_MARKET, … |
| La Liga 2 OU15 OVER | 212 | +0.0146 | n/a | n/a | −0.0022 | 2 | – | PRICE_QUALITY_PROBLEM, SIDE_SPECIFIC_EDGE* |
| Ligue 2 OU25 OVER | 153 | +0.0110 | −0.078 | +0.004 | +0.0008 | 27 | +0.0417 | CALIBRATION_FAILURE, REGIME_DRIFT |
| Ligue 2 OU25 UNDER | 70 | +0.0044 | −0.163 | −0.009 | −0.0035 | 21 | −0.0087 | INSUFFICIENT_SAMPLE, SIDE_SPECIFIC_EDGE* |
| Ligue 2 BTTS YES / NO | 143 / 80 | −0.0002 / −0.0047 | n/a | n/a | +0.0015 / +0.0009 | 16 / 22 | −0.025 / +0.009 | INSUFFICIENT_SAMPLE, REGIME_DRIFT |
| Ligue 2 OU15 OVER | 146 | +0.0050 | n/a | n/a | −0.0019 | 0 | – | INSUFFICIENT_SAMPLE, PRICE_QUALITY_PROBLEM |
| Serie B OU25 OVER | 187 | +0.0042 | +0.011 | +0.014 | −0.0024 | 42 | −0.0123 | NO_EDGE_YET |
| Serie B OU25 UNDER | 70 | +0.0221 | −0.576 | −0.004 | −0.0087 | 9 | +0.0196 | INSUFFICIENT_SAMPLE, CALIBRATION_FAILURE |
| Serie B BTTS YES | 188 | −0.0006 | n/a | n/a | −0.0009 | 41 | −0.0214 | NO_EDGE_YET |
| Serie B BTTS NO | 69 | +0.0105 | n/a | n/a | −0.0005 | 9 | +0.0030 | INSUFFICIENT_SAMPLE, CALIBRATION_FAILURE |
| Serie B OU15 OVER | 174 | −0.0008 | n/a | n/a | −0.0036 | 0 | – | PRICE_QUALITY_PROBLEM |

\* SIDE_SPECIFIC_EDGE is a per-track 90%-CI flag with no multiplicity correction. With 35 tracks, about 2 such flags are
expected by chance alone, so they are **leads to re-test on an untouched block, not findings.**

The scorecard also carries, per track: odds bands (1.50–1.70 … 2.40+), disagreement bands (0–2 … 10pp+) with win rate,
ΔLL, ΔBrier, ROI and CLV, and a monotonicity test. It also carries the weekly Top-5 rank panel
(v9 `output/league_weekly_research.csv`; 3–4 settled rows per track so far, so INSUFFICIENT) and the forward
first-sight block. The disagreement bands are **not monotone** in any well-sampled track: bigger disagreement with the
market does not mean better results. That matches the earlier "tier ladder carries no information" finding.

## What deserves a preregistered forward test

**Nothing, under the brief's own condition** (beat the market on holdout). `registry/standard_repair/registration_v1.json`
was deliberately **not** written. The workflow evaluates forward evidence for the served model only.

The three highest-value next experiments. Each gets a new ID, and each is scored on the 2026-Q4 untouched block
(available January 2027) with **no re-selection**:

1. **STD-REPAIR-LEAGUE1+LIGUE2-OU25-MARKET-STRETCH-V1.** Hypothesis: the O/U 2.5 market is under-confident in
   League One and Ligue 2. The calibration slope was above 1 in both validation and holdout. Model: logit(p) =
   logit(market) × (1 + s) with one shrunken s per league, fitted on data before 2026-10-01. It is the simplest possible
   repair and needs no team data.
2. **STD-REPAIR-POOLED-OU15-ABLATION_SELECTED-V1 / LGBM_RESID_FULL, frozen as they are now.** Re-score them on 2026-Q4
   and, more importantly, on **real** O/U 1.5 first-sight quotes. That first needs O/U 1.5 capture in the Standard
   leagues: forward coverage is 0.6% of fixtures today. Without real quotes, an O/U 1.5 "win" is a win over a proxy.
3. **Late-information residual.** The pre-match → close move carries 0.0025 log loss of information, more than any
   model. Test whether as-of team-news signals (Pro `team_news`, injuries at first sight) predict the *direction of the
   line move* rather than the result. A model that anticipates the close is the realistic path to positive CLV.

## Outputs, loop and registry

* Code: `src/studies/standard_repair/` (`data`, `candidates`, `evaluate`, `ablation`, `forward`, `scorecard`,
  `registry`, `report`, `v9_probe`). Commands: `python -m src.studies.standard_repair {build|run|forward|scorecard|weekly|monthly}`.
  `ablation` runs as `python -m src.studies.standard_repair.ablation`.
* Results: `output/standard_repair/results.json` and `results.csv` (all arms, both periods, CIs, BH q),
  `ablation.json`, `scorecard.json` and `scorecard.csv` (**the reader for the v9 League Repair Lab**; no v9 page was
  edited), `forward_first_sight.csv`.
* Weekly loop: `.github/workflows/pro_standard_repair.yml` runs Monday 07:40 UTC and is tolerant, with per-file
  staging. It writes `output/standard_repair_weekly.json` and `output/standard_repair/WEEKLY.md` and appends to
  `scorecard_history.jsonl`. On the first Monday of each month it also writes `monthly_YYYY-MM.{json,md}`
  (improved/degraded tracks, models beating the market, positive-CLV selection rules, tracks ready for promotion,
  experiments to kill). CI has no v9 training frame, so the historical blocks are carried forward from the committed
  scorecard and only forward / rank-panel evidence is refreshed. The benchmark is re-run on a workstation.
* Registry: `registry/standard_repair/experiments.json` holds 92 experiments: 54 pooled arms, 3 ablation-selected
  models and 35 tracks. Decisions: 12 REJECTED_BELOW_MARKET, 19 REJECTED_INCONSISTENT, 12 REJECTED_NO_INCREMENTAL_SIGNAL,
  12 NO_INCREMENTAL_SIGNAL_CONSISTENT_SIGN, 2 NO_INCREMENTAL_SIGNAL_AFTER_MULTIPLICITY, 31 NO_EDGE_YET and 4
  CONTINUE_RESEARCH.
  Each ID is write-once; a material change gets a new ID. `journey.jsonl` is the append-only per-track learning
  journey, at V1.
* Ladder: every track sits at **RESEARCH_REPAIR**. Promotion (CHALLENGER_READY → … → ACTIVE) is owned by part A in v9
  and needs a preregistered exit rule.

## Caveats

* The holdout is about 9.5 months, including the start of 2026/27 (34 matchday-weeks). It is enough to rule out
  effects of about 0.002 log loss, not 0.0005.
* The BTTS / O/U 1.5 baselines are synthetic (market-implied via Poisson). The conclusions for those two markets are
  about information over the market's *goal expectation*, not over a quoted BTTS / O/U 1.5 price.
* v9's historical arm is a reproduction: v9's recipe, Standard-only, trained on CI-like data. The served model is
  measured separately on first-sight rows and agrees: +0.012 log loss on O/U 2.5.
* Local data: v9's frame from 2023-08 (the frame Pro studies use). As CLAUDE.md notes, CI trains v9 on less data than
  local. That does not affect this study, which never trains in CI.

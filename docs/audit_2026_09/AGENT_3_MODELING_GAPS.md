# AGENT 3 — Football Modeling Audit

**Date:** 2026-09-10 · **Scope:** v9 modelling (read-only), v10 `src/combo` model assets · **Python:** `v9/.venv` (pandas 3.0.3)

---

## HEADLINE

`edge = p_model − 1/odds` is not a model signal. `p_over25` is confined to **[0.333, 0.552], std 0.0402**
while the de-vigged market spans **[0.225, 0.792], std 0.0746**, and the two correlate at only **0.269** — so
the variance of `edge` is dominated by the price, not the model (`corr(edge, 1/odds) = −0.538` vs
`corr(edge, p_model) = +0.193`; `spearman(edge, odds_taken) = +0.587, p≈0`). Mean odds taken rise
monotonically with tier: VALUABLE 2.338 → MARKSMAN 2.744 → SNIPER 2.848. Flat-bet ROI in these leagues
falls monotonically as the price lengthens (UNDER −6.4% → −9.4%). **The tier ladder is a price ladder
pointed the wrong way**: SNIPER preferentially selects the worst-priced bets on the board. And on
12,187 walk-forward rows the model adds **nothing** beyond the price — bootstrap residual Δlog-loss
**−0.00005, CI95 [−0.00063, +0.00045]**.

That is the −91.63u. It is not a threshold-calibration problem, and it will not be fixed by moving a threshold.

---

## FINDINGS

| # | Finding | Evidence | Conf | Impact | Fix |
|---|---|---|---|---|---|
| 1 | Model adds zero information beyond the price (standard) | residual Δlogloss −0.00005, CI95 [−0.00063,+0.00045], n=12,187 | PROVEN | CRITICAL | — |
| 2 | `edge` is a longshot selector, not a model signal | corr(edge,1/odds)=−0.538 vs corr(edge,p_model)=+0.193; spearman(edge,odds)=+0.587 | PROVEN | CRITICAL | WEEKS |
| 3 | Deployed thresholds are env overrides, not config | `predict.yml:190-192` LEAGUE_SNIPER_CAP=0.12, MARKSMAN=0.08, VALUABLE=0.03 | PROVEN | CRITICAL | HOURS |
| 4 | COVID exclusion matches 0 rows; decay weighting inert | 0 of 37,623; 7,112 COVID rows (18.9%) retained; 1 distinct weight (1.0) | PROVEN | HIGH | HOURS |
| 5 | New-format model is worse than a constant | logloss 0.69328 vs constant 0.69122; AUC 0.50752; residual Δ **+0.00040** | PROVEN | CRITICAL | — |
| 6 | Deployed predictor has no honest metric anywhere | `model.py:238-254` meta fit on `y_test`, scored on same rows; `metrics["__meta__"]={}` | PROVEN | HIGH | DAYS |
| 7 | 23 of 65 declared features never reach the model | `feature_cols` len 42 (STD) / 27 (NF) vs FEATURE_COLS 65 | PROVEN | HIGH | DAYS |
| 8 | `retrain.py` passes no sample weights at all | `retrain.py:371` `train_model(std_valid)` — no `sample_weight` | PROVEN | MEDIUM | HOURS |
| 9 | Ligue 2 is bet but has 0 CI training rows | `fd_history.parquet`: Ligue 2 absent; 10 of 17 STD leagues absent | PROVEN | HIGH | DAYS |
| 10 | `MAX_OU_ODDS` does not exist | 0 refs in v9 `*.py`/`*.yml`; CLAUDE.md documents it as a guard | PROVEN | MEDIUM | HOURS |
| 11 | v9's "Dixon-Coles" is a fixed transform of 2 features | `poisson.py:24` rho=−0.08 hardcoded; λ = own goals scored only | PROVEN | MEDIUM | DAYS |
| 12 | Market feature injected on the fallback path | `feature_engineering.py:523,936` `= implied_prob_over` (raw, vigged) | PROVEN | MEDIUM | HOURS |
| 13 | Auto-optimizer deploys an in-sample-fitted threshold | `backtest.py:512` deployed th fitted on ALL data; OOS only gates approval | PROVEN | HIGH | DAYS |
| 14 | Form crosses divisions unadjusted; 24% of rows affected | `feature_engineering.py:126` groupby("team") only; 33 of 215 clubs multi-division | PROVEN | MEDIUM | DAYS |
| 15 | Rolling window is sorted league-major → future rows leak | 21 rows with a future-dated predecessor, gap median 1,123 days | PROVEN | LOW | HOURS |
| 16 | `min_periods=1` guts the blind-fixture guard | `feature_engineering.py:127`; guard fires only at zero matches | PROVEN | MEDIUM | HOURS |
| 17 | Pro's Dixon-Coles never compared to a price | `model_1x2_eval.csv` baseline logloss ≈ ln(3) = base rate, not market | PROVEN | HIGH | DAYS |
| 18 | Market in these leagues is well calibrated | slope 1.0636, intercept 0.0317, n=12,187; all price buckets negative | PROVEN | HIGH | — |

---

## 1. THE OPEN QUESTION IS ANSWERED

The seed asked: *why is `edge_pct` ~9% on rows tiered SNIPER when SNIPER needs 0.15–0.25, and is the
6.11% median the edge the decision was actually made on?*

**`edge_pct` IS the edge the decision was made on. The thresholds are not the ones in `config.py`.**

`v9/.github/workflows/predict.yml:188-192`:

```yaml
REQUIRE_FORM_DATA: "0"
REQUIRE_FORM_DATA_UNTIL: "2026-09-15"
LEAGUE_SNIPER_CAP: "0.12"
MARKSMAN_THRESHOLD: "0.08"
VALUABLE_THRESHOLD: "0.03"
```

`config.py:329` applies the cap: `LEAGUE_SNIPER_THRESHOLDS = {k: min(v, _SNIPER_CAP) ...}`. With
`_SNIPER_CAP = 0.12`, the entire documented per-league calibration collapses:

| League | documented (config) | deployed | source |
|---|---|---|---|
| League One | 0.25 | **0.12** | cap |
| Ligue 2 | 0.25 | **0.12** | cap |
| La Liga 2 | 0.20 | **0.12** | cap |
| Bundesliga 2 | 0.20 | **0.12** | cap |
| Championship | 0.15 | **0.07** | optimizer (`approved:true`) |
| Serie B | 0.15 | **0.12** | optimizer (`approved:true`) |
| MARKSMAN global | 0.14 | **0.08** | env |
| VALUABLE global | 0.04 | **0.03** | env |

Every observed tier reconciles under the deployed set. Worked examples from the ledger:

- Championship SNIPER @ 8.74% → optimizer `sniper_th` 0.07. Direct.
- Bundesliga 2 SNIPER @ 12.67%, La Liga 2 SNIPER @ 13.31% → capped `sniper_th` 0.12. Direct.
- La Liga 2 MARKSMAN @ 8.63%, League One @ 8.18% → global `MARKSMAN_THRESHOLD` 0.08. Direct.
- Serie B SNIPER @ 11.64% → MARKSMAN (0.10 optimizer floor) then `MARKSMAN→SNIPER` drift upgrade (Confirmed, ≥ `DRIFT_UPGRADE_EDGE` 0.10).
- Bundesliga 2 MARKSMAN @ 5.70%, Ligue 2 @ 4.27% → `VALUABLE→MARKSMAN` drift upgrade, which has **no edge floor** (`betting.py:211-213`).

So the seed's framing — "37 of 38 staked MARKSMAN below the 0.14 threshold" — is **not an anomaly**.
It is the configuration working as deployed. The real anomaly is that the calibration was switched off.

**The one-line env change is where the loss lives.** Of the 42 settled post-cutoff staked standard bets:

| | n | win % | P&L | ROI |
|---|---|---|---|---|
| clears its own **documented** floor | 10 | 50.0% | **+0.69u** | +6.9% |
| **below** the documented floor | 32 | 25.0% | **−13.97u** | **−43.7%** |

n=10 vs n=32 is below the evidence floor for a forward ROI claim, but this is a *decomposition of a
realised loss*, not an estimate: 32 of 42 staked bets, carrying 101% of the standard-track loss, would
never have been placed under the thresholds `config.py` documents. `betting.py:126-137` even warns that
falling back to the hand-set values "can never regress an env without it" — the env override is the
regression.

**Secondary defect, confirmed:** `VALUABLE→MARKSMAN` on `Confirmed` drift has no edge floor while
`MARKSMAN→SNIPER` requires 0.10. This bypasses an *explicit per-league disable*: `config.py:338`
sets Bundesliga 2's MARKSMAN floor to its SNIPER threshold with the comment "no MARKSMAN bets here;
8-20% = −10.8% ROI". Eight Bundesliga 2 MARKSMAN bets were placed anyway, median edge 5.70%, −3.23u.
The drift upgrade writes tiers the base tier function is designed to refuse.

---

## 2. THE EDGE THESIS — MEASURED, NOT ASSERTED

All numbers from `output/backtest_results_standard.csv` and `..._newformat.csv`, both written
**2026-09-02** by the current monthly backtest (standard: 12,187 rows, 7 leagues, 2022-09→2026-05;
new-format: 2,414 rows, 12 correctly-named leagues, 2025-08→2026-08). These are walk-forward
out-of-sample predictions from the current model, not stale artifacts — the Dutch-as-Norway staleness
noted in memory is gone.

### 2.1 Standard (the real-money track)

| predictor | logloss | brier | AUC |
|---|---|---|---|
| market de-vig | **0.67982** | 0.24341 | **0.59009** |
| v9 model | 0.69100 | 0.24893 | 0.52720 |
| 50/50 average | 0.68262 | 0.24477 | 0.58672 |
| constant base rate | 0.69240 | 0.24963 | 0.50000 |

The model beats a constant by 0.00140 nats. The market beats a constant by 0.01258. **The model
captures ~11% of the information the market already has, and is strictly worse than the market on
every metric.** Blending it with the market makes the market worse (0.68262 > 0.67982).

**Residual test** (does the model help *after* the price is known — the only test that matters):

- 3 chronological folds: Δlogloss −0.00116, +0.00042, −0.00016. **Sign flips.** Mean −0.00030.
- Bootstrap (200 resamples, 50/50 split): **mean −0.00005, CI95 [−0.00063, +0.00045], 61% negative.**
- `logit(p_model)` coefficient +0.21 to +0.29 — positive, but worth 0.0003 nats, i.e. ~2% of the
  market's own information content.

**Conf: PROVEN.** n=12,187 is well above the discipline floor. This is a powered null, not an
underpowered maybe. This independently reproduces v11's placebo verdict on a completely different
data path — v11 tested the *residual against price moves*, I tested the *residual against outcomes*.
Both land on zero.

### 2.2 New-format (where the live P&L is positive) — WORSE

| predictor | logloss | brier | AUC |
|---|---|---|---|
| market de-vig | **0.66973** | 0.23854 | **0.61779** |
| v9 NF model | 0.69328 | 0.25006 | 0.50752 |
| constant | 0.69122 | 0.24903 | 0.50000 |

**The new-format model is worse than a constant** (0.69328 > 0.69122), AUC 0.5075, and
`corr(p_model, p_mkt) = 0.078` — it is essentially orthogonal to the price. Residual Δ is
**+0.00040** with 64% of bootstraps positive: adding it to the price *hurts*, though CI95
[−0.00114, +0.00274] spans zero.

ROI by edge bucket is pure noise — +4.9, −8.1, +10.8, −13.1, +2.2, −9.1, +8.7 — with avg odds
climbing monotonically 2.25 → 3.30. **This refutes any reading of the live new-format P&L
(+2.5%/+2.2%/+35.3%, n=87/48/29) as evidence of edge.** There is no model information behind it, and
the sample sizes are below the floor. It is variance around a −6% overround.

> **I disagree with the implicit seed framing that new-format is "the part that works."** The pkl
> reports NF logistic AUC 0.6023 on a single 20% chronological split; walk-forward gives 0.5075. The
> 0.60 does not survive contact with walk-forward, and NF is the *weaker* of the two tracks, not the
> stronger.

### 2.3 Why the edge metric is structurally an anti-signal

`p_over25` range **[0.333, 0.552]**, std **0.0402**. De-vigged market std **0.0746**.
`corr = 0.269`. Variance decomposition of `edge` on the 4,278 rows where a side was chosen:

```
Var(p_model) = 0.001969   (149% of Var(edge))
Var(1/odds)  = 0.002668   (202% of Var(edge))
-2*Cov       = -0.003317  (-251%)
Var(edge)    = 0.001319
corr(edge, 1/odds_taken) = -0.5378
corr(edge, p_model)      = +0.1926
spearman(edge, odds_taken) = +0.5874  (p ≈ 0)
```

The price is the larger term **and** the more strongly correlated one. Mechanically: a 14% edge
requires `1/odds ≤ p_model − 0.14 ≈ 0.34`, i.e. **odds ≥ 2.94** on the chosen side. The SNIPER tier
cannot express "the model is confident" — the model is never confident, its probability never leaves
a ±4pp band around 0.48. It can only express "the price is long."

Confirmed by tier: mean odds VALUABLE 2.338 → MARKSMAN 2.744 → SNIPER 2.848, and by edge bucket:
2.22 → 2.30 → 2.40 → 2.49 → 2.58 → 2.81 → 3.00. Perfectly monotone.

And realised outperformance (`realized − devig_implied`) is **not** monotone in the model's edge:
+0.06pp, +1.83, +2.02, **−3.79**, +2.95, **−1.01**, +9.14 (last bucket n=60). The metric does not
order true edge.

**This is the same "longshot machine" that killed props (−41% to −57%, AUC≈0.5), operating in the
standard team model.** Invariant 2 was established from the props version of this. It applies here.

### 2.4 The documented guard against exactly this does not exist

CLAUDE.md: *"Main O/U odds are bounded by `MAX_OU_ODDS` to reject stale or fringe prices."*
`grep -rn MAX_OU_ODDS` across all v9 `*.py` and `*.yml`: **zero matches.** The only price guards are
`MIN_OVER_ODDS`/`MIN_UNDER_ODDS` = 1.75, which are **floors** — they exclude short prices and admit
every long one. The system has a documented ceiling that was never implemented, and the tier ladder
walks straight through where it should have been.

`EDGE_CEILING = 0.19` was meant to catch this ("above 19% the model is overconfident, backtest shows
−20% ROI at 16-20%"). It is unreachable for every per-league league: `betting.py:171` returns SNIPER
on `edge >= sniper_thresh` **before** the ceiling is tested at line 178, and line 176 skips the
ceiling entirely when `has_per_league` is true — which is every bet league. So the ceiling fires only
for leagues on the global threshold. **Both anti-longshot guards are absent or dead.**

---

## 3. THE MARKET IS NOT THE SOFT TARGET IT IS ASSUMED TO BE

Tested on the same 12,187 standard rows:

- **Calibration:** `logit(p_outcome) ~ logit(p_mkt)` gives slope **1.0636**, intercept **0.0317**
  (perfect = 1, 0). Decile reliability errors ±1.5pp, one 2.75pp outlier at n=1,215.
- **No exploitable price pocket.** Flat-betting every price bucket loses, on both sides, monotonically:

| odds bucket | OVER ROI (t) | UNDER ROI (t) |
|---|---|---|
| 1.00–1.70 | −4.72% (−2.70) | −6.39% (−5.67) |
| 1.70–1.90 | −3.18% (−1.79) | −7.40% (−5.00) |
| 1.90–2.10 | −4.65% (−2.57) | −7.92% (−3.46) |
| 2.10–2.40 | −6.86% (−3.45) | −8.32% (−2.79) |
| 2.40+ | −4.81% (−1.46) | −9.39% (−1.72) |

Overround mean **1.0642** (p10 1.0542, p90 1.0773). Always-OVER −4.92% ±0.92; always-UNDER −7.28% ±0.83.

There is no favourite-longshot bias to harvest, and **the longshot direction is the losing direction** —
which is precisely the direction the edge metric selects. The 6.42% margin is fully binding.

**Adversarial caveat on my own result, and it is the most important caveat in this report.**
These are football-data.co.uk **closing average** prices (`AvgC>2.5` first in `_OVER_COLS`). Closing
consensus is the sharpest price that exists. v9 bets a *single pre-match OddsAPI quote*, hours or days
earlier. So I have proven the *closing consensus* is efficient; I have **not** proven the price v9
actually takes is efficient. The gap between "best available pre-match quote" and "closing consensus"
is the only place an edge can still live in this market — and it is measured by CLV, not by a model.
`book_odds_snapshots` (143,799 rows, 24 real bookmakers, 80.1% two-sided, 99.4% fixture join) is
exactly the instrument for that question and nothing has asked it yet.

---

## 4. TRAINING PIPELINE — THREE SILENT NO-OPS

`output/fd_history.parquet` is the CI training cache (`data_loader.py:851`). Its `season` column is
**`str`** with values `'2019'…'2026'`.

**4a. COVID exclusion removes nothing.** `config.py:251` `COVID_SEASONS = {"2019/20","2020/21"}`.
`raw["season"].isin(COVID_SEASONS)` matches **0 of 37,623 rows**. The 7,112 rows that *are* COVID-era
football (2019+2020 = **18.9% of the cache**) stay in training — empty stadiums, suppressed home
advantage, distorted goal rates. `pipeline.py:189` logs *"Excluded COVID seasons: 0 rows removed"*
on every run.

**4b. Recency weighting is inert.** All ten `TRAINING_DECAY_WEIGHTS` keys are `"YYYY/YY"`. Against
`'2019'…'2026'` **not one matches** — the assigned weight set is exactly `{1.0}`. `train()` still
receives the array, aligns it, and passes it to `fit`, so it runs and does nothing.

Two independent bugs stack here. Even with correct keys the dict tops out at `"2024/25": 4.0` and
has **no entry for 2025/26 or 2026/27** — the live season and the one before it would fall to
`DEFAULT_DECAY_WEIGHT = 1.0` while two-year-old football carried 4.0. The intent is monotone recency;
the implementation would have produced a hump at 2024/25 with the current season at the floor.
Same failure shape as the `COLLECT_SEASONS`/`PROP_SEASONS` freeze in CLAUDE.md — a season-keyed
constant someone must remember to bump. Still live, in a different table.

**4c. `retrain.py` never passes weights anyway.** `retrain.py:371` is
`std_results = train_model(std_valid)` — no `sample_weight`. `pipeline.py:155` does pass them.
The weekly production retrain runs `retrain.py`. So recency weighting is dead **twice over**, and
`pipeline.py --mode train` and `retrain.py` train materially different models from identical data
with no reconciliation and no gate between them.

**4d. Bet leagues with no training data.** 10 of 17 `STANDARD_FORMAT_LEAGUES` have **zero** rows in
the CI cache: Belgian First Division A, Dutch Eredivisie, **Ligue 2**, National League, Portuguese
Primeira Liga, all four Scottish tiers, Turkish Super Lig. **Ligue 2 is in `ENABLED_LEAGUES`** — it is
bet in production and appears in the live ledger (n=1, −1.00u) — and contributes nothing to a CI-trained
model. Its features are median-imputed from other divisions, which per invariant 8's own logic produces
a *confident-looking wrong* edge. Invariant 7 justifies the superset as leagues that "improve the
model"; in CI, ten of them cannot.

The cache can supply at most **9,444** standard rows (2023-2026 only, zero before 2023). The deployed
`model_v9_standard.pkl` reports 15,130 + 2,670 + 4,450 = **22,250**. The two environments train
substantively different standard models — 2.4x the rows, different league coverage — and, with no
accept/reject gate, whichever runs last wins.

---

## 5. THE DEPLOYED PREDICTOR HAS NO HONEST METRIC

`src/model.py:238-254`:

```python
meta_X = np.column_stack([results[n]["model"].predict_proba(X_test)[:, 1] for n in results])
meta_clf.fit(meta_X, y_test)                 # fitted on the test split
meta_proba = meta_clf.predict_proba(meta_X)[:, 1]
log.info(f"  {'meta_logistic':20s}  auc={round(roc_auc_score(y_test, meta_proba), 4)}")  # scored on the same rows
```

The docstring says *"The test split was never seen by any base model, so there is no leakage."* True
of the base models; **the meta-logistic is fit and scored on identical rows.** Its reported AUC is
in-sample by construction, and `predict_proba()` (line 308-311) uses this meta as the **primary**
blend at inference. `metrics["__meta__"]` is written as `{}`.

So: the three base models have honest test metrics, and **the thing that actually ships has none** —
no held-out AUC, no held-out log-loss, no calibration measurement, ever. Combined with the seed's
finding that `retrain.yml` does not commit `backtest_metrics_history.json` (last real entry
2026-06-17, 4 model changes since 2026-08-16), there is **no validated performance number for the
deployed predictor at any point in its history**.

Recovered meta weights (normalised):

| model | STD test AUC | meta weight |
|---|---|---|
| logistic | 0.5484 (z=4.59) | **0.653** |
| gradient_boost | 0.5232 (z=2.19) | 0.179 |
| lightgbm | 0.5288 (z=2.72) | 0.168 |

The meta puts 65% on the plain logistic. **The "LogReg + GradientBoosting + LightGBM ensemble" is a
logistic regression with a 35% tree nudge** — and the boosters are barely distinguishable from chance
(GBM z=2.19 on n=4,450). The whole GBM/LightGBM apparatus contributes a third of a blend whose total
information beyond price is zero.

---

## 6. FEATURES: 23 OF 65 NEVER ARRIVE

`_prep` (`model.py:126`) silently drops any declared column absent from the training frame.
Deployed `feature_cols`: **42** (standard), **27** (new-format), against 65 declared.

**Absent from the standard model:** all 5 formation/lineup features (Phase 5), all 3 H2H features
(Phase 6), **all 6 API-Football Bet365 odds features** (Phase 7 — `api_implied_over25`,
`api_overround`, `api_implied_btts/over35/over15/draw`), both season-stage features (Phase 9), both
coach-caretaker features (Phase 10), possession, blocked shots, and `home_pitch_artificial`.

These are computed at *predict* time and absent at *train* time, so the trained model has no
coefficient for them and inference never looks at them. Per CLAUDE.md, re-enabling `predict.yml`
enrichment costs **~10–14k API-Football calls/day**. The organisation's own stated rule is *"Data no
model reads is pure cost"* and *"whether a consumer exists"* — for the O/U model, **there is no
consumer for eight of these enrichments**. (Injury/lineup data may still serve props; the odds,
H2H, formation, season-stage and coach features do not appear in any deployed team model.)

`home_pitch_artificial` is absent from **new-format**, which is precisely where it was designed to
matter (Finland/Sweden/Norway, `ARTIFICIAL_PITCH_LEAGUES`). Feature and use-case never met.

Two silent-nonsense paths:

- **`p_over25_poisson_dc` is not a Dixon-Coles model.** `poisson.py:24` hardcodes `rho = −0.08` and
  `feature_engineering.py:521` sets `λ_home = home_scored_last5`, `λ_away = away_scored_last5`,
  clipped. No fitted attack/defence ratings, no time decay, no per-league fit — and **it ignores the
  opponent's defence entirely**, though `home_conceded_last5`/`away_conceded_last5` are right there
  in the frame. Expected home goals should be `attack_home × defence_away × league_mean`; this is
  `attack_home` alone. So the feature is a fixed nonlinear transform of two features the GBM already
  has. Its 2.39% (STD) / 3.21% (NF) importance is the tree rediscovering a kink it could build itself.
- **The fallback injects a raw market price as a feature.** `feature_engineering.py:523` and `:936`:
  `df["p_over25_poisson_dc"] = df["implied_prob_over"].fillna(0.5)` — that is `1/odds_over25`,
  **not de-vigged**. On any path where rolling form is missing, a vigged bookmaker price becomes a
  model input, and `edge = p_model − 1/odds` then differences the price against itself. This is the
  exact failure §3 of the brief forbids, sitting on a fallback branch. Not currently the dominant
  path in training, but it is one missing column away from being it.

Also `bookmaker_overround` is the **5th most important standard feature (5.47%)** while carrying
**exactly 0.000000** importance in new-format. Total market-derived importance: 7.9% STD / 3.2% NF —
so v9 is *not* meaningfully trained to the market today, which is the one thing protecting the
residual measurement in §2 from being circular. Worth preserving deliberately rather than by accident.

---

## 7. SEGMENTATION, WINDOWS, REGIME

**Rolling windows** (`feature_engineering.py:124-127`):

```python
tc = tc.sort_values(["team", "league", "date"])          # line 121
tc.groupby("team")[stat].transform(lambda x: x.shift(1).rolling(n, min_periods=1).mean())
```

- **Grouped by `team` only** — form is never reset at a season boundary or a division change. **33 of
  215 standard clubs appear in more than one standard division; their rows are 24.0% of the standard
  team-match frame.** A club relegated from the Championship carries Championship goal rates into
  League One, and `attack_str = team_avg_scored / half_league_avg` divides them by the *new* league's
  average — a systematic distortion on roughly a quarter of rows with no promotion/relegation
  adjustment anywhere. Mechanism and the 24% are PROVEN; the ROI impact is unmeasured (PLAUSIBLE).
- **Sorted league-major, so time can run backwards.** `transform` preserves frame order, and the sort
  is `team, league, date` — so for Bolton the frame holds Championship 2026-08 *before* League One
  2026-05. **21 rows have a future-dated predecessor in their rolling window, median gap 1,123 days.**
  Genuine leakage. *Adversarially: 21 rows is 0.11% of the standard frame and the window is 5 wide, so
  the true footprint is at most ~84 rows. This is a correctness defect with negligible P&L impact —
  I am reporting it as a code bug, not as an explanation for anything.* One-line fix: sort by
  `["team", "date"]`.
- **`min_periods=1`** means one prior match yields a non-NaN "last-5". The blind-fixture guard
  (invariant 8) tests `isna()`, so it fires **only at zero matches** — a club with 1–4 matches is
  fully bettable on a 1-match average and the guard is silent. Combined with `REQUIRE_FORM_DATA=0`
  (live until 2026-09-15, five days from now), early-season fixtures are currently tiered on
  1-to-4-match "form" *and* median imputation. The self-expiring override is good engineering; the
  `min_periods=1` hole survives its expiry.

**Season stage / regime change:** `season_stage_ratio` and `is_late_season` are declared and
**absent from both deployed models** (§6). There is no promotion/relegation flag, no
newly-promoted indicator, no manager-change feature reaching a model (`*_coach_is_caretaker`
also absent), and no regime-break handling of any kind. With recency weighting inert (§4b) the
model has **no mechanism whatsoever** for treating recent football as more informative than
2019 football.

**Segmentation** is the one thing done right. Invariant 1 holds in code: separate `.pkl`, separate
`feature_cols` (42 vs 27), separate backtests, `mode_train` filters on
`STANDARD_FORMAT_LEAGUES` / `NEW_FORMAT_LEAGUES`. `retrain.py:388-397` even documents the fix that
made the two tracks fail independently. No violation found.

**Threshold optimizer** (`backtest.py:489-590`) — a genuine methodological hole:

- **The deployed number is fitted on all the data.** Docstring line 512: *"DEPLOYED `sniper_th` = grid
  value maximising ROI on ALL non-COVID data."* The walk-forward OOS pass produces `roi_oos`, which
  gates only the `approved` boolean — **and it evaluates a different threshold** (`bt[0]`, retuned per
  season) than the one deployed. So the procedure is validated and a different number ships.
- `roi_insample` is the max over a 22-point grid — an upward-biased statistic by construction.
- `marksman_th = sniper_th − 0.02` (line 583) is **never optimized**. For both approved leagues the
  MARKSMAN floor that decides ¾-stake real money is an arbitrary offset nobody measured.
- Approval samples are `bets_oos` = 164 (Championship) and 100 (Serie B). Both **below the n<250
  floor** for justifying a parameter change. And COVID exclusion here uses
  `getattr(config,"COVID_SEASONS", ...)` against the same string seasons as §4a — likely also a no-op.

This is not a clean invariant-6 breach (the OOS pass is a real attempt at discipline), but it does
fit a threshold on data it then reports performance over, and it deploys a strictly less-validated
number than the one it approved.

---

## 8. MODERN PRACTICE — WHAT ACTUALLY HAS EVIDENCE

The only question: **evidence of information beyond bookmaker prices.** Nothing in this codebase has
produced any, and one asset is closer than the others.

### `v10/src/combo/dixon_coles.py` — well built, wrong benchmark

188 lines, and genuinely competent: per-league fitting ("pooling leagues would make Boca Juniors and
Barnsley comparable, which they are not"), exponential time decay (`HALF_LIFE_DAYS = 180`), the
identifiability constraint (mean attack pinned to zero), `MIN_MATCHES_PER_LEAGUE = 300`, explicit
chronological-only evaluation, `MAX_GOALS = 10` score matrix, and the `rho` correction on the four
low scorelines. The module docstring's reasoning for choosing DC over a multiclass classifier — a
score distribution makes 1X2/totals/BTTS/joints mutually consistent — is correct and is the right
argument. This is a substantially better model than anything in v9.

**But `output/model_1x2_eval.csv` benchmarks it against the wrong thing.** `logloss_baseline` runs
1.0141–1.1237, i.e. ≈ `ln(3) = 1.0986` — a **base-rate prior**, not a price. `beats_baseline=True`
in 14 of 20 leagues means *"beats guessing"*. Nobody has ever asked whether it beats a bookmaker.
Test samples are 31–169 per league; 14/20 at p=0.5 is p≈0.058.

I ran the market comparison on the only settled data that exists — `v10/output/paper_1x2.csv`,
**30 settled rows**:

| predictor | logloss | RPS |
|---|---|---|
| Dixon-Coles | 1.1195 | 0.2354 |
| market de-vig | **1.0424** | **0.2153** |
| uniform | 1.0986 | 0.2333 |

**INSUFFICIENT_DATA at n=30** — this decides nothing and I am not claiming it does. But the
direction is a warning, not a comfort: worse than the market and worse than uniform. And the
disagreements are enormous — mean |model − market| = 6.7pp on home, **max 24.2pp** (Burnley
p_home 0.7349 vs market 0.4930). v9's model is *under*-dispersed and manufactures edge from long
prices; the DC is *over*-dispersed and would manufacture edge from its own confidence. Same failure,
opposite sign. **The most likely outcome of trading this DC on 1X2 without first proving a residual
is a faster version of the v9 loss.**

`paper_1x2.csv` already carries `p_*`, `o_*`, de-vigged `m_*`, closing `c_*` and `result` — the exact
residual-test schema. The infrastructure is complete and the answer is ~200 settled rows away, at
zero incremental cost.

### The rest of the landscape, judged on evidence

| approach | evidence of beating the price | verdict |
|---|---|---|
| Calibrated logistic / GBM ensemble on team features (v9, both tracks) | **Measured: none.** residual CI spans zero on n=12,187; NF worse than a constant | falsified |
| Dixon-Coles / bivariate Poisson (v10, well built) | **Never tested against a price.** Beats a base-rate prior only, n=31–169/league | untested — test it, don't ship it |
| v9's `p_over25_poisson_dc` | Not a Poisson model; a fixed transform of 2 in-model features | not a candidate |
| Elo / dynamic team strength | Nothing built, nothing measured. Elo is a compression of the same result history the rolling features already carry | SPECULATIVE — no reason to expect a different answer |
| Bayesian hierarchical / dynamic DC | Nothing built. Its advantage is honest uncertainty, which is only usable inside a market-anchored decision rule that does not exist yet | premature |
| Market-informed / market-anchored residual (v11's architecture) | The **only** framing consistent with every measurement in this audit and in v11's placebo battery | the one live thesis |
| Book-level dispersion / consensus (`book_odds_snapshots`) | **Untouched.** 143,799 rows, 24 real books, 80.1% two-sided, 99.4% join. The closing consensus is efficient (§3); whether the *best pre-match quote* is has never been asked | highest expected value in the repo |

**The uncomfortable synthesis.** Every model in this system, at every level of sophistication, lands
in the same place: some standalone discrimination, zero measurable information beyond the price. That
is not a modelling-quality problem — the DC is a good model and it does not help either. It is what an
efficient market looks like. The market's *closing* price in these leagues is calibrated to slope
1.064 with ±1.5pp decile errors. What has **not** been tested is the gap between the best pre-match
quote across 24 books and that closing consensus. That gap is measured by CLV, needs no team model,
and the data has been sitting in `book_odds_snapshots` since 2026-09-09.

---

## OPEN QUESTIONS

1. Was `LEAGUE_SNIPER_CAP=0.12` / `MARKSMAN_THRESHOLD=0.08` / `VALUABLE_THRESHOLD=0.03` a deliberate
   volume decision for the data-gathering season, or drift? `config.py:322` says the cap exists to
   "widen the SNIPER tier without editing these numbers" — so intentional. Was the −43.7% ROI of the
   band it opened ever anticipated? This is the single highest-value question in the audit.
2. Which `model_v9_standard.pkl` is actually live — the 22,250-row local artifact or a 9,444-row CI
   build? With no gate and no committed metrics history the answer is currently unknowable, and the
   two contain different leagues.
3. Is `SNIPER +14.36% ROI (n=145)` in the current backtest anything but noise? It is the only positive
   number in the standard track and it sits at the longest average odds (2.848) in a market where ROI
   falls monotonically with price. Prior says noise.
4. Does the *best pre-match quote across 24 books* beat the closing consensus? §3 proves the closing
   price is efficient and says nothing about the price v9 takes.
5. Does the Pro Dixon-Coles beat 1X2 prices? `paper_1x2.csv` answers it at n≈200-300 settled. At n=30
   it is losing to uniform.
6. `EXCLUDE_COVID_SEASONS` is a no-op in CI — was the 22.01% June baseline computed with or without
   COVID rows, locally or in CI? If it differs from the current 3.86% on that basis, the "regression"
   everyone is chasing may be partly an artifact-comparison error.

## DO NOT BUILD

- **Any threshold re-tune on the 42 settled staked bets.** n=42, and it is the same data that would
  evaluate it — invariant 6. The finding is that the *documented* thresholds were bypassed by an env
  var; restoring a pre-existing calibration is not tuning, re-fitting one is.
- **A better estimator for the standard O/U model** — XGBoost, CatBoost, a neural net, stacking, HPO.
  The residual CI spans zero at n=12,207. The ceiling is not the estimator; the market already holds
  the information. Better AUC would buy nothing.
- **Wiring the 23 dropped features into training.** Tempting, cheap-looking, and it optimises the
  wrong objective — a model with no residual edge does not acquire one from H2H rates and formations.
  *Do* decide deliberately whether to keep paying 10-14k calls/day for eight enrichments no team
  model reads.
- **Trading the Pro Dixon-Coles on 1X2.** Genuinely the best model asset here and it has never met a
  price. Its 24pp disagreements with the market are the v9 failure with the sign flipped. Measure the
  residual first.
- **An Elo / team-strength track.** Elo compresses the same result history the rolling features
  already encode, and those carry no residual information. No mechanism for a different answer.
- **Fixing the league-major sort as a priority item.** Real leakage, 21 rows, 0.11%. One-line fix
  when something else is open in that file; not a finding to act on alone.
- **Any props modelling proposal.** Invariant 2. Worth noting that §2.3 *independently reproduces*
  the mechanism that established it — the longshot machine is the same one, in the team model.

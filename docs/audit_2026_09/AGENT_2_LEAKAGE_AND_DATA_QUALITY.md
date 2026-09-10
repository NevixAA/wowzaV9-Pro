# AGENT 2 — Leakage & Data Quality Audit

**Date:** 2026-09-10
**Scope:** every modelling and research pipeline in `v9/`, `v10/` (Pro), root harness — lookahead
bias, train/test contamination, batch-dependent preprocessing, imputation, closing-price
leakage, post-kickoff contamination, duplication, timestamps, synthetic odds, retrospective
tuning.
**Rules of engagement honoured:** read-only on `v9/` and `wowza-v11/`; the only file written is
this one. Every number below was computed this run or read at a cited `file:line`.

---

## HEADLINE

**The losses are not a leakage artifact and not a statistical subtlety. `predict.yml` overrides
three tier thresholds in workflow env — `MARKSMAN_THRESHOLD 0.14 → 0.08`,
`VALUABLE_THRESHOLD 0.04 → 0.03`, `LEAGUE_SNIPER_CAP 0.12` — and the two edge bands this opens
are measured, on v9's own leak-free walk-forward backtest, at −6.49% ROI (n=3,419, 95% CI
[−10.2%, −2.8%], excludes zero) and −5.36% ROI (n=1,537). `config.py:277` documents that the
0.14 floor exists *because* the 8–14% zone was measured at −1.6% ROI. The workflow silently puts
the system back into the band it was told to avoid.**

The three most-cited worries are, on measurement, **not** what is wrong:
lookahead in the rolling features (clean), out-of-distribution imputation (real, worth <1pp of
probability), and post-kickoff closing prices (0 of 455 provable). I report all three as
refuted or downgraded below.

---

## FINDINGS TABLE

| # | Finding | Conf. | Cat. | Impact | Fix |
|---|---|---|---|---|---|
| 1 | `predict.yml` env reverts the MARKSMAN floor to 0.08 and drops VALUABLE to 0.03; both bands are backtest-negative, one with CI excluding zero | PROVEN | EXECUTION | CRITICAL | HOURS |
| 2 | The seed's open question answered: `edge_pct` **is** tip-time `best_edge`; the low edges come from `LEAGUE_SNIPER_CAP=0.12` + approved per-league `sniper_th` as low as 0.07 | PROVEN | EXECUTION | CRITICAL | HOURS |
| 3 | Pro `settlements` is 95.7% duplicate rows — 126,259 stored vs 5,489 distinct outcomes (23.0×) | PROVEN | DATA_QUALITY | HIGH | DAYS |
| 4 | `over15` side-market backtest is 100% fabricated prices (12,186/12,187 rows @ constant 1.40); it certified 4 live-approved markets | PROVEN | MARKET_DATA | CRITICAL | DAYS |
| 5 | `_prep` recomputes imputation medians from the **prediction batch**; same fixture moves up to 8.17pp on board composition alone | PROVEN | ARCHITECTURE | HIGH | HOURS |
| 6 | The ledger records the **maximum** tier/edge over ~40 re-sightings per fixture (`_TIER_RANK` upgrade); combined with #5 this is a threshold-crossing-by-noise engine | PROVEN | STATISTICAL | HIGH | DAYS |
| 7 | The deployed predictor is the meta-logistic blend, whose `metrics` dict is empty **by construction** — the shipped model has never been scored | PROVEN | PROCESS | HIGH | HOURS |
| 8 | Backtest writes live betting thresholds (`best_params_standard.json`); deployed value is the in-sample grid maximum, `approved` gate certifies a different number | PROVEN | STATISTICAL | HIGH | DAYS |
| 9 | `optimize_side_market_thresholds` has no OOS split at all — pure retrospective tuning, `min_bets=20` | PROVEN | STATISTICAL | HIGH | DAYS |
| 10 | Side-market `_OVERROUND = 1.08` inflates every side-market edge by +2.9 to +5.3pp | PROVEN | MARKET_DATA | HIGH | HOURS |
| 11 | "Closing" odds are `snapshots[-1]` with no kickoff filter and no timestamp read; 48% of closes are ≥1 day pre-kickoff, 18.2% equal the entry price exactly | PROVEN | DATA_QUALITY | HIGH | DAYS |
| 12 | Pro/shadow `p_model` is 100% reconstructed from the max-selected ledger `edge_pct`, timestamp-misaligned against `p_market` | PROVEN | STATISTICAL | HIGH | DAYS |
| 13 | Standard backtest evidence is +3.86% ROI on n=380 — CI spans zero. That is the whole basis. | PROVEN | STATISTICAL | HIGH | WEEKS |
| 14 | 23 of 65 declared features are silently dropped; 4 more are constant-zero. API-Football enrichment feeds features the model cannot contain. | PROVEN | DATA_QUALITY | MEDIUM | HOURS |
| 15 | `_closing_odds_json` name fallback discards the date — cross-season mismatch possible (1.8% of keys today) | PROVEN | DATA_QUALITY | LOW | HOURS |
| 16 | `min_periods=1` in `_rolling` defeats the blind-fixture guard for 1–4 match histories | SUPPORTED | DATA_QUALITY | MEDIUM | HOURS |
| — | **REFUTED:** rolling/expanding features contain no lookahead | PROVEN | — | — | — |
| — | **REFUTED:** post-kickoff closing-price contamination (0/455 provable) | PROVEN | — | — | — |
| — | **DOWNGRADED:** out-of-distribution zero-fill imputation — real, but <1pp effect | PROVEN | — | — | — |

---

## 1. THE PRIMARY DEFECT — workflow env reverses a measured decision

`v9/.github/workflows/predict.yml:188-192`:

```yaml
REQUIRE_FORM_DATA: "0"
REQUIRE_FORM_DATA_UNTIL: "2026-09-15"
LEAGUE_SNIPER_CAP: "0.12"
MARKSMAN_THRESHOLD: "0.08"
VALUABLE_THRESHOLD: "0.03"
```

`v9/config.py:277-279` states the reason the floor is 0.14:

> *MARKSMAN raised 8%→14% on 2026-06-17: sweep showed 8–14% zone is −1.6% ROI; 14%+ zone is
> +6.5% ROI.*

I re-measured both bands on `output/backtest_results_standard.csv` (v9's own leak-free
walk-forward output, n=12,187), flat 1u, PnL reconstructed from `best_side` + `over25` + the
actual odds columns so the measurement is independent of whatever tier the backtest staked:

| edge band | how production reaches it | n | flat-stake ROI | 95% CI |
|---|---|---|---|---|
| **[0.03, 0.08)** | drift `VALUABLE→MARKSMAN`, **no edge floor** (`betting.py:211-213`) | 3,419 | **−6.49%** | **[−10.2%, −2.8%]** |
| **[0.08, 0.14)** | production `MARKSMAN_THRESHOLD=0.08` | 1,537 | −5.36% | [−11.3%, +0.6%] |
| [0.14, ∞) | the config default the env overrides | (the band the sweep called +6.5%) | | |

The first row is the important one: **n=3,419 and the confidence interval excludes zero.** By my
own sample discipline this is the only band in the entire audit that clears the n≥250 bar *and*
has a CI off zero. It is negative, and production stakes it.

New-format is not evidence either way: [0.08, 0.14) is +0.24% on n=641, CI [−9.1%, +9.6%].

**Compounding effect of `LEAGUE_SNIPER_CAP=0.12`.** `config.py:329` applies
`min(v, _SNIPER_CAP)` to every per-league SNIPER threshold, collapsing the hand-calibrated
ladder — League Two .14, Bundesliga 2 .20, La Liga 2 .20, League One .25, Ligue 2 .25,
Championship .15, Serie B .15, Greek .25 — to a flat **0.12**. The ROI comment beside each value
(`+22.6%`, `+53.5%`, `+45.2%`) is the calibration being overridden.

Second-order: because `LEAGUE_SNIPER_THRESHOLDS` still *contains* those leagues,
`has_per_league` stays `True` at `betting.py:158`, so the `EDGE_CEILING` overconfidence
downgrade at `betting.py:177-181` is skipped — justified in the comment as *"Per-league
thresholds are backtest-optimised — no ceiling needed there."* Under the cap they are no longer
backtest-optimised. The ceiling is disabled for exactly the leagues whose calibration was
discarded.

---

## 2. THE SEED'S OPEN QUESTION — answered, and both hypotheses are wrong

> *"why is edge_pct ~9% on rows tiered SNIPER (needs 0.15-0.25)? Either edge_pct is recorded at
> settlement not at tip time, or tiering uses a different best_edge."*

**Neither. `edge_pct` is tip-time `best_edge`, and the deployed thresholds really are that low.**

`src/ledger.py:163` `edge = float(row.get("best_edge", 0.0))`, written at `:198` as
`round(edge * 100, 2)`. `best_edge` is set in `betting.py:319` from the same
`edge_over`/`edge_under` the tier is computed from, in the same function call. There is no
settlement-time path that touches it. **The 6.11% median IS the edge the decision was made on.**

All four staked standard SNIPER rows post-cutoff reconcile exactly:

| league | edge_pct | drift | deployed SNIPER threshold | path |
|---|---|---|---|---|
| Championship | 8.74 | New | **0.07** (`best_params_standard.json`, `approved:true`) | `betting.py:171` direct |
| Serie B | 11.64 | Confirmed | 0.12 approved; MARKSMAN 0.10 | base MARKSMAN → drift upgrade (`betting.py:208`) |
| Bundesliga 2 | 12.67 | New | not approved → `min(0.20, LEAGUE_SNIPER_CAP 0.12)` = **0.12** | `betting.py:171` direct |
| La Liga 2 | 13.31 | Neutral | not approved → `min(0.20, 0.12)` = **0.12** | `betting.py:171` direct |

`v9/models/best_params_standard.json` deploys **Championship `sniper_th: 0.07`,
`marksman_th: 0.05`, `approved: true`**. A Championship MARKSMAN therefore needs a 5% edge, not
14% — which is why the staked median is 6.11%. Measured breakdown of the 42 settled staked
standard S+M rows post-cutoff:

```
                          n  med_edge  min_edge   pnl  wins
Bundesliga 2 MARKSMAN     8     5.70      3.61  -3.23     2
             SNIPER       1    12.67     12.67  -1.00     0
Championship MARKSMAN     7     5.58      3.36  -0.81     3
             SNIPER       1     8.74      8.74  +1.20     1
La Liga 2    MARKSMAN     9     8.63      3.59  -6.92     1
             SNIPER       1    13.31     13.31  -1.00     0
League One   MARKSMAN     6     8.19      3.26  -3.86     1
Ligue 2      MARKSMAN     1     4.27      4.27  -1.00     0
Serie B      MARKSMAN     7     5.58      3.62  +2.04     4
             SNIPER       1    11.64     11.64  +1.30     1
```

**Where the seed is right:** the asymmetric drift guard is real. `betting.py:208` requires
`best_edge >= DRIFT_UPGRADE_EDGE` for `MARKSMAN→SNIPER`; `betting.py:211` requires **nothing**
for `VALUABLE→MARKSMAN`. With `VALUABLE_THRESHOLD=0.03` that path stakes edges from 3.26% —
inside the band proven negative in §1.

---

## 3. Pro `settlements` — 23× duplication

Measured via `v10/src/data/season_store.py::read` this run:

| table | rows stored | exact duplicates on the natural key | distinct facts |
|---|---|---|---|
| **settlements** | 126,259 | **120,770 (95.7%)** on `(fixture_key, market, result)` | **5,489** |
| market_snapshots | 172,430 | 3,301 (1.9%) on `(fixture_key, market, odds, odds_source, observed_at)` | — |
| book_odds_snapshots | 143,799 | **0 (0.0%)** | 143,799 |
| movement_observations | 691,123 | — | — |

Mechanism: `pro_backfill_results.yml` runs `25 * * * *`. Each hourly run re-collects **all**
settled fixtures and appends the whole set under a new `run_id` (50 distinct `run_id`s).
`season_store.append` refuses to overwrite (`season_store.py:228`) but performs **no
deduplication — by design** (`:19` *"Append is the only operation this module supports"*).
Nothing is wrong with the store; the collector is re-asserting a finished fact 50 times.

The module's own docstring (`:157-164`) already warns about this class of bug — *"Those
duplicates inflate every `n` the research depends on, and `n` is what gates whether a signal
graduates"* — but attributes it to local writes and fixes it with a CI-only guard
(`_in_ci()`, `:100`). **That guard cannot help here: these are CI runs.**

**Honest scope limit.** The primary consumer is safe: `v10/src/pipelines/shadow.py:187` does
`s.sort_values("observed_at").drop_duplicates("fixture_key", keep="last")`, and `:204` does the
same for `model_snapshots`. So the current research numbers are not 23× inflated. The exposure
is (a) `stats()` row counts and the "1.6M rows / canonical warehouse" headline, which are
largely duplication, and (b) any *new* consumer that reads the table without deduping — the
naive read inflates `n` 23× and narrows every confidence interval by √23 ≈ 4.8×.

`book_odds_snapshots` is genuinely clean at 0% duplication — the newest table is the best-built
one.

---

## 4. The `over15` backtest is entirely fabricated prices

`src/backtest.py:233`:

```python
_DEFAULT_ODDS = {"btts": 1.85, "over15": 1.40, "over35": 2.60}
```

`:268-271` fills every missing `odds_<target>` with that constant. Measured on the committed
backtest outputs:

| market | rows | rows at the hardcoded default | **placed tips (S+M) at the default** |
|---|---|---|---|
| **over15** | 12,187 | **12,186 (100.0%)** | **2,121 / 2,122 (100.0%)** |
| over35 | 12,187 | 12,169 (99.9%) | 0 / 0 |
| btts | 12,187 | 6,352 (52.1%) | **0 / 925 (0.0%)** |

With a constant price the derived `fair_prob = (1/1.40)/1.08 = 0.6614` is also constant, so
`edge = p_model − 0.6614` (`backtest.py:318-319`). **The over15 tier is a bare
model-probability threshold and the reported ROI is the payout of an invented number.** There is
no market in the measurement, so it cannot be an edge test.

This is not confined to a research file. `output/league_roi_config.json` →
`approved_markets_by_league` lists **over15 as approved** for Bundesliga 2 (+13.5%),
Championship (+7.86%), League Two (+9.97%) and Serie B (+4.21%) — all four numbers derived from
the 1.40 constant — and `telegram_bot/notifier.py:338` reads that file.
`models/best_params_over15.json` deploys thresholds 0.07–0.11 certified on the same synthetic
prices, at `bets` counts of **27** (Championship) and **30** (Ligue 2).

Note also `models/best_params_side_markets.json.SYNTHETIC_BAK_20260701` — this problem was
recognised in July 2026 and a backup taken. The live `best_params_over15.json` is dated
2026-09-02 and is still 100% synthetic.

**BTTS is the honest counter-example and should be kept separate:** 0% of its placed tips used a
default. Its backtest is on real prices.

---

## 5. Batch-dependent preprocessing — the same fixture gets a different probability

`src/model.py:124-130`:

```python
def _prep(df, feat_cols=None):
    cols = [c for c in (feat_cols or FEATURE_COLS) if c in df.columns]
    X = df[cols].copy().apply(pd.to_numeric, errors="coerce")
    col_medians = X.median().fillna(0.0)     # <-- computed from THIS frame
    X = X.fillna(col_medians)
    return X, cols
```

`save_models` (`:263-281`) persists no imputation values, so at inference the medians are
recomputed **from the prediction batch**. A fixture's feature vector therefore depends on which
other fixtures happen to be on the board.

Measured on the live board (`output/predictions.csv`, 77 standard fixtures), scoring each
fixture as part of the whole board versus scoring it alone through the identical pickle:

```
mean |Δp_over25| = 2.61 pp
max  |Δp_over25| = 8.17 pp
fixtures moving >4pp (= the entire VALUABLE_THRESHOLD): 22 / 77
```

**8.17pp exceeds the production MARKSMAN floor of 0.08.** Board composition alone is enough to
move a fixture from AVOID to staked and back.

`predict.yml` runs every 5 minutes and the board turns over continuously, so this is not a
theoretical concern — it is resampled all day.

### Adversarial correction — the out-of-distribution story is real but small

The remit asks what the model receives when xG is 0% populated. Answer: `home_xg_last5` has
`scaler.mean_ = 0.0`, `scale_ = 1.0`, `gbm importance = 0.0`. **xG was constant-zero in
training too** — `WOWZA_FULL_ENRICH=1` in `retrain.yml:45` does not populate it. The model
receives 0.0, which is exactly the train mean. z = 0. **Harmless.** Four of 42 features
(`home/away_xg_last5`, `home/away_insidebox_last5`) are dead constant-zero columns.

The genuine out-of-distribution cases are elsewhere. Cross-referencing predict-time population
against the fitted scaler:

| feature | populated at predict | GBM importance | z-score when zero-filled |
|---|---|---|---|
| `home_fouls_pg_roll` | **0.0%** | 3.80% | **−5.24** |
| `away_fouls_pg_roll` | **0.0%** | 4.38% | **−5.23** |
| `home_corners_pg_roll` | **0.0%** | 4.78% | **−3.50** |
| `away_corners_pg_roll` | **0.0%** | 2.96% | **−3.52** |
| 8 half-time features | 0.0% | ~7.2% | −2.0 to −3.3 |
| season splits, rest days | 44–49% | ~25% | (batch median) |

≈24.6% of the GBM's decision weight is computed on physically impossible values (zero fouls per
game, zero corners per game) on every prediction.

**But I must report that this barely matters.** Re-scoring the board with correct train-mean
imputation instead of zero-fill:

```
mean |Δp_over25| = 0.84 pp   max 2.59 pp
fixtures moving >4pp: 0 / 77
```

The reason is finding #13: the model is nearly flat (`p_over25` sd = 0.053, GBM AUC 0.523), and
a model that barely discriminates cannot be badly perturbed. **The structural defect is real;
the causal claim "this is why we lose" is refuted.** Fix it for correctness, not for P&L.

---

## 6. The ledger records the maximum, not the observation

`src/ledger.py:145-178`. `_TIER_RANK = {SNIPER:3, MARKSMAN:2, VALUABLE:1, AVOID:0}`; on re-seeing
a fixture at a stronger tier the row is overwritten in place:

```python
existing.at[i, "signal_tier"]  = tier
existing.at[i, "edge_pct"]     = round(edge * 100, 2)
```

The stated intent (`:141-144`) is legitimate — record the tier the tip was *sent* at. The
consequence is not. `predict.yml` requests 57 runs/day at ~15% delivery ≈ 8.5 runs/day, over
~5 days to kickoff ≈ **~40 observations per fixture**, and the ledger keeps the **maximum**.

With the per-observation batch noise measured in §5 (sd ≈ 2.6pp) and N = 40,
E[max] ≈ mean + sd·√(2 ln N) = mean + **7.1pp of pure noise**. Production's MARKSMAN floor is
8pp. **A fixture with a true edge near zero will, after 40 noisy observations, record a maximum
around 8pp and be staked.** That is a quantitative account of why the staked edge distribution
piles up just above the floor at a 6.11% median: an edge distribution centred on the threshold
is the signature of threshold-crossing-by-noise, not of selecting genuine edges.

Findings #5 and #6 are one mechanism: batch-composition noise, resampled ~40×, maximum
retained, staked.

Cross-check against `bets_ledger.csv.pre_tierfix_bak` (4,476 rows) vs current (5,176): 238 rows
changed tier, mean `edge_pct` 12.89 → 13.42. Note the matrix also contains **98 SNIPER→VALUABLE
downgrades**, so "best-tier-wins" is not the only rewrite acting on this file. The
upgraded-vs-not performance split (n=36 vs 137) is **INSUFFICIENT_DATA** and I draw nothing from
it.

---

## 7. The shipped model has never been scored

`v9/models/metrics_model_v9_standard.json` and the pickle payload:

```
logistic        acc 0.5364  auc 0.5484  logloss 0.68833   n_test 4450
gradient_boost  acc 0.5272  auc 0.5232  logloss 0.69153   n_test 4450
lightgbm        acc 0.5290  auc 0.5288  logloss 0.69052   n_test 4450
__meta__        {}                                     <-- EMPTY
```

`predict_proba` (`model.py:308-311`) uses `__meta__` — the meta-logistic blend — whenever it
exists, and it always exists. `train()` sets `results["__meta__"]["metrics"] = {}` at
`model.py:252`, and `save_models` copies `{k: v["metrics"]}` at `:270`. **The object that
generates every tip has an empty metrics dict by construction.**

Worse, the meta blend is fit on the split it would be scored on: `model.py:243-245`
`meta_clf.fit(meta_X, y_test)` then `meta_proba = meta_clf.predict_proba(meta_X)` — the logged
meta AUC at `:248` is in-sample. The base-model AUCs *are* honest OOS (Platt calibration is
fitted on the last 15% of *train*, `:170-172`, chronologically before the test split — that part
is correct and I verified it).

This closes the loop on the seed's "retrain does not gate" finding: there is **nothing to gate
on**. `retrain.py:370` saving before `:393` backtesting is the lesser problem; the deployed
estimator emits no metric at all.

New-format is the same shape: `metrics_model_v9_newformat.json` has base AUCs 0.6023 / 0.5831 /
0.5735 on n_test=3,938 and `"__meta__": {}`.

The base numbers deserve a line of their own. **GBM AUC 0.5232 on n=4,450** is z ≈ 2.7 above
coin-flip (SE ≈ 0.0087) — detectable, economically negligible. The observed `p_over25` sd of
0.053 on the live board is the same fact seen from the other side.

---

## 8–10. Retrospective tuning, quantified

**#8 — the backtest writes live betting thresholds.** `pipeline.py:444-446` calls
`optimize_standard_thresholds(std_results)` and writes `models/best_params_standard.json`;
`betting.py:132-137` reads it in production. A monthly backtest silently re-tiers the live
system.

`backtest.py:540-549` `_best_threshold` picks the **ROI-maximising** grid point over
`arange(0.04, 0.25, 0.01)` (22 candidates). `:582` deploys that in-sample maximum. The
walk-forward OOS pass (`:556-568`) is genuinely constructed — tune on prior seasons, apply
blind to the next — but it computes `roi_oos` at a **per-fold** threshold, then `approved`
(`:580`) gates real money while `:582` deploys a **different** number. **The gate certifies a
procedure and ships a parameter it never evaluated.**

The file's own contents demonstrate the optimism the gate is meant to catch:

| league | in-sample ROI @ optimum | n | OOS ROI | n | approved |
|---|---|---|---|---|---|
| La Liga 2 | **+14.39%** | **31** | **−5.84%** | 94 | false |
| League One | +4.11% | 36 | **−59.0%** | 7 | false |
| Serie B | **+45.67%** | 52 | +17.02% | 100 | **true** |
| Championship | +2.59% | 308 | +3.32% | 164 | **true** |

The two highest in-sample ROIs on the smallest n are the two worst OOS. And these are exactly
the leagues the seed found worst in the live ledger (La Liga 2 −6.92u, League One −3.86u). The
mechanism is confirmed from three independent directions.

Championship's +2.59% is the **maximum over 22 grid points** on n=308; per-bet SD ≈ 1.0 gives
SE ≈ 5.7pp, so the point estimate is 2.59 ± 11pp before any multiple-comparison correction. Its
deployed `sniper_th=0.07` is below the global `SNIPER_THRESHOLD` (0.12), below the global
`MARKSMAN_THRESHOLD` (0.14), and below the hand-set Championship value (0.15). Serie B's
`roi_insample: 45.67` on n=52 is approved and live. Both are **INSUFFICIENT_DATA** for a
parameter change under any reasonable standard (n<250).

This is invariant 6 violated in substance. Note the same origin taints the hand-set constants:
`config.py:320-327` records `"League Two: 0.14 → ROI +22.6%"`, `"La Liga 2: 0.20 → ROI +53.5%"`
— thresholds chosen from backtest ROI and written back into config.

**#9 — `optimize_side_market_thresholds` (`backtest.py:422-486`) has no OOS pass whatsoever.**
It grid-searches `edge_min..edge_max` maximising ROI on the same `results_df` it is handed,
`min_bets=20`, and returns `sniper_th` = the maximiser with `marksman_th = sniper_th − 0.02`
(never optimised). Compare `optimize_standard_thresholds`, which at least attempts a
walk-forward. This is the function that produced `best_params_over15.json` — grid-maximised
ROI on 100% fabricated prices (§4), at n=27–30 for two leagues.

**#10 — the side-market overround constant.** `backtest.py:229` `_OVERROUND = 1.08`, applied as
`fair_prob = (1/odds)/1.08` (`:318`). Dividing implied probability by 1.08 *understates* it,
inflating every edge:

| market | default price | honest implied | backtest `fair_prob` | **edge inflation** |
|---|---|---|---|---|
| over15 | 1.40 | 0.7143 | 0.6614 | **+5.29 pp** |
| btts | 1.85 | 0.5405 | 0.5005 | +4.00 pp |
| over35 | 2.60 | 0.3846 | 0.3562 | +2.85 pp |

The over15 SNIPER threshold of 0.10 is therefore an honest 0.047 — **more than half the stated
threshold is the constant.**

---

## 11. "Closing" odds are not closing odds

`update_results.py:307-335`. The docstring says *"Return the LAST recorded odds snapshot before
kick-off"*. The code is:

```python
last = snapshots[-1]
field = "under" if side == "UNDER" else "over"
```

**No kickoff filter, and the timestamps are never read** — though every snapshot carries them.
Verified structure of `v9/odds_history_v9.json` (455 fixture keys, 2,490 snapshots): each
snapshot is `{'ts', 'ts_last', 'over', 'under', 'n'}`. `ts`/`ts_last` are ignored entirely.

### Adversarial test — my post-kickoff hypothesis is REFUTED

I predicted in-play contamination and tested it two ways. Both came back negative:

1. **Outcome-independence test** (the decisive one — CLV measured strictly pre-kickoff must be
   independent of the result). n=685 settled with CLV:
   `WIN mean CLV 13.52% vs LOSS 11.26%`, diff +2.27pp, **Welch t=0.75, p=0.451**,
   Mann-Whitney p=0.17, point-biserial r = **0.028**. **No detectable outcome leakage.**
2. **Timestamp test.** Last-snapshot day relative to fixture day:
   `0 / 455 = 0.0%` fall on a later calendar day. Unambiguous post-match closes: **none**.
   (5.5% of same-day closes are at hour ≥20 UTC, consistent with the seed's 5.4% post-kickoff
   figure, but not provable without kickoff times.)

**Report this as refuted.** The metric is broken a different way:

```
last snapshot 1-6 days BEFORE fixture date : 218 / 455 (47.9%)
last snapshot on fixture day               : 237 / 455 (52.1%)
fixtures with only ONE snapshot            :  49 / 455 (10.8%)
ledger rows where closing_odds == odds exactly : 125 / 685 (18.2%)
median clv_pct                             : exactly 0.00
snapshots per fixture                      : median 4, mean 5.5, max 23
```

`drift.py` stores price *changes* only, so a fixture whose price never moved after the tip has
`snapshots[-1] == ` the entry snapshot and CLV is exactly 0 — which is a **coverage failure
recorded as a neutral result**. 48% of "closes" are captured 1–2 days early. Against the seed's
near-kickoff coverage collapse (T-1h 32.6%, T-30m 14.5%), **this is a T-48h line, not a closing
line, and CLV against it measures nothing about beating the market's final opinion.**

That matters beyond v9: CLV is the gate v11's `BET` state depends on (`MIN_CLV_N=150` and
positive CLV) and it is an input to Pro's `evaluate_gate()` (`clv_n`). Both gates are built on a
quantity that is 18% structural zeros and 48% two-days-early.

**Unexplained residual, flagged not asserted:** the distribution has a large tail
(p90 +75%, p99 +125%, max +287%; 18.7% of rows above +50%) and a systematic side asymmetry —
`OVER n=203 mean −9.71%` vs `UNDER n=482 mean +19.53%`, a 31pp gap. Entry→close means are
OVER 2.24→2.82, UNDER 2.34→2.08. I could not establish the mechanism this run. It is not
outcome-correlated (test 1 above), so it is noise or a side/price mismatch rather than a peek.
**Worth one focused hour; I am not going to guess.**

**#15 (latent).** The name fallback at `update_results.py:320-327` matches on normalised home
and away names and **discards the `| match_date` component of the key**, so a recurring fixture
can resolve to a different date's snapshots. Today only 4 of 451 pairs (8 of 455 keys, 1.8%) are
ambiguous, because the JSON is pruned to current fixtures — so this is a real bug with a small
current blast radius. It will grow with any change to the pruning policy.

---

## 12. Pro's model-vs-market comparison uses a max-selected probability

`v10/src/pipelines/shadow.py:225-232`. `p_model` prefers a genuine `model_snapshot` and falls
back to `p_model_over` reconstructed from the ledger's `edge_pct`
(`src/importers/current_wowza.py:381`). The code's own comment states the fallback is currently
**universal**:

> *"These cannot overlap yet and that is structural, not a bug: model_snapshots come from
> predictions.csv, which is PRE-MATCH only, while settlements are by definition finished.
> Nothing Pro has snapshotted has settled yet."*

So `p_model_source` is `ledger_edge_pct` for essentially every row. And by finding #6 the
ledger's `edge_pct` is the **maximum over ~40 re-sightings**, not the value at any single
moment. It is then joined against `p_market` de-vigged from `market_snapshots` deduped
`keep="last"` (`:186`, `:204`).

**Two quantities measured at different, non-aligned times, one of them max-selected, compared as
if simultaneous.** For a residual test — "does the model add anything once the price is known" —
that is exactly the wrong input, and it is a plausible contributor to the seed's placebo result:
a max-selected `p_model` correlates with whichever direction the price series wandered furthest,
which is the same series `p_market` is drawn from. This is a concrete, testable mechanism for
the seed's *"p_market(t) sits in BOTH the residual and the future move with opposite signs"* —
and it means the placebo battery's verdict on the *price series* may be a verdict on this join,
not on the model.

**This is the single highest-value thing to fix before any further residual research**, because
every residual number computed to date runs through it.

---

## 13. What the standard model's backtest evidence actually is

Current `output/backtest_results_standard.csv`, tiers as the backtest computed them:

```
placed (SNIPER 145 + MARKSMAN 235) = 380 bets
total staked 380u   total pnl +14.7u   ROI +3.86%
win rate 38.4%   avg winning odds 2.70   (0.384x1.70 - 0.616 = +3.7%, internally consistent)
```

**ROI +3.86% on n=380.** Per-bet SD ≈ 1.4 → SE ≈ 7.2pp → 95% CI ≈ **[−10.3%, +18.0%]**. The CI
spans zero. That is the entire out-of-sample basis for the standard track, against a live staked
result of −36.3% ROI on the MARKSMAN subset.

`output/backtest_metrics_history.json` holds **4 entries, latest `2026-06-17`** — confirming the
seed. The June standard entry claims `roi_% 22.01` on `total_bets 5011`, which I **could not
reproduce** from any committed artifact (today's file has 380 placed rows, not 5,011). I flag the
+22% as unreproducible rather than assert a mechanism for it. Both new-format entries in that
file record `total_bets: 0`.

**Tier coverage gap.** The new-format backtest produces `{VALUABLE: 1099, AVOID: 712,
SNIPER: 603}` — **no MARKSMAN tier at all**, because the backtest runs the config default 0.14
while production runs 0.08. `backtest.yml:37-53` and `retrain.yml:41-46` set only
`ODDS_API_KEY`, `APIFOOTBALL_KEY`, `WOWZA_FULL_ENRICH` — none of the threshold overrides.
**The backtest never evaluates the tier production stakes most of.** The seed's 87 new-format
OU25 MARKSMAN bets have zero backtest coverage of any kind.

---

## 14. Feature inventory — what the model actually contains

`FEATURE_COLS` declares **65**; the trained standard model contains **42**. `_prep`'s
`if c in df.columns` filter (`model.py:126`) silently drops 23 columns absent from the *training*
frame:

```
home/away_attack_formation, combined_attack_intent, home/away_forward_count,
h2h_over25_rate, h2h_avg_goals, h2h_home_win_rate,
api_implied_over25/btts/over35/over15/draw, api_overround,
season_stage_ratio, is_late_season, home/away_coach_is_caretaker,
home/away_possession_last5, home/away_blocked_last5, home_pitch_artificial
```

These are the API-Football enrichments `predict.yml` re-enabled at ~10–14k calls/day
(root `CLAUDE.md`). They are present in the *prediction* frame and absent from the *training*
frame, so the model **cannot** contain them and never will under this loader. Consistent with
the documented finding that `_enrich_with_af_odds` is a permanent no-op (historical odds are
unpurchasable). Plus 4 constant-zero columns (xG, inside-box). **Net: 38 of 65 declared features
carry information; the enrichment cost buys features no model reads.** New-format carries 27
features.

---

## What is CLEAN — verified, report as passing

These were checked properly and are correct. They should not absorb further audit budget.

1. **No lookahead in rolling or expanding features.** `feature_engineering.py:124-127`
   `_rolling` is `groupby("team")[stat].transform(lambda x: x.shift(1).rolling(n).mean())` —
   shift *before* roll. League averages `:136` and `:154` are `expanding().mean().shift(1)`.
   Season venue splits `:228-236` are `expanding().mean().shift(1)` within
   `(league, season, team, venue)`. This is textbook-correct and consistently applied.
2. **The walk-forward backtest loop is sound.** `backtest.py:92-100` trains on `df.iloc[:start]`
   and predicts `df.iloc[start:start+walk]` with `train_ratio=0.85`; the internal calibration
   split is the most recent 15% of *train*, chronologically before the test window. No test-window
   leakage into the fold model.
3. **Chronological split and calibration in `train()`.** `model.py:148-174` sorts by date, splits
   by position, and fits Platt on `X_cal` (last 15% of train). Correct. (The meta blend is the
   exception — §7.)
4. **`referee_foul_avg` is not a live leak.** `feature_engineering.py:261` aggregates over the
   full frame with no shift, which *would* be leakage — but the feature was dropped
   (`model.py:77`) and is absent from all 42 columns. Dead code.
5. **`season_store.append` itself.** Run-partitioned, refuses overwrite (`:228`), separates
   `observed_at` from `ingested_at` (`:203-211`) precisely so leakage stays detectable, and
   guards local writes (`:188`). The duplication in §3 is a collector cadence problem, not a
   store defect.
6. **`book_odds_snapshots`.** 143,799 rows, 0% duplication, real bookmaker names, `snapshot_ts`
   present. Genuinely the cleanest table in the system and, per the seed, still unexploited.
7. **`shadow.py` deduplicates** `settlements` and `model_snapshots` on `fixture_key` before use.

---

## OPEN QUESTIONS

1. **The CLV side asymmetry.** OVER −9.71% (n=203) vs UNDER +19.53% (n=482), and a tail to
   +287%. Not outcome-correlated, so not a peek. Mechanism unidentified. One focused hour.
2. **The unreproducible +22.01% ROI / 5,011 bets** in `backtest_metrics_history.json`
   (2026-06-17). It is the number the config comments and project memory are anchored to, and no
   committed artifact reproduces it. Was it a different league set, a pre-`min_odds` guard, or a
   different stake rule?
3. **Does `evaluate_gate()` read `settlements` directly?** If any future caller does, its `clv_n`
   and block counts inflate 23×. Worth a dedup at the read boundary rather than in each consumer.
4. **Was `best_params_standard.json` different when the mid-August tips were sent?** The file is
   dated 2026-09-02 and is overwritten in place with no version history, so the tier a historical
   tip was assigned at is not reconstructible. Under `LEAGUE_SNIPER_CAP=0.12` all four SNIPER
   rows reconcile without needing this, but the provenance gap is real and will bite the next
   audit.

---

## DO NOT BUILD

- **A leakage fix for the rolling features.** They are correct (§clean 1). Effort here is wasted.
- **A train-mean imputer as a P&L fix.** Do it for correctness — it is 20 lines — but it moves
  probabilities <1pp (§5). Anyone selling it as a revenue fix is wrong.
- **A post-kickoff filter on closing odds as the CLV fix.** 0 of 455 closes are provably
  post-match. The problem is that closes are 48% *too early*, which is a collection-cadence
  problem, not a filter.
- **A bigger side-market backtest, more markets, or more seasons for over15.** The prices are
  invented (§4). More rows of a constant is more of nothing. Fix the price source or delete the
  market.
- **Any new threshold optimiser.** Two exist and both are the problem. The system does not need a
  better search over thresholds; it needs to stop deploying in-sample maxima at n=31.
- **Deduplicating the Pro store in place.** It is append-only by deliberate design and the main
  consumer already dedups. Fix the hourly collector's re-assertion and add a dedup at the `read()`
  boundary; do not start mutating partitions.
- **Re-litigating player props.** Invariant 2. Nothing in this audit touches it.

---

## RECOMMENDED ORDER (all are bug fixes, not feature work — invariant 3 compatible)

1. **Delete the three threshold overrides from `predict.yml:190-192`** (§1). One-line-per-value
   revert of a config override to the values `config.py` documents. Largest measured effect in
   this audit, and the only band with a CI off zero.
2. **Add an edge floor to the `VALUABLE→MARKSMAN` drift upgrade** (`betting.py:211`) to match the
   guard the `MARKSMAN→SNIPER` path already has (§2).
3. **Fix `p_model` in `shadow.py`** before any further residual research (§12). Every residual
   number to date runs through a max-selected probability.
4. **Persist imputation values in the model payload** (§5). `_prep` must accept fitted medians,
   not recompute them from the batch.
5. **Stop the hourly settlements re-append** and dedup at the `season_store.read()` boundary (§3).
6. **Either source real over15 prices or withdraw over15 from `approved_markets_by_league`** (§4).
7. **Emit real metrics for `__meta__`** (§7) — until then there is nothing for any gate to read.

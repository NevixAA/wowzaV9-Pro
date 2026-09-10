# The Weekly Learning Engine

**Agent 15 — Weekly Self-Improvement Engine Design**
Written 2026-09-10 against Pro `v10/`, v9 `v9/` (frozen), v11 `wowza-v11/`.
All claims tagged PROVEN | SUPPORTED | PLAUSIBLE | SPECULATIVE.

---

## 0. The design in one page

Twelve auditors converged on one result from twelve directions: **there is no measured edge, and
the instruments that said otherwise were broken.** The estate's problem is not that it improves
too slowly. It is that it has no mechanism capable of telling improvement from noise, and it has
been changing live parameters weekly anyway — `best_params_standard.json` moved Bundesliga 2's
SNIPER threshold 0.04 -> 0.19 -> 0.18 across three monthly fits (Agent 11), and it is read ahead
of config in the live money path at `v9/src/betting.py:154-157`.

So this engine is deliberately **asymmetric**. It is easy to learn something and hard to change
anything. Its expected output for the rest of this season is `KEEP_CHAMPION`, every week, with a
growing rejection log. That is success, not failure.

The engine separates three clocks that the current system has fused into one:

| Clock | Period | What it may do | What it may NOT do |
|---|---|---|---|
| **OBSERVE** | weekly, automatic | freeze data, measure everything, publish | write any parameter, model, or threshold |
| **CHALLENGE** | evidence-triggered (counters, typically 4-8 weeks) | build a challenger against a pre-registered ticket | evaluate itself, promote itself |
| **PROMOTE** | gate-triggered, `workflow_dispatch` only | run `evaluate_gate()`, promote or reject | run on a schedule, or run without a ticket |

The weekly job **cannot** change the system. Not "should not" — cannot, because it has no code
path to a parameter file and its workflow stages an explicit file list that contains none. That
structural separation is §R, and it is the section that matters most.

### The one number that reframes everything

Agent 5 concluded Pro's promotion gate is blocked for another 35-55 days per segment because
clean closes accrue at 2.7-4.3/day. I re-measured this run, reading `book_odds_snapshots` as the
**change-log it is** (Agent 4's F2 correction) rather than as a snapshot panel — last quote per
book per fixture, carried forward, before the 1-minute lock:

```
OU25 fixtures in book_odds_snapshots            797
  with >=1 two-sided book close before lock     797  (100.0%)
  with >=3 two-sided book closes                772  ( 96.9%)
  with >=5 two-sided book closes                652  ( 81.8%)

accrual of >=3-book closes, by kickoff week
  2026-W34 162   2026-W35 170   2026-W36 219   2026-W37 200
```

**[PROVEN]** A gate-eligible de-vigged close exists for ~97% of priced OU25 fixtures and accrues
at **170-220 per week**, not 2.7-4.3 per day. `min_clv_n=150` is reachable per segment in **one to
three weeks**, not 35-55 days. Agent 5's figure came from requiring >=3 books *within a single
snapshot instant*, which the archive cannot express because every writer stores
consecutive-distinct changes only (`v9/src/predict.py:199-200`).

The gate was never blocked by data. It was blocked by nobody building the close correctly. That is
the single highest-leverage fact in this design, and it is why §A defines the close once, in code,
and every other section consumes that definition.

### What this engine will NOT fix

Being adversarial about my own deliverable: the two largest measured positive-expectation actions
in the entire audit round sit **outside** this engine.

- Best-price execution on decisions already made: **+2.03pp ROI**, CI [+1.41, +2.73] (Agent 4);
  **+0.72pp** at today's panel depth rising to **+1.80pp** at >=5 books (Agent 11). Both larger
  than any modelling effect measured on either side of zero.
- Margin reduction: Matchbook's median OU25 overround **2.76%** vs the best-of-soft **5.52%**
  (Agent 10) — **+2.6pp** with zero model risk, blocked on a business question nobody has asked.

This engine does not deliver those. It exists to stop the estate harming itself, and to make the
residual question answerable. Do not fund it as a revenue project.

---

## A. The weekly data freeze

**Lives in:** Pro. `v10/src/pipelines/weekly_freeze.py`, new.
**Runs:** `pro_weekly_freeze.yml`, cron `0 5 * * 1` (Monday 05:00 UTC).
**Writes:** `v10/output/weekly/<research_week>/freeze.json` and appends one row to a new
append-only table `data/season_2026_27/research_weeks/`.

### A.1 Three cutoffs, not one

A single "data cutoff" is what makes freezes irreproducible. Three timestamps are needed because
three different things arrive late:

```python
research_week         = "2026-W37"                    # ISO %G-W%V
outcome_cutoff_ts     = Sunday 21:00:00Z of week N    # last kickoff whose RESULT we accept
observation_cutoff_ts = Monday 04:00:00Z of week N+1  # ingest wall: nothing observed after this
market_lock_rule      = "minutes_to_kickoff >= 1"     # src/market/curve.py LOCK_SECONDS = 60
```

`outcome_cutoff_ts` sits 7 hours before `observation_cutoff_ts` because results land through
`pro_backfill_results.yml` (`25 */6 * * *`). A fixture that kicks off Sunday 20:00Z is settled by
Monday 04:00Z; one kicking off Sunday 22:00Z is not, and must belong to week N+1 rather than
entering week N as a silent missing label.

### A.2 What the freeze records

Every field below is required. A freeze missing any field is a hard error, not a warning — the
point of the freeze is that it fully determines the result (the discipline
`v10/src/pipelines/experiment.py` already applies to experiment manifests).

```json
{
  "research_week": "2026-W37",
  "freeze_created_at": "2026-09-14T05:00:11Z",
  "outcome_cutoff_ts": "2026-09-13T21:00:00Z",
  "observation_cutoff_ts": "2026-09-14T04:00:00Z",

  "repo_shas": {
    "pro_git_sha": "<src/data/season_store.py::pro_git_sha()>",
    "v9_source_sha": "<HEAD of NevixAA/wowza-betting at fetch time>",
    "v11_git_sha": "<HEAD of NevixAA/wowza_v11>"
  },

  "model_versions": {
    "v9_model_content_sha": "<src/data/v9_source.py:94 model_content_sha>",
    "v9_model_sha_mtime": "<v9/src/provenance.py::_model_sha() — RECORDED AS UNRELIABLE>",
    "n_model_files": 12,
    "model_bytes": 48211934,
    "pro_champion_ids": {"standard|OU25": "pro_std_ou25_v3", "new_format|OU25": "..."}
  },

  "calc_versions": {
    "feature_manifest_hash": "<registry.hash_manifest(feature_registry.to_frame())>",
    "imputer_manifest_hash": "<hash of src/features/imputers.ImputerManifest>",
    "calibration_version": "<hash of the fitted CalibrationModel>",
    "threshold_hash": "<hash of the EFFECTIVE threshold table, see A.4>",
    "market_calc_version": "devig=power;consensus=median_ex_book;lock_s=60;history_d=7;panel=locf"
  },

  "row_counts": {
    "book_odds_snapshots": 143799,
    "settlements_raw": 126259, "settlements_dedup": 5489,
    "settlements_backfill_unique": 514,
    "clean_closes_ge3_books": 772,
    "eval_frame_ou25_standard": 0, "eval_frame_ou25_new_format": 0
  },

  "freeze_sha": "<hash_manifest of everything above>"
}
```

**[PROVEN]** `v9/src/provenance.py:60-83` hashes `name:size:mtime`, and the docstring says so
explicitly. Every CI checkout stamps a fresh mtime on identical bytes, so `model_sha` is a run
identifier masquerading as a model identifier. Pro's `model_content_sha`
(`v10/src/data/v9_source.py:82-96`) hashes actual bytes and hashes filenames too, so an added or
renamed model changes the version. **The freeze records both and uses only the content sha.** The
mtime one is kept solely so historical `predictions.csv` rows remain traceable.

### A.3 Reproducibility: how "no future data" is enforced

Three layers, because one is a promise and three is a mechanism:

1. **Partition filter at the read boundary.** Pro's store is append-only and run-partitioned
   (`data/season_2026_27/<table>/dt=YYYY-MM-DD/run=<run_id>.parquet`), so a freeze read is
   `dt <= outcome_cutoff_date` **and** `observed_at <= observation_cutoff_ts`. Nothing later can
   enter, and re-running the freeze on a store that has since grown returns byte-identical rows.
   Implemented as `weekly_freeze.py::read_frozen(table, freeze)` — the **only** sanctioned reader
   in the weekly path.

2. **Dedup at the read boundary, not per consumer.** **[PROVEN, Agent 2]** `settlements` holds
   126,259 rows for 5,489 distinct `(fixture_key, market, result)` outcomes — 23.0x inflation from
   `pro_backfill_results.yml` re-asserting all results hourly. I reproduced it this run: raw
   126,259 -> dedup 5,489. Any CI computed on the raw table narrows by ~4.8x. `read_frozen` dedups
   on the table's `REQUIRED` key plus value columns and records `n_raw` and `n_dedup` in the
   freeze. Do **not** mutate partitions — `season_store` is append-only by deliberate design and
   Agent 2's do-not-build stands.

3. **Leakage assertions.** Reuse `src/validation/splits.py::assert_no_leakage` and
   `FinalHoldoutGuard` verbatim. Add two freeze-specific assertions: no market observation used as
   a close has `minutes_to_kickoff < 1` or `is_post_kickoff`; no row's `observed_at` exceeds
   `observation_cutoff_ts`. Both raise `LeakageError` (already defined, `splits.py:41`).

### A.4 The effective threshold table must be reconstructed before it can be hashed

**[PROVEN — six auditors independently]** `config.py` is not the operative configuration.
`v9/.github/workflows/predict.yml:190-192` sets `LEAGUE_SNIPER_CAP=0.12`,
`MARKSMAN_THRESHOLD=0.08`, `VALUABLE_THRESHOLD=0.03`; `config.py:329` applies
`min(v, _SNIPER_CAP)`; and `models/best_params_standard.json` is read *ahead of both* at
`betting.py:154-157`, giving Championship SNIPER 0.07 / MARKSMAN 0.05. Any statement about "the
0.14 threshold" is a statement about a number not in force since 2026-08-21.

So `threshold_hash` is computed over a **reconstructed** table:
`weekly_freeze.py::effective_thresholds()` resolves, per league x market x tier, the value that
actually bound, in the documented precedence order (best_params -> per-league config -> cap ->
global env -> config default), and records the source of each. Anything else hashes a fiction.

Consequence worth stating plainly: because `best_params_standard.json` is overwritten in place
with no version history, **the effective table for past weeks is not fully reconstructible**. From
W38 onward it is. Earlier weeks carry `threshold_hash: "UNRECONSTRUCTABLE"` and every
threshold-conditioned statement about them is tagged `TIER_REGIME_AMBIGUOUS` (§M).

---

## B. Weekly model performance: champion vs challenger

**Lives in:** Pro. `v10/src/pipelines/weekly_learn.py` (new), using
`v10/src/validation/market_relative.py` **as it stands** — it already implements `log_loss`,
`brier`, `auc`, `ece`, `compare`, `compare_by`, and `sample_label` with the exact bands the gate
consumes (`INSUFFICIENT_SAMPLE <50`, `EARLY_SIGNAL 50-250`, `RESEARCH_ONLY 250-1000`,
`VALIDATED >=1000`, `market_relative.py:40-43`).

### B.1 The evaluation frame

One row per `(fixture_key, market)` inside the freeze, built by joining:

| Column | Source |
|---|---|
| `y` | `settlements_backfill` (`y` = did OVER 2.5 happen; 514 unique rows today) |
| `p_model_champion` | `model_snapshots.model_prob` at the decision horizon, or re-scored |
| `p_model_challenger` | challenger scored on the same rows |
| `p_market_open`, `p_market_h`, `p_market_close` | de-vigged consensus per horizon (§G) |
| `book_count_close`, `panel_dispersion` | `book_odds_snapshots` LOCF panel |
| `odds_taken`, `odds_best_panel` | `bets_ledger` (v9, read-only) x panel |
| `league`, `model_type`, `odds_band`, `season_stage`, `minutes_to_kickoff` | as stored |
| `placebo_floor` | v11 (§O.4) |

`p_market_*` uses `src/market/devig.py::power_devig` (Agent 10: the power method "universally
outperforms multiplicative and outperforms or is comparable to Shin"; Agent 4 measured the whole
de-vig question at 0.0002 Brier — settled, do not reopen).

### B.2 Metrics, in the priority order the gate already enforces

`registry.py`'s own docstring fixes the ordering and it is correct — reproduce it, do not
re-litigate it:

1. **market-relative logloss / Brier** — `compare(y, p_model, p_market)` returns model-only,
   market-only, and blend; the only decisive quantity is `blend - market`.
2. **calibration** — `ece(y, p, bins=10)`, gate max 0.05.
3. **real-odds backtest** — REAL prices only. **[PROVEN, Agent 2]** `v9/src/backtest.py:233`
   `_DEFAULT_ODDS={'over15':1.40}` fills 12,186 of 12,187 over15 rows (100.0%) with a constant,
   which made `edge = p_model - 0.6614` a bare probability threshold and certified four leagues in
   `league_roi_config.json`. `odds_policy="REAL_ONLY"` is what refuses this and
   `min_real_odds_coverage=0.80` is what measures it.
4. **CLV** — from the §A close, never from `bets_ledger.clv_pct`.
5. **sample size** — `sample_label`, gate requires `VALIDATED`.

AUC is recorded and **cannot promote anything** (`registry.py` docstring;
`res.checks["auc_recorded"]` is informational). Agent 6 measured exactly why: `p_model` AUC 0.5826
vs consensus-fair AUC 0.5806 on the same n=319 — the discrimination is *inherited from the price*,
because `p_model = edge_pct/100 + 1/odds`.

### B.3 Segmentation

`compare_by` is called once per segmentation, each producing a long frame with `n` attached:

```
by league                 (17 standard + 15 new_format)
by market                 (OU25 / BTTS / OVER15 / OVER35)
by odds_band              (<=1.7, 1.7-2.1, 2.1-2.5, 2.5-3.0, >3.0)
by season_stage           (early <=W6, mid, late >=W32)   -- derived, not v9's inert flag
by horizon                (§G bands)
by model_type x tier      (standard/new_format x SNIPER/MARKSMAN/VALUABLE)
```

Then `src/validation/multiple_testing.py::benjamini_hochberg(q=0.05)` over **all** segment
p-values jointly, with `n_hypotheses` persisted. Its docstring already states the arithmetic: 200
segments at alpha=0.05 yields ~10 false positives. Agent 7 showed what this prevents — the
new_format BTTS SNIPER cell at +35.3% ROI has tier-permutation P=0.2044.

**Odds band matters more than it looks.** **[PROVEN, Agent 6]** odds > 3.0 is 6.1% of bets and
37.6% of the loss: n=48, ROI -53.85%, bootstrap CI [-80.9, -20.6]. Agent 3 found ROI falls
monotonically with price on 4,278 backtest rows while `edge` correlates +0.5874 (Spearman) with
the price taken. The odds band is where the anti-signal is visible; it is not an optional cut.

---

## C. Weekly retraining: how to test the cadence rather than assume it

The brief is right to refuse the assumption. Here is the arithmetic that makes the answer
predictable, stated **before** the experiment so the experiment can falsify it.

### C.1 The pre-registered prediction

**[PROVEN]** Measured this run: labelled outcomes accrue at ~170-220 fixtures/week (§0), and
settled v9 bets at ~150/week (new_format 92-110, standard 48-56, W35-W36). The standard training
frame is ~14k-22k rows (`v9/models/metrics_model_v9_standard.json` reports n_test=4,450 on a
chronological split; Agent 3 puts the deployed pickle at 22,250 rows local / <=9,444 in CI).

A weekly refit therefore changes the training set by **~200 / ~14,000 = ~1.4%**.

**[SUPPORTED] Pre-registered prediction:** a weekly refit cannot move market-relative logloss by
more than sampling noise, and the cadence experiment will return `MONTHLY` or `AFTER_N(N~1000)` —
i.e. ~5 weeks — with weekly refitting indistinguishable from monthly. If the experiment returns
`WEEKLY` with a CI excluding zero, this prediction is wrong and that is a genuine discovery worth
acting on.

### C.2 The cadence x window replay experiment

**Lives in:** Pro. `v10/src/pipelines/cadence_experiment.py` (new), run **once**, offline, by
`workflow_dispatch`. Not a weekly job — it is a one-time study whose answer becomes a constant.

Design: chronological replay over the frozen store. Walk forward in weekly steps. At each step,
under each policy, decide whether to refit; if refitting, fit on that policy's window; then score
**only the next unseen block**. Never score a row the policy's fit has seen.

```
CADENCES                              TRAINING WINDOWS
  WEEKLY                                FULL_HISTORY (flat weights)
  BIWEEKLY                              LAST_3_SEASONS + current
  MONTHLY                               LAST_2_SEASONS + current
  AFTER_N   (N in {500, 1000, 2000})    LAST_1_SEASON  + current
  DRIFT_TRIGGERED (PSI>0.25, 3 wk)      EXPANDING
                                        ROLLING_104_WEEKS
                                        RECENCY_WEIGHTED (half-life 26 / 52 / 104 wk)
```

7 cadences (counting the three N values) x 9 windows (counting three half-lives) = **63
hypotheses** -> BH at q=0.05 with `n_hypotheses=63` persisted. Primary metric: delta
market-relative logloss vs the incumbent policy, paired by fixture, fixture-clustered bootstrap
(Agent 7's method — 5,000 resamples of the *difference*, not of each arm).

**Decision rule, pre-registered:** adopt the **cheapest** policy whose paired delta CI excludes
zero *and* survives BH. If no policy's CI excludes zero -> `UNCHANGED`, keep the current cadence,
and record the study as closed for the season. Ties go to the cheaper cadence and the *longer*
window, because a longer window forgets less (§S).

### C.3 Two measured facts the experiment must not inherit

**[PROVEN, Agent 3]** Recency weighting has never actually been tested, twice over.
`config.py:251` `COVID_SEASONS={'2019/20','2020/21'}` matches **0 of 37,623 rows** because
`fd_history.parquet.season` is `'2019'..'2026'`, and all 10 `TRAINING_DECAY_WEIGHTS` keys are
`'YYYY/YY'` so the set of distinct assigned weights is exactly `{1.0}`. Separately
`v9/retrain.py:371` calls `train_model(std_valid)` with **no `sample_weight` argument at all**,
while `pipeline.py:155` does pass weights — so the weekly production retrain runs the unweighted
path. The experiment must construct its own weights from a correctly-parsed season key, and must
report COVID-era inclusion as an explicit arm.

---

## D. Champion/challenger: use `evaluate_gate()`, add only the feeder

**Do not write a new gate.** `v10/src/models/registry.py::evaluate_gate` (line 133) is complete,
correct, and unit-tested. Its nine named checks:

| check | requirement | source |
|---|---|---|
| `odds_policy_real` | `odds_policy == "REAL_ONLY"` | `GATE["require_real_odds"]` |
| `real_odds_coverage` | >= 0.80 | `min_real_odds_coverage` |
| `holdout_rows` | >= 1000 | `min_rows_holdout` |
| `sample_validated` | `sample_label == "VALIDATED"` | `market_relative.SAMPLE_BANDS` |
| `market_relative_logloss` | `logloss_improvement > 0.0` | vs **market**, not vs old model |
| `market_relative_brier` | `brier_improvement > 0.0` | both, so neither carries alone |
| `calibration` | `ece <= 0.05` | `max_ece` |
| `clv_sample` | `clv_n >= 150` | `min_clv_n`, = v11's `MIN_CLV_N` |
| `clv_positive` | `mean_clv_pct > 0.0` | `min_mean_clv_pct` |

Plus `Registry.promote(..., beat_champion=True)` (line 225), which additionally requires the
challenger to beat the **incumbent's** `logloss_improvement`. Missing evidence FAILS — the
docstring says so and that is the correct default.

### D.1 On ambiguity: KEEP CHAMPION, and it is not a special case

`evaluate_gate` returns `GateResult(passed=False, reasons=[...])` for anything short of all nine.
There is no "provisional", "under review", or "promote pending". The caller's only two outcomes
are `PROMOTED` and `REJECTED(reasons)`. `KEEP_CHAMPION` is the default state and requires no
decision — the system is in it unless a promotion succeeds.

### D.2 Step 0: the registry is empty, and the incumbent is not promotable

**[PROVEN]** `v10/registry/` contains exactly one file: `.gitkeep`. Zero `ModelRecord`s have ever
been written, `.promote(` and `Registry(` appear nowhere in `v10/src/` (Agent 11), and
`evaluate_gate` is reached only from `Registry.promote()`, which is called only from
`tests/test_registry_gates.py`. So `beat_champion` has nothing to compare against.

`v10/src/models/register_incumbent.py` (new, ~80 lines) writes the first records:

- **v9 standard OU25 and new_format OU25 as `EXTERNAL_INCUMBENT`**, status `LIVE`, with their
  honest metrics: Agent 3 measured standard model logloss **0.69100** vs market de-vig **0.67982**
  on n=12,187, i.e. `logloss_improvement = -0.0111`; new_format **0.69328** vs a constant
  **0.69122**, i.e. worse than a constant. `notes` records
  `market_features_present=True; trained_on_closing_odds=True`.
- Why "external": **[PROVEN, Agent 10]** `v9/src/data_loader.py:49` puts `AvgC>2.5` — the
  **closing** average — first in `_OVER_COLS`, and `bookmaker_overround` plus six `api_implied_*`
  columns are declared features at `v9/src/model.py:88,101-107`. The incumbent is therefore already
  partly trained to the market. It can be a *reference*, but it must never be the champion in an
  A-vs-B market-residual comparison, because the comparison would be circular. The first real
  champion must be a **Pro-built, market-free model A** (§E).

Registering the incumbent with a negative `logloss_improvement` is not pessimism, it is the
prerequisite for the gate to mean anything. And note the immediate consequence: with
`mean_clv_pct` measured at **-0.031%** (Agent 12, n=405 clean) and the v11 controlled residual at
**+0.0002, p=0.90**, two of the nine checks fail *today* for every candidate. **The gate would
currently refuse everything.** Say so in the first review, or someone will read the first
`REJECTED` as a bug.

### D.3 The rejection log — how you know the gate works

**Lives in:** Pro, append-only. `data/season_2026_27/gate_decisions/` plus the human-readable
`v10/output/weekly/rejection_log.csv`.

One row per gate evaluation, ever, including re-evaluations of the same challenger:

```
research_week, decision_ts, model_id, scope, market, challenger_kind,
ticket_id, freeze_sha, decision (PROMOTED|REJECTED),
failed_checks (semicolon list), reasons (verbatim GateResult.explain()),
logloss_improvement, brier_improvement, ece, clv_n, mean_clv_pct,
holdout_rows, sample_label, real_odds_coverage, beats_champion,
n_hypotheses_this_week, look_number, look_budget_remaining
```

`look_number` and `look_budget_remaining` are the multiplicity ledger (§R.5). A gate with an empty
rejection log has never been exercised, and an engine that only records successes is a marketing
document.

### D.4 One gap in the gate, fixed outside it

`evaluate_gate` has no multiple-testing and no anytime-validity check. Evaluated every week against
a fixed bar, a challenger gets 52 looks a year and the effective false-promotion rate is far above
the nominal one. **Do not edit the gate** — put multiplicity in the *admission* rule (the challenge
ticket, §R.2) and in the look budget (§R.5). The gate answers "is this challenger good enough"; the
ticket answers "is this challenger allowed to ask".

---

## E. Do market snapshots improve the model? Models A-E

This is the section with the highest contamination risk, so the firewall is described before the
experiment.

### E.1 The five models

| id | features | purpose |
|---|---|---|
| **A** | football only. No odds, no overround, no `api_implied_*`, no `p_over25_poisson_dc` fallback | the **only** production candidate |
| **B** | A + opening de-vigged consensus (first observation within `HISTORY_DAYS=7`) | how much of the price is knowable early |
| **C** | A + de-vigged consensus at the latest **allowed** horizon (§G, never past lock) | the ceiling |
| **D** | A + movement features (open->h drift, velocity, dispersion, book churn) | is the *path* informative beyond the level |
| **E** | market only (de-vigged consensus, no football at all) | **the baseline everything is measured against** |

Model A must be built fresh in Pro. **[PROVEN]** v9's standard model cannot serve as A: its
`FEATURE_COLS` include `bookmaker_overround` and six `api_implied_*` columns, and `odds_over25` is
sourced from the closing average. Agent 3 also measured that `bookmaker_overround` is the standard
model's **5th most important feature at 5.47%** while new_format assigns it exactly 0.000000 — so
the two tracks are not even contaminated the same way. (Invariant 1 already forbids mixing them;
this is a second reason to keep the A-builds separate.)

Feature membership is enforced by category, not by eyeballing a list: `v10/src/feature_registry.py`
already defines `FOOTBALL`, `MARKET`, `MICROSTRUCTURE`, `INFORMATION`, `QUALITY` (lines 57-61).
Model A's manifest is asserted to contain **zero** `MARKET` and zero `MICROSTRUCTURE` features. The
assertion is in the builder, and its hash is in the freeze.

### E.2 The two questions are different, and conflating them is the classic error

**Question 1 — does it improve OUTCOME PREDICTION?**
Compare on logloss/Brier/ECE against **E**, chronologically, on the final holdout only. Expected
shape: C >= B >= E > A. This is nearly guaranteed and nearly worthless on its own — of course
adding the price improves a forecast, the price is the best single forecast available
(**[PROVEN, Agent 10]**: market closing logloss 0.68000 / AUC 0.5848 on n=4,450 versus v9's best
base model 0.68833 / 0.5484 on the same n; over the full 7 seasons Pinnacle closing scores
0.67274 / 0.6100 on n=13,216).

**Question 2 — does it improve BETTING VALUE?**
Only answerable against the price you would actually pay, so the metric is not logloss: it is CLV
against the §A close, beat-close rate, and ROI **on a decision rule fixed in advance**. And here
B-E are structurally disqualified: a model containing the current price cannot generate an edge
against that price, because its "disagreement" is by construction a lagged copy. Training to the
market collapses the residual to zero **by construction** (brief §3) — B-E are the mechanism by
which that would happen.

### E.3 The firewall: three enforced barriers

1. **Scope naming.** B-E register with `scope` suffixed `:research` (e.g.
   `standard:research|OU25`) and `status="RESEARCH"`. `Registry.champion()` filters on
   `status == "LIVE"`, so a RESEARCH record can never be returned as a champion.
2. **A promotion guard in the caller, not the gate.** `src/models/challenger.py::submit()` refuses
   — raises, does not warn — any promotion request for a record whose `feature_manifest_hash`
   resolves to a manifest containing a `MARKET`-category feature. Override requires a hand-written
   ticket naming the invariant being crossed. This is the concrete answer to "how to run this as
   research without contaminating the production opinion": the production opinion is model A, and
   the code cannot promote anything else.
3. **Separate output paths.** B-E metrics land in `v10/experiments/<experiment_id>/` (the existing
   `experiment.py` layout: `manifest.json`, `metrics.json`, `by_league.csv`, `calibration.csv`,
   `bets.parquet`) and appear in the weekly review under a `RESEARCH` heading. They never enter
   `weekly_model_scoreboard.csv` with a promotable status.

### E.4 What B-E are actually *for*

They measure a number nothing else can: **delta(C, E)** — how much football information exists that
the price does *not* already contain, measured on top of the price rather than against it.

- If **C ~ E** (delta CI spans zero): there is no football residual. Then model A's ceiling is zero
  and every hour spent on A is waste. This is a **go/no-go on the entire modelling programme**, and
  it is the cheapest such test available.
- If **C > E** with a CI excluding zero: a residual exists. You still cannot bet C. But you now know
  A is *worth building*, and delta(C, E) is the target A must approach.

Agent 10 supplies both the external precedent and the correct objective: arXiv 2608.11505 fitted a
market-vs-structural-model pooling weight of exactly **0.000** on 7,220 Serie A matches, and
Hubacek & Sir (arXiv 2010.12508) prove profit is achievable with an inferior model *by explicitly
decorrelating it from the market*. Decorrelating from the price is the opposite operation from
fitting to it, and delta(C, E) is how you tell whether there is anything left to decorrelate.

---

## F. Should the score move when the market moves? `MARKET_CONFIRMATION_SCORE`

### F.1 Why this must be a separate layer, with evidence

v9 already has a silent probability-adjacent adjustment and it is measurably harmful.
**[PROVEN]** `v9/src/betting.py:211-213` upgrades VALUABLE -> MARKSMAN on
`drift_signal == "Confirmed"` with **no edge floor**, while :208 requires `best_edge >= 0.10` for
MARKSMAN -> SNIPER. Agent 6 measured the states: `Conflicted` n=135, ROI **-20.99%**,
CI [-38.9, -2.9] — one of the very few CIs in the whole audit round that excludes zero — and the
code's response (`betting.py:205`) is to downgrade SNIPER+Conflicted to MARKSMAN, i.e. bet it at
3/4 stake instead of not at all. Agent 3 adds that this upgrade path bypasses Bundesliga 2's
explicit MARKSMAN disable (`config.py:338`, commented "no MARKSMAN bets here; 8-20% = -10.8% ROI"),
and eight such bets were staked anyway at median edge 5.70% for -3.23u.

And **[PROVEN, Agent 4]** the signal is smaller than its own ruler: mean |over_drift| over a
fixture's life is **4.32%** of the opening price, while the median cross-book range at a *single
instant* is **8.67%** of price. v9's drift verdict also inverts on ~3.8% of fixtures purely because
the selected book switches between open and close (18.11% of fixtures switch book; 56.1% of |drift|
on those is the switch).

So: market movement is currently consumed as an unfloored stake multiplier built on a quantity half
the width of the measurement noise. MCS replaces that with something measured.

### F.2 Definition

**Lives in:** Pro. `v10/src/market/confirmation.py` (new), consuming `book_odds_snapshots` via the
§A LOCF panel and `src/market/devig.py`.

```
For a (fixture_key, market, side) and a decision timestamp t_d:

  p0 = de-vigged consensus fair prob at t_d      (median across books, EX our book)
  p1 = de-vigged consensus fair prob at LOCK     (the §A close)
  raw_move = (p1 - p0) signed toward OUR SIDE    (+ = market moved toward us)

  MCS = raw_move / sigma_segment
        sigma_segment = sd(raw_move) within (league, market, horizon_band, book_count_band),
                        estimated on PRIOR blocks only, minimum 250 observations,
                        else MCS = NaN and reason = "INSUFFICIENT_DATA"
```

Normalising by a *prior-block* sigma is what stops MCS being re-scaled by the sample it is
evaluated on. `book_count_band` is in the conditioning set because Agent 4 measured churn at 18.1%
of consensus-movement variance on a correct panel and 42-53% on a raw read — the noise floor
depends on panel depth, so sigma must too.

### F.3 The test

Pre-registered in `docs/PREREGISTERED_HYPOTHESES.md` before computation:

- **H_F1:** MCS adds information about the outcome *given* the market price.
  Model: `logit(y) ~ p_market_close + p_model + MCS` on the frozen eval frame.
  Pass: beta_MCS CI excludes zero on **>=2 of 3** chronological blocks, each with **n >= 1,000**,
  and survives BH among that week's hypotheses.
- **H_F2:** MCS adds *betting* value. On the same fixed decision set, does conditioning on
  `MCS < threshold_prereg` improve realised CLV? Metric: paired fixture-clustered bootstrap of
  delta-CLV. Pass: CI excludes zero on >=250 bets.
- **Falsification:** if beta_MCS CI spans zero in >=2 of 3 blocks, MCS is closed for the season and
  its look budget is spent.

### F.4 The permitted consumer, and why it is a veto only

If H_F1 and H_F2 both pass, MCS's **only** permitted first consumer is a **VETO**: a candidate bet
whose MCS is below a pre-registered floor becomes `NO_BET`. Never a tier promotion, never a stake
multiplier, never an adjustment to `p_model`.

The reason is structural, not stylistic: a veto can only *remove* bets, so its worst case is fewer
bets. A promotion *manufactures* bets that no edge test authorised — which is precisely the
mechanism that produced the unfloored VALUABLE -> MARKSMAN population. A veto's downside is
bounded; a promotion's is not.

Output: `v10/output/weekly/<week>/mcs_scoreboard.csv` and a `market_confirmation_score` column in
`weekly_signal_layers.csv`. Never written into `model_prob`.

**Prerequisite (blocking):** v11's `scripts/v11_momentum_control.py:158` returns
`out.sort_index()["p_at"]` after a `pd.merge_asof`, which resets to a fresh RangeIndex — so every
movement value lands on the wrong row. **[PROVEN, Agent 7]** corr(prev_move, future_move) =
**-0.9995**, P(sign flip) = 0.996, against a real series where **81.9%** of consecutive deltas are
exactly 0. Any movement research built before that one line is fixed is nine wrong answers.

---

## G. Which horizon carries the information?

**Lives in:** Pro. `v10/src/market/horizon.py` (new) + `weekly_horizon.csv`.

### G.1 The bands, and what the data can currently support

Measured this run on `book_odds_snapshots` OU25 (797 fixtures, 74,379 rows):

| band | share of observations | fixtures with >=1 obs | verdict today |
|---|---|---|---|
| > 24h | 63.5% | 774 (97%) | measurable |
| 6-24h | 17.9% | 566 (71%) | measurable |
| 3-6h | 6.3% | 383 (48%) | measurable |
| 1-3h | 6.1% | 441 (55%) | measurable |
| 30-60m | 2.6% | 213 (27%) | EARLY_SIGNAL |
| 10-30m | 2.1% | 164 (21%) | EARLY_SIGNAL |
| 0-10m | 1.6% | 136 (17%) | **INSUFFICIENT_DATA** |
| post-KO | **0.0%** | 0 | clean — no in-play contamination on this table |

**[PROVEN]** The near end of the horizon question is **not currently answerable**: n=136 at T-10m
is below the n<250 bar and barely above the n<50 floor. Agent 5's regression explains why — per-
fixture T-30m coverage fell from 84.7% (n=177, KO 08-19..08-26) to 29.4% (n=228, KO 08-31..09-06),
a -55.4pp change with CI [-63.3, -47.4], degrading in **17 of 17** leagues after commits 674e36e0
/ f7d10352 / 0104cf96.

So §G ships in two stages, and the first stage is instrumentation:

- **Stage 1 (now):** answer G for > 24h, 6-24h, 3-6h, 1-3h. Report the near bands as
  INSUFFICIENT_DATA with their n, every week, so the gap is visible rather than silently absent.
- **Stage 2 (after the near-kickoff worker):** re-run at the near end. Agent 5's spec —
  ~28 fixtures/day x 60 polls = 1,704 API-Football calls/day, taking utilisation from a measured
  ~15.0% to ~17% of 75,000 — must run in **Pro**, on **API-Football** credits, never on The Odds
  API (projected 89,842/100,000, and `markets x regions` billing would make the same cadence
  ~204,000/month). Justify it as instrumentation for the gate, not as edge.

### G.2 The per-horizon table

One row per `(research_week, league, market, horizon_band)`:

```
n_fixtures, n_bets,
market_brier_h, market_logloss_h,          -- de-vigged consensus AT that horizon vs outcome
model_residual_h, residual_ci_lo, ci_hi,   -- compare(y, p_model, p_market_h).blend - .market
mean_abs_future_move_to_lock,              -- how much price information is still to come
outcome_base_rate,
clv_if_struck_here, beat_close_rate,
roi_if_struck_here, roi_ci_lo, roi_ci_hi,
placebo_floor_h,                           -- v11 zero-information predictor at this horizon
sample_label, bh_q, verdict
```

`mean_abs_future_move_to_lock` is the column that makes this actionable: it says how much of the
price's eventual information has not yet arrived. If the model's residual is positive at T-24h and
zero at T-1h, the honest reading is not "we are good early" but "the market has not yet priced what
we know, and by the close it has" — which is a *timing* opportunity (§N) rather than a forecasting
one. The reverse pattern means the opposite. Both are real answers; the brief is right that we do
not know which.

---

## H. League threshold optimisation without violating invariant 6

### H.1 What is wrong with the two existing optimisers

**[PROVEN]** `v9/src/backtest.py:540-549` picks the ROI-maximising point over 22 grid values and
`:582` **deploys that in-sample maximum**, while `:580` computes `approved` from a *different*,
per-fold OOS threshold. So the number that is validated is not the number that ships.
`optimize_side_market_thresholds` (`:422-486`) has **no train/test split at all** at `min_bets=20`.
And `marksman_th = max(th - 0.02, edge_min)` (`:583`) is an unmeasured offset that decides
3/4-stake real money.

The output is visibly unstable. **[PROVEN, Agent 11]** across three revisions of
`best_params_standard.json`: Bundesliga 2 sniper_th 0.04 -> 0.19 -> 0.18 (0.04 -> 0.19 in **seven
days**), Championship 0.24 -> 0.08 -> 0.07, League Two 0.20 -> 0.07; `approved` flipped in 3 of 7
leagues, with Championship rejected at n_oos=311 (ROI -7.90) and then **approved** at n_oos=164
(+3.32) one month later on a *growing* dataset.

**The intervention is a deletion, not a better search.** Agents 2, 6, 11 and 12 all reach this
independently. Nothing in this design re-optimises live thresholds.

### H.2 The compliant method: nested, evaluate-only

**Lives in:** Pro. `v10/src/pipelines/threshold_curves.py` (new). Research output only; writes no
parameter anywhere.

```
For each (league, market, tier):
  chronological blocks k = 1..K  (K=4, src/validation/splits.py::chronological_blocks)
  for k in 1..K-1:
      curve_k    = ROI vs threshold on block k          (FITTING, discarded)
      th_star_k  = argmax(curve_k)                      (a number, frozen here)
      eval_{k+1} = ROI at th_star_k on block k+1 ONLY   (EVALUATION, reported)
  report the EVALUATION series. Never report argmax ROI.
```

The reported quantity is the performance of a rule *chosen before it was seen*, which is the whole
of invariant 6. `FinalHoldoutGuard` prevents a second read of the last block.

### H.3 Verdicts and the minimum n

| verdict | condition |
|---|---|
| `HIGHER` | mean evaluated delta > 0, CI excludes zero, argmax moved up in >=3 of 4 blocks, n_eval >= 250 |
| `LOWER` | symmetric |
| `UNCHANGED` | n_eval >= 250 and CI spans zero |
| `INSUFFICIENT_DATA` | n_eval < 250, or direction inconsistent across blocks |

`n_eval` counts **evaluated bets in out-of-sample blocks only**. The direction-consistency rule
exists because a single block's argmax at n=31 is a coin flip — La Liga 2 in-sample +14.39% on
n=31 became OOS -5.84%; League One +4.11% on n=36 became -59.0% (**[PROVEN]**,
`best_params_standard.json`).

**Predicted verdict for almost every cell: INSUFFICIENT_DATA.** Agent 6 tested all leagues with
staked n>=5 and found **not one** CI excluding zero, 17 of 17. At the measured ~150 settled
bets/week pooled across both tracks and all tiers, a single league x market x tier cell accrues a
few bets a week. **Per-league threshold work is not authorised this season** (§R.3), and this
pipeline exists to *say that with a number* every week rather than to be trusted when it eventually
returns something.

### H.4 The MARKSMAN/SNIPER asymmetry the seed found

The seed is right that `LEAGUE_MARKSMAN_THRESHOLDS` covers only
`{Bundesliga 2: .20, League Two: .14}` while `LEAGUE_SNIPER_THRESHOLDS` covers most leagues. But
the asymmetry is **not** the binding defect, and the audits corrected this in three ways worth
recording so the next reader does not re-chase it:

- **[PROVEN]** The global floor in force is **0.08**, not 0.14 (`predict.yml:190-192`), and
  `best_params_standard.json` overrides both.
- **[PROVEN, Agent 10]** `config.py:283-285` sets
  `SNIPER_THRESHOLD = 0.12 < MARKSMAN_THRESHOLD = 0.14` and `betting.py:171` tests SNIPER
  **first**, so for a globally-thresholded league `_base_tier` can *never* emit MARKSMAN. Every
  such MARKSMAN row necessarily came from the drift promotion. The asymmetry in the threshold
  *tables* is downstream of an ordering bug in the *tier function*.
- **[PROVEN, Agents 7, 11, 12]** Fixing the drift floor targets the **better** half. Agent 12:
  below-threshold (drift-promoted) n=21 ROI -13.4% vs compliant n=21 ROI -49.9%. Agent 7:
  drift-manufactured n=19 ROI -28.7% vs earned-on-edge n=20 ROI -35.8% (standard), and +6.5% vs
  -4.6% (new_format). Agent 11: 79% of the standard MARKSMAN loss cleared the operative floor.

Therefore this design does **not** propose the drift-floor fix as an improvement. It proposes
recording the effective threshold and the promotion path per row (§A.4, §M
`TIER_REGIME_AMBIGUOUS`) so the question becomes answerable at n>=250 instead of being settled at
n=21 in either direction.

---

## I. Adaptive thresholds — designed, and explicitly BLOCKED

`minimum_required_edge = f(context)` is the right long-run shape and it is not authorised yet.

### I.1 Why blocked

**[PROVEN]** The *input* carries no information. Agent 12: `corr(edge_pct, pnl) = +0.0220`,
permutation p=0.664, Spearman +0.0257 p=0.602, n=416. Agent 6: Spearman(edge, win) = **+0.0037**,
p=0.918, n=788, and a logistic on edge controlling for `1/odds` gives beta=+0.443, se=0.983,
p=0.652. Agent 7: Spearman(edge_pct, pnl) = **-0.0052** on 184 post-cutoff staked bets, with the
>=14% bucket at -10.2% ROI.

A function of a variable that does not order outcomes cannot order outcomes. Worse, Agent 12
measured `corr(edge_pct, clv_pct) = -0.2022`, n=405, permutation p=0.00005, bootstrap CI
[-0.290, -0.113], monotone by bucket (edge 0-4% -> CLV +1.183%; edge 8-10% -> -3.108%). The claimed
edge is *anti*-correlated with beating the close.

**Gating rule: §I is BLOCKED until §H returns any verdict other than INSUFFICIENT_DATA for at least
one league x market, and until §G identifies at least one horizon with a positive residual CI
excluding zero.** Ship the measurement; do not ship the rule.

### I.2 The design, for when it unblocks

```
risk_index = monotone scalar built from PRE-DECISION context only:
    book_count, panel_dispersion, minutes_to_kickoff, PSI severity of the row's own features,
    n_missing_features, thin_form flag (1-4 matches), no_form_data flag,
    league, market, odds_band, MCS (only if §F passed)

min_required_edge = isotonic_fit(risk_index) on blocks 1..k, EVALUATED on block k+1 only
```

Monotone/isotonic rather than a free-form learner, on purpose: it has one degree of freedom per
knot and cannot invent a non-monotone pocket, which is the shape false discoveries take here.

Promotion conditions: beats the flat threshold on **>=3 of 4** evaluation blocks, on **>=250**
evaluated bets, surviving BH, with the same paired fixture-clustered bootstrap. Anything less ->
`INSUFFICIENT_DATA`, and the look budget decrements.

Two context variables deserve their own note because they are the ones most likely to be real:
`no_form_data` and `thin_form`. **[PROVEN, Agents 2 and 3]** `feature_engineering.py:127` uses
`rolling(n, min_periods=1)`, so a team with **one** prior match presents a "last-5" average
indistinguishable from a true one, and `betting.py:353-358` only forces AVOID on NaN — so the
invariant-8 guard fires at zero matches and not at insufficient ones. Compounded until 2026-09-15
by `predict.yml:188` `REQUIRE_FORM_DATA='0'`. Agent 12's open question is the right one and it is
free: **split all 416 settled bets by `no_form_data` before 2026-09-15**, because the population
changes when the guard re-arms.

---

## J. Weekly feature drift

**Lives in:** Pro. Use `v10/src/monitoring/drift.py` **as it stands** — `psi()` (line 45,
training-quantile bin edges, correctly refusing to move the ruler with the thing measured),
`ks_statistic()` (71), `feature_drift()` (119), `prediction_drift()` (195), `health_summary()`
(232), thresholds `PSI_STABLE=0.10`, `PSI_SIGNIFICANT=0.25`, `KS_SIGNIFICANT=0.15`,
`OUT_OF_RANGE_SIGNIFICANT=0.05`.

**Output:** `v10/output/weekly/<week>/weekly_feature_drift.csv` + append to
`data/season_2026_27/feature_drift/`.

### J.1 The one addition needed

`feature_drift()` needs a **training reference distribution**, and no champion currently persists
one. Add to `register_incumbent.py` / `challenger.py`: at registration, write
`v10/registry/refs/<model_id>_train_ref.parquet` holding, per feature, the training quantiles (21
points) plus min/max/mean/sd/missingness. Small, versioned with the model, and it makes drift
measurable against what the model was *fitted* on rather than against last week.

Without it, "drift" measures week-to-week variation in the serving population, which is a different
and much less useful quantity.

### J.2 Fields

```
research_week, model_id, feature, category (FOOTBALL|MARKET|...), required,
psi, ks, out_of_range_pct, missingness_serve, missingness_train,
mean_train, mean_serve, sd_train, sd_serve, n_serve,
flags (semicolon), severity (OK|WATCH|SIGNIFICANT),
drift_persistence_weeks
```

### J.3 Drift is an observation. It authorises nothing on its own.

`drift_persistence_weeks` is the counter, and the only trigger is **PSI > 0.25 on a *required*
feature for >=3 consecutive weeks** (§R.3). One week of PSI 0.3 is noise on n~200; three
consecutive weeks is a regime.

`drift.py`'s own docstring already states the correct posture — "Nothing here decides anything. It
produces flags" — and this design keeps it. Two known conditions this will surface immediately,
both already measured, both worth watching rather than fixing blind:

- **[PROVEN, Agent 2]** When a column is 100% NaN in a prediction batch, `model.py:128-129`
  produces exactly 0.0, which is z = -5.24 / -5.23 for `home/away_fouls_pg_roll` and -3.50 / -3.52
  for the corners rolls — about **24.6% of GBM decision weight on physically impossible values**.
  But re-scoring the live board with correct train-mean imputation moved `p_over25` by only
  **0.84pp mean / 2.59pp max**, with **0 of 77** fixtures crossing 4pp. Fix it for correctness
  (~20 lines); do **not** sell it as a P&L fix.
- **[PROVEN, Agents 2 and 3]** 23 of 65 declared features never reach the trained model —
  `model.py:126` drops columns absent from the *training* frame, so the deployed pickle has 42
  columns (standard) / 27 (new_format). The dropped set includes all six `api_implied_*` columns
  that ~10-14k API-Football calls/day currently buy. Drift monitoring must report on the **42
  deployed** features and separately list the 23 as `NOT_IN_MODEL`, or it will report drift in
  features that cannot affect anything.

---

## K. Weekly calibration

**Lives in:** Pro. `market_relative.ece()` + `src/models/calibration.py` (`fit_calibration` line
129, `calibration_table` line 179, `LeagueCalibration`, per-league-with-shrinkage).
**Output:** `v10/output/weekly/<week>/weekly_calibration.csv`.

### K.1 Fields

```
research_week, model_id, model_type, market, league, odds_band, bin_index,
p_lo, p_hi, n, mean_p_pred, observed_rate, residual_pp,
ece_segment, ece_ci_lo, ece_ci_hi, sample_label,
direction (HOT|COLD|OK), calibration_persistence_weeks
```

Ten equal-width probability bins (matching `ece(..., bins=10)`), and the *same* bins every week —
recomputing bin edges on new data silently changes the test, exactly as
`docs/PREREGISTERED_HYPOTHESES.md` already warns about quartiles.

### K.2 This is the cheapest legitimate improvement available

**[PROVEN, Agent 6]** On the model's own selected bets, n=788: mean `p_model` **0.5435** vs actual
**0.4086** — **+13.5pp overconfident**; Brier 0.2586 vs the book's 0.2372; logloss 0.7143 vs
0.6667. On staked tiers, **+16.8pp** bias. Against a measured de-vigged consensus fair line
(n=319), the model overstates by **+8.58pp**.

And Agent 6's ranking result: `p_model` AUC **0.5826** vs consensus-fair AUC **0.5806**. The
model's *ordering* is roughly as good as the market's. What it lacks is calibration and price.
Recalibration attacks the measured defect directly, needs no new features, and does not touch odds.

### K.3 Recalibration challengers

Candidates, all already implemented: global Platt (`_fit_platt`, line 53), isotonic,
per-league-shrunk (`fit_calibration`). Fitted **only on the CALIBRATION block** of the freeze
(`splits.py` block 2), scored **only on the FINAL HOLDOUT** (block 4). Submitted through the normal
ticket -> gate path.

Trigger: `calibration_persistence` >= 4 consecutive weeks with |residual_pp| > 5pp in the **same
direction** on a segment with n >= 500 (§R.3). Given the measured +8.6 to +16.8pp bias, **this is
the trigger most likely to fire first**, and it is the right one to fire first.

**Forbidden alternative, named so it is not proposed:** blending the market probability into the
model output would close the calibration gap **by construction** and destroy the residual that is
the only thing being measured (brief §3; Agents 6 and 11 both flag it). Isotonic/Platt on realised
**outcomes** achieves the same calibration without touching a price.

---

## L. Weekly market learning: `bookmaker_information_score`

**Lives in:** Pro. `v10/src/market/book_info.py` (new), reading `book_odds_snapshots` through the
§A LOCF panel.
**Output:** `v10/output/weekly/<week>/weekly_book_info.csv` + `data/season_2026_27/book_info/`.

### L.1 The panel, measured

`book_odds_snapshots`: 143,799 rows, 24 bookmakers, markets OU25 74,379 / BTTS 51,780 / OU35 15,813
/ OU15 1,827. Per-book OU25 fixture coverage, measured this run:

```
betsson      776   nordicbet   776   williamhill  719   unibet_se    641
leovegas_se  641   onexbet     623   unibet_nl    595   tipico_de    577
matchbook    531   pmu_fr      464   codere_it    439   coolbet      436
betonlineag  342   pinnacle    273   gtbets       266   betanysports 107
mybookieag    66
```

**[PROVEN] Pinnacle covers 273 of 797 OU25 fixtures (34.3%).** That is `RESEARCH_ONLY` under the
existing sample bands and it is **not enough to call any book sharp**. Agent 4's lead/follow result
(pinnacle +0.120 lead-minus-follow, z~2.5) is real and is about *the consensus*, not about
*outcomes* — and Agent 4 flagged the confound himself: a book is being compared to a consensus it
is inside.

### L.2 Four components, each reported separately with its own n

```
1 lead_frequency
    P(book moves in the direction consensus_EX_BOOK moves at t+dt)
  - P(book moves in the direction consensus_EX_BOOK moved at t-dt)
    -- the book is EXCLUDED from the consensus it is scored against (removes Agent 4's confound)

2 close_correlation
    corr( book fair prob at T-6h , consensus_EX_BOOK fair prob at LOCK )

3 stability
    1 - share of consensus-moves (>0.4pp) during which this book did not move
    + reprice_frequency = moves per fixture-hour
    -- upper bound only: LOCF cannot distinguish "frozen" from "withdrew the market" (Agent 4)

4 outcome_brier
    Brier of the book's OWN de-vigged fair price at LOCK against y
    -- the only component about being RIGHT rather than about being FIRST
```

### L.3 The composite, and the evidence bar

```
bookmaker_information_score is published ONLY when n_fixtures >= 250 for that book x market.
Below that: components published with n, composite = NaN, verdict = INSUFFICIENT_DATA.

A book is labelled SHARP only if outcome_brier's CI excludes the panel-median book's Brier.
Leading the consensus is not sharpness. It is being early.
```

**[PROVEN, Agent 4]** the ceiling here is small: at OU25 the whole gap from a base-rate constant
(0.24454) to the best estimator (closing consensus 0.23622) is ~0.008 Brier, and every consensus
variant tested lands within 0.00024 of every other (median 0.23622, trimmed 0.23639, mean 0.23646,
1/best_odds with no de-vig at all 0.23641, n=291). So `bookmaker_information_score`'s honest job is
**not** to find a better probability. It is to decide **which books to hold accounts with** — which
is §N's `book_selection` and `price_shopping` attribution, and *that* is worth +1.4 to +2.7pp.

Concretely: Agent 4's greedy panel found `{betsson, onexbet, unibet_se, matchbook}` recovers
**99.36%** of the best OU25 price at 99.96% instant coverage; five books reach 99.56%; beyond that
< 0.4%. `book_info.py` should re-derive that greedy panel weekly and report **panel drift** — if the
recovering set changes, the account roster is stale. Agent 4's do-not-build stands: more than five
books is operational cost.

---

## M. Weekly error analysis with a fixed taxonomy

**Lives in:** Pro. `v10/src/pipelines/weekly_error.py` (new).
**Output:** `v10/output/weekly/<week>/weekly_error_analysis.csv`.

### M.1 The taxonomy is fixed, and adding a code starts a new counter

Codes are pre-registered. A code added mid-season gets its own counter starting at that week — it
does **not** retroactively reinterpret earlier weeks. Without that rule the taxonomy becomes a
narrative device that always explains the most recent loss.

| code | definition (mechanical, no judgement) |
|---|---|
| `NO_FORM_DATA` | `no_form_data == True` |
| `THIN_FORM` | 1-4 prior matches for either team (the `min_periods=1` hole) |
| `IMPUTED_FEATURE_HEAVY` | > 20% of the model's decision weight on imputed values |
| `FEATURE_DRIFT_SIGNIFICANT` | any required feature PSI > 0.25 that week |
| `NAME_RESOLUTION_FALLBACK` | the fixture resolved via a substring/normalised fallback |
| `STALE_CLOSE` | §A close older than T-6h |
| `THIN_PANEL` | < 3 two-sided books at the close |
| `NO_TWO_SIDED_CLOSE` | no de-vig possible |
| `PRICE_TAKEN_BELOW_BEST` | `odds_taken < odds_best_panel` at the decision instant |
| `LONGSHOT` | `odds_taken > 3.0` |
| `CALIBRATION_HOT` / `CALIBRATION_COLD` | the row's bin residual > +5pp / < -5pp |
| `MODEL_MARKET_DISAGREE_LARGE` | abs(p_model - p_market_close) > 10pp |
| `TIER_REGIME_AMBIGUOUS` | tier not reproducible from the row's own recorded edge + effective table |
| `GENUINE_VARIANCE` | residual bucket: none of the above |

`TIER_REGIME_AMBIGUOUS` is not a rare edge case. **[PROVEN, Agent 1]** re-running
`_base_tier + _apply_drift_adjustment` on the recorded edge/league/side/drift of all 210 live
standard rows produced **97 mismatches = 46.2%**. **[PROVEN, Agent 11]** `ledger.py:169` ratchets
the tier upward over ~2,000 re-evaluations while `generated_at` stays at first sighting and `odds`
stays at first sighting while `edge_pct` advances — so a single row can straddle three threshold
regimes and its `(edge, odds)` pair mixes two snapshots.

`GENUINE_VARIANCE` is load-bearing in the other direction: **if it dominates, stop looking for
bugs.** Agent 6's Monte-Carlo null on v9's own 788 entry prices gives H0 mean **-37.60u**, sd 31.9
against observed -68.75u, p=0.164 at overround 1.05. A -2u week is inside the null band and means
nothing.

### M.2 Fields

```
research_week, taxonomy_code, model_type, market, league,
n_bets, n_fixtures, pnl, roi, roi_ci_lo, roi_ci_hi,
mean_clv, beat_close_rate, share_of_week_loss, share_of_season_loss,
n_new_this_week, cumulative_n, sample_label
```

`share_of_loss` is the field that stops the taxonomy being decorative: **[PROVEN, Agent 6]**
`LONGSHOT` is 6.1% of bets and **37.6%** of the loss. That ratio is the output, not the count.

---

## N. Weekly edge attribution

**Lives in:** Pro. `v10/src/pipelines/weekly_attribution.py` (new).
**Output:** `v10/output/weekly/<week>/weekly_edge_attribution.csv`.

### N.1 The method: counterfactuals with the decision set held FIXED

Every component is a counterfactual on prices, timing, or books — **never** on the decision set.
Re-deriving `edge_pct` off a better price and re-tiering would be fitting thresholds on the same
outcomes being evaluated (invariant 6). Agent 4 states this discipline explicitly and it is why the
+2.03pp number is trustworthy: "same bets, better price".

| component | counterfactual |
|---|---|
| `model` | P&L of the actual selection vs P&L of a market-only selection on the same board |
| `price_shopping` | same bets at best-of-panel price - at the price taken |
| `timing` | same bets at the best price available across horizons - at the taken horizon |
| `book_selection` | taken book's price - panel median at the same instant |
| `threshold` | P&L of bets clearing the *effective* threshold vs those admitted by drift promotion |
| `variance` | realised - sum(components), reported **with** the Monte-Carlo null band |

### N.2 What the components already measure, and one live disagreement

- `price_shopping`: **[PROVEN, Agent 4]** best price captured on only **46.6%** of 311 matched
  bets; mean shortfall 1.909% of price (p90 5.991%); paired counterfactual on settled n=217 moves
  -20.90u (-9.63%) -> -16.50u (-7.60%), **+2.03pp**, bootstrap CI **[+1.41, +2.73]**. new_format
  flips -1.75% -> +0.43%. Root cause: `v9/src/predict.py:136-139` takes the first-listed
  bookmaker's price (`if pt == 2.5 and nm == "Over" and not ov25: ov25 = pr`).
- **Disagreement to report, not resolve:** Agent 11 measures the same uplift at **+0.72pp** at
  today's panel depth (best-of-available overround 1.0552 vs single-book 1.0696, n=12,748 groups,
  median 2 books) rising to **+1.80pp** restricted to groups with >=5 books (n=2,457, 19.3% of
  groups). Agent 6 measures **+4.35pp** on 319 settled bets against each book's last pre-kickoff
  quote. Three numbers, three panel definitions. `weekly_edge_attribution.csv` therefore carries
  **`panel_definition`** as a column and reports all three, because Agent 6's own open question is
  the right one: is the gap real execution loss, or an artifact of comparing against a quote that
  was not simultaneously live at tip time? One week of tip-time book snapshots stamped to the minute
  settles it, and that is the same collection change §G stage 2 needs.
- `variance`: the null band is mandatory. Without it, the attribution table invites reading a
  negative `model` component as a model regression when it is inside the noise.

---

## O. `WEEKLY_WOWZA_REVIEW_YYYY_WXX.md`

**Lives in:** Pro. `v10/docs/weekly/WEEKLY_WOWZA_REVIEW_2026_W37.md`, **generated** by
`v10/src/pipelines/weekly_review.py`. Not hand-written — a hand-written review is where "the model
improved" gets in.

### O.1 Fixed section order

1. **FREEZE** — `freeze.json` verbatim, including `freeze_sha`. A review whose freeze cannot be
   re-read is not evidence.
2. **DECISIONS TAKEN THIS WEEK** — first, not last. Expected content for most weeks:
   `KEEP_CHAMPION (no ticket open)`. If a promotion or rejection happened, the `GateResult`
   verbatim.
3. **SCOREBOARD DELTAS W(N-1) -> W(N)** — §Q's table. Every row carries a CI and a verdict; there is
   no free-text field for a quality claim.
4. **GATE STATUS** per `(scope, market)` — all nine checks, each PASS/FAIL with its measured value
   and the threshold it was compared against. Failing checks are named, never summarised.
5. **REJECTION LOG** — this week's entries plus season-to-date counts by `failed_checks`.
6. **COUNTERS** — every accumulation counter, its current value, its trigger, and weeks-to-trigger
   at the current accrual rate. This is the section that tells a reader what the system is waiting
   for.
7. **DRIFT** (§J) — significant features only, plus persistence counters.
8. **CALIBRATION** (§K) — reliability table plus persistence counters.
9. **MARKET LEARNING** (§L) — book scores with n; the greedy best-price panel and whether it moved.
10. **HORIZON** (§G) — the per-horizon table, INSUFFICIENT_DATA rows included.
11. **ERROR TAXONOMY** (§M) — ranked by `share_of_week_loss`.
12. **ATTRIBUTION** (§N) — with the null band.
13. **NEGATIVE RESULTS** — mandatory, never empty (§O.4).
14. **OPEN QUESTIONS** — carried forward with an owner and, for each, a mandatory **"what would
    change our mind"** line naming the measurement and its n.
15. **DO NOT BUILD** — the standing list, so each week's reader inherits the closed questions rather
    than re-opening them.

### O.2 Length discipline

The review is a data artifact with prose captions, not an essay. Every number appears exactly once
in the CSVs and is *referenced* by the review. If a number is in the review and in no CSV, it cannot
be recomputed and does not belong.

### O.3 A `KEEP_CHAMPION` week is a full-length review

The temptation is to skip the review when nothing happened. Nothing happening is the *result*, and
the counters in §O.6 are how a reader knows the engine is alive rather than stalled. **[PROVEN,
Agent 1]** v11 has silently persisted nothing since 2026-09-07 21:30 UTC — a stalled pipeline and a
correctly-quiet one look identical from the outside unless the quiet one publishes.

### O.4 Negative results are published, and the floor is a required field

`placebo_floor` — the score a **zero-information** predictor achieves on the same rows — is a
required column in the scoreboard, following Agent 10's citation of "Report the Floor"
(arXiv 2606.09473) and v11's own battery. Agent 7's corrected battery is the current state of that
evidence and it must be quoted with its correction:

**[PROVEN, Agent 7]** after fixing the `merge_asof` index bug (`v11_momentum_control.py:158`),
usable moved rows fall to 4,756 across 341 fixtures and the toward-rates are v9 **0.5257**
[.5068, .5431], league_baseline 0.5282, fixed_anchor 0.5185, shuffled_residual 0.5179,
midpoint_0.50 0.5156 — and **every paired difference CI spans zero**. The seed's headline "mean
reversion +29.2pp beats v9" collapses from 0.9960 to **0.2508**. So: the model is indistinguishable
from a constant, *and* the placebo battery that said otherwise was itself broken. Both facts go in
the review, every week, until the residual question is settled.

---

## P. `weekly_model_scoreboard.csv`

**Lives in:** Pro. `v10/output/weekly/<week>/weekly_model_scoreboard.csv` plus append-only
`data/season_2026_27/model_scoreboard/`.

### P.1 Fields

```
-- identity / freeze
research_week, freeze_sha, model_id, scope, market, version, status,
model_kind (EXTERNAL_INCUMBENT|PRO_A|PRO_A_RECAL|RESEARCH_B|RESEARCH_C|RESEARCH_D|RESEARCH_E|META_TRUST),
model_content_sha, git_sha, feature_manifest_hash, imputer_manifest_hash,
calibration_version, threshold_hash, market_calc_version,

-- window
train_start, train_end, train_rows, train_window_policy, sample_weight_policy,
holdout_start, holdout_end, holdout_rows, validation_type, odds_policy,

-- standalone (informational; cannot promote)
auc, logloss, brier, ece,

-- market-relative (decisive)
market_logloss, market_brier, blend_logloss, blend_brier,
logloss_improvement, logloss_impr_ci_lo, logloss_impr_ci_hi,
brier_improvement,  brier_impr_ci_lo,  brier_impr_ci_hi,
placebo_floor_logloss, placebo_floor_brier,
sample_label, n_hypotheses, bh_q,

-- betting evidence
real_odds_coverage, clv_n, mean_clv_pct, clv_ci_lo, clv_ci_hi, beat_close_rate,
roi, roi_ci_lo, roi_ci_hi, n_bets, monte_carlo_null_mean, monte_carlo_null_sd,

-- decision
gate_passed, failed_checks, beats_champion, ticket_id, look_number,
decision (PROMOTED|REJECTED|KEEP_CHAMPION|OBSERVED_ONLY), decision_reasons
```

### P.2 Status values, and the mapping to the registry's own vocabulary

The brief asks for `CHAMPION / CHALLENGER / RESEARCH / REJECTED`. `registry.py` already defines
`STATUSES = ("RESEARCH", "PAPER", "SHADOW", "LIVE", "BLOCKED", "RETIRED")`. Two vocabularies will
drift unless the mapping is fixed in one place:

| scoreboard `status` | registry `ModelRecord.status` | meaning |
|---|---|---|
| `CHAMPION` | `LIVE` | currently producing the production opinion |
| `CHALLENGER` | `PAPER` or `SHADOW` | has an open ticket, awaiting or facing the gate |
| `RESEARCH` | `RESEARCH` | measured, never promotable (all of B-E, §T's meta model) |
| `REJECTED` | `BLOCKED` | faced the gate and failed; retained with reasons |
| *(not shown)* | `RETIRED` | a former champion; appears in history rows only |

`src/models/challenger.py::scoreboard_status(record)` is the single implementation. The scoreboard
never invents a status.

---

## Q. Improvement must be measurable: W36 -> W37 deltas

**Lives in:** Pro. `v10/output/weekly/<week>/weekly_deltas.csv`.

### Q.1 Fields

```
research_week, prev_research_week, metric, scope, market, segment,
value_prev, value_now, delta,
delta_ci_lo, delta_ci_hi, ci_method (paired_fixture_clustered_bootstrap_5000),
n_prev, n_now, n_new_this_week, n_overlap,
verdict (IMPROVED|DEGRADED|NO_CHANGE_DETECTED|INSUFFICIENT_DATA),
bh_q, n_hypotheses
```

### Q.2 The verdict rule

```
INSUFFICIENT_DATA     if n_now < 250  or  n_new_this_week < 50
IMPROVED              if delta CI excludes zero in the good direction AND survives BH
DEGRADED              symmetric
NO_CHANGE_DETECTED    otherwise      <-- the default, and the honest answer nearly always
```

`NO_CHANGE_DETECTED` is deliberately not called "no change". The measurement failed to detect one;
that is a statement about the instrument, and at n~200/week the instrument is weak by construction.

### Q.3 Why paired and fixture-clustered

Two arms scored on the *same* fixtures are not independent samples, and multiple markets on one
fixture share an outcome. Agent 7's method — bootstrap the **difference**, resampling **fixtures** —
is the correct one and it changed conclusions: the same data that gave "mean reversion +29.2pp" gave
"every paired difference CI spans zero" once done properly.

### Q.4 The banned sentence

The template has **no field** for a free-text quality claim. "The model improved" is
unrepresentable in `weekly_deltas.csv`; the only expressible statements are a signed delta with a CI
and one of four verdicts. That is the enforcement — not a style guide.

---

## R. No weekly overfitting: separating OBSERVATION from MODEL UPDATE

**This section matters more than any other, and it is enforced structurally rather than by
discipline.**

### R.1 Two workflows, two permission sets

```
pro_weekly_freeze.yml   cron 0 5 * * 1        -> output/weekly/<week>/freeze.json
                                                 data/season_2026_27/research_weeks/
pro_weekly_learn.yml    cron 0 6 * * 1        -> output/weekly/<week>/*.csv
                                                 docs/weekly/WEEKLY_WOWZA_REVIEW_*.md
                                                 data/season_2026_27/{model_scoreboard,
                                                   feature_drift,book_info,gate_decisions}/
pro_promote.yml         workflow_dispatch ONLY -> registry/registry.json
```

The observation workflow **cannot** write a parameter, for three independent reasons:

1. `src/pipelines/weekly_learn.py` imports no writer for any parameter path. It has no
   `Registry(...).promote` call, no `best_params*.json` writer, no `.pkl` writer.
2. An exit assertion: `assert_no_param_writes(PARAM_PATHS)` compares the mtimes of
   `registry/registry.json`, `registry/refs/*`, `config/pro_config.py`, every `models/*.pkl` and
   every `best_params*.json` before and after the run. Any change is a hard failure.
3. The workflow stages an **explicit file list**. Never `git add -A`. **[PROVEN, root CLAUDE.md and
   Agent 1]** `git add -A` in `v10/` would swallow the entire untracked legacy v9 copy, and five Pro
   workflows already use `git add -A data`.

`pro_promote.yml` has no `schedule:` trigger at all. A promotion cannot happen because a week ended.

### R.2 The challenge ticket: nothing may be built or promoted without one

`v10/registry/tickets/<ticket_id>.json`, written **by a trigger**, never by a human noticing a bad
week. Appended to `docs/PREREGISTERED_HYPOTHESES.md`, which already mandates that cut points be
literals read from the file rather than recomputed on the new sample.

```json
{
  "ticket_id": "T-2026-W41-RECAL-STD-OU25",
  "opened_at": "2026-10-12T06:03:00Z",
  "trigger_id": "calibration_persistence",
  "trigger_rule_text": "|residual_pp| > 5pp, same direction, >=4 consecutive weeks, segment n>=500",
  "counter_values_at_fire": {"weeks": 4, "residual_pp": [8.9, 9.4, 7.7, 8.1], "n": [612, 588, 701, 655]},
  "authorised_freeze": "2026-W41",
  "hypothesis": "Per-league-shrunk Platt on the CALIBRATION block reduces final-holdout ECE below 0.05 without degrading market-relative logloss.",
  "primary_metric": "ece on final holdout",
  "decision_threshold": "ece <= 0.05 AND logloss_improvement not worse than champion's",
  "falsification": "ece > 0.05 on final holdout, OR logloss_improvement degrades by more than its CI width",
  "look_budget": 3,
  "looks_used": 0,
  "scope": "standard",
  "market": "OU25",
  "forbidden": ["any MARKET-category feature", "any threshold change", "any v9 edit"]
}
```

A gate evaluation with no valid ticket, or with a ticket whose `authorised_freeze` is not the current
freeze, or with `looks_used >= look_budget`, is **refused before the gate runs**.

### R.3 The evidence-accumulation triggers, with the measured arithmetic

Every trigger is stated with the accrual rate I measured, so weeks-to-fire is a fact and not a hope.

| trigger | condition | authorises | weeks to fire at measured rate |
|---|---|---|---|
| `new_labelled_outcomes` | >= 1,000 labelled outcomes since champion's `train_end` | a REFIT challenger (same features, more data) | **~5** at ~200/wk |
| `clv_evidence_ready` | >= 150 clean §A closes in a segment | the gate to be *evaluated* at all | **1-3** at 170-220/wk (§0) |
| `calibration_persistence` | >= 4 consecutive weeks abs(residual_pp) > 5pp, same direction, segment n >= 500 | a RECALIBRATION challenger | **~4** — likely first to fire |
| `drift_persistence` | >= 3 consecutive weeks PSI > 0.25 on a *required deployed* feature | a FEATURE/IMPUTER challenger | data-dependent |
| `new_settled_bets_segment` | >= 1,000 settled bets in a league x market x tier | a THRESHOLD challenger in that segment | **not this season** (below) |
| `degradation_persistence` | >= 4 consecutive weeks of negative market-relative logloss delta | a **BLOCK review**, not a retune | — |
| `horizon_evidence_ready` | >= 250 fixtures with a close in a near band | §G stage 2 | after the near-kickoff worker |

**[PROVEN] `new_settled_bets_segment` cannot fire this season.** Measured settled bets: ~150/week
pooled across both tracks and all tiers (new_format 92-110, standard 48-56, W35-W36). A single
league x market x tier cell gets a handful. Agent 12's power calculation makes it worse: with
sd(pnl per flat 1u) = **1.126** at n=416, detecting a true +5% ROI at 80% power needs **n=3,975**
(11,043 for +3%) — and standard SNIPER, the only real-money tier, arrives at **5.7/month**, i.e.
**58 years**. Writing that number into the trigger table is the point: the design does not
*discourage* weekly threshold tuning, it makes the counter that would authorise it publicly
unreachable.

### R.4 Confidence sequences, so looking every week is legitimate

Fixed-n p-values recomputed weekly are the wrong instrument for a continuously accumulating ledger.
**[Agent 10, external]** Waudby-Smith & Ramdas (arXiv 2010.09686) give time-uniform confidence
sequences for the mean of a **bounded** random variable via betting martingales; per-bet returns are
bounded, so it applies directly to ROI and CLV. Shekhar & Ramdas (arXiv 2310.01547) show the width
penalty is near-optimal, i.e. anytime-validity is nearly free.

**Lives in:** Pro. `v10/src/validation/anytime.py` (new, ~120 lines). Every counter's associated
metric is tracked as a confidence sequence, and the promotion condition becomes "**the lower bound
has cleared zero**" rather than "n has reached 150 and the point estimate is positive". This is a
strict improvement on `min_clv_n=150` and it does **not** require editing `evaluate_gate` — the
sequence is computed by the feeder, and `mean_clv_pct` / `clv_n` are populated only once the
sequence's lower bound clears, so the gate's own check becomes the last of two hurdles rather than
the only one.

### R.5 A hard look budget

Each hypothesis gets a fixed number of decision looks per season, written into its ticket and
decremented in the rejection log (`look_number`, `look_budget_remaining`). Exhausted budget -> the
hypothesis is **closed as INSUFFICIENT_DATA for the season**, not re-opened under a new name. This
is the multiplicity control that `evaluate_gate` does not contain, placed where it belongs.

### R.6 Two live landmines this section must disarm

- **[PROVEN, Agent 7]** `v9/scripts/fix_ledger_tiers.py:69-70` sets
  `new_tier = "SNIPER" if rederived == "SNIPER" else "MARKSMAN"` for any row keyed in
  `telegram_bot/notified.json`, **regardless of edge**, deliberately leaving `edge_pct` stale. It
  already rewrote 42 live rows (27 VALUABLE->MARKSMAN, 15 VALUABLE->SNIPER) with only 15 edge
  changes. Re-running it **redefines the staked population by selecting on having been notified**.
  This script must never run again, and the weekly engine must never invoke it.
- **[PROVEN, Agents 2 and 3]** `pipeline.py:444-446` writes `models/best_params_standard.json` from
  `optimize_standard_thresholds` and `betting.py:132-137` reads it **in production**, with the
  monthly backtest committing it as "auto: parallel backtest". An automatic, unversioned,
  in-sample-maximum write into the live money path is the single clearest invariant-6 violation in
  the estate. The engine cannot fix it (v9 is frozen), but the freeze records its hash every week
  (§A.4) so its movements become visible, and Pro's own thresholds are never written by any
  scheduled job.

### R.7 The success criterion, stated so nobody misreads it

A season that ends with **zero promotions, a populated rejection log, and every counter's
weeks-to-fire published every week** is a season in which the engine worked. The failure mode is not
"we never promoted anything". It is "we promoted something and cannot say why".

---

## S. Experience replay and sample weighting

### S.1 What is currently true

**[PROVEN, Agent 3]** There is no recency weighting in production, twice over: all 10
`TRAINING_DECAY_WEIGHTS` keys are `'YYYY/YY'` against a season column of `'YYYY'`, so distinct
assigned weights = `{1.0}`; and `retrain.py:371` passes no `sample_weight` at all. Also
`COVID_SEASONS` matches **0 of 37,623 rows**, leaving 7,112 COVID-era rows (18.9%) in training while
`pipeline.py` logs "Excluded COVID seasons: 0 rows removed".

So "should we weight by recency" has never actually been asked. It is an arm of §C's experiment, not
an assumption.

### S.2 The design

Candidate weighting policies (an arm of §C, chosen on block k, evaluated on k+1):

```
FLAT                    w = 1
EXPONENTIAL_HALFLIFE    w = 0.5 ** (age_weeks / H),  H in {26, 52, 104}
SEASON_STEP             w = {current: 1.0, -1: 0.7, -2: 0.5, -3: 0.3, older: 0.1}
ROLLING_WINDOW          w = 1 inside last 104 weeks, 0 outside
REPLAY_BUFFER           recent rows at w=1 + a stratified reservoir of older rows (S.3)
```

### S.3 The replay buffer, and why plain recency is dangerous here

Plain recency forgets **leagues**, not just time. **[PROVEN, Agent 3]** `fd_history.parquet` holds
22 leagues and **10 of 17** `STANDARD_FORMAT_LEAGUES` have zero CI training rows — including
**Ligue 2, which is a bet league** and appears in the live ledger. A rolling window makes thin
leagues thinner.

`REPLAY_BUFFER`: keep all rows from the last 52 weeks at w=1, plus a **stratified reservoir** of
older rows sampled to a fixed quota per `(league, season, outcome)` cell — so a league with few
recent matches keeps its historical rows and does not vanish from the fit. Reservoir size and quotas
are hyperparameters of the §C experiment, not tuned weekly.

### S.4 The catastrophic-forgetting guard

A global gain bought by forgetting a bet league is refused. Concretely, a hard promotion
pre-condition in the challenger feeder (not in `evaluate_gate`, which stays untouched):

```
For every league in ENABLED_LEAGUES with holdout n >= 250:
    challenger logloss must not exceed champion logloss by more than the CI width of the delta.
Any violation -> the challenger is REJECTED with failed_check "forgetting_guard",
and the violating leagues are named in the rejection log.
```

Leagues with n < 250 are reported as `INSUFFICIENT_DATA` and cannot block a promotion — otherwise
the guard becomes unpassable, which is its own failure mode. Agent 3's related warning belongs in
the same file: `feature_engineering.py:126` groups rolling form by `team` only, so a relegated club
carries Championship goal rates into League One, and **24.0%** of standard team-rows belong to
multi-division clubs. Regime change is currently unmodelled *and* unweighted; the replay design
should not pretend otherwise.

---

## T. Meta-learning: "when should I trust myself over the market?"

**Prototype only. `scope` suffix `:research`, `status="RESEARCH"`, never a stake multiplier.**

### T.1 Target and features

```
y_meta = 1 if the model's per-row log-loss contribution was LOWER than the market's on that row
         (i.e. -log p_model(outcome) < -log p_market_close(outcome))
       = 0 otherwise
output: p_trust
```

Feature allowlist, enforced by `feature_registry` **category**, not by inspection: `FOOTBALL`,
`MICROSTRUCTURE`, `QUALITY` only. Permitted: `book_count`, `panel_dispersion`,
`minutes_to_kickoff` at decision, PSI severity of the row's own features, `n_missing_features`,
`no_form_data`, `thin_form`, league, `odds_band`, season stage, rest days, and `MCS` **only if §F
passed**. Forbidden: anything observed after the lock, and `p_market_close` itself.

### T.2 The leakage trap, named

`y_meta` is defined **using the outcome**. Any post-kickoff information in the features makes the
model self-fulfilling and it will look spectacular. This is the single reason it must be
prototype-only and category-enforced: the failure mode is a beautiful AUC that means nothing.
Validation is the same four chronological blocks, the same final-holdout guard, and the same gate as
any other model.

### T.3 Why this may be worth more than raw probability improvement

Raw improvement must beat the market **everywhere** to be usable, and the measured everywhere answer
is zero: v11's controlled residual coefficient is **+0.0002, p=0.90**; Agent 11 shows the
uncontrolled +1.2306 [1.145, 1.320] collapsing ~1,300x to +0.00089 [-0.00051, +0.00235] once the
price's own velocity is controlled; Agent 3's bootstrap residual delta-logloss on n=12,187 is
-0.00005, CI [-0.00063, +0.00045], sign-flipping across all three chronological folds.

A trust model needs only to find a **subset** where the model is better. That is a strictly easier
question and a monetisable one: it converts a globally-null residual into a conditionally-positive
one **if such a subset exists**. Agent 10's external anchor makes the point sharply — Clegg, Song &
Cartlidge (arXiv 2605.16066) report a model **less** accurate than Betfair (70.2% vs 70.6%) earning
4.5% ROI over 17,458 in-play bets, while our props model is *more* accurate than its market and
unprofitable. Accuracy is orthogonal to edge; **conditional** accuracy is not.

### T.4 And its failure is the most valuable result in the design

If `p_trust` is uninformative (AUC ~ 0.5 on the final holdout, CI spanning 0.5), then the null is
**homogeneous**: the model has no pocket anywhere, in any league, at any horizon, at any panel
depth. That is the strongest available argument to stop spending on the model at all — and it is
much cheaper to establish than a season of per-segment searching, because it asks the question once
instead of 200 times.

Either outcome is a decision. That is what makes it worth prototyping despite the leakage risk.

---

## U. Ownership, schedules, and build order

### U.1 Ownership — respecting the existing split

| repo | role in this engine | changes |
|---|---|---|
| **v9** | **data source only, read over HTTP** via `v10/src/data/v9_source.py`. Keeps producing `predictions.csv`, `bets_ledger.csv`, `book_odds_snapshots.csv`, `odds_history_v9.json`. | **NONE.** Invariant 3. The engine is designed to work with v9 exactly as it is — every v9 defect in this document is *measured and compensated for in Pro*, not fixed in v9. |
| **Pro (v10)** | the entire engine | all new code and workflows below |
| **v11** | the scientific judge: placebo battery, residual test, `placebo_floor` | two **bug fixes** required (U.3) before its output may enter a freeze |

**Two permissible v9 bug fixes**, both explicitly bug fixes and neither required by this design: the
missing kickoff filter at `update_results.py:329` / `_closing_for_market`, and the date-blind name
fallback at `update_results.py:318-327`. Both fall under invariant 3's bug-fix exception. The engine
does not wait for them — it builds its own close from `book_odds_snapshots` (§A), which is why it
can ship against a frozen v9.

### U.2 New Pro modules

```
src/pipelines/weekly_freeze.py       A       freeze, read_frozen, effective_thresholds
src/pipelines/weekly_learn.py        B J K M N   the observation run (writes no parameter)
src/pipelines/weekly_review.py       O       generates the .md
src/pipelines/threshold_curves.py    H       research only
src/pipelines/cadence_experiment.py  C S     one-off, workflow_dispatch
src/models/register_incumbent.py     D.2     writes the first ModelRecords + train_ref
src/models/challenger.py             D E R   submit(), scoreboard_status(), firewall guards
src/market/confirmation.py           F       MARKET_CONFIRMATION_SCORE
src/market/horizon.py                G       per-horizon panel + metrics
src/market/book_info.py              L       bookmaker_information_score + greedy panel
src/validation/anytime.py            R.4     confidence sequences
src/monitoring/counters.py           R.3     the accumulation counters
src/models/meta_trust.py             T       prototype
```

Reused **unchanged**: `src/models/registry.py`, `src/monitoring/drift.py`,
`src/validation/{splits,market_relative,multiple_testing}.py`, `src/models/calibration.py`,
`src/market/{devig,consensus,curve,best_price,clv_schema}.py`, `src/data/season_store.py`,
`src/feature_registry.py`, `src/pipelines/experiment.py`.

### U.3 v11's two blocking bug fixes

1. **`scripts/v11_momentum_control.py:158`** (and `:141`) — `pd.merge_asof` returns a fresh
   RangeIndex, so `out.sort_index()["p_at"]` assigns movement values to the wrong rows. Every
   momentum/movement/placebo number is void until fixed (§O.4).
2. **Staging** — `output/v11_placebo_table.csv` (written at `:643`) and
   `output/v11_chronological_folds.csv` (`:647`) are **not** in `v11_collect.yml`'s 18-path staging
   list, so the audit's central result is computed 16x/day and destroyed. Also
   `output/v11_market_movement.csv` is still tracked at its 2026-08-23 state — a dead filename the
   rewritten script no longer produces, reading as current. And the v11 push epilogue lacks
   `-X theirs`, so one conflict leaves the rebase in progress and all five retries fail — which is
   the signature of its ~58-hour silence.

### U.4 Schedule

| workflow | cron (UTC) | job |
|---|---|---|
| `pro_weekly_freeze.yml` | `0 5 * * 1` | §A freeze; hard-fails on any leakage assertion |
| `pro_weekly_learn.yml` | `0 6 * * 1` | §B G J K L M N P Q, then §O review; **no parameter writes** |
| `pro_promote.yml` | **`workflow_dispatch` only** | §D gate; refuses without a valid current-freeze ticket |
| `pro_cadence_experiment.yml` | **`workflow_dispatch` only** | §C S, once |
| `pro_near_kickoff_worker` | continuous (external worker, Pro-owned) | §G stage 2 instrumentation |
| `pro_weekly_audit.yml` | `15 6 * * 1` (**existing**) | keep — it catches green-workflow-no-data, this estate's only historical failure mode |

Offsets: the 05:00 freeze sits after `pro_backfill_results.yml` (`25 */6 * * *`, i.e. 00:25 and
06:25), so it consumes the 00:25 run's results — which is why `outcome_cutoff_ts` is Sunday 21:00Z
with 7 hours of settlement margin. Learn at 06:00 gives the freeze an hour.

**Delivery caution.** **[SUPPORTED, Agent 1 / seed]** workflows requesting >=26 runs/day receive
8-38% of them; <=8/day receive ~100%. These are 1/week each, deep in the reliable band. Do **not**
add cadence to them, and do **not** clone an existing workflow's push epilogue — it is already
duplicated ~30 times in three divergent conflict policies across the three repos (21 v9 files with
`-X theirs` plus a pushed flag; 8 v10 files and 1 v11 file without). Extract a composite action
first.

### U.5 Build order (each step independently useful)

| # | step | hours | why in this position |
|---|---|---|---|
| 1 | §A `weekly_freeze.py` + `read_frozen` (with dedup) | 8 | nothing else is reproducible without it; also fixes the 23x settlements inflation at the read boundary |
| 2 | §A the **close**: LOCF panel -> de-vigged consensus at lock | 6 | unblocks CLV, the gate, §G, §L, §N. The single highest-leverage six hours in this document (§0) |
| 3 | §D.2 `register_incumbent.py` | 4 | the gate is meaningless with an empty registry; produces the first honest baseline numbers |
| 4 | v11's two bug fixes (U.3) | 2 | `placebo_floor` is a required scoreboard field and is currently void |
| 5 | §B + §P + §Q + §O — the observation run end to end | 16 | first real review; establishes the counters |
| 6 | §K calibration + §J drift with `train_ref` | 10 | the trigger most likely to fire, and the cheapest legitimate improvement |
| 7 | §R counters, tickets, look budgets, `anytime.py` | 12 | must exist **before** any challenger, or the first challenger sets the precedent |
| 8 | §N attribution (three panel definitions) | 8 | quantifies the +1.4 to +2.7pp execution question, which is where the money actually is |
| 9 | §L book_info + greedy panel | 8 | decides the account roster |
| 10 | §G stage 1 horizons | 6 | answers the far end now; documents the near end as INSUFFICIENT_DATA with n |
| 11 | §E models A-E with the firewall | 20 | the go/no-go on the whole modelling programme, delta(C, E) |
| 12 | §C cadence experiment | 12 | one-off; retires the "retrain weekly" assumption |
| 13 | §F MCS | 10 | after U.3, and veto-only |
| 14 | §H threshold curves (research only) | 10 | expected output: INSUFFICIENT_DATA, said with a number |
| 15 | §T meta_trust prototype | 12 | either finds a pocket or closes the programme |
| — | §I adaptive thresholds | — | **BLOCKED** on §H and §G |

Steps 1-7 (~58 hours) are the engine. Everything after is a consumer of it.

---

## V. Do not build

- **A new promotion gate.** `evaluate_gate()` exists, is correct, is tested, and its nine checks are
  the right nine. The missing work is registration and a feeder, not a gate.
- **Any threshold re-tune on current samples.** Spearman(edge, pnl) = -0.005 to +0.026 across three
  independent measurements (n=184, 416, 788); the >=14% bucket is -10.2% ROI; no league CI excludes
  zero, 17 of 17. Also invariant 6.
- **The drift-floor fix as an improvement.** It targets the *better* half in both tracks (-13.4% vs
  -49.9%; -28.7% vs -35.8%; +6.5% vs -4.6%) at n=19-25. Record the promotion path; do not change it.
- **A better pre-match estimator, or new football features.** Residual CI spans zero at n=12,187;
  the market closing price beats the model on the model's own metric and n; arXiv 2608.11505 fitted a
  pooling weight of 0.000; local Understat-xG and weather nulls are instances of the same regularity.
  Wiring the 23 dropped features in is the same mistake with extra steps.
- **Blending market probability into `p_model`,** or retraining on odds. Collapses the residual by
  construction (brief §3). Note it is *partly already true* — `AvgC>2.5` is the first entry in
  `_OVER_COLS` — which is why model A must be built fresh.
- **De-vig refinement, consensus-estimator variants, or a de-vig project.** The whole question is
  worth 0.00024 Brier (n=291). Power is already correct and near-optimal for a symmetric two-way
  market.
- **More bookmaker accounts beyond five.** Four books recover 99.36% of the best OU25 price; five
  reach 99.56%; beyond that < 0.4%.
- **A bigger OddsAPI plan for prop coverage, or more API-Football credits.** Props calls came back
  *empty*, not rate-limited; API-Football sits at ~15.0% of 75,000/day. Buy nothing to fix coverage.
- **Historical odds backfill from API-Football.** Settled 2026-08-19 for ~830 calls, pre-match only.
  *Do* record Agent 10's correction: The Odds API **does** sell 5-minute historical snapshots back to
  2020-06-06 on all plans, so the CLAUDE.md generalisation "no history is buyable at any price" is
  false in general and true for API-Football. Keep the two justifications separate.
- **Any player-props path.** Invariant 2, not revisited.
- **A dashboard for anything in this document before its CSV exists.** `output/ht_ledger.csv` is read
  by two dashboard pages and **has never existed**.
- **Re-running `v9/scripts/fix_ledger_tiers.py`.** It promotes rows to MARKSMAN off a Telegram log
  regardless of edge and would redefine the staked population by selection on notification.
- **Cloning a workflow's push epilogue.** Extract a composite action first.

---

## W. Open questions this design cannot close

1. **Does the §A close, built correctly, show any CLV at all?** Agent 11's cleaned figure is
   +0.222% on n=372 with a CI admitting +1.0%; Agent 12's is -0.031% on n=405; Agent 1's is +0.162%
   CI [-0.68, +1.00] on n=381. Against a measured 6.96% overround, +1.0% would be material. This is
   the cheapest decisive test in the estate and step 2 of the build order produces it.
2. **Is the price-shopping uplift +0.72, +2.03, or +4.35pp?** Three panel definitions, three
   numbers. Settled by one week of tip-time book snapshots stamped to the minute — the same
   collection change §G stage 2 needs. It decides whether the largest measured finding in the whole
   audit round is bankable.
3. **Can we actually bet Matchbook or Pinnacle at size from this jurisdiction, and at what
   commission?** +2.6pp of pure margin reduction, zero model risk, and no dataset here can answer
   it. Agent 10 is right that this business question dominates a season of modelling work and nobody
   has asked it.
4. **Was `LEAGUE_SNIPER_CAP=0.12` / `MARKSMAN=0.08` / `VALUABLE=0.03` a deliberate volume decision
   for a data-gathering season, or drift?** The answer decides whether §A.4 is a bug fix or a
   documentation fix, and whether `config.py`'s per-league ROI comments should be struck. The commit
   message is the missing document.
5. **Is the standard model's compressed output (`p_over25` sd 0.023-0.040 live) a transient or the
   steady state?** Thirty days of committed `predictions.csv` recovered from git history settles it,
   ~1 hour, and it decides whether model A is worth building at all.
6. **Split all 416 settled bets by `no_form_data` before 2026-09-15.** The guard was disabled for
   the entire measurement window (`predict.yml:188`) and self-re-arms on the 15th, after which the
   population changes and the comparison is gone. Free, and it is the strongest live alternative
   explanation for the shortfall.
7. **Does delta(C, E) exclude zero?** §E's go/no-go. Until it is measured, every hour spent on model
   A is spent against an unquantified ceiling — including the hours this design allocates to it.

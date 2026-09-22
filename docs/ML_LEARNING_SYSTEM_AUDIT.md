# ML Learning System Audit — 2026-09-22

Scope: `NevixAA/wowza-betting` (v9), `NevixAA/wowzaV9-Pro`, `NevixAA/wowza_v11`.
Method: every claim below is derived from committed artifacts, git history and code actually
executed by CI. Where something could not be established from here it says so.

---

## A. Executive summary

**The ML system is not learning, and — in the production path — it never has.**

Not "learning badly", not "learning slowly". The chain
*challenger → untouched chronological validation → incumbent comparison → recorded decision*
has never executed in v9's production retraining path, not once, in the repository's history.

The reason is structural rather than a bug. `retrain.yml` runs `python pipeline.py --mode train`.
That entry point calls `mode_train()`, which calls `_train_one()`, which called `train_model()`
and then `save_models()` — unconditionally. `mode_train` runs **no backtest at all** (backtests
live in a separate monthly workflow), so at the moment the live model was overwritten there was
nothing to compare it to. Every retrain replaced the incumbent with whatever had just been
fitted, and no decision was recorded because no decision was ever made.

The file that *does* contain comparison logic — `retrain.py`, with `_print_comparison` — has
**never been executed by any workflow**. Checked across the whole history of `retrain.yml`: it
has only ever run `pipeline.py --mode train` (and briefly `--mode backtest` in June).

On top of that, three independent collection/training failures were running silently:

| what | frozen since | days | detected by |
|---|---|---|---|
| all seven model artifacts | 2026-08-30 | 23 | this audit |
| `player_history.parquet` (props training data) | 2026-08-17 | 36 | this audit |
| `fd_history.parquet` cache (0 rows ever served) | 2026-09-05 | 17 | this audit |

Each ran daily, committed daily, and reported success daily.

**Inference was healthy throughout.** Tips went out every day, the dashboard updated, ledgers
grew, Telegram fired. That is precisely the trap: a 23-day-old model predicts confidently every
single day, and nothing in the estate's monitoring could tell the difference.

Everything in §D has been fixed and pushed. The loop has not yet completed a full cycle, so the
honest verdict remains **not yet proven** — the first genuine learning event will be the next
successful retrain, and §M describes how it will now announce itself.

---

## B. Current architecture — the real path

```
fixture (OddsAPI / API-Football)
  └─ predict.py                  every ~5 min, v9            → output/predictions.csv, bets.csv
market snapshot
  └─ capture_*_odds_forward.py   8×/day                      → odds history, book_odds
match result
  └─ update_results.py           every 2h                    → bets_ledger, side_bets_ledger
settlement
  └─ Pro importers               pro_collect 40 */2          → data/season_*/settlements/
canonical historical row
  └─ football-data.co.uk + fd_history.parquet cache          → training frame
feature generation
  └─ src/feature_engineering.build_features                  → rolling form, strengths
training dataset
  └─ pipeline.mode_train → load_all_matches → build_features
chronological split
  └─ INSIDE train_model (train/cal/test), never a random split
challenger training
  └─ _train_one → train_model
OOS evaluation           ← ADDED 2026-09-22. Did not exist.
incumbent comparison     ← ADDED 2026-09-22. Did not exist.
promotion / rejection    ← ADDED 2026-09-22. Did not exist.
model artifact
  └─ models/model_v9_*.pkl + metrics_model_v9_*.json
future inference
  └─ predict.py loads the .pkl
```

The gap was the three middle-lower rows. Everything above them worked.

---

## C. Last genuine learning event

**NONE.**

Evidence, all independently checkable:

* `retrain.yml` has only ever run `pipeline.py --mode train`. `retrain.py` — the only file
  containing incumbent-comparison logic — is not referenced by any workflow.
* `mode_train()`'s call graph is `{_train_one, load_all_matches}`; `_train_one`'s is
  `{train_model, save_models, load_models}`. No backtest, no evaluation, no comparison.
* `pipeline.py` contains zero references to `backtest_metrics_history.json` or `_save_metrics`.
* `output/backtest_metrics_history.json` — the only historical record of a train-vs-previous
  comparison — has **two commits in the repository's entire history**, the initial import and
  one on 2026-06-17. Neither came from a retrain workflow.
* `output/retrain_log.json` did not exist before 2026-09-22.

So the answer to "when did V9 last genuinely learn" is not a date. The mechanism was absent.

**Closest thing to a learning event:** 2026-08-30, when the model artifacts last changed. But
that was an unconditional overwrite with no validation and no recorded decision, which is
training, not learning.

---

## D. Failures found

### D1 — No promotion gate in the executed path — CRITICAL

* **Root cause:** `_train_one` called `save_models()` immediately after `train_model()`;
  `mode_train` runs no backtest.
* **Affected period:** the whole history of the workflow.
* **Scientific impact:** total. No challenger was ever tested; a degraded model shipped as
  readily as an improved one, and neither outcome was recorded.
* **Production impact:** the live model could silently get worse. Undetectable after the fact.
* **Fix:** `_train_one` now reads the incumbent's held-out metrics from
  `models/metrics_<stem>.json`, trains the candidate, compares **mean held-out log loss**, and
  saves only if it has not risen beyond `TRAIN_MAX_LOGLOSS_RISE` (default 0.005). Per model,
  independently. `train_model` already produces a chronological train/cal/test split, so the
  comparison costs nothing extra.
* **Verification:** decision table exercised across six states (no incumbent / improved / flat /
  small rise / large rise / broken candidate). `_mean_logloss` verified against the real
  committed `metrics_model_v9_standard.json` → 0.69013.

### D2 — Retraining dead since 2026-08-30 — CRITICAL

* **Root cause:** on 2026-09-06 `WOWZA_FULL_ENRICH: '1'` was added to `retrain.yml`, expanding
  API-Football enrichment from 15 new-format leagues to **46**. `retrain.yml` had **no
  `actions/cache` step**, so every run refetched all of it cold against a 120-minute cap.
* **Aggravating factor:** this is the same incident CLAUDE.md already documents from
  2026-08-15 in `predict.yml`, including the sentence "Re-enabling requires caching
  `api_football_cache/` first." `predict.yml` got its cache on 2026-09-06. `retrain.yml` got
  the enrichment switch the same day and not the cache.
* **Fix:** `actions/cache` on `api_football_cache` + `apifootball_ou_cache`, same key strategy
  as `predict.yml`; `timeout-minutes` 120 → 240 so the first cold run can complete and populate
  the cache rather than being killed and leaving it empty — the FPL-sidecar deadlock shape.

### D3 — Player history frozen 35 days — CRITICAL

* **Root cause:** the collect gate computed its cooldown from
  `git log -1 --format=%cI -- player_history.parquet`. `actions/checkout@v4` defaults to
  `fetch-depth: 1`; in a shallow clone that returns HEAD's own timestamp, always minutes old.
  `hours >= 20` was therefore never true.
* **Evidence:** `history_extend_health.json` records `"hours_since_commit": "2.1"` every day,
  while the real gap between commits touching that file is **168 hours**.
* **Timing:** gate introduced 2026-08-18; newest match in the parquet 2026-08-17.
* **Class:** the **fourth** instance of "a freshness signal the CI checkout destroys"
  (`provenance._model_sha`, `fpl_api._cached_fetch`, `registry.age_hours`). mtime was the old
  vector; a shallow `git log` is a new one with identical shape.
* **Fix:** cooldown now reads `last_collect_at` from the committed
  `output/history_extend_health.json`. Absent stamp = infinitely old (collect). The stamp
  advances only when a collect actually ran and is carried forward otherwise.
* **Verification:** five states simulated; today's real state now returns collect = **True**.

### D4 — `fd_history.parquet` cache: 37,623 rows, 0 ever served — HIGH

* **Root cause, two halves of one thing — `season` has no single convention.** The downloader
  probes `(league, "2024/25")`; the cache stores standard leagues under a calendar **year**
  (`'2023'..'2026'`) because they were seeded from the new-format path, where a year is correct.
  The probe could never hit. And concatenating the two conventions produced an object column of
  mixed `int`/`str`, so `to_parquet` threw and the cache could never be updated — the exception
  was swallowed into a warning.
* **Fix:** key the have-set on the stored season **and** a label derived from the match date
  (a standard season runs Aug–May, so it is recoverable); cast the key columns to `str` before
  writing.
* **Verification:** have-set 138 → 289 keys; 21 of 30 finished-season requests now served from
  cache instead of 0. **All 10 live-season requests still download fresh** — the current season
  is never cached, by design.

### D5 — Side-market thresholds fitted and judged on the same rows — HIGH

* **Root cause:** `optimize_side_market_thresholds` was a pure in-sample grid search. The
  standard optimizer had a walk-forward pass; this one had none.
* **Fix:** the same walk-forward, producing `roi_oos` / `bets_oos` / `approved`.
* **Measured:** in-sample figures are inflated 3–5×, and four of fourteen cells invert —
  BTTS League Two +17.6% → **−3.1%**, Over 1.5 Ligue 2 +7.3% → **−7.8%**.
* **No league is silenced.** Unapproved leagues tip at the global bar and keep collecting.

### D6 — `over15` certified on synthetic prices — HIGH (fixed earlier the same day)

100% of over15 backtest rows carried the constant 1.40 fallback; 2,122 of 2,122 "placed" tips
sat on it. Rows lacking a real price are now tagged `price_synthetic`, tiered `NO_PRICE` and
excluded from bets and ROI. Replayed: over15 placed tips 2,122 → 1; **BTTS unchanged at 925**,
because all its placed tips had real forward-captured prices.

### D7 — v11 movement study frozen four weeks — MEDIUM (fixed earlier the same day)

Snapshot cadence fell from a 33-minute gap to 170–246 minutes; `_asof`'s 35-minute tolerance
could never match, so every movement column went all-NaN from 2026-08-31 and the placebo table
recomputed byte-identical output daily. Window is now chosen from measured cadence, a zero-row
run exits non-zero, and every output row is stamped with the window used.

---

## E. Training-data freshness

| model | training input | newest match | age | new settled fixtures unseen |
|---|---|---|---:|---:|
| standard | `fd_history.parquet` + live download | 2026-09-05 (cache) | 17d | 155 |
| new_format | same | 2026-09-05 (cache) | 17d | 237 |
| btts / over15 / over35 / ht | same | 2026-09-05 (cache) | 17d | 392 |
| **props** | `player_history.parquet` | **2026-08-17** | **36d** | 0 collected |

**Caveat, stated because the number overstates the problem:** `fd_history.parquet` is a *cache*
that CI supplements with a live download of the current season at runtime. The 17-day figure is
the cache's staleness (D4), not proof that training saw nothing newer. The props figure has no
such caveat — 36 days with zero rows collected is the real number.

---

## F. Retraining history

| date | outcome |
|---|---|
| 2026-08-02 … 2026-08-30 | weekly, succeeded, **no comparison, no decision recorded** |
| 2026-09-06 / 09-13 / 09-20 | did not complete (D2) |
| 2026-09-22 | manual run in progress at time of writing |

`backtest_metrics_history.json`: 2 commits ever, last 2026-06-17.

---

## G. Incumbent vs challenger

No challenger has ever existed as a distinct artifact. Current incumbents, all dated
2026-08-30, with their recorded held-out metrics (mean log loss across base models):

| model | mean held-out log loss |
|---|---:|
| standard | 0.69013 |
| new_format | 0.67440 |
| btts | 0.68742 |
| over15 | 0.55078 |

These are now the baseline the gate compares against.

---

## H. Leakage audit

* Chronological splits confirmed: `train_model` uses train/cal/test by time, never random.
  `optimize_standard_thresholds` and (now) `optimize_side_market_thresholds` walk forward by
  season.
* Calibration study fits every calibrator on an earlier slice and scores on a later unseen one.
* Threshold study chooses on the earlier 60% and reports the later 40%.
* **Remaining risk, not yet resolved:** the inference-time median-imputation question from §20
  (whether preprocessing medians are computed from the prediction batch rather than from
  training) was **not** re-verified in this pass. It is called out in `CLAUDE.md` invariant 8 as
  having produced a confident-looking edge on a fixture with no history. Treated as open.

---

## I. Feature freshness

**Not demonstrated, and deliberately not claimed.** The prompt asks for proof that a recent
match changes a team's rolling inputs. That requires building features before and after a
settlement, which needs the training frame CI builds at runtime. It was not run here, so no
claim is made either way. This is the most important remaining gap and is listed in §N.

---

## J. Player props learning

Collection frozen 36 days (D3, fixed). Predictions continued the whole time on stale history —
`props_health.json` recorded `"stale": true` every morning and nothing acted on it.

**sklearn version skew (§11) — not investigated.** The reported 1.9.0 → 1.9.1 mismatch was not
examined in this pass. Not retrained, not upgraded, nothing pinned. Open.

---

## K. Side-market learning

Real-price-only certification enforced (D6). OOS threshold validation added (D5). BTTS retains
its certification because it was always priced from genuinely captured odds; over15/over35 do
not inherit credibility from synthetic pricing.

---

## L. Learning curve

**Cannot be produced.** It requires a history of (model version → validation metrics), and that
history does not exist: `backtest_metrics_history.json` has two entries, the last from June.
`output/retrain_log.json` now accumulates exactly these fields, so the curve becomes available
from the first successful retrain onward. §17's more-data-helps experiment is not attempted
here — it should run on the record once there is one.

---

## M. Monitoring added

* `output/retrain_log.json` — per model per run: promoted/blocked, reason, rows, held-out log
  loss before and after.
* `output/ml_learning_health.json` (Pro, daily) — per model: `PASS / NO_NEW_DATA /
  TRAINING_DUE / STALE / FAILED / BLOCKED`, incumbent age, training-input age, new settled
  fixtures unseen, and the last genuine learning event. **`NO_NEW_DATA` and `STALE` are
  deliberately distinct** — an international break and a dead collector both look like "nothing
  changed", and only one is healthy. That distinction is what every failure above needed.
* GitHub annotations: `::error` for STALE/FAILED/BLOCKED, `::warning` for TRAINING_DUE, and an
  explicit error when no learning event is on record.
* Telegram: `notify_retrain_result()` reports per model whether it got sharper.
* v11: a zero-usable-row movement run now exits non-zero instead of printing a table.

---

## N. Remaining blockers

1. **The loop has not completed a cycle.** Everything is wired; nothing has run end to end.
2. **Feature freshness unproven** (§I) — the single most valuable next check.
3. **Median-imputation leakage unverified** (§H).
4. **sklearn version skew uninvestigated** (§J).
5. **No challenger/incumbent artifact separation** (§8). The gate compares metrics and declines
   to overwrite; it does not keep challengers in `models/challengers/` with provenance.
6. **No canary test** (§21). CI cannot yet fail on "running but not learning".
7. **Dataset fingerprinting is computed but not attached to model artifacts** (§19).

---

## Verdict

```text
RUNNING_REPOS_SAFE=YES
V9_PREDICTIVE_LOGIC_UNCHANGED=YES

NEW_DATA_REACHES_TRAINING=PARTIAL
TRAINING_DATA_FRESH=NO
FEATURES_ADVANCE_WITH_NEW_MATCHES=UNVERIFIED

RETRAIN_PIPELINE_OPERATIONAL=REPAIRED_UNVERIFIED
CHALLENGER_CREATION_OPERATIONAL=NO
CHRONOLOGICAL_OOS_VALIDATION_OPERATIONAL=YES
INCUMBENT_COMPARISON_OPERATIONAL=REPAIRED_UNVERIFIED
PROMOTION_GATE_OPERATIONAL=REPAIRED_UNVERIFIED
REJECTION_GATE_OPERATIONAL=REPAIRED_UNVERIFIED
MODEL_PROVENANCE_COMPLETE=NO

PLAYER_PROPS_LEARNING_OPERATIONAL=REPAIRED_UNVERIFIED
SIDE_MARKET_OOS_LEARNING_OPERATIONAL=YES

SILENT_STALENESS_DETECTION=YES
LEARNING_HEALTH_MONITORING=YES

LAST_GENUINE_MODEL_LEARNING_DATE=NONE
CURRENT_INCUMBENT_MODEL_AGE_DAYS=23
NEW_SETTLED_MATCHES_SINCE_INCUMBENT=392

ML_LEARNING_SYSTEM_HEALTHY=NO
SAFE_TO_CONTINUE_PROSPECTIVE_COLLECTION=YES
```

`REPAIRED_UNVERIFIED` is used deliberately where a fix is written, tested in isolation and
pushed, but has not yet executed a real cycle in CI. Per §22 a green workflow is not evidence;
these become `YES` when `retrain_log.json` records a decision and `ml_learning_health.json`
reports `PASS`.

`SAFE_TO_CONTINUE_PROSPECTIVE_COLLECTION=YES` — collection is the one part of the estate that
has been working throughout, and §24's evidence cannot be reconstructed later. Keep collecting.

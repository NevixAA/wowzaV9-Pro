# MIGRATION_PLAN.md — wowzaV9-Pro

Prompt 1 forbids starting with a rewrite: *"First inspect the full repo and Actions runtime,
map dependencies and reusable components, then write the migration plan."* The audit is
`WORKFLOW_MAP.md`. This is the plan.

---

## Decisions taken (2026-08-17)

| decision | value |
|---|---|
| Pro location | the former `v10/` folder → repo `wowzaV9-Pro` |
| v9 (`wowza-betting`) | **frozen baseline.** Runs as-is all season. Not modified by Pro work |
| v10's staging role | retired. `CLAUDE.md` invariant 3 no longer applies and must be rewritten |
| `wowza-v11` | **keeps running.** Pro *ports* its market layer; v11 continues its own shadow log |
| Telegram from Pro | **none.** Pro never notifies this season |
| v9's leaky `__meta__` blend | left in place. Documented as a known baseline property |
| legacy v10 code | preserved on disk under `_legacy/`, **not committed**. Ported deliberately |

Two independent shadows (v11 market-first, Pro strict-validation) disagreeing is information,
which is why v11 stays.

---

## The sequencing decision, and why it inverts the prompts

Prompt 1 is 22 items of engineering. Prompt 2 is a data mandate. **Prompt 2 goes first.**

- **Prompt 1's work is retrospective.** Fixing the stacker, building the registry, adding
  FDR control — the historical rows do not move. The same work yields the same answer in
  December.
- **Prompt 2's work is irreversible.** Every day without the season store is a day of
  open→close curves, model snapshots at T-7d/T-3d/T-1h, and feature-state-at-decision-time
  that is **permanently gone.** "What did the model think at 12:00, and what was the market
  price then" cannot be backfilled.

So the build order is: capture first, then validate. Phase 1 is the only phase with a clock
on it.

---

## Phase 0 — audit ✅ done

`docs/WORKFLOW_MAP.md`. Findings that shape everything downstream:

1. Six artifacts have 2–3 concurrent writers resolved by `git pull --rebase -X ours`, which
   **silently discards the losing run's rows.** Prompt 2's "append, never overwrite" is not
   achievable on v9's storage model.
2. Failures are silent by default (`continue-on-error` everywhere; health emitted only as
   annotations). Two multi-day outages this week, both green.
3. Season-keyed config is hand-maintained; three instances of the same rot.
4. Quota is not the constraint (~60k/day spare). Wall-clock in the 5-minute loop is.
5. v11 already implements Prompt 1 §9, §10, §2, §11 and §15.

---

## Phase 1 — canonical season store + importer  ⏱ **urgent, start now**

Satisfies Prompt 2 §4–§9, §13–§16, §18.

**Storage design — chosen to make the Phase-0 finding structurally impossible:**

```
data/season_2026_27/
  <table>/dt=YYYY-MM-DD/run=<run_id>.parquet
```

Run-partitioned. Two runs can never write the same bytes, so there is no conflict surface and
no `-X ours` discard. Append is the only operation. A separate single-writer compaction job
may later roll partitions up; it never deletes a source partition.

Tables, per Prompt 2 §4: `fixtures`, `model_snapshots`, `market_snapshots`,
`feature_snapshots`, `signals`, `settlements`, `clv`, `player_props`, `live_signals`,
`data_quality`.

**`src/importers/current_wowza.py`** normalises v9's legacy outputs into those tables. It
reads v9's committed data (the pattern v11 already uses) and **never writes to v9.**

Non-negotiables:
- **Every evaluated fixture is stored** — AVOID, NO_BET, PAPER, RESEARCH, BLOCKED included
  (§5). Not just SNIPER/MARKSMAN/VALUABLE.
- **Repeated predictions are all retained** with `prediction_timestamp`, `model_id`,
  `model_sha` (§7). Never overwrite.
- **`odds_source` on every row** — `REAL` / `SYNTHETIC` / `IMPUTED` / `UNKNOWN` (Prompt 1 §8).
- **Data-quality flags, not deletion** (§16): `MARKET_MAPPING_INVALID`, `ODDS_ORDER_INVALID`,
  `MISSING_OPPOSITE_SIDE`, `STALE_PRICE`, `LOW_BOOK_COUNT`, `ENTITY_UNRESOLVED`,
  `FEATURE_DEGRADED`, `MODEL_VERSION_UNKNOWN`, `SYNTHETIC_ODDS`, `SETTLEMENT_UNCERTAIN`.
  Contaminated rows are flagged and kept, never silently dropped (§3).
- **Control-group buckets** recorded at write time (§9): residual bands
  `<0, 0–2, 2–4, 4–6, 6–8, 8–10, 10%+` and odds bands
  `1.20–1.50, 1.50–1.75, 1.75–2.00, 2.00–2.50, 2.50–3.50, 3.50+`. Goal is
  `E[CLV | residual]`, not re-validating old thresholds.

**Collector workflow** — `.github/workflows/pro_collect.yml`. Scheduled (Prompt 2 §17), **no
Telegram secret**, own concurrency group, asserts non-empty output and exits non-zero
otherwise. Reads v9 over HTTP; shares no state with v9.

**Exit criteria:** every v9 artifact in §7 of the audit has a normalised Pro table; a full day
of snapshots lands without manual intervention; row counts reconcile against v9; the workflow
goes red when it produces nothing.

---

## Phase 2 — market layer (port, don't rewrite)

Satisfies Prompt 1 §9, §10, §11.

Port from `wowza-v11/src/edge_engine.py` into `src/market/`: `power_devig`,
`proportional_devig`, `market_baseline`, the CLV gate, and the `BET`/`PAPER`/`NO_BET`
separation. Port `resolve()` from `v9/src/team_names.py` into `src/data/entities.py` for
Prompt 1 §18, adding resolution-rate tracking and failure classification (promotion, rename,
reserve team, wrong league, missing alias).

Each port carries an **OLD / NEW / WHY / RISK** note. Tests: de-vig output is a valid
probability; one-sided markets cannot produce a fair probability; invalid market mappings are
quarantined; a blind fixture cannot become LIVE.

---

## Phase 3 — validation rebuild

Satisfies Prompt 1 §1, §2, §3, §4, §7, §16, §17.

`v9/src/model.py` is **not** ported. Confirmed defect at `model.py:235-249`:

```python
# "The test split was never seen by any base model, so there is no leakage."  ← false
meta_X = np.column_stack([results[n]["model"].predict_proba(X_test)[:,1] for n in results])
meta_clf.fit(meta_X, y_test)
meta_proba = meta_clf.predict_proba(meta_X)[:, 1]   # scored on its own training data
```

Three distinct problems: the reported meta AUC is **in-sample**; the comment asserts safety
that does not hold (it is the *base* models that never saw the split, which is irrelevant to
the meta model); and there is **no final holdout at all** — the split is three blocks and the
last does triple duty as base-model eval, meta training set, and meta eval. The blend is also
in v9's live predict path, so production probabilities come from an unvalidated blend fit on
one small slice.

Pro implements four chronological blocks — **TRAIN / CALIBRATION / META-TRAIN / FINAL
HOLDOUT** — or chronological OOF stacking. Persist AUC, LogLoss, Brier, ECE, calibration
intercept/slope and n on the final holdout only.

Then market-relative validation (§2): **A** = Wowza only, **B** = market consensus only,
**C** = market + Wowza, chronologically OOS, globally and per league. Incremental LogLoss and
Brier improvement of C over B is the deployment evidence. Standalone AUC is not.

Also: persisted training-time imputers (§4 — never impute from the prediction batch),
league-aware shrinkage calibration (§7), block/bootstrap CIs (§16), Benjamini–Hochberg FDR
across the league × market × side × odds-band × tier search (§17).

Model families enter as `RESEARCH` and move only on evidence: standard O2.5 ≈0.55,
new-format O2.5 ≈0.60 (highest priority), BTTS ≈0.53, O1.5 ≈0.54, O3.5 ≈0.56, HT weak, props
no established edge, live experimental. **Those AUCs are themselves suspect** where they came
from the ensemble — re-derive on a real holdout before using them to prioritise.

---

## Phase 4 — provenance, registry, gates

Satisfies Prompt 1 §5, §6, §12, §13, §14, §15, §19, §20.

Feature contracts (dtype, required, training distribution, missing rate, serving limits) with
PSI/KS drift; `experiments/<experiment_id>/` holding manifest, metrics, by-league,
bets.parquet, calibration and plots; the model registry; champion/challenger promotion where
retraining produces a **challenger**, never an automatic replacement; and
`output/system_registry.json` as the single machine-readable production truth.

Deployment gate checks model status, league/market approval, feature health, odds health,
freshness and validation state — **separately** from signal tier. `SNIPER + PAPER` is valid.

---

## Phase 5 — shadow comparison

Satisfies Prompt 2 §18, Prompt 1 migration section.

Per fixture retain: baseline (v9) probability and signal, Pro probability and signal, v11
probability and signal, market consensus, best odds, closing probability and odds, result.
Three independent opinions against one market price.

**Production does not switch automatically.** Ever.

---

## Guardrails

1. **Never write to v9.** Pro reads v9's committed output over HTTP. No shared files.
2. **No Telegram from Pro** this season.
3. **No Pro job shares a concurrency group with v9's `predict`, or lengthens it.**
4. **Nothing is deleted.** Legacy outputs are research assets (Prompt 2 §3). Contaminated
   rows get a quality flag, never a delete.
5. **A collector producing zero rows fails loudly.** No more green outages.
6. **No season literals.** Derive from date; test asserts the live season is present.
7. **Secrets stay out of the repo.** v10's `.env` holds live API-Football, Google and GitHub
   credentials — these must reach CI as repository secrets and be rotated, since they have
   been sitting in a plaintext file.
8. **Never headline synthetic-odds ROI.** `REAL_ONLY` or `INSUFFICIENT_MARKET_DATA`.
9. **Never promote on AUC alone.**

---

## Deliverable status

| deliverable | state |
|---|---|
| `docs/WORKFLOW_MAP.md` | ✅ done |
| `docs/MIGRATION_PLAN.md` | ✅ this file |
| `ARCHITECTURE.md` | phase 1 |
| `MODEL_VALIDATION_STANDARD.md` | phase 3 |
| `BETTING_VALIDATION_STANDARD.md` | phase 3 |
| `MODEL_REGISTRY.md` | phase 4 |
| `CHANGELOG_PRO.md` | continuous |
| `output/pro_readiness.json` | phase 4 |
| `output/system_registry.json` | phase 4 |

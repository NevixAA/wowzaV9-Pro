# Wowza System Contract — v2.0.0

*The authoritative map of what Wowza is **today**. Written for a new engineer, and for every
future AI session that needs to understand the estate before changing it.*

**Machine-readable twin:** [`registry/WOWZA_SYSTEM_CONTRACT.json`](../registry/WOWZA_SYSTEM_CONTRACT.json)
· schema: [`registry/WOWZA_SYSTEM_CONTRACT.schema.json`](../registry/WOWZA_SYSTEM_CONTRACT.schema.json)
· validator: `python -m src.validation.validate_system_contract` (read-only)

| verified against | commit |
|---|---|
| v9 (`wowza-betting`) | `cacee086` |
| Pro (`wowzaV9-Pro`) | `9d986b12` |
| v11 (`wowza_v11`) | `6d3d6995` |

> **What changed from v1.0.0 (2026-09-24).** v1 called v9 "change-controlled" but never separated
> *routine model learning* from *architectural change*, which risks an agent reading "don't modify
> v9" as "stop v9 retraining". It also understated the tier stake semantics and left the threshold
> regimes unrecorded. Those are the substantive corrections here.

---

## 1. Estate overview

Three independent repositories, three generations, one shared data root.

| | repo | role | status |
|---|---|---|---|
| **v9** | `NevixAA/wowza-betting` | live production | `PRODUCTION_CHANGE_CONTROLLED` |
| **Pro** | `NevixAA/wowzaV9-Pro` | evidence, validation, learning | `ACTIVE_RESEARCH` |
| **v11** | `NevixAA/wowza_v11` | market-first shadow | `EXPERIMENTAL` |

---

## 2. Repository roles

**v9** — collection, training, retraining, prediction, settlement, Telegram, operational output.
257 tracked files, 22 workflows, **no test suite** (`test_telegram.py` is a manual send check;
validation here is the backtest and audit harness — never claim v9 tests pass).

**Pro** — canonical evidence, validation, shadow learning, research, paper systems, Bet Builder,
next-generation foundation. 3,013 tracked files, 10 workflows. Holds the estate's **only** real
test suite: `python -m pytest tests/` from `v10/`. Reads v9's committed output over HTTP
(`src/data/v9_source.py`); no write path into v9 exists.

**v11** — market-first experimental research, read-only consumer of v9. 50 tracked files, 1
workflow. **Zero** occurrences of `api.telegram.org` or `sendMessage` anywhere in the repo.

---

## 3. V9 production learning lifecycle

```
new completed matches → history expands → retraining → challenger
     → validation → promotion gate → new production model artifact
```

**This is good. Do not block it.**

Confirmed live at HEAD: `output/retrain_log.json` records retrains on 2026-09-24, 09-25 and
09-26, every comparison on `basis=same_holdout`, with both promotions and blocks occurring.

---

## 4. Routine retraining vs architecture changes

The central distinction of this contract.

| | ROUTINE MODEL LEARNING | ARCHITECTURAL / BEHAVIORAL CHANGE |
|---|---|---|
| policy | **allowed and expected** | **explicit approval required** |
| new training rows, new end date | ✓ | |
| new fitted coefficients, trees, calibration | ✓ | |
| new model artifact, new validation metrics | ✓ | |
| new target definition, new feature family | | ✓ |
| different algorithm or calibration architecture | | ✓ |
| new league routing, new preprocessing behavior | | ✓ |
| new threshold system, staking logic, Telegram semantics | | ✓ |
| new promotion methodology, training-source switch | | ✓ |

```
V9_CONTINUOUS_RETRAINING_ALLOWED   = YES
V9_ARCHITECTURE_CHANGE_CONTROLLED  = YES
V9_LITERAL_FREEZE_CORRECT          = NO
```

These are not contradictory. **"Do not modify V9" does not mean "stop V9 retraining."**

The two evolution paths, which must not be confused:

```
NEW FOOTBALL → v9 routine retraining → refreshed production artifact
NEW IDEA → Pro / v11 → chronological evidence → challenger
         → repeated validation → owner approval → deliberate v9 upgrade
```

---

## 5. Data architecture

```
football-data.co.uk ──> output/fd_history.parquet     62,321 rows / 30 leagues
API-Football        ──> output/af_history.parquet     89,432 rows / 33 leagues
                    ──> player_history.parquet       501,602 rows / 31 leagues
                    ──> output/af_ht_history.parquet   6,977 rows / 15 leagues  [STALE]
OddsAPI / RapidAPI  ──> live prices, unified to { fixture_id: (over, under) }
```

`player_history.parquet` is a **directory of per-season parts** since 2026-09-27 — a finished
season is immutable, so git stores it once instead of rewriting 90 MB daily.

### Shared root — `DO_NOT_MOVE_OR_RENAME`

`v9/config.py` sets `DATA_DIR = BASE_DIR.parent`, i.e. the `mixed/` folder. Both v9 and the
`LEGACY_IGNORED` copy inside `v10/` read these by relative path. Members include
`England_Leagues_4_Seasons_With_Summary.xlsx` (local-only, never committed — so **CI trains on
less data than a local run**), `sofascore_cache.json`, `best_params.json`.

**Future product code must never reorganize this shared root for cleanliness.**

### Identity invariants

**Team** — canonical resolution is league-scoped and refuses ambiguous matches
(`src/team_names.resolve`); `src/data_loader._canonicalise_clubs` unifies spellings, dedupes on
`(date, league, home, away)` keeping the most complete row, and **quarantines score conflicts
rather than picking a side**. Alternate club spellings previously split rolling form across two
"teams". Never join sources by raw team string when canonical resolution exists.

**Player** — a player belongs to his **latest club**, not every club he has played for.
Implemented at `player_model/predict.py:454-472`: sort by date, `drop_duplicates(player_id,
keep="last")` over **club** rows only. History holds internationals where `team` is the player's
country, which is why club-only matters.

### Missing data — two different policies

| | |
|---|---|
| **canonical storage** | prefer `NaN`. Never invent a value. |
| **model preprocessing** | may legitimately impute at fit/inference (`src/model._prep`) |

"Write NaN, never invent a number" applies to **evidence and canonical storage**, not to all
model preprocessing. Conflating them produces wrong conclusions in both directions.

### Leakage invariants

Chronological split · as-of features · train-only preprocessing · no post-kickoff information ·
no random split for time-dependent validation. Verified: `_rolling` is
`x.shift(1).rolling(n)` grouped by team, and no raw same-match column appears in `FEATURE_COLS`.

---

## 6. Models

> **Existence is not authorization.** Each of these is a separate field:
> `MODEL_EXISTS` ≠ `MODEL_CAN_NOTIFY` ≠ `MODEL_IS_PAPER` ≠ `MODEL_CAN_BE_STAKED` ≠
> `MODEL_HAS_VALIDATED_EDGE` ≠ `MODEL_CAN_BE_COMMERCIALISED`.

**Match models (7):** `model_v9_standard` (O/U 2.5), `model_v9_newformat` (O/U 2.5),
`model_v9_btts`, `model_v9_over15`, `model_v9_over35`, `model_ht_over05`, `model_ht_over15`.

**Player models (9):** goals, goals2, goals3, assists, cards, sot, sot2, sot3, sot4 — **all
PAPER, none real-money authorized.**

Architecture: LogReg + GradientBoosting (+ LightGBM) ensemble, Platt-calibrated, per market,
chronological walk-forward split — never random.

---

## 7. League routing

```
DESIGN_SEPARATION        = YES
STRICT_RUNTIME_ISOLATION = NO
```

Routing is real — `src/predict.py:323-335` uses separate `std_mask` / `nf_mask` and separate
artifacts. But **two runtime fallbacks allow crossover**:

```python
# predict.py:332 — missing new-format artifact → new-format fixtures scored by STANDARD
nf_payload = payload_newformat if payload_newformat is not None else payload

# predict.py:339-343 — league in NEITHER list → scored by STANDARD
unknown_mask = ~std_mask & ~nf_mask
```

Do **not** write "standard and new-format can never mix". Say design-separate, runtime-permissive.

HT models apply under `std_mask` only, so 0% HT on new-format leagues is correct by design.

---

## 8. Signals and betting states

**Two separate dimensions.** Collapsing them is how "the model is accurate" becomes "the bet is
profitable".

| dimension | vocabulary |
|---|---|
| `prediction_state` | FORECAST · RESEARCH · VALIDATED · RETIRED |
| `betting_state` | PAPER · LIVE · BLOCKED · NO_BET |
| v9 tiers | SNIPER · MARKSMAN · VALUABLE · AVOID |
| v11 states | BET · PAPER · NO_BET |

### Tier stake semantics — corrected from v1

From `src/betting.py:143-145` and `src/backtest.py:358`:

| tier | meaning |
|---|---|
| SNIPER | meets per-league threshold — **full stake** (1.0) |
| MARKSMAN | edge ≥ `MARKSMAN_THRESHOLD` — **3/4 stake** (0.75) |
| VALUABLE | edge ≥ `VALUABLE_THRESHOLD` — **half stake / monitor** (0.5) |

v1 called VALUABLE "information only". That was wrong — it carries a half-stake weight, and
MARKSMAN is a real tip.

### Threshold regimes — reference is not active

| | `config.py` (REFERENCE) | `predict.yml` (ACTIVE) |
|---|---|---|
| `MARKSMAN_THRESHOLD` | 0.14 | **0.08** |
| `VALUABLE_THRESHOLD` | 0.04 | **0.03** |
| `LEAGUE_SNIPER_CAP` | unset (no cap) | **0.12** |

**Historical performance must not silently pool threshold regimes.** A bet taken under MARKSMAN
0.08 is not comparable to one under 0.14. *Recommendation only, not implemented:* future
publications should carry a `threshold_regime_id`.

### Rolling-form guard

Default **ARMED** — a fixture with no rolling form is forced to AVOID (invariant 8).

It **was** overridden for early-season testing (`REQUIRE_FORM_DATA=0`), but the override was
deliberately time-boxed by `REQUIRE_FORM_DATA_UNTIL=2026-09-15` and the code re-arms
**regardless of the env flag** once that date passes. Evaluated 2026-09-27: `expired=True`,
guard **ARMED**. Don't pretend the override never happened; it did, and it self-expired.

---

## 9. Real-money boundaries

**There is no automated bet placement anywhere in the estate.** No `place_bet`, no
`place_order`, no exchange integration. Matches for "betfair", "smarkets", "matchbook" are
bookmaker *name lists used to read prices*.

What the code produces is a **recommended** stake — `kelly_pct`, described in `src/ledger.py:22`
as *"recommended stake as % of bankroll (25% Kelly)"*.

```
SNIPER_STAKED_BY_CODE                  = NO
MARKSMAN_STAKED_BY_CODE                = NO
VALUABLE_STAKED_BY_CODE                = NO
ONLY_SNIPER_REAL_MONEY_CODE_ENFORCED   = NO
OWNER_REAL_MONEY_POLICY_CONFIRMATION_REQUIRED = YES
```

"Real money is standard 2nd-division O/U SNIPER only" is **owner operating policy**. It cannot
be proven or refuted from the repository. **Do not rewrite production to make the code match
that sentence, and do not modify MARKSMAN.**

> **A Telegram notification must never be assumed to be a wager.**

---

## 10. Notification boundaries

| repo | pipeline | notifies | dedup |
|---|---|---|---|
| v9 | predict / tips | ✓ | `notified.json`, `date\|home\|away\|SIDE` + opposite-side guard |
| v9 | player props | ✓ (PAPER) | `player_notified.json` |
| v9 | live scanner | ✓ | `live_notified.json`, match+minute |
| v9 | daily digest | ✓ | `DIGEST\|<utc-date>` |
| **Pro** | **bet_builder** | ✓ | `pro_bet_builder.yml:94,110` |
| **Pro** | **paper_1x2** | ✓ | `pro_paper_1x2.yml:80-81` |
| Pro | collect | ✗ | binds no Telegram secret |
| v11 | everything | ✗ | none exist |

```
PRO_COLLECT_MUST_NOT_NOTIFY = the correct invariant
"Pro never notifies"        = FALSE, do not encode it
```

---

## 11. Pro canonical architecture

Canonical match / market / player layers, training views with dataset manifests, as-of feature
builders, entity resolution with quarantine, and a data-quality canary. `src/architecture/`,
`src/shadow_learning/`, `src/prediction_lab/`.

---

## 12. V11 research architecture

```
validate odds → de-vig (power) → consensus p_market
  → blend model as a SMALL RESIDUAL, capped per segment (NF 0.45 / std 0.40 / else 0.30)
  → uncertainty lower bound → EV lower bound → CLV gate → longshot cap
```

Defaults to **NO_BET**. `MIN_CLV_N = 150` at HEAD; `BET` needs a segment's clean CLV count ≥ 150
and positive, otherwise `PAPER`. That gate deliberately solves the bootstrap trap.

```
V11_READS_V9_ONLY = YES    V11_WRITES_V9 = NO
V11_CAN_STAKE     = NO     V11_CAN_NOTIFY = NO
```

**The residual test** — does the model improve Brier / log loss *after* the market price is
known — is the primary question. **Standalone AUC is not v11's success metric.**

---

## 13. Research validity

| research | status | note |
|---|---|---|
| v11 momentum, **pre-fix** | **INVALIDATED** | `merge_asof` index reset; commits `929f783`, `4ed8aa9` |
| v11 momentum, **post-fix** | **CURRENT** | fixed `ba21c4c` (09-10), artifacts regenerated `6d3d699` (09-22) |
| canonical player history | **CURRENT** | verified against artifact — see below |
| more match rows → better model | **CURRENT** | **NO.** Restored features worth 0.0005–0.002 log loss |
| calibration +13.64pp | CURRENT | provenance `AGENT_13_RED_TEAM.md:100`, `DOCUMENTED_ONLY` |
| tier ladder carries no information | **EXPERIMENTAL** | evidence with a sample, **not** an invariant |

### Canonical player history — verified, 41 months, 123 rows

| variant | log loss | AUC | PR-AUC |
|---|---|---|---|
| **canonical** | **0.24697** | **0.76314** | **0.23423** |
| current | 0.25131 | 0.74745 | 0.22280 |
| frozen | 0.25525 | 0.73591 | 0.21295 |

Classification: **`PREDICTION_QUALITY_RESEARCH`, not `BETTING_EDGE`.** Recovering canonical
player history measurably improves prediction. It does **not** create a betting edge and does
**not** change `real_money_enabled` for props.

It also answers the learning question: **frozen is the worst variant on all three metrics.**
Retraining on accumulated experience beats a frozen model — on prediction quality, which is
separate from architecture and separate from betting edge.

---

## 14. Shared filesystem risks

See §5. `odds_history_v9.json` is tracked at v9 **root** (not `output/`), is load-bearing for
drift, and must stay committed: `critical=true`, `move_safe=false`.

---

## 15. Health and canaries

Training coverage (`output/training_coverage.json`), props health, history-extend health, API
usage monitor (30 min), Pro data-quality canary, v11 research freshness.

> **Green CI does not prove the statistical instrument is measuring anything.** v11's momentum
> work exited 0 for four weeks while measuring nothing.

---

## 16. Future product boundary — contract only, nothing built

```
V9 / approved Pro outputs → Product Publisher → Product PostgreSQL → FastAPI → Web / Android
```

The product must **never**: train models · promote models · change thresholds · change staking ·
change retraining · write to v9, Pro or v11 · control Telegram · move the shared root · import
internal model code into a frontend.

**It must handle model-version evolution.** v9 retrains, so the product *will* see
`model_version` A, B, C. The publisher publishes `model_version`, `dataset_id`, `generated_at`
and `code_sha` so a customer's historical predictions stay attributable.

**Immutable history.** 14:00, 16:00 and 18:00 are three snapshots, never one overwritten value.

**The frontend must never decide** FORECAST / PAPER / VALIDATED / LIVE from a probability or an
edge. That state arrives from the backend.

**Claim boundary.** Predictive accuracy · calibration · market residual · CLV · historical
betting ROI · prospective betting ROI are **six different things**. Never convert "better AUC"
into "profitable bet", or "player prediction improved" into "player prop edge".

Player forecasts *may* become product features even though betting stays permanently PAPER:
*"Messi scores: 34%"* is a forecast; *"BET Messi to score"* is a betting claim.

---

## 17. AI permissions

```json
{
  "v9":      "READ_ONLY_BY_DEFAULT_EXCEPT_ROUTINE_EXISTING_RETRAINING",
  "pro":     "RESEARCH_CHANGES_ALLOWED_WITH_TESTS",
  "v11":     "EXPERIMENTAL_CHANGES_ALLOWED_WITH_TESTS",
  "product": "ISOLATED_DEVELOPMENT_ALLOWED"
}
```

The v9 carve-out means the **existing** retraining machinery keeps running. It does **not**
permit an agent to trigger new or altered retraining architecture.

Explicit authorization required for: feature changes · model changes · threshold changes ·
staking changes · notification changes · training-source switches · promotion methodology.

> A prompt such as *"improve Wowza"*, *"build the product"* or *"make predictions better"* does
> **not** imply permission to modify v9 architecture.

### Source-of-truth precedence

1. executable code · 2. workflow config · 3. machine-readable registries · 4. generated
health/manifests · 5. docs · 6. comments · 7. historical README · 8. old summaries

**Code proves implementation. Code does not prove owner bankroll policy.** Owner policy stays
separately labelled.

---

## 18. Current verified SHAs

v9 `cacee086` · Pro `9d986b12` · v11 `6d3d6995`

**Staleness is not failure.** `CONTRACT_STALE=YES` means only that the documentation needs
re-verification. It must never stop v9, retraining, predictions, Telegram or collectors, and
v9 production must never depend on the validator. **Do not auto-regenerate this from CI** — a
system that silently rewrites architectural truth is worse than a stale document.

---

## 19. Known unknowns

| item | status |
|---|---|
| which Telegram tips became real wagers | `OWNER_CONFIRMATION_REQUIRED` |
| whether the deployed model is better in money terms | `UNKNOWN` — no fair OOS window yet |
| `pro_paper_1x2` sending module | `UNKNOWN` — secrets bound, module not traced |
| residual-vs-velocity conflict (v11 post-fix vs `AGENT_11`) | `CONTESTED` |
| `output/af_ht_history.parquet` | `STALE` — written only by a script no workflow runs |
| `player_history.parquet` growth vs the 100 MB limit | mitigated by the season split; watch the guard |

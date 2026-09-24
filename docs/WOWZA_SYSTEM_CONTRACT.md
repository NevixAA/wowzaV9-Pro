# Wowza System Contract

*The authoritative map of what Wowza is **today**. Written for a new engineer, and for every
future AI session that needs to understand the estate before changing it.*

**Machine-readable twin:** [`registry/WOWZA_SYSTEM_CONTRACT.json`](../registry/WOWZA_SYSTEM_CONTRACT.json)
· schema: [`registry/WOWZA_SYSTEM_CONTRACT.schema.json`](../registry/WOWZA_SYSTEM_CONTRACT.schema.json)
· validator: `python -m src.validation.validate_system_contract` (read-only)

| verified against | commit |
|---|---|
| v9 (`wowza-betting`) | `6dc09e31` — local HEAD, 3 ahead / 2 behind origin |
| Pro (`wowzaV9-Pro`) | `4011587f` — clean |
| v11 (`wowza_v11`) | `6d3d6995` — local HEAD, 8 ahead of origin |

> Every statement below was read off those three trees. Nothing was inferred from an old README.
> If HEAD has moved, run the validator: it reports `CONTRACT_STALE=YES` and changes nothing.

---

## 1. System overview

Three independent repositories, three generations, one shared data root.

| | repo | role | status |
|---|---|---|---|
| **v9** | `NevixAA/wowza-betting` | live production — sends the tips | `CHANGE_CONTROLLED` |
| **Pro** | `NevixAA/wowzaV9-Pro` | evidence, validation, learning | `ACTIVE_RESEARCH` |
| **v11** | `NevixAA/wowza_v11` | market-first shadow | `EXPERIMENTAL` |

### "v9 is frozen" — restated

**v9 is not immutable, and this contract does not claim it is.** Between 2026-09-22 and
2026-09-24 it received training-data expansion, club-name canonicalisation, promotion-gate
changes and a notifier fix, on top of continuous automated commits.

The accurate statement is:

> v9 is the live production generation. It is **change-controlled**: do not redesign it
> casually, and every change needs explicit owner authorization. It is not locked.

That is `OWNER_POLICY`, not a code-enforced constraint.

---

## 2. Repository ownership

### v9 — production
- 257 tracked files, 22 workflows, no test suite
- Owns: `player_history.parquet`, `output/*`, `models/*`, all Telegram tips
- Reads: football-data.co.uk, API-Football, OddsAPI, RapidAPI, the shared root
- `test_telegram.py` is a manual send check, **not** a suite. Never claim v9 tests pass — run
  the relevant backtest instead.

### Pro — evidence and validation
- 3,013 tracked files, 10 workflows
- **Holds the estate's only real test suite**: `python -m pytest tests/` from `v10/`
  (no pytest config file exists). `python -m src.combo.tests` is a separate Bet Builder
  correctness gate, not a unit suite.
- Reads v9's committed output **over HTTP** (`src/data/v9_source.py`). No write path into v9.

### v11 — market shadow
- 50 tracked files, 1 workflow
- Reads v9 at `raw.githubusercontent.com/NevixAA/wowza-betting/main/output` (`config.py:13`),
  with an optional read-only sibling-clone fallback
- **Zero** occurrences of `api.telegram.org` or `sendMessage`. It cannot notify.

---

## 3. The production money path

```
football-data.co.uk ──> output/fd_history.parquet
API-Football        ──> output/af_history.parquet, player_history.parquet
OddsAPI / RapidAPI  ──> live prices
        │
   src/data_loader.py      canonicalise clubs, resolve names, merge HT, impute
        │
   src/model.py            LogReg + GradientBoosting (+ LightGBM), Platt-calibrated,
                           CHRONOLOGICAL split — never random
        │
   src/predict.py          edge = model_prob − 1/odds  →  SNIPER / MARKSMAN / VALUABLE
        │
   telegram_bot/notifier.py
```

### There is no automated staking. Anywhere.

This is the single most important safety fact in the contract.

**No bet-placement code exists in any of the three repos.** No `place_bet`, no `place_order`,
no exchange integration. The matches for "betfair", "smarkets" and "matchbook" are *bookmaker
name lists used to read prices* (`v10/src/market/best_price.py:50`,
`wowza-v11/src/book_consensus.py:51`).

What the code produces is **advisory**: a tier, an edge, and `kelly_pct`, described in
`src/ledger.py:22` as *"recommended stake as % of bankroll (25% Kelly)"*. `src/portfolio.py`
caps same-day correlated exposure. `pages/12_Portfolio.py` is a simulation.

Therefore:

| | |
|---|---|
| `REAL_MONEY_SCOPE_CODE_VERIFIED` | **NO** |
| `REAL_MONEY_SCOPE_OWNER_POLICY_REQUIRED` | **YES** |

The claim *"real money is standard-format second-division O/U SNIPER only"* is
**`OWNER_OPERATING_POLICY`**. It cannot be proven from code, because no code stakes anything.

> **A Telegram notification must never be assumed to be a wager.**

---

## 4. Notification paths

| repo | pipeline | notifies? | credentials | dedup |
|---|---|---|---|---|
| v9 | predict / tips | **yes** | `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | `notified.json`, key `date\|home\|away\|SIDE` + opposite-side guard |
| v9 | player props | **yes** (PAPER) | same | `player_notified.json` |
| v9 | live scanner | **yes** | same | `live_notified.json`, match+minute window |
| v9 | daily digest | **yes** | same | `DIGEST\|<utc-date>` |
| **Pro** | **bet_builder** | **yes** | `pro_bet_builder.yml:94,110` | notify dedup |
| **Pro** | **paper_1x2** | **yes** | `pro_paper_1x2.yml:80-81` | — |
| Pro | collect | **no** | `pro_collect.yml:5` binds none | — |
| Pro | all other `pro_*` | no | — | — |
| v11 | everything | **no** | none exist | — |

### Correction to a stale claim

> ~~"Pro never notifies"~~ — **false.**

The accurate rule is:

> **Pro *collection* must never notify. Explicitly authorized Pro research/paper pipelines
> (`bet_builder`, `paper_1x2`) may notify.**

Note that `pro_collect.yml:5` asserts *"NO TELEGRAM SECRET IS REFERENCED HERE, AND NONE EXISTS
IN THIS REPO."* The first half is true; the second half is stale — two other Pro workflows do
bind Telegram secrets.

---

## 5. Signal states

```
FORECAST   a probability exists
RESEARCH   produced by a research pipeline, not a production one
PAPER      tracked in a ledger at flat stake, no money
VALIDATED  an out-of-sample result supports it
LIVE       currently emitted by production
BLOCKED    gated off
RETIRED    no longer produced
```

**These are not interchangeable, and the UI must never decide which one applies** — see §14.

---

## 6. Model registry

Existence proves nothing. A model existing does **not** imply a validated edge, real-money
authorization, notification authorization, or commercial authorization. Those are separate
fields in the JSON.

### Match models (7)

| model | market | format | state | real money |
|---|---|---|---|---|
| `model_v9_standard` | O/U 2.5 | standard | LIVE | owner policy only |
| `model_v9_newformat` | O/U 2.5 | new-format | LIVE | no |
| `model_v9_btts` | BTTS | standard | LIVE | no |
| `model_v9_over15` | Over 1.5 | standard | LIVE | no |
| `model_v9_over35` | Over 3.5 | standard | LIVE | no |
| `model_ht_over05` | HT Over 0.5 | standard | LIVE | no |
| `model_ht_over15` | HT Over 1.5 | standard | LIVE | no |

HT models apply under `std_mask` only (`src/predict.py:386`) — **half-time is
standard-leagues-only by design**, so 0% HT coverage on new-format leagues is correct, not a gap.

### Player models (9)

`goals`, `goals2`, `goals3`, `assists`, `cards`, `sot`, `sot2`, `sot3`, `sot4` — **all PAPER,
none real-money authorized.**

> Prediction quality and betting edge are different things. Canonical player-history recovery
> improving predictive quality does **not** authorize betting.

---

## 7. Invariants — verified, not repeated

The full table with evidence types is in the JSON. The ones that changed on inspection:

### Invariant 1 — "standard and new-format never mix" → **PARTIALLY ENFORCED**

Routing is real (`src/predict.py:323-335`, separate masks, separate artifacts). But there are
**two fallbacks that score a non-standard fixture with the standard model**:

```python
# src/predict.py:332
nf_payload = payload_newformat if payload_newformat is not None else payload
#            ^ missing NF artifact → new-format fixtures scored by the STANDARD model

# src/predict.py:339-343
unknown_mask = ~std_mask & ~nf_mask
#            ^ a league in NEITHER list → scored by the STANDARD model
```

Do not restate this invariant as absolute.

### Invariant 3 — "v9 is frozen" → **RESTATED** (see §1)

### Invariant 9 — "write NaN, never invent a number" → **SPLIT**

Applies to **canonical storage**. Model preprocessing legitimately imputes at inference
(`src/model._prep`). These are two different policies and conflating them produces wrong
conclusions.

### Holding as stated

| # | invariant | evidence |
|---|---|---|
| 2 | player props paper-only | owner policy + no staking path exists |
| 4 | v11 never touches v9 | `CODE_ENFORCED` |
| 5 | prediction is pre-match only | `CODE_ENFORCED` — `predict.py:87` filters on `commence_time` |
| 7 | training-only leagues are not bet leagues | `CONFIG_ENFORCED` |
| 10 | `odds_history_v9.json` stays committed | `CODE_ENFORCED` — tracked at v9 **root**, not `output/` |
| 11 | canonical club resolution | `CODE_ENFORCED` |

---

## 8. Shared root — `DO_NOT_MOVE_OR_RENAME`

`v9/config.py` sets `DATA_DIR = BASE_DIR.parent`, i.e. the `mixed/` folder itself. Both v9 and
the legacy copy inside `v10/` read these by relative path.

Members include `England_Leagues_4_Seasons_With_Summary.xlsx` (local-only, never committed —
so **CI trains on less data than a local run**), `sofascore_cache.json`, `best_params.json`.

**Future product code must not reorganize the shared filesystem.**

---

## 9. Pro: tracked vs legacy — and a correction

`v10/.gitignore` is a **whitelist**: line 13 is `/*` (ignore every root entry), followed by `!`
re-admissions for `.github`, `README.md`, `docs`, `config`, `src`, `registry`, `experiments`,
`tests`, `data`, `models`, `output`.

Everything else on disk — `pipeline.py`, `app.py`, `retrain.py`, `telegram_bot/`,
`player_model/` — is **`LEGACY_IGNORED`**.

> **Correction.** A prior note claimed `git add -A` in `v10/` *"would swallow all of it"*. That
> is **false**. Those files are git-*ignored*, so `git add -A` skips them. Verified with
> `git check-ignore -v` and a `git add -An` dry run, which listed only Pro-tree files.
>
> The real residual risk is different: `git add -A` **would** stage generated experiment output
> under `experiments/` and `docs/`. Stage per file.

**Never mistake the legacy `app.py` or `pipeline.py` for current Wowza architecture.** They
ship nothing.

---

## 10. Research validity registry

Prevents future sessions quoting dead research.

| research | status | note |
|---|---|---|
| v11 momentum, **pre-fix** | **INVALIDATED** | `merge_asof` index reset; commits `929f783`, `4ed8aa9`. The quoted "0.995 / 0.753 / 0.711 vs 0.703" toward-rates are void. |
| v11 momentum, **post-fix** | **CURRENT** | Fixed `ba21c4c` (2026-09-10); artifacts regenerated `6d3d699` (2026-09-22). |
| calibration +13.64pp | CURRENT | Provenance found: `docs/audit_2026_09/AGENT_13_RED_TEAM.md:100`. `DOCUMENTED_ONLY`. |
| tier ladder carries no information | **EXPERIMENTAL** | Registered as evidence with a sample, **not** as a permanent invariant. |
| restored corners/HT features | CURRENT | Worth ±0.002 log loss. See below. |

### The post-fix v11 result reverses the pre-fix one

Current output is a regression, not a toward-rate. `residual_pp` is positive with a CI
excluding zero in **every** specification — residual-only 0.0153 (p=0.00, n=51,692), +momentum
0.0091, +full controls 0.0142 (p=0.00, n=29,846).

**This contradicts `docs/audit_2026_09/AGENT_11_PRO_BENCHMARK.md:29`**, which reports the
residual coefficient collapsing to +0.00089 (p=0.232) once price velocity is controlled. Two
artifacts disagree. Neither is dismissed here — it is logged as `CONTESTED`.

---

## 11. Known ambiguities — `UNKNOWN` is a valid result

| item | status |
|---|---|
| Which Telegram tips became real wagers | `OWNER_CONFIRMATION_REQUIRED` |
| Whether the deployed standard model is better in money terms | `UNKNOWN` — no fair OOS window yet |
| `pro_paper_1x2` sending module | `UNKNOWN` — secrets bound, module not traced |
| Invariant 8 (never bet without rolling form) | `UNVERIFIED_IN_THIS_PASS` |
| residual-vs-velocity conflict | `CONTESTED` |
| `output/af_ht_history.parquet` | `STALE` — last match 2026-06-23; written only by `backfill_ht_parallel.py`, which **no workflow runs** |
| Scottish League One / League Two | `LISTED_BUT_ABSENT` — in `STANDARD_FORMAT_LEAGUES`, present in no history file |

---

## 12. Training and promotion

- Gate lives in `v9/pipeline.py`; tolerance env `TRAIN_MAX_LOGLOSS_RISE`
- **Default at HEAD is `0.030`** (was `0.005`, changed in `a3207713`, 2026-09-24 08:26 UTC)
- **No workflow overrides it** — verified across all 22 v9 workflows
- Decisions recorded in `v9/output/retrain_log.json`, including `comparison_basis`:
  `same_holdout` is honest, `stored_metrics_FALLBACK` is a **weak comparison across different
  test sets**
- Known event: the 2026-09-24 08:22:54Z retrain **blocked** `model_v9_standard` for a
  +0.00533 rise against the then-deployed 0.00500 tolerance. The loosening landed four minutes
  later.

---

## 13. Product boundary — contract only, nothing built

```
V9 / approved Pro outputs  →  WOWZA PRODUCT PUBLISHER  →  Product DB  →  Wowza API  →  clients
```

The product is a **downstream consumer**. It must not:

- write into v9, Pro or v11
- move shared root files
- change thresholds, staking, collectors, Telegram behaviour or retraining
- import internal model code into a frontend

### Immutable prediction history

A changed probability is published as a **new snapshot**, never an overwrite:

```
snapshot A → snapshot B → snapshot C → kickoff → result
```

so users can see what Wowza actually predicted at the time.

---

## 14. Claim safety

Never convert:

| from | into |
|---|---|
| "AUC improved" | "profitable betting system" |
| "the player scorer model predicts better" | "player scorer bets have edge" |
| "a tip was sent" | "a bet was placed" |

Prediction quality, calibration, market residual, CLV, historical betting ROI and prospective
betting ROI are **six different things**.

---

## 15. AI change permissions

```json
{
  "v9":      "READ_ONLY_BY_DEFAULT",
  "pro":     "RESEARCH_CHANGES_ALLOWED_WITH_TESTS",
  "v11":     "EXPERIMENTAL_CHANGES_ALLOWED_WITH_TESTS",
  "product": "ISOLATED_DEVELOPMENT_ALLOWED"
}
```

> **v9 changes require explicit owner authorization.** No AI agent may infer authorization from
> a broad request such as *"improve Wowza"*, *"make the model better"* or *"build the app"*.
> Product work never implies permission to modify v9.

A genuine production-down emergency may be **reported** immediately. Fixing it is a separate
authorization.

---

## 16. Source-of-truth hierarchy

1. Current executable code
2. Current workflow configuration
3. Current machine-readable registry
4. Current generated health/manifests
5. Current documentation
6. Historical comments
7. Old architecture descriptions

**Caveat:** code proves *behaviour*. It does not prove owner *policy*. Fields labelled
`OWNER_POLICY` cannot be confirmed or refuted by reading code.

---

## 17. Keeping this honest

```bash
cd v10
python -m src.validation.validate_system_contract          # read-only
python -m src.validation.validate_system_contract --json   # machine-readable
```

It compares the recorded SHAs against current HEADs and reports `CONTRACT_STALE=YES/NO`. It
never writes, never fetches, never regenerates.

**A stale architecture document must never stop v9 from sending tips.** Staleness is a warning
and exits 0 by default; `--strict` is available for a reporting workflow, never for the predict
path.

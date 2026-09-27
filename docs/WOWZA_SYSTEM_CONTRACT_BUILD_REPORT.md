# System Contract — build report (v2.1.0)

*What was inspected at HEAD, what was found, what changed from v1, and what could not be proven.*

Generated 2026-09-27. Read-only mission: no running repository was modified by it.

---

## HEADs scanned

| repo | commit |
|---|---|
| `NevixAA/wowza-betting` (v9) | `cacee086d39723e85f1c244e6b4101ad2727a00b` |
| `NevixAA/wowzaV9-Pro` (Pro) | `9d986b1275552775500ab28704f59d927f0a7983` |
| `NevixAA/wowza_v11` (v11) | `6d3d69956fabf4f0645dd5f4b4ea642d4afcc05f` |

33 workflows (22 / 10 / 1) · 16 model artifacts (7 match, 9 player) · 3 Telegram send sites.

---

## What v2 corrects in v1

### 1. "V9 is frozen" was too strong, and dangerously so

v1 recorded `CHANGE_CONTROLLED` but never separated **routine model learning** from
**architectural change**. That leaves an agent free to read *"do not modify v9"* as *"stop v9
retraining"* — which would halt the thing that makes Wowza improve.

v2 splits them explicitly and confirms the learning loop is live: `output/retrain_log.json`
shows retrains on 09-24, 09-25 and 09-26, all on `basis=same_holdout`, with both promotions and
blocks occurring.

```
V9_CONTINUOUS_RETRAINING_ALLOWED   = YES
V9_ARCHITECTURE_CHANGE_CONTROLLED  = YES
V9_LITERAL_FREEZE_CORRECT          = NO
```

### 2. Tier stake semantics were understated

v1 described VALUABLE as "information only". The code says otherwise
(`src/betting.py:143-145`, `src/backtest.py:358`): SNIPER full stake, **MARKSMAN 3/4**,
**VALUABLE half stake / monitor**.

This does not change the real-money verdict — **no tier is staked by code, because no code
places a bet**. But the distinction matters, and per the brief nothing was modified to make the
code match the owner's policy sentence.

### 3. Threshold regimes were unrecorded

| | `config.py` (REFERENCE) | `predict.yml` (ACTIVE) |
|---|---|---|
| `MARKSMAN_THRESHOLD` | 0.14 | **0.08** |
| `VALUABLE_THRESHOLD` | 0.04 | **0.03** |
| `LEAGUE_SNIPER_CAP` | unset | **0.12** |

Historical performance must not pool regimes. A `threshold_regime_id` is **recommended, not
implemented** — no v9 change was made.

### 4. The rolling-form override was undocumented — and has expired

`REQUIRE_FORM_DATA=0` was set in `predict.yml` for early-season testing, time-boxed by
`REQUIRE_FORM_DATA_UNTIL=2026-09-15`. The code re-arms the guard **regardless of the env flag**
once that date passes (`src/betting.py:385-399`).

Evaluated 2026-09-27: `expired=True`, guard **ARMED**. Invariant 8 is live again. The override
happened, was deliberately bounded, and self-expired as designed — all three facts are recorded.

---

## Findings carried forward from v1, re-verified at HEAD

- **No automated bet placement exists** in any repo. The "betfair / smarkets / matchbook"
  matches are bookmaker name lists used to read prices.
- **"Pro never notifies" is false** — `pro_bet_builder.yml:94,110` and `pro_paper_1x2.yml:80-81`
  bind Telegram secrets; `pro_collect.yml` binds none.
- **Invariant 1 has two runtime fallbacks** (`predict.py:332`, `predict.py:339-343`) where a
  new-format or unknown-league fixture is scored by the **standard** model. Recorded as
  `DESIGN_SEPARATION=YES`, `STRICT_RUNTIME_ISOLATION=NO`.
- **Pro legacy files are `LEGACY_IGNORED`, not untracked.** `v10/.gitignore` is a whitelist, so
  `git add -A` skips them. v1's claim that it "would swallow all of it" was wrong.

---

## Newly verified at HEAD

**Player identity** — latest **club**, not every club. `player_model/predict.py:454-472`: sort
by date, `drop_duplicates(player_id, keep="last")` over club rows only. Internationals are
excluded because `team` there is the player's country.

**V11 market states** — `MIN_CLV_N = 150` at HEAD (`wowza-v11/config.py:22`), `NO_BET` is the
default (`src/edge_engine.py:154-156`).

**Leakage invariants** — `_rolling` is `x.shift(1).rolling(n)` grouped by team; no raw
same-match column appears in `FEATURE_COLS`; `train()` uses a chronological split.

**Canonical player research** — the brief quoted numbers; they were checked against the artifact
`output/shadow_learning/player_walkforward_performance.csv` (41 months, 123 rows) and match to
five decimals:

| variant | log loss | AUC | PR-AUC |
|---|---|---|---|
| canonical | 0.24697 | 0.76314 | 0.23423 |
| current | 0.25131 | 0.74745 | 0.22280 |
| frozen | 0.25525 | 0.73591 | 0.21295 |

Classified `PREDICTION_QUALITY_RESEARCH`, **not** `BETTING_EDGE`. It does not change
`real_money_enabled` for props. It also answers the learning question: **frozen is the worst
variant on all three metrics.**

**More rows ≠ better model** — the restored corners/HT families were worth 0.0005–0.002 log loss
across 7 monthly folds on the 7 standard bet leagues, against the 0.048 the retrain metrics
appeared to claim. The apparent AUC 0.534 → 0.709 was measured across two *different* test sets.

---

## Research validity

| research | status |
|---|---|
| v11 momentum pre-fix (`929f783`, `4ed8aa9`) | **INVALIDATED** — `merge_asof` index reset |
| v11 momentum post-fix (fixed `ba21c4c`, regenerated `6d3d699`) | **CURRENT** |
| canonical player history | **CURRENT**, `TEST_VERIFIED` |
| more match rows → better model | **CURRENT** — answer is no |
| calibration +13.64pp | **CURRENT**, `DOCUMENTED_ONLY` (`AGENT_13_RED_TEAM.md:100`) |
| tier ladder carries no information | **EXPERIMENTAL** — evidence, not architecture |

`ALL_V11_MOMENTUM_RESULTS = INVALID` is **not** encoded — corrected post-fix runs exist and are
current, and they *reverse* the pre-fix conclusion, which puts them in tension with
`AGENT_11_PRO_BENCHMARK.md:29`. Logged `CONTESTED` rather than resolved by fiat.

---

## Unverified / owner-confirmation-required

- which Telegram tips became actual wagers → `OWNER_CONFIRMATION_REQUIRED`
- the real-money scope claim → `OWNER_OPERATING_POLICY`
- whether the deployed model is better in money terms → `UNKNOWN`
- `pro_paper_1x2` sending module → `UNKNOWN`
- `output/af_ht_history.parquet` → `STALE`, written only by a script no workflow runs

---

## Tests and checks

| | result |
|---|---|
| `python -m pytest tests/` (from `v10/`) | **18 passed** |
| `python -m src.validation.validate_system_contract` | **0 errors, 0 warnings, `CONTRACT_STALE=NO`** |
| JSON Schema validation (Draft-07) | **passes** |

The validator gained three checks in v2 — continuous retraining allowed, architecture
change-controlled, literal-freeze rejected — so the central correction cannot silently regress.

---

## Added in 2.1.0 — the three registries 2.0.0 omitted

Re-checking 2.0.0 against the brief found three sections genuinely missing and the model
registry thinner than §13 asks. Filled:

| | |
|---|---|
| §57 workflow registry | **33 workflows** (22 v9 / 10 Pro / 1 v11) classified COLLECT · PREDICT · TRAIN · SETTLE · NOTIFY · RESEARCH · REPORT · HEALTH · MAINTENANCE, each with cron, timeout, secrets, Telegram flag, criticality and failure cost |
| §58 health registry | **11 artifacts**, each with producer, condition tested, failure meaning, and whether it blocks production — none do |
| §47 market data registry | **9 sources**, each with consumer, role, granularity, licensing |
| §13 model fields | 8 → **17** per model; player models gained all of theirs |
| §15 player props | `prediction_enabled` / `paper_enabled` / `notification_allowed` / `real_money_enabled` / `predictive_quality_claim` as separate fields |

### A correction the workflow registry surfaced

`retrain.yml` is `0 3 * * *` — **daily** until 2026-10-05, then automatically back to Sundays
only. CLAUDE.md says *"retrain Sunday 03:00"*, which is currently wrong. It is also the
explanation for retrains on 09-24, 09-25 and 09-26: a deliberate temporary regime, not drift.

### Two hard warnings now recorded in the market registry

**API-Football `/odds` is pre-match only.** Once a fixture finishes, its odds are gone — probed
3 fixtures per season 2019–2025 both with and without a bookmaker filter, 0 of 3 every time,
plus 770 consecutive empty fetches. Historical odds cannot be backfilled at any price, which is
why forward-capture cadence matters and why `scripts/backfill_af_odds.py` must not be run.

**`book_odds_snapshots.csv` is a change-log, not a panel.** Consecutive-distinct values only, so
at any single timestamp only the entities that just moved are present. Carry forward per entity
before aggregating; not doing so has produced three separate wrong conclusions.

---

## Files changed

```
v10/docs/WOWZA_SYSTEM_CONTRACT.md                 rewritten to the 19-section structure
v10/docs/WOWZA_SYSTEM_CONTRACT_BUILD_REPORT.md    this file
v10/registry/WOWZA_SYSTEM_CONTRACT.json           1.0.0 -> 2.0.0
v10/registry/WOWZA_SYSTEM_CONTRACT.schema.json    new enums + v9_change_policy required
v10/src/validation/validate_system_contract.py    3 new checks
```

No v9 file, no v11 file, no Pro production logic.

---

## Final verdict

```
SYSTEM_CONTRACT_BUILT=YES

V9_CURRENTLY_RUNNING=YES

V9_CONTINUOUS_RETRAINING_ALLOWED=YES
V9_CONTINUOUS_RETRAINING_CONFIRMED=YES
V9_ARCHITECTURE_CHANGE_CONTROLLED=YES
V9_LITERAL_FREEZE_CORRECT=NO

V9_TRAINING_PATH_MAPPED=YES
V9_RETRAINING_PATH_MAPPED=YES
V9_PROMOTION_GATE_MAPPED=YES

STANDARD_NEWFORMAT_DESIGN_SEPARATE=YES
STRICT_RUNTIME_TRACK_ISOLATION=NO

PLAYER_PROPS_PAPER_ONLY_VERIFIED=YES

SNIPER_STAKED_BY_CODE=NO
MARKSMAN_STAKED_BY_CODE=NO
VALUABLE_STAKED_BY_CODE=NO

ONLY_SNIPER_REAL_MONEY_CODE_ENFORCED=NO
OWNER_REAL_MONEY_POLICY_CONFIRMATION_REQUIRED=YES

PRO_CAN_NOTIFY=YES
PRO_COLLECT_CAN_NOTIFY=NO

V11_READS_V9_ONLY=YES
V11_WRITES_V9=NO
V11_CAN_STAKE=NO
V11_CAN_NOTIFY=NO

V11_PRE_FIX_MOMENTUM_INVALIDATED=YES
V11_POST_FIX_RESEARCH_IDENTIFIED=YES

SHARED_DATA_DIR_RISK_VERIFIED=YES

PRO_TRACKED_LEGACY_CLASSIFIED=YES

CALIBRATION_13_64PP_CLAIM_VERIFIED=YES
TIER_INFORMATION_CLAIM_VERIFIED=NO

PRODUCT_BOUNDARY_DEFINED=YES
PRODUCT_CAN_WRITE_V9=NO
PRODUCT_CAN_WRITE_PRO=NO
PRODUCT_CAN_WRITE_V11=NO

PRODUCT_SUPPORTS_MODEL_VERSION_EVOLUTION=YES

CONTRACT_VALIDATOR_BUILT=YES
CONTRACT_STALE=NO

PRO_TESTS_PASS=YES

V9_FILES_CHANGED=NO
V11_FILES_CHANGED=NO
PRO_PRODUCTION_LOGIC_CHANGED=NO

RUNNING_REPOS_SAFE_AFTER_MISSION=YES
```

### Fields deliberately not YES

**`V9_LITERAL_FREEZE_CORRECT=NO`** — required by the brief and correct: v9 retrains continuously.

**`STRICT_RUNTIME_TRACK_ISOLATION=NO`** — two real fallbacks exist. Recording YES would be false.

**`SNIPER/MARKSMAN/VALUABLE_STAKED_BY_CODE=NO`** — no code places a bet, so no tier is staked by
code. The tier→stake mapping produces a *recommendation*.

**`ONLY_SNIPER_REAL_MONEY_CODE_ENFORCED=NO`** — and hence
`OWNER_REAL_MONEY_POLICY_CONFIRMATION_REQUIRED=YES`.

**`TIER_INFORMATION_CLAIM_VERIFIED=NO`** — the claim is traceable to audit documents but was not
reproduced from a re-runnable artifact in this pass. Registered as `EXPERIMENTAL` evidence with
its sample, deliberately **not** promoted to an architectural invariant.

### Caveat on `CALIBRATION_13_64PP_CLAIM_VERIFIED=YES`

Means the **provenance was located** (`docs/audit_2026_09/AGENT_13_RED_TEAM.md:100`, corroborated
in `VERIFICATION_OF_AUDIT_CLAIMS.md:243-244`) — not that the calculation was re-executed. Its
evidence type is `DOCUMENTED_ONLY`.

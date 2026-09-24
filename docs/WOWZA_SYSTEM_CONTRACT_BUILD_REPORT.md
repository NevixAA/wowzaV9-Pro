# System Contract — build report

*What was inspected to produce [`WOWZA_SYSTEM_CONTRACT.md`](WOWZA_SYSTEM_CONTRACT.md) and
[`registry/WOWZA_SYSTEM_CONTRACT.json`](../registry/WOWZA_SYSTEM_CONTRACT.json), what was found,
and what could not be proven.*

Generated 2026-09-24. Read-only mission: no running repository was modified by it.

---

## Repos inspected

| repo | commit | state at inspection |
|---|---|---|
| `NevixAA/wowza-betting` (v9) | `6dc09e3115c21ac29545f988d99a55dd0ab60c1a` | 3 ahead / 2 behind origin |
| `NevixAA/wowzaV9-Pro` (Pro) | `4011587f68dac613c7f77f941a03d6ccc10041df` | clean, in sync |
| `NevixAA/wowza_v11` (v11) | `6d3d69956fabf4f0645dd5f4b4ea642d4afcc05f` | 8 ahead of origin |

Both divergences are **pre-existing** and were not created by this mission. v9's two extra
commits are authorized work from the same session (props collection fix; both-sides tip guard
plus a retrain hold). v11's eight unpushed commits predate the session entirely and were not
touched.

## Inventory

- **33 workflows** — v9 22, Pro 10, v11 1
- **16 model artifacts** — 7 match, 9 player
- **3 Telegram send sites** — `v9/telegram_bot/notifier.py`, `v10/src/combo/notify.py`, and a
  `LEGACY_IGNORED` copy at `v10/telegram_bot/notifier.py` that ships nothing
- **257 / 3,013 / 50** tracked files

---

## What the inspection changed about the accepted story

### 1. "v9 has been frozen since 2026-08-19" — not literally true

v9 received training-data expansion, club canonicalisation, promotion-gate changes and a
notifier fix in the three days before this contract was built, on top of continuous automated
commits. Recorded as `CHANGE_CONTROLLED`, not `IMMUTABLE`, with the freeze recorded as
`OWNER_POLICY`.

### 2. "Pro never notifies" — false

`pro_bet_builder.yml:94,110` and `pro_paper_1x2.yml:80-81` both bind `TELEGRAM_TOKEN` and
`TELEGRAM_CHAT_ID`. `pro_collect.yml` binds neither and says so at line 5 — but the same
comment also asserts *"NONE EXISTS IN THIS REPO"*, which is stale.

Accurate rule recorded: **Pro collection must never notify; explicitly authorized Pro
research/paper pipelines may.**

### 3. "`git add -A` in v10/ would swallow the legacy files" — false

`v10/.gitignore` is a whitelist (`/*` at line 13, then `!` re-admissions). `pipeline.py`,
`app.py`, `retrain.py`, `telegram_bot/notifier.py` and `player_model/pipeline.py` are all
**git-ignored**, verified with `git check-ignore -v`. A `git add -An` dry run listed only
Pro-tree files.

Classification corrected from `LEGACY_UNTRACKED` to `LEGACY_IGNORED`. The **real** residual
risk is different and is now recorded: `git add -A` *would* stage generated experiment output
under `experiments/` and `docs/`.

### 4. Invariant 1 has two real exceptions

"Standard and new-format never mix" is `PARTIALLY_ENFORCED`. Routing is genuine, but:

- `src/predict.py:332` — if the new-format artifact is missing, **new-format fixtures are
  scored by the standard model**
- `src/predict.py:339-343` — a league in neither list is **scored by the standard model**

### 5. The v11 `merge_asof` bug was fixed two weeks ago

Prior documentation still describes every momentum number as void. The fix landed in `ba21c4c`
(2026-09-10) and the artifacts were regenerated in `6d3d699` (2026-09-22), **after** it.

Pre-fix results (`929f783`, `4ed8aa9`) are recorded `INVALIDATED`; current artifacts are
recorded `CURRENT`. The post-fix output also **reverses** the pre-fix conclusion: `residual_pp`
is positive with a CI excluding zero in every specification, including full controls.

That sits in direct tension with `docs/audit_2026_09/AGENT_11_PRO_BENCHMARK.md:29`. Logged as
`CONTESTED`; neither artifact dismissed.

---

## Real-money path

**No automated bet placement exists in any repo.** Searched for `place_bet`, `place_order`,
`submit_bet`, exchange integrations. The only "betfair / smarkets / matchbook" matches are
bookmaker *name lists used to read prices*.

The code emits advisory output: tier, edge, and `kelly_pct` — *"recommended stake as % of
bankroll (25% Kelly)"* (`src/ledger.py:22`).

Consequently the claim *"real money is standard-format second-division O/U SNIPER only"* is
recorded as `OWNER_OPERATING_POLICY`, **not** a code-enforced invariant:

```
REAL_MONEY_SCOPE_CODE_VERIFIED           = NO
REAL_MONEY_SCOPE_OWNER_POLICY_REQUIRED   = YES
```

A Telegram notification is never assumed to be a wager.

---

## Unverified owner policies

- which tips became real wagers
- the real-money scope claim
- "no retrospective tuning"
- invariant 8 (never bet a fixture with no rolling form) — not verified in this pass

## Things found stale or absent

| item | finding |
|---|---|
| `output/af_ht_history.parquet` | last match 2026-06-23; written only by `backfill_ht_parallel.py`, which **no workflow runs**. Feeds HT grading, not prediction. |
| Scottish League One / Two | in `STANDARD_FORMAT_LEAGUES`, present in no history file |
| Pro test suite | 18 tests pass, but **no workflow executes them**, and `pytest` is not in `requirements.txt` |

---

## Placement decisions

The brief proposed `scripts/validate_system_contract.py`. **Pro has no tracked `scripts/`
directory** — its whitelist `.gitignore` would silently ignore anything placed there. The
validator lives at `src/validation/validate_system_contract.py` instead, beside the other
validators.

Contract artifacts went to Pro alone, as the brief preferred: one source of truth, in the
governance layer.

---

## Tests and checks run

| | result |
|---|---|
| `python -m pytest tests/` (from `v10/`) | **18 passed** |
| `python -m src.validation.validate_system_contract` | **27 checks, 0 errors, 0 warnings, `CONTRACT_STALE=NO`** |
| JSON Schema validation of the contract | **passes** (Draft-07, via `jsonschema`) |

`pytest` and `jsonschema` were installed into the local v9 virtualenv to run these. That
virtualenv is not committed; `requirements.txt` was not modified.

The validator earned its place immediately — its first run **caught a real schema violation in
the contract itself** (an `evidence` field carrying free text instead of an enum value), which
was then fixed.

---

## Files changed by this mission

```
v10/docs/WOWZA_SYSTEM_CONTRACT.md                     new
v10/docs/WOWZA_SYSTEM_CONTRACT_BUILD_REPORT.md        new
v10/registry/WOWZA_SYSTEM_CONTRACT.json               new
v10/registry/WOWZA_SYSTEM_CONTRACT.schema.json        new
v10/src/validation/validate_system_contract.py        new
```

No v9 file, no v11 file, and no Pro production logic was touched.

---

## Final verdict

```
SYSTEM_CONTRACT_BUILT=YES

V9_CURRENTLY_RUNNING=YES
V9_LITERAL_IMMUTABILITY_CONFIRMED=NO
V9_CHANGE_CONTROLLED=YES

PRO_ROLE_VERIFIED=YES
V11_SHADOW_ISOLATION_VERIFIED=YES

PLAYER_PROPS_PAPER_ONLY_VERIFIED=YES
REAL_MONEY_SCOPE_CODE_VERIFIED=NO
REAL_MONEY_SCOPE_OWNER_POLICY_REQUIRED=YES

PRO_CAN_NOTIFY=YES
PRO_COLLECT_CAN_NOTIFY=NO
V11_CAN_NOTIFY=NO

SHARED_DATA_DIR_RISK_VERIFIED=YES
TRACKED_VS_LEGACY_PRO_FILES_CLASSIFIED=YES

V11_PRE_FIX_MOMENTUM_RESULTS_INVALIDATED=YES
V11_POST_FIX_RESULTS_IDENTIFIED=YES

CALIBRATION_13_64PP_CLAIM_VERIFIED=YES

PRODUCT_BOUNDARY_DEFINED=YES
PRODUCT_CAN_WRITE_V9=NO
PRODUCT_CAN_WRITE_PRO=NO
PRODUCT_CAN_WRITE_V11=NO

CONTRACT_VALIDATOR_BUILT=YES
CONTRACT_STALE=NO

PRO_TESTS_PASS=YES

V9_FILES_CHANGED=NO
V11_FILES_CHANGED=NO
PRO_PRODUCTION_LOGIC_CHANGED=NO

RUNNING_REPOS_SAFE_AFTER_MISSION=YES
```

### Two fields deliberately not YES

**`V9_LITERAL_IMMUTABILITY_CONFIRMED=NO`** — this is the correct answer, not a failure. The
brief asked for it to be determined from the repository, and the repository says v9 is
change-controlled rather than immutable.

**`REAL_MONEY_SCOPE_CODE_VERIFIED=NO`** — also correct. No code stakes anything, so no code can
verify the scope of what is staked. That is precisely why
`REAL_MONEY_SCOPE_OWNER_POLICY_REQUIRED=YES`.

### Caveat on `CALIBRATION_13_64PP_CLAIM_VERIFIED=YES`

This means the **provenance was located** — `docs/audit_2026_09/AGENT_13_RED_TEAM.md:100`,
corroborated in `VERIFICATION_OF_AUDIT_CLAIMS.md:243-244` — not that the calculation was
re-executed in this pass. Its evidence type is `DOCUMENTED_ONLY`.

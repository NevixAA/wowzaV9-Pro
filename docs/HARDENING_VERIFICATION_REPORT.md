# Hardening brief — final verification report

Date: 2026-08-23 · v9 `822de193` · Pro `e35fac0` · v11 `5993ca8`

Answers the brief's section 17. Each item states what was verified and how, with the number that
proves it. Items I did **not** complete are named as such rather than reframed.

---

## 1. Romanian Superliga resolved

**Not a config bug.** Enumerated all 67 OddsAPI soccer competitions: no Romanian competition
exists at any tier under `romania / roman / liga_i / liga1 / superliga / super_liga / fcsb / cfr`
(the only "superliga" hit is Denmark). Declared in v9 `config.PROVIDER_UNSUPPORTED` with
`reason: NO_ODDSAPI_SPORT_KEY`, `provider: oddsapi`, `verified: 2026-08-22`, and kept in
`ENABLED_LEAGUES` deliberately. The audit now separates `CONFIG_BROKEN` (FAIL) from
`PROVIDER_UNSUPPORTED` (PASS + INFO), so an unfixable gap stops competing for attention with a
real one. **Verified:** audit `config` area, 3 checks passing; `pro_tests` asserts the
declaration carries both a reason and a verification date.

## 2. League coverage and sport-key validity

20 enabled leagues, 29 sport keys, all keys valid against OddsAPI, zero orphans.
**Verified:** `pro_tests` — "every enabled league has a sport key OR is declared unsupported".
That check FAILED first with 19 false positives because I guessed the attribute name
`SPORT_KEYS`; the real one is `ODDS_API_SPORT_KEYS`. Fixed.

## 3. Registry regenerates from canonical storage

`src/pipelines/registry.py` is the single writer. Counts always measured from parquet footer
metadata, never carried forward; if the store read fails it **raises and writes nothing**, because
a registry that can fall back to its own last value cannot distinguish "nothing changed" from
"the refresh failed". Non-count blocks may be inherited but are named in `carried_forward`.
Atomic write → read back → assert `total_rows` → `os.replace`.

Drift that prompted this, over four days: `market_snapshots` 51,638→74,740 (−31%),
`model_snapshots` 20,210→55,670 (−64%), `settlements` 24,114→43,555 (−45%), total 118,955→231,753
(−49%). **Verified:** wired to `pro_collect` on `steps.collect.outcome == 'success'`, and observed
firing unprompted in CI at 09:01 and 10:54 UTC.

## 4. Registry freshness and reconciliation in the audit

Tested **separately**, because this bug was invisible to either alone — the file was accurate for
the day it was written, and freshness cannot see wrong counts. Limit 30h (collect is 2-hourly, so
30h means ~15 consecutive misses). **Verified:** negative-tested on four synthetic cases — stale
timestamp (91.5h > 30h), fresh-but-wrong counts (freshness passes, reconciliation fails), absent
table, unparseable `generated_at`. Currently 12/12 tables reconcile, 0 mismatches.

## 5. `data_quality` populated

Held **0 rows from the day the store was created** — it had no writer. Now 12 findings, one per
(table, flag), with counts, affected date span, and sample keys.

| table | finding | rows | verdict |
|---|---|---|---|
| market_snapshots | BTTS_FIRST_HALF_MISLABEL | 1,167 | FAIL |
| market_snapshots | MISSING_OPPOSITE_SIDE | 4,726 | WARN |
| player_props | MISSING_OPPOSITE_SIDE | 12,082 (60.06%) | WARN |
| model_snapshots | MODEL_VERSION_UNKNOWN | 1,536 | WARN |
| movement_observations | INSUFFICIENT_BOOKS / MISSING_KICKOFF | 731 / 365 | WARN |
| fixtures, feature_snapshots | NOT_CLASSIFIED | — | WARN |

**Verified:** `12/12 tables populated`, and the audit's long-standing
`empty: ['data_quality']` warning is gone.

## 6. Quality taxonomy centralised

`src/quality.py`: **RAW** (everything — the only level that can measure contamination), **CLEAN**
(excludes rows whose value is wrong), **STRICT_CLEAN** (also excludes rows whose quality could not
be verified). 13 registered flags, each marked `wrong` or unverified. `at_level` requires the
level as an argument rather than defaulting. Documented in `docs/ARTIFACT_ROLES.md`.
**Verified:** 21 `pro_tests` checks, including that an *unknown* flag degrades to CLEAN rather
than to STRICT (a typo must reduce safety, not remove it).

## 7. CLV schema, raw preserved apart from clean

`src/market/clv_schema.py`. All brief fields present. **CLEAN coverage 32.6% → 73.0%** by
recovering 430 real closes from `player_props`; STRICT_CLEAN honestly held at 26.6%.
**Verified:** audit `clv schema` area; `pro_tests` asserts raw and clean are separate columns.

Three things I got wrong and fixed: the **unit trap** (`clv_records.csv` stores a FRACTION,
`bets_ledger.csv` a PERCENT, same column name — my ×100 produced a 100× error, and
`CLV_PLAUSIBLE_ABS=25` has therefore always been *inert* against `clv_records`); the **join**
(keyed on a `fixture_key` built from columns that file does not have — overlap 0 of 57); and
**conflating two meanings of `close == entry`** (a recovered close that genuinely did not move is
a measurement; a v9-sourced one is ambiguous, so it is marked unverified rather than asserted to
be fabrication).

## 8. Cross-repo health contract

`src/contract.py` declares 9 v9 artifacts with path, consumers, required columns, freshness,
**grain**, and caveat. Missing columns are FAIL, not WARN. **Verified:** audit `contract` area,
9/9 present, all required columns present, all within freshness limits. It caught two of my own
mis-declarations on the first run.

## 9. Snapshot density and near-kickoff coverage

`src/monitoring/snapshot_coverage.py`. Main O/U: median 41 snapshots per series, T-1h 71.4%,
T-30m 63.7%, T-10m 35.4%. Side markets: median **1**, T-10m **0.8%** — the standing finding, and
the likely reason CLV coverage is thin. Main market gated against regression; side markets
reported as INFO because a floor at an aspiration fires every run. **Verified:** negative-tested
across five degradation modes.

## 10. Atomic / failure-safe refresh

Implemented for the registry: temp file → read back → validate `total_rows` → `os.replace`
(atomic on NTFS and ext4). **Not generalised** to every writer — see item 17.

## 11. Deterministic tests

`python -m src.pro_tests` → **67 checks, all passing**, covering the brief's named list.
`python scripts/v11_tests.py` → **142 checks, all passing** (43 pre-existing + 68 movement +
31 results). Three bugs in my own test file, all found by running it: `sys.path.insert(0, v9)`
shadowed Pro's `config` package and killed three later groups; the wrong attribute name produced
19 false positives; and v11's modules cannot be imported inside Pro at all, so the close-selection
test runs as a subprocess in v11's own directory rather than reimplementing the function.

## 12. Weekly audit expanded

From 5 areas to **10**: `wiring`, `odds_curve`, `tips`, `collection`, `snapshot coverage`,
`contract`, `clv schema`, `movement research`, `registry`, `config`.
**Current: 28 PASS, 8 INFO, 1 WARN, 0 FAIL.** The remaining WARN is CLV coverage.

Also fixed a false alarm in my own audit: it FAILed `predictions.csv` at 08:01 UTC on a healthy
pipeline, then self-healed minutes later — a daily red flash that always cleared before anyone
looked. Only active hours inside the gap now count. Unit-tested at 8 points across the clock.

## 13. Four artifacts documented

`docs/ARTIFACT_ROLES.md` — what each answers, its grain and cadence, and **why it cannot be
merged into any of the others**.

## 14. Props sending wrong teams — FIXED

Víctor Muñoz (id 338751) resolved Osasuna → Liverpool. Cause: club came from the last
*appearance*, so a summer transfer stayed invisible until the player next played. Now resolved
from the live FPL squad, joined on `player_id`, falling back to appearance history.
**131 of 526 Premier League squad players (25%) were mislabelled**; 139 corrected across 7,232
history rows.

## 15. BTTS market — FIXED (data), hypothesis REFUTED (model)

**Data:** the capture parsers matched the bet *name* by substring, so bet 34 "Both Teams Score −
First Half" (Yes ≈5.50) overwrote bet 8 "Both Teams Score" (Yes ≈1.91). Fixed at all four sites.
I under-reported the damage at first by measuring only the standard file:

| file | contaminated btts_yes | |
|---|---|---|
| standard_sidemarket_odds_history.csv | 271 / 6,358 | 4.3% |
| newformat_odds_history.csv | **931 / 3,778** | **24.6%** |

A quarter of new-format BTTS training prices were first-half quotes. Both v9 read paths now
filter at 3.20 — a threshold inside a genuinely **empty** gap (clean 1.34–2.97, contaminated
3.40–7.00, zero observations between implied 0.31 and 0.33). No data deleted.

**Model:** the asymmetry hypothesis is **refuted**. 778 labelled rows, chronological split, 156
test rows, scored against the BTTS base rate: base-rate constant Brier 0.24445 (best), volume
0.25272, volume+`lam_min` 0.25294, volume+all asymmetry 0.26545. Difference CI
[−0.02500, −0.00008] — asymmetry *hurts*. Per-feature AUC explains why: `p_btts_dc` 0.5032,
`lam_min` **0.4898** (below chance), while the best discriminator is a volume feature at 0.5600.
The physics is right (`dc_p_btts(1.25,1.25)=0.519` vs `(2.30,0.20)=0.166`) but the **lambdas carry
no per-team signal**. The real bottleneck is upstream: per-team scoring-rate estimation. Nothing
shipped. Calibration bias −6.4 to −7.5pp, so **BTTS-NO stays disabled**.

## 16. BTTS tips flowing

`src/btts_odds.py` fetches per-event BTTS via OddsAPI; `SIDE_MARKET_LABELS["btts"] = "BTTS — YES"`
so the side is named. 16 tips produced on the live run.

## 17. What I did NOT do

Stated plainly rather than reframed:

- **Generalised atomic refresh.** Only the registry writes atomically. Other writers were left
  alone.
- **The BTTS model upgrade itself.** Diagnosed and the proposed fix refuted; the productive next
  step (better per-team lambdas — opponent-adjusted, longer windows, shrunk to the league mean)
  is a larger piece of work and should not start on 156 test rows.
- **Two verifications I cannot perform here.** The live-scanner fix needs one real Actions run to
  confirm (`gh` is unauthenticated in this environment), and the football-data grading has never
  executed because this network blocks `football-data.co.uk` outright — connection refused, not a
  certificate error. Logic is unit-tested and the failure path degrades to "nothing newly graded"
  with every unavailable league named, never to wrong results.
- **`fixtures` and `feature_snapshots` remain unclassifiable** — no `quality_flags` column. Their
  writers need flagging added; reported as `NOT_CLASSIFIED` rather than silently counted as clean.

## Standing state

```
canonical tables      12/12 populated, 269,383 rows
weekly audit          28 PASS, 8 INFO, 1 WARN, 0 FAIL
Pro tests             67 checks passing
v11 tests            142 checks passing
open WARN             CLV coverage (the honest residual)
```

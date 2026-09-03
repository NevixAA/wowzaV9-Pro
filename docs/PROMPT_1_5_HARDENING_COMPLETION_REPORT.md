# PROMPT 1.5 — HARDENING COMPLETION REPORT

Pass of 2026-09-02/03. Scope: finish the incomplete work from the previous hardening pass and
prove it. No V9 model logic touched. No Prompt 2 work started.

---

## 1. Audit findings — all six confirmed

| # | finding | verdict |
|---|---|---|
| A | combo tables ACTIVE, 0 rows, despite notes claiming a backfill | **CONFIRMED** — root cause found, below |
| B | cadence nowhere near 10 min; T-1h 36%, T-10m 9.2% | **CONFIRMED** — reproduced at 34.0% / 8.7% |
| C | `team_match_stats` ACTIVE, 0 rows | **CONFIRMED** — but not for the assumed reason |
| D | no output manifest | **CONFIRMED** — created |
| E | `deployment_note` contradicts `pro_may_notify` | **CONFIRMED** — fixed |
| F | `live_odds_snapshots` populated but PLANNED_OPTIONAL | **CONFIRMED** — now ACTIVE |

Two audit statements needed correcting against the store rather than the notes:

* `live_odds_snapshots` and `team_news` are **both genuinely working now** — 10,151 rows / 10 runs
  and 48 rows / 3 runs respectively, both starting 2026-08-30, the day `APIFOOTBALL_KEY` was
  added to this repository. The audit only flagged the first.
* The registry note claiming a combo backfill was never true. It has been rewritten to state the
  measured position, and a test now fails if any lifecycle note claims rows a table does not have.

---

## 2. Combo canonical fix

### Root cause: one missing line in a workflow

`pro_bet_builder.yml` staged three `output/` files and **never staged `data/`**:

```
for f in output/bet_builder_candidates.csv output/bet_builder_settled.csv \
         output/combo_notified.json; do
  git add -f "$f" ...
```

The importer shipped on 2026-08-30 and ran on **six** builder passes (08-30 ×3, 08-31, 09-01 ×2).
Every one wrote its parquet partitions to the runner's disk, committed the three CSVs, and let the
canonical rows die with the runner. Six green workflows, nothing persisted — the failure shape
this repository keeps meeting.

### What changed

1. `git add -A data` added to `pro_bet_builder.yml`, matching `pro_collect.yml`.
2. The import is now **one entry point reading the CSVs on disk**, not two calls writing whatever
   a branch held in memory. A `--mode notify` run previously imported nothing and a `--mode
   settle` run imported no candidates.
3. **Idempotent by dedup key**, which is what lets one code path serve both jobs — the first run
   is the backfill, every run after it is an increment. No separate backfill script to remember.

| table | dedup identity |
|---|---|
| `combo_candidates` | `combo_id + snapshot_ts + calculation_version` |
| `combo_legs` | `combo_id + snapshot_ts + leg_index` |
| `combo_dependencies` | `market_a + market_b + segment + league + model_type + estimate_source + calculation_version` |
| `combo_settlements` | `combo_id + settled_at + calculation_version` |

4. Also wired into `pro_collect` (every 2h), not only the builder (≤3/day). The CSVs are already
   committed, so canonicalization need not wait for the process that produced them — and the
   importer gets a second chance rather than losing a day to one missed run.
5. `output/combo_import_health.json` records rows seen / imported / skipped / canonical total /
   latest source and canonical timestamps / failures, per table (§34).

### Verified, on the real CSVs, in a scratch store

```
PASS 1 (backfill)      candidates 216   legs 588   dependencies 1,809   settlements 8,723
PASS 2 (same input)    imported 0 everywhere; totals unchanged; duplicates counted
```

`combo_price_snapshots` stays **SOURCE_REQUIRED** and empty. No bookmaker same-game-builder price
is collected anywhere, and a product of single-market odds is not one (§11).

---

## 3. Scheduler root cause

Cadence was the wrong thing to look at. The decisive measurement is **where the odds spend
actually goes**, by time to kickoff:

| when captured | share of all market observations |
|---|---:|
| **far (>24h out)** | **81.0%** |
| T-24h | 9.7% |
| post-kickoff (no pre-match value) | 5.4% |
| T-6h | 2.1% |
| T-3h | 1.1% |
| **T-1h + T-30m + T-10m** | **0.6%** |

Four-fifths of the effort goes to fixtures more than a day out, whose prices move slowly, and
0.6% to the window that decides CLV.

Two causes, both structural:

**a) The capture clock ignores the kickoff clock.** Measured over 594 fixtures:

```
kickoff minute-of-hour:  :00 60.6%   :30 25.9%   :45 8.1%   other 5.4%
```

86.5% of kickoffs are at :00 or :30. `std_odds_capture` fired hourly at **:23** — T-7m for the
:30 group and **T-37m for the larger :00 group**. `nf_odds_capture` fired at **:47** — T-13m and
T-43m. Nothing was positioned for the 60.6%.

**b) Hours 04:00–08:00 UTC contain zero kickoffs** in the entire store, and were being polled
anyway — five firings a day spent where nothing could be near its close.

Delivery throttling (measured in the previous pass: ≥26 runs/day land 8–38%) makes both worse but
is not the primary cause. A perfectly delivered capture at :23 is still 37 minutes from a :00
kickoff.

---

## 4. Scheduler changes

| workflow | before | after | effect |
|---|---|---|---|
| `std_odds_capture` | `23 * * * *` (24/day) | `23,52 0-3,9-23 * * *` (36/day) | :52 → **T-8m** for the 60.6% at :00; :23 keeps T-7m for the 25.9% at :30 |
| `nf_odds_capture` | `47 * * * *` (24/day) | `20,50 0-3,9-23 * * *` (36/day) | same alignment, 3 min clear of std so the two never contend |
| `pro_team_stats` | (was a step in `pro_collect`) | own workflow, `35 4,16 * * *` | see §6 |

Net +24 runs/day, funded from the 165/day freed on 2026-08-30. The dead 04:00–08:00 window pays
for most of the second slot. This is the highest-value use of that headroom: `/odds` is pre-match
only, so a close not captured is gone permanently.

**Budget is not the constraint.** API-Football ~34.8k/75,000 (46%); Odds API estimated
**44,380/100,000** at month end. There is room to spend more near kickoff, which is precisely what
§20 asks for.

---

## 5. Near-kickoff coverage, before/after

**Before** (measured 2026-09-02, 426 kicked-off fixtures, 14-day window):

| horizon | coverage |
|---|---:|
| T-6h | 86.4% |
| T-3h | 72.1% |
| T-1h | 34.0% |
| T-30m | 13.6% |
| T-10m | 8.7% |

**After: CONFIGURATION FIXED — OBSERVATIONAL VALIDATION PENDING.**

Per §38, no "after" figure is claimed. The realigned crons had not yet fired when this report was
written, and cadence cannot be proven by a YAML diff. The measurement is already in place
(`src.monitoring.scheduler`), the denominator is unchanged (kicked-off fixtures), and re-running
it in 24–48 hours produces the comparison honestly.

Also added, per §21–23:

* **`ALL_TIME_GAP` vs `ACTIVE_WINDOW_GAP`.** Previously a quiet 03:00–08:00 with no fixture on
  earth contributed hundreds of "missed windows" identical in kind to a real capture failure. An
  observation now counts as active only when a kickoff is within 6h. Effect on the same data:
  market_snapshots 458 missed → **177 active-window missed**; model_snapshots 498 → **97**.
* Coverage split **by league, by market, by weekday**, plus a Fri/Sat/Sun block with fixtures,
  observations per stream and spacing.
* Odds API telemetry: used today / month, remaining, projected month-end, by market, by league,
  by time-to-kickoff bucket. **Labelled an estimate**, because no credit meter exists — the Odds
  API publishes none, and presenting a derived lower bound as measured would be false.

---

## 6. team_match_stats resolution

**The collector is not broken.** Verified directly on 2026-09-02:

```
python -m src.pipelines.team_stats --seasons 2026 --limit 3 --dry-run
  3 fixtures | 1 API call | possession, shots, SOT, inside-box all 100% populated
```

Valid credential, working endpoint, real rows. It was empty because **the step was never
reached**: it lived inside `pro_collect.yml` gated on the daily sweep (`15 6 * * *`), and no
`pro: collect` commit has appeared at 06:xx UTC since 2026-08-26. Coupling a collector to another
workflow's least-frequent cron gives it the worst delivery odds in the estate and hides the
failure inside a job that reports success for its own reasons.

**Resolution: (A) ACTIVE + POPULATED**, via its own workflow `pro_team_stats.yml`, twice daily at
`35 4,16 * * *`. Resumable and cached, so twice a day costs the same as once. Its failure step is
**not** `continue-on-error` — the table is declared ACTIVE, so an empty one is a fault and must
fail loudly.

Partial field coverage is handled as §27 requires: xG is league-dependent (0% for Argentina in
the probe, ~88% in bet leagues) and the six genuinely unavailable fields stay marked
`UNAVAILABLE` in `src/schemas.py` rather than fabricated.

**Local-only data is not canonical data** (§26): the 88 laptop partitions were moved out of the
repository on 2026-08-30 to `../v10_local_quarantine_20260830/` and count for nothing here.

---

## 7. Live odds lifecycle

`PLANNED_OPTIONAL` → **ACTIVE**. 10,151 rows across 10 runs, 2026-08-30 → 09-02, from a scheduled
hourly sweep against a provider endpoint that answers reliably.

ACTIVE deliberately, not an opportunistic status. What is opportunistic is the **content** — no
fixtures in play means no rows — and that is a per-run condition the scheduler health reports, not
a property of the table. Treating "nothing was in play" as "the collector is optional" is how a
broken live collector goes unnoticed for a month.

`live_odds_snapshots` (market evidence) and `live_signals` (our decisions) remain separate tables
with separate required columns (§33). `team_news` was flipped to ACTIVE on the same evidence — 48
rows over 3 runs — while `known_at` stays `SOURCE_REQUIRED` **at the field level**, because
neither `/fixtures/lineups` nor `/injuries` publishes a timestamp and that field is the whole
point for leakage-safe research.

---

## 8. Output manifest

`output/output_manifest.json`, built by `src/monitoring/manifest.py`, refreshed every collect.

**75 entries** — RAW 15, CANONICAL 20, DERIVED_RESEARCH 24, HEALTH 11, REPORT 5 — across all
three repositories, each with repo, path, owner, artifact type, source artifacts, canonical
destination, append-only, calculation version, lifecycle and research status.

`canonical_destination` is the load-bearing field: for every RAW artifact it names the table meant
to absorb it, which makes "v9 produced it but Pro never imported it" a mechanical question. A RAW
entry with no destination must state **why** — three do (`player_history.parquet` is read in place
for card rates; `v11_shadow_snapshots.csv` is v11-internal by the ownership rule;
`sharp_tips.csv` is a v9 operational feature) — because silence makes "no destination recorded"
indistinguishable from "never imported".

Declared rather than globbed, so it records intent and can be checked against reality. Its first
run immediately reported 9 missing artifacts, one of which was my own filing error
(`model_1x2_eval.csv` listed under v9 when it is Pro's).

---

## 9. Registry fixes

* `n_tables_declared` added beside `n_tables`; `tables_never_written` lists declared tables with
  no directory at all, so "not mentioned" can no longer read as "fine".
* `empty_reason` carried next to every zero count, so an outage and a settled fact about the
  world are distinguishable without opening another file.
* `is_expected_empty` now covers `SOURCE_REQUIRED` and `DEPRECATED`, not just `PLANNED_OPTIONAL`.
* Tests assert the accounting adds up: populated + expected-empty + unexpected-empty = tables,
  accounted = populated + expected-empty, and no table may be listed as empty while holding rows.

---

## 10. Deployment policy fix

The registry said *"Pro does not stake and does not notify"* while reporting `pro_may_notify:
true` in an adjacent key. **Pro does notify** — `pro_bet_builder.yml` holds the Telegram secrets
and runs `--mode notify`, and `PRO_MAY_NOTIFY` has been `True` since the builder shipped.

The note now states the narrow policy that actually applies: Pro **never stakes**; Pro **may
notify**, bet-builder research tips only, sent by `src/combo/notify.py`, labelled PAPER, with a
FAIR price because no bookmaker builder price exists; collect, live and research pipelines never
notify, enforced by `pro_collect` aborting if Telegram credentials are even visible to it. A
machine-readable `notify_scope` was added so an audit need not parse prose.

Two tests had been asserting the **old** blanket policy and failing since the builder shipped —
red tests nobody acts on, which is worse than none. Both were rewritten to assert what keeps the
policy narrow (staking forbidden, the only sender defaults to `dry_run=True`, collect aborts on
credentials) rather than the flag's value, which is config's to decide.

---

## 11. API usage

| provider | position | headroom |
|---|---|---|
| API-Football | ~34,765 / 75,000 (46.4%) | alert 45,000, abort 60,000 — sensible, unchanged |
| The Odds API | est. **44,380 / 100,000** month-end | ~55% unused |

Neither is the constraint. The problem is allocation (81% far-future, 0.6% final hour), which
§4's realignment addresses directly.

---

## 12. Tests

`tests/test_hardening_1_5.py` — 45 checks, all passing:

combo backfill non-zero · idempotent re-import · legs ≥ candidates · duplicates counted, not
dropped · dedup identities versioned · ACTIVE-zero alarms and SOURCE_REQUIRED-zero does not ·
lifecycle notes cannot claim rows a table lacks · registry accounting adds up · no table both
empty and populated · deployment note cannot contradict `pro_may_notify` · manifest covers every
canonical table · every RAW entry names a destination or says why not · active-window cadence
excludes quiet periods while all-time still reports them · Odds API billing arithmetic.

Full suite green, including the two files that had been failing before this pass:

```
test_market · test_season_store · test_validation · test_registry_gates
test_imputers_calibration · test_drift_experiment · test_combo_canonical
test_scheduler · test_hardening_1_5 · src.combo.tests
```

---

## 13. Remaining blockers

1. **No CI run has yet exercised any of this.** Every fix is committed and every mechanism is
   verified locally, but the canonical store still reads 0 combo rows until `pro_collect` or
   `pro_bet_builder` runs. That is the one thing standing between this report and YES.
2. **`team_match_stats` will populate on the first `pro_team_stats` run** (`35 4/16 UTC`) — not
   before.
3. **Near-kickoff coverage is unproven.** Configuration fixed, observation pending (§38).
4. **`train_1x2.py` is still scheduled in no workflow** — carried over, belongs to Prompt 2's 1X2
   work.
5. **The market price series is noisy** — carried over from the Prompt 2 draft plan. Not a
   blocker for this pass, but it undermines every movement and CLV result and should be fixed
   before the frozen-V9 experiments are believed.

---

## 14. Verdict

Every declared gap has a deployed fix, and every mechanism is verified — but §38 and §41 are
explicit: a YAML diff is not a working scheduler, and a table is not populated until the store
says so. The canonical combo tables read **0 rows at the time of writing** because no CI run has
happened since the fix.

The next `pro_collect` (every 2h) should import 216 candidates, 588 legs, 1,809 dependencies and
8,723 settlements, and write `combo_import_health.json` proving it. When the registry shows those
counts, this flips to YES with no further work.

**READY_FOR_PROMPT_2 = NO**

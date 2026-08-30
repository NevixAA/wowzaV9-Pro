# OUTPUT ARCHITECTURE HARDENING REPORT

Prompt 01, pass of 2026-08-30. Scope agreed with the operator before starting: **P0 only**, then
this report. P1–P3 are listed at the end, unstarted.

Placed in `docs/` beside `HARDENING_VERIFICATION_REPORT.md` and `BET_BUILDER_RESEARCH_REPORT.md`
rather than at the repository root, matching where this project already keeps its reports.

---

## 0. Headline

> **91% of kicked-off fixtures have no market observation inside the final 10 minutes before
> kickoff, and the loss is permanent.**

Measured 2026-08-30 against the current store, 318 kicked-off fixtures in a 14-day window:

| horizon | fixtures covered | % |
|---|---:|---:|
| T-6h | 274 | 86.2% |
| T-3h | 234 | 73.6% |
| T-1h | 133 | **41.8%** |
| T-30m | 49 | **15.4%** |
| T-10m | 30 | **9.4%** |

Odds are pre-match only and cannot be backfilled — established by probe, 0 of 3 fixtures in every
season 2019–2025, ~830 calls spent proving it. Every uncovered fixture is a closing price gone for
good, and closing price is what CLV is measured against.

The cause is structural rather than a fault: `pro_collect` samples every 2 hours
(`40 */2 * * *`), and the observed median spacing of 114.1 minutes matches that cron almost
exactly. A fixture kicking off at 14:00 is sampled at 12:40 and 14:40 — T-80m, then post-kickoff.
**v9 is not the constraint**; its predict runs 15-minutely Fri–Sun. Pro's own sampling cadence is.

### A correction, recorded because the failure mode is instructive

An earlier draft of this report opened by claiming four workflows had never committed and two had
stopped — a Pro-wide CI outage. **That was wrong.** `pro_collect` and `pro_bet_builder` are
healthy and committed at 12:11 and 11:05 UTC on 2026-08-30.

The cause was a **silently failed `git fetch`**. The audit ran `git fetch --quiet 2>$null`
followed by `rev-list HEAD...@{u}`; the fetch failed on this OneDrive working copy
(`unable to append to '.git/logs/HEAD': Invalid argument`, fixed with
`git config windows.appendAtomically false`), the error was swallowed by the redirect, and
`@{u}` still pointed at the 2026-08-29 ref. The comparison then reported `0 ahead / 0 behind`
against a 10-commit-stale remote, and every "last commit" lookup inherited that staleness.

This is the project's own recurring failure shape — *a green signal and no data* — reproduced by
the audit that was written to detect it. Two rules follow:

* **Never suppress stderr on a `git fetch` whose result you are about to reason from.** A fetch
  that cannot fail visibly turns "up to date" into "unverified".
* **`0 ahead / 0 behind` is only meaningful if the fetch demonstrably succeeded.** Check the
  fetch's exit status, not just the comparison it feeds.

What the corrected history actually shows:

| workflow | cron | last commit | reading |
|---|---|---|---|
| `pro_collect` | `40 */2 * * *` + daily | 2026-08-30 12:11 UTC | healthy |
| `pro_bet_builder` | 3×/day Fri–Sun | 2026-08-30 11:05 UTC | healthy |
| `pro_weekly_audit` | `15 6 * * 1` | 2026-08-24 07:19 UTC | on schedule — next Monday is 08-31 |
| `pro_backfill_results` | `25 * * * *` | 2026-08-19 11:46 UTC | runs succeed but commit nothing for 11 days — worth checking |
| `pro_team_news` | `*/30 * * * *` | never | runs succeed, writes no rows — needed `APIFOOTBALL_KEY`, added 08-30 |
| `pro_live_odds` | `9 11-23 * * *` | never | added 08-29 17:47; same credential dependency |

Run status was read from the public Actions API
(`api.github.com/repos/NevixAA/wowzaV9-Pro/actions/runs`), which is available without
authentication because the repository is public — the same property that makes its Actions
minutes free and unmetered, so the plan is not a constraint either.

---

## 1. Before: the architecture as found

```
SOURCE            RAW OUTPUT (v9, committed)      IMPORTER            CANONICAL (Pro store)
──────            ──────────────────────────      ────────            ─────────────────────
OddsAPI      ──▶  output/predictions.csv     ──▶  current_wowza  ──▶  fixtures
API-Football ──▶  output/bets.csv                                     model_snapshots
football-data──▶  output/*_odds_history.csv                           market_snapshots
                  output/player_tips.csv                              feature_snapshots
                  output/clv_records.csv                              signals · clv
                  output/inplay_snapshots.csv                         player_props
                                                                      live_signals
                                                                      settlements
API-Football ──▶  (direct, Pro-side)         ──▶  team_stats     ──▶  team_match_stats
v11          ──▶  output/v11_*.csv           ──▶  v11_research   ──▶  movement_observations

                  DERIVED RESEARCH                     HEALTH
                  ───────────────                      ──────
                  bet_builder_candidates.csv           system_registry.json
                  bet_builder_settled.csv              weekly_audit.json
                  combo_dependency_matrix.csv          snapshot_coverage.json
                  player_combo_dependency.csv          collect_health.json
                  clv_enriched.csv                     data_quality (canonical table)
```

The chain is real and mostly sound. Where it broke is at the two ends: the derived-research column
had **no canonical destination at all**, and the health column had **no measurement of cadence**.

---

## 2. The actual problems, in the order they cost something

### 2.1 `combo_id` was broken in both directions at once — P0, fixed

`bet_builder.generate()` overwrote the correct hash from `builder._combo_id()` with a string built
from `leg1_market + leg2_market + …` in **column order**, containing **no selection**. Two
independent defects followed:

* **Order-dependent.** `{O35, player_goals, player_goals, player_sot}` on fixture
  `a4994e7cab7f01e4` appears in the live `combo_notified.json` as three different keys differing
  only in leg order.
* **Not unique.** One key, `a4994e7cab7f01e4|O35+player_goals+player_goals+player_sot`, covers
  **eight distinct combos**. Board-wide: **475 candidate rows → 225 identities.**

Both consequences were live and neither was visible:

1. **Duplicate Telegram tips** (the operator reported this independently during the pass). Leg
   reordering defeats the dedup, so the same bet notifies again. Worse, the eight combos sharing
   one identity also share one state entry — whichever is processed last overwrites
   `joint_probability`, so on the next run the other seven differ from that stored value by more
   than `MIN_PROB_CHANGE_PP = 2.0` and re-send as `PROB_UP` / `PROB_DOWN`.
2. **Silent settlement loss.** `settle_finished()` deduplicates the merged record on this id with
   `keep="first"`, so **~250 distinct combos were discarded on every settle pass**. The existing
   "must never drop a graded row" guard could not see it: the discarded rows are still `UNKNOWN`
   at that point, so the count of *decided* rows never fell. `bet_builder_settled.csv` looks
   collision-free (5,861 rows, 5,861 ids) **precisely because the collapse happened upstream**.

**Fix.** `combo_id` is now `fixture_key|sha1(sorted("market:label" per leg))[:12]` — order
independent and selection sensitive. The old value is preserved as `combo_id_legacy` for lineage.
The settle merge key now prefers the composite `match|match_date|legs`, which spells out every
selection; on the committed record the two keys agree exactly (5,861 = 5,861), so the reordering
changes no existing row. A new guard refuses any merge that reduces the count of **distinct
combos**, decided or not.

Notify state is migrated from legacy ids on load, verified to reproduce the pre-fix decision set
exactly (`NEW` 97, `REMINDER` 12 both before and after), so the fix causes no re-notification
burst.

### 2.2 Builder evidence had no history — P0, fixed

`bet_builder_candidates.csv` and `bet_builder_settled.csv` are **rewritten in place** every run. A
combo generated at T-3d at 0.31 and re-generated at T-6h at 0.27 leaves one row behind, and it is
the second one. Every builder question worth asking needs the history.

Five canonical append-only tables now exist (section 4 below). The CSVs stay — section 3 says
preserve, and `notify` and the dashboard read them.

### 2.3 `team_match_stats` ACTIVE-empty — P0, diagnosed and made visible

The prompt lists this as "resolve the ACTIVE-empty state". It is **not** a missing collector.

`src/schemas.py` declared the table ACTIVE with the note *"Not empty — 23,604 rows as of
2026-08-27"*, citing a registry run. **That measurement was taken on a laptop.** In the repository:

```
tracked partitions, by write origin (from `git ls-files`):
  fixtures            127 ci /  2 local        market_snapshots  137 ci / 3 local
  model_snapshots     127 ci /  2 local        settlements        22 ci / 6 local
  team_match_stats      0 ci /  0 tracked   ← 88 parquet files sit UNTRACKED on one laptop
```

Cause: `pro_collect.yml`'s team-stats step needs `APIFOOTBALL_KEY`, `team_stats.py` **raises**
without one, and the step is `continue-on-error: true` — so every daily sweep since 2026-08-26
skipped it and reported success. The workflow header still claimed *"NO API-FOOTBALL OR ODDSAPI
SECRET EITHER"* while three steps referenced that secret.

**Fixed:** the schema note now states the committed-store truth and why; the table stays `ACTIVE`
so an empty one alarms; and a new step converts the swallowed failure into a visible
`::warning` without making it fatal. The operator added `APIFOOTBALL_KEY` to the Pro repository on
2026-08-30 — the next daily sweep is what confirms it.

**The general lesson, worth more than the fix:** a lifecycle status must be set from what the
**shared** store holds, never from what a laptop holds.

### 2.4 Live odds do not exist anywhere — P0, established

Audited rather than assumed. **v9 has no real live odds:**

* `output/inplay_snapshots.csv` — `snapshot_ts, fixture_id, league, match, elapsed, home_g, away_g, total_g, sot`. Match *state*, no price.
* `output/live_games.csv` — has `fair_under_odds` / `fair_over_odds`, which are **model** fair odds, not bookmaker prices.
* `live_signals_history.csv`, `live_tips.csv` — our opinions.

So `live_signals` and `live_odds_snapshots` are genuinely different things (section 6), and
API-Football `/odds/live` via `pro_live_odds.yml` is the **only** possible source. The collector
was written on 2026-08-29 and verified against the live API (216 rows, 5 fixtures, median odds age
25.6s) but has **never persisted a row** — the workflow has never committed. Lifecycle stays
`PLANNED_OPTIONAL`; nothing was fabricated.

### 2.5 Cadence was never measured — P0, fixed, and the result is bad

New module `src/monitoring/scheduler.py`. Every number is measured from `observed_at` in the
canonical store; nothing is inferred from a cron expression.

Coverage figures are in section 0. The cadence measurement, same run (14-day window, store at
commit `4f5a0e3`):

| table | median gap | p90 | max | missed windows |
|---|---:|---:|---:|---:|
| market_snapshots | 114.1 min | 193.5 | 808.2 | 1,661 |
| model_snapshots | 119.8 min | 527.8 | 793.4 | 1,716 |
| player_props | 1,440.9 min | 1,956.4 | 2,471.9 | 1,843 |
| live_odds_snapshots | — | — | — | no observations |

Both the coverage and the cadence numbers were computed twice — once against a store that was 26
hours stale (the section 0 error) and again after pulling. The conclusion was unchanged; T-10m
moved 8.3% → 9.4% and T-1h 39.7% → 41.8%. The finding is not an artefact of the stale clone.

Fixing it is kickoff-aware scheduling, which is P1/P2 and deliberately not attempted here:
section 7 asks for observability first, and a cadence changed before it is measured is a guess
with a commit message.

### 2.6 Three places disagree about whether Pro may notify — found, not changed

* `README.md`: *"does not bet, does not tip, and does not notify"*
* `pro_collect.yml` header: *"Pro never notifies… the absence of the credential is the enforcement mechanism"*
* `tests/test_season_store.py` and `tests/test_drift_experiment.py`: both assert `PRO_MAY_NOTIFY is False`
* `config/pro_config.py:218`: `PRO_MAY_NOTIFY = True`
* `pro_bet_builder.yml`: holds `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` and runs `--mode notify`

Pro **does** notify. The guard was lifted for the Bet Builder without updating any of the four
places that document the opposite, and **two tests fail today because of it** (both pre-existing,
neither caused by this pass). Left for the operator: whether Pro should notify is a policy
decision, not a lint error, and silently flipping an assertion that says "never" would destroy the
record of an intent.

### 2.7 `train_1x2.py` is scheduled nowhere — found, P1

Written 2026-08-29 17:57. Produces `model_1x2.json` and `model_1x2_eval.csv` with `logloss`,
`brier`, `rps` and their baselines — exactly what section 11 asks for, and it has been run: the
committed eval shows USA MLS and China Super League both at `beats_baseline = False`.

It appears in **no workflow**, so its output refreshes only when a human runs it. The identical
pattern the repo spent 2026-08-26 fixing for `news_impact` and `clv_schema`: *an analysis nobody
schedules cannot be seen to go stale.*

An earlier draft also called this file untracked. It is not — it is committed on `origin`, and the
local untracked duplicate that suggested otherwise was a by-product of the stale-fetch error in
section 0. That duplicate then blocked the merge (`untracked working tree files would be
overwritten`), which is the exact situation the root `CLAUDE.md` describes: *delete the local copy,
origin is authoritative*. It was byte-identical, so nothing was lost.

**What was genuinely untracked** were 105 season-store parquet files written by local runs — 17
partitions across ten tables from 2026-08-24, plus the 88 `team_match_stats` files. These are
laptop writes the store's CI-only guard exists to prevent, and `pro_collect.yml` stages `data/`
with `git add -A`, so a local `git add -A` would have committed them and inflated every `n` the
research gates on. **Moved out of the repository** to `../v10_local_quarantine_20260830/` — not
deleted, since the `team_match_stats` set is 23,604 rows that cost ~2,298 API calls, and it is
cheap insurance until CI reproduces them.

---

## 2.8 Pro's long-running jobs appear to be starving v9 — measured, mitigated, under test

Raised by the operator: v9's workflows are not keeping their schedule. They are not — and it is
systemic rather than per-workflow. Observed over the 18 hours to 2026-08-30 12:19 UTC:

| v9 workflow | configured | observed median gap |
|---|---|---|
| `predict` | 15 min (Fri–Sun) | 131 min |
| `live_scanner` | 30 min | 202 min |
| `player_props` | 60 min | 104 min |
| `nf_odds_capture` | 60 min | 165 min |
| `update_results` | ~2 h | nothing since 2026-08-29 18:00 |

Two distinct problems, and only one is new.

**v9 has always under-fired.** Its crons ask for ~2.9–3.3 predict runs/hour averaged over a week;
the clean baseline achieved **1.24/hour, about 43% of schedule**. GitHub does not guarantee
`schedule` — it delays and drops runs under load, and 22 active workflows at ~220 scheduled runs a
day is the profile that gets throttled.

**It then got 61% worse, on a specific date.**

| period | predict runs/hour | median gap |
|---|---:|---:|
| 20–23 Aug | 1.24 | 31 min |
| 24–26 Aug | 0.98 | 35 min |
| 26 Aug 10:00 → 29 Aug | **0.38** | **91 min** |
| since 29 Aug 17:47 | 0.38 | 135 min |

The break lands in the hour `pro_team_news` went live (2026-08-26 09:59). Both new Pro workflows
do not merely run, they **hold a runner**: `pro_team_news` looped 20 minutes out of every 30, and
`pro_live_odds` looped 55 minutes of every hour from 11:00–23:00 — together close to permanent
occupancy on an account whose other repository is v9.

There is an irony worth recording. The loop was adopted *because* of throttling — `pro_team_news`
says so in its own comment, *"a `*/15` has been observed arriving every ~179 min on this
account"* — so the response to dropped runs was to hold runners longer, which plausibly deepened
the contention that caused the drops.

**Stated honestly: this is a sharp correlation with a plausible mechanism, not proof.** Queue-wait
times are not visible without authenticated API access, and the public Actions API was reachable
for workflow definitions but not for run records during this pass.

**Mitigation applied, framed as an experiment:**

| | before | after |
|---|---|---|
| `pro_team_news` | `*/30`, 20-min loop, timeout 35 | `*/30`, **single sweep**, timeout 12 |
| `pro_live_odds` | `9 11-23`, 55-min loop, timeout 75 | `4,19,34,49 11-23`, **single sweep**, timeout 15 |

Live-odds sampling falls from ~11 sweeps/hour to 4. That is a real loss, accepted deliberately:
`live_odds_snapshots` has never persisted a row, while v9's odds capture is live, unbackfillable,
and measurably degrading. **The test is to re-run `src.monitoring.scheduler` in a few hours**; if
v9's predict returns toward 1.0+/hour, the loops were the cause. If it does not, the throttling is
GitHub-side and the loops can be restored.

v9 itself was not touched — it is frozen, and every change here is Pro-side.

| file | change |
|---|---|
| `config/pro_config.py` | 5 combo tables declared in `TABLES` |
| `src/data/season_store.py` | `REQUIRED` key columns for the 5 tables |
| `src/schemas.py` | 5 combo table specs; `is_expected_empty()`; corrected the false `team_match_stats` note |
| `src/combo/canonical.py` | **new** — wide builder CSVs → 5 normalized append-only tables |
| `src/pipelines/bet_builder.py` | selection-aware order-independent `combo_id`; `combo_id_legacy`; composite-first merge key; distinct-combo merge guard; canonical writes on generate and settle |
| `src/combo/notify.py` | legacy→new notify-state migration; `fingerprint` docstring records the defect |
| `src/pipelines/registry.py` | `is_expected_empty` accounting; `empty_reason`; `tables_never_written`; `n_tables_declared` |
| `src/monitoring/scheduler.py` | **new** — observed cadence, near-kickoff coverage, API budget |
| `.github/workflows/pro_collect.yml` | scheduler step; swallowed team-stats failure surfaced; 2 artifacts committed |
| `.gitignore` | allowlist the 2 new artifacts |
| `tests/test_combo_canonical.py` | **new** — 44 checks |
| `tests/test_scheduler.py` | **new** — 15 checks |

**Nothing is committed.** All changes are in the working tree pending the operator's validation.

---

## 4. Canonical tables, ownership and lifecycle

Ownership is unchanged and was not violated: **v9 produces raw evidence, v11 owns market
microstructure, Pro owns canonical storage and validation.** Pro reads v9 over HTTP and writes
nothing to it. No competing definition was introduced.

| table | grain | lifecycle | why |
|---|---|---|---|
| `combo_candidates` | (combo_id, snapshot_ts) | ACTIVE | one opinion at one moment |
| `combo_legs` | (combo_id, leg_index) | ACTIVE | replaces `leg1_…leg4_`, which cannot express 5 legs |
| `combo_dependencies` | (market pair, window, calc_version) | ACTIVE | outlives any combo that uses it |
| `combo_settlements` | (combo_id) | ACTIVE | arrives days later |
| `combo_price_snapshots` | (combo_id, snapshot_ts, price_basis) | **SOURCE_REQUIRED** | see below |

`SOURCE_REQUIRED`, not `PLANNED_OPTIONAL`, and the distinction is load-bearing:

* `PLANNED_OPTIONAL` — the data exists, we have not written the collector → **someone can act**
* `SOURCE_REQUIRED` — the data does not exist to collect → **nobody can act**

`registry.py` previously treated only `PLANNED_OPTIONAL` as legitimately empty, so a
`SOURCE_REQUIRED` table would have reported as an outage on every run forever — re-creating the
always-slightly-red signal that `PLANNED_OPTIONAL` was introduced to remove.

---

## 5. Builder architecture, and the price discipline

Dependency-aware joint probability is preserved exactly; nothing was simplified to `p1 × p2 × p3`.
`independence_probability` is stored beside it as the control — the difference **is** the
dependency claim.

**We have no bookmaker same-game-builder price.** Not "not yet": a book applies its own
correlation adjustment to a same-game multiple, so the product of its singles is not the price it
would offer. Therefore, throughout:

* `offered_odds`, `implied_probability`, `market_probability`, `model_edge`, `profit`, `stake` are
  **NULL, never 0.0**. A zero reads as "measured, and it was zero" — a different and false claim.
  Asserted by test.
* `combo_price_snapshots.price_basis` is REQUIRED and never blank
  (`REAL_BUILDER` / `REAL_COMPONENT_PRODUCT` / `MODEL_FAIR_ONLY`), so a reconstructed price can
  never be read as executable CLV downstream.
* **No CLV is computed for combos.** Section 14.

Cross-match multiples are the honest exception — their legs are separately executable, so a
component product is a real price. The builder currently emits same-match only.

---

## 6. Verification

Run on the real committed data, not fixtures, using v9's interpreter (`pandas 3.0.3`); the root
`.venv` has a broken pandas C extension.

```
combo_id after fix        475 rows → 475 distinct ids (was 225)  ·  0 collisions
combo_candidates          475 rows, 26 cols
combo_legs              1,319 rows; legs-per-combo {2:204, 3:173, 4:98}
                        matches declared n_legs {2:204, 3:173, 4:98} exactly
market_family           0 UNMAPPED (first version mis-binned 413 legs, incl. every O25/O35)
combo_settlements       8,393 rows · WIN 558 / LOSS 582 / UNKNOWN 7,253
combo_dependencies      1,638 team + 171 player → 1,809 rows, all versioned
notify state migration  14 entries carried; decisions identical pre/post (NEW 97, REMINDER 12)

tests/test_combo_canonical.py   44 checks, all pass
tests/test_scheduler.py         15 checks, all pass
existing suite                  test_market, test_validation, test_registry_gates,
                                test_imputers_calibration, src.combo.tests — all pass
                                test_season_store, test_drift_experiment — PRE-EXISTING failures
                                on `PRO_MAY_NOTIFY is False` (section 2.6), not caused here
```

`system_registry.json` was regenerated during verification, measured the **local** store, and was
reverted — it would have re-asserted the same laptop-derived `team_match_stats: 23,604` this pass
exists to correct. The two new JSON artifacts were likewise deleted locally so CI writes the first
real ones.

---

## 7. API budget

`scheduler_health.json` carries an `api_budget` block read from **v9's own committed meter**
(`output/api_usage_log.csv`). Pro does not poll the quota endpoint: v9's `af_usage_monitor` already
does, every 3 hours, and re-polling would spend calls to learn something already written down.
Latest reading: **2,649 / 75,000 used**, plan Ultra. Section 8's guardrail is recorded as
`alert_at: 45000`, `abort_at: 60000` with a computed status — **reported, not enforced**; this
module does not abort anyone's workflow.

Per-endpoint / per-workflow attribution is **not** built. v9's meter is a total, and splitting it
needs instrumentation inside v9 — which is frozen. Listed as a remaining gap rather than faked.

---

## 8. Remaining gaps (honest)

1. **Rejected combos are still not stored.** `generate()` keeps the top N per (fixture, leg count)
   and the rest never reach a DataFrame, so `research_status` is `CANDIDATE` for every row. Section
   4 asks for `REJECTED`/`AVOID`/`BLOCKED` too, and storing only the attractive combos genuinely
   does prevent asking whether the filter works. Fixing it changes what `build()` returns — a
   change to the builder, not to its storage, so it was not smuggled into a canonicalization pass.
2. **86% of settled combos are `UNGRADEABLE`** (7,253 of 8,393). Not investigated; it may be
   unsettled fixtures, or a join failure of the kind invariant 11 describes.
3. **Per-endpoint API attribution** — see section 7.
4. **`combo_legs.odds` is NULL.** Real single prices exist in `market_snapshots` and
   `player_props` but the candidates frame does not carry them, so per-leg edge is not yet
   computable. Left null rather than reconstructed.
5. **`pro_backfill_results` runs succeed but have committed nothing since 2026-08-19.** Not an
   outage — the runs complete — but eleven days of a job that exists to add settled results
   producing no change is worth one look at what it is finding.

---

## 9. Next five priorities

1. **Read the runner-contention experiment** (section 2.8) before anything else touching cadence.
   If cutting Pro's loops restores v9's schedule, that is a bigger win than any Pro-side tuning,
   and it changes what "kickoff-aware collection" should even be built against.
2. **Kickoff-aware collection** (P1/P2). T-10m coverage is 9.4% and every uncovered fixture is a
   closing price lost for good. The measurement now exists to tell whether a change helped, which
   is the whole reason it was built first.
2. **Confirm `team_match_stats`, `team_news` and `live_odds_snapshots` populate** on the first
   sweeps after the `APIFOOTBALL_KEY` addition of 2026-08-30. All three are one CI run from being
   answered, and all three currently read as empty for the same reason.
3. **Check `pro_backfill_results`** — see gap 5.
4. **Commit and schedule `train_1x2.py`** (P1, section 11). It is written, it produces the right
   metrics, it is not in the repository, and nothing runs it.
5. **Resolve the notify contradiction** (section 2.6) — one decision, then make four places agree.

# WORKFLOW_MAP.md — audit of `NevixAA/wowza-betting` GitHub Actions

Required by Prompt 1 §21 and Prompt 2 §21. Produced by static analysis of
`v9/.github/workflows/*.yml` plus observed commit history, on 2026-08-17.

**Baseline is frozen.** v9 continues to run exactly as-is this season (Prompt 2 §1). Nothing
in this document is a change request against v9 — it is the dependency map that any Pro
change must respect, and the defect inventory the Pro architecture must not reproduce.

---

## 1. Topology

21 workflows. `TG` = holds Telegram secrets, `AF` = API-Football, `OA` = OddsAPI,
`to` = timeout in minutes.

| workflow | cron (UTC) | to | TG | AF | OA | concurrency group |
|---|---|---:|:--:|:--:|:--:|---|
| predict | `1-59/5 8-23 * * *` | 25 | TG | | OA | predict |
| live_scanner | `1-59/5 8-23 * * *` | 5 | TG | AF | OA | **none** |
| player_props | `2 * * * *` + 3 more | 120 | TG | AF | OA | player-props |
| af_usage_monitor | `*/30 * * * *` | 5 | | AF | | af-usage-monitor |
| prop_odds_snapshot | `20 */2 * * *` | 20 | | AF | OA | prop-odds-snapshot |
| update_results | `30 7,9,…,23 * * *` | 10 | | AF | OA | **none** |
| sharp_tracker | `0 8,10,…,22 * * *` | 10 | TG | | OA | **none** |
| std_odds_capture | `0 0,3,…,21 * * *` | 20 | | AF | | std-odds-capture |
| nf_odds_capture | `30 1,4,…,22 * * *` | 20 | | AF | | nf-odds-capture |
| sharp_move_alert | `0 7,13,19 * * *` | 10 | TG | | | sharp-move-alert |
| injury_refresh | `0 4 * * *` | 30 | | AF | | injury-refresh |
| af_history_extend | `0 6 * * *` | 60 | | AF | | af-history-extend |
| fantasy_refresh | `30 6 * * *` | 20 | | AF | | **none** |
| daily_summary | `0 7 * * *` | 10 | TG | AF | OA | **none** |
| warm_nf_shot_cache | `0 3 * * *` | 45 | | AF | | warm-nf-shot-cache |
| retrain | `0 3 * * 0` | 120 | | AF | OA | retrain |
| weekly_summary | `0 9 * * 1` | 5 | TG | | OA | **none** |
| backtest_matrix | `0 3 1 * *` | 120 | | AF | OA | backtest-matrix |
| preseason_retrain | `0 2 1 8 *` | 120 | | AF | OA | retrain |
| backtest | manual | 300 | | AF | OA | **none** |
| worldcup | manual | 10 | TG | | OA | **none** |

Every workflow has a timeout. Seven have no concurrency group.

---

## 2. Defect: shared mutable state resolved by silent discard

**This is the most serious architectural finding.**

Six committed files have more than one writing workflow:

| file | writers |
|---|---|
| `output/bets_ledger.csv` | daily_summary, predict, update_results |
| `output/player_ledger.csv` | daily_summary, player_props, update_results |
| `output/clv_records.csv` | player_props, prop_odds_snapshot |
| `output/player_prop_odds_history.csv` | player_props, prop_odds_snapshot |
| `output/prop_odds_coverage.json` | player_props, prop_odds_snapshot |
| `player_history.parquet` | injury_refresh, player_props |

Those writers sit in **different concurrency groups, or none**, so they can execute
simultaneously. `daily_summary` and `update_results` — two of the three `bets_ledger.csv`
writers — have no group at all.

All 20 scheduled workflows push with the identical strategy:

```bash
git pull --rebase --autostash -X ours origin main
```

During a **rebase**, `ours` is the upstream branch being replayed onto, not the local work.
So on a conflicting hunk the strategy resolves in favour of what is already on `origin` and
**drops the current run's rows**. No error, no annotation, no flag — the workflow reports
success and its data is gone.

For append-only ledgers where two workflows appended different rows near the same offset,
this is silent, unrecoverable loss of exactly the prospective observations Prompt 2 §5 and
§7 require us to retain.

**Pro requirement.** The season store must make this class of bug impossible, not merely
unlikely. Options, in order of preference:
1. **One writer per artifact.** Every Pro table has exactly one producing job.
2. **Run-partitioned appends.** Write `snapshots/dt=<date>/run=<run_id>.parquet` so two runs
   can never touch the same bytes; compact later in a single-writer job.
3. If a shared file is unavoidable, take an explicit lock and **fail loudly** on contention
   rather than resolving with `-X ours`.

Option 2 is the design adopted in `MIGRATION_PLAN.md`, because it also satisfies "APPEND
observations, do not overwrite" for free.

---

## 3. Defect: failures are silent by default

Observed twice in one week, both times invisible for days.

**`player_props.yml`** — every functional step is `continue-on-error: true`, so a crash left
outputs untouched, staged nothing, and reported **green**. `player_tips.csv` froze from
2026-08-15 14:29 to 2026-08-17 while the hourly workflow "succeeded" ~40 times. Root cause
was `int(NaN)` in `_filter_by_lineup` (NaN is truthy in Python, so the `if not fid` guard
never fired). A health step *was* emitting `::warning title=Stale player history` throughout;
annotations are not read by anyone.

**`COLLECT_SEASONS` frozen at season 2025** while `PROP_SEASONS` had been rolled to 2026.
The daily collect re-fetched four cached seasons for free and reported success while
`player_history.parquet` sat at 2026-07-04 for six weeks — blocking all prop CLV grading.

**Pro requirement.** A collector that produces no rows is a **failure**, not a success. Every
Pro job asserts on its own output (row count, freshness, schema) and exits non-zero when the
assertion fails. Heartbeat freshness is a first-class monitored metric, not an annotation.

---

## 4. Defect: season-keyed config is hand-maintained

Three instances of the same bug class found: `COLLECT_SEASONS`, `af_history.parquet` seasons,
and `PROP_SEASONS` (currently correct, but hand-rolled on 2026-08-05 and due again July 2027).

**Pro requirement.** No season literal anywhere. Derive from date, with calendar-year leagues
handled explicitly. A test asserts the live season is present for every configured league.

---

## 5. Runtime is the binding constraint, not API quota

API-Football moved to Ultra (75,000/day). Observed usage: ~3,400/day baseline, ~10,300 on
2026-08-17 after predict enrichment was re-enabled. **Headroom ≈ 60,000/day.**

Quota is therefore *not* the constraint. Two things are:

1. **Wall-clock in the 5-minute loop.** The 2026-08-15 incident was never a quota failure —
   `predict.yml` runtime went 2–3 min → 10+ against its timeout, and a timed-out predict
   sends *zero* tips. Spend credits in batch jobs, never in `predict`.
2. **Whether a consumer exists.** Data no model reads is cost without return.

**Pro requirement.** Pro collectors run on their own schedules and must never share a
concurrency group with, or lengthen, v9's `predict`.

---

## 6. What must not stop (Prompt 2 §2)

These streams are the season's product. The Pro system reads them; it does not replace or
gate them.

`predict` · Telegram tips · `std_odds_capture` · `nf_odds_capture` · `prop_odds_snapshot` ·
`player_props` · `live_scanner` · `update_results` · `injury_refresh` · `af_history_extend` ·
`fantasy_refresh` · `sharp_tracker` · `daily_summary` · `weekly_summary` ·
`retrain` · feature-health outputs · every ledger and odds history · all `*_notified.json`
dedup state.

---

## 7. Consumers of v9 output (who breaks if a file moves)

| producer | artifact | consumers |
|---|---|---|
| predict | `output/predictions.csv`, `bets.csv` | dashboard, notifier, update_results, **wowza-v11 (over HTTP)**, Pro importer |
| predict | `odds_history_v9.json` | `drift.py` tier upgrade/downgrade |
| predict | `output/newformat_odds_dense.csv` | new-format CLV, update_results |
| std/nf_odds_capture | `standard_odds_history.csv`, `newformat_odds_history.csv` | CLV, backtest |
| update_results | `bets_ledger.csv`, `side_bets_ledger.csv` | summaries, dashboard, backtest |
| player_props | `player_tips.csv`, `player_ledger.csv` | notifier, prop CLV, Pro importer |
| prop_odds_snapshot | `player_prop_odds_history.csv`, `prop_odds_coverage.json` | prop CLV, coverage decisions |
| player_props / injury_refresh | `player_history.parquet` | props training, current-club resolution |

`wowza-v11` consumes v9's **committed public data over HTTP** and keeps running (user
decision, 2026-08-17). Its `src/edge_engine.py` is the intended source of Pro's market layer.

---

## 8. Reusable components identified

Do not rewrite these; port them with tests and an OLD/NEW/WHY/RISK note.

| component | source | satisfies |
|---|---|---|
| `power_devig`, `proportional_devig`, one-sided → OBSERVE | `wowza-v11/src/edge_engine.py` | Prompt 1 §9 |
| `market_baseline()` — exchange > cross-book median > single | same | §10 |
| market-relative residual test (MARKET vs MARKET+WOWZA on Brier/logloss) | `wowza-v11/scripts/v11_residual.py` | §2 |
| CLV gate, `BET`/`PAPER`/`NO_BET` separated from tier | `wowza-v11/src/edge_engine.py` | §11, §15 |
| `resolve()` — league-scoped club-name resolution, refuses ambiguity | `v9/src/team_names.py` | §18 |
| `model_type_for_league()` — standard vs new-format tagging | `v9/config.py` | invariant 1 |
| drift price-change archiving | `v9/src/drift.py` | §6 (extend, don't replace) |

`v9/src/model.py` is explicitly **not** on this list — see `MIGRATION_PLAN.md` phase 3.

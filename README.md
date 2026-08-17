# wowzaV9-Pro

Next-generation validation and research system for the Wowza football betting stack.

**This repo does not bet, does not tip, and does not notify.** It is a shadow/challenger and
the canonical research store for season 2026/27.

## Central question

> Does each model contain information **beyond the betting market**, and is the evidence
> strong enough to deploy?

Standalone AUC does not answer that. Market-relative LogLoss/Brier, calibration, clean
real-odds CLV and honest uncertainty do.

## The three live systems

| system | repo | role this season |
|---|---|---|
| **v9** | `NevixAA/wowza-betting` | **production + frozen baseline.** Tips, notifications, all collection. Untouched |
| **v11** | own repo | market-first shadow. Keeps running independently |
| **Pro** | this repo | strict validation engine + canonical season store. No tips |

Pro **reads v9's committed output over HTTP** and never writes to it.

## Season 2026/27 is a data-collection season

Success is explicitly *not* ROI. It is observability, prospective data, real market snapshots,
correct timestamps, provenance, control groups, clean settlement and shadow comparison. The
upgraded selective production system is a **next-season** objective.

Consequently: **signal tier ≠ deployment mode.** `SNIPER`/`MARKSMAN`/`VALUABLE`/`AVOID` is
signal strength. `LIVE`/`PAPER`/`RESEARCH`/`BLOCKED` is permission. `SNIPER + PAPER` is valid
and useful — it still gets recorded, settled and CLV-graded.

## Start here

- [`docs/MIGRATION_PLAN.md`](docs/MIGRATION_PLAN.md) — phases, decisions, guardrails
- [`docs/WORKFLOW_MAP.md`](docs/WORKFLOW_MAP.md) — audit of v9's 21 workflows and its defects

## Layout

```
config/         src/data/       src/features/   src/models/
src/market/     src/validation/ src/betting/    src/monitoring/
src/pipelines/  src/importers/
registry/       experiments/    models/  output/  data/  tests/  docs/
_legacy/        preserved, uncommitted: v10's stale v9 snapshot + v9 workflow reference
```

## Rules that do not bend

1. Never write to v9. Never send Telegram from here.
2. Nothing is deleted — contaminated rows get a quality flag, not a delete.
3. Append only. Repeated predictions for the same fixture are all retained.
4. Real odds only for profitability claims; otherwise `INSUFFICIENT_MARKET_DATA`.
5. Never promote on AUC alone. No validation, no promotion.
6. A collector that produces zero rows **fails loudly**.
7. No season literals in config — derive from the date.

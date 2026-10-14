# wowzaV9-Pro

Next-generation validation and research system for the Wowza football betting stack.

**This repo never stakes and never writes into v9.** It is the challenger, the canonical
research store for season 2026/27, and the evidence layer that decides what may receive money.

It does send a few things to Telegram, all labelled PAPER: Bet Builder combos, the top 1X2
picks, and one daily tip scoreboard. (An earlier version of this file said "does not tip, and
does not notify"; that stopped being true when Bet Builder notifications were switched on.)

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
| **Pro** | this repo | strict validation engine + canonical season store + League Scout. Paper tips only |
| **wowza-exec** | `NevixAA/wowza-exec` (private) | Cloudbet execution control. PAPER_ONLY, fail-closed; obeys a policy Pro recommends and a human approves |

Pro **reads v9's committed output over HTTP** and never writes to it.

## Season 2026/27 is a data-collection season

Success is explicitly *not* ROI. It is observability, prospective data, real market snapshots,
correct timestamps, provenance, control groups, clean settlement and shadow comparison. The
upgraded selective production system is a **next-season** objective.

Consequently: **signal tier ≠ deployment mode.** `SNIPER`/`MARKSMAN`/`VALUABLE`/`AVOID` is
signal strength. `LIVE`/`PAPER`/`RESEARCH`/`BLOCKED` is permission. `SNIPER + PAPER` is valid
and useful — it still gets recorded, settled and CLV-graded.

## What runs here (added 2026-10-08)

| Piece | Code | Output | Cadence |
|---|---|---|---|
| **League Scout** — odds (Pinnacle, Bet365, cross-book median) for O/U 1.5/2.5/3.5 + BTTS, results + 4 past seasons, a baseline goals model frozen before kickoff, for ~200 leagues Wowza does not bet (owner's 30 lower tiers first) | `src/scout/` | `output/scout/REPORT.md`, `league_status.json` | every 2 h (`pro_scout.yml`) |
| **Tip scoreboard** — how the 1X2 and Bet Builder tips Pro SENDS are doing; voided-leg combos kept separate; builder ROI not reported (no builder price exists) | `src/pipelines/tip_scoreboard.py` | `output/TIP_SCOREBOARD.md` + daily Telegram recap | 05–11 UTC (`pro_tip_scoreboard.yml`) |
| **Upgrade studies** — Argentina BTTS controls; UNDER diagnosis; does the model add to the market (out-of-sample residual test); per-cell evidence (shrinkage, BH-FDR, reality check, sequential CLV, CUSUM); market-anchored O/U challenger with a first-sight forward record; pre-registered props segments | `src/studies/` | `output/studies/REPORT.md` | daily (`pro_studies.yml`) |
| **Player Model V3 / Edge Lab** — new player features (shrunk form, usage share, opponent personnel, roles), SOT count models, expected minutes, and the market-residual test on real prop prices | `src/player_v3/` | `output/player_v3/PLAYER_V3_REPORT.md` | on demand |
| **Player V3 forward test** — the prop market-residual rule, frozen 2026-10-14 and tested only on props settled from 2026-10-15 (150 per market to decide) | `src/player_v3/forward.py` | `output/player_v3/FORWARD_TEST.md` | daily (`pro_player_v3_forward.yml`) |
| **Calibration form** — v9's Platt (on the raw probability) vs Platt on log-odds, same models otherwise | `src/studies/calibration_form.py` | `output/studies/CALIBRATION_FORM.md` | on demand |
| **Price Trader lab** — can a Wowza back be greened later at a real price for a profit? Hedge maths, exit rules, placebo, chronological holdout, paper engine | `src/price_trader/` | `output/price_trader/PRICE_TRADER_REPORT.md` | daily (`pro_price_trader.yml`) |
| **Bankroll review / league promotion** — monthly staking-policy recommendation; weekly league promotion review + canonical league registry | `src/bankroll/`, `src/scout/promotion.py`, `src/scout/registry.py` | `output/bankroll/`, `output/scout/` | monthly / weekly |
| **Research index** — every study's latest verdict in one file; the v9 dashboard's Pro page ("Latest findings") renders it, so a new result shows up without a dashboard change | `src/monitoring/research_index.py` | `output/research_index.json` | after each study run (`pro_research_index.yml`) |

Findings as of 2026-10-08 (details in `output/studies/REPORT.md`):

* **Argentina BTTS** is a league scoring regime the market prices slowly — BTTS 38% in 2025,
  56% since August; blind YES did as well as Wowza's picks. The only cell that survives FDR, and
  still PAPER (73 bets of the 150 the gate needs).
* **v9's O/U 2.5 probability is compressed near 52%** (sd 0.059 vs the market's 0.092). Its
  UNDER "edges" are matches the market rates high-scoring — and the market is right. Adding the
  model to the market improves no market out of sample. Owner decision: no change to v9 before
  ~2026-10-29, while the challenger's forward record builds.

Findings added 2026-10-14:

* **Team markets and player props give different answers, and both are true.** For team O/U and BTTS
  the model adds nothing once the price is known. For **player props**, Player V3 adds a little to
  the price out of sample: goals, SOT 1+, 2+ and 3+ (log-loss −0.005 to −0.011). That is accuracy only.
  No prop bet has shown a profit, so props stay **paper**. The pre-registered forward test decides
  (~4 months to reach 150 per market).
* **Calibration form:** Platt on log-odds beats v9's Platt-on-probability on **12 of 12** models
  (player and team). Team models stay compressed (calibration slope > 1). Adopting it in v9 is an
  architecture change and needs owner approval plus a shadow period.
* **Price Trader: no tradeable edge.** Entered at Wowza's real signal, the price moved toward Wowza on
  41.5% of 934 trades. A model-free placebo did as well. Locking in a profit lost 9.6–10.6% per trade
  under every exit rule, because the ~5% bookmaker margin is bigger than the moves. V11's 70%+ toward
  rates are fair-probability drift, not trades. The paper engine keeps running. Instant arbitrage
  showed up on 1% of snapshots and stays theoretical until stake limits are known.

Data traps found on the way, worth knowing before any new study:

* v9's Bet365 BTTS history contains **first-half** pairs (YES 8.00 / NO 1.08) that pass a margin
  check; drop with `src.quality.BTTS_YES_MAX`.
* v9 stamps **local** match dates, API-Football **UTC**; `fixture_key` joins miss about half.
  Use `src.studies.common.match_frames`.
* `output/**` is deny-all in `.gitignore`: whitelist every new output file by name, and add one
  path per `git add` — a multi-path add stages nothing if any path is missing.

## Start here

- [`docs/MIGRATION_PLAN.md`](docs/MIGRATION_PLAN.md) — phases, decisions, guardrails
- [`docs/WORKFLOW_MAP.md`](docs/WORKFLOW_MAP.md) — audit of v9's 21 workflows and its defects

## Layout

```
config/         src/data/       src/features/   src/models/
src/market/     src/validation/ src/betting/    src/monitoring/
src/pipelines/  src/importers/  src/scout/      src/studies/
registry/       experiments/    models/  output/  data/  tests/  docs/
_legacy/        preserved, uncommitted: v10's stale v9 snapshot + v9 workflow reference
```

## Rules that do not bend

1. Never write to v9. Never stake. Telegram only for PAPER-labelled combos, 1X2 picks and the scoreboard; never a paper league (USA MLS).
2. Nothing is deleted — contaminated rows get a quality flag, not a delete.
3. Append only. Repeated predictions for the same fixture are all retained.
4. Real odds only for profitability claims; otherwise `INSUFFICIENT_MARKET_DATA`.
5. Never promote on AUC alone. No validation, no promotion.
6. A collector that produces zero rows **fails loudly**.
7. No season literals in config — derive from the date.

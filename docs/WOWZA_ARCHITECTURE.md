# WOWZA — system architecture

> **Superseded by [`WOWZA_SYSTEM_CONTRACT.md`](WOWZA_SYSTEM_CONTRACT.md).** This narrative
> overview was written first and is kept because it reads more like a tour than a contract. The
> contract is authoritative: it carries per-assertion evidence types, verified commit SHAs, a
> research-validity registry and a read-only validator. Where the two disagree, the contract
> wins — it corrects several statements below, notably that v9 is change-controlled rather than
> frozen, that Pro *does* notify from two workflows, and that invariant 1 has two real
> fallbacks.

*Written for an engineer picking up the estate cold. Describes what is actually running as of
2026-09-24, not what was planned. Every count in this document was read off the repos rather
than remembered; where something is stale or unverified it says so.*

---

## 1. Three generations, three repos, one shared root

`mixed/` is not one application. It is the shared root of three independent Python projects
plus a standalone validation harness. Each has its own `config.py`, `requirements.txt` and
lifecycle.

| | folder | repo | role | status |
|---|---|---|---|---|
| **v9** | `v9/` | `NevixAA/wowza-betting` | **Production.** Sends the tips, takes the money | **FROZEN** since 2026-08-19 |
| **Pro** | `v10/` | `NevixAA/wowzaV9-Pro` | Evidence store, validation, Bet Builder, next season's foundation | active |
| **v11** | `wowza-v11/` | own repo | Market-first shadow — logs decisions, never acts | active |
| **harness** | `validation/` `scripts/` `backtest/` | — | Leak-free walk-forward + forensic quant audit | on demand |
| **record** | `PlayerProps_Research/` | — | Audits, deep dives, 139-feature catalog. Start at `00_INDEX.md` | reference |

`v9/config.py` sets `DATA_DIR = BASE_DIR.parent`, i.e. **the shared root**. The historical
Excel, `sofascore_cache.json` and `best_params.json` live there and are read by v9 and by the
legacy copy inside `v10/`. Moving or renaming a root file breaks two generations at once.

### The `v10/` trap

The folder was once a git-free copy of v9. That is over. The directory is now the working tree
of **wowzaV9-Pro**, and the repo tracks **only** the Pro layer — 905 files under twelve
top-level entries:

```
src/{pipelines,combo,live,market,models,features,validation,monitoring,importers,data,betting}
config/pro_config.py   registry/   data/   models/   output/   docs/   tests/   experiments/
.github/workflows/pro_*.yml
```

Everything else still sitting in `v10/` — `pipeline.py`, `app.py`, `retrain.py`,
`player_model/`, `pages/`, `research/`, the `*_cache/` dirs, the June/July `.parquet`
experiments — is **untracked leftover** of the old copy. `git status` there will never show it
and `git add -A` would swallow all of it. Editing those files ships nothing.

---

## 2. v9 — production

### 2.1 The money path

```
football-data.co.uk ──> output/fd_history.parquet     62,321 rows / 30 leagues   [team O/U]
API-Football        ──> output/af_history.parquet     61,578 rows / 30 leagues   [enrichment]
                    ──> player_history.parquet       347,771 rows / 31 leagues   [props + fantasy]
                    ──> output/af_ht_history.parquet    6,977 rows / 15 leagues   [HT grading]
OddsAPI / RapidAPI  ──> live prices, unified to { fixture_id: (over, under) }
        │
        ▼
   src/data_loader.py
     canonicalise club spellings, resolve names league-scoped, merge HT scores,
     median-impute, dedupe on (date, league, home, away) keeping the fullest row
        │
        ▼
   src/model.py
     LogReg + GradientBoosting ensemble, Platt calibration, per market,
     CHRONOLOGICAL (walk-forward) split — never a random split
        │
        ▼
   src/predict.py
     edge = model_prob − 1/bookmaker_odds
     SNIPER (full stake) / MARKSMAN (three quarters) / VALUABLE (half)
        │
        ▼
   telegram_bot/notifier.py
```

### 2.2 Sixteen models, two tracks that never mix

**Standard-format** — leagues with shots, corners and O/U odds history:

| file | market |
|---|---|
| `model_v9_standard.pkl` | Over/Under 2.5 — *the only market carrying real money* |
| `model_v9_btts.pkl` | both teams to score |
| `model_v9_over15.pkl` | Over 1.5 |
| `model_v9_over35.pkl` | Over 3.5 |
| `model_ht_over05.pkl` | half-time Over 0.5 |
| `model_ht_over15.pkl` | half-time Over 1.5 |

**New-format** — leagues with goals + 1X2 only:

| file | market |
|---|---|
| `model_v9_newformat.pkl` | Over/Under 2.5 |

**Player props** — nine models, paper only:

`model_player_goals` · `goals2` · `goals3` · `assists` · `cards` · `sot` · `sot2` · `sot3` · `sot4`

Separate `.pkl` files, separate backtests, separate league sets. `model_type_for_league()` is
the canonical tag and is duplicated verbatim into v11's config so the two cannot diverge.

The HT models apply under `std_mask` in `src/predict.py` — **half-time is standard-leagues
only**. New-format fixtures carry no HT data and are not meant to.

### 2.3 Twenty-two workflows

| cadence | workflows |
|---|---|
| every 5 min, 08–23 UTC | `predict` |
| ~10 min | `live_scanner` |
| hourly to 6-hourly | `player_props` |
| every 2 h | `sharp_tracker`, `update_results`, `sharp_move_alert` |
| 8×/day | `std_odds_capture`, `nf_odds_capture` |
| daily | `player_history_extend` 03:40, `injury_refresh` 04:00, `daily_summary`, `fantasy_refresh`, `prop_odds_snapshot`, `af_history_extend`, `af_usage_monitor` (30 min), `warm_nf_shot_cache` |
| weekly | `retrain` Sun 03:00, `weekly_summary` |
| monthly / seasonal | `backtest`, `backtest_matrix`, `preseason_retrain`, `worldcup` |

`predict` commits **each output file individually** so one missing file cannot abort the whole
commit. That was the fix for a duplicate Telegram-tip flood.

### 2.4 Props collection (rebuilt 2026-09-24)

`player_model/config.py::PROP_LEAGUES` is the **single source of truth** for which leagues the
prop model touches. `data_fetcher.APIFOOTBALL_LEAGUES` is *derived* from it, and
`_autofill_missing_leagues()` gives any league without an explicit plan four seasons. A league
can no longer be tippable and uncollectable at the same time — which it was, for four weeks.

`api_current_season(league_id)` asks API-Football which season it considers current and
**appends** the answer to the plan. It never substitutes, so a wrong or missing answer can only
fail to add, never remove. This exists because no date arithmetic survives a league changing
its calendar.

Two environment knobs:

| var | effect |
|---|---|
| `WOWZA_COLLECT_SEASONS_BACK` | seasons of depth per league. CI sets `1` (live season only); unset locally means full depth |
| `WOWZA_API_REQUEST_DELAY` | seconds between calls. 450/min is an **account** limit shared with CI, so a local backfill should set ~0.35 |

---

## 3. Pro (`v10/`) — where new work happens

Reads v9's committed output **over HTTP** (`src/data/v9_source.py`) and never writes into v9 —
same discipline as v11.

**Ten workflows**: `pro_collect` (2-hourly snapshot at :40 to dodge v9's runners, plus a daily
sweep), `pro_team_news` (30 min), `pro_live_odds`, `pro_backfill_results`, `pro_bet_builder`
(Fri–Sun plus weekdays), `pro_team_stats`, `pro_paper_1x2`, `pro_prediction_lab`,
`pro_research`, `pro_weekly_audit`.

Pro's README says it "does not bet, does not tip, and does not notify". That is **no longer
literally true** — `pro_bet_builder.yml` has a `--mode notify` step and `src/combo/notify.py`
sends. It still never writes into v9.

Pro holds the estate's **only real test suite**. There is no pytest config, so run it from
`v10/` as `python -m pytest tests/`. `python -m src.combo.tests` is a separate thing: a Bet
Builder correctness gate the workflow runs before every pass, not a unit suite. **v9 and v11
have no tests** — for those, validation is the backtest and audit harness, so do not claim
tests pass; run the relevant backtest instead.

---

## 4. v11 — market-first shadow

The opposite philosophy to v9, adopted because out-of-sample research showed that "the model
disagrees with the book" is a longshot machine, not an edge (props −41% to −57%, AUC ≈ 0.5).

```
validate odds (overround + O/U ordering)
  → de-vig (power method)        → consensus p_market
  → blend model as a SMALL RESIDUAL, capped per segment (NF 0.45 / standard 0.40 / else 0.30)
  → uncertainty lower bound      → EV lower bound
  → CLV gate                     → longshot hard cap
```

Defaults to **NO_BET**. States are `BET` / `PAPER` / `NO_BET`; `BET` requires a segment's clean
CLV count ≥ `MIN_CLV_N` (150) and positive, otherwise `PAPER`. That gate deliberately solves the
bootstrap trap — you need CLV history to bet, but cannot accumulate it without paper-executing
first.

Scripts: `v11_shadow`, `v11_grade`, `v11_residual`, `v11_market_movement`, `v11_microstructure`,
`v11_fit_evidence`, `v11_momentum_control`, `v11_tests`. One workflow, `v11_collect.yml`.

**Every number produced by `v11_momentum_control.py` is void.** Line 158 does
`return out.sort_index()["p_at"]` on a `pd.merge_asof` result, which carries a fresh
`RangeIndex` in sorted-key order — so assigning it back lands every value on the wrong row.
Treat those results as unmeasured, not disproven.

The **residual test** — does the model improve Brier or log loss *after* the market price is
known — is the real measure of whether the model knows anything the market does not. Standalone
AUC is not.

---

## 5. The invariants

Hard-won conclusions, not preferences. Violating any of them silently corrupts results.

1. **Standard and new-format never mix.** Two model tracks, two `.pkl` sets, two backtests.
2. **Player props are paper-only, permanently.** The model is genuinely accurate (AUC 0.62–0.85,
   calibrated) and has **no betting edge** — market AUC matches or beats it. Confirmed
   2026-07-09 across 8 tests on the bug-fixed model. Accuracy is monetised through the no-vig
   **Fantasy** family instead.
3. **v9 is frozen.** Only exception: production down. Then fix the narrowest possible thing and
   say so.
4. **v11 never touches v9.** It reads v9's public raw GitHub output only.
5. **Predict is pre-match only.** In-play belongs to the live scanner.
6. **No retrospective tuning.** The strategy is frozen before the backtest.
7. **Training-only leagues are not bet leagues.** `STANDARD_FORMAT_LEAGUES` is a superset of
   `ENABLED_LEAGUES`.
8. **Never bet a fixture with no rolling-form history.** Missing features are median-imputed, so
   a blind fixture produces a confident-looking wrong edge, not a cautious one.
9. **Write NaN, never an invented number.**
10. **`odds_history_v9.json` must stay committed.**
11. **Club names differ between sources.** Use `src/team_names.resolve` — league-scoped, refuses
    ambiguous matches.
12. **A player belongs to his latest CLUB**, never to every club he has played for. Club-only:
    history holds internationals where `team` is the player's country.

---

## 6. Where the money actually is

Real money sits on **standard-format second-division Over/Under SNIPER only**. Props, HT, 1X2,
live signals, combinations and new-format are all paper.

The load-bearing negative result, which survived an adversarial selection-bias attack: **the
model is overconfident by +13.64pp** — claimed 0.5430 against realised 0.4066, z = 7.81,
n = 792 — and the gap is the same size on staked bets (+16.80pp) as on never-staked VALUABLE
(+10.78pp). That is the finding: **the tier ladder carries no information.** The bookmaker's own
*vigged* price beats the model on Brier (0.2368 vs 0.2583) on the model's own selected bets.

---

## 7. Traps that have each already produced a wrong conclusion

**The deployed thresholds are not the `config.py` defaults.** Every threshold is
`float(os.getenv(NAME, default))` and `predict.yml` sets the environment. The live MARKSMAN
floor has been 0.08 since 2026-08-21, not the 0.14 in `config.py`. Always load the production
env before reasoning about a threshold.

**Every `*_snapshots` table is a change-log, not a panel.** Writers store consecutive-*distinct*
values only, so at any single timestamp only the entities that just moved are present. Use
last-observation-carried-forward per entity before aggregating. This one storage decision has
caused three separate wrong conclusions.

**`pd.merge_asof` resets the index and `sort_index()` cannot undo it.** See §4.

**Never compute freshness from file mtime.** `git checkout` resets mtime on every CI run, so
anything mtime-based reads as ~0 hours old and never refreshes. Found three times in this
estate. Use a recorded timestamp in a committed sidecar, and treat an unknown age as
**infinitely old**.

**GitHub Actions cannot hit a clock.** Runner queue wait is 0.0 min at every percentile — that
is never the constraint. But delivery and punctuality trade off: at ~57 runs/day only 13% of
slots fire; once daily is ~100% but lands 4–5 **hours** late. Cron minutes do not survive the
dispatcher. So: never make anything depend on a cron firing near its slot; in-run adaptive loops
are the only real timing control; make a time-sensitive job idempotent first, then
over-schedule it.

**Historical odds cannot be backfilled.** API-Football's `/odds` endpoint is pre-match only.
Probed 3 fixtures per season 2019–2025, both with and without a bookmaker filter: 0 of 3 every
time. `scripts/backfill_af_odds.py` cannot work — it will happily burn 20,000 calls writing
empty results. Forward capture is the only option, which is why the capture scripts' cadence
matters and why a day of closing prices not captured is gone.

**A glob, a gitignore or a gitattributes rule is a repo-wide change even when it is one line.**
A `*.csv text eol=lf` rule checked against 4 of 48 tracked CSVs left one file permanently
"modified", which aborted every `git pull --rebase` and killed two workflows at the push step
while every functional step showed green.

---

## 8. Known gaps, stated plainly

- **Seasons 2023–2024 for the fifteen prop leagues added 2026-09-24** are not yet collected;
  the live season is. Needs roughly two more days of spare API quota.
- **Prop odds coverage is split**: 10 of 26 collected leagues have an OddsAPI sport key, 16
  depend on API-Football alone. Collecting player *form* is not the same as having a *price*.
  `output/prop_odds_coverage.json` is the learned ledger — read it before theorising.
- **`output/af_ht_history.parquet` is stale** (last match 2026-06-23, 15 leagues). It is written
  only by `backfill_ht_parallel.py`, a manual script no workflow runs. It feeds HT *grading*,
  not prediction; standard leagues get half-time scores live from football-data.co.uk at
  65–100% coverage. Low priority, but do not mistake it for live.
- **Scottish League One and League Two** are listed in `STANDARD_FORMAT_LEAGUES` but appear in
  no history file, so they contribute nothing to training.
- **CI trains on less data than local.** The historical Excel is local-only and never committed,
  so cloud retrains see fewer seasons. Treat per-league backtest returns as re-validated each
  retrain, never as a fixed headline.
- **Main O/U odds have no upper bound.** `MAX_OU_ODDS` does not exist anywhere in `v9/`; only
  `MIN_OVER_ODDS = MIN_UNDER_ODDS = 1.75`. Odds > 3.0 is 6.1% of settled bets and 35.5% of the
  net loss, ROI −53.9%, and **every one of those 48 bets is new_format**. Excluding them takes
  new_format from −39.92u to −14.07u and leaves standard untouched. Adding the bound is a live
  selection change needing its own evidence — but do not believe the guard is already there.

---

## 9. Commands

Run from inside the relevant generation folder, never from the root.

```bash
# Pro (v10/) — every entrypoint is a module
python -m src.pipelines.pro_collect
python -m src.combo.tests                     # gate before every Bet Builder pass
python -m src.pipelines.bet_builder --mode generate --days N
python -m pytest tests/                       # the only real test suite in the estate

# v9 — team models
python pipeline.py --mode predict|train|backtest|all
python pipeline.py --mode backtest-side --market btts|over15|over35
python retrain.py
streamlit run app.py

# v9 — player props
python -m player_model.pipeline --mode collect|train|predict|all

# v11 — shadow
python scripts/v11_shadow.py
python scripts/v11_residual.py

# root validation harness
python scripts/leakage_audit.py
python scripts/quant_audit.py --predictions path\to\predictions.csv
```

---

## 10. Editing rules

**Never edit a source file with a PowerShell `Get-Content | Set-Content` round-trip.** On
PowerShell 5.1, `Get-Content -Raw` without `-Encoding` reads UTF-8 as cp1252 and
`Set-Content -Encoding utf8` adds a BOM. On 2026-08-15 this destroyed every emoji in
`telegram_bot/notifier.py` and Telegram sent mojibake for ~50 minutes. Use an editor tool, or
Python with an explicit `encoding="utf-8"`.

**Check the cost before enabling a dormant code path.** Wiring one key into `predict.yml`
switched on eight enrichments that had been dead for months; runtime went 2–3 min to 10+ against
a 15-minute timeout.

**`git` on this repo is slow** (OneDrive plus large caches). Use `git status -uno`. If a rebase
fails with `could not detach HEAD`, that is OneDrive file locking — use `git pull --no-rebase`.

**Secrets** come from environment variables loaded from gitignored local files and supplied as
repository secrets in CI. Each of the three repos carries its own set. `v10/` is now a real repo
with its own remote, so a stray secret there is as public as one in v9.

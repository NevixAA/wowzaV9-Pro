# V9 FROZEN — PROSPECTIVE VALIDATION PLAN

Prompt 02, pass of 2026-08-30. Scope agreed with the operator: **P0 only**, then this plan.
Prompt 01's hardening pass is committed and pushed (`9af9240`), which was its stated precondition.

---

## 0. Headline

The primary experiment ran, and it returns a **clean negative with a measurement warning
attached**.

`v11_market_movement.py` reports a fixture-level toward-Wowza rate of **57.9%** (n=465,
p=0.00225), which reads as the market drifting our way. Controlled:

| model | residual coefficient | p |
|---|---:|---:|
| residual only | **+1.2033** | <0.001 |
| + momentum (prev move, velocity, acceleration) | +0.0007 | 0.24 |
| + full controls (add time-to-kickoff, dispersion) | **+0.0005** | 0.49 |

And the reason it collapses is not merely momentum. `p_market(t)` appears in the residual and in
the future move **with opposite signs**, so its measurement noise alone manufactures a positive
coefficient. The placebo control quantifies exactly that:

| variant | coefficient |
|---|---:|
| real residual | +1.2033 |
| **placebo — model probabilities shuffled across fixtures** | **+0.7300** |
| **price only — no model at all, just `−p_market`** | **+0.9968** |

A model probability that *cannot know anything* reproduces **61%** of the headline, and the price
by itself reproduces **83%**. So:

> On 421 fixtures of prospective data, the frozen V9 residual shows **no measurable ability to
> predict subsequent market movement** once momentum and the shared-price artefact are accounted
> for. The uncontrolled 57.9% should be read as arithmetic, not as price discovery.

**This is a result, not a failure.** Prompt 02 section 12 is explicit that HEALTH=PASS with
NO_EDGE is valid, and section 14 defines success as better evidence rather than a better number.
It is also not final: 421 fixtures is the `RESEARCH` band, below section 10's 500-fixture first
checkpoint, and the window is 13 days inside a single month.

**The actionable part is the measurement, not the model.** A price-only coefficient near +1.0
means the market series mean-reverts almost completely against its own noise from one hour to the
next, which no real market does. That points at the series, not the market: `v11_p_market` is
de-vigged from a book panel whose membership changes between snapshots, so part of every measured
"move" is a change in *which books were quoting*, not a change in price. Fixing that — a fixed
book panel, or a consensus over a stable subset — is the highest-value next step, because every
movement, CLV and lead/lag result inherits this noise.

---

## 1. The exact freeze point

| item | value |
|---|---|
| v9 repository | `NevixAA/wowza-betting`, branch `main` |
| v9 HEAD at this pass | `f69e24fa6f8f9c0341295a9df2d52181200f28cf` (2026-08-30 12:14 UTC) |
| **model version (canonical)** | **`09c6a7d2098d`** — content digest over 16 `.pkl` files, 12.2 MB |
| models last changed | `a2ee7541`, 2026-08-30 09:58 UTC, *auto: weekly main-model retrain* |
| model_id | `v9_baseline` |
| model types | `standard`, `new_format` — never mixed (root invariant 1) |

### "Frozen" means frozen METHODOLOGY, not frozen weights

Worth stating plainly, because the two are easy to conflate. `retrain.yml` runs every Sunday at
03:00 UTC and rewrites the `.pkl` files, so V9's probabilities change weekly by design. That does
not violate the freeze — section 1 forbids changing feature weights, model families, blending,
training methodology or feature engineering *to improve performance*; a scheduled retrain on new
data is none of those. But section 1 also requires that anything materially changing
probabilities increments the version, and **a weekly retrain does exactly that**.

With `model_content_sha` this now happens by itself: the version changes when, and only when, the
model bytes change. Measured since 2026-08-16 that is **4 times** — the Sunday retrains plus a
props model refresh.

### The provenance defect this replaced

V9 stamps its own `model_sha` into `predictions.csv`, and it cannot be used as a version.
`v9/src/provenance.py::_model_sha` hashes each file's **size and mtime** rather than its contents,
and a CI `git checkout` resets mtime on every run:

```
commits that actually changed models/*.pkl, since 16-Aug     4
distinct model_sha values in model_snapshots, same window    95
```

A version that changes 24× more often than the thing it versions cannot answer "was this
prediction made by the frozen model", which is the question this entire phase rests on.

The docstring justified size+mtime as avoiding I/O in the 5-minute predict path. Measured: 16
files, 12.2 MB, **46 ms**, once per process because the result is cached — 0.03% of a ~3-minute
run. The cost was never the constraint.

**Fixed Pro-side, not in v9.** Prompt 02 section 1 permits provenance fixes to V9, but does not
require them to be made there, and Pro already checks v9 out — so the same answer was available
without opening a frozen repository (root CLAUDE.md invariant 3). `src/data/v9_source.py::
v9_model_version()` digests the committed model files; `model_content_sha` is stamped on every
`model_snapshots` row; v9's own `model_sha` is preserved untouched alongside it for lineage; and
`MODEL_VERSION_UNKNOWN` is now flagged on the *content* sha, so a row with v9's stamp but no
usable version is no longer counted as versioned.

### Maintenance policy going forward

* Only bug, leakage, mapping, parsing, operational, probability and provenance fixes to v9.
* Every such fix documented here with its date and whether it moved probabilities.
* The weekly retrain is a **version event**, recorded automatically by `model_content_sha`.
* No prediction is ever overwritten; the store is append-only and run-partitioned.

---

## 2. Current samples and coverage

Canonical store at `4f5a0e3`, season 2026/27, window 2026-08-17 → 2026-08-30 (13 days):

| table | rows | note |
|---|---:|---|
| movement_observations | 241,063 | v11 research, archived verbatim |
| market_snapshots | 116,325 | |
| model_snapshots | 103,640 | now carries `model_content_sha` |
| settlements | 73,692 | 6,531 with a closing price |
| player_props | 45,175 | paper only, permanently (root invariant 2) |
| fixtures / feature_snapshots / signals | 21,697 each | |
| **clv** | **5,310** | **138 fixtures** — the binding constraint |
| live_signals | 642 | our opinion in-play, not a price |
| live_odds_snapshots | **0** | see section 5 |
| team_match_stats / team_news | **0** | credential added 2026-08-30, unconfirmed |
| combo_* (5 tables) | **0** | created in prompt 01; fill on the next builder run |

### Sample-size state (section 10)

| measure | n | band |
|---|---:|---|
| movement experiment | 421 fixtures | `RESEARCH` |
| toward-rate headline | 465 fixtures | `RESEARCH` |
| **clean CLV** | **138 fixtures** | **`DATA_COLLECTION`** |

Nothing here is above section 10's 500-fixture first checkpoint. **No graduation of any league or
market is defensible from this data**, and the 79% toward-rate in the `residual +6:+10` bucket
(n=39, already labelled `INSUFFICIENT_SAMPLE`) is exactly the kind of number section 10 exists to
stop anyone acting on.

### Close and CLV quality

`clv_pct` is populated on 61.5% of CLV rows and covers 138 fixtures. Raw CLV is preserved and
never rewritten; clean and strict-clean are derived. Given the price-noise problem in section 0,
**CLV percentages measured on this series should be treated as provisional** — they inherit
whatever part of a "move" is book-panel composition rather than price.

---

## 3. Prior-momentum methodology (implemented)

`wowza-v11/scripts/v11_momentum_control.py`, wired into `v11_collect.yml` so it re-runs as the
sample grows rather than being remembered as settled.

```
future_move_pp ~ residual_pp + prev_move_pp + velocity_pp_h
               + acceleration_pp_h2 + hours_to_kickoff + dispersion
```

* Ordinary least squares via `np.linalg.lstsq`. Transparent first, per section 2 — no ML.
* **Inference clustered by fixture.** One fixture contributes many snapshots and consecutive
  observations of one drifting price are nearly the same observation; treating them as
  independent would shrink intervals by roughly √(snapshots per fixture) and manufacture
  significance. The bootstrap resamples fixtures, refits, and takes percentile intervals.
* Prior windows 15m–24h, future targets 30m/1h/3h, matched with `merge_asof` under an explicit
  tolerance — without one, "30 minutes ago" silently matches a price from six hours back.
* Roles reported separately and never pooled: `WOWZA_LEADS`, `WOWZA_AGREES_WITH_EXISTING_MOVE`,
  `WOWZA_OPPOSES_MARKET`, `UNKNOWN_NO_PRIOR`.

**One bug found and fixed during the first run, recorded because it is easy to repeat:** velocity
was defined as `prev_move / (window/60)`, which is `prev_move` times a constant — perfectly
collinear. `lstsq` does not fail on that, it silently splits the coefficient, and the run printed
`prev_move_pp` and `velocity_pp_h` with identical values (−0.5197 each). Velocity is now measured
over a genuinely shorter window.

**Do not read the role table as a strategy.** `WOWZA_OPPOSES_MARKET` shows 99.6% "toward" and
`WOWZA_AGREES` shows 0.5% — that is the same mean-reversion arithmetic from section 0 seen from a
different angle, not a finding that fading the market works.

---

## 4. Scheduler status

From prompt 01's `src/monitoring/scheduler.py`, measured from stored timestamps:

| horizon | fixtures covered | % of 318 kicked-off |
|---|---:|---:|
| T-6h | 274 | 86.2% |
| T-3h | 234 | 73.6% |
| T-1h | 133 | 41.8% |
| T-30m | 49 | 15.4% |
| T-10m | 30 | **9.4%** |

Odds are pre-match only and unbackfillable, so each uncovered fixture is a closing price lost
permanently — and the close is what CLV is measured against, which makes this the same problem as
section 2's thin CLV sample seen upstream.

Cause is structural: `pro_collect` samples 2-hourly and observed median spacing is 114.1 min.
Section 4's ~10-minute target during high activity is not met and cannot be met by this design.

**Separately, a contention experiment is running.** v9's own workflows fire at roughly 43% of
their configured rate at best, and fell to ~12% after 2026-08-26. Pro's two loop-holding jobs were
cut to single sweeps on 2026-08-30 to test whether they were starving the shared account; see
`OUTPUT_ARCHITECTURE_HARDENING_REPORT.md` section 2.8. **Re-measure before changing any cadence**,
because if v9's schedule recovers the whole collection picture changes.

---

## 5. Live status

**There is no live odds capability yet, and v9 cannot provide one.** Audited rather than assumed:
`inplay_snapshots.csv` is score/SOT state and `live_games.csv` holds *model* fair odds, not
bookmaker prices. API-Football `/odds/live` via `pro_live_odds.yml` is the only route. The
collector is written and was verified against the live API (216 rows, 5 fixtures, median odds age
25.6s) but has never persisted a row — it needed `APIFOOTBALL_KEY`, added 2026-08-30.

Section 6's live research is therefore **blocked on data, not on modelling**, and the correct
state is to wait for the first real sweeps rather than build a live layer against nothing.
`LIVE_PRICE_IMPROVEMENT` remains undefined until then, and must never be called CLV.

---

## 6. Builder and 1X2 status

**Builder** — canonical storage landed in prompt 01: `combo_candidates`, `combo_legs`,
`combo_dependencies`, `combo_settlements` (ACTIVE), `combo_price_snapshots`
(`SOURCE_REQUIRED` — no bookmaker builder price is collected anywhere, and a component product is
not one). Dependency-aware joint probability preserved; `offered_odds`, `model_edge` and `profit`
are NULL rather than 0.0. Remains PAPER/RESEARCH. A live `combo_id` defect that was discarding
~250 distinct combos per settle pass, and sending duplicate tips, was fixed in the same pass.

**1X2** — `train_1x2.py` exists, is committed, and produces `model_1x2_eval.csv` with LogLoss,
Brier, RPS and their baselines. Current result: USA MLS and China Super League both
`beats_baseline = False`. It is **scheduled in no workflow**, so it refreshes only when a human
runs it — the same defect the repo fixed for `news_impact` in August. Applying section 2's
residual→movement question to H/D/A with fixture-level clustering is not started.

---

## 7. Critical DQ failures

1. **Market-price series noise** (section 0). A price-only coefficient of +0.9968 means the series
   nearly fully reverts against its own noise hour to hour. Every movement, CLV and lead/lag
   result inherits this. **Highest-priority fix in the whole plan.**
2. **CLV covers 138 fixtures**, `clv_pct` 61.5% populated. Below every section 10 threshold.
3. **T-10m coverage 9.4%** — permanent, per fixture, unrecoverable.
4. **Three canonical tables empty pending first credentialed run**: `team_match_stats`,
   `team_news`, `live_odds_snapshots`.
5. **v9's `model_sha` is not a version** — mitigated Pro-side, but any *other* consumer of v9's
   `predictions.csv` still reads the churning value.

---

## 8. Bookmaker lead/lag plan (P1, not started)

Section 3 needs bookmaker identity per quote. `market_snapshots` carries `bookmaker` and
`n_books`, so the raw material exists. The plan, in order:

1. Fix the price series first (section 7.1) — lead/lag measured on a noisy consensus will find
   whichever book happens to be quoting, not whichever moves first.
2. Classify books REFERENCE / CONSENSUS / SOFT-SECONDARY / UNKNOWN **from evidence** — lead
   frequency, closeness to the final price, overround — never from reputation.
3. Only then test whether movement sequences look like V9 → reference → consensus → soft.

---

## 9. Next five priorities

1. **Fix the market-price series.** Fixed book panel or a stable consensus subset, so a "move" is
   a price change and not a change in which books were quoting. Everything downstream inherits it.
2. **Read the runner-contention experiment**, then decide cadence. If cutting Pro's loops restores
   v9's schedule, that is worth more than any Pro-side tuning.
3. **Confirm the three empty tables populate** after the credential addition — one CI run each.
4. **Grow clean CLV toward 500 fixtures**, which is section 10's first checkpoint and currently
   the binding constraint on every claim in this document.
5. **Schedule `train_1x2.py`** and extend the momentum-control regression to H/D/A with
   fixture-level clustering.

---

## 10. What this plan deliberately does not do

No V9 model change. No retuning of residual thresholds, odds bands, league filters or time windows
to make history look profitable. No promotion of any segment. The negative result in section 0 is
recorded as evidence and left standing — section 12 forbids fixing negative results, and the
honest reading is that we do not yet have the sample, or a clean enough price series, to answer
the question the phase was built to ask.

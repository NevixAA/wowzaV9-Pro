# AGENT 11 - Professional Benchmark

**Run date:** 2026-09-10 | **Scope:** benchmark Wowza against realistic, publicly documented
professional betting-syndicate practice. Score DATA, MODELING, EXECUTION, RESEARCH,
INFRASTRUCTURE, ADAPTIVE LEARNING out of 10.
**Discipline:** every number below was computed this run from the estate's own files, or read at a
cited `file:line`. Sample rule: n<50 is not evidence, n<250 does not justify a parameter change.

---

## HEADLINE

**The one KPI that could tell this estate whether it has an edge before P&L converges - closing
line value - is broken in the direction that flatters the system by roughly 70x. The stored CLV
series reads +15.03% mean; restricted to physically possible rows it is +0.22% with a 95% CI of
-0.56% to +1.01%, i.e. zero.** Two independent contamination channels in
`v9/update_results.py` produce it, and the dashboard already compensates for the symptom without
anyone having fixed the source. Separately, the audit seed's diagnosis of the staked-tier defect
is **refuted**: production has not used `MARKSMAN_THRESHOLD = 0.14` since 2026-08-21, and 79% of
the standard MARKSMAN loss comes from bets that *did* clear the operative floor.

---

## SCORECARD

| Dimension | Score | One-line justification (all measured) |
|---|:--:|---|
| DATA | **6/10** | 1,622,660 rows / 20 canonical tables with git+model SHA provenance per prediction row - but 33.1% of stored closing prices are physically impossible and 18.4% are the bet price copied. |
| MODELING | **4/10** | Right target function (market-relative logloss), correct chronological splits, standard/new-format isolation real - but the residual coefficient collapses from +1.2306 (p=0.0) to +0.00089 (p=0.232) once price velocity is controlled, and v9 never de-vigs, so the whole tier ladder is denominated in overround. |
| EXECUTION | **3/10** | -91.63u on 1,159 settled bets (-7.9%); flat 1u with Kelly off is the correct call while edge is unproven - but price-taking is unoptimised and worth a measured +0.72pp/side today, +1.80pp/side at 5+ books. |
| RESEARCH | **8/10** | Genuine pre-registration with fixed falsification conditions, a placebo battery built to kill the house thesis (and it did), six documented kill decisions. Top-decile for a solo operation. |
| INFRASTRUCTURE | **5/10** | ~28 automated workflows, per-file commits, self-expiring override flags - but **no CI job runs the test suite**, and 6 of 10 files in `v10/tests/` contain zero pytest-collectable tests. |
| ADAPTIVE LEARNING | **3/10** | Retrain does not gate; and the one adaptive loop wired to live money moved a threshold 375% in seven days, which is the signature of fitting noise. |

**Weighted read:** this is a research estate with production attached, not a production estate with
research attached. The research and provenance layers are close to professional. The
decision-and-execution layer is where the units are being lost, and it is the layer with the least
measurement discipline applied to it.

---

## FINDINGS

### F1. ANSWERED: why edge_pct sits far below MARKSMAN_THRESHOLD - neither of the seed's two hypotheses (PROVEN)

The seed asked: *"why is edge_pct ~9% on rows tiered SNIPER (needs 0.15-0.25)? Either edge_pct is
recorded at settlement not at tip time, or tiering uses a different best_edge."*

**Neither. `config.py` is not the operative configuration.**
`v9/.github/workflows/predict.yml:190-192`:

```yaml
LEAGUE_SNIPER_CAP: "0.12"
MARKSMAN_THRESHOLD: "0.08"
VALUABLE_THRESHOLD: "0.03"
```

All three are `os.getenv`-backed in `config.py:281-285`, and `LEAGUE_SNIPER_CAP` is applied as
`min(v, _SNIPER_CAP)` over every entry of `LEAGUE_SNIPER_THRESHOLDS` (`config.py:329`). So since
**2026-08-21** the live gates have been SNIPER 0.12 (all leagues, capped down from 0.14-0.25),
MARKSMAN 0.08, VALUABLE 0.03 - not 0.14. On top of that `models/best_params_standard.json`
supplies still lower per-league floors for any league flagged `approved`, read *ahead of* config at
`src/betting.py:154-156` and `185-186`: Championship has run at **sniper 0.07 / marksman 0.05**
since 2026-09-01.

`edge_pct` is written together with `signal_tier` in the same statement, on first insert
(`src/ledger.py:198-199`) and on re-see upgrade (`src/ledger.py:174-177`). It is **never** written
at settlement. So the seed's first hypothesis is false and the 6.11% median *is* the edge the tier
decision was made on. It only looks anomalous when compared to a threshold that has not been in
force for three weeks.

Two real defects sit underneath:

* **The ledger tier is a max-ratchet, not a decision.** `ledger.py:169` upgrades on a stronger
  tier and never downgrades, so a fixture polled every 5 minutes for up to 7 days records the
  **maximum tier over ~2,000 draws**. `generated_at` is left at first sighting, so the row's
  timestamp is not the run that set its tier - which is how row 4989 (Championship, generated
  2026-08-31, edge 5.22%) is MARKSMAN: it was re-tiered after the 2026-09-01 optimizer dropped
  Championship's marksman floor to 0.05. A single ledger row can therefore straddle two threshold
  regimes.
* **`odds` is not updated on upgrade** (`ledger.py:171-173` only *reads* `cur_odds`). After an
  upgrade the row pairs a first-sighting price with a later-run edge. Any EV or ROI computed from
  the `(edge_pct, odds)` pair in this file mixes two snapshots.

`predict.yml:166-168` already carries the correct warning ("from 2026-08-21 the ledger mixes TWO
tier regimes; any ROI or CLV comparison spanning this date must split on it"). The seed's analysis
did not split on it. Neither does the success-rates page.

### F2. REFUTED: the asymmetric drift guard is not where the money went (PROVEN)

Seed: *"Of 38 staked standard MARKSMAN bets, 37 (97%) had edge_pct BELOW 14% ... those 37 are
-12.78u (-34.5% ROI). They arrive via `_apply_drift_adjustment`, and the guards are ASYMMETRIC."*

"97% below 14%" is true and **expected by construction** - the operative floor is 0.08 (F1), so
below-14% MARKSMAN rows are the normal case, not the defect. Splitting at the *operative* floor
instead, on live settled rows with `match_date >= PERFORMANCE_CUTOFF_DATE` (2026-08-10):

| arrival path | n | P/L | ROI | drift mix |
|---|--:|--:|--:|---|
| edge < 0.08 - only reachable via the floorless VALUABLE->MARKSMAN upgrade | 25 | **-2.92u** | **-11.7%** | Confirmed 20, Conflicted 3, New 1, Neutral 1 |
| edge >= 0.08 - **cleared the operative floor**, legitimate base MARKSMAN | 13 | **-10.86u** | **-83.5%** | Conflicted 10, New 2, Neutral 1 |
| total staked standard MARKSMAN | 38 | -13.78u | -36.3% | |

**79% of the loss (-10.86 of -13.78u) is in the cohort that passed every gate.** Closing the
asymmetric guard would have removed 25 of 38 bets and recovered 2.92u of a 13.78u hole. The seed's
proposed fix targets the wrong two-thirds of the sample.

The guard asymmetry is still a real design flaw worth fixing on its own merits - with VALUABLE at
0.03, `betting.py:211-213` promotes a **3.0% edge to a three-quarter stake** with no floor
whatsoever, while the reverse promotion at `208-210` demands 0.10. But it is a tail-risk fix, not
the leak.

Sample discipline: n=13 and n=25 are both far below the n<250 bar. **INSUFFICIENT_DATA for any
threshold change in either direction.** What is established is the *attribution*, not a new
parameter. (Standard SNIPER post-cutoff is n=4 at +0.5u - report it as INSUFFICIENT_DATA and
nothing else.)

### F3. CLV - the professional KPI - is contaminated ~70x in the flattering direction (PROVEN)

Computed on `v9/output/bets_ledger.csv`, `source == "live"`, settled (WIN/LOSS), n=788:

| metric | value |
|---|--:|
| rows with a stored closing price | 681 (86.4%) |
| of those, `closing_odds` **byte-identical** to the bet price | 125 (18.4%) |
| genuinely different | 556 |
| **mean CLV on those 556** | **+15.03%** (95% CI +11.45 .. +18.62) |
| rows with abs(CLV) > 20% - impossible for a pre-match OU2.5 line | **184 (33.1%)** |
| rows with abs(CLV) > 50% | 170 |
| `closing_odds` max | **11.0** vs a bet-odds ceiling of 6.0 (`MAX_OU_ODDS` bounds the main line) |
| **CLV restricted to abs(CLV) <= 20% (n=372)** | **+0.222%, 95% CI -0.561 .. +1.005** |
| ...standard only (n=112) | +0.434% |
| ...new-format only (n=259) | +0.148% |

The contaminated series says new-format beats the close by **+18.76%**; the plausible subset says
**+0.15%**. Examples are diagnostic of the mechanism - UNDER 2.5 taken at 2.30 with a "closing"
price of 1.25 (CF Montreal v Toronto), at 1.96 closing 1.22 (Vitoria v Vasco), at 2.80 closing
1.40 (Seattle v Portland). An UNDER 2.5 at 1.20-1.25 is not a pre-match price; it is a **0-0 at
the 70th minute**. The "closing" line is in-play, captured on the side that was winning, which
manufactures large positive CLV precisely on the bets that won.

Root cause, two independent channels, both read this run:

1. **`update_results.py:258-283` `_closing_for_market`** filters on match **date** and market, then
   takes `sort_values("snapshot_ts").iloc[-1]`. There is **no comparison against kickoff time**.
   Any same-calendar-day post-kickoff snapshot becomes "the close". (Seed: 5.4% of odds
   observations are post-kickoff.)
2. **The same function, lines 276-277**, falls back on name-match failure to `_names_match`, the
   substring / first-word matcher - applied to a frame filtered only by date and market. It can
   therefore attach a *different fixture's* price. This is the exact failure mode root
   `CLAUDE.md` invariant 11 was written about ("a naive `startswith(first_word)` mapped
   `Real Valladolid CF` onto any club starting 'Real'"), reintroduced in the CLV path. It explains
   a `closing_odds` of 11.0 on a two-way market.
3. `_closing_odds_json:330` takes `snapshots[-1]` with no kickoff filter either, despite a
   docstring promising "the LAST recorded odds snapshot **before kick-off**".

**Fair in the other direction:** the dashboard already knows.
`v9/pages/1_Dashboard.py:298-320` applies `_PLAUS = 25.0`, separates flat rows from moved rows,
reports the **median** not the mean, and its help text states the raw mean is "inflated by
impossible closing prices". That comment is exactly what a professional data-quality note looks
like. But `telegram_bot/notifier.py:703-710` `_sharp_split_lines` splits sharp-confirm vs
sharp-disagree on **raw unfiltered `clv_pct > 0` / `< 0`**, so the weekly Telegram summary has been
classifying the 170 abs(CLV)>50% rows as sharp confirmations. One surface filters; the other does
not; the source is unfixed.

**Consequence for the edge thesis:** the estate's own best-available CLV measurement, cleaned, is
**zero within noise**. That independently corroborates the -91.63u P&L and the v11 placebo result
by a third, unrelated route. Three independent measurements now agree.

### F4. The model contributes nothing once the price's own velocity is controlled (PROVEN)

Read from `wowza-v11/output/v11_momentum_control.csv` (60min prior / 60min future window):

| spec | `residual_pp` coef | p | n_obs |
|---|--:|--:|--:|
| residual only | **+1.2306** [1.145, 1.320] | **0.0** | 36,107 |
| + momentum controls | +0.00095 [-0.00028, +0.00216] | 0.15 | 10,911 |
| + full controls | +0.00089 [-0.00051, +0.00235] | 0.232 | 8,546 |

A **~1,300x collapse**. And in every controlled spec the only stable, significant, sign-consistent
term is `velocity_pp_h` at **-0.2384 [-0.2531, -0.2205], p=0.0** - a *negative* coefficient on the
price's own recent velocity, i.e. mean reversion in the price series. The seed's mechanism claim is
correct and now has a coefficient attached: the entire apparent "our residual predicts where the
market moves" effect is the price series' autocorrelation, and the residual adds 0.0009 with
p=0.23 on top of it.

Labelling hazard (PLAUSIBLE, not proven): the *uncontrolled* spec that shows the huge significant
effect carries `sample_status = VALIDATABLE`, while every controlled spec that annihilates it
carries `RESEARCH`. The label almost certainly tracks sample size and window coverage rather than
credibility - but a reader skimming for "VALIDATABLE" rows would come away with exactly the wrong
conclusion. Worth a note in the column's docstring.

### F5. Price-taking is unoptimised, and it is the single largest measured gain available (PROVEN)

Computed on `v9/output/book_odds_snapshots.csv`, market OU25, 24 real bookmakers:

| basis | overround (median) | vs single book |
|---|--:|--:|
| single book (n=33,523 two-sided book-quotes) | **1.0696** | - |
| best-of-available (n=12,748 groups, median 2 books) | **1.0552** | **+0.72pp edge per side** |
| best-of-available, groups with >=5 books (n=2,457) | **1.0337** | **+1.80pp edge per side** |

Books per snapshot-group: median 2, mean 2.7, p90 6, max 17.

This is the professional baseline this estate most clearly fails: a syndicate takes the best of N
books as a matter of course, and it requires **no model improvement at all**. At -7.9% ROI over
1,159 bets, a systematic +1.8pp of price recovers roughly 23% of the loss *rate*.

**But be honest about what is reachable today:** only **19.3%** (2,457/12,748) of two-sided groups
carry >=5 books, so the achievable-now figure is the **+0.72pp**, not +1.80pp. The
`predict.yml:163` comment claiming "taking the best of ~12 books halves the margin (7.74% ->
3.19%)" is directionally right but overstates what today's book coverage supports by about 2.5x -
3.19% is the >=5-book number, available on a fifth of the board. Widening book coverage is a
prerequisite for the headline figure, not a consequence of it.

### F6. The only adaptive loop wired to live money is fitting noise (PROVEN)

`src/betting.py:154-156` and `185-186` read `models/best_params_standard.json` **ahead of** the
hand-set config for any league flagged `approved`. That file is rewritten and auto-committed by the
monthly backtest ("auto: parallel backtest"). Three consecutive revisions, recovered from git:

| league | 2026-07-26 | 2026-08-02 | 2026-09-01 | sniper_th swing |
|---|---|---|---|--:|
| Bundesliga 2 | sn0.04 mm0.04 oos-8.48 | sn0.19 mm0.17 oos+4.57 | sn0.18 mm0.16 oos-8.50 | **375% of min** |
| Championship | sn0.24 mm0.22 oos n/a | sn0.08 mm0.06 oos-7.90 | sn0.07 mm0.05 oos+3.32 **APPROVED** | **243%** |
| League Two | sn0.20 mm0.18 oos n/a | sn0.07 mm0.05 oos-19.07 | sn0.07 mm0.05 oos-19.15 | **186%** |
| Serie B | sn0.05 mm0.04 oos+8.53 **A** | sn0.13 mm0.11 oos+13.01 **A** | sn0.12 mm0.10 oos+17.02 **A** | **160%** |
| League One | sn0.22 oos-100.0 | sn0.14 oos-27.75 | sn0.14 oos-59.0 | 57% |
| Ligue 2 | sn0.10 oos n/a | sn0.12 oos+1.72 **A** | sn0.12 oos-5.27 | 20% |
| La Liga 2 | sn0.16 oos-6.63 | sn0.17 oos-12.88 | sn0.17 oos-5.84 | 6% |

* Bundesliga 2's "optimal" SNIPER threshold moved **0.04 -> 0.19 in seven days**. Serie B moved
  0.05 -> 0.13 in the same seven days. A parameter that swings 160-375% of its own value between
  consecutive fits of largely overlapping data is fitting noise, by definition.
* The `approved` flag flipped in **3 of 7** leagues, with the OOS ROI **sign** flipping with it:
  Ligue 2 +1.72 (approved) -> -5.27 (revoked); Bundesliga 2 +4.57 -> -8.50; Championship -7.90
  (rejected, n_oos=311) -> +3.32 (approved, n_oos=**164**). The approval that mattered most came
  with a sample that nearly halved.
* Consequence: since 2026-09-01, Championship - the highest-volume standard league - has been
  betting SNIPER at **0.07** and MARKSMAN at **0.05**, thresholds set by a fit that reversed its
  own verdict one month earlier on twice the data.
* This is an **automated retrospective re-tuning of live betting thresholds**, on a repo declared
  FROZEN (invariant 3) and under a no-retrospective-tuning rule (invariant 6). Nobody approves it;
  a cron does.

This is the highest-value single intervention in the estate: it is a *deletion*, it costs hours,
and it does not require the edge thesis to be resolved first.

### F7. The test suite does not run, and it contains the promotion gate (PROVEN)

* `grep -rln "pytest|pro_tests|tests/"` over `v10/.github/workflows/` returns **exactly one hit**:
  `pro_bet_builder.yml:70 -> python -m src.combo.tests`, which gates Bet Builder only. **No CI job
  anywhere runs `v10/tests/`.**
* 6 of the 10 files in `v10/tests/` contain **zero** pytest-collectable tests - no `test_*`
  function, no `Test*` class, and there is no `conftest.py`, `pytest.ini`, `pyproject.toml` or
  `setup.cfg` in the repo. `test_market.py`, `test_validation.py`, `test_registry_gates.py`,
  `test_season_store.py`, `test_imputers_calibration.py` and `test_drift_experiment.py` are
  `main()` scripts with a private `check()` helper and an `if __name__ == "__main__"` block.
* So the command CLAUDE.md documents - `python -m pytest tests/` - collects **18 tests from 3
  files** (`test_combo_canonical` 7, `test_hardening_1_5` 8, `test_scheduler` 3) and **exits 0
  while silently executing none** of the market, validation, registry-gate, season-store,
  calibration or drift suites. A green pytest run here is not evidence.
* Confirming the seed on the gate: `.promote(` and `Registry(` appear **nowhere** in `v10/src/`.
  `evaluate_gate` (`src/models/registry.py:133`) is reached only from `Registry.promote()`
  (`:239`), which is called only by `tests/test_registry_gates.py` - one of the six files pytest
  cannot collect. The champion/challenger gate is dead code guarded by a test that never runs.
  (Note for precision: `src/pipelines/registry.py` is a *different* module - an artifact/freshness
  registry - and it *is* imported by `weekly_audit`, `experiment` and `pro_tests`. Do not conflate
  the two.)

### F8. What this estate does better than most professional shops (PROVEN, and it should be said)

* **Pre-registration that actually binds.** `v10/docs/PREREGISTERED_HYPOTHESES.md` fixes the
  statistic, cut points, sample definition, decision threshold and falsification condition before
  the data exists, and adds the rule that cut points are *literals read from the file* and never
  recomputed on the new sample - "recomputing quartiles on new data silently changes the test into
  a different one that happens to share a name". That is the single practice separating
  professional from amateur quant research, and it is rare even in funded teams.
* **Documented self-correction.** The same file records a wrong reading and who corrected it
  ("That reading was **wrong**, and the correction came from the user pointing out we have almost
  no live data"), and labels its own stratification "both post-hoc".
* **A placebo battery built to kill the house thesis, which then killed it** and was kept anyway
  (F4). Most operations do not build the test that can end their project.
* **Row-level provenance.** `v9/src/provenance.py` stamps `generated_at`, `git_sha` and
  `model_sha` on every prediction row, explicitly so that "which model version generated this?" -
  "the first question any deployed signal has to be able to answer" - is answerable. Many
  commercial systems cannot answer it.
* **Self-expiring overrides.** `betting.py:388` `REQUIRE_FORM_DATA_UNTIL` re-arms a safety guard on
  a hard date "whatever this flag says... The override cannot outlive its reason". Better
  feature-flag hygiene than most commercial code.
* **Kills are recorded and honoured.** Weather, Understat xG, corners/cards O/U, prop edge, combo
  structure, 1X2 - six documented dead ends with "do not re-pursue". Retaining negative results is
  a top-decile habit.
* **Scale with structure.** 1,622,660 rows across 20 partitioned canonical tables, including
  `data_quality` as its own 1,522-row time series (quality is monitored, not assumed) and
  `movement_observations` at 691,123 rows.

---

## WHAT A 10 LOOKS LIKE, CONCRETELY

**DATA 10** - a true closing line per bet from one reference book (Pinnacle or equivalent),
captured inside T-5m, at >99% coverage of staked bets, with a second independent source for
reconciliation; a physical-plausibility assertion (`abs(CLV) <= 25%`, `closing_odds` inside the
market's possible range, `snapshot_ts < kickoff_utc`) that **fails the pipeline** rather than being
filtered in a dashboard; and no substring team matcher anywhere in a price-join path.

**MODELING 10** - the de-vigged multi-book consensus is the baseline; the model enters only as a
bounded residual with a pre-registered cap; promotion requires beating that baseline out-of-sample
on logloss with a pre-committed minimum sample; and edge is computed against a fair price, never a
raw one. (Today `betting.py:246-249` computes `edge = p_model - 1/odds` on the raw quote, so with a
~7% overround roughly 3.5pp is charged to the model on each side before it is consulted - a
perfectly calibrated model reports about -3.5% both ways, and the tier ladder is measuring vig.)

**EXECUTION 10** - best-of-N across >=8 books with per-book stake limits modelled; fractional Kelly
on a de-vigged edge with a pre-committed drawdown rule; CLV as the go/no-go gate before P&L has
converged; and the operative configuration living in one versioned place rather than split between
`config.py`, a workflow `env:` block and an auto-committed JSON.

**RESEARCH 10** - every live parameter traceable to a pre-registered test, and the pre-registration
file **read mechanically by the code that acts on it** so a threshold cannot drift away from its
registered justification. This estate is close: it has the file and the discipline; F6 is what
happens where the wiring is missing.

**INFRASTRUCTURE 10** - tests run on every push and block the merge; a model file can become live
only by passing the promotion gate; and no workflow requests more runs per day than the platform
delivers (predict asks 57/day and gets ~15%).

**ADAPTIVE LEARNING 10** - every parameter change gated on a pre-registered OOS improvement with a
minimum sample, versioned and reversible, with the prior value's *live* performance recorded before
the swap - so a 0.04 -> 0.19 -> 0.18 sequence could not reach production without someone seeing all
three numbers side by side.

---

## RECOMMENDED ORDER (cost-weighted, no edge resolution required)

1. **HOURS.** Stop `models/best_params_standard.json` feeding live tiering (F6): ignore `approved`,
   or require a minimum OOS sample and threshold stability across two consecutive fits. It is a
   deletion and it is the clearest measured noise-fit in the estate.
2. **HOURS.** Add `snapshot_ts < kickoff_utc` to `_closing_for_market` and `_closing_odds_json`, and
   remove the `_names_match` substring fallback from the price path (F3). Then recompute the whole
   CLV series and treat the cleaned +0.22% [-0.56, +1.01] as the operative number.
3. **HOURS.** Make `telegram_bot/notifier.py:703-710` use the dashboard's plausibility filter, so
   the two surfaces stop disagreeing.
4. **DAYS.** Rename the 6 script-style test files' entry points to `test_*` (or add a
   `test_main()` wrapper), add a `pytest` job to Pro CI, and wire `Registry.promote()` into the
   training pipelines (F7).
5. **DAYS-WEEKS.** Build best-of-N price selection on `book_odds_snapshots` and widen book coverage
   past the 19.3% of groups that currently carry >=5 books (F5). This is the only lever measured to
   improve economics without the edge thesis being settled.

## DO NOT BUILD

* **Anything that treats the seed's -34.5% MARKSMAN figure as a threshold-tuning problem.** F2
  shows 79% of that loss cleared the operative gate; n=13 and n=25 cannot support a parameter
  change in any case.
* **Any CLV-conditioned logic** (v11's `MIN_CLV_N`/`clv_n` gates, CLV-weighted staking, sharp
  confirm/disagree filters) until F3 is fixed. Right now they would be conditioning on in-play
  prices and cross-fixture mismatches.
* **A bigger odds plan or more API spend.** The Odds API is at 89,842/100,000 with no headroom and
  API-Football at 3% of 75,000 - the binding constraints are workflow wall-clock and whether a
  consumer exists, and F5's uplift needs *breadth of books at the moments already sampled*, not
  more calls.
* **Any player-props betting proposal.** Invariant 2. Not revisited here.
* **Retraining on odds** to close the residual gap. It would collapse the residual to zero by
  construction and destroy the only quantity being measured.

## OPEN QUESTIONS

1. Does the cleaned CLV stay at zero once the kickoff filter and the name-match fix are applied to
   the *whole* series? +0.22% on n=372 has a CI that admits +1.0%, which on a 7% overround market
   would be meaningful. This is the cheapest decisive test in the estate.
2. Is the 18.4% of rows where `closing_odds == odds` a genuine flat line or a missing observation?
   The dashboard comment at `pages/1_Dashboard.py:298-303` says the author tried and could not
   separate them, and that stripping the zeros swings the positive rate from 36.5% to 51.0%.
   `book_odds_snapshots` (143,799 rows, real per-book timestamps) may now answer what the pruned
   `odds_history_v9.json` could not.
3. Which threshold regime is each staked row's tier actually from? The max-ratchet plus the
   2026-08-21 env change plus the 2026-09-01 optimizer commit means a single row can straddle
   three. Every economic table in this audit round inherits that ambiguity, including mine.
4. Why did the Championship OOS sample fall from 311 to 164 bets between two monthly fits one month
   apart, while the ROI flipped sign? A shrinking OOS window on a growing dataset is backwards and
   suggests the optimizer's sample definition is itself unstable.

# PROMPT 2 — TARGETED COLLECTION HARDENING REPORT

Pass of 2026-09-07/08. Targeted operational work only. No architecture redesign, no V12, no
change to V9 predictive logic.

---

## Changes made

| repo | file | why |
|---|---|---|
| v9 | `.github/workflows/std_odds_capture.yml` | NEAR-mode selection was unreachable; inverted the test |
| v9 | `.github/workflows/nf_odds_capture.yml` | same defect, same fix |
| v9 | `update_results.py` | crash on every unpriced prop (10 consecutive failed runs) |
| v9 | `.github/workflows/update_results.yml` | `if: always()` — the crash was discarding work that had succeeded |
| v11 | `src/research_state.py` | classify counts CUMULATIVE vs RE_DERIVED; explain the CLV recount |
| v11 | `scripts/v11_momentum_control.py` | §9–13 full control set, 4-way classification, placebo battery, chronological folds |

Commits: v9 `87c9104c`, `7acadf7a`; v11 `a18411d`, `4ed8aa9`.

---

## Root cause — why near-kickoff observations remained sparse

**Two causes. The first is a bug; the second is why the headline metric misleads.**

### 1. The NEAR branch has been unreachable since 2026-08-29

Both capture workflows chose between NEAR (12h window, internal sampling loop) and WIDE (every
look-ahead fixture, single pass) by string-matching a cron:

```
std:  github.event.schedule == '*/15 * * * *'       -> NEAR
nf:   github.event.schedule == '7-59/15 * * * *'    -> NEAR
```

Those crons were replaced on 2026-08-29 (96/day → hourly) and again on 2026-09-02
(kickoff-aligned). **The comparison strings were never updated.** GitHub sets
`github.event.schedule` to the exact cron that fired, so once those strings stopped existing the
test could never be true: `MH` stayed empty, every scheduled run took the WIDE branch, and the
loop that produces T-1h / T-30m / T-10m density became unreachable on any schedule.

Corroborated in the data: `standard_sidemarket_odds_history.csv` contains **no loop-spaced
capture (≤10 min apart) since 2026-08-23**.

This is also, directly, the 80% far-horizon allocation the brief asks about. WIDE prices the whole
look-ahead board on every firing, so far-future fixtures dominate by sheer count.

Two things it invalidates, stated plainly:

* **My own 2026-09-02 kickoff-clock realignment could not have worked.** The aligned slots fired,
  then ran WIDE. Delivery even improved (std 5.0 → 8.3 runs/day, nf 6.0 → 10.1) while T-10m
  coverage fell — the contradiction that exposed the bug.
* **The 2026-09-05 change raising `LOOP_MIN` from 25 to 40 was tuning a branch nothing could
  reach.**

**Fix:** the test is inverted — match the WIDE cron explicitly, treat every other scheduled firing
as NEAR. That fails *safe*: editing the wide cron thins the far horizon instead of deleting the
close. The chosen mode is echoed into the run log. Verified by simulating every configured cron:

```
std '5 0,6,12,18 * * *'    -> WIDE      std '23,52 0-3,9-23 * * *' -> NEAR
nf  '35 1,7,13,19 * * *'   -> WIDE      nf  '20,50 0-3,9-23 * * *' -> NEAR
manual dispatch, no max_hours          -> WIDE
```

### 2. The share-of-observations metric is confounded

Horizon allocation as a *percentage of observations* is dominated by how many fixtures exist at
each horizon, not by scheduler quality. Measured per day:

| day | far | T-6h | T-1h | T-30m | T-10m | n |
|---|---:|---:|---:|---:|---:|---:|
| 09-03 | 95.0% | 0.3% | 0.0% | 0.1% | 0.0% | 5,005 |
| 09-04 | 71.9% | 2.0% | 0.2% | 0.4% | 0.0% | 3,198 |
| **09-05 (Sat)** | **51.6%** | 9.8% | 2.4% | 1.7% | 0.3% | 4,895 |
| **09-06 (Sun)** | 68.3% | 3.0% | 1.3% | 1.6% | 0.1% | 4,974 |
| 09-07 | 94.1% | 0.0% | 0.0% | 0.3% | 0.0% | 1,189 |

The two "good" days are Saturday and Sunday. On a dense fixture day a WIDE sweep incidentally
catches more near-kickoff fixtures, so the share improves without the scheduler changing at all.
**Per-fixture coverage is the honest metric** — did *this* fixture get an observation inside
T-10m — and that is what `high_activity_coverage.json` reports. The share-of-observations figure
should not be used as the success criterion (§22: do not fake improvement by redefining a metric,
and equally, do not chase one that moves for the wrong reasons).

---

## Before

Near-kickoff coverage, 14-day window, 584 kicked-off fixtures:

| horizon | coverage |
|---|---:|
| T-6h | 89.7% |
| T-3h | 71.1% |
| T-1h | 32.9% |
| T-30m | 14.5% |
| T-10m | 7.1% |

Split by whether the fixture kicked off before or after the 09-02 realignment — the split that
exposed the bug:

| horizon | ko before 09-03 (426 fx) | ko after 09-03 (158 fx) |
|---|---:|---:|
| T-6h | 89.4% | 96.8% |
| T-1h | 34.0% | 32.3% |
| T-10m | **8.7%** | **3.2%** |

---

## After — what scheduling behaviour changed

NEAR runs now actually happen. On each delivered NEAR firing the collector samples repeatedly for
~40 minutes with kickoff-aware spacing (2 min inside T-20m, 3 min inside T-45m) and a
kickoff-aware extension bounded by `MAX_LOOP_MIN`.

**No coverage improvement is claimed.** The fix landed 2026-09-07 ~09:00 UTC and near-kickoff
coverage accumulates prospectively. Per §8 this is a baseline, not a result.

### Why this needed no extra polling budget — and the budget correction

The two capture workflows run on **API-Football**, not the Odds API. Current position:

| provider | used | projected month-end | headroom |
|---|---|---|---|
| The Odds API | 23,958 this month | **89,842 / 100,000** | ~10% |
| API-Football | 2,292 today | 3.1% of 75,000/day | **~97%** |

So the near-kickoff loop draws on the budget with 97% spare and **does not touch the constrained
one**. Reallocation here is close to free.

This corrects a figure in my own earlier report: on 2026-09-02 I recorded the Odds API projection
as 44,380/100,000. That reading was taken on day 2 of the month, when a linear month-end
projection is unstable. At day 8 it is 89,842. **The brief is right that Odds API is effectively
at its allowance, and no change in this pass increases Odds API consumption.**

Consequently **no further scheduler change was made**. The Odds-API-funded path is `predict`,
which is v9's live tip engine; raising its cadence would push a 90%-consumed budget over and
destabilise the tip path for a research gain. §0A's minimal-change rule and §18's "do not simply
increase total polling" both point the same way: the lever worth pulling was the broken NEAR
branch, and it is pulled.

---

## Safety verification

| question | answer |
|---|---|
| V9 predictive logic changed? | **NO** — no feature, estimator, calibrator, threshold, ensemble or model artifact touched |
| V9 model artifact changed? | **NO** — `model_content_sha` unchanged by this work |
| Existing collectors disabled? | **NO** — none disabled; one *repaired* |
| Canonical schemas changed? | **NO** — no column added, removed or retyped |
| API budget guards active? | **YES** — `MIN_QUOTA=5000` floor intact in the capture scripts; `alert_at 45000` / `abort_at 60000` intact |
| Notification scope changed? | **NO** — Pro still notifies only bet-builder PAPER tips; no staking |

The two v9 changes are workflow logic and a log-formatting crash. Both are operational bug fixes
under §3's carve-out, and neither can alter a probability.

---

## Tests

* `update_results.py --days 3 --dry-run` → **exit 0**, all five settlement sections complete
  (was: `ValueError` at line 634). Wrote nothing, confirmed by `git status`.
* Every configured cron simulated against the new NEAR/WIDE branch → correct in all five cases.
* All 7 Pro workflow YAMLs and both v9 capture YAMLs parse; step counts unchanged.
* `python -m src.research_state --check` → overall **PASS**, exit 0, writes nothing.
* `scripts/v11_tests.py` → all pass.
* `v11_momentum_control.py` → runs clean after fixing a duplicate-column bug it exposed in itself.
* Pro suite: `test_market`, `test_season_store`, `test_validation`, `test_registry_gates`,
  `test_imputers_calibration`, `test_drift_experiment`, `test_combo_canonical`, `test_scheduler`,
  `test_hardening_1_5`, `src.combo.tests` — **all pass**, no pre-existing failures outstanding.

### A second, larger defect found while testing

`update_results` had failed **10 consecutive runs** since 2026-09-06 19:26.

*Root cause:* the 2026-09-06 change "an unpriced prop has no P&L" correctly sets `pnl = ""`
(invariant 9). Its aggregate handles that properly — line 679 filters `""` before summing. The
per-row log line did not: `f"PnL={pnl:+.3f}u"` → `ValueError: Unknown format code 'f' for object
of type 'str'`. Per invariant 13 most props are never priced, so it raised on roughly the first
prop of every run.

*What it cost:* `update_results.py` settles five ledgers in sequence, saving each as it finishes.
The crash exited 1 and the commit step had **no `if: always()`**, so it was skipped and the
ledgers already written died with the runner. The last failed run had logged
`RESULTS UPDATED — 7 bet(s), PnL +1.490u, CLV +1.46% → SHARP` and `Ledger saved` before dying.
Discarded ten times, while the sections that worked kept working.

Both fixed. Backlog waiting to settle: 36 O/U, **448 player props** (58W/97L/293 VOID), 26 sharp,
24 side-market. This directly restores CLV accumulation, which every §24–25 measurement depends
on.

---

## CLV monotonicity investigation — 670 → 669

**Explained. Not a bug, and nothing was lost.**

`clv_n` is not cumulative. CLV is computed only for fixtures whose price *moved*
(`|move| ≥ MIN_MOVE_PP = 0.2pp`), and for a fixture that has not kicked off the "close" is the
latest snapshot **so far** and keeps updating on every collect. A still-open fixture that retraces
toward its entry falls back under 0.2pp, leaves the moved set, and takes its CLV row with it.

Verified on the 09-03 22:40 → 09-04 01:05 pair, where `clv_n` went 546 → 543:

* `n_fixtures` was **606 in both**.
* At detail level, fixtures carrying a CLV were **624 in both** — no observation disappeared.
* Four fixtures stopped qualifying and one started:

| fixture | league | move before | move after |
|---|---|---:|---:|
| `ef11ebf4` | USA MLS | −0.43pp | **0.00pp** (close returned exactly to entry) |
| `e49c11ff` | USA MLS | −0.22pp | +0.03pp |
| `4f589c89` | Brazil Serie A | −2.12pp | −0.15pp |
| `e536f76f` | Bundesliga 2 | +0.42pp | +0.03pp |

All four kicked off *after* both readings — still open, still re-pricing.

So the metric was right and the **warning** was wrong: it treated a re-derived quantity as an
accumulating one. Counts are now classified, and monotonicity is **not** forced anywhere:

* `CUMULATIVE` — `movement_observations`, `movement_fixtures`, `graded_settled`. A decrease here
  is real (loss, broken join, overwrite) and still WARNs.
* `RE_DERIVED` — `movement_clv_n`, `movement_summary_fixture_n`, `residual_n`. A decrease is
  recorded in a new `expected_recount_deltas` block **with its cause**, so the next reader does
  not re-investigate it.

Current state: `clv_n` 625 and rising (373 on 08-30), `monotonicity_warnings: []`.

---

## Scientific status — §5 preserved, no edge claimed

Extended the controlled experiment rather than the system's flattery.

**Placebo battery (§12)** — every variant scored identically on the same rows:

| predictor | toward-rate | vs V9 |
|---|---:|---:|
| mean reversion (`−prev_move`) | **0.995** | +29.2pp |
| **fixed anchor** (a single constant) | **0.753** | +5.0pp |
| shuffled residual (model attached to wrong fixtures) | 0.711 | +0.8pp |
| **v9_residual** | **0.703** | — |
| market only | 0.501 | −20.2pp |
| random direction | 0.499 | −20.4pp |

**Three predictors containing no football information beat the model.** The fixed anchor beating
it by 5pp independently reproduces the ~57.7% vs ~57.6% the brief already flagged.

*Why:* `p_market(t)` appears in the residual **and** in the future move with opposite signs, so a
noisy "now" reading makes them mirror each other automatically. "Is the price above the middle"
and "will it come back" both answer that better than the model, which adds its own noise without
adding information. v11's own `placebo_toward_rate` docstring named the mechanism first: the
model's probabilities are more *central* than the market's, so "moved toward the model" and
"moved toward the middle" are frequently the same sentence.

**Chronological folds (§13)**, expanding window, never a random split: significant in **0 of 4**.
Controlled coefficient **+0.0002, p=0.90**.

**§11's missing fourth class added.** `WOWZA_NEUTRAL` (residual < 2pp cannot lead anything) cut
`WOWZA_LEADS` from 414 observations to **293** — most of what was labelled "leading" was a quiet
market with a residual too small to act on, inflating the one bucket the price-discovery claim
rests on.

A mean-reversion score of 0.995 is a **measurement verdict**: most of what we record as
snapshot-to-snapshot "movement" is recording noise, not price change.

---

## Remaining limitations

1. **No per-bookmaker identity in the canonical store.** `market_snapshots.bookmaker` holds two
   values (`v9_selected_best`, `v9_capture`) and `book_count` is entirely null. So §6's de-vig
   hierarchy cannot be evaluated, a fixed book panel cannot be built, and §28–30 book lead/lag
   research is **not currently possible** from Pro. v9's `book_odds_snapshots.csv` does carry
   per-book data and is not imported. This is the single biggest blocker on the market-quality
   work and I did not attempt it in this pass — it is a schema addition, and §0A/§0B say to
   propose rather than sneak one in.
2. **Near-kickoff coverage unproven.** Fix deployed 09-07; needs match days.
3. **Odds API at ~90% projected.** No room to increase that path.
4. **`train_1x2.py` scheduled in no workflow** — carried from the previous pass.
5. **`scheduler_health.status` reads FAIL locally** on core-table freshness because this laptop's
   store trails CI by hours. Not an outage; the CI-generated artifact is the authority.

---

## Final verdict

```
RUNNING_REPOS_SAFE                     = YES
V9_PREDICTIVE_LOGIC_UNCHANGED          = YES
COLLECTORS_HEALTHY                     = YES
NEAR_KICKOFF_REALLOCATION_DEPLOYED     = YES
V11_CLV_WARNING_EXPLAINED              = YES
SAFE_TO_CONTINUE_PROSPECTIVE_COLLECTION = YES
```

`COLLECTORS_HEALTHY = YES` is asserted *after* repairing `update_results`, which had been failing
for ~36 hours when this pass began. Pro canonical: **1,234,231 rows across 20 tables**, 19
populated, zero unexpected-empty, zero importer failures. v11 research fresh, overall PASS.

No edge is claimed, and the evidence moved further against one.

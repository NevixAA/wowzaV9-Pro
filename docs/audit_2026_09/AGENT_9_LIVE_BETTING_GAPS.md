# Agent 9 — Live Betting Gaps

Adversarial audit, 2026-09-10. Read-only on `v9/` and `wowza-v11/`. Every number below was
computed this run from the season store, `v9/output/`, or `data/football_data/`, or read at the
cited `file:line`.

---

## Headline

**The live scanner has never observed a market price, and the live price table has never been
joinable to a live signal.** The two datasets live in disjoint key spaces and their fixture
intersection is exactly **0**. So the question "what is the delay between a live signal and an
executable price?" has no answer: no executable price is ever observed, at any delay. The 57
logical live signals are *gradeable* (WIN/LOSS) but not *evaluable* — no entry price, no edge,
no EV, no stake, no P&L. And at n=48 settled with a 95% CI of [0.295, 0.588] around a 43.8% hit
rate, the record cannot distinguish a working scanner from a broken one in either direction.

A correction to the seed while we are here: `side_bets_ledger`'s +18u is **100% pre-match**.
`source=live` is the antonym of `source=backtest`, not "in-play".

---

## Findings

| # | Finding | Evidence | Conf | Impact | Fix |
|---|---|---|---|---|---|
| F1 | Live prices and live signals are in disjoint key spaces. Intersection = 0 fixtures | 0 of 52; 87.2% of live-odds fixtures resolve to no `fixture_key` | PROVEN | CRITICAL | DAYS |
| F2 | The scanner never fetches a market price; the 12% live-edge gate does not exist | `live_scanner.py:7`, `:60` (declared, never referenced) | PROVEN | CRITICAL | WEEKS |
| F3 | In-play resolution is ~1 frame per match — nothing time-varying is measurable | 66.7% of match-days have exactly 1 observation; median span 0 min | PROVEN | HIGH | DAYS |
| F4 | `lam_ht = lam_total/2` overstates first-half λ by 11.8% | H1 share 0.4473, CI [0.4432, 0.4513], n=21,026 matches | PROVEN | HIGH | HOURS |
| F5 | The HT path uses zero in-play evidence — v2's live λ bypasses 56% of signals | `live_scanner.py:617` passes `lam`, not `_lam_rem` | PROVEN | HIGH | DAYS |
| F6 | Asymmetric fair-price band: OVER capped, UNDER uncapped | UNDER tip at model p=0.0513 (fair 19.49) on 2026-09-05 | PROVEN | MEDIUM | HOURS |
| F7 | A null SOT reading becomes 0 and collapses λ_remaining 40–74% | `live_scanner.py:134`, `api_football.py:231`; 12.9% of readings are 0 | PROVEN | MEDIUM | HOURS |
| F8 | 9 of 57 signals never settle; no HT market exists in Pro `settlements` | all 9 PENDING >7d old, oldest 73d | PROVEN | MEDIUM | DAYS |
| F9 | n=48 cannot establish live calibration in either direction | hit 43.8%, CI [0.295,0.588], claimed 0.550 — claim inside CI | PROVEN | MEDIUM | MONTHS |
| F10 | `live_signals` is 95.2% duplicate rows; 7 signals carry conflicting results | 1,182 rows → 57 logical, dup factor 20.7 | PROVEN | MEDIUM | HOURS |
| F11 | Live O/U 2.5 is often not the main live line; 25.0% of prices untakeable | 2.5 on 39.2% of fixtures; takeable 48.9% at minutes 35–45 | PROVEN | MEDIUM | DAYS |
| F12 | Red cards / possession / xG absent from the scanner — and worth less than they look | +0.1161 goals, z=4.0, but only +2.52pp on P(over 2.5) | SUPPORTED | LOW | DAYS |
| F13 | `live_odds_snapshots` has no `league` column and no league filter | 1,323 fixtures in 11 days = the whole world; 20 in-scope | PROVEN | LOW | HOURS |

---

## F1 — The join does not exist (CRITICAL, PROVEN)

`live_odds_snapshots` and `movement_observations` are keyed on `fixture_id` **only**. Every
decision and outcome table — `live_signals`, `signals`, `settlements`, `clv`, `fixtures`,
`market_snapshots`, `feature_snapshots`, `model_snapshots`, `book_odds_snapshots` — is keyed on
`fixture_key` **only**. A bridge carrying both columns exists in exactly two tables:
`team_match_stats` and `team_news` (3,365 distinct pairs).

Building that bridge and applying it:

```
live_odds distinct fixture_id:                  1,323
  resolvable to a fixture_key:                    170  = 12.8%
  ORPHANED (no fixture_key anywhere in Pro):    1,153  = 87.2%
rows resolvable:                    7,895 / 56,478     = 14.0%
of the 170 resolvable, present in `fixtures`:      49  = 3.7% of 1,323
```

So a live-price fixture that can be walked all the way to a league, a kickoff and a `model_type`
exists for **49 of 1,323 fixtures (3.7%)**.

The decisive test:

```
live_signals distinct fixture_key:                 52
live_odds fixture_keys (after bridge):            170
INTERSECTION:                                       0
signals dated in the live-odds era (>= 2026-08-30): 9
  of those, with a live price:                      0
```

Not one live signal in the scanner's history has a matching live price row. The collector at
`v10/src/live/collector.py` writes `fixture_id` because it reads API-Football's `/odds/live`
payload directly; nothing maps it through the resolver that `team_match_stats` already uses.
This is the single highest-value repair in my remit: it is a column, not a model.

The seed's row count is also stale — the table is 56,478 rows across 44 files now, not ~49k.

## F2 — There is no market price, therefore no edge (CRITICAL, PROVEN)

`v9/src/live_scanner.py:7`:

> `No live odds API needed — we calculate the FAIR live price and alert the user`

`v9/src/live_scanner.py:60`:

```python
MIN_LIVE_EDGE     = 0.12   # 12% edge threshold for live alerts (higher bar than pre-match)
```

`MIN_LIVE_EDGE` is referenced **nowhere else in the 924-line file** (grep: one hit, the
declaration). Every gate in `_detect_signals` compares the model's own fair price to a constant
(`MIN_FAIR_UNDER`, `MIN_FAIR_OVER`, `MAX_FAIR_OVER`, `HT_MIN_FAIR_UNDER`, `HT_MIN_FAIR_OVER`).
No bookmaker price enters the decision. `grep -rn "odds/live\|live_odds"` over `v9/src/*.py` and
`v9/pipeline.py` returns nothing: v9 never fetches a live price at all.

Consequences:

* `live_signals` has no odds/price/stake/edge/EV column of any kind (checked: zero columns whose
  name contains `odd`, `price`, `stake`, `ev`, `edge`).
* The signal-to-executable-price delay is **undefined**, not large. There is no price event to
  measure against.
* **Seed correction.** `side_bets_ledger` (254 rows, 147 settled, 88W-59L, +18.10u) is entirely
  pre-match: markets are `btts` 175 / `over15` 74 / `over35` 5, **zero** HT or in-play markets,
  and 223 of 254 rows have `signal_date != match_date`. `bets_ledger.source` takes values
  `{backtest: 4115, live: 1061}` — `live` means "produced by the production run", not "in-play".
  **The live scanner has never contributed a single unit to any ledger.**

Alerts have also been off since 2026-09-06 (`live_scanner.py:794`, `LIVE_ALERTS` gate;
`live_scanner.yml` sets `LIVE_ALERTS: ''`), so there is not even a human execution path.

## F3 — One frame per match (HIGH, PROVEN)

`v9/.github/workflows/live_scanner.yml:64` — `cron: '4 8-23 * * *'`, 16 firings/day, hourly,
single sweep, `timeout-minutes: 5`. A football match lasts ~105 wall-clock minutes.

Measured on `v9/output/inplay_snapshots.csv` (983 rows, 2026-08-07 → 2026-09-10, 535 match-days):

```
observations per match-day:  1 → 357 (66.7%)   2 → 32   3 → 77   4 → 33   5 → 19   6 → 15   7 → 2
elapsed span per match-day:  median 0 min, p75 16, p90 71
inter-observation gap:       median 16 match-min, p75 26, p90 40, max 82
```

The Pro side is worse: 1,308 of 1,323 live-odds fixtures (98.9%) have exactly one snapshot, and
1,316 (99.5%) exactly one distinct `match_minute`. `live_odds_snapshots` is not a time series —
it is one photo per match.

This voids the stated Phase-2 plan at `live_scanner.py:47-49`:

> `K + the game-state multipliers are HEURISTIC PLACEHOLDERS — to be FITTED from the in-play
> snapshots we start collecting (Phase 2). Do not treat as calibrated.`

`BLEND_K_MINS = 30.0` is the weight on *how fast to trust in-play evidence over the prior*. You
cannot fit a time-blend weight on data with one time point per match. Two thirds of the sample
has a span of zero minutes.

Note what the fix is **not**: asking GitHub for more firings. `predict.yml:72-78` records the
measurement — `live_scanner 224 requested → 1 delivered`. The pattern that works is one firing
that samples internally (`std_odds_capture`), which `pro_live_odds.yml` explicitly abandoned.
But density buys nothing until F1 is fixed, because the rows are orphaned on arrival.

## F4 — `lam_total / 2` is wrong by 11.8% (HIGH, PROVEN, one constant)

`v9/src/live_scanner.py:190`:

```python
lam_ht = lam_total / 2
```

Measured across every `data/football_data/**/*.csv` file carrying `HTHG`/`HTAG` — **21,026
matches, 57,252 goals, 9 divisions, 78 season files**:

```
mean FT goals 2.7229   mean H1 1.2179   mean H2 1.5050
H1 share of all goals: 0.4473    95% CI [0.4432, 0.4513]     (z vs 0.50 ≈ 25)
=> lam_total/2 OVERSTATES first-half lambda by 11.8%
```

Per-division `h1_share` ranges 0.4332 (SC2) to 0.4688 (SC3); every division with n≥300 is below
0.47. This is not a league artefact.

Calibration of the exact quantities the HT signals gate on:

| quantity | empirical | Poisson(λ/2) | error | Poisson(λ×0.447) | error |
|---|---|---|---|---|---|
| P(HT under 0.5) | 0.2924 | 0.2563 | **−3.61 pp** | 0.2959 | +0.35 pp |
| P(HT under 1.5) | 0.6546 | 0.6052 | **−4.94 pp** | 0.6562 | +0.16 pp |

Replacing `/2` with `×0.447` removes 90–97% of the unconditional calibration error.

Direction: the bug **understates** P(HT UNDER), so `fair_under = 1/p_under` is quoted ~8% too
high. `HT_MIN_FAIR_UNDER = 1.18` is a lower bound on that inflated number, so the gate admits
more HT_UNDER signals than it should and each claims a fair price it does not need. This affects
**32 of 57 logical signals (56%)** and **8 of 8 signals that ever fired in our bet leagues** (all
HT_UNDER — Bundesliga 2, Serie B, League One, Championship).

**This is not retrospective tuning (invariant 6).** 0.4473 is measured on 21,026 historical
matches that are entirely disjoint from the 57 live signals any revised gate would be evaluated
on. **It is also not a v9 edit (invariant 3).** v9 is frozen; this is a bug report, and the fix
belongs in Pro's live layer.

## F5 — The HT path ignores the entire v2 upgrade (HIGH, PROVEN)

`live_scanner.py:473-476` computes the v2 live-adjusted λ and hands it to the full-match model:

```python
_sot_live  = (sot_by_fixture or {}).get(game.get("fixture_id"))
_lam_rem   = (_live_lambda_remaining(lam, elapsed, _sot_live, home_g, away_g)
              if _sot_live is not None else None)
probs      = _live_probs(total_g, elapsed, lam, lam_remaining_override=_lam_rem)
```

`live_scanner.py:617` hands the HT model the **pre-match** λ instead:

```python
ht = _ht_probs(total_g, elapsed, lam)
```

`_ht_probs` (lines 184–209) takes `lam_total`, halves it, applies linear time decay, and reads
nothing else. No shots on target, no game-state multiplier, no possession, no red card. So the
"Live Scanner v2 (LIVE)" in-play λ upgrade applies only to full-match O/U 2.5, and bypasses the
majority of the signals the scanner actually produces — including every one that fired in a
league we bet.

## F6 — OVER is capped, UNDER is not (MEDIUM, PROVEN)

`live_scanner.py:53-58`:

```python
MIN_FAIR_UNDER    = 1.28   # only alert if fair UNDER odds >= this
MIN_FAIR_OVER     = 2.00
MAX_FAIR_OVER     = 3.30   # ... Without an upper bound the STRONG_STUCK/COMEBACK signals fired
                           # on 0-0 games late where live P(over) was 1-8% (fair 12-100)
                           # -> no book offers value, guaranteed loser. (audit C1)
```

The C1 fix put a **band** on OVER. UNDER got a floor and no ceiling. Neither
`HT_MIN_FAIR_UNDER = 1.18` nor `HT_MIN_FAIR_OVER = 1.55` has a ceiling either.

Measured consequence. Implied fair odds on the side actually tipped, by signal family (57 logical
signals, dedup keep-last):

| signal | n | mean fair | median | max | mean p(tipped side) |
|---|---|---|---|---|---|
| STRONG_STUCK | 7 | 44.29 | 26.39 | **151.52** | 0.085 |
| UNDER_RECOVERY | 13 | 3.89 | 2.60 | **19.49** | 0.373 |
| HT_OVER_0.5 | 5 | 3.37 | 3.67 | 3.94 | 0.305 |
| HT_UNDER_1.5 | 16 | 1.32 | 1.26 | 1.61 | 0.765 |
| HT_UNDER_0.5 | 12 | 1.26 | 1.23 | 1.52 | 0.797 |
| UNDER_HOLD | 4 | 1.33 | 1.31 | 1.41 | 0.755 |

**24 of 57 signals (42%) tip a side the model itself gives under 50%.**

Being fair to the C1 fix: every absurd STRONG_STUCK row (fair 22–152) is dated 2026-06-27 to
2026-08-08, i.e. *before* the fix, and STRONG_STUCK has not fired since 2026-08-08. The cap
works. But UNDER_RECOVERY fired on **2026-09-05** — a month after the cap — on Argentina Primera
at 1-1 in the 26th minute, with the model's own p(UNDER 2.5) = **0.0513**, a fair price of
**19.49**. It lost. The exact failure C1 was written to stop, on the side C1 did not cover. Same
structural shape as the seed's `_apply_drift_adjustment` asymmetry: the guard was added to one
branch and not its mirror.

## F7 — A null shot count reads as "no shots taken" (MEDIUM, PROVEN)

Three lines conspire:

* `v9/src/api_football.py:231` — `parsed["shots_on_target"] = int(v or 0)`; a null "Shots on
  Goal" (routine for in-play statistics before the feed populates) becomes `0`.
* `v9/src/live_scanner.py:744` — `.get("shots_on_target", 0)`; an absent statistic becomes `0`.
* `v9/src/live_scanner.py:134` — `r_live = (SOT_TO_GOAL * float(live_sot or 0)) / elapsed`.

So the dict *has* the key with value 0, `_sot_live is not None` passes, the live branch fires, and
the model concludes the in-play scoring rate is exactly zero. This is root invariant 9 ("Write
NaN, never an invented number") violated in the live path.

Incidence, from the 729 SOT readings in `inplay_snapshots.csv`:

```
elapsed  0-15   n=59   sot==0: 71.2%   median 0
elapsed 15-30   n=111  sot==0: 28.8%   median 1
elapsed 30-45   n=287  sot==0:  6.3%   median 3
elapsed 45-60   n=85   sot==0:  1.2%   median 5
overall: 94 of 729 readings (12.9%) are zero; 46 of them at elapsed >= 20
```

SOT is also simply absent on 25.8% of frames (729 of 983 populated; 59.4% in August, 91.4% in
September) — the one feature driving the live λ is missing on a quarter of the collected data.

Magnitude, at 0-0 with prior λ=2.55:

| elapsed | λ naive | λ (sot=0) | collapse | p_under naive | p_under (sot=0) |
|---|---|---|---|---|---|
| 20 | 1.983 | 1.190 | −40.0% | 0.681 | 0.882 |
| 38 | 1.473 | 0.650 | −55.9% | 0.816 | 0.972 |
| 55 | 0.992 | 0.350 | −64.7% | 0.921 | 0.994 |
| 75 | 0.425 | 0.112 | −73.7% | 0.991 | 1.000 |

**Adversarial note against my own finding.** At 0-0 the collapse drives `fair_under` to 1.03–1.13,
*below* the `MIN_FAIR_UNDER = 1.28` floor, so it **suppresses** full-match UNDER alerts rather
than manufacturing them. And the observed UNDER_RECOVERY signals had *high* λ (fair 1.85–19.49),
not collapsed λ — so this bug is **not** the cause of the losses. It is a data-integrity defect
whose net sign on the tip stream is unmeasured. Do not sell it as the smoking gun.

## F8 — 15.8% of signals never settle, and HT cannot settle at all (MEDIUM, PROVEN)

Of 57 logical signals: 25 LOSS, 16 WIN, **16 PENDING**. All 9 distinct PENDING logical rows have
`match_date` more than 7 days old:

```
World Cup 2026   2026-06-29  UNDER_RECOVERY  — 73 days stale, re-imported PENDING on 2026-09-09
World Cup 2026   2026-06-30  HT_UNDER_0.5    — 72 days
World Cup 2026   2026-07-03  HT_UNDER_1.5    — 69 days
... 6 more, min 33 days
```

These are not lagging, they are abandoned. The answer to "is there a settled outcome per live
signal?" is **48 of 57 = 84.2%**, with a permanent 15.8% hole.

Separately, Pro's `settlements` table (126,259 rows, 4,825 fixtures) holds markets
`{OU25: 123478, BTTS: 1558, OVER15: 1219, OVER35: 4}` — **no HT market exists**. So the 32 HT
signals (56% of the total) can never be settled by Pro's settlement machinery; only v9's own
grader in `live_signals_history.csv` touches them. 26 of the 52 live-signal fixture_keys do
appear in `settlements`, but only for the pre-match OU25 market.

## F9 — The record cannot answer the question (MEDIUM, PROVEN)

Exact Clopper-Pearson intervals on the 48 settled logical signals:

| signal | n | wins | hit | 95% CI | claimed p | claim in CI? |
|---|---|---|---|---|---|---|
| HT_UNDER_1.5 | 15 | 11 | 0.733 | 0.449 – 0.922 | 0.772 | yes |
| HT_UNDER_0.5 | 8 | 3 | 0.375 | 0.085 – 0.755 | 0.787 | **no** |
| UNDER_RECOVERY | 10 | 2 | 0.200 | 0.025 – 0.556 | 0.364 | yes |
| STRONG_STUCK | 6 | 2 | 0.333 | 0.043 – 0.777 | 0.055 | yes |
| HT_OVER_0.5 | 5 | 1 | 0.200 | 0.005 – 0.716 | 0.305 | yes |
| UNDER_HOLD | 4 | 2 | 0.500 | 0.068 – 0.932 | 0.755 | yes |
| **ALL** | **48** | **21** | **0.438** | **0.295 – 0.588** | **0.550** | **yes** |

The scanner's overall claimed probability (0.550) sits inside its own confidence interval. The
honest verdict is **INSUFFICIENT_DATA**, and that cuts both ways: the record neither convicts nor
exonerates. Do not read the 21W-27L line in `live_scanner.py:775-779` as a measurement.

HT_UNDER_0.5 is the one family whose claim falls outside its interval — but with six families
tested at α=0.05, one rejection is roughly a 1-in-4 coincidence. PLAUSIBLE, not established.
Note that F4 predicts exactly this direction of miscalibration for HT_UNDER, which is the only
reason to take it seriously at all.

Accumulation rate: 44 logical signals at the first import (2026-08-17) → 57 at the latest
(2026-09-09) = **0.54 new signals/day**. Reaching n=250 takes ~360 more days at the current
hourly cadence. Live signal evaluation is a multi-season project as currently instrumented.

## F10 — `live_signals` is 95.2% duplicates (MEDIUM, PROVEN)

```
raw rows:                    1,182
unique logical signals:         57      (dup factor 20.7)
distinct fixture_key:           52
import runs:                    24      each writing the entire v9 CSV
```

The importer re-imports the whole of `live_signals_history.csv` on every run (24 runs, 44 → 57
rows each). Worse, **7 of 57 logical signals carry more than one distinct `result` across
imports** (PENDING on an early import, WIN/LOSS later), so any `groupby('result')` on the raw
table both double-counts and mixes settlement states. Reading the seed's "live_signals ~1k" as
~1,000 signals is out by a factor of 20.

Correct dedup key: `[fixture_key, league, match_date, score, elapsed_mins, signal_type, bet]`,
`keep='last'` by `ingested_at`. That reproduces `live_signals_history.csv` exactly (57 rows).

One thing I checked and it is *not* a bug: three identical-looking Bundesliga 2 HT_UNDER_1.5
signals on 2026-08-30 (0-0 at minute 20, all WIN) are three **different** fixtures kicking off in
the same slot, not a dedup failure. It is a portfolio-correlation exposure, not a duplicate.

## F11 — Stale-price and line-availability risk (MEDIUM, PROVEN)

`v10/src/live/collector.py:50` — `STALE_ODDS_SECONDS = 120`, flagged on `odds_updated_at` age
alone. Across 56,478 rows: 12,029 stale (21.3%), 3,694 suspended (6.5%), **25.0% not takeable**
(stale OR suspended). Odds age: median 47.4s, p75 68.3s, p90 249.5s, p99 11,891s, max 75,336s.

Takeability by match minute — this is the operational number:

| minute | rows | stale | susp | median age | **takeable** |
|---|---|---|---|---|---|
| pre-kickoff (0) | 2,351 | 72.0% | 35.2% | 172.8s | **28.0%** |
| 1–20 | 9,812 | 1.6% | 3.8% | 45.5s | 94.6% |
| 21–35 | 7,931 | 1.9% | 4.5% | 38.9s | 94.9% |
| **36–45** | **17,988** | **49.4%** | 3.4% | **115.7s** | **48.9%** |
| 46–55 | 5,509 | 7.1% | 3.5% | 47.0s | 89.5% |
| 56–65 | 4,560 | 4.7% | 11.9% | 43.9s | 87.3% |
| 66–75 | 3,692 | 2.4% | 9.0% | 39.6s | 90.0% |
| 76–90 | 4,199 | 10.5% | 8.9% | 47.4s | 83.0% |

The 36–45 trough is the halftime freeze (12,003 rows carry `match_status = 'Halftime'`; the feed
stops updating `odds_updated_at`, the collector flags age > 120s). This matters directly:
`HT_LOCK_ELAPSED = 35` means HT_UNDER_0.5 fires into the window where **half the prices are not
takeable**, and both 2026-09-05 Bundesliga 2 HT_UNDER_0.5 signals fired at minute 38.

Line availability. `TOTALS_LINE` is 11,054 rows over 1,321 fixtures, and the live line is
**dynamic**:

```
line 2.50 appears on 518 of 1,321 fixtures = 39.2%   (1,060 rows)
main-line median by minute: 2.62 (0-30'), 2.25 (30-45'), 2.25 (45-60'), 2.50 (60-75'), 2.50 (75'+)
```

So the fixed 2.5 line the model prices is the live main line in a minority of situations. A live
O/U 2.5 signal will often be quoting against a line nobody is making a market on.

Two genuinely good results, stated plainly: **530 of 530 (100%)** of (snapshot, fixture) groups on
the 2.5 line are two-sided, so live de-vig is possible wherever the line exists; and 806 of 1,060
(76.0%) of 2.5-line rows are takeable. Live BTTS: 1,898 rows / 932 fixtures, 76.1% takeable.

## F12 — Red cards, possession, xG: absent, and smaller than they look (LOW, SUPPORTED)

`grep -ni "red_card\|card\|possession\|xg\|expected_goal\|substitut"` over the 924-line
`live_scanner.py` returns **zero** substantive hits. Game state is score + elapsed + shots on
target, nothing else. `api_football.get_fixture_statistics` already returns `possession`
(`api_football.py:213`) and it is never read.

Measured on the same 21,026 matches (`HR`/`AR` columns):

```
19.04% of matches have >= 1 red card
              n       FT goals   H1      H2      P(over 2.5)
0 reds    17,022      2.7008   1.2072  1.4936     0.5132
1 red      3,507      2.8164   1.2649  1.5515     0.5349
2+ reds      497      2.8209   1.2515  1.5694     0.5634

>=1 red vs 0 red: +0.1161 goals, se 0.0291, z = 4.0
P(over 2.5):      +2.52 pp
second half only: +0.0601 goals
```

Statistically solid (z=4.0 at n=21,026) and **operationally small**: +2.52pp against a scanner
that nominally wants a 12% edge. And this is a match-level *association* — I have no red-card
minutes, so it cannot isolate the in-play effect, and a red at 88' cannot have caused the goals
that preceded it. Grade SUPPORTED, and the conclusion is the opposite of the obvious one: **red
cards are not why the live scanner loses, and a red-card feature is not the next thing to build.**

## F13 — The live table is unscoped (LOW, PROVEN)

`live_odds_snapshots` has **no `league` column**, and `v10/src/live/collector.py` applies no
league filter — it captures every fixture API-Football reports as in play, worldwide (1,323
fixtures in 11 days). Combined with F1, you cannot restrict the table to our leagues at all
without the resolver. Of the 170 bridgeable fixtures, in-scope leagues account for 20: Serie B 7,
La Liga 2 5, League Two 4, Bundesliga 2 2, League One 2.

---

## The two clocks

`live_scanner.yml` fires at `:04` hourly (16/day). `pro_live_odds.yml` fires at `:09` hourly
(13/day). They are separate repos, separate crons, uncoordinated, both single-sweep. Even if F1
were fixed tomorrow, a signal generated at `:04+δ` would be matched against a price observed at
`:09+δ'` with GitHub's start jitter on both — and I measured that jitter as real (live-odds
snapshots land on 29 distinct minutes-of-hour, from :02 to :59).

Observed: 157 distinct scanner runs over 33 days and 44 live-odds snapshots over 10 days. I will
**not** convert those into delivery rates: a scan with no live fixtures writes no row, so absence
of a row is not evidence of a dropped firing. That confound is unresolved and I am flagging it
rather than estimating. The per-fixture measurement in F3 (98.9% single-snapshot) is the
un-confounded version of the same point and is sufficient.

---

## Do not build

1. **Live staking, in any form.** Out of scope by instruction, and F9 shows n=48 could not support
   the decision even if it were in scope.
2. **A red-card or possession live feature.** F12: +2.52pp on P(over 2.5), match-level only, and
   worthless while 87.2% of live prices are orphaned (F1).
3. **More cron firings for either live workflow.** `predict.yml:72-78` measured
   `live_scanner 224 requested → 1 delivered`. The estate is scheduler-starved. And density buys
   nothing until the rows are joinable.
4. **Fitting `BLEND_K_MINS` or the game-state multipliers now.** F3: 66.7% of match-days have one
   frame and a median span of zero minutes. A time-blend weight is not identifiable on that.
5. **An in-play xG model.** No table holds in-play xG; the one in-play feature that exists (SOT) is
   populated on 74.2% of frames at one frame per match.
6. **Merging `live_odds_snapshots` into `live_signals`.** They are different objects, and F1 shows
   the join does not exist regardless.
7. **Editing v9's live scanner constants.** Invariant 3 — v9 is frozen. F4, F6 and F7 are bug
   reports whose fixes belong in Pro's live layer, not in v9 this season.
8. **Reading `side_bets_ledger`'s +18u as live-betting evidence.** F2: it is 100% pre-match.

## Open questions

1. Why does `v10/src/live/collector.py` emit `fixture_id` when every other Pro writer emits
   `fixture_key`? Was the resolver call omitted, or does the live payload lack the fields the
   resolver needs? This determines whether F1 is a two-line fix or a name-resolution project.
2. Was the "audit C1" `MAX_FAIR_OVER` fix deliberately UNDER-exempt, or was the UNDER side simply
   never audited? The 2026-09-05 fair-19.49 UNDER tip suggests the latter.
3. Is the 49.4% stale rate at minutes 36–45 the provider suspending markets at halftime, or the
   collector reading a frozen `odds_updated_at` on prices that are in fact takeable?
   `STALE_ODDS_SECONDS = 120` flags on age alone and cannot tell these apart.
4. Why do 9 live signals sit PENDING for up to 73 days? Is the grader missing those fixtures'
   results, or does it silently skip World Cup / summer-league fixtures?
5. Pro's `settlements` has no HT market. Is HT O/U intended to be a settleable market in Pro, or
   are HT signals permanently research-only? 56% of live signals depend on the answer.

# AGENT 5 — Snapshot Infrastructure Audit

Date: 2026-09-10. Read-only on `v9/` and `wowza-v11/`. All numbers computed this run from
`v10/data/season_2026_27/` with `v9/.venv/Scripts/python.exe`, or read at the file:line cited.

---

## Headline

**The closing line no longer exists, and it was destroyed by our own fix.** The schedule cut of
2026-08-27..08-30 (`674e36e0`, `f7d10352`, `0104cf96` — "ask GitHub for less so it delivers
more") raised the *delivery ratio* and halved the *absolute* capture rate: the share of fixtures
with any odds observation inside T-30m fell from **84.7% (n=177) to 29.4% (n=228), a −55.4pp
change with a 95% CI of [−63.3, −47.4]**, degrading in **17 of 17 leagues present in both
windows** (unweighted mean −64.8pp). The 2026-09-07 NEAR-branch fix (`87c9104c`) did not restore
it. The direct consequence: the accrual rate of clean OU25 closes fell from 5.1–6.8/day to
2.7–4.3/day, so Pro's promotion gate (`min_clv_n = 150`, `v10/src/models/registry.py:48`) now
needs 35–55 more days per segment instead of 22–29 — **no model can be promoted to LIVE for next
season until near-kickoff capture is restored.**

Two secondary results overturn seed numbers: multi-book **consensus is available on 83–94% of
fixture-markets, not 34.9%**, and **55.6% of the canonical `market_snapshots` table carries no
market observation timestamp at all**.

---

## Findings table

| # | Finding | Evidence | Conf. | Impact |
|---|---|---|---|---|
| 1 | Closing-line capture collapsed at the 08-27..08-30 schedule cut; 17/17 leagues | T-30m coverage 84.7% (n=177) → 29.4% (n=228); Δ −55.4pp CI [−63.3,−47.4] | PROVEN | CRITICAL |
| 2 | Median "close" on record is 46 min stale at T-10m; only 16.6% fresher than 15 min | LOCF staleness table below, n=625 | PROVEN | CRITICAL |
| 3 | Clean-close accrual too slow for the promotion gate | OU25 <=T-30m, >=3 books, two-sided: standard 96, new_format 91 in 24 days vs `min_clv_n=150` | PROVEN | CRITICAL |
| 4 | The 09-07 NEAR fix did not restore coverage; point estimate is worse | n=34: T-30m 8.8%, zero-obs-in-final-hour 88.2% (A window: 9.0%) | SUPPORTED (n<50) | HIGH |
| 5 | Seed's "34.9% have >=3 books" is a storage artefact; true panel is median 9 books | 34.8% reproduced per-instant; LOCF panel median 9, 94.3% >=3 ever, 83.5% >=3 inside T-6h | PROVEN | HIGH |
| 6 | 55.6% of `market_snapshots` has no observation timestamp — timing questions unanswerable | 95,855/172,430 rows `captured_at` null; `observed_at == ingested_at` on 100% of rows; `src/importers/current_wowza.py:150-166` never sets it | PROVEN | HIGH |
| 7 | `captured_at` mixes two ISO formats; a naive `to_datetime(utc=True)` silently NaTs 83% | 63,663 rows length 20 ("...Z"), 12,912 length 19 (naive), same column | PROVEN | HIGH |
| 8 | v11 declares STALE_CLOSE_PRICE "not assessed" on 100% of 691,123 rows for a reason that no longer holds | `wowza-v11/src/movement.py:162-166`; `book_odds_snapshots` now supplies per-book timestamps | PROVEN | HIGH |
| 9 | No opening line exists: only 12.6% of fixtures have any observation at T-7d | first-obs median 6.83d (v9_capture) / 6.35d (book_odds); `NEXT_N = 20` at `scripts/capture_nf_odds_forward.py:63` | PROVEN | MEDIUM |
| 10 | Budget is not the constraint — API-Football runs at 15.0% of cap; 33% of observations sit at 3–7d where coverage is already 97% | 14-day mean 11,220/75,000; allocation table below | PROVEN | HIGH |
| 11 | The Odds API has no headroom, and it is the only multi-book source | seed 89,842/100,000; `book_odds_snapshots` fed by `v9/src/btts_odds.py` + `src/predict.py:194` | SUPPORTED | HIGH |
| 12 | 33.6% of `odds_histories` rows carry a placeholder midnight timestamp | 25,724/76,575 have ts exactly 00:00:00, dating to 2024-08-10 | PROVEN | MEDIUM |
| 13 | Seed's allocation and post-kickoff figures do not reproduce | measured 57.6% >24h (not 81%), 6.9% final hour (not 0.6%), 0.019% post-kickoff (not 5.4%) | PROVEN | MEDIUM |
| 14 | Delivery is better than the seed's 15%; the ceiling is now the ask, not the drop rate | book_odds write-passes/day vs predict cron: median >=35% of requested, 78.8–82.5% on 08-22/23 | SUPPORTED | MEDIUM |

---

## 1. Method, and a correction that changes every coverage number

### 1.1 What can be measured, and what cannot

`market_snapshots` holds 172,430 rows from two sources:

| source | rows | has a market observation timestamp? |
|---|---|---|
| `v9:predictions#2` | 95,855 (55.6%) | **No.** `captured_at` is null on all of them |
| `v9:odds_histories#0` | 76,575 (44.4%) | Yes, `captured_at` |

`observed_at == ingested_at` on **100%** of all 172,430 rows — `observed_at` is Pro's ingest
clock, not the market's. The importer never had a market timestamp to write for the predictions
path (`v10/src/importers/current_wowza.py:150-166` builds the block from `predictions.csv`
columns only; only `from_odds_histories` sets `captured_at`, at line 246). So **no timing question
can be asked of 55.6% of the canonical market table.** Any coverage figure derived from
`observed_at` measures Pro's 2-hourly collect cadence, not odds capture — which is the most likely
origin of the seed's divergent allocation numbers.

Timing-bearing observation sets actually available:

| set | rows (pre-kickoff, played fixtures) | timestamp | books |
|---|---|---|---|
| `book_odds_snapshots` | 126,015 | `snapshot_ts` | 24 real |
| `market_snapshots` / `v9_capture` | 20,893 | `captured_at` | Bet365 only (id 8) |

Of the 76,575 `odds_histories` rows, **25,724 (33.6%)** carry a timestamp of exactly `00:00:00`,
some dating to 2024-08-10 — a date rolled into a timestamp field by a historical backfill. They
are excluded here; they would otherwise put a fake "T-19h" observation on every fixture.

### 1.2 The storage model makes naive coverage a lower bound

All three archives store **consecutive-distinct price changes only**:

- `v9/scripts/capture_std_sidemarket_odds_forward.py:338-343`
- `v9/src/btts_odds.py:87-106` (`append_book_rows`)
- `v9/src/predict.py:199-204`

So the absence of a row at T-30m does not mean nothing was polled; it can mean the price did not
move. "Was there an observation at horizon H" therefore conflates *not polled* with *polled,
unchanged*, and understates polling. The decision-relevant metric is instead **is a price known
at H, and how stale is it** — last-observation-carried-forward, which a price-change file plus a
base price fully determines. Both are reported below. The seed's coverage series (T-6h 91.6%,
T-30m 14.5%) is the naive metric, and is a lower bound.

### 1.3 Universe

809 fixtures in Pro's `fixtures` table (343 standard, 466 new-format); **625 with kickoff before
2026-09-10 06:00Z** are the measurement universe. Kickoff cross-check: `fixtures.kickoff_utc` vs
`book_odds_snapshots.kickoff_utc` agree to the minute on 98.5% of fixture-kickoff pairs
(median absolute difference 0.0 min). A horizon is "eligible" for a fixture only if
`kickoff − H >= 2026-07-31 08:16Z`, the first observation in the store.

---

## 2. Per-fixture coverage by horizon

### 2.1 Naive coverage (an observation landed near the nominal horizon)

"covered" = an observation inside `[0.5H, 1.5H]`. "any inside H" = any observation at or after
the horizon. Target error = minutes between the nominal horizon and the nearest observation.

All sources, all 625 played fixtures:

| horizon | eligible | covered | % | % any inside H | median abs target error | p90 |
|---|---|---|---|---|---|---|
| OPEN (first obs) | 625 | 625 | 100.0 | — | median first obs **6.88 d** | — |
| T-7d | 625 | 576 | 92.2 | 100.0 | 246 min | 4,058 min |
| T-3d | 625 | 612 | 97.9 | 99.0 | 76 min | 582 min |
| T-24h | 625 | 608 | 97.3 | 98.4 | 52 min | 296 min |
| T-12h | 625 | 577 | 92.3 | 96.6 | 66 min | 258 min |
| T-6h | 625 | 539 | **86.2** | 94.4 | 41 min | 218 min |
| T-3h | 625 | 535 | 85.6 | 89.9 | 32 min | 119 min |
| T-1h | 625 | 380 | **60.8** | 57.1 | 21 min | 118 min |
| T-30m | 625 | 275 | **44.0** | 45.8 | 22 min | 148 min |
| T-10m | 625 | 101 | **16.2** | 24.0 | 28 min | 168 min |
| LAST pre-KO | 625 | 625 | 100.0 | — | median last obs **37.9 min** | p90 4,112 min |

These are higher than the seed's series (T-6h 91.6% vs 86.2%, T-1h 32.6% vs 60.8%, T-30m 14.5%
vs 44.0%) because this measurement uses both timing-bearing sources including the newly imported
`book_odds_snapshots`, and excludes the placeholder-midnight rows.

By source: `book_odds` alone gives T-30m 40.3%, T-10m 15.0%; `v9_capture` alone gives T-30m
26.6%, T-10m 11.0%. **Neither source reaches the near horizon on its own; the union barely
does.**

By model track (invariant 1 respected — never pooled for a modelling claim, only reported side
by side): standard reaches T-30m on 53.4% (n=266), new-format on 37.0% (n=359). Standard is
better served at every horizon inside T-6h.

### 2.2 Missing horizons

- **OPEN does not exist.** Median first observation is 6.88 days before kickoff; only **12.6%**
  of fixtures have any observation at or before T-7d, and 11.2% have a first observation beyond
  7 days. The ceiling is structural: the forward capture prices `NEXT_N = 20` fixtures per league
  (`v9/scripts/capture_nf_odds_forward.py:63`) and predict's board is a rolling window. There is
  no opening line in this store, and there cannot be one without a wider look-ahead.
- **T-10m is effectively absent.** 16.2% naive; median target error 28 min against a 10-minute
  nominal, i.e. the "T-10m" observation is typically a T-38m observation.
- **T-1h and T-30m are the collapse zone**, and are exactly the horizons the closing line forms in.

### 2.3 The metric that matters: is a price known, and how stale

LOCF, all sources, 625 played fixtures:

| horizon | % price known | median staleness | p90 staleness | % fresher than 60 min | % fresher than 15 min |
|---|---|---|---|---|---|
| T-7d | **12.6** | 1,179 min | 7,980 min | 1.0 | 0.2 |
| T-3d | 96.8 | 213 min | 1,219 min | 20.6 | 3.7 |
| T-24h | 98.9 | 118 min | 505 min | 25.8 | 7.7 |
| T-12h | 99.2 | 124 min | 499 min | 28.3 | 8.0 |
| T-6h | 99.2 | 108 min | 505 min | 36.5 | 16.5 |
| T-3h | 99.2 | 57 min | 453 min | 50.7 | 17.9 |
| T-1h | 100.0 | 46 min | 238 min | 60.0 | 19.7 |
| T-30m | 100.0 | 41 min | 228 min | 60.8 | 24.2 |
| T-10m | 100.0 | **46 min** | **186 min** | 57.0 | **16.6** |

Read the last row plainly: at ten minutes before kickoff, a price is on file for every fixture,
and on the median fixture that price was last observed **46 minutes earlier**. On one fixture in
ten it is over three hours old. **We do not have closing prices. We have hour-old prices that we
call closing prices.**

This matters more than any individual coverage percentage, because of Agent-level finding in the
seed: the v11 placebo battery showed that `p_market(t)` sitting in both the residual and the
future move manufactures a positive coefficient from measurement noise alone. A 46-minute-stale
close is precisely that noise. Improving close capture is a **measurement** upgrade that would let
the residual test be run honestly. It is not, and must not be read as, a betting upgrade.

---

## 3. The regression: what the schedule cut did

Timeline of the schedule changes (from `git log` in `v9/`, read-only):

| date | commit | change |
|---|---|---|
| 2026-08-26 | `21493e36` | side-market capture: adaptive spacing near kickoff |
| 2026-08-27 | `674e36e0` | **predict cadence 5 min -> 10 min** |
| 2026-08-29 | `f7d10352` | **repo total ask 696 -> 250 runs/day** |
| 2026-08-29 | `9f920ced` | predict weighted to Fri-Sun (57/day mean) |
| 2026-08-30 | `0104cf96` | ask 227 -> 177 runs/day |
| 2026-09-07 | `87c9104c` | NEAR branch unreachable since 08-29 — fixed |

Closing-line freshness by regime, universe = played fixtures with any pre-kickoff observation:

| window | n | median last obs | within 10m | within 30m | within 60m | within 180m |
|---|---|---|---|---|---|---|
| **A** pre-cut, KO 08-19..08-26 | 177 | 10.5 min | 49.7% | **84.7%** | 91.0% | 97.7% |
| **B** transition, KO 08-27..08-30 | 163 | 51.7 min | 8.0% | 36.2% | 54.0% | 93.9% |
| **C** post-cut, KO 08-31..09-06 | 228 | 77.2 min | 18.9% | **29.4%** | 40.4% | 81.6% |
| **D** post-NEAR-fix, KO 09-07..09-09 | 34 | 100.9 min | 8.8% | 8.8% | 11.8% | 82.4% |

Observation density in the run-up:

| window | n | median obs in final 6h | % with zero obs in final 6h | median obs in final 1h | % with zero obs in final 1h |
|---|---|---|---|---|---|
| A | 177 | 67 | 1.1% | 26 | **9.0%** |
| C | 228 | 36 | 11.4% | 0 | **59.6%** |
| D | 34 | 31.5 | 5.9% | 0 | **88.2%** |

Sampling interval for the same fixture (p90 of the gap between consecutive capture instants):

| window | T-6h..T-1h median samples/fixture | p90 gap | T-1h..KO median samples/fixture |
|---|---|---|---|
| A | 9.0 | 50 min | 4.0 |
| C | 4.0 | 126 min | 3.0 |
| D | 4.0 | 188 min | 2.0 |

### 3.1 Is it real, or a league-mix artefact?

Two-proportion 95% CIs on "has an observation inside T-30m":

- A vs C: **−55.4 pp, CI [−63.3, −47.4]** — excludes zero by a wide margin.
- A vs D: −75.9 pp, CI [−86.8, −65.0].
- `book_odds` alone A vs C: −59.3 pp, CI [−67.1, −51.6].
- `v9_capture` alone A vs C: −38.0 pp, CI [−47.0, −29.1].

Both sources degraded, so this is not one workflow. League-controlled (17 leagues with fixtures in
both A and C): **C is worse in 17 of 17**, unweighted mean −64.8 pp, range −22.2 pp (Mexico Liga
MX) to −100.0 pp (Brazil Serie A, Finland, Ireland). The regression is not a mix effect.

### 3.2 The 2026-09-07 fix did not fix it

Window D is n=34, below the n<50 evidence bar, so **INSUFFICIENT_DATA for a trend claim** — and I
am not making one. What can be said at n=34: 88.2% of post-fix fixtures had **zero** observations
in the final hour, and the exact binomial 95% CI on that is roughly [73%, 96%], which **excludes
window A's 9.0%**. So the narrow statement is safe: *the fix did not restore pre-cut near-kickoff
capture.* Whether it made things worse than window C cannot be determined at this sample size and
should be re-measured after 2026-09-20 (three more weekends, ~200 fixtures).

Confound to keep in view: D falls in an international break, and its league mix (MLS 14,
Championship 9, Finland 6) is unusual. Re-measure, do not conclude.

### 3.3 Why "ask for less" backfired

The delivery *ratio* did improve. Using distinct `book_odds` write-passes per day as a lower bound
on delivered predict runs (a delivered run with no price change writes nothing, so this
under-counts):

| day | dow | requested | write-passes | >= delivery |
|---|---|---|---|---|
| 2026-08-22 | Sat | 80 | 63 | 78.8% |
| 2026-08-23 | Sun | 80 | 66 | 82.5% |
| 2026-08-24 | Mon | 40 | 48 | 120% (dispatches) |
| 2026-09-05 | Sat | 80 | 20 | 25.0% |
| 2026-09-09 | Wed | 40 | 18 | 45.0% |

Median lower-bound delivery over 23 days is **35%**, and 78–82% on the pre-cut weekend. This
**refutes the seed's "predict asks 57/day and gets ~15%"** — 15% would be 8.6 runs/day, and 18–66
write-passes/day were observed. But the important point is arithmetic, not rate: absolute
delivered runs fell from 26–66/day to 4–20/day. **A higher percentage of a much smaller ask is
fewer captures.** The delivery-ratio optimisation was measured on the wrong objective.

---

## 4. Cost efficiency: useful snapshots per API credit

API-Football daily peak `requests_used`, from `v9/output/api_usage_log.csv` (676 rows):

- 14-day mean: **11,220 / 75,000 = 15.0%**. Headroom ~63,800/day.
- Range over the last 25 days: 2,249 (partial 09-10) to 42,616 (08-18 = 57% of cap).
- **The seed's "3% of 75,000" matches only the partial current day.** The 08-17/08-18 pair at
  37,944 and 42,616 is close enough to the proposed 45,000 alert to matter operationally.

Where the observations actually sit (pre-kickoff, played fixtures, n=146,908):

| bucket | book_odds | v9_capture | ALL |
|---|---|---|---|
| 0–10 min | 1.85% | 1.08% | 1.74% |
| 10–30 min | 2.45% | 1.45% | 2.31% |
| 30–60 min | 2.98% | 1.78% | 2.81% |
| 1–3 h | 7.28% | 5.56% | 7.04% |
| 3–6 h | 7.82% | 6.32% | 7.61% |
| 6–12 h | 9.60% | 8.52% | 9.45% |
| 12–24 h | 11.15% | 9.12% | 10.86% |
| 1–3 d | 24.90% | 23.64% | 24.72% |
| 3–7 d | 31.96% | 38.13% | 32.84% |
| post-kickoff | — | — | **0.019%** |

**The seed's allocation figures do not reproduce.** Measured: 57.6% beyond 24h (seed: ~81%),
6.86% inside the final hour (seed: 0.6%), 0.019% post-kickoff (seed: 5.4%). The seed's
post-kickoff figure in particular is 280x my measurement; the most likely cause is `observed_at`
(ingest clock) being used as the observation time, or the `captured_at` format trap in finding 7
having silently dropped 83% of the timing-bearing rows. My numbers use `captured_at`/`snapshot_ts`
with `format="mixed"` and exclude placeholder-midnight rows.

Credit efficiency of the API-Football path:

- Useful near-kickoff rows (<= T-6h) from `v9_capture`: **3,383 over 40 days = 84.6/day.**
- Distinct near-kickoff capture instants per fixture (<= T-6h): **median 2, mean 2.5**, across 507
  fixtures. Two samples in the final six hours.
- The WIDE run costs ~350 calls per window by its own accounting
  (`v9/scripts/capture_std_sidemarket_odds_forward.py:291`, SUPPORTED — read in code, not measured
  by me), and there are 8 WIDE firings/day requested across the two capture workflows, so roughly
  **2,800 credits/day buys the 3–7 day horizon that already has 96.8% LOCF coverage and where the
  price does not move.** Against 84.6 useful near rows/day, that is on the order of **30–40
  credits per useful near-kickoff row**, and ~90–110 per distinct near-kickoff instant.

The conclusion is not "spend more". It is that the *allocation* is inverted: about four fifths of
the spend goes to horizons that are already covered, and 3% to the final hour, which is the only
horizon that is not.

---

## 5. Two seed numbers that are wrong, and one v11 blocker that has lifted

### 5.1 Multi-book consensus: 83–94%, not 34.9%

I reproduce the seed exactly on its own metric — grouping `(fixture_key, market, snapshot_ts)`
gives 31,108 groups, **82.5% two-sided, 34.8% with >=3 books, median 2, p90 5, max 17.** But that
metric counts *books that changed price at the same instant*, because the file stores
consecutive-distinct changes only (section 1.2). It is not the number of books quoting.

Under LOCF — distinct books ever quoting a given `(fixture_key, market)`:

| measure | value |
|---|---|
| median panel width | **9 books** (OU25: 12, BTTS: 9, OU35: 8, OU15: 4) |
| p10 / p90 / max | 3 / 14 / 17 |
| share with >= 3 books | **94.3%** |
| share with >= 5 books | 85.0% |
| panel width using only T-6h..KO observations | median 7; **83.5% with >= 3 books** |

So multi-book consensus and cross-book de-vig are available on the large majority of
fixture-markets, not a third of them. The seed's figure understates the usable panel by a factor
of about 2.7 and would have led to abandoning consensus pricing that is in fact available.

### 5.2 v11's unassessable CLV quality flags are now assessable

`wowza-v11/src/movement.py:162-166`:

> `# STALE_ENTRY_PRICE / STALE_CLOSE_PRICE / SYNTHETIC_ODDS need per-book quote timestamps and`
> `# a provenance marker that these snapshots do not carry. Inventing a proxy ... would`
> `# misclassify a genuinely settled market, so they are declared unassessed.`
> `not_assessed += ["STALE_ENTRY_PRICE", "STALE_CLOSE_PRICE", "SYNTHETIC_ODDS"]`

That was correct when written. It is now stale: `book_odds_snapshots` carries per-book
`snapshot_ts`, `minutes_to_kickoff`, `is_post_kickoff` and the real book name, for 24 books and
143,799 rows. The consequence of the code as it stands: **all 691,123 `movement_observations` rows
carry STALE_CLOSE_PRICE, STALE_ENTRY_PRICE and SYNTHETIC_ODDS in `quality_not_assessed`, while
`clv_quality` reads OK on 96.7% of them** (668,381 OK, 19,449 INSUFFICIENT_BOOKS, 3,293
MISSING_KICKOFF; 780 of 807 unique fixtures OK on their last snapshot). A CLV record labelled OK
whose close was never checked for staleness, on data where the median close is 46 minutes stale,
is a label that will be believed and should not be.

`n_books` is null on the rows I sampled, so `INSUFFICIENT_BOOKS` is *not assessed* on 159,029 rows
rather than evaluated. Section 5.1 says a real book count would mostly pass (83.5% have >=3 books
inside T-6h), so wiring it in is a favourable change, not a destructive one.

---

## 6. What this costs the promotion gate

`v10/src/models/registry.py:41-50` sets `min_clv_n = 150` and `min_mean_clv_pct = 0.0`, and
`evaluate_gate` (line 133) treats missing evidence as a failure — correctly. Nothing calls it yet
(seed), but when it is called, this is what it will find.

Clean closes available today, defining a clean close as **an observation inside the window, from
>= 3 distinct books, two-sided** (so it can be de-vigged), over the 625 played fixtures:

| close window | standard, all markets | new_format, all markets | standard OU25 | new_format OU25 |
|---|---|---|---|---|
| <= T-10m | — | — | 53 | 35 |
| <= T-30m | 195 | 219 | **96** | **91** |
| <= T-60m | 275 | 288 | 137 | 118 |
| <= T-180m | 431 | 481 | 216 | 196 |

Read against `min_clv_n = 150`: on the bet market (OU25) with a defensible close (<= T-30m),
**both segments are below the gate** after 24 days. Relaxing to T-60m still fails
(137 / 118). Only a "close" three hours before kickoff clears it, and a T-180m price is not a
close — at T-3h the median observation on file is already 57 minutes stale.

Accrual rate, which is the actionable number:

| regime | segment | clean OU25 closes (<= T-30m) | of played | rate | days to `clv_n=150` |
|---|---|---|---|---|---|
| A pre-cut (8 d) | standard | 41 / 68 | 60.3% | 5.12/day | **29** |
| A pre-cut (8 d) | new_format | 54 / 109 | 49.5% | 6.75/day | **22** |
| C post-cut (7 d) | standard | 30 / 110 | 27.3% | 4.29/day | **35** |
| C post-cut (7 d) | new_format | 19 / 118 | 16.1% | 2.71/day | **55** |
| D post-fix (3 d) | standard | 1 / 14 | 7.1% | 0.33/day | 450 (n=14, INSUFFICIENT_DATA) |
| D post-fix (3 d) | new_format | 1 / 20 | 5.0% | 0.33/day | 450 (n=20, INSUFFICIENT_DATA) |

At the pre-cut rate both segments would have a gate-eligible CLV sample by late September. At the
post-cut rate, standard lands mid-October and new-format early November. **Restoring near-kickoff
capture buys roughly one month of the season back on the only gate that can promote a model.**
That is the whole value case, and it is a measurement value case, not a betting one.

---

## 7. GitHub Actions vs an always-on worker

### 7.1 Is GitHub Actions sufficient? No — and the insufficiency is structural

Three independent facts:

1. **The platform drops scheduled events, and the drop rate rises with the ask.** v9's own
   measurement (`v9/.github/workflows/predict.yml:70-80`): 224 requested -> 1 delivered for
   live_scanner, 144 -> 1 for predict, against 100 -> 3 for the capture workflows; queue wait 0s
   at median, p90 and max (seed). This is not queueing, it is dropping.
2. **The only remedy available inside Actions — ask for less — reduces absolute capture.** Measured
   in section 3: ratio up, captures down, T-30m coverage −55.4 pp, 17/17 leagues.
3. **Actions cannot aim at a minute.** The NEAR workflows already compensate by looping internally
   for 40 minutes with adaptive spacing (`std_odds_capture.yml:191-231`) — an in-process scheduler
   bolted inside a cron job, because the cron cannot be trusted. That is an always-on worker with
   a 40-minute lifetime and a 55-minute timeout, delivered at random times. The architecture has
   already converged on the answer; it is just running in the wrong container.

The single regime that ever achieved 84.7% T-30m coverage did so with predict at 5-minute cadence
and a repo-wide ask of ~696 runs/day — a configuration that has since been abandoned *because the
platform would not serve it*. There is no setting of the Actions cron that gets both.

### 7.2 Costed comparison

Compute is not the deciding variable, and it is worth saying so precisely so the decision is not
made on a price.

| | GitHub Actions (today) | Always-on worker |
|---|---|---|
| compute cost | **$0** — v9 is a public repo, so Actions minutes are free (`v10/src/data/v9_source.py:118-122` reaches v9 over unauthenticated `raw.githubusercontent.com`) | **$0–5/month** (Oracle Always Free tier $0; Hetzner CX22 ~EUR 4.5/mo; Fly.io shared-cpu-1x 256 MB ~$2/mo) |
| API-Football credits for near capture | ~2,800/day currently spent on the far horizon; ~85 useful near rows/day | 28.4 fixtures/day mean x 60 polls (10-min from T-6h, 2-min from T-1h) = **1,704 calls/day**; worst observed day 89 fixtures = 5,340 |
| resulting API-Football utilisation | 11,220/75,000 = 15.0% | 12,900/75,000 = 17% mean; 16,600 = 22% on the worst day |
| timing determinism | none — 10% to 125% of requested runs, arriving at unpredictable minutes | exact; T-2m achievable |
| achieved T-30m coverage | 29.4% (current regime), 84.7% at best ever | design target ~100%, bounded only by whether a book quotes |
| failure mode | silent partial coverage that looks healthy | single point of failure — needs a heartbeat |
| v9 code change required | yes (frozen — invariant 3 forbids it) | **none** — the worker belongs in Pro, which is not frozen |

Total incremental cash cost of the worker: **at most about USD 60/year**, and plausibly zero. The
system it informs has 1,159 settled bets and −91.63 units on the ledger. The cost is not the
question; the reason to hesitate is whether a consumer exists, and section 6 shows one does: the
promotion gate's `min_clv_n`, and v11's residual test.

### 7.3 What the worker must and must not do

**Recommendation: build a near-kickoff odds worker, in Pro, on API-Football credits.** Specifically:

- **Runs where Pro runs, not in v9.** v9 is frozen (invariant 3) and this is a new capability, not
  a bug fix. Pro already reads v9 over HTTP and writes only its own store; the worker writes
  `book_odds_snapshots` / `market_snapshots` partitions through `season_store.append`, which is
  run-partitioned and cannot conflict.
- **Kickoff-aware, not cron-aware.** Poll each fixture at T-6h, then every 10 min to T-1h, then
  every 2 min to kickoff. 60 polls/fixture, 1,704 calls/day mean. Stop at kickoff — invariant 5.
- **Funded from API-Football, never from The Odds API.** The Odds API is projected 89,842/100,000
  this month with no headroom, and it bills markets x regions, so 1,704 polls/day across OU25 and
  BTTS on `uk,eu` would be roughly 6,800 credits/day = ~204,000/month, twice the entire plan.
  **Do not intensify the multi-book path without a separate, explicit plan decision.** Note the
  asymmetry this creates: the API-Football path is Bet365-only, so the worker buys a fresh
  two-sided close from one book, not a fresh consensus. That is still a real close, and section
  5.1 shows the wider panel is already reconstructable at lower frequency from what we have.
- **Keeps the existing WIDE Actions crons as the far-horizon backstop.** They cover T-7d..T-24h at
  96.8–99.2% already, and a worker outage must not lose the whole curve.
- **Writes a heartbeat row into Pro's `data_quality` table every cycle**, so a dead worker is a
  failed check rather than silently thinning coverage — which is exactly how the 08-29..09-07
  NEAR-branch outage stayed invisible for nine days.

**And it must not do any of the following**, which are the attractive-looking adjacent moves:

- It must not create a live-odds or in-play path. Invariant 5.
- It must not become a reason to bet. Nothing here changes the seed's verdict that the edge thesis
  is unproven and that three zero-information predictors beat the model. A better close makes the
  residual test *measurable*, which may well end with a clearer negative.
- It must not touch props. Invariant 2.
- Its output must not be used to re-fit any threshold on the fixtures it improved. Invariant 6.

---

## 8. Cheap fixes worth doing regardless of the worker

Ranked by value per hour, all inside Pro:

1. **Normalise `captured_at` to a single ISO form on import** (`v10/src/importers/current_wowza.py:246`)
   and parse with `format="mixed"` on read. Today the column mixes 63,663 Z-suffixed and 12,912
   naive values; `pd.to_datetime(col, utc=True)` NaTs 83% of the rows without raising. Every
   downstream timing analysis is exposed to this. HOURS.
2. **Flag the 25,724 placeholder-midnight `captured_at` rows** (33.6% of `odds_histories`, some
   dated 2024-08-10) with a `SYNTHETIC_TIMESTAMP` quality flag. Pro's discipline is to store dirty
   rows and flag them; these are currently indistinguishable from real observations. HOURS.
3. **Populate `n_books` in `movement_observations` from `book_odds_snapshots`** and stop declaring
   `INSUFFICIENT_BOOKS` unassessed on 159,029 rows. The data exists now. HOURS.
4. **Assess `STALE_CLOSE_PRICE` / `STALE_ENTRY_PRICE`** from `book_odds_snapshots.snapshot_ts`
   (`wowza-v11/src/movement.py:162-166`) and add close staleness in minutes as a first-class
   column. This is the single change that stops `clv_quality = OK` from over-claiming. DAYS.
5. **Record a market observation timestamp on the predictions path**, or mark those 95,855 rows
   explicitly as timing-unknown so no analysis silently uses `observed_at` as an observation time.
   The right fix is upstream (v9 emitting an odds timestamp in `predictions.csv`) and v9 is frozen,
   so the honest interim is an explicit `TIMESTAMP_IS_INGEST` flag on import. HOURS.
6. **Re-measure window D after 2026-09-20.** n=34 is not evidence. Three more weekends gives ~200
   fixtures and settles whether `87c9104c` helped at all.

---

## 9. Where I disagree with the seed, with the numbers

| seed claim | my measurement | note |
|---|---|---|
| T-6h 91.6%, T-1h 32.6%, T-30m 14.5%, T-10m ~7% | 86.2% / 60.8% / 44.0% / 16.2% | different sources and timestamp handling; also a lower bound either way (section 1.2) |
| ~81% of odds observations on fixtures >24h out | **57.6%** | measured on `captured_at`/`snapshot_ts`, n=146,908 |
| 0.6% in the final hour | **6.86%** | |
| 5.4% post-kickoff | **0.019%** | 280x divergence; likely `observed_at` used as observation time |
| only 34.9% of book groups have >=3 books, median 2 | reproduced exactly on that metric, but the LOCF panel is **median 9 books, 94.3% with >=3** | the per-instant metric is a price-change-storage artefact |
| API-Football at 3% of 75,000/day | **15.0%** 14-day mean; peak 42,616 (57%) | 3% matches only the partial current day |
| predict asks 57/day and gets ~15% | >= 35% median, 78.8–82.5% on the pre-cut weekend | write-passes are a lower bound on delivered runs |
| the NEAR branch was unreachable 08-29..09-07, fixed in `87c9104c` | confirmed as a real outage, but it is **not the main cause** — `book_odds` (which comes from predict, not the capture workflows) degraded *more* than `v9_capture` (−59.3 pp vs −38.0 pp) | the dominant cause is the 08-27..08-30 schedule cut, not the string-matching bug |

The last row is the one that matters for what gets fixed next: `87c9104c` repaired the smaller of
two regressions, and the larger one is still in force.

---

## 10. Confidence and open questions

**PROVEN** (computed this run or read at the cited line): findings 1, 2, 3, 5, 6, 7, 8, 9, 10, 12, 13.
**SUPPORTED**: findings 4 (n=34, direction only), 11 (Odds API budget taken from the seed), 14
(write-passes are a lower bound), and the ~350-calls-per-WIDE-window figure (code comment).
**PLAUSIBLE**: that restoring pre-cut near-kickoff density restores the pre-cut clean-close yield
(60.3% / 49.5%) rather than something lower — the A window benefited from a 5-minute predict
cadence that will not return, and the worker's Bet365-only feed is a narrower panel.
**SPECULATIVE**: that a genuinely fresh close changes the sign of anything in the residual test.
Label it and move on.

Open questions I could not answer:

1. What does The Odds API charge for the next plan tier? The multi-book path's future is a pricing
   question I have no data for, and I will not invent a number.
2. Did window D degrade *below* window C, or is it league mix and n=34? Re-measure after 09-20.
3. `book_odds_snapshots` write-passes exceeded the predict cron on 2026-08-24/25 (48 and 50 vs 40
   requested). Manual dispatches are the likely explanation, but I did not verify it, and if
   something else writes that file the delivery lower bound is looser than stated.
4. How much of the 3–7 day WIDE spend could be reallocated rather than added? Answering it needs a
   movement measurement — how often a price actually changes between T-7d and T-24h — which is
   answerable from `book_odds_snapshots` and which I did not run.
5. `market_snapshots.book_count` is null throughout, and `bookmaker` holds only two synthetic
   values. Whether to backfill it from `book_odds_snapshots` or to deprecate the columns is a
   schema decision for whoever owns the contract.

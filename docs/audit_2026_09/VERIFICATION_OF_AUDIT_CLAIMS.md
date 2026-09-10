# Independent verification of the audit's load-bearing claims

**2026-09-10.** Written by the orchestrating session, not by any of the fifteen agents. Its
purpose is to re-derive the audit's money-relevant claims from the primary data before anyone
acts on them, because a subagent's confident number is not evidence — and two of the numbers
checked here needed correcting.

Method: v9's own `output/bets_ledger.csv` and Pro's `book_odds_snapshots`, `v9/config.py` for
thresholds, flat 1u, bootstrap CIs at 8,000 resamples, `scipy` for tests. Every result below is
segmented **per model** and, where the sample allows, **per model × tier** — never pooled, per
the standing instruction that each model owns its own tiers and its own results.

---

## 1. The per-model × tier scoreboard — the answer to "is this worth my money"

Settled, live-source, post-`PERFORMANCE_CUTOFF_DATE` (2026-08-10), flat 1u:

| model | tier | n | win% | P/L | ROI/bet | 95% CI | verdict |
|---|---|---:|---:|---:|---:|---|---|
| new_format | MARKSMAN | 84 | 41.7% | +0.07u | +0.001 | [−0.253, +0.259] | indistinguishable from 0 |
| new_format | SNIPER | 18 | 50.0% | +3.79u | +0.211 | [−0.366, +0.798] | indistinguishable from 0 |
| new_format | VALUABLE | 128 | 41.4% | −8.62u | −0.067 | [−0.260, +0.133] | indistinguishable from 0 |
| **standard** | **MARKSMAN** | **38** | **28.9%** | **−13.78u** | **−0.363** | **[−0.662, −0.028]** | **SIGNIFICANTLY LOSING** |
| standard | SNIPER | 4 | 50.0% | +0.50u | +0.125 | — | insufficient data |
| standard | VALUABLE | 82 | 39.0% | −14.59u | −0.178 | [−0.391, +0.046] | indistinguishable from 0 |

Track totals:

| model | n | P/L | ROI/bet | 95% CI | verdict |
|---|---:|---:|---:|---|---|
| new_format | 230 | −4.76u | −0.021 | [−0.170, +0.131] | flat — no edge demonstrated either way |
| **standard** | **124** | **−27.87u** | **−0.225** | **[−0.404, −0.038]** | **SIGNIFICANTLY LOSING** |

**[PROVEN]** Exactly one cell is statistically losing money: **standard MARKSMAN**, 28.9% strike
rate over 38 bets. The `standard` track as a whole is significantly losing, and its CI excludes
zero. `new_format` is not losing significantly — it is simply not demonstrating anything.

**The cell carrying real money — standard O/U SNIPER, $30/bet — has n=4.** Nothing can be
concluded about it in either direction. It is unvalidated, not disproven. That is a materially
different statement from "the standard track loses", and both are true simultaneously.

## 2. `edge_pct` carries no measurable information about P&L — CONFIRMED, with a correction

Agent 6 reported corr +0.022, p=0.664, n=416. Re-derived on 792 settled live bets:

| scope | n | pearson | spearman |
|---|---:|---|---|
| pooled | 792 | +0.0132 (p=0.711) | +0.0224 (p=0.529) |
| new_format | 630 | +0.0078 (p=0.846) | +0.0115 (p=0.774) |
| standard | 159 | −0.0926 (p=0.245) | +0.0279 (p=0.727) |

Per model × tier: six measurable cells, **not one significant**, and the sign is negative in four.

**[PROVEN]** `edge_pct` — the quantity that selects every bet and sizes every stake — has no
measurable relationship to realised P&L in any model or tier.

**A correction to an intermediate claim of my own.** An ROI-by-edge-bucket pass first returned
Spearman −0.900, p=0.037 for `standard`, i.e. significantly *inverted*. That does **not** survive
requiring n≥15 per bucket: it was driven by buckets of n=1 and n=5. With small buckets dropped it
is −0.500, p=0.667. The defensible claim is **"no information"**, not "inverted". Recorded because
the inverted version is the more dramatic one and it is wrong.

The per-bet correlation is also intrinsically low-powered — a single bet's P&L is a binary
outcome times a price. The bucketed monotonicity test is the fairer instrument, and it agrees:
no cell shows ROI rising with claimed edge.

## 3. Odds > 3.0 — CONFIRMED, and it is a `new_format` problem only

| band | n | % of bets | P/L | ROI/bet | 95% CI |
|---|---:|---:|---:|---:|---|
| ≤1.7 | 1 | 0.1% | +0.62u | +0.620 | — |
| 1.7–2.1 | 281 | 35.5% | −27.85u | −0.099 | [−0.214, +0.013] |
| 2.1–2.5 | 307 | 38.8% | −9.02u | −0.029 | [−0.157, +0.099] |
| 2.5–3.0 | 155 | 19.6% | −10.65u | −0.069 | [−0.269, +0.140] |
| **>3.0** | **48** | **6.1%** | **−25.85u** | **−0.539** | **[−0.807, −0.206]** |

**[PROVEN]** `odds > 3.0` is the only band whose CI excludes zero. It is 6.1% of bets and
**35.5% of the net loss** (−25.85u of −72.75u). Agent 6's "37.6%" is confirmed — the small
difference is sample scoping, and the denominator matters: against *gross* losing bets rather
than net P/L the share is 8.7%.

**The part the pooled framing hid.** Excluding odds > 3.0, per model:

| model | as-is | with ≤3.0 only |
|---|---|---|
| new_format | n=630, −39.92u, ROI −0.063 | n=**582**, **−14.07u**, ROI −0.024 |
| standard | n=159, −29.83u, ROI −0.188 | n=**159**, **−29.83u**, ROI −0.188 |

**All 48 longshot bets are `new_format`. `standard` has none, and is completely unchanged.** So
this is a new-format selection defect worth ~26u, and per invariant 1 any fix belongs on that
track alone. It explains none of `standard`'s loss.

Relatedly, `edge_pct` correlates with the price taken **only in standard** (Spearman +0.4549,
p=1.7e-09, n=159) and not at all in new_format (+0.0120, p=0.76). Agent 3's +0.5874 on backtest
rows is the same effect. So "edge is a longshot machine" is true of `standard`'s selection
*within* the 1.75–3.0 range, while new_format's problem is that nothing stops it going above 3.0.
Two different faults; they should not be described as one.

### `MAX_OU_ODDS` does not exist

Root `CLAUDE.md` claimed under Data gotchas that "Main O/U odds are bounded by `MAX_OU_ODDS` to
reject stale or fringe prices." Grepping all of `v9/` for that identifier returns nothing. What
exists is `MIN_OVER_ODDS = MIN_UNDER_ODDS = 1.75`, a lower bound only. The sole upper bounds in
the estate are `live_scanner.MAX_FAIR_OVER = 3.30` (live path, and on *fair* odds) and
`sharp_tracker`'s garbage-data limits (>15). **There is no upper bound on the main O/U path**,
which is precisely how 48 bets above 3.00 were placed. `CLAUDE.md` corrected the same day.

## 4. Best-price execution — REAL but the headline was overstated

Agent 4's F1: v9 takes the first-listed bookmaker's price rather than the best, worth +2.03 ROI
points, CI [+1.41, +2.73], n=217.

**The mechanism is PROVEN at the code level.** `v9/src/predict.py:135-138` reads
`if pt == 2.5 and nm == "Over" and not ov25: ov25 = pr` — first book in the API response wins and
later books are never compared. `book_odds_snapshots` shows the cost directly: one fixture-side
at one instant quoted betsson 1.55, gtbets 1.58, leovegas_se 1.60. v9 books 1.55.

**The size depends entirely on how "available" is defined, and this is where the claim needs
care.** Three measurements on the same 323/221 matched settled bets:

| definition | n | v9 worse on | paired delta | p |
|---|---:|---:|---|---|
| best price seen *any time* pre-kickoff | 323 | 91.6% | **+6.51pp** [+5.34, +7.71] | 7e-24 |
| median per-instant best | 323 | 50.8% | +0.36pp [−0.43, +1.13] | 0.36 |
| **best at the decision instant** | **221** | **45.2%** | **+1.25pp [+0.62, +1.91]** | **0.00026** |

The first is **look-ahead contaminated** — a maximum over the whole pre-kickoff window requires
knowing in advance when the peak would occur. It should never be quoted as an achievable gain.
The third is the executable one: at the moment v9 decides, shop every book in hand and take the
best. n=221 matches Agent 4's 217 and 45.2% matches their 46.6%, so we measured the same
population; the delta differs by snapshot-matching choice.

**[PROVEN] +1.25 ROI points, CI [+0.62, +1.91], p=0.00026.** When a better price existed it was
on average **3.57%** better. This is the only positive-expectation finding verified in this pass,
and it needs no model to be correct.

**But state the size honestly against the hole it has to fill.** `standard` is −22.5 ROI points
and `new_format` −2.1. A +1.25pp execution gain is real, free of model risk, and does **not**
make either track profitable. It is worth doing on its own merits, not as a rescue.

**It is not a one-line change.** `edge = model_prob − 1/odds`, so taking a better price *raises*
`edge_pct` and can move a bet's tier and stake. Agent 4 flags this too. It is a live selection
change and carries the approval requirement that implies.

---

## What was left alone, deliberately

Nothing in this pass changed a model, a threshold, a stake, or a collector. Every item above is
either already-shipped presentation/scheduling work or a recommendation requiring explicit
approval:

* adding an upper odds bound (new_format) — **needs approval**, it is a live selection change
* best-price selection in `predict.py` — **needs approval**, it moves tiers via `edge_pct`
* anything about the standard MARKSMAN cell — **needs approval**

## Standing caveats

* Post-cutoff samples are small: 124 `standard` and 230 `new_format` settled bets. "Significantly
  losing" at n=124 is a real result but a fragile one, and it should be re-run as the season adds
  settlements rather than treated as settled fact.
* `book_odds_snapshots` begins 2026-08-19, so only 221–323 of 792 settled bets can be matched to
  per-book quotes at all. The best-price result is measured on the recent subset.
* Multiple comparisons: this pass tested ~20 hypotheses. The two survivors (odds>3.0 and
  best-price) have p-values of 1e-3 and 3e-4, which clear a Benjamini-Hochberg screen at q=0.05
  over that count, but the design doc's estate-wide correction over ~200 segments is the right
  frame and is stricter than this.

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

## 3b. The staked-tier defect was MISDIAGNOSED — production never used 14%

I had been reporting, across several sessions, that "37 of 38 staked standard MARKSMAN bets had a
measured edge below the 14% MARKSMAN threshold they were supposedly selected for." Agent 3 and
Agent 6 independently flagged this as misdiagnosed, and they are right.

`config.py:282` is `MARKSMAN_THRESHOLD = float(os.getenv("MARKSMAN_THRESHOLD", "0.14"))` — 0.14 is
only the **default**. `predict.yml` sets the environment for every production run:

```
LEAGUE_SNIPER_CAP: "0.12"
MARKSMAN_THRESHOLD: "0.08"
VALUABLE_THRESHOLD: "0.03"
```

So the deployed MARKSMAN floor has been **0.08 since 2026-08-21**, not 0.14. Measuring against
0.14 was measuring against a rule production does not apply. Re-measured with the production env
loaded, and against each bet's **own league's** effective threshold
(`LEAGUE_MARKSMAN_THRESHOLDS` covers only `Bundesliga 2` and `League Two`, both 0.12):

| threshold used | bets below it |
|---|---|
| 0.14 — config default, what I wrongly used | 37 of 38 (97.4%) |
| 0.08 — deployed global | 25 of 38 (65.8%) |
| **own league's effective floor** | **25 of 38 violate; 13 meet it** |

| league | effective floor | n | edge range | meets floor | P/L |
|---|---:|---:|---|---:|---:|
| Bundesliga 2 | 12.00% | 8 | 3.61–13.72 | 1/8 | −3.23u |
| Championship | 8.00% | 7 | 3.36–9.12 | 1/7 | −0.81u |
| La Liga 2 | 8.00% | 9 | 3.59–14.08 | 6/9 | −6.92u |
| League One | 8.00% | 6 | 3.26–11.43 | 4/6 | −3.86u |
| Ligue 2 | 8.00% | 1 | 4.27 | 0/1 | −1.00u |
| Serie B | 8.00% | 7 | 3.62–12.54 | 1/7 | +2.04u |

**[PROVEN]** A real defect survives — **two thirds of staked standard MARKSMAN bets do not meet
the floor they are nominally selected by**, with edges as low as 3.26%. But the magnitude and the
framing were both wrong, and the correct diagnosis matters: the deployed thresholds live in
**workflow environment variables, not in `config.py`**. Any future threshold analysis that reads
`config.py` and stops there is measuring a system that isn't running.

Also corrected: I had characterised the drift adjustment as promoting the worse bets. Per drift
signal on these 38: `Confirmed` n=20 ROI −0.205 (mean edge 4.83), `Conflicted` n=13 ROI −0.525
(mean edge 9.00), `Neutral` n=2, `New` n=3. The bets with the *highest* claimed edge
(`Conflicted`) did worst — consistent with edge carrying no information — but at these cell sizes
no drift-signal claim is supportable in either direction. Withdraw it rather than reverse it.

## 4. Best-price execution — Agent 4 was RIGHT; my first correction of it was wrong

Agent 4's F1: v9 takes the first-listed bookmaker's price rather than the best, worth +2.03 ROI
points, CI [+1.41, +2.73], n=217.

> **This section was published on 2026-09-10 claiming Agent 4 had overstated the effect at
> +2.03pp and that the executable figure was +1.25pp. That claim was mine and it was wrong.**
> I read `book_odds_snapshots` as a snapshot panel — grouping by `(fixture-side, instant)` — when
> it is a **change-log** storing consecutive-distinct changes only. At any single instant only
> the books that just moved are present, so I saw a median of **3** books per bet instead of the
> **8** actually quoting: a 2.7x understatement of panel depth, and therefore of the best price
> available.
>
> Read correctly, with last-observation-carried-forward per bookmaker up to the decision instant:
> **+1.99 ROI points, CI [+1.37, +2.67], p=7.2e-09, n=221** — v9 worse on 55.7% of bets, mean
> improvement +4.05% when one existed. Against Agent 4's +2.03pp CI [+1.41, +2.73] n=217, that is
> the same measurement.
>
> The sting: Agent 4's report states this trap explicitly ("read as a panel it understates book
> depth 6x") and I made it anyway while checking their arithmetic. The change-log storage format
> has now caused three separate wrong conclusions in this estate — sparse near-kickoff rows
> looking like a dead NEAR loop, Agent 5's 35-55-day gate estimate, and this. **Anything reading
> a `*_snapshots` table must carry forward per entity before aggregating.**

**The mechanism is PROVEN at the code level.** `v9/src/predict.py:135-138` reads
`if pt == 2.5 and nm == "Over" and not ov25: ov25 = pr` — first book in the API response wins and
later books are never compared. `book_odds_snapshots` shows the cost directly: one fixture-side
at one instant quoted betsson 1.55, gtbets 1.58, leovegas_se 1.60. v9 books 1.55.

**The size depends entirely on how "available" is defined, and this is where the claim needs
care.** Three measurements on the same 323/221 matched settled bets:

| definition | n | v9 worse on | paired delta | p | status |
|---|---:|---:|---|---|---|
| best price seen *any time* pre-kickoff | 323 | 91.6% | +6.51pp [+5.34, +7.71] | 7e-24 | **look-ahead — never quote** |
| best at decision instant, last-instant books only | 221 | 45.2% | +1.25pp [+0.62, +1.91] | 3e-04 | **wrong — panel misread** |
| median per-instant best | 323 | 50.8% | +0.36pp [−0.43, +1.13] | 0.36 | wrong, same cause |
| **best at decision instant, LOCF panel** | **221** | **55.7%** | **+1.99pp [+1.37, +2.67]** | **7e-09** | **correct** |

The first is look-ahead contaminated — a maximum over the whole pre-kickoff window requires
knowing in advance when the peak would occur, and it should never be quoted as achievable. The
middle two understate the panel, as described above. The last is the executable one: at the moment
v9 decides, take the best price among all books whose last-known quote is on file.

**[PROVEN] +1.99 ROI points, CI [+1.37, +2.67], p=7.2e-09, n=221.** When a better price existed it
was on average **4.05%** better. This is the only positive-expectation finding verified in this
pass, and it needs no model to be correct.

**But state the size honestly against the hole it has to fill.** `standard` is −22.5 ROI points
and `new_format` −2.1. A +1.99pp execution gain is real, free of model risk, and does **not**
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

## 5. The v11 placebo battery is void — a one-line `merge_asof` bug

The red team's headline, and it lands on code this session's predecessor wrote. Reproduced from
scratch in pandas 3.0.3:

`wowza-v11/scripts/v11_momentum_control.py:158` ends `_asof()` with
`return out.sort_index()["p_at"]`. **`pd.merge_asof` resets the index**, so `out` carries a fresh
`RangeIndex` in `target_ts`-sorted order; `sort_index()` on that is a no-op and cannot recover the
caller's row order. `build()` then does `d[name] = d["v11_p_market"] - _asof(...)`, which aligns
by index — so every movement value lands on the wrong row. Minimal repro returns `[0.1, 0.2, 0.3]`
where the correct answer is `[0.3, 0.1, 0.2]`.

**Every momentum, movement and placebo number from that script is void**, including the result
that has been quoted as settled ("mean reversion 0.995, fixed anchor 0.753, shuffled residual
0.711 all beat v9's 0.703 toward-rate"). It was also handed to all thirteen auditors in their
shared brief as `PROVEN`. It is not proven; it is unmeasured. The fix is to carry the caller's
index through the sort explicitly rather than trying to restore it afterwards.

**What replaces it as the load-bearing negative result** is Agent 6's calibration gap, which the
red team attacked with a selection-bias simulation and could not dent: **claimed 0.5430 vs
realised 0.4066 = +13.64pp, z=7.81, n=792**; +16.80pp on staked bets and +10.78pp on
never-staked VALUABLE. The gap being the *same size* in both is the finding — the tier ladder
carries no information. And Brier: model 0.2583 versus the bookmaker's own **vigged** price
0.2368.

That is a better result than the one it replaces, because it is denominated in the model's own
metric rather than in a movement series.

### My own `merge_asof` use in §4 was checked, not assumed

The same function appears in the best-price test above. Verified empirically rather than argued:
that code reads `odds`, `pnl` and the matched price off the **same merged frame** and never
assigns a merge result back onto another frame by index, so row-internal consistency holds
regardless of the index reset. Confirmed with a constructed case.

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

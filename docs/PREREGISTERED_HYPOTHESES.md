# Pre-registered hypotheses

Written **before** the confirming data exists. Invariant 6: the strategy is frozen before the
backtest; thresholds are never changed after seeing results.

Anything in this file was found by looking at data we already had. That makes each one a
**hypothesis**, not a result — and the reason to write it down here, with its numbers and its
falsification condition fixed, is so the next test is a genuine out-of-sample check rather than a
story told about numbers already seen.

Rules for this file:

- Add a hypothesis only with its test **fully specified**: the statistic, the cut points, the
  sample definition, the decision threshold, and what would falsify it.
- Never edit a hypothesis after data arrives. Add a **result** section beneath it instead.
- Cut points and thresholds are LITERALS here and must be read from here by the evaluation code,
  never recomputed from the new sample. Recomputing quartiles on new data silently changes the
  test into a different one that happens to share a name.

---

## H1 — the model's information is concentrated where it DISAGREES with the price

**Registered:** 2026-08-19
**Registered at v9 sha:** 06c6b41ed2b1 · **Pro sha:** 899d748 (approx, this commit)
**Status:** OPEN

### Origin, stated honestly

The aggregate market-relative test kept weakening as the sample grew:

| sample | C vs B logloss | p |
|---|---|---|
| n=156 (bet-only) | +0.02752 | 0.0057 |
| n=343 (+176 controls) | +0.00786 | 0.1125 |
| n=564 (+352 controls) | +0.00396 | 0.1965 |

I first read that as noise decaying toward zero. That reading was **wrong**, and the correction
came from the user pointing out we have almost no live data. Stratifying showed the aggregate was
being **diluted**, not decaying: the declined-fixture controls sit at exactly zero improvement
because the model barely disagrees with the price on them, so averaging them in drags the mean down
arithmetically.

In-sample stratification on n=564, blend weight fixed at w=0.20:

| stratum | mean \|p_model − p_market\| | C vs B logloss | p | 90% CI |
|---|---|---|---|---|
| v9 BET these | 0.1703 | +0.01126 | 0.1370 | [−0.00049, +0.02456] |
| v9 DECLINED (controls) | 0.0482 | −0.00044 | 0.7482 | [−0.00264, +0.00185] |
| gap Q1 [0.000, 0.031) | — | −0.00132 | 0.0382 | [−0.00239, −0.00024] |
| gap Q2 [0.031, 0.065) | — | −0.00045 | 0.7883 | [−0.00319, +0.00232] |
| gap Q3 [0.065, 0.123) | — | −0.00029 | 0.9367 | [−0.00622, +0.00557] |
| **gap Q4 [0.123, 0.541]** | — | **+0.01790** | 0.1172 | [+0.00014, +0.03768] |

Two patterns, both post-hoc:

1. The improvement lives essentially **only in Q4**, the top disagreement quartile.
2. In Q1, where the model agrees with the price, blending **hurts** (p=0.0382) — coherent, since
   adding a weaker signal to an already-good estimate is noise injection.

This was found after seeing the data, across four strata, so it is not evidence. It is a
prediction to be tested.

### The hypothesis

On fixtures **not used to form this hypothesis**, blending the model into the market at w=0.20
improves log-loss versus the market alone **when |p_model − p_market| ≥ 0.123**, and does not
improve it below that threshold.

### The test, fixed now

- **Sample:** settled OU 2.5 fixtures with `match_date > 2026-08-18` — strictly after the data
  behind the table above. Both BET and DECLINED fixtures included; excluding declines is the
  selection bias that produced the spurious p=0.0057.
- **Statistic:** mean per-fixture log-loss difference, market-only minus blend, positive meaning
  the blend is better. Paired block bootstrap, `block=5`, `n_boot=4000`, matching what produced the
  numbers above.
- **Blend weight:** **w = 0.20**, fixed. Not tuned on the new sample, and not tuned on the old one.
- **Strata cut points:** **0.031 / 0.065 / 0.123** on `|p_model − p_market|`, taken as LITERALS
  from this document. Do **not** recompute quartiles on the new sample.
- **Minimum sample:** 150 fixtures in the high stratum. Below that the test is under-powered and
  the verdict is `INSUFFICIENT`, not `REFUTED` — absence of significance at small n is not
  evidence of absence.
- **Decision:**
  - `SUPPORTED` — high stratum improvement > 0 with bootstrap p < 0.05, **and** the low stratum
    (gap < 0.123) shows no significant improvement.
  - `REFUTED` — high stratum improvement ≤ 0, or p ≥ 0.05 with n ≥ 150 in that stratum.
  - `INSUFFICIENT` — fewer than 150 fixtures in the high stratum.
- **Also recorded, not part of the decision:** whether Q1 remains negative. If blending genuinely
  hurts on agreement, the design implication is that blend weight should scale with disagreement
  rather than being flat — but that is a follow-up hypothesis, not this one.

### What would falsify it

The high stratum showing no improvement, or the low stratum improving just as much. The latter
would mean the effect is not about disagreement at all and the stratification was noise-fitting.

### Known confounds, acknowledged in advance

- Every price behind the table above is a **single captured snapshot**, effectively an opening
  price. Forward capture of open→moving→close only began 2026-08-19, so a later test using closing
  prices is measuring a **different and better** quantity. That is an improvement, but it means a
  changed result may reflect the price series, not the model.
- The sample is heavily new-format and summer/second-tier: 485 of 564 fixtures were `new_format`.
- The market itself scored only 0.69378 against a 0.69224 base-rate baseline on this sample, i.e.
  barely informative. On a sharper market the same model may add nothing.

### Result

_Empty until the evaluation runs. Do not edit the sections above._

---

## H2 — CLV readiness gates everything downstream

**Registered:** 2026-08-19 · **Status:** OPEN (measurement, not a claim)

The weekly audit measured CLV present on **366 of 4,795 settled tips (7.6%)**. v11 requires
`MIN_CLV_N = 150` clean observations **per segment** before any signal may reach `BET`, so at that
coverage every signal stays `PAPER` regardless of model quality.

**Recorded monthly, no decision attached:** clean CLV observation count per segment, and the
implied date at which the first segment reaches 150 at the current accrual rate. This exists to
make the bottleneck visible over time rather than to be accepted or rejected.

---

## F1 — FINDING: contaminated historical CLV (already fixed upstream 2026-08-10)

**Found:** 2026-08-19 · **Status:** CLOSED for new data, residue handled at read time

170 of 366 CLV rows in `bets_ledger.csv` are impossible, e.g. entry 1.96 vs "closing" 1.20 giving
`clv_pct` +63.3.

**Root cause — v9 commit `c19ca31`, 2026-08-10**, "stop corrupt O/U lines entering the closing-odds
archives": the O/U parser matched ANY bet whose name contained "Over/Under", so non-goal markets
(corners, cards, team totals) leaked their "Over 2.5" price into the goal `over25` key, and BTTS
prices were copied into `over25`/`under25`. Those prices sit near 1.20-1.30, which manufactures a
large positive CLV out of nothing.

| evidence | value |
|---|---|
| contaminated rows whose closing == an archived **BTTS** price | **22** |
| clean rows whose closing == a BTTS price | **0** |
| contamination by month | Jul **81%**, 1-9 Aug **45%**, after 2026-08-09 **0%** |
| fix landed | **2026-08-10** — the day after the last bad row |

**Two of my own diagnoses were wrong, recorded because both were plausible:**

1. *"mis-joined market or fixture"* — refuted. The archived `over25`/`under25` pair at the bad
   moment is a coherent market: overround median **1.016** across 3,446 fixtures. It was a real
   market, just not the goals one.
2. *"in-play prices used as the close"* — the leaked prices mimic a 0-0 second half almost exactly
   (under shortens, over lengthens), which is why it fitted so well. But `src/predict.py` already
   skips kicked-off fixtures (`if dt <= now: continue`), and no in-play goals price would land
   exactly on a BTTS quote.

For terminology: `over25` and `under25` are **not different markets**. They are the two bettable
sides of ONE line from one model probability, which is why "wrong market" could never have explained
a 46% -> 80% move.

**Consequence measured:** unfiltered `new_format` mean CLV reads **+26.26%**; clean it is
**-0.015%**. Segments cleared to BET goes 1 -> **0**. The apparent CLV edge was entirely
contamination.

**Handling.** `c19ca31` states it cleaned data going forward and left "existing archive rows
unchanged... a one-time historical re-filter can be done separately if wanted". That re-filter is
now applied at **read time** — `CLV_PLAUSIBLE_ABS = 25%` in `src/pipelines/monthly_eval.py` and
`v11_shadow._rolling_clv_stats` — rather than by rewriting history, which also honours "no deleting,
we can't lose data". Both raw and filtered figures are always reported so the filter's effect stays
visible.

**Separately adopted as good practice, not as a fix for this:** `src/market/curve.py` defines one
curve for every model and market — opening -> moving -> closing with the close **locked 60s before
kick-off**, 7 days of history, and in-play rows returned separately for their own table. v11 already
guarded this on its own snapshots; this makes it explicit and reusable.

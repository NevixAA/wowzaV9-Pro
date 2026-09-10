# AGENT 6 — ECONOMIC EDGE AUDIT

**Date:** 2026-09-10 · **Scope:** v9 `bets_ledger.csv`, `side_bets_ledger.csv`, `clv_records.csv`,
`book_odds_snapshots.csv`, `models/best_params_standard.json`, `output/backtest_*`; Pro
`clv_enriched.csv`. Read-only. Everything below is recomputed this run unless marked otherwise.

---

## HEADLINE

**The −68.75u live loss is statistically indistinguishable from betting the same 788 prices at
random and paying the spread (H0 mean −37.60u, sd 31.9, p=0.164). The system has no measurable
skill and no measurable anti-skill — and `edge_pct`, the number every tier and stake is derived
from, has ZERO correlation with whether the bet wins (Spearman +0.0037, p=0.918, n=788). The
largest measured, model-free improvement available is +4.35pp of ROI from taking the best
available price instead of the one v9 actually took — 74.6% of bets were struck below the best
book on the board.**

---

## THE NUMBER FIRST: WHERE IS THE MONEY

`bets_ledger.csv` holds 5,163 rows, of which **4,115 are `source=backtest`** — not live money.
The live book is:

| | n | win% | P/L | flat ROI | 95% boot CI | P(ROI>0) | P(ROI>3%) |
|---|---|---|---|---|---|---|---|
| **live, settled** | **788** | **40.9%** | **−68.75u** | **−8.72%** | −16.6 .. −0.7 | 0.015 | 0.001 |
| live staked (SNIPER+MARKSMAN) | 376 | 41.0% | −25.10u | −6.68% | −18.2 .. +5.0 | 0.132 | 0.052 |
| live VALUABLE (paper/half) | 412 | 40.8% | −43.65u | −10.59% | −21.3 .. 0.0 | 0.025 | 0.006 |
| backtest rows (not money) | 260 | 40.4% | −19.58u | −7.53% | | | |

Total settled 1,048 = −88.33u. The seed's "1,159 settled / −91.63u" is close but stale; VOID rows
(122, all pnl 0) account for most of the difference. Live window 2026-04-26 .. 2026-09-09.

Risk metrics, live book: **profit factor 0.852, max drawdown 84.97u** — the drawdown *exceeds*
the total loss, i.e. there was never a profitable stretch to give back. On the staked tiers alone
max DD is 30.15u = **$904 at the planned $30/bet, 30% of the $3,000 bankroll**. Kelly-weighted ROI
(`kelly_pct` as the weight) is mildly better than flat in every cut (all −6.57% vs −8.72%; staked
−3.77% vs −6.68%), which given finding 2 is noise, not a staking result.

**57.6% of the live loss sits in the paper tier.** VALUABLE is −43.65u of −68.75u. The staked
tiers lost 25.10u. Any statement of the form "the system lost 91 units" is describing a book that
is 52% never-staked signals.

---

## FINDINGS

| # | Finding | Evidence | Conf | Impact | Fix |
|---|---|---|---|---|---|
| 1 | −68.75u is indistinguishable from blind betting + vig | H0 p=0.164 (5% ovr), 0.076 (3%) | PROVEN | CRITICAL | — |
| 2 | `edge_pct` carries zero information about outcome | ρ=+0.0037 p=0.918; logit β=+0.443 z=0.45 p=0.652, n=788 | PROVEN | CRITICAL | WEEKS |
| 3 | 74.6% of bets below best available price; +4.35pp ROI left on table | n=319, mean shortfall +5.32% | PROVEN | HIGH | DAYS |
| 4 | Real vig measured for the first time: OU25 1.0696/book, 1.0464 at ≥3 books | 33,523 two-sided quotes | PROVEN | HIGH | — |
| 5 | Model loses to the bookmaker's own VIGGED price on Brier and log loss | 0.2586 vs 0.2372; 0.7143 vs 0.6667 | PROVEN | CRITICAL | WEEKS |
| 6 | Reported +12.28% CLV is a measurement artifact; true CLV ≈ 0/negative | 25% of rows carry the whole mean; clean subset +0.34%, beat 38.0% | PROVEN | HIGH | DAYS |
| 7 | No CLV measurement exists for the bets that carry the money | `clv_records.csv` 1,756 rows, 100% props | PROVEN | HIGH | DAYS |
| 8 | Only two segments have a CI excluding zero: odds>3.0 and drift=Conflicted | −53.85% CI[−80.9,−20.6]; −20.99% CI[−38.9,−2.9] | PROVEN | HIGH | HOURS |
| 9 | Backtest has no demonstrated predictive validity for live league ROI | k=18, ρ=+0.325 p=0.188, sign agreement 50.0% | SUPPORTED | CRITICAL | MONTHS |
| 10 | OPEN QUESTION resolved: `edge_pct` IS the decision-time edge | src/ledger.py:175,198; update_results.py:832 | PROVEN | MEDIUM | — |
| 11 | The 6.11% median has TWO causes, not one: optimizer thresholds + drift loophole | 7 of 38 legit under best_params_standard.json; 31 not (−11.35u) | PROVEN | HIGH | HOURS |
| 12 | +18.10u side book: p=0.031 vs a measured fair line, but fails every corroborating test | n=147; model AUC 0.4898 < book 0.5054; CLV −2.51% | SUPPORTED | MEDIUM | — |
| 13 | New-format places 79% of live bets; every recorded backtest shows total_bets=0 | backtest_metrics_history.json, 4 entries, last 2026-06-17 | PROVEN | HIGH | DAYS |
| 14 | Ledger pools bets from different threshold regimes | 7 sub-bar SNIPERs tagged drift="New"; config.py:283 | PROVEN | MEDIUM | — |
| 15 | book_odds_snapshots BTTS slice has `kickoff_utc` 100% NULL | 52,236 of 144,982 rows (36%) | PROVEN | MEDIUM | HOURS |
| 16 | Pro's canonical CLV store closes 10.6h AFTER kickoff at the median | `minutes_close_before_kickoff` median −638 | PROVEN | HIGH | DAYS |

---

## 1. THE LOSS IS NOT EVIDENCE OF A BAD MODEL. IT IS EVIDENCE OF NO MODEL.

Monte-Carlo null: take v9's own 788 entry prices, assume **zero skill** — the true probability is
the de-vigged implied probability `(1/odds)/overround` — and let the coin fall 100,000 times.

| assumed overround | H0 mean P/L | sd | observed | p(obs ≤ H0) |
|---|---|---|---|---|
| 1.03 | −23.00u | 32.1 | −68.75u | 0.076 |
| **1.05** | **−37.60u** | **31.9** | **−68.75u** | **0.164** |
| 1.07 | −51.46u | 32.0 | −68.75u | 0.294 |

And the true overround is not assumed — it is now measured (§4) at **1.0696** for OU25. At that
figure the observed loss is squarely inside the null. **The system paid the spread 788 times.**

This *corrects* the natural reading of the −91.63u headline. There is no evidence the model
actively picks the wrong side. The bets' realised win rate (0.4086) sits 1.2–3.6pp below the
implied probability of the price paid depending on the vig assumption — none of it significant at
n=788 (z=−0.43 against the measured consensus fair line, n=319). The verdict is **zero
information**, not negative information, and that distinction matters: a negative-information
model can be inverted; a zero-information model has to be replaced.

---

## 2. `edge_pct` DOES NOT PREDICT ANYTHING (the money version of the v11 placebo result)

| sample | ρ(edge, win) | p | ρ(edge, pnl) | p | logit β_edge (controls 1/odds) | z | p |
|---|---|---|---|---|---|---|---|
| all live (788) | +0.0037 | 0.918 | +0.0166 | 0.641 | +0.443 | +0.45 | 0.652 |
| standard (159) | −0.0345 | 0.666 | +0.0279 | 0.727 | −9.00 | −1.32 | 0.188 |
| new_format (626) | −0.0003 | 0.994 | +0.0035 | 0.930 | +0.175 | +0.17 | 0.867 |

Realised ROI by claimed edge band is not merely flat — it is non-monotone in a way no amount of
noise-smoothing rescues:

| edge band | n | win% | P/L | ROI |
|---|---|---|---|---|
| ≤4% | 109 | 41.3% | −10.34u | −9.49% |
| 4–6% | 234 | 39.3% | −30.55u | −13.06% |
| **6–8%** | **76** | **48.7%** | **+7.14u** | **+9.39%** |
| **8–10%** | **89** | **34.8%** | **−18.26u** | **−20.52%** |
| 10–14% | 115 | 44.3% | −0.57u | −0.50% |
| 14–19% | 65 | 40.0% | −6.90u | −10.62% |
| >19% | 100 | 40.0% | −9.27u | −9.27% |

The best and worst buckets are adjacent. The tier system, the per-league thresholds, the drift
upgrades and the Kelly fractions are all monotone functions of a quantity with ρ=0.004 against
the outcome. **v11's placebo battery said the residual is uninformative on the price series; this
says the same thing in units, on real settled money, with p=0.918.** The two results are
independent and they agree.

Note the trap in the AUC numbers. On the 319 bets joinable to real book data, `p_model` has
AUC 0.5826 — which looks like discrimination. But `p_model = edge_pct/100 + 1/odds`, and the
consensus fair probability on the same rows has AUC 0.5806. **The AUC belongs to the price, not
the model.** Strip the price and the edge component's contribution is ρ=0.004.

---

## 3. THE BIGGEST AVAILABLE WIN IS EXECUTION, NOT MODELLING

`output/book_odds_snapshots.csv` (imported 2026-09-09; 144,982 rows, 24 real books, window
2026-08-19..09-10) makes this measurable for the first time. Joining 319 settled live O/U bets to
the last pre-kickoff quote from every book on the same fixture (median **11 books** observed per
fixture; 95.3% have ≥3):

* v9's entry odds **matched or beat the best available price on only 25.4%** of bets.
* Median entry **2.25** vs median best available **2.36**.
* Mean shortfall `best/entry − 1` = **+5.32%** (median +5.05%, p90 +13.98%); `best > entry` on
  **74.6%** of bets.
* Counterfactual: same bets, same outcomes, best available price → **ROI −5.23% vs −9.58%
  realised, +4.35pp**.

That is larger than every model effect measured anywhere in this audit. It is parameter-free,
requires no retraining, and violates no invariant.

Two honest caveats. `best` is the maximum over each book's *last pre-kickoff* quote, not
necessarily a price simultaneously live at the moment v9 tipped — so +4.35pp is an upper bound.
And it presumes accounts at the books quoting it. Halve it for realism and it still dominates.

The structural cause is a recording gap: **no v9 bet records which bookmaker's price it took.**
`market_snapshots.bookmaker` carries only the synthetic `v9_selected_best` / `v9_capture` and
`book_count` is entirely null, and `bets_ledger` has no bookmaker column at all. The label says
"selected best"; the measurement says 25.4%. Nobody could see the gap because nothing logged it.
**Bookmaker-level attribution — an explicit remit item — is impossible on the current schema.**

---

## 4. THE REAL VIG (first measurement in this system)

Pre-kickoff two-sided quotes only. 100% of OU rows in `book_odds_snapshots` are genuinely
pre-kickoff (max 168h out); the BTTS slice has no kickoff stamp at all (§ finding 15).

| market | two-sided quotes | median per-book overround | best-of-book (median 2 books) | best-of-book, ≥3 books | arb share |
|---|---|---|---|---|---|
| OU25 | 33,523 | **1.0696** (p25 1.0598, p75 1.0847) | 1.0581 | **1.0464** | 0.3–0.7% |
| BTTS | 22,860 | **1.0795** | 1.0707 | 1.0496 | 1.1–1.2% |
| OU35 | 7,197 | 1.0650 | 1.0520 | 1.0387 | 0.5–1.3% |
| OU15 | 849 | 1.0603 | 1.0542 | 1.0427 | 0.2–1.2% |

Consequences that were previously guessed at and are now numbers:

1. **The hurdle is 4.6–8.0%, not "a couple of percent".** With ≥3 books shopped it is 4.6%.
2. **`edge = p_model − 1/odds` systematically understates true edge**, because `1/odds` is a
   vigged probability. At a fair p of 0.45 and an overround of 1.0696, a *perfectly calibrated*
   model reports edge = 0.45 − 0.4813 = **−3.1%**. So `VALUE_THRESHOLD=0.04` corresponds to a
   true edge of roughly +0.9pp vs fair, and `MARKSMAN_THRESHOLD=0.14` to roughly +10.9pp. The
   thresholds are not as loose as they look — but they are also not the quantities the comments
   next to them claim, and nothing in the codebase does this conversion.
3. Arbitrage across the 24 books is 0.3–1.2% of fixtures. Not a business, but a sanity check that
   the price collection is real.

---

## 5. CALIBRATION: THE VIGGED BOOK PRICE BEATS THE MODEL

`p_model` back-solved exactly as `edge_pct/100 + 1/odds`; `p_book = 1/odds` (vig **included** —
a deliberately handicapped comparator).

| sample | n | mean p_model | mean p_book | actual | model bias | Brier model / book | LogLoss model / book |
|---|---|---|---|---|---|---|---|
| all live | 788 | 0.5435 | 0.4442 | 0.4086 | **+13.5pp** | 0.2586 / **0.2372** | 0.7143 / **0.6667** |
| staked | 376 | 0.5776 | 0.4313 | 0.4096 | **+16.8pp** | 0.2678 / **0.2340** | 0.7373 / **0.6598** |
| post-cutoff staked | 184 | 0.5199 | — | 0.3967 | +12.3pp | 0.2482 / **0.2319** | 0.6897 / **0.6557** |
| standard staked | 46 | 0.5263 | 0.4299 | 0.3261 | **+20.0pp** | 0.2596 / **0.2299** | 0.7126 / **0.6525** |

Against the **measured consensus de-vigged fair line** (n=319): model overstates fair by
**+8.58pp**; Brier 0.2443 vs fair 0.2339; mean EV vs fair **−6.00%** against a realised ROI of
−9.58%. Against Pinnacle specifically (n=84, too small to conclude): model AUC 0.5139 vs Pinnacle
0.5480.

The one nuance that is not purely damning: on the consensus join the model's *ranking* (AUC
0.5826) equals the consensus's (0.5806). Calibration, not discrimination, is where the model
fails — but see §2: that AUC is the price's, not the model's.

---

## 6. THE REPORTED CLV IS AN ARTIFACT. THERE IS NO POSITIVE CLV.

`bets_ledger.clv_pct`, 681 of 788 settled rows carry a close:

* mean **+12.28%**, median **+0.00%**, **beat_close 47.3%** (below half), 18.4% exactly equal.
* **170 rows (25.0%) have |clv| > 50%** and contribute **+12.02pp of the +12.28% mean** — i.e.
  essentially the entire reported CLV.
* Those rows' closing odds have median **1.30** against an entry median of **2.14**. No
  pre-match O/U 2.5 line travels from an implied 47% to an implied 77%.
* **104 of them are UNDER bets closing ≤1.35, and they win 51.9% against the 40.3% UNDER base
  rate (z=2.4, p=0.016). Zero OVER bets close ≤1.35.** A late in-play Under on a 0-0 trades at
  ~1.20; that asymmetry is the signature.
* Mechanism, read in code: `update_results.py:329` takes `snapshots[-1]` and
  `_closing_for_market` takes `m.sort_values("snapshot_ts").iloc[-1]` — **neither filters on
  kickoff**, despite the docstring saying "last recorded odds before kick-off". In
  `output/newformat_odds_dense.csv`, **30.6% of last-per-fixture snapshots are stamped at or
  after `match_date` 12:00**.
* **Clean subset (|clv| ≤ 50, n=511): mean CLV +0.34%, beat_close 38.0%, ROI −9.88%.** And
  ρ(clv, pnl) = 0.030, p=0.493 — the recorded CLV does not even correlate with the outcome.
* Post-cutoff staked bets (n=178, the most recent and best-collected): **beat_close 38.2%, mean
  CLV −1.23%**.

**Conclusion: v9 does not beat the closing line.** Any argument that rests on "+12% CLV proves we
have an edge even if the P&L is noisy" is resting on 170 contaminated rows. This does not
materially distort ROI (AUC(clv→win) is only 0.529) — it distorts the *diagnostic that was being
used to justify continuing*.

### And there is no CLV at all for the bets that carry the money

* `v9/output/clv_records.csv`: 1,756 rows. **Every `bet_id` prefix is `PLAYER`.** Markets: sot
  1,190, goals 295, cards 158, sot2 94, assists 18, sot3 1. **Zero team O/U rows.** 1,618 of
  1,756 are `notes=AVOID` — not even bets.
* Pro's `clv_enriched.csv` (18,593 rows) is the same props universe. Median
  `minutes_close_before_kickoff` = **−638** (the "close" is captured **10.6 hours after
  kickoff**); 2,490 rows are explicitly post-kickoff; only **761** are strictly pre-kickoff, and
  those beat close 10.5% of the time. Quality flags: OK 8,582 (mean CLV **−0.02%**, beat_close
  42.2%, mean clean CLV −1.65%), CLOSE_EQUALS_ENTRY 4,023, CLOSE_NOT_PROVEN_PRE_KICKOFF 3,251,
  CLV_IMPLAUSIBLE 1,610, NO_CLOSE 1,127. Only **672 of 18,593 rows have a result**.

So the canonical CLV infrastructure measures, with a post-kickoff close, the one market the
system will never bet. The 8,582 OK-quality rows say mean CLV −0.02%. Pro's flags are doing their
job — the flags are the finding.

---

## 7. WHICH SEGMENTS ARE BAD, AND WHICH ARE MERELY SMALL

Only **two** segments in the whole live book have a 95% bootstrap CI excluding zero.

**(a) Longshots — odds > 3.0.** n=48, **−25.85u, ROI −53.85%, CI[−80.9, −20.6], P(ROI>0)=0.001.**
14.6% win rate against a mean implied 30.6%. **6.1% of the bets, 37.6% of the total loss.**

| odds band | n | win% | P/L | ROI | share of loss |
|---|---|---|---|---|---|
| ≤2.5 | 586 | 44.7% | −33.25u | −5.67% | 48.4% |
| 2.5–3.0 | 154 | 34.4% | −9.65u | −6.27% | 14.0% |
| **>3.0** | **48** | **14.6%** | **−25.85u** | **−53.85%** | **37.6%** |

Against the fair (de-vigged) probability these bets underperform by 14pp (z≈−2.2, p≈0.03). v11
already has a **longshot hard cap** in `edge_engine.py`; v9 has none. n=48 is below the brief's
evidence bar, so this is SUPPORTED not PROVEN — but the CI, the directional prior from v11's
props research (−41% to −57% on longshots) and the loss share all point the same way, and the fix
is a bounded odds ceiling, not a fitted parameter.

**(b) `drift_signal = Conflicted`.** n=135, **−28.33u, ROI −20.99%, CI[−38.9, −2.9],
P(ROI>0)=0.010.** This is the better-powered version of the seed's standard-MARKSMAN finding.

| drift signal | n | win% | P/L | ROI | CI |
|---|---|---|---|---|---|
| New | 479 | 40.7% | −45.84u | −9.57% | −19.2 .. +0.6 |
| **Conflicted** | **135** | **35.6%** | **−28.33u** | **−20.99%** | **−38.9 .. −2.9** |
| Confirmed | 62 | 40.3% | −1.79u | −2.89% | −31.9 .. +27.5 |
| Neutral | 112 | 48.2% | +7.21u | +6.44% | −14.1 .. +27.4 |

`_apply_drift_adjustment` (src/betting.py:205) handles SNIPER+Conflicted by **downgrading it one
step to MARKSMAN — which is still a ¾-stake bet.** The market moving against the model is the one
drift state with a CI excluding zero, and the code's response is to keep betting it smaller. On
n=135 the correct response is NO_BET. This is the single highest-confidence actionable segment in
the audit.

**Everything else spans zero.** Reproduced in full so the "merely small" cases are not mistaken
for good ones:

| model × tier | n | win% | P/L | ROI | CI | P(ROI>3%) |
|---|---|---|---|---|---|---|
| new_format VALUABLE | 296 | 41.9% | −24.08u | −8.14% | −20.7 .. +4.6 | 0.043 |
| standard VALUABLE | 113 | 38.9% | −16.57u | −14.66% | −34.5 .. +5.2 | 0.040 |
| **standard MARKSMAN** | **39** | **30.8%** | **−13.16u** | **−33.74%** | **−63.3 .. −1.3** | 0.013 |
| new_format SNIPER | 215 | 41.9% | −12.00u | −5.58% | −20.6 .. +9.6 | 0.133 |
| standard SNIPER | 7 | 42.9% | −0.10u | −1.43% | −68.6 .. +94.3 | INSUFFICIENT |
| new_format MARKSMAN | 115 | 42.6% | +0.16u | +0.14% | −21.4 .. +21.5 | 0.400 |

Per-league staked, n≥5 — **not one league has a CI excluding zero in either direction**:
Sweden +15.26% (n=43), Finland +13.96% (n=24), Serie B +41.75% (n=8), Brazil +6.61% (n=31),
Austrian +15.08% (n=13) on the plus side; Norway −32.53% (n=32), La Liga 2 −49.17% (n=12),
Bundesliga 2 −47.00% (n=9), League One −64.33% (n=6) on the minus side. Every one of these is
INSUFFICIENT_DATA. The correct reading of the per-league table is **"we do not know", 17 times.**

Other cuts, for completeness: UNDER 550 bets −50.55u (−9.19%) vs OVER 238 −18.20u (−7.65%);
August −49.23u (n=423) vs September +8.87u (n=115); pre-cutoff −7.62% (n=372) vs post-cutoff
−9.71% (n=416) — the cutoff bought nothing. On time-to-kickoff, **575 of 788 settled bets were
first seen >72h out** (ROI −8.46%) and no near-kickoff band reaches usable n; this matches the
collection finding that 81% of odds observations sit >24h from kickoff.

---

## 8. THE OPEN QUESTION, ANSWERED

> *"Why is `edge_pct` ~9% on rows tiered SNIPER? Either `edge_pct` is recorded at settlement, or
> tiering uses a different `best_edge`."*

**Neither. `edge_pct` is the edge the decision was actually made on, and the 6.11% median is
real.** Proven by code read:

* `src/ledger.py:198` writes `"edge_pct": round(edge*100, 2)` in the **same dict literal** as
  `"signal_tier": tier`, where `edge = float(row.get("best_edge", 0.0))` — the value used by
  `_base_tier`/`_apply_drift_adjustment` on that run.
* `src/ledger.py:175` overwrites `edge_pct`, `kelly_pct` and `drift_signal` **only when
  `_TIER_RANK[new] > _TIER_RANK[cur]`** — so tier and edge always move together to the run that
  produced the higher tier.
* `update_results.py:832` touches only `result`, `pnl`, `closing_odds`, `clv_pct`. **Nothing
  writes `edge_pct` at settlement.**

One residual staleness worth knowing: if a fixture is re-seen at a *higher edge but the same
tier*, `edge_pct` is not updated. So `edge_pct` = the edge at the moment the row's peak tier was
first reached — a lower bound on the strongest edge ever seen, and exactly the decision-time
value for the tier recorded. Fit for purpose.

### The mechanism has TWO causes, and the seed found only one

Of the 38 standard MARKSMAN rows below 14% (P/L −12.16u):

* **7 are legitimate.** `models/best_params_standard.json` marks **Championship
  (`marksman_th`=0.05, `sniper_th`=0.07)** and **Serie B (0.10 / 0.12)** as `approved`, and
  `src/betting.py:184-190` **prefers the optimized threshold over both the per-league config and
  the global 0.14** for approved leagues. A Championship MARKSMAN at 5.58% edge is the system
  working as designed. This also fully explains the SNIPER-at-8.74% row: Championship's SNIPER
  bar is **0.07**.
* **31 are the loophole (−11.35u).** Bundesliga 2 (8 rows, bar 0.20), La Liga 2 (9, bar 0.14),
  League One (6, bar 0.14), Serie B (6 at ~5.3% against a 0.10 bar), Ligue 2 (1), Championship
  (1). Nothing in `_base_tier` admits these. They arrive via
  `_apply_drift_adjustment`'s third branch — `VALUABLE + Confirmed → MARKSMAN` — which
  **carries no edge floor at all**, while the upgrade one level above it
  (`MARKSMAN + Confirmed → SNIPER`) requires `best_edge >= DRIFT_UPGRADE_EDGE` (0.10).

So the asymmetry the seed identified is real and costs −11.35u of the −12.16u, but 18% of the
"defect" is the *threshold optimizer* legitimately setting a 5% MARKSMAN bar in Championship on
the strength of a backtest that §9 shows has no demonstrated live validity. **Fixing the drift
guard alone leaves the larger problem standing.**

### And the SNIPER question has a third answer: regime pooling

Only **12 of 222 SNIPER rows** fall below their own league's SNIPER bar (ROI −45.42%, n=12,
INSUFFICIENT_DATA), and only 3 of those are drift-`Confirmed`. **Seven are tagged `New`** — no
drift adjustment at all. Their edges cluster at 10.2–10.6%, just above the **old**
`SNIPER_THRESHOLD` of 0.10 that `config.py:283` records as "raised from 0.10" to 0.12.

**The ledger therefore pools bets made under different threshold configurations**, and
`best_params_standard.json` is rewritten by `optimize_standard_thresholds` on *every backtest*.
Any tier-level ROI computed from this ledger is a mixture across regimes. This caps the
resolution of every number in §7 and is a reason to record the active threshold set on each
ledger row.

---

## 9. THE PROCESS PROBLEM: THE BACKTEST DOES NOT PREDICT LIVE

The current backtests (both files written 2026-09-02) against the live book, per league, live
n≥10 (k=18):

| | Spearman | p | Pearson | p | sign agreement |
|---|---|---|---|---|---|
| all leagues (k=19) | +0.205 | 0.399 | +0.063 | 0.796 | 47.4% |
| live n≥10 (k=18) | +0.325 | 0.188 | +0.282 | 0.258 | **50.0%** |

Live-bet-weighted backtest ROI **−0.05%** against realised **−7.72%**. The inversions land
exactly on the leagues the configuration trusts most:

| league | backtest ROI | backtest n | live ROI | live n |
|---|---|---|---|---|
| La Liga 2 | +0.13% | 111 | **−32.24%** | 34 |
| League One | +4.11% | 36 | **−37.53%** | 30 |
| Championship | +5.04% | 27 | **−20.48%** | 21 |
| Argentina Primera | +1.55% | 244 | −22.61% | 57 |
| Mexico Liga MX | +33.13% | 16 | −0.50% | 46 |
| Finland | −28.78% | 18 | **+19.35%** | 43 |
| Serie B | +26.07% | 73 | +41.53% | 17 |

k=18 has low power and ρ=+0.325 does not *rule out* a moderate relationship. But 50.0% sign
agreement is a coin flip, and `best_params_standard.json` `approved` **Championship on
`roi_oos`=+3.32 with `bets_oos`=164** — live returned −20.48%. **The per-league thresholds, the
`approved` flag, and the "ROI +53.5%" comments beside `LEAGUE_SNIPER_THRESHOLDS` are all
downstream of an instrument with no demonstrated out-of-sample validity.** Verdict:
INSUFFICIENT_DATA to claim the backtest works — which is itself the finding, because the system
treats it as settled.

Corroborating the seed on gating, verified this run: `retrain.py:370` `save_models(...)` precedes
`retrain.py:393` `run_backtest(...)`, and `_print_comparison` at 407 only prints — there is no
accept/reject in the file. `output/backtest_metrics_history.json` holds **4 entries, last
2026-06-17**. Its 2026-06-17 standard entry claims `roi_% = 22.01` with `sniper_roi_% = 60.64`;
live standard delivered **−18.76%** (n=159). **Every new-format entry in that file shows
`total_bets: 0` and `roi_%: 0.0`** — the track carrying **79% of live bets (626 of 788)** has no
backtest bet on record in the metrics history at all, though `backtest_by_league_newformat.csv`
(2026-09-02) now shows 603 bets at −0.68%. Pro's `registry.py::evaluate_gate` is called only from
`registry.py:239` (`promote`) and from `tests/test_registry_gates.py` — no pipeline invokes it.

---

## 10. THE ONE ENCOURAGING NUMBER, AND WHY IT IS NOT YET EVIDENCE

`side_bets_ledger.csv`: 254 rows, **147 settled, 59.9% win, +18.10u, ROI +12.31%, bootstrap
CI[−2.8, +27.9], P(ROI>0)=0.944** — the CI spans zero. Window 2026-08-09 .. 2026-09-09, one month.

Against a **measured** consensus fair line from `book_odds_snapshots` (n=126 joinable, no assumed
overround): H0 mean **−6.63u** vs observed **+13.62u**, **p=0.0314** one-sided. With an assumed
overround instead: p=0.0145 (1.05), 0.0078 (1.07), 0.0252 (1.03) — robust to the assumption.

That is the strongest single result in this audit. Every corroborating test fails:

* **The model's own probability ranks worse than the bookmaker's.** n=126: model AUC **0.4898**
  vs consensus fair AUC 0.5054. Below chance.
* **CLV is negative.** n=135: beat_close 47.4%, mean −2.51%, AUC(clv→win) 0.4705.
* **The stated edge is uncorrelated with the outcome.** ρ(`ev_pct`, pnl)=+0.097 p=0.243;
  ρ(`edge_pct`, pnl)=−0.018 p=0.826.
* **It is one market and one league.** BTTS is 88 of 147 rows and **+17.16u of the +18.10u**;
  Argentina Primera is 96 of 147 and +13.58u. `over15` (n=59) is +0.94u, ROI +1.6%.
* BTTS won 11.2pp more often than the consensus fair line said (0.5682 vs 0.4566, n=88, z=+2.10)
  **while its EV vs that line was −5.06%** — the return came from outcomes, not from price.
* Selection effect: I tested BTTS and Argentina *because* they were the winners. With ~20
  market × tier × league cells, p=0.03 on the best one is expected roughly once by chance.

So: a genuine +18u that beats a properly measured null at p=0.03, produced by a model whose
probabilities rank below the bookmaker's, with negative CLV, in one market, in one league, in one
month, at **n=147 < 250**. **SUPPORTED, INSUFFICIENT_DATA. Keep it on paper and keep collecting.**
Note also that `book_odds_snapshots`' BTTS slice has `kickoff_utc` **100% NULL** (52,236 of
144,982 rows), so no time-to-kickoff or strict pre-kickoff analysis is possible for precisely the
market carrying this P&L.

---

## 11. WHAT I TRIED THAT DID NOT WORK (adversarial against my own findings)

I expected the measured consensus EV to be the replacement for `edge_pct`, and the band table is
seductive:

| EV vs consensus fair | n | win% | P/L | ROI |
|---|---|---|---|---|
| < −5% | 182 | 37.4% | −25.46u | −13.99% |
| −5% .. 0% | 92 | 41.3% | −9.26u | −10.07% |
| 0% .. +5% | 29 | 48.3% | +1.63u | +5.62% |
| +5% .. +10% | 13 | 46.2% | +1.07u | +8.23% |
| > +10% | 3 | 66.7% | +1.45u | +48.33% |

Binary split: EV>0 → n=45, +4.15u, **ROI +9.22%, CI[−23.4, +42.6]**; EV≤0 → n=274, −34.72u,
**ROI −12.67%, CI[−25.7, +0.6]**. A 21.9pp spread.

**It does not hold up.** ρ(EV, pnl) = **+0.019, p=0.733** — the continuous relationship is null,
the monotone band table is 5 noisy cells, and the EV>0 arm's CI spans zero at n=45. I am
reporting it as PLAUSIBLE / INSUFFICIENT_DATA, not as a rule. The band table nearly fooled me and
it will fool the next reader; the rank correlation is the number to quote.

---

## 12. WHAT TO DO, IN ORDER OF EVIDENCE PER UNIT OF WORK

1. **Log the bookmaker and the full book on every bet, and take the best price** (§3). +4.35pp
   measured upper bound, no model change, no invariant touched. It is also the precondition for
   *any* future bookmaker-level attribution, which today is impossible.
2. **Fix `closing_odds` to require `snapshot_ts < kickoff_utc`** — `update_results.py:329` and
   `_closing_for_market`. This is a bug fix, permissible under the v9 freeze, and it stops the
   only diagnostic anyone trusts from lying (§6). Then extend `clv_records` to team bets, which
   it does not cover at all.
3. **`Conflicted` → NO_BET** (n=135, ROI −20.99%, CI[−38.9, −2.9]) and **an odds ceiling around
   3.0** (n=48, −53.85%, 37.6% of the loss). Both are removals of existing behaviour, not fitted
   parameters. Both are threshold changes and therefore **Pro-only under invariant 3** — stage in
   Pro, measure forward, do not touch v9 this season.
4. **Give `_apply_drift_adjustment`'s `VALUABLE → MARKSMAN` branch the same `DRIFT_UPGRADE_EDGE`
   floor its sibling has** (src/betting.py:212). Symmetry restoration, −11.35u attributable, but
   note §8: it fixes 82% of a defect whose other 18% is the optimizer.
5. **Stamp the active threshold set on each ledger row** (§8) so tier-level ROI stops being a
   mixture across regimes.
6. **Wire `registry.py::evaluate_gate` into Pro's retrain and persist
   `backtest_metrics_history.json` as a workflow artifact.** Until then no retrain is
   evaluable, and the last record is 2026-06-17 (§9).
7. **Recalibrate rather than retrain.** The model's ranking on real bets equals the consensus's
   (AUC 0.5826 vs 0.5806) while its probabilities run 8.6–13.5pp hot. Isotonic/Platt
   recalibration **on outcomes** is the indicated move. Fitting to odds is exactly what §3 of the
   brief forbids and would collapse the residual by construction — do not.

**Do not do:** raise stakes anywhere; promote the BTTS/Argentina result (n=147, model AUC<0.5,
negative CLV); re-tune per-league thresholds on the backtest (§9); read the −91.63u as proof the
model is inverted (§1); or read any single-league table in §7 as anything but "we do not know".

---

## 13. REMIT ITEMS I COULD NOT ANSWER

* **Bookmaker segmentation** — impossible. No bet in either ledger records the book it was
  struck with; `market_snapshots.bookmaker` has two synthetic values and `book_count` is null.
  §3 is the closest available proxy and it is a counterfactual, not an attribution.
* **Residual-bucket segmentation** — no residual column exists in either ledger. v11's residual
  lives in its own shadow log against price series, not against settled bets.
* **Time-to-kickoff at entry** — `bets_ledger` records `match_date` (a date) but no kickoff time,
  so my TTK bands rest on a 15:00 proxy and the near-kickoff cells have n=17–55. Treat the whole
  TTK cut as indicative only. `book_odds_snapshots` has real `kickoff_utc` for the OU markets and
  should be the basis going forward — but not for BTTS, where it is 100% null.
* **Kelly ROI** is reported using the recorded `kelly_pct` as a weight; `USE_KELLY` is off in
  production, so this is a counterfactual, not history.

---

### Reproduction

Scripts used this run (scratchpad, not committed):
`econ.py` (segmentation + bootstrap), `econ2.py` (tier forensics, edge→outcome, CLV),
`econ3.py` (leakage test, side ledger), `econ4.py` (H0 nulls, Pro CLV),
`econ5.py` (book_odds_snapshots overround, consensus fair, best-price counterfactual).
Interpreter: `v9/.venv/Scripts/python.exe`. Bootstrap B=20,000; Monte-Carlo nulls B=100k–200k.

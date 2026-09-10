# AGENT 12 — Cost / ROI Engineering

**Audit date:** 2026-09-10 · **Scope:** where the next $100 and the next 100 engineering hours should go
**Data as measured this run** (v9 ledgers re-read 2026-09-10 14:06; numbers differ slightly from the
2026-09-08 seed because the files have moved on — see §0).

---

## HEADLINE

**The quantity that governs every tiering and staking decision in v9 — `edge_pct` — has no measurable
relationship to money (corr +0.022 with P&L, permutation p = 0.664, n = 416) and a *significantly
negative* relationship to closing-line value (corr −0.202, p = 0.00005, n = 405, bootstrap CI
[−0.290, −0.113]). The higher the claimed edge, the harder the market moves against the bet.
Therefore every candidate that buys better *inputs* to that edge — a bookmaker panel, an exchange
feed, more credits, more leagues, more markets, xG, lineups — is improving the input to a function
whose output is uncorrelated with return. The next $100 should be spent on nothing. The next 100
hours should be spent building the measurement apparatus in Pro (model registration + the existing
promotion gate + probability-space CLV), which is free, already 80% written, and would immediately
and correctly refuse the current champion.**

---

## 0. Where I disagree with the seed, with the number

| Seed claim | My measurement | Verdict |
|---|---|---|
| `MARKSMAN_THRESHOLD = 0.14`; 37 of 38 staked MARKSMAN bets (97%) were below it | **Production runs 0.08**, not 0.14 — `v9/.github/workflows/predict.yml:191`. Also `LEAGUE_SNIPER_CAP: "0.12"` at :190 clamps all 8 hand-set SNIPER thresholds to 0.12, and `VALUABLE_THRESHOLD: "0.03"` at :192. Against the *effective* live thresholds, **21 of 42 staked rows comply** | **REFUTED (mis-specified baseline).** The "97% violation" statistic just re-states that the live MARKSMAN floor is 0.08 |
| The 37 drift-promoted rows are −12.78u / −34.5% ROI → fixing the drift floor recovers that | Rows **below** the effective threshold (the true drift artifacts, all `drift=Confirmed`): n=21, **−2.81u, −13.4% ROI**. Rows that **comply**: n=21, **−10.47u, −49.9% ROI** | **REFUTED.** The drift-promoted cohort is the **better** half. Fixing the floor addresses 21% of the loss and leaves the worse 79% |
| OPEN: is `edge_pct` recorded at settlement, or does tiering use a different `best_edge`? | **Neither.** Recorded at tip time; see §2 | **ANSWERED.** The 6.11% median **is** the edge the decision was made on |
| API-Football at 3% of 75,000/day ("huge headroom") | Mean daily total **11,220 = 15.0%** of limit (last 14d); all-time mean 14.6%; **max ever 42,616 = 56.8%** | **REFUTED.** Headroom is real but 5x smaller than stated, and mean usage (11,220) *exceeds* the old Pro cap of 7,500 — the Ultra plan is correctly sized, not wasteful |
| Near-kickoff coverage: T-1h 32.6%, T-30m 14.5%, T-10m ~7%, 5.4% post-kickoff | On `book_odds_snapshots` (92,746 timestamped obs, 798 fixtures): T-1h **40.2%**, T-30m **32.7%**, T-10m **17.4%**, post-kickoff **0.0%**, >24h out **63.6%** of obs (not 81%) | **PARTIALLY REFUTED.** The new table is materially better and has zero post-kickoff contamination. Downgrades the always-on collector from urgent to MEDIUM |
| `side_bets_ledger`: 143 settled, +18.56u flat — the one bright spot | 147 settled, +18.10u, **ROI +12.3% ± 15.4pp → CI [−3.1%, +27.7%] spans zero**. Tier ordering **inverted**: VALUABLE +21.4% > SNIPER +14.2% > MARKSMAN −12.2%. corr(edge,pnl) = +0.017, p = 0.847. Mean CLV **−2.507%** | **NOT EVIDENCE.** n=147 < 250, CI spans zero, tiers random, CLV negative |
| `evaluate_gate()` — "NOTHING CALLS IT" | It **is** called (`v10/src/models/registry.py:239` from `promote()`), imported by 3 pipelines (`weekly_audit.py`, `experiment.py`, `shadow.py`) and unit-tested (`v10/tests/test_registry_gates.py`). But **`v10/registry/` contains only `.gitkeep`** — zero records | **REFINED.** The gate is complete; the missing piece is *registration*, which is much cheaper than building a gate |
| bets_ledger: 1,159 settled, 41% win, −91.63u | 1,048 settled (WIN/LOSS) + 122 VOID, 40.7% win, **−88.33u** | Consistent; the file has advanced two days |

---

## 1. Findings table

| # | Finding | Evidence | Conf | Impact | Fix |
|---|---|---|---|---|---|
| F1 | The claimed edge carries **no** information about P&L | corr = +0.0220, perm p = 0.664; Spearman ρ = +0.0257, p = 0.602; n = 416 | PROVEN | CRITICAL | — |
| F2 | Bets underperform the **book's own implied probability** by 3.85pp while claiming +5.11pp | realised−implied = −3.85%; shortfall 8.95pp ± 4.65pp → **CI excludes zero**; n = 416 | PROVEN | CRITICAL | — |
| F3 | CLV is **significantly negatively** correlated with claimed edge | corr = −0.2022, n = 405, perm p = 0.00005, bootstrap CI [−0.290, −0.113]; monotone by bucket: 0–4%→+1.18%, 14%+→−2.96% | PROVEN | CRITICAL | — |
| F4 | `edge_pct` is recorded **at tip time**, not settlement — the 6.11% median is the decision edge | `ledger.py:198` writes on insert; `:169–179` overwrites only on strict tier-rank increase then `continue`s; no settlement path writes it | PROVEN | HIGH | — |
| F5 | Production thresholds are **not** the config defaults, and the optimizer path is **uncapped** | `predict.yml:190–192`; `betting.py:154–157` uses `float(_opt["sniper_th"])` with no `_SNIPER_CAP` → Championship live at SNIPER 0.07 / MARKSMAN 0.05 | PROVEN | HIGH | DAYS |
| F6 | Fixing the drift-promotion floor is **negative EV** — it targets the better half | below-threshold n=21 −13.4%; compliant n=21 −49.9%; CI ±48.5pp; violates invariants 3 and 6 | PROVEN | MEDIUM | — |
| F7 | The staked program is **statistically unfalsifiable** | sd(pnl)=1.126 → n=3,975 for +5% ROI at 80% power. Standard SNIPER = 5.7/month → **58 years**. $100 = 3.3 bets | PROVEN | CRITICAL | — |
| F8 | v9's edge is **conservative by ~2.6pp**, not inflated | `1/best_odds` retains 2.61pp median residual vig vs consensus de-vig; n = 4,457 groups with ≥3 two-sided books | PROVEN | HIGH | DAYS |
| F9 | A fixed panel is feasible but its independence is **illusory** | 5 books ≥97% of 798 fixtures, but Unibet+LeoVegas = Kindred and Betsson+NordicBet = Betsson Group → ~3 real sources. Fair-p dispersion only 1.18pp median | PROVEN | MEDIUM | DAYS |
| F10 | The exchange feed **already exists**; Pinnacle covers 56% | `betfair_ex_uk` 456 rows = 3.8% of fixtures; `pinnacle` 6,693 = 56.1% | PROVEN | MEDIUM | HOURS |
| F11 | Budget instrumentation is **exactly inverted** | API-Football (non-binding, 15%) has a logged monitor + 30-min workflow; OddsAPI (binding, ~90%) has **zero** in-repo telemetry — grep for `x-requests-remaining`/`requests_remaining` over `v9/src/*.py v9/*.py` returns nothing | PROVEN | HIGH | HOURS |
| F12 | The promotion gate would **reject the current champion** | GATE needs `min_clv_n`=150 ∧ `min_mean_clv_pct`>0 ∧ logloss_impr>0 ∧ brier_impr>0 ∧ ECE≤0.05. Measured mean CLV = −0.031%; v11 controlled residual coef +0.0002, p=0.90 → **two independent checks fail** | PROVEN | CRITICAL | DAYS |
| F13 | `clv_prob` is **100% NULL** across all 1,756 `clv_records` rows | `clv_pct` n=1,447 mean +0.0036; `clv_prob` **n=0**. Also `clv_records` is entirely props (sot 1190, goals 295, cards 158) — the paper-only track | PROVEN | HIGH | DAYS |
| F14 | Near-kickoff coverage is ~2x better than the seed states, on the new table | T-1h 40.2%, T-30m 32.7%, T-10m 17.4%, post-kickoff 0.0%; median last quote 1.37h pre-KO | PROVEN | MEDIUM | DAYS |
| F15 | Retrain has no gate **and destroys its own evidence** | `retrain.py:371` `save_models()` precedes `:393` `run_backtest()`; `_print_comparison` at `:407` only prints. 5 of 7 optimizer leagues are `approved:false` with negative OOS ROI | PROVEN | HIGH | DAYS |

---

## 2. The open question, answered

**`edge_pct` is written at tip time. It is not a settlement artifact, and tiering does not use a
different `best_edge`.** Three independent proofs:

1. `v9/src/ledger.py:198` writes `edge_pct = round(edge*100, 2)` on first insert, where
   `edge = float(row.get("best_edge", 0.0))` (`:163`) — the same `best_edge` that `betting.py:319`
   computes and `:323` tiers on.
2. `ledger.py:165–179` is a **ratchet on tier, not on edge**: it overwrites `edge_pct` only when
   `_TIER_RANK[new] > _TIER_RANK[cur]`, then `continue`s (`:179`). Once a row reaches SNIPER nothing
   can touch it again. So a SNIPER row's `edge_pct` is the edge **at the instant it became SNIPER**.
3. `grep -n edge_pct v9/src/*.py v9/*.py` finds writes only in `append_tips` and `append_side_tips`.
   No settlement/grading path writes it.

**So why is `edge_pct` ~9% on rows tiered SNIPER?** Not drift, and not a bug — the thresholds are
lower than the seed assumed. All four standard SNIPER rows are explained exactly:

| league | edge | effective SNIPER need | source of need | drift |
|---|---|---|---|---|
| Championship | 8.74% | **0.07** | `best_params_standard.json`, `approved:true`, **uncapped** | New |
| Serie B | 11.64% | 0.12 | optimizer (approved) — base MARKSMAN 0.10, then `Confirmed` + edge ≥ `DRIFT_UPGRADE_EDGE` 0.10 | Confirmed |
| Bundesliga 2 | 12.67% | 0.12 | hand-set 0.20 **clamped by `LEAGUE_SNIPER_CAP=0.12`** | New |
| La Liga 2 | 13.31% | 0.12 | hand-set 0.20 clamped to 0.12 | Neutral |

The two `drift=New` rows settle it: no drift path could have produced them, and their edges sit
exactly at their league's live threshold.

**Consequence:** the 6.11% median **is** the number the decision was made on, so F1/F2/F3 are tests
of the real decision variable, not of a bookkeeping artifact. That is what makes them fatal.

**Also worth naming:** `DRIFT_UPGRADE_EDGE = 0.10` is very nearly dead code. Reaching base-MARKSMAN
requires edge ≥ the MARKSMAN floor, which in production is 0.08 — so the 0.10 guard binds only in
the narrow 0.08–0.10 band, and never for the ceiling-downgrade path. Separately,
`_base_tier:177–181` downgrades edge > `EDGE_CEILING` (0.19) to MARKSMAN *because* the backtest
showed high edges are overconfident — and `_apply_drift_adjustment:208–210` then **silently
promotes it straight back to SNIPER** whenever drift is `Confirmed`. The ceiling is reversible by
the very signal F3 shows is anti-predictive.

---

## 3. The economics, measured

### 3.1 Edge-implied vs realised ROI (live, post-cutoff 2026-08-10, flat 1u)

| cohort | n | avg odds | median edge | edge-implied ROI | realised ROI | gap | 95% CI on realised |
|---|---|---|---|---|---|---|---|
| standard SNIPER | 4 | 2.38 | 12.16% | +29.0% | +12.5% | 16.5pp | [−115, +140] |
| standard MARKSMAN | 38 | 2.24 | 6.11% | +13.7% | **−36.3%** | 49.9pp | [−68.5, −4.0] |
| standard VALUABLE | 88 | 2.12 | 3.88% | +8.2% | −20.9% | 29.1pp | [−42.4, +0.6] |
| new_format SNIPER | 55 | 2.49 | 14.72% | +36.7% | −2.1% | 38.8pp | [−33.7, +29.5] |
| new_format MARKSMAN | 87 | 2.51 | 8.64% | +21.7% | +2.5% | 19.2pp | [−22.9, +27.8] |
| new_format VALUABLE | 144 | 2.32 | 4.46% | +10.4% | −6.8% | 17.1pp | [−25.2, +11.7] |
| **ALL** | **416** | 2.34 | 5.10% | **+11.9%** | **−9.7%** | **21.6pp** | [−20.5, +1.1] |

The gap is positive in **all six** cohorts and grows with claimed edge. At n=416 the realised ROI's
upper bound (+1.1%) sits well below the edge-implied +11.9%.

### 3.2 The odds-scale-free version (the one that matters)

Realised win-rate minus the book's own implied probability. If the edge were real this column
would rise with claimed edge and roughly equal it.

| claimed-edge bucket | n | claimed | realised−implied | shortfall | ±1.96SE |
|---|---|---|---|---|---|
| 0–4% | 109 | 3.44% | −4.25% | 7.69pp | 9.24pp |
| 4–6% | 143 | 4.64% | −5.29% | 9.93pp | 7.92pp |
| 6–8% | 28 | 6.71% | +11.20% | −4.49pp | 18.95pp |
| 8–10% | 47 | 8.68% | **−14.94%** | 23.62pp | 12.83pp |
| 10–14% | 54 | 12.09% | +3.03% | 9.05pp | 12.71pp |
| 14%+ | 35 | 18.17% | −4.46% | 22.63pp | 16.20pp |
| **POOLED** | **416** | **5.11%** | **−3.85%** | **8.95pp** | **4.65pp** |

`corr(claimed edge, realised−implied) = +0.0255, perm p = 0.599`. **The pooled shortfall CI excludes
zero.** No monotonicity anywhere.

### 3.3 CLV — the finding that corroborates v11 from a different data source

`corr(claimed edge, clv_pct) = −0.2022`, n = 405, permutation p = 0.00005 (20,000 draws),
bootstrap 95% CI **[−0.290, −0.113]**, Spearman ρ = −0.1921 (p = 1e-4).

| edge bucket | n | mean CLV% |
|---|---|---|
| 0–4% | 109 | **+1.183** |
| 4–6% | 139 | **+1.344** |
| 6–8% | 28 | +0.813 |
| 8–10% | 47 | **−3.108** |
| 10–14% | 51 | −2.224 |
| 14%+ | 31 | **−2.955** |

Overall mean CLV ≈ 0 (−0.031%). So the tips *as a whole* price roughly fairly — but the **high-edge
subset**, which is exactly the subset that gets staked, systematically buys prices the market then
moves against. That is the signature of selecting stale or erroneous quotes, not of finding value.

This is an entirely independent confirmation of the v11 placebo battery: v11 measured a shadow log
and found three information-free predictors beating the model; this measures the live ledger and
finds the model's own confidence anti-correlated with market agreement. **Two different datasets,
same verdict.** `corr(clv_pct, pnl) = +0.055` — CLV itself barely predicts P&L at n=405 either,
which is what one expects when both are near-noise.

### 3.4 What v9's edge actually measures (F8) — a worked example

v9 computes `edge = p_model − 1/best_odds`. But `1/best_odds` is **not** a probability — it still
contains bookmaker margin. One real group from `book_odds_snapshots`, four books, same instant:

| bookmaker | OVER | UNDER | overround | de-vigged p(Over) |
|---|---|---|---|---|
| codere_it | 1.88 | 1.76 | 1.1001 | 0.4835 |
| coolbet | 1.92 | 1.82 | 1.0703 | 0.4866 |
| onexbet | 1.92 | 1.78 | 1.0826 | 0.4811 |
| pinnacle | 1.95 | 1.82 | 1.0623 | 0.4828 |

Best OVER price = 1.95 → raw implied p = 1/1.95 = **0.5128**. Consensus *fair* p = **0.4831**.
The best price on the board still carries **2.97pp** of margin.

Across n = 4,457 groups with ≥3 two-sided books the median residual vig is **2.61pp** (p25 3.60,
p75 1.41). So v9's reported edge **understates** the fair-line edge by ~2.6pp — it is
*conservative*, not inflated.

**This makes the picture worse, not better.** A reported 6.11% median edge is really a ~8.7%
fair-line edge, which on avg odds 2.24 implies **+19.5%** expected ROI against a realised
**−36.3%** — a ~56pp calibration failure. The problem is not that v9 measures the price wrong;
it is that `p_model` is wrong by far more than any pricing correction can cover.

### 3.5 Statistical power — why $100 cannot buy information

`sd(pnl per flat 1u bet) = 1.126` (n = 416).

| to detect a TRUE ROI of | n needed (80% power, α=0.05) |
|---|---|
| +3% | 11,043 |
| +5% | **3,975** |
| +8% | 1,552 |
| +10% | 993 |

Arrival rates measured over the 37-day post-cutoff window:
- all live tiers (paper): **337/month** → ~**1.0 year** to prove +5% ROI
- standard SNIPER (**the only real-money tier**): **5.7/month** → **58 years**

At $30/stake, **$100 = 3.3 bets**, of which ~4 would settle in 18 days. n=4 is not evidence of
anything, in either direction.

---

## 4. WHERE THE NEXT $100 GOES

**Answer: nowhere. Bank it.** This is not a rhetorical flourish — it is the arithmetic of §3.5.
The binding constraint on this system is *measurement*, and every measurement improvement worth
making is an engineering task costing $0 in cash.

Ranked, if money must move:

| Candidate | EV | Reasoning |
|---|---|---|
| **Hold the $100** | **HIGH** | The system cannot convert cash into information at this volume. 58-year readout on the staked tier (F7) |
| OddsAPI headroom — **but only after 4 hours of instrumentation** | **MEDIUM, conditional** | This is the one budget that is actually binding (~90k/100k per seed) and the **only** one with zero telemetry (F11). Spending before instrumenting repeats the API-Football error: a plan sized 6.7x above mean need. Instrument first, then decide from data |
| More API-Football credits | **NEGATIVE** | 15.0% mean utilisation of 75,000/day; max ever 56.8% (F11). Paying for ~64,000 unused calls/day already. More credits buy strictly nothing |
| Increase real-money stakes | **NEGATIVE** | F1/F2/F3 say the staked selection is anti-correlated with market agreement. Scaling stakes scales a measured −3.85pp/bet disadvantage |
| Paid xG feed / xG backfill | **NEGATIVE** | Already settled by prior work: 133k Understat shots tested with segmented + 5-fold CV → **zero AUC gain**, redundant with goals/shots. Closed. Re-buying it is paying for a proven null |
| Paid lineup/injury feed | **NEGATIVE** | Already collected — `v10/data/season_2026_27/team_news` exists via `pro_team_news.yml` (*/30). Volume is 344K/18 files, so the gap is *usage*, not *acquisition*. Buy nothing; wire up what arrives |
| Betfair direct exchange feed | **NEGATIVE (as a purchase)** | `betfair_ex_uk` is **already in the feed** (456 rows, 3.8% of fixtures) and `pinnacle` covers **56.1%** (F10). A sharp reference already exists on over half the book. This is an OddsAPI region/market **config** question worth ~4 hours, not a purchase |
| Historical odds backfill | **NEGATIVE** | Established 2026-08-19 at a cost of ~830 calls: API-Football `/odds` is pre-match only, 0 of 3 hits in every season 2019–2025, 770 consecutive empty fetches. **The quota cannot buy back the past at any price** |

---

## 5. WHERE THE NEXT 100 ENGINEERING HOURS GO

All HIGH items live in **Pro (`v10/`)**, so none of them touch frozen v9 (invariant 3).

### HIGH — 62 hours

| # | Work | Hours | Why it is the best hour available |
|---|---|---|---|
| H1 | **Register every trained model as a `ModelRecord` and run `evaluate_gate()`** | 24 | The gate is *done*: 9 named checks (`registry.py:148–175`), thresholds set (`:41–49`), `promote()` wired (`:239`), unit-tested (`tests/test_registry_gates.py`), imported by 3 pipelines. `v10/registry/` holds only `.gitkeep` — **no record has ever been written**. Every field of `ModelRecord` (`:65–109`) is computable from artifacts that already exist. Payoff is immediate and decisive: measured mean CLV −0.031% fails `clv_positive`, and v11's residual coef +0.0002 (p=0.90) fails `market_relative_logloss` — **the current champion is not promotable, and the gate would say so in words** (F12). This also permanently fixes F15: `retrain.py` saves at :371 *before* backtesting at :393 and only *prints* at :407, and `retrain.yml` never stages `backtest_metrics_history.json`, so 4 model changes since 2026-08-16 have no recorded verdict |
| H2 | **Populate `clv_prob` and build team-model CLV in probability space** | 18 | `clv_prob` is **100% NULL** across all 1,756 `clv_records` rows (F13), so every CLV number in the system lives in odds-percent space — price-level dependent and not comparable across markets. Worse, `clv_records.csv` is *entirely player props* (sot 1190, goals 295, cards 158), i.e. the permanently-paper track, so the team-model CLV the gate needs exists only as `bets_ledger.clv_pct`. `book_odds_snapshots` now makes a proper two-sided de-vig possible on 80% of groups. This is H1's key input **and** the only scale-free way to track F3 prospectively |
| H3 | **Log OddsAPI quota headers on every call** | 4 | Cheapest item on the entire list. The binding budget is uninstrumented while the non-binding one is polled every 30 minutes (F11). Unblocks every future spend decision, including the only conditional $100 in §4 |
| H4 | **Recompute the edge against a de-vigged consensus and re-run F1/F2/F3 on it** | 16 | The one genuine chance to *rescue* the edge thesis. v9's edge is conservative by 2.61pp (F8), so the current tests are run on a biased statistic. If the corrected edge shows a positive CLV correlation, the thesis survives in weakened form; if it stays at −0.20, the thesis is dead on two independent measures and the residual-blend architecture should be retired. **Either outcome is worth 16 hours.** Pre-register the test before computing it (invariant 6) |

### MEDIUM — 34 hours

| # | Work | Hours | Reasoning |
|---|---|---|---|
| M1 | **Fixed 3-source bookmaker panel as canonical `p_market` in Pro** | 20 | Feasible: 5 books cover ≥97% of 798 fixtures (unibet_se 99.1%, leovegas_se 99.1%, betsson 97.5%, nordicbet 97.5%, onexbet 97.2%). **But be honest about what it buys**: Unibet+LeoVegas are both Kindred and Betsson+NordicBet both Betsson Group, so a "5-book consensus" is ~**3 independent sources** (F9). Cross-book *fair-probability* dispersion is only 1.18pp median / 3.09pp p90 — the books agree; the spread is almost all vig. So the panel buys a **2.61pp systematic de-vig correction** (valuable, it is an accounting error) and ~1.2pp of noise reduction (marginal). Prerequisite for H4. Not an edge — a correction |
| M2 | **Near-kickoff collector coverage** | 14 | Real but half the size the seed implies (F14): T-30m coverage is already **32.7%** and T-1h **40.2%**, with **0.0%** post-kickoff waste on `book_odds_snapshots`; median last quote is 1.37h pre-KO. Free in credits (API-Football at 15%). The genuine constraint is **GitHub Actions delivery**, not quota: workflows asking ≥26 runs/day get 8–38% while ≤8/day get ~100%, and predict asks 57/day for ~15%. So **more cron frequency will not work** — this must be one batch job with an internal sampling loop, on a low-frequency schedule. Value is entirely in feeding H2 a true close |

### LOW — do not spend the hours yet

| Candidate | Reasoning |
|---|---|
| More leagues | Adds n to a metric with zero measured information (F1). Scaling a null produces a bigger null. Also constrained by the standing "ONLY OUR LEAGUES" rule |
| More markets | The seed's bright spot does not survive: side markets are +12.3% ROI but **CI [−3.1%, +27.7%] spans zero** at n=147 (< 250), tier ordering is **inverted** (VALUABLE +21.4% > SNIPER +14.2% > MARKSMAN −12.2%), corr(edge,pnl) = +0.017 (p=0.847), and mean CLV = **−2.507%**. That is noise with a negative closing line, not an edge to extend |
| Betfair/Pinnacle depth via OddsAPI region config | ~4h probe is cheap and worth doing opportunistically, but Pinnacle at 56.1% coverage already supplies a sharp reference (F10). Do it inside M1, not as its own project |
| Per-league threshold re-optimisation | 5 of 7 optimizer leagues are `approved:false` with negative OOS ROI, and the 2 approved ones set **uncapped** live thresholds (Championship 0.07). Re-fitting is retrospective tuning (invariant 6) on n=42. Fix the *plumbing* (F5) under H1's evidence discipline instead |

### NEGATIVE — actively do not do these

| Candidate | Why it is negative, not merely low |
|---|---|
| **Fix the drift-promotion floor** | Triple-blocked. (a) It targets the **better** half: drift-promoted n=21 at −13.4% vs compliant n=21 at −49.9% (F6). (b) n=21, CI ±48.5pp → INSUFFICIENT_DATA; n<250 does not justify a parameter change. (c) It is a threshold change to a **frozen** v9 (invariant 3) fitted on the very results used to evaluate it (invariant 6). It would also *look* like a fix while leaving 79% of the loss untouched — the worst possible outcome, because it would close the investigation |
| **Retrain on odds / to the market** | Makes the residual collapse to zero by construction and destroys the only quantity being measured (brief §3). It would convert F3 from a finding into an artifact |
| **Raise `LEAGUE_SNIPER_CAP` / tune thresholds to recover the loss** | Same invariant-6 violation, on n=42 |
| **xG backfill** | Proven null by prior work (133k shots, segmented + CV, zero AUC gain). Re-running it spends weeks to re-derive a negative |
| **Any props betting work** | Invariant 2, permanently. Note `clv_records` mean CLV is +0.0036 on props — do not let that tempt anyone; it is the paper track and stays there |
| **A bigger OddsAPI plan to fix prop coverage** | The calls came back *empty*, not rate-limited. Plan size is not the constraint |

---

## 6. Adversarial review of my own findings

Where I could be wrong, stated plainly:

1. **n=416 over 37 days of early season.** At n=416 I have ~85% power to detect a true correlation
   of 0.15. I can rule out a *large* edge–P&L relationship; I **cannot** rule out a true correlation
   of ~0.05. My claim is "no *usable* edge signal", not "provably exactly zero". F3 (corr −0.20,
   p=0.00005) is the robust one because its effect is larger and its sign is wrong.
2. **`edge_pct` is the ratchet-frozen promotion-moment value** (F4), not the closing edge. This is
   the right variable for F1/F2/F3 — it is the edge the decision used — but it means my tests say
   nothing about whether a *differently timed* edge would predict better. H4 is the test that
   would answer that.
3. **F1's correlation is attenuated** by heteroskedastic P&L (odds range 1.75–3+). That is exactly
   why I ran §3.2, which is odds-scale-free and gives the same answer with a tighter SE.
4. **Early-season form is thin.** `REQUIRE_FORM_DATA=0` was live for this whole window
   (`predict.yml:188`), so an unknown share of these 416 bets were tiered on **median-imputed**
   features — precisely the failure mode invariant 8 exists to prevent. This is a genuine
   alternative explanation for part of F2 and F3, and it is **testable at zero cost** because
   `no_form_data` is still written to every row. *I did not split on it.* That is the single most
   valuable follow-up measurement and it belongs in H1's evidence pass. The guard self-re-arms
   2026-09-15, so the population changes from that date — measure before it does.
5. **My 2.61pp vig figure is a median over groups with ≥3 two-sided books** — 4,457 of 12,611
   groups (35%). Thinner groups may differ, so the correction is best-estimated on the panel
   subset, which is another reason M1 precedes H4.
6. **The seed and I disagree on collection coverage** because we measured different tables. Mine is
   `book_odds_snapshots` (real books, 0% post-kickoff); the seed's figures look like
   `market_snapshots`, whose `bookmaker` column holds only two synthetic values and whose
   `book_count` is entirely null. Neither is wrong; the tables differ, and the newer one is better.

---

## 7. Open questions

1. **Split all 416 bets by `no_form_data`.** Free, and it is the strongest live alternative
   explanation for F2/F3 (§6.4). Do it before 2026-09-15.
2. **Does the de-vig-corrected edge (H4) restore any CLV correlation?** The only remaining path by
   which the edge thesis survives.
3. **Why is `betfair_ex_uk` at 3.8% and `pinnacle` at 56.1%** when both are requested? Region/market
   config, or genuine OddsAPI coverage? Decides whether a true exchange close is reachable at all.
4. **Who set `LEAGUE_SNIPER_CAP=0.12` and `MARKSMAN_THRESHOLD=0.08`, and against what evidence?**
   These override eight backtest-calibrated thresholds with one number and are the direct cause of
   the staked cohort's composition (F5). The commit message is the missing document.
5. **Is `EDGE_CEILING` reachable in production at all,** given `_apply_drift_adjustment:208–210`
   promotes ceiling-downgraded rows straight back to SNIPER on `Confirmed`?
6. **`clv_prob` was designed and never populated** (F13) — was that abandoned deliberately, or
   forgotten? It is the correct measure and the gate wants it.

---

*Read-only on v9 and wowza-v11 throughout. No source file, workflow, data partition or config was
modified; nothing was committed or pushed. This report is the only file written.*

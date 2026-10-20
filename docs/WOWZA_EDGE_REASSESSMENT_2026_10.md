# Wowza edge reassessment — October 2026

**Question:** where does evidence of value exist, and where is the system simply unable to observe the counterfactual?
No global "edge / no edge" verdict. **No production threshold, stake, routing, champion or selection rule was changed.**

Code: `src/studies/edge_reassessment.py` (Pro). Outputs: `output/edge_reassessment/` (`candidates_forward.csv`,
`ou25_breakdowns.csv`, `edge_monotonicity.csv`, `odds_bands.csv`, `tiers.csv`, `tier_ordering.csv`,
`model_vs_market.csv`, `edge_reassessment.json`). Forward tests: `registry/candidate_forward_tests.json`.

## Evidence classes (never pooled)

| class | what | coverage |
|---|---|---|
| **ALL_FIXTURE** | every fixture v9 priced, from its 689 committed `predictions.csv` snapshots (2026-08-15 → 10-20), first sight per fixture × market, settled from Pro `team_match_stats` via v9's league-scoped resolver (100% agreement with ledger results on 720 shared fixtures). Close = last committed snapshot **strictly before kickoff and within 6 h of it**, else NaN. | 3,032 settled rows: OU25 1,317 · BTTS 1,168 · O1.5 103 · O3.5 444. Valid close 94% (2,847); 147 had no observation near kickoff, 38 only one observation — those get a result but NaN CLV. |
| **LIVE** | v9 ledgers, first sight. Selection-censored: below-gate fixtures never enter. | 1,674 settled tips |
| **V91_SHADOW** | v9 `output/v91_shadow.csv` (OU25, from 10-04), an independent capture, settled by the P0 fix (v9 `9184f99b`/`63faa1a0`; 29 frozen columns hash-identical, independently re-verified: 0 changed cells vs the pre-fix commit) | 641 rows, 375 settled; close = last archived pre-kickoff price (median 319 min before kickoff, so not a certified closing line) |

## Decision matrix

| track | market | segment | historical OOS | forward / all-fixture ROI | CLV | model vs market | status | action |
|---|---|---|---|---|---|---|---|---|
| standard | OU25 | all | walk-forward at pre-match price: v9 VALUABLE −9.1% [−11.7, −6.7], log loss 0.014 worse than the price | **−13.0% [−24.0, −1.2]** n326 | +0.7 | market better; **AUC 0.476, residual coefficient negative (p 0.03)** | EDGE_NOT_RANKING_OUTCOMES | **PAPER ONLY** (evidence) — owner chose to keep League One/Two live: KEEP LIVE / LOW SIZE as an owner decision |
| standard | OU25 | League One, League Two VALUABLE | — | live −40.4% [−65.7, −17.5] n38; −43.2% [−63.9, −21.0] n29 | ~0 | — | NEGATIVE | evidence says **KILL**; owner decision: keep (stakes already minimum via rating 1–2) |
| new_format | OU25 | all | historical prices invalid (best-of-books, 11% with margin < 0) | +0.6% [−9.4, 11.0] n440 | NF CLV implausible | market better (AUC 0.580 vs 0.593) | EDGE_NOT_RANKING_OUTCOMES | RESEARCH |
| new_format | OU25 | odds > 3.00 | — | **−51.1% [−79.4, −21.1]** n47 | −1.1 | — | NEGATIVE | **KILL** candidate (needs owner approval: a live selection change) |
| new_format | OU25 | gate candidates: Finland 0.08, Ireland 0.07, Mexico 0.09, Sweden 0.10, Denmark 0.05, Japan 0.10, Austria 0.10 | fit / validation / holdout positive in v9's gate registry (Ireland 29.8 / 32.4 / 37.5%; Finland 13.7 / 6.4 / 26.6%) — after 1,682 hypotheses and on invalid NF prices | post-discovery n 0–5 each; forward n 0 | — | — | REGISTERED | **FORWARD TEST** (H-GATE-02..07, 12, 14) |
| new_format | BTTS | Argentina | H-BTTS-01 discovery +40.6% | all-fixture edge≥4% +36.4% [11.8, 62.2] n81 — **but every Argentina BTTS-Yes returns +33.2% (n89) and the model's edge is never negative there**; H-BTTS-01 post-registration 21/150, +4.6% [−28.0, 39.6] | −0.04 (single-book) | Brier model 0.240 vs market 0.216 (n8) | ACCRUING | KEEP LIVE / LOW SIZE + FORWARD TEST (frozen H-BTTS-01..04). It is a league regime, not model selection. |
| new_format | BTTS | ex-Argentina | H-BTTS-02 discovery +12.7% (CI incl. 0) | blanket Yes −2.9% (n502); edge<0 −6.7% (n398); **edge≥4% +18.8% [−7.7, 44.1] n32**; H-BTTS-02 post-reg 13/150 +36.1% | −0.7 | market sufficient (LR p 0.32) | ACCRUING | **FORWARD TEST** — the one genuine-looking selection gradient (H-BTTS-02, H-VAL-02) |
| standard | BTTS | all | gate registry: League One 0.03 (24.1 / 23.8 / 5.6%), Serie B 0.02 (14.6 / 8.1 / 21.6%), Championship, La Liga 2, League Two | **all-fixture edge≥0 −0.2% [−14.6, 14.3] n227; edge≥4% −6.5% n59** vs LIVE VALUABLE +27.0% n44 | +1.4 to +3.3 | market sufficient | CONFLICTING | **FORWARD TEST** (H-GATE-03, 08, 09, 11, 13; H-VAL-03) — likely false positive |
| new_format | O1.5 | all | **historical backtest INVALID** (99.7% of prices are exactly 1.40, a default fill) | genuine snapshot prices +3.5% [−12.7, 18.5] n78; live +8.3% n108 | −0.1 | no opposite price → FAIR_EDGE_AVAILABLE = NO | edge ranks (ρ 0.24, p 0.03) | **FORWARD TEST** |
| standard | O1.5 | all | invalid backtest | −28.3% n15 | −0.2 | — | INSUFFICIENT | INSUFFICIENT |
| both | O3.5 | all | — | small; edge does not rank | — | — | EDGE_NOT_RANKING_OUTCOMES | PAPER ONLY |
| both | tiers | OU25 | — | first-sight: NF VALUABLE +8.1% > SNIPER −8.4% > MARKSMAN −30.7%; std MARKSMAN +3.8% > VALUABLE −16.7% > SNIPER −59.5% | — | model overconfident +13 to +38 pp in MARKSMAN/SNIPER | operational tier ≠ measured confidence | RESEARCH (no cut-off search in this sample) |

## A. Main OU25

* **Does edge rank outcomes?** No, on either track (all-fixture: NF ρ(edge, P/L) +0.035 p 0.36; standard +0.008
  p 0.83; the standard decile-ROI rank correlation is **−0.70**). Label: **`EDGE_NOT_RANKING_OUTCOMES`**. Edge does
  rank the *excess hit rate* weakly (ρ ≈ +0.20) — the model picks slightly more winners at shorter prices, which
  the price already pays for. **No threshold was optimised over this signal.**
* **Windows (all positive-edge candidates):** NF last 7 +9.0% / 14 +6.3% / 30 +1.7% / since Aug 21 +1.2%; standard
  last 7 −3.1% / 14 −8.9% / 30 −8.1% / since Aug 21 −7.3%. "Since current champion (10-18)" and "post-registration
  (10-21)" have **no settled rows yet**.
* **Side:** NF OVER +12.9% (n121) vs UNDER −4.1% (n319); standard OVER −10.3%, UNDER −16.2%.
* **Odds bands (pre-registered coarse bands, BH across 26 cells):** NF 2.00–2.50 +11.2% [−3.1, 25.9]; NF >3.00
  −51.1% [−79.4, −21.1]; standard 1.80–2.00 −19.0%, 2.00–2.50 −13.4%. **No OU25 band survives FDR**; the
  ">3.00 is bad" result holds (CI excludes zero) — consistent with the earlier finding that odds > 3.0 were 6% of
  bets and 35% of the loss.
* **Entry time:** 88% of first sightings are ≥ 96 h before kickoff; the short-horizon cells are too small to read.
* **Movement state:** all-fixture first-sight drift is "New" on every row (the drift signal needs history) — the
  movement split is only meaningful on the live ledger (see the VALUABLE deep dive: Conflicted −19.5%, Neutral +5.9%).

### V91_SHADOW cross-check (independent capture, OU25, 375 settled)

| track | all positive-edge candidates | ρ(edge, P/L) all rows | by v9 tier (n, ROI) | below-gate AVOID with edge ≥ 0 |
|---|---|---|---|---|
| new_format | n 162, **+8.9% [−1.8, 20.6]**, CLV −0.1 | −0.042 (p 0.55) | VALUABLE 50 +31.8% · MARKSMAN 33 −7.3% · SNIPER 24 −18.5% | n 55, +9.8% |
| standard | n 92, **−9.7% [−27.8, 26.4]**, CLV +0.5 | −0.026 (p 0.74) | VALUABLE 43 −6.0% · MARKSMAN 7 +5.3% · SNIPER 8 −71.9% | n 34, −3.0% |

Two independent captures agree: **edge does not rank OU25 outcomes**, new-format is mildly positive with an interval
including zero, standard is negative, and the tier ladder is inverted on new-format.

## B. BTTS

* **Frozen Argentina family — progress only, definitions untouched:**

  | id | post-registration (from 10-02) | progress | status |
  |---|---|---|---|
  | H-BTTS-01 Argentina ROI | n 21, ROI +4.6% [−28.0, 39.6] (block-10 bootstrap, 10,000) | 14% of 150 | ACCRUING |
  | H-BTTS-02 ex-Argentina ROI | n 13, ROI +36.1% | 9% of 150 | ACCRUING |
  | H-BTTS-03 Argentina consensus CLV | single-book CLV −0.85% shown as context only | — | NOT EVALUABLE HERE (the registered metric needs ≥3 two-sided books) |
  | H-BTTS-04 Argentina calibration | n 8: Brier model 0.240 vs de-vigged market 0.216 | — | ACCRUING |

* **Season regime:** BTTS-Yes happened 61.4% (NF) / 57.7% (std) against a fair market price of 56.2% / 54.4%.
  Every BTTS-Yes bet was helped by that — it is why blanket Argentina BTTS-Yes returns +33%.
* **Edge ranks BTTS outcomes** (NF ρ +0.32, std +0.26, both p < 0.001) — but in NF this is mostly *between* leagues
  (Argentina has both the highest edges and the highest BTTS rate). Inside "ex-Argentina" the gradient is
  −6.7% (edge < 0) → +18.8% (edge ≥ 4%), n 32: the most interesting selection signal in the estate, and far too
  small to call.
* **The only odds cell that survives FDR:** NF BTTS 2.00–2.50, +36.9% [12.4, 62.2], q 0.027 — Argentina-dominated.
* **Ledger price integrity:** side-market upgrades overwrite the odds in place, so 44 of 268 live BTTS tips are
  booked at a longer price than at first sight; ROI at first-sight prices is **+23.4% vs +24.0%** in the ledger.
  Small, but the published price is the first one.
* **New historical candidates** (Serie B 0.02, League One 0.03, Championship, La Liga 2, League Two) are registered
  as NEW tests (H-GATE-03/08/09/11/13), never inside the Argentina family. Their historical windows end in 2024.

## C. Over 1.5

The historical O1.5 backtest is **INVALID**: 99.7% of its prices are exactly 1.40 (`src/data_loader.py:542/587`
fill paths). Its ROI is not quoted anywhere here. Re-certified from genuinely observed prices only: NF +3.5%
[−12.7, 18.5] (n78, 36 matchdays, close coverage 78%, CLV −0.06), standard −28.3% (n15). Live ledger +8.3%
(n108). Edge ranks outcomes on NF (ρ +0.24, p 0.03). No Under 1.5 price is captured → no fair edge.

## D. Model vs market (all-fixture, de-vigged two-sided prices)

| track | market | n | log loss model / market | Brier model / market | paired Brier diff [95%] | AUC model / market | residual given market (LR p) | verdict |
|---|---|---|---|---|---|---|---|---|
| NF | OU25 | 680 | 0.6785 / 0.6717 | 0.2428 / 0.2397 | +0.0031 [−0.002, 0.008] | 0.580 / 0.593 | +0.31 (0.37) | MARKET_SUFFICIENT |
| std | OU25 | 637 | 0.6987 / 0.6852 | 0.2528 / 0.2461 | **+0.0067 [0.002, 0.011]** | **0.476** / 0.572 | **−1.14 (0.03)** | MARKET_SUFFICIENT — model anti-informative |
| NF | BTTS | 591 | 0.6757 / 0.6750 | 0.2414 / 0.2412 | +0.0002 [−0.007, 0.007] | 0.538 / 0.539 | +0.76 (0.32) | MARKET_SUFFICIENT |
| std | BTTS | 577 | 0.6840 / 0.6825 | 0.2454 / 0.2447 | +0.0007 [−0.003, 0.004] | 0.518 / 0.529 | +0.54 (0.54) | MARKET_SUFFICIENT |

**"Does Wowza know something the price does not?"** — not detectably, in any market. **"Can selection still create
betting value when the market is the better forecaster?"** — a separate hypothesis; the only place the data
hints yes is BTTS outside Argentina, where the forecast is no better than the price but the edge still sorts
winners from losers (n 32).

## E. Tier system

On OU25 SNIPER does not systematically beat MARKSMAN (first-sight: NF SNIPER > MARKSMAN, std MARKSMAN > SNIPER;
live: MARKSMAN > SNIPER on NF, SNIPER > MARKSMAN on std), and the top tiers carry the worst calibration error
(+19 to +38 pp). **Operational tier ≠ measured confidence.** Not repaired by searching new cut-offs here.

## Candidate-forward framework

`registry/candidate_forward_tests.json`: 14 cells from v9's gate registry graded CANDIDATE (generated 2026-10-06,
1,682 hypotheses examined). 13 REGISTERED with production gates, candidate gate, discovery date, historical
fit/validation/holdout ROI and n, forward start 2026-10-21T00:00Z, min forward n (OU25 100, side 80), ≥10
matchdays, matchday block bootstrap, BH family H-GATE-*, pass/fail criteria. One (Argentina O1.5) is DISCOVERY —
the source gives no gate. Rows between discovery and forward start are reported as POST_DISCOVERY and never count.
**The evaluator cannot assign CONFIRMED.** Production behaviour unchanged.

---

### Strongest current evidence
1. **New-format OU25 odds > 3.00 lose** (−51.1% [−79.4, −21.1]) — consistent across live and all-fixture data.
2. **Standard OU25 has no information beyond the price, and its residual is negative** (AUC 0.476, p 0.03 against).
3. **BTTS-Yes was under-priced this season**, above all in Argentina — a regime that pays any BTTS-Yes bettor.
4. **OU25 edge does not rank outcomes** on either track.

### Most likely false positives
* Standard BTTS VALUABLE (+27% live, −0.2% / −6.5% on the all-fixture record).
* New-format OU25 gate candidates (Ireland, Finland, Mexico, Sweden): best points of their own fit curves, on
  best-of-books historical prices.
* Argentina BTTS as *model skill* (blanket Yes earns the same).
* The VALUABLE "4–8% sweet spot" on OU25 (reverses walk-forward; CLV falls as edge rises).

### Missing evidence
* Any settled forward row for the registered tests (start 2026-10-21).
* Consensus CLV (≥3 two-sided books) for H-BTTS-03.
* A valid historical single-book price series for new-format OU25.
* Under 1.5 / Under 3.5 prices (fair edge impossible on O1.5/O3.5).
* Results since the 10-18 champion.

### Instrumentation failures
1. `output/v91_shadow.csv` — 641 rows since 10-04 were never settled. **FIXED 2026-10-20** (v9 `9184f99b`): 375 settled, 45 finished rows still open (Japan/Denmark API-Football seasons hardcoded stale; Brazil/Finland/China name aliases) — owner decisions listed in v9 `docs/P0_SHADOW_SETTLEMENT_FIX.md`.
2. `src/ledger.py` overwrites tier, edge (and for side markets the odds) in place on upgrade — the ledger is not
   first-sight; 31% of OU25 tips affected.
3. `retrain_batch_id` is never populated; `model_version` is absent from snapshots before 2026-10-18 — results
   cannot be attributed to a model.
4. New-format OU25 CLV is implausible (SNIPER +23% live) — best-of-books closing prices.
5. Historical new-format OU25 prices are best-of-books (11% two-way margin < 0) — every NF OU25 backtest ROI is inflated.
6. Historical O1.5 prices are a 1.40 default fill.
7. Snapshot capture is sparse near kickoff (5% of rows without a close within 6 h).

### Markets that should receive research priority
* **BTTS outside Argentina** (the only selection gradient that survives the blanket-bet control).
* **New-format O1.5 on genuine prices** (edge ranks outcomes; needs n).
* **The new-format OU25 > 3.00 cut** (cheap, clear, needs an owner decision to act on).

### Markets that should stop consuming research time
* **Standard OU25 model-side improvements** (injuries, lineups, per-league calibration, market anchoring all tested
  this month — none beats the price; the residual is negative).
* **O3.5** (edge does not rank, small n).
* **Tier cut-off tuning on OU25** (the signal being cut does not rank outcomes).
* **Historical O1.5 backtests** (default prices).

```text
PRODUCTION_SELECTION_CHANGED = NO   TIER_THRESHOLDS_CHANGED = NO   STAKING_CHANGED = NO   BET_ENABLED_CHANGED = NO
```

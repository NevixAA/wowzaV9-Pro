# VALUABLE deep dive — 2026-10-20

**Question:** where, why and under which market conditions does a *moderate* Wowza–market disagreement have value?
**Scope:** measure → explain → validate → start a prospective shadow. Nothing in production was changed.

```text
PRODUCTION_SELECTION_CHANGED = NO
TIER_THRESHOLDS_CHANGED      = NO
STAKING_CHANGED              = NO
BET_ENABLED_CHANGED          = NO
```

Code: `src/studies/valuable/{snapshots,deep_dive,shadow,report}.py`. Data: v9 `bets_ledger.csv` + `side_bets_ledger.csv`
(live, first sight) at v9 `cb3309b0`; 689 committed v9 `predictions.csv` snapshots (2026-08-15 → 10-20); Pro
`team_match_stats`; v11 `output/` at its latest commit. Units are flat 1u, settled WIN/LOSS only, VOID excluded.

---

## 1. Three facts that change how VALUABLE must be read

**1a. The ledger is not first-sight for tier or edge.** `src/ledger.py:243-255` (OU25) and `:373-381` (side markets)
*upgrade a logged tip in place* when a later run before kickoff gives it a higher tier: tier and edge are
overwritten (OU25 keeps the first odds; side markets overwrite the odds too). A ledger "SNIPER" means "reached
SNIPER at some point"; "VALUABLE" means "never rose above VALUABLE". **31% of OU25 tips were upgraded after first
sight.** The true first-sight tier was rebuilt from the snapshot of the run that created each tip (65% of OU25 tips
matched; the rest predate 08-15 or their run's snapshot was never committed).

**1b. Tier is not an edge band.** Drift adjustments move tips between tiers (`src/betting.py:198-213`), so 163
MARKSMAN tips have an edge *below* the MARKSMAN floor. "VALUABLE" is a label, not a numeric range.

**1c. Raw edge ≠ fair edge, and in the opposite direction to the hypothesis.** OU25 production edge is
`p − 1/odds`, which *includes* the bookmaker margin. De-vigging with both sides (mean overround 1.077) makes the
**fair edge larger: +2.34 pp on average** (raw 7.25% → fair 9.58%, n 1,012). So raw 4–8% is roughly **fair 6–10%**,
not 1–4%. BTTS production uses a fixed 1.08 overround; the real two-sided overround is 1.082, so production edges
are only slightly inflated (7.29% vs fair 6.67%, n 420). O1.5/O3.5 have no opposite price: `FAIR_EDGE_AVAILABLE = NO`.

---

## 2. Reproduction of the owner audit (Oct 6–19, first sight)

| tier | N | W–L | P/L | ROI |
|---|---|---|---|---|
| VALUABLE | 146 | 88–58 | +33.04u | **+22.6%** |
| MARKSMAN | 110 | 53–57 | +3.63u | +3.3% |
| SNIPER | 88 | 37–51 | −8.16u | −9.3% |

Exact match. **The audit pools OU25 with the side markets.** Split: OU25 VALUABLE 95 tips +22.1%, side VALUABLE
51 tips +23.6%. The edge-band figures also reproduce exactly when pooled (last 14: 3–4% 52 / +4.3%, 4–6% 72 / +25.2%,
6–8% 22 / +57.4%; since Aug 26: 196 / −5.8%, 238 / +7.6%, 51 / +38.4%) — but **3–4% is OU25-only by
construction** (side-market VALUABLE starts at 4%), so "4–8 beats 3–4" partly compares BTTS against OU25.

## 3. Windows (VALUABLE, by market)

| window | OU25 N / ROI [90% CI] | BTTS N / ROI [90% CI] | pooled |
|---|---|---|---|
| full live history | 615 / −7.7% [−16.6, 0.6] | 134 / +20.9% [6.1, 35.3] | −2.5% |
| since Aug 26 | 354 / −2.0% [−13.5, 9.2] | 126 / **+23.7% [9.9, 38.5]** | +4.6% [−5.0, 13.9] |
| pre Oct 6 | 520 / −13.1% [−21.5, −4.7] | 88 / +21.6% [1.6, 42.1] | −8.4% |
| Oct 6 onward = last 14 | 95 / +22.1% [−5.4, 48.8] | 46 / +19.5% [−0.5, 36.4] | +22.6% [1.1, 41.7] |
| last 7 | 45 / +44.2% | 25 / +31.4% | +40.2% |

**OU25 VALUABLE flipped from −13% to +22% on Oct 6. BTTS VALUABLE has been ~+20% the whole time.**

## 4. Is the tier hierarchy inverted? (true first-sight tiers, OU25)

| first-sight tier | since Aug 26 | Oct 6 onward |
|---|---|---|
| VALUABLE | 571 / −2.0% | 164 / +17.1% [−3.7, 34.9] |
| MARKSMAN | 132 / −12.7% | 51 / −22.5% [−41.7, −0.9] |
| SNIPER | 64 / −14.6% | 37 / −14.8% |

The inversion **survives** on first-sight labels, so it is not caused by the in-place upgrades (upgraded tips −4.0%
vs not-upgraded −6.7%: no difference). Within the same league × market × model cell, VALUABLE beats both higher
tiers in 9 of 24 cells — **not systematic**. What is systematic is in §5.

## 5. Does edge rank outcomes? (Spearman, edge vs P/L)

| model × market | N | ρ(edge, P/L) | q (BH) |
|---|---|---|---|
| new_format OU25 | 910 | −0.013 | 0.85 |
| standard OU25 | 374 | −0.006 | 0.98 |
| new_format BTTS | 213 | **+0.293** | **<0.001** |
| standard BTTS | 55 | +0.123 | 0.77 |

**EDGE_NOT_RANKING_OUTCOMES for OU25.** A 12% OU25 edge does no better than a 4% one, so on OU25 the tier ladder
orders noise and *any* threshold just chooses which noise to bet. Calibration says why: on OU25 the model is
**overconfident in every band** (+6 to +9 pp, +16 pp above 12%) while the de-vigged market is within ±2.3 pp. The
large edges are model error, not information — the "huge residual → calibration error" explanation holds for OU25.
On BTTS the edge does rank outcomes (largely Argentina, ρ +0.33), but BTTS-Yes hit 58–83% this season against
45–55% priced by **both** model and market — part of that profit is a season regime, not skill.

## 6. Edge bands and the 1–3% question

* **Live ledger:** below 3% (OU25) / 4% (side) is **LEDGER_CENSORED** — those tips never existed. It cannot answer 1–3%.
* **Snapshot history (every fixture, recorded at the time, never bet, settled via team_match_stats; cross-check vs
  the ledger's own WIN/LOSS on 720 shared fixtures: 100% agreement):** OU25 raw 1–3% NF +3.8% [−22.5, 30.8] n107,
  std −13.8% [−31.2, 2.8] n100; fair 1–3% NF −1.9%, std −10.4%. **No edge below the floor.**
* **Within OU25 VALUABLE since Aug 26:** 3–4% −5.8% (n196), 4–6% +3.1% (n120), 6–8% +16.3% (n31) — but CLV *falls*
  as edge rises (+0.37 → −0.17 → −0.74). High ROI with no price confirmation; and the walk-forward below reverses.
* **BTTS:** 4–8% production edge NF +17.9% [2.5, 33.8] n90; std +25.0% [−3.8, 51.3] n43; fair-edge 4–8% NF +19.6%
  [4.4, 35.7], std +31.1% [2.3, 59.9].

## 7. Walk-forward (band chosen on discovery Aug 10–Sep 20 only; validation Sep 21–Oct 5; holdout Oct 6–19)

| cell | band | discovery | validation | holdout |
|---|---|---|---|---|
| OU25 NF | pre-specified 4–8 | −9.0% (n126) | n3 | +65.1% (n21) |
| OU25 std | pre-specified 4–8 | −24.4% (n58) | −60.8% (n5) | +23.0% (n22) |
| OU25 NF / std | chosen on discovery: 3–4 | −2.3% / −15.2% | n2 / −31.1% | −20.7% / +22.7% |
| BTTS NF | chosen on discovery: 4–8 | +20.9% (n50) | +2.5% (n7) | +16.5% (n33) |
| BTTS std | chosen: 4–6 | +32.9% (n28) | n0 | +22.5% (n12) |

**OU25 4–8% is a reversal, not a stable region. BTTS 4–8% is the only band that kept its sign out of sample.**

## 8. Odds × market (VALUABLE since Aug 26)

OU25: <1.80 −33.9% (n8), 1.80–2.00 +2.1% (n105), 2.00–2.50 −5.8% (n183), 2.50–3.00 +13.4% (n52), >3.00 −50.0% (n6).
BTTS: <1.80 +7.8% (n36), 1.80–2.00 +21.6% (n65), **2.00–2.50 +52.0% [15.8, 83.6] (n25)**. No OU25 odds band is
distinguishable from zero; the BTTS 2.00–2.50 cell is small.

## 9. Side, drift, regime

* **Side (OU25 VALUABLE since Aug 26):** OVER −13.3% [−26.4, −1.2] n139; UNDER +5.3% [−8.2, 19.2] n215.
* **Drift (OU25, all tiers):** VALUABLE+Conflicted −19.5% [−34.2, −4.3] n158 vs VALUABLE+Neutral +5.9% n156;
  SNIPER+Confirmed −49.3% n18. When the market moves against the tip, the tip loses — registered as H-VAL-04.
* **Model regime:** the retrain promoted a new champion on **every day through Oct 4** on both tracks, then
  rejected on Oct 5 and Oct 11, and promoted again on Oct 18. **The hot window Oct 6–19 is exactly the period one
  unchanged champion served.** One window, confounded with the calendar — registered as H-VAL-07, not concluded.
  (`retrain_batch_id` is empty on every ledger row and snapshot `model_version` only exists from Oct 18, so the
  ledger itself cannot attribute results to a model version — an instrumentation gap.)
* **Tier-gate regime:** pre-Aug-21 OU25 VALUABLE −16.0% (n206), post +−3.4% (n409); BTTS only exists post.

## 10. Concentration

* **Last 14:** top 5 league×market cells = **77.7%** of VALUABLE profit (Bundesliga 2 OU25, Argentina BTTS,
  Serie B OU25, Mexico OU25, Finland OU25). Ex top league +18.1% [−3.1, 36.4]; ex top 3 cells +12.3%
  [−10.9, 32.1]; ex top 5 cells +7.5% [−18.8, 28.8]; **ex Argentina +20.3% [−6.8, 41.4]**; ex best 5 winners +17.2%
  [−4.5, 36.4]. Positive point estimates everywhere, but every interval crosses zero once the top cell is removed.
* **Since Aug 26:** top 5 cells = **184%** of the profit (the rest lost money): ex top 5 cells −4.9% [−16.9, 6.0];
  ex Argentina +4.3% [−5.2, 13.5].

## 11. Cells (all live history, VALUABLE, N ≥ 10; empirical-Bayes shrunk toward tier×market×model; BH across cells)

**No VALUABLE cell survives multiple-testing control (best q = 0.61).**

| promising (shrunk ROI) | N | observed | shrunk | CLV |
|---|---|---|---|---|
| Championship BTTS std | 21 | +21.9% | +27.0% | +2.0 |
| Serie B BTTS std | 23 | +31.7% | +27.0% | +0.6 |
| Argentina BTTS NF | 29 | +35.8% | +25.1% | **−3.9** |
| Brazil BTTS NF | 20 | +32.3% | +22.5% | +1.0 |
| Finland OU25 NF | 26 | +40.0% | +8.9% | (NF CLV unreliable) |
| Serie B OU25 std | 27 | +29.1% | +4.3% | +1.5 |

| clearly bad | N | observed [90% CI] |
|---|---|---|
| League Two OU25 std | 29 | −43.2% [−63.9, −21.0] |
| League One OU25 std | 38 | −40.4% [−65.7, −17.5] |
| USA MLS OU25 NF (paper) | 45 | −25.4% [−47.7, −0.4] |
| Argentina OU25 NF | 46 | −32.0% [−61.1, 3.8] |
| La Liga 2 OU25 std | 44 | −20.8% [−42.8, 0.9] |
| Austrian OU25 NF | 16 | −40.9% |

Controls behave as the brief required: **Finland OU25 (+40%) vs Finland BTTS** and **Argentina BTTS (+36%) vs
Argentina OU25 (−32%)** — the same league, opposite economics; VALUABLE is not a league property.
**Bundesliga 2 OU25** is the variance control: last 14 +77.9% (n11) but since Aug +8.9% [−35.9, 52.6] (n25) with
CLV −4.3% and weak v11 movement — results-only, not equal evidence to Finland/Mexico.

## 12. v11 convergence (OU25 only — never applied to BTTS)

OUTCOME_AND_PRICE (VALUABLE ROI > 0 with N ≥ 10 and ≥3 of: VALUABLE CLV > 0, v11 CLV > 0, toward > placebo, v11
residual helps): **Finland, Japan, Mexico, Serie B, Sweden, Ligue 2**. But **no league's v11 placebo interval
excludes zero** (Finland +0.032 [−0.003, 0.065] is the closest), so the price half of that support is weak.
OUTCOME_ONLY: Bundesliga 2, Championship, Denmark, Norway. NEGATIVE: Brazil, League One, League Two, USA MLS.
PRICE_ONLY: Argentina, La Liga 2.

**Caveat:** new-format OU25 CLV in the ledger is implausible (China VALUABLE +31.8%, SNIPER +37%, "New"-drift
rows +27.6%) — the same best-of-books price problem found in the market-anchor study. New-format OU25 CLV is not
evidence either way until the closing-price source is fixed.

---

## 13. Answers

1. **Is VALUABLE genuinely outperforming recently?** Yes in the last 14 days (+22.6% [1.1, 41.7] pooled), but
   since Aug 26 it is +4.6% [−5.0, 13.9] and the recent run is concentrated (top 5 cells = 78%).
2. **After controlling for league and market?** Not systematically — VALUABLE beats both higher tiers in 9 of 24
   cells. The inversion that *is* systematic is on OU25, where edge does not rank outcomes at all.
3. **Is 1–6% best?** No. 1–3% shows no edge in snapshot history; 3–4% OU25 loses (−5.8%).
4. **Can 1–3% be tested honestly today?** Not from the ledger (censored). Historically only from committed
   snapshots (done: no edge). Prospectively: yes — the shadow started (§14).
5. **Is 4–8% a better range?** For OU25 **no** (walk-forward reversal, non-ranking edge, CLV falls with edge).
   For BTTS **yes as a candidate** (only band stable out of sample) — registered, not proven.
6. **After de-vigging?** OU25 fair edges are *larger* (+2.3 pp), not smaller; the picture does not improve. BTTS
   fair-edge 4–8% stays positive (NF +19.6%, std +31.1%).
7. **Is raw edge miscalibrated?** On OU25, yes: model overconfident by 6–9 pp in every band; the market is
   calibrated. On BTTS both model and market under-predicted Yes this season.
8. **Higher edge negatively correlated with ROI somewhere?** Finland OU25 (ρ −0.25) and the OU25 CLV gradient;
   globally OU25 is flat (ρ ≈ 0), BTTS NF positive.
9. **Promising cells:** BTTS — Championship, Serie B, Brazil, Argentina (CLV negative); OU25 — Finland, Serie B
   (after shrinkage single digits). None survives FDR.
10. **Clearly bad:** League One OU25, League Two OU25, USA MLS OU25, Argentina OU25, La Liga 2 OU25, Austria OU25.
11. **OU25 cells supported by v11:** Finland, Japan, Mexico, Serie B, Sweden, Ligue 2 — weakly (no placebo CI
    excludes zero).
12. **Results-only with poor CLV:** Bundesliga 2 OU25 (CLV −4.3), Argentina BTTS (−3.9), Championship OU25.
13. **Concentrated?** Yes — 78% of last-14 profit from 5 cells; since Aug the rest of VALUABLE lost money.
14. **Profitable ex-Argentina?** Point estimate yes (+20.3% last 14, +4.3% since Aug), intervals include zero.
15. **Did retraining create the regime change?** Unknown. The hot window coincides exactly with one unchanged
    champion after weeks of daily promotions — registered (H-VAL-07); the ledger lacks model-version fields.
16. **Price, model, league mix or variance?** Mostly variance and league mix on OU25 (non-ranking edge, falling
    CLV, reversal out of sample); on BTTS a mix of a real ranking signal and a high-BTTS season.
17. **What to shadow-test next:** the 7 registered hypotheses (§14), led by BTTS 4–8% (H-VAL-02/03) and the
    drift-Conflicted filter (H-VAL-04).

## 14. Prospective registration and shadow

* **Hypotheses:** `registry/valuable/hypotheses_v1.json` (sha256 `aab9ac95…c079`), forward start 2026-10-21,
  min N 100–300, ≥8 matchdays, pass = 90% CI lower bound > 0 and CLV ≥ 0 and BH q ≤ 0.10 across the family.
  This study can only ever assign REGISTERED / ACCRUING / REJECTED / FORWARD_SUPPORTED — never CONFIRMED.
* **Shadow:** `output/valuable_shadow/valuable_shadow.csv` via `.github/workflows/pro_valuable_shadow.yml` (daily):
  every candidate with raw edge ≥ 0 (OU25 Over/Under, BTTS Yes/No, O1.5, O3.5) at first sight, from v9's own
  committed snapshots (each row names its v9 commit), settled later. Never notified, never bet. A day's dry run on
  Oct 19–20 snapshots produced 461 first-sight candidates, 40% of OU25 and 63% of BTTS below the VALUABLE floor.

## 15. Owner summary

```text
VALUABLE_LAST14_N    = 146          VALUABLE_LAST14_ROI    = +22.6%  [90% CI +1.1, +41.7]
VALUABLE_SINCE_AUG_N = 493          VALUABLE_SINCE_AUG_ROI = +4.6%   [-5.0, +13.9]
  of which OU25      = 354 / -2.0%  BTTS = 126 / +23.7% [+9.9, +38.5]

BEST_RAW_EDGE_BAND   = OU25: none (edge does not rank outcomes) | BTTS new_format 4-8% (+17.9%, n90)
BEST_FAIR_EDGE_BAND  = OU25: none | BTTS new_format fair 4-8% (+19.6%, n87), standard (+31.1%, n34)

1_TO_3_LIVE_TESTABLE = NO  (ledger-censored; snapshot history shows no edge; prospective shadow started)
4_TO_8_CANDIDATE     = OU25 NO (walk-forward reversal) | BTTS YES (registered H-VAL-02/03)
EDGE_MONOTONIC       = VARIES_BY_CELL  (OU25 flat rho~0; BTTS new_format rho +0.29, q<0.001)

BEST_VALUABLE_LEAGUE_MARKET_CELLS  = [Championship BTTS, Serie B BTTS, Brazil BTTS, Argentina BTTS*, Finland OU25, Serie B OU25]
                                     (*negative CLV; none survives FDR)
WORST_VALUABLE_LEAGUE_MARKET_CELLS = [League Two OU25, League One OU25, USA MLS OU25, Argentina OU25, La Liga 2 OU25, Austria OU25]
V11_CONFIRMED_OU_CANDIDATES        = [] strictly (no placebo CI excludes zero); weakly: Finland, Japan, Mexico, Serie B, Sweden, Ligue 2
PROSPECTIVE_HYPOTHESES_REGISTERED  = [H-VAL-01 .. H-VAL-07]

PRODUCTION_SELECTION_CHANGED = NO
TIER_THRESHOLDS_CHANGED      = NO
STAKING_CHANGED              = NO
BET_ENABLED_CHANGED          = NO
```

**Bottom line.** VALUABLE is not one region. On **OU25** a moderate disagreement is *not* where the value is —
the model's edge does not rank outcomes, its large edges are calibration error, and the recent run reverses its
own earlier history. On **BTTS** a moderate disagreement (4–8%) is the most consistent positive result in the
estate, with a real edge-to-outcome gradient — but partly carried by a season in which both teams scored far more
often than anyone priced. That is the one to watch prospectively.

## Methodology

First sight = earliest ledger row per fixture (OU25) or fixture × market (side). True first-sight tier/edge =
the snapshot of the same run (ledger minute-stamp + 59 s, backward, ≤ 90 min). Fair edge = model probability minus
proportional two-sided de-vig of that run's prices. CIs = 90% matchday block bootstrap (2,000 draws). Shrinkage =
empirical Bayes, τ² by method of moments, per-bet variance ≈ 1. Multiplicity = Benjamini–Hochberg. Walk-forward
bands chosen on discovery only from a fixed candidate list. Below-floor candidates settled from Pro
`team_match_stats` with v9's league-scoped `team_names.resolve`; validated against the ledger's own results.
Instrumentation gaps found: ledger tier/edge overwritten in place; `retrain_batch_id` never populated;
`model_version` absent from snapshots before 2026-10-18; new-format OU25 CLV implausible.

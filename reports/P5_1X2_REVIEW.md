# P5: 1X2 model review on repaired data (2026-11-09)

Owner request 2026-11-09: "check the 1x2 model, I think it needs a look. We need to improve it, the
scores aren't good for now." Research only: nothing here is promoted, staked or changes the paper
record (`output/paper_1x2.csv` is untouched).

**Bottom line.** The served 1X2 model is badly out of date. Retrained on clean data and kept
current, it gets clearly better. A multinomial logistic model on v9's clean features is the best
model we have, and it beats the current recipe significantly on the holdout. **No model beats the
bettable market price, though, and no betting rule survives the holdout.** The 1X2 market stays
research. The one PROMISING lead is a league-wide one: draws in the Eredivisie. It is not proven.

## 1. Inputs (100% real, nothing filled)

| | |
|---|---|
| Matches | v9 `data-truth-100` at `804799a1` (the Phase 2 retrain commit). Served frame from committed data, offline, every loader correction applied, COVID seasons excluded: **58,472 matches, 32 leagues** (frame hash `80dbe5a7cfe0e5fe`) |
| Features | v9 `build_features` (point in time). The feature list is v9's Phase 2 list (43 columns), with the same `require_present` rule |
| 1X2 prices | football-data pre-match (`Avg`, else `B365`, else `PS`) and closing (`AvgC`, …) for the 17 European leagues in Pro's `fd_raw`: **24,279 of 24,622 rows joined (98.6%)**. v9 sharp-tracker h2h snapshots (opening and the last snapshot before kickoff) for the rest: **2,340 of 2,784 joined (84%)**, Jun–Nov 2026 only. Joins use v9's league-scoped resolver only; unmatched rows are counted in `extract.json`, never guessed |
| Bettable price | football-data **Bet365 pre-match**. Elsewhere the sharp tracker's opening h2h; that file does not record the bookmaker, which is flagged |
| No price | K-League 1, Romanian Superliga and Saudi Pro League have no 1X2 price in either source |

Code: `src/studies/onex2_extract_v9.py` (runs inside v9) and `src/studies/onex2_review.py`.
Outputs: `experiments/onex2_review_2026_11/`. The prediction cache is not committed; it can be
rebuilt.

## 2. Diagnosis: why the served model scores badly

| # | Cause | Evidence |
|---|---|---|
| 1 | **Stale.** `output/model_1x2.json` is the model fitted *before* the evaluation cutoff of 2026-04-27, saved and served since 2026-09-05, and never retrained (no workflow runs `train_1x2`) | Freezing a clean refit of the same recipe at 2026-04-01 costs **+0.0114 log loss** on the holdout against the same recipe refit monthly (CI [+0.0068, +0.0168]) |
| 2 | **Low coverage.** Promoted and newly seen teams have no rating | The served model rates only **1,729 of 5,576 holdout matches (31%)** |
| 3 | **Its training source is gone.** It was fitted on Pro's `season_store` plus the 88 laptop-written partitions that were quarantined on 2026-08-30 | Pro's store now holds 6,417 rows from 2026-01-22 on, and only **3 leagues** reach the 300-match minimum. `train_1x2` today cannot rebuild it |
| 4 | **The selection rule picks longshots.** The paper record tips the top 3% by model-vs-price edge | On clean data, "bet the max-EV outcome" loses **−13.6% over 3,013 holdout bets**, CI [−19.5%, −7.8%], mean odds 3.49. This is the longshot effect the `paper_1x2` docstring warned about |
| 5 | **Draw spread.** Dixon-Coles spreads draw probabilities too widely | Holdout: when it says ≥ 0.35, draws happen 0.26 of the time (n 127); when it says ≤ 0.20, they happen 0.198 (n 615). Overall calibration is fine: draw 0.254 predicted vs 0.259 observed, home 0.435 vs 0.434 |
| — | Not a cause: home advantage | The observed home-win rate is stable at 0.43–0.44 every year from 2021 to 2026. The draw rate moved from 0.268 to 0.258 |

**Separate data bug found in Pro's store (out of scope, not fixed):** 3 matches dated in the
future carry a score: Swiss Super League 2026-11-28 and 2026-12-06, and Ukraine Premier League
2027-05-08. They are probably misdated rescheduled fixtures.

## 3. Candidates (Phase 2 protocol)

The walk-forward region is 2024-07-01..2026-03-31, and the **holdout** is the owner-approved
2026-04-01..2026-11-08. Every rating model is **refit at each month start on earlier matches only**
(rolling 3-year window). Hyperparameters, the blend and the selection rules were chosen on the
walk-forward region only.

The comparison follows v9's PG-1.0 block, reused and not re-chosen: common rows, a one-sided paired
bootstrap over match dates (B = 2000), and Holm over the family. The reference is **dc180**, the
served recipe (Dixon-Coles, half-life 180 days) retrained on clean data and refit monthly.

| Candidate | What | WF Δ log loss | **Holdout** Δ log loss (95% CI) | Holm p | Verdict |
|---|---|---|---|---|---|
| mnlogit | Multinomial logistic, v9 Phase 2 features + Elo difference + league, C = 0.5 | −0.0023 | **−0.0094** [−0.0143, −0.0044] | 0.006 | **BETTER_THAN_REFERENCE** |
| elo_ord | Per-league Elo (K 25, new team at the league mean, chosen on WF) + ordered logit | −0.0013 | −0.0060 [−0.0107, −0.0008] | 0.045 | BETTER_THAN_REFERENCE |
| dc_hl | Dixon-Coles, half-life 365 (chosen on WF over 90 and 180) | −0.0013 (WF: better) | −0.0017 [−0.0038, +0.0005] | 0.153 | NOT_SHOWN_BETTER |
| blend_entry | Multinomial logistic on log p_mnlogit + log p_market_entry, fitted 2025-07..2026-03, frozen | — | −0.0306 [−0.0369, −0.0242] | 0.004 | BETTER_THAN_REFERENCE |
| market_entry | De-vigged **pre-match** price (benchmark, bettable) | −0.0209 | −0.0296 [−0.0355, −0.0235] | 0.004 | BETTER_THAN_REFERENCE |
| market_close | De-vigged **closing** price (benchmark only, not bettable) | −0.0242 | −0.0351 | — | BENCHMARK_ONLY |

The holdout has 5,030 common rows over 188 matchdays; the priced subset has 3,613 rows over 176
matchdays.

**Against the bettable market (own Holm family, holdout, 4,004 rows):**

| | Δ log loss vs market_entry | 95% CI | Holm p |
|---|---|---|---|
| mnlogit (best model) | **+0.0226 (worse)** | [+0.0165, +0.0286] | 1.0 |
| blend_entry | −0.0008 | [−0.0024, +0.0010] | 0.37 (not shown better) |

The blend's weights confirm it: the market terms carry most of the weight. The best model on clean
data is still about 0.023 log loss behind the pre-match market and 0.03 behind the close.

**Per league** (`per_league_vs_market.csv`, holdout, 53–262 priced rows per league): the
pre-match market has a lower log loss than mnlogit in almost every league. The blend edges the
market in a few leagues (Championship 1.038 vs 1.047, League One 1.006 vs 1.016, Turkey 0.985
vs 0.991, Sweden 0.997 vs 1.004, Portugal 0.961 vs 0.975), but those per-league samples are too
small to test.

**Run note (transparency):** the first run picked the blend's base model by comparing each model's
log loss on its own rows. The models cover different rows, so that ranked row sets, not models,
and it picked dc_hl. Following the declared rule ("best on WF"), it now ranks by the difference
against the reference on common rows, which picks **mnlogit**. Every candidate verdict above is
identical in both runs; only the blend's base and the selection probabilities changed. The first
run's blend gave −0.0307 and the same conclusion.

## 4. Selection rules (bets at Bet365 / opening prices)

**111 configurations** were searched on the walk-forward region:
- best EV ≥ t, t ∈ {0, .03, .06, .10};
- the same with an odds cap of {2.0, 3.0, 4.5};
- favourite-only EV ≥ t;
- draw-only EV ≥ t;
- **league-wide**: every match, one outcome, per league (the owner allows these if the data supports
  them; tested, not assumed).

Each family's best parameter, plus every league-wide cell with positive walk-forward ROI on at least
100 bets, was carried to **one** holdout check. Holm runs over the 7 carried configurations; the
owner's strict PROVEN rule needs ≥ 150 bets and Holm p < 0.05.

| Rule | WF bets / ROI | Holdout bets | Holdout ROI (95% CI) | CLV | Verdict |
|---|---|---|---|---|---|
| best EV ≥ 0 | 8,280 / −9.2% | 3,013 | −13.6% [−19.5, −7.8] | +0.9% | UNPROVEN (losing) |
| best EV ≥ 0, odds ≤ 2.0 | 1,053 / −6.1% | 416 | −5.1% [−14.6, +4.8] | +0.7% | UNPROVEN |
| favourite, EV ≥ 0 | 2,591 / −9.2% | 912 | −7.2% [−14.3, +0.2] | +0.7% | UNPROVEN |
| draw, EV ≥ 0 | 3,080 / −2.5% | 1,158 | −2.5% [−11.5, +6.3] | −0.6% | UNPROVEN |
| Belgium, every draw | 548 / +0.9% | 138 | −24.5% [−45.5, −2.9] | −2.8% | UNPROVEN |
| **Eredivisie, every draw** | 556 / +4.4% | 125 | **+34.2%** [−1.3, +70.3] | +0.1% | **PROMISING** (Holm p 0.20, n < 150) |
| Serie B, every draw | 690 / +4.4% | 149 | −4.9% [−23.0, +13.9] | −0.2% | UNPROVEN |

**Nothing is PROVEN.** Every model-driven rule loses on the walk-forward region before any cost.
The draw family loses least, which matches the market pricing draws slightly short: on priced
holdout rows the de-vigged entry price says 0.247 and draws happen 0.259 of the time. Eredivisie
draws are the one league-wide lead; they need the monthly live evidence before any stake.

## 5. Recommendation and decisions for the owner

1. **Retire `output/model_1x2.json` as the 1X2 opinion.** Replace it in the paper record with
   **mnlogit**, refit monthly on v9's clean frame, or with the **blend** where an entry price
   exists. That is the owner's call, because it changes what the paper record logs. Past rows stay;
   new rows carry the new `calc_version`.
2. **Stop ranking 1X2 by model-vs-price edge.** It is the losing slice: −13.6% on 3,013 holdout bets.
   The paper record should keep logging every fixture, as it already does, and change the
   **notified** slice from "top 3% edge" to nothing until a rule is PROVEN.
3. **Track Eredivisie draws as a LEAGUE_WIDE research cell** in the monthly re-optimisation, paper
   only.
4. **Retraining.** `train_1x2` can no longer rebuild from Pro's store (3 leagues ≥ 300 rows). The
   1X2 model should train from v9's clean frame through this study's extractor, monthly, as part of
   the monthly cycle the owner asked for.
5. **Data bug.** Fix the 3 future-dated scored matches in Pro's store (Swiss and Ukraine leagues).
6. **No 1X2 price** for K-League 1, Romanian Superliga or Saudi Pro League: those leagues cannot
   be measured against the market until prices are collected.

Reproduce:

```
python src/studies/onex2_extract_v9.py <v9 root at 804799a1> <extract dir> experiments/ou_info_inputs_2026_10/fd_raw
python -m src.studies.onex2_review --extract <extract dir> --v9 <v9 root>
```

The run was **local**: the same committed data and code, and deterministic (all seeds fixed). The
Phase 2 comparison step outgrew GitHub's 16 GB runner, so this study does not rely on it.

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

## 6. Implemented (owner approved all five steps, 2026-11-09, paper/research only)

### 6.1 Served model: multinomial logistic, refit monthly from v9's clean data

- **One door into v9.** `src/pipelines/onex2_v9_bridge.py` runs inside v9 with the network blocked.
  - `history` mode: the training extract, the same files the study used. Rerun on `804799a1`, it
    reproduces the study's frame hash `80dbe5a7cfe0e5fe`.
  - `upcoming` mode: appends the upcoming fixtures, without results, to the history and runs the
    **same** `build_features` as training. On 5 real matches blanked to "upcoming", 0 of 43 feature
    columns differed. A club no rule can place, a club with an earlier fixture still pending, and a
    fixture already in the history are not served, and each is counted.
- **Model.** `src/models/onex2_clean.py`:
  - multinomial logistic, Elo K 25 (entry at the league mean), C 0.5, 3-year window;
  - plus a blend with the de-vigged pre-kickoff price, fitted on the last 9 months' out-of-sample
    predictions;
  - it refuses to serve when v9's feature code (a fingerprint) or the scikit-learn minor version
    differs from training, and it never serves a league it was not trained on.
- **Monthly job.** `src/pipelines/train_1x2_clean.py` with
  `.github/workflows/pro_train_1x2_clean.yml`: the 2nd of each month, **off until the repository
  variable `PRO_1X2_CLEAN_ENABLED` is `true` at go-live**. It reads v9's default branch, which must
  carry the repaired loader.
- **Local proof run** (as of 2026-11-09, v9 `804799a1`):
  - 30,278 training matches, 32 leagues, 76 model inputs;
  - blend fitted on 5,345 priced out-of-sample matches;
  - last-9-months out-of-sample log loss: model 1.0266 against the entry market 1.0055 (the market
    is still better, as P5 found);
  - served on 91 real fixtures of 2026-11-05..08: every name resolved, fingerprint matched, all 91
    priced and blended.
- **Paper record.** `paper_1x2` now logs `p_*` from the clean model, `pb_*` from the blend (with
  `blend_price_class`), the model's canonical club names, `calc_version 2.0.0`, the model date and
  v9 commit.
  - With no clean model on disk it logs **nothing** and says so. It never falls back to
    `model_1x2.json`, which the manifest now marks RETIRED.
  - Past rows are untouched.

### 6.2 The top-3% picks are stopped

`notify()` still re-prices each pick and records its reasons, but it selects nothing
(`NOTIFY_RULE = None`, reason `NO_PROVEN_RULE`). Every fixture is still logged. The workflow's
`PAPER_1X2_TOP_PCT` setting is gone.

### 6.3 Eredivisie draws: a LEAGUE_WIDE research cell

`config/onex2_research_cells.json` defines the cell. Every Eredivisie row in the paper record
carries `research_cell / research_pick / research_odds`. The monthly job scores the cell on the
bettable history since 2024-07-01 and on the **live** paper bets, applying the strict PROVEN rule
to the live bets only. The first run gives: history 684 bets, **+9.4%** [−4.5%, +23.0%], CLV
+0.9%; live: ACCRUING.

### 6.4 Pro store bug: three scored fixtures dated in the future

- **Cause.** For the two Swiss rows, API-Football marked the **return** fixture FT with the first
  leg's score. Basel v Grasshoppers 0-0 and Sion v Lausanne 1-0, both played 2026-10-25, appear
  mirrored onto the return fixtures dated 2026-11-28 and 2026-12-06. The Ukrainian row
  (2027-05-08) was observed 190 days before its kickoff, so it cannot be a played match, but the
  mirror cause is **not provable** for it (its reverse fixture is not stored).
- **Corrections, beside the originals.** `output/corrections/team_match_stats_unplayed.csv` lists
  the 3 rows; the store rows are unchanged.
- **Five readers were still using them unguarded:** `train_1x2`, `btts_eval`, `tourney`,
  `xg_value` and `edge2_forward`. All now go through `result_guard`.
- **What blocks a repeat:**
  - `tests/test_result_guard_readers.py` fails on any result reader without the guard (it was
    shown to fail with `btts_eval`'s fix reverted);
  - `python -m src.pro_tests` fails when the store holds an unplayed scored row that is not in the
    corrections file;
  - the collector already skips such rows (since 2026-11-02).

### 6.5 Cost of collecting 1X2 prices for K-League 1, the Romanian Superliga and the Saudi Pro League (not started)

**Inputs (measured, not assumed):**
- Fixtures over the last 365 days of v9's clean frame: K-League 1 **225** (77 match days, at most
  6 a day), Romania **317** (161 days, at most 4), Saudi **339** (119 days, at most 7).
- 3 price snapshots per fixture: first sight, 75 minutes and 15 minutes before kickoff, the
  moments of v9's pre-kickoff capture.
- API-Football: 1 `/odds?fixture=` call per fixture per snapshot, as v9's `src/api_football.py`
  calls it.
- OddsAPI: 1 credit per `/odds` call (h2h, one region), which covers a whole league.

| Source | K-League 1 | Romanian Superliga | Saudi Pro League | Against the quota |
|---|---|---|---|---|
| **API-Football** `/odds` | 675 calls a year (1.8 a day, peak 18) | 951 (2.6 a day, peak 12) | 1,017 (2.8 a day, peak 21) | **7.2 a day on average, at most 51 on a peak day = 0.01% of 75,000 a day** |
| **OddsAPI** h2h | 19–56 credits a month (`soccer_korea_kleague1`) | **not available**: no Romanian competition in the OddsAPI catalogue (v9, verified 2026-08-22) | 30–85 credits a month (`soccer_saudi_arabia_pro_league`) | 49–141 a month, against an account already burning about 3,700 a day (v9 `oddsapi_quota_health.json`; its 100,000 monthly allowance is marked *assumed* there) |
| **football-data `ROM.csv`** | — | full history, but **closing prices only** (benchmark, never bettable) | — | no API cost |

The cross-check, at most 51 calls on a peak day, gives the same picture. The break-even is about
311 leagues of this size before API-Football odds use 1% of the daily quota.

**Recommendation.** Use API-Football `/odds` for all three: one source, negligible quota, and it
covers Romania, which OddsAPI cannot. Add football-data `ROM.csv` closing prices as the Romanian
benchmark.

**Two unknowns to check first (3 calls, not made):**
- whether API-Football's `/leagues` coverage marks `odds: true` for leagues 292, 283 and 307 (v9's
  coverage journal does not store the odds flag);
- how far back API-Football keeps pre-match odds. Until that is checked, assume **no backfill**:
  the market comparison for these leagues would start from the first collected round.

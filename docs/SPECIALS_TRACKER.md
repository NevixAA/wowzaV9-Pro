# Specials tracker (research only)

Owner brief, 2026-11-09: find matches that look like 6+ goals, a crazy score, or a 0-0, when the data supports it. For now the tracker only collects them, so we can track them and get better. **No tips, no stakes, no messages.**

## What it does

`src/specials/` produces three things:

- **`tracker.py`** (daily, `.github/workflows/pro_specials.yml`). It is OFF until `PRO_SPECIALS_ENABLED=true`.
  - **What gets logged:** one row, frozen before kickoff, for every upcoming fixture the Dixon-Coles score model can rate. It holds:
    - the full exact-score grid from 0-0 to 6-6, plus an "other" cell;
    - goal bands 0-1 / 2-3 / 4-5 / 6+, and margin bands per side;
    - the specials: 5+/6+/7+ goals, a side scoring 4+, a 4+ margin, 0-0, and 0-1 goals;
    - each value against that league's own base rate, taken from matches before the log date.
  - **Flags:** a fixture is flagged when its probability is above the league's own cutoff from the study (`cutoffs.json`).
  - **Results:** graded from v9's repaired history (90 minutes) into `specials_settled.csv`, kept beside the log.
- **`study.py`**: a walk-forward over v9's repaired history.
  - The model is refit per league each month, on earlier matches only.
  - A candidate is in the top 10% of that league's own earlier out-of-sample predictions.
  - Results are compared with a block bootstrap by match date, plus Holm across all 16 tests.
  - It re-runs on the 1st of each month and rewrites `cutoffs.json`.
- **`history.py`**: reads v9's served frame through v9's own loader, offline, in a subprocess.

## History study result (2026-11-09: 56,861 out-of-sample matches, 32 leagues, 2019-09 to 2026-10)

The 2026-11-09 history comes from v9's loader at wowza-betting `bdab0d9e`.

**The model ranks these matches better than the league base rate.** In each special, the flagged 10% hit more often than their own league base. All 16 tests are significant after Holm (p_holm 0.008):

| Special | Flagged | Hit rate | League base | Lift |
|---|---|---|---|---|
| 5+ goals | 5,506 | 19.7% | 13.1% | 1.50× |
| 6+ goals | 5,507 | 9.0% | 5.1% | 1.76× |
| 7+ goals | 5,507 | 3.2% | 1.9% | 1.68× |
| a side 4+ | 5,394 | 17.9% | 10.0% | 1.79× |
| win by 4+ | 5,264 | 10.8% | 4.8% | 2.24× |
| 0-0 | 4,567 | 9.8% | 7.9% | 1.25× |
| 0-1 goals | 4,277 | 31.9% | 26.5% | 1.20× |
| unusual exact score | 6,459 | 1.04% | 0.11% | 9.5× (only 67 events) |

**But the raw probabilities are overconfident. They are not prices.**

- For flagged 6+ goal matches the model said 15.2% on average, and 9.0% happened. For flagged 0-0 it said 16.7%, and 9.8% happened.
- On every out-of-sample match, the raw probability scores worse than the plain league base rate: negative Brier skill for 5+/6+/7+ goals, 0-0 and 0-1.
- Over the whole grid, the model overpredicts 0-0 (8.6% vs 7.5%) and underpredicts 2-1 / 2-2 / 1-1.

So the ranking is useful, but the probability levels need calibration before any comparison with a price.

**Per-league evidence is thin.** The median league has about 13 flagged 6+ goal events and about 10 flagged 0-0 events. These cells are descriptive, uncorrected and mostly INSUFFICIENT; the pooled results above are the evidence.

## Price coverage for special markets

- **Under/Over 1.5** (the 0-1 goals special): v9 captures both sides, and the tracker attaches the last quote before kickoff. In a 2026-11-05 dry run, 18 of 90 fixtures were quoted.
- **Correct score (0-0, exact scores) and Over 4.5 / 5.5 / 6.5:** not captured anywhere before kickoff, so the tracker records them as NOT_CAPTURED. Pro's API-Football live feed has a handful of "Not Started" rows: Over 4.5 for 7 fixtures, home 4+ for 191. Those are keyed by API-Football fixture id, with no proven join to Pro's fixture_key, so they are not used.
- **Adding them** would take API-Football `/odds?fixture=` calls (correct score, exact goals, Over 4.5/5.5): about 1 call per fixture per snapshot. At one pre-match snapshot per tracked fixture, that is roughly 100–200 calls a day on the 75k/day plan. This is an owner decision.

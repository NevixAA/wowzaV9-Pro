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
- **Collected since 2026-11-09 (owner approved):** `src/specials/prices.py` takes real quotes from API-Football `/odds?fixture=`.
  - **Markets:** Goals Over/Under 0.5/1.5/4.5/5.5/6.5, Exact Score, and Total - Home/Away 3.5. Exact full-time bet names only; every bookmaker; both sides as offered; our capture time and the provider's update time.
  - **Proven link:** a provider fixture is used only when it is the one fixture of its canonical league on the same UTC date whose home and away clubs v9's resolver places on the Pro fixture. Otherwise it is counted as unproven or no_pro_fixture.
  - **Budget:** `/status` is read first. A run never draws the key below 25,000 and makes at most 250 calls; each run is recorded in `special_price_runs.csv`.
- **Dry runs (2026-11-09, CI, nothing written):**
  - **Linked run (run 42598820410):** the 3-day window during the international break held 3 provider fixtures in 2 leagues; 1 was linked and its odds call returned no quote yet. Calls: 2 `/fixtures` + 1 `/odds`.
  - **Availability probe (run 42599161057):** next 7 days of our leagues, 40 fixtures in 7 leagues, 60 calls by our counter (the provider's remaining-requests header moved 73,101 → 73,076). 34 of 40 were quoted:

    | Market | Share of probed fixtures | Bookmakers |
    |---|---|---|
    | Over/Under 4.5 and 5.5 | 85% | 7 |
    | Over 6.5 | 82.5% | 3 |
    | Under 6.5 | 62.5% | 3 |
    | Under/Over 0.5 | 85% | 6 |
    | Under 1.5 | 85% | 7 |
    | Exact Score 0:0, 4:3, 3:3 | 85% | 8 |
    | Exact Score 5:2, 4:4 | 85% | 7 |
    | Home / Away Over 3.5 | 85% / 82.5% | 5 |

    121 distinct exact scores were quoted, from 9 bookmakers in all.

## Calibration (CAL-1)

`src/specials/calibration.py` uses q = sigmoid(a_k + b_k·logit(p) + δ_k,L):

- **Per outcome:** a_k and b_k are fitted on every league's earlier out-of-sample rows.
- **Per league:** each league gets its own intercept δ_k,L, shrunk toward 0 by a learned empirical-Bayes weight. That weight is reported for each league: 0.29–0.90 across outcomes, median 0.60–0.79.
- **No stand-ins:** a league with fewer than 200 earlier rows gets no calibrated probability. Nothing pooled is served to it.
- **Walk-forward:** each month is calibrated only on earlier months. The raw and calibrated probabilities are stored side by side.
- **Flags unchanged:** flagging is unaffected, because the calibration is monotone within a league.

Before and after, on 48,940 out-of-sample rows (Brier skill against the league base rate):

| Special | Actual | Raw mean | Calibrated mean | Skill raw → calibrated | Flagged: actual / raw / calibrated |
|---|---|---|---|---|---|
| 5+ goals | 13.8% | 13.9% | 13.5% | −0.0058 → +0.0083 | 19.7% / 28.3% / 20.3% |
| 6+ goals | 5.6% | 6.2% | 5.3% | −0.0070 → +0.0065 | 9.05% / 15.2% / 9.04% |
| 7+ goals | 2.0% | 2.5% | 2.0% | −0.0119 → +0.0030 | 3.2% / 7.3% / 3.7% |
| a side 4+ | 10.4% | 11.5% | 10.3% | +0.0044 → +0.0153 | 18.0% / 25.8% / 17.9% |
| win by 4+ | 5.1% | 5.6% | 5.0% | +0.0100 → +0.0160 | 10.9% / 15.2% / 10.9% |
| 0-0 | 7.4% | 8.6% | 7.8% | −0.0107 → +0.0020 | 9.7% / 16.8% / 11.0% |
| 0-1 goals | 25.3% | 27.0% | 26.1% | −0.0103 → +0.0058 | 31.6% / 44.8% / 34.7% |

After calibration the model beats every league's own base rate on every special. That is the precondition for any later comparison with the real prices above.

## Go-live

Set the repository variable `PRO_SPECIALS_ENABLED` to `true`; that is the only step. The daily job (07:53 UTC) then:
1. collects prices;
2. logs, settles and evaluates;
3. on the 1st of each month, re-runs the study and the calibration;
4. commits only `output/specials/*`.

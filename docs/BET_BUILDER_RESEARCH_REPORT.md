# Bet Builder + Multi-Match Combo Research — Phase 0–3 Report

**Date:** 2026-08-29 · **Repo:** `NevixAA/wowzaV9-Pro` · **Status:** research only, nothing staked
**V9 untouched** — no logic, threshold, model or collector in `wowza-betting` was modified.

## Bottom line

**No combination is ready for live deployment. PAPER/RESEARCH ONLY** — as §42 anticipated.

But the central premise of the brief is now **measured rather than asserted**, on 23,604 settled
fixtures:

| | P(A) | P(B) | independence says | **actually** | ratio |
|---|---|---|---|---|---|
| O2.5 ∧ BTTS | 0.5034 | 0.5316 | 0.2676 | **0.4098** | **1.53** |
| O3.5 ∧ BTTS | 0.2780 | 0.5316 | 0.1478 | **0.2440** | **1.65** |
| U2.5 ∧ BTTS_NO | 0.4966 | 0.4684 | 0.2326 | **0.3748** | **1.61** |
| O3.5 ∧ BTTS_NO | 0.2780 | 0.4684 | 0.1302 | **0.0341** | **0.26** |

Multiplying marginals is wrong by up to **+65%** and down to **−74%**. **Independence is
statistically defensible for only 8 of 63 legitimate pairs.**

---

## 1. Existing markets discovered (Phase 0 audit)

**Pro canonical store:**

| Table | Rows | Relevance |
|---|---|---|
| `team_match_stats` | **23,604** | **the foundation** — 100% scoreline coverage |
| `market_snapshots` | 105,185 | prices; includes 1X2 (see below) |
| `model_snapshots` | 93,662 | OU25/OU15/OU35/BTTS/HT_OU05/HT_OU15 — **no 1X2** |
| `settlements` | 63,484 | 62,820 OU25, 469 OVER15, 195 BTTS |
| `player_props` | 35,086 | props, PAPER-quality |
| `fixtures` | 19,643 | **only ~372 distinct** — one row per fixture *per run* |

Model markets available: `OU25`, `OU15`, `OU35`, `BTTS`, `HT_OU05`, `HT_OU15`. **1X2 is priced
but not modelled.**

## 2–3. Historical coverage and overlap

`team_match_stats` is the unlock. It carries `home_goals`/`away_goals` with **100% coverage**,
2023-01-26 → 2026-08-25, 4 seasons, 23 leagues. Every builder market is a pure function of that
one scoreline, so overlap is **total by construction** — one row settles O1.5, O2.5, O3.5, BTTS,
BTTS_NO, HOME, DRAW, AWAY, 1X, X2, 12 simultaneously and coherently.

`settlements` was rejected as the base: it is 99% OU25 and records only fixtures where a *bet
existed*, a selected subset that would bias every dependency measurement.

Base rates (n=23,604): O1.5 74.16% · O2.5 50.34% · O3.5 27.80% · BTTS 53.16% ·
HOME 44.13% · DRAW 26.14% · AWAY 29.73%.

**Half-time markets are NOT derivable** — no half-time score in the table. Declared in
`events.HT_EVENTS` with reasons rather than omitted. Do not approximate them from full-time goals.

## 4–6. Settled N, dependencies, strongest and weakest

`output/combo_dependency_matrix.csv` — 1,638 rows across 26 segments (overall + 21 leagues +
4 seasons). Every cell is a plain count; no model, no fitted parameter.

**Strongest positive** (multiplication understates): O3.5+BTTS 1.65 · U2.5+BTTS_NO 1.61 ·
O2.5+BTTS 1.53 · U2.5+DRAW 1.52 · BTTS+DRAW 1.33 · O2.5+HOME 1.19

**Strongest negative** (multiplication overstates): O3.5+BTTS_NO 0.26 · O2.5+BTTS_NO 0.40 ·
U2.5+BTTS 0.46 · O2.5+DRAW 0.48 · O1.5+BTTS_NO 0.60

**Independence defensible for 8 of 63 pairs** — and every one pairs a totals market with `1X` or
`AWAY`. Goals carry information about HOME and DRAW but are close to independent of AWAY. That is
a structural finding worth keeping.

**Stability (Q1).** `output/combo_dependency_stability.csv`. The most reliable dependencies are
the *mild* ones (O1.5+U3.5 spread 0.054, BTTS+1X 0.054), while the strongest are the most variable
— O3.5+BTTS ranges **1.44–2.17** across segments. Direction is consistent for those, magnitude is
not, so a league-specific estimate or a wide interval is required before pricing.

**20 of 63 pairs flip direction across segments.** Those are noise being read as structure and
must not price anything.

## 7. Calibration of joint probabilities

**Not yet measurable.** Calibration compares *predicted* joint probabilities against outcomes, and
predicted joints require model marginals joined to settled scorelines — which is blocked (§13).
The empirical matrix is ground truth, not a prediction, so it cannot be calibrated against itself.

## 8–11. Candidates and leg quality

**Zero candidates generated.** Phases 4–5 are not implemented, deliberately: generating builder
candidates before the joint estimator is validated would produce priced output with no basis.

Executable builder odds: **none collected anywhere in any repo.** Per §9 and §21, without real
same-game-builder prices we may test joint *calibration* but must never claim builder ROI.

## 12. Player-prop limitations

Unchanged and respected: props are PAPER-only (invariant 2). `player_props` holds 35,086 rows but
prop legs must not automatically qualify. Per §5, if player-match dependence cannot be estimated
from existing inputs it must be flagged `JOINT_PLAYER_DEPENDENCE_UNMODELED` and not priced — that
remains the position, and no player leg has been priced.

## 13. Missing data — the blockers, in order

1. **Executable same-game-builder prices.** Nothing has them. Without them there is no EV, only
   joint-probability research. Cannot be backfilled — bookmaker correlation adjustment is not
   reconstructable by multiplying singles (§21).
2. **Price↔outcome key mismatch.** `market_snapshots.fixture_key` is a hash
   (`01388458397f35b3`); `team_match_stats.fixture_id` is an API-Football id (`971352`). Joining
   on (date, home, away) matches only **19.0%** because team names differ across sources exactly
   as invariant 11 warns — `Birmingham City`/`Birmingham`, `Norwich City`/`Norwich`,
   `Lincoln City`/`Lincoln`. **This blocks all settlement, for combos and for 1X2.** The fix is
   `team_names.resolve`, not a looser match.
3. **Half-time scores**, for HT markets.
4. **Model marginals joined to outcomes**, for calibration.

## 14. Tests

`python -m src.combo.tests` — **54 deterministic checks, all passing.** No network, no store.
Covers settlement from scoreline, null-score handling, nesting, redundancy refusal, Fréchet
bounds, joint ≤ min(marginals), prohibition of independence multiplication, phi bounds,
sample-status labels, HT unavailability.

Pro's existing suite (80 checks) still passes.

**Two bugs the tests caught in my own code:**

- **Redundancy was hand-listed and incomplete.** `U15+BTTS_NO` reported ratio 2.14 with
  `p_joint == p_a` exactly (U15 *implies* BTTS_NO); `HOME+X2` reported phi **−1.0**; `U15+O25`
  and `U25+O35` reported 0.0. None are dependencies — they are definitions. Replaced with exact
  set-containment over the scoreline space, which is decidable and stays correct when a market is
  added. Excluded pairs went 20 → 28, matrix 71 → 63 legitimate pairs, degenerate rows → 0.
- **Three tests passed vacuously.** A 5×5 grid gives 25 fixtures, below `MIN_CELL_N=30`, so
  `pair_rows` returned `[]` and `all([])` passed three checks before `StopIteration` killed the
  run silently. Grid widened and a non-empty assertion added.

## 15. Files changed

New in Pro: `src/combo/events.py`, `src/combo/dependency.py`, `src/combo/tests.py`,
`docs/BET_BUILDER_RESEARCH_REPORT.md`.
New outputs: `output/combo_dependency_matrix.csv`, `output/combo_dependency_stability.csv`.
**V9: nothing. V11: nothing.**

## 16. Ready for live?

**No.** No executable builder prices, no validated joint estimator, no settlement path, no
calibration. `deployment_mode` would be `PAPER` if candidates existed, and none do.

---

# 1X2 Research (brief §43–§72)

## What exists

| | |
|---|---|
| Snapshots | 5,592 rows (`h2h_home` 2,039 · `h2h_away` 2,049 · **`h2h_draw` 1,504**) |
| Fixtures | 650 · 21 leagues |
| **Collection window** | **2026-08-17 → 2026-08-26 = 8 days** |
| Bookmakers | **1** (`v9_capture`) — a consensus, not per-book |
| Complete 3-way snapshots | 944 of 1,197 (78.9%) |
| Overround | median **1.0806**, p05 1.0521, p95 1.1018 — healthy; 1 implausible row |
| **Wowza 1X2 model** | **NONE — `model_snapshots` has no 1X2 market** |

## What this permits, and what it does not

**Possible now:** de-vig (overround is clean and plausible), and building the §49 baseline —
a score distribution from expected goals, giving coherent P(Home)/P(Draw)/P(Away).

**Not possible now, and the reasons are structural, not effort:**

- **Residuals (§52) and toward-Wowza (§53–55) cannot be computed at all.** They need
  `p_wowza_home/draw/away`, and no 1X2 model exists. This is the gating item.
- **Movement research (§47) is nearly impossible.** Median **1** complete 3-way snapshot per
  fixture, mean 1.45; only **204 of 650 fixtures (31.4%)** have ≥2. Movement needs two points.
- **Dispersion / microstructure (§56) is impossible.** One source, so `n_books` is always 1 and
  bookmaker dispersion is undefined.
- **Settlement is blocked** by the same key mismatch as §13 above.
- **~500 snapshots lack the draw price**, and a 3-way market cannot be normalised without all
  three legs. Flag `MISSING_DRAW_ODDS`.

**Sample status:** 650 fixtures = `RESEARCH` by count — but §66's own caveat applies with force.
**Eight days is one market regime.** The same limitation that governs the V11 microstructure work.

## Recommended simplest defensible start (§71)

1. **Fix the key mismatch first.** Nothing — combos or 1X2 — can be settled until prices join to
   outcomes. Highest-value single fix in either brief.
2. **Fit a Dixon-Coles score distribution** on `team_match_stats` (23,604 fixtures with goals, and
   `home_xg`/`away_xg` at ~88% coverage). Dixon-Coles over plain Poisson specifically because the
   low-score correction is where Poisson misprices draws, and §57 requires draws be treated
   separately. This single layer serves **both briefs**: it yields coherent 1X2 *and* the joint
   O1.5/O2.5/O3.5/BTTS probabilities the builder needs (§59).
3. **Validate it against the empirical matrix already built.** The model must reproduce
   O2.5∧BTTS = 0.4098 before it is trusted for anything unmeasured. That test now exists.
4. Only then: residuals, movement, candidates.

**Do not** build a home/draw/away tipster. The question is whether Wowza knows something the 1X2
market has not priced — and today we cannot ask it, because there is no Wowza 1X2 opinion.

---

# UPDATE — candidates generated, and a 1X2 model now exists

## Same-match builder candidates (Phase 4) — DONE

`output/bet_builder_candidates.csv`: **8,471 candidates over 161 upcoming fixtures.**
4,426 priced EXACTLY from a fitted score distribution; 4,045 player/card legs carrying Fréchet
bounds only. 0 rejected for monotonicity violation.

The joint engine (`src/combo/score_model.py`) fits a Dixon-Coles distribution to **v9's own**
O1.5/O2.5/O3.5/BTTS probabilities, so it inherits Wowza's opinion rather than replacing it
(§4, §60), and then reads every joint off the score matrix exactly — no independence anywhere.

**Validated against the empirical matrix before use:**

| pair | empirical (n=23,604) | score model | independence |
|---|---|---|---|
| O2.5 ∧ BTTS | 0.4098 | **0.4160** (+0.006) | 0.2662 (−0.144) |
| O3.5 ∧ BTTS | 0.2440 | **0.2536** (+0.010) | 0.1493 (−0.095) |
| U2.5 ∧ BTTS_NO | 0.3748 | **0.3837** (+0.009) | 0.2339 (−0.141) |
| U2.5 ∧ DRAW | 0.1978 | **0.1805** (−0.017) | 0.1226 (−0.075) |

Model error 0.006–0.017; independence error 0.075–0.144. **Roughly 10–20× more accurate.**

Worked example from the live output — Boca Juniors vs Lanus, **Over 3.5 + BTTS**:
joint **0.1676**, fair odds **5.97**. Independence says 0.0870 → **11.49**. Pricing by
multiplication would demand nearly double the true fair price.

`builder_odds` is empty and `executable` is False on every row: no same-game-builder prices are
collected anywhere, and §21 forbids reconstructing them from singles. EV is NULL, not invented.

## Player and card legs — bounded, not faked

Props carry a model probability and a price and **nothing linking a player's shots to the match
goal environment**. So per §5 they are priced with Fréchet bounds and flagged
`JOINT_PLAYER_DEPENDENCE_UNMODELED`. Independence is *not* used, because the true dependence is
known to be positive and independence would understate it by an unknown amount.

## 1X2 model (§43–§72, §49) — BUILT

`src/combo/dixon_coles.py`. Per-league attack/defence ratings, home advantage, and the
Dixon-Coles low-score correction, fitted by weighted MLE with a 180-day half-life. Chosen over a
multiclass classifier because it yields a score distribution, which is what makes 1X2, totals,
BTTS and the builder joints mutually consistent (§59–60) — and because §50 rules out optimising
accuracy.

**Out-of-time evaluation** — trained strictly before 2026-02-01, scored strictly after.
22 leagues, **3,498 fixtures**:

| | LogLoss | Brier | RPS |
|---|---|---|---|
| Base rate (no model) | 1.0690 | 0.6462 | 0.2274 |
| **Dixon-Coles** | **1.0427** | **0.6270** | **0.2180** |

**Beats the base rate by 0.0263 LogLoss.** Calibration: HOME 43.6% predicted vs 44.8% actual,
**DRAW 25.5% vs 25.8%**, AWAY 31.0% vs 29.4%. Draws — the outcome §57 flags as fragile — are the
best-calibrated of the three.

**Against the market (§51), the honest answer is: unknown.** Only **41 fixtures** were
comparable, which is below §66's 100-fixture `DATA_COLLECTION` floor. On those 41 the market
scored 1.0855 and the model 1.1112, so the model did not beat it — but **41 fixtures cannot
answer this question** and the number is recorded, not concluded.

Two reasons the sample collapsed, both already named as blockers: the 8-day price window, and
the fixture-key mismatch. The 86-fixture join behind those 41 used a **loose** name matcher that
strips City/Town/United — which could collide Manchester City with Manchester United. It was
adequate for a feasibility probe and is **not safe for production**; `team_names.resolve` is
required before any of this is trusted.

## Phase status

| Phase | State |
|---|---|
| 0 Audit | **done** |
| 1 Market-event schema | **done** — `src/combo/events.py` |
| 2 Historical outcome matrix | **done** — 23,604 fixtures |
| 3 Empirical dependency matrix | **done** — 1,638 rows, stability included |
| 4–5 Candidate generation | not started — blocked on builder prices |
| 6 Settlement | not started — blocked on the key mismatch |
| 7 Calibration | not started — needs 4 and 6 |
| 8 Player props | not started |
| 9 Score distribution / Monte Carlo | **recommended next**, serves both briefs |

The brief says not to skip to Phase 9. Phases 0–3 are complete and Phase 9's foundation — a
validated joint layer with ground truth to check against — is exactly what they built.

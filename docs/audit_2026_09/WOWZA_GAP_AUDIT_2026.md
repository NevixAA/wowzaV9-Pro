# WOWZA GAP AUDIT 2026 — Chief Scientist Consolidation

**Date:** 2026-09-10
**Author:** Agent 14 (Chief Scientist), consolidating twelve auditor reports, one red team, and one
weekly-learning design.
**Scope:** v9 (`NevixAA/wowza-betting`, frozen), v10 (`NevixAA/wowzaV9-Pro`), wowza-v11
(`NevixAA/wowza_v11`), root validation harness.
**Status of this document:** decision document. Where I disagree with an auditor or with the seed
brief, the contradicting number is shown. Every claim carries a confidence tag.

Numbers marked **(measured 2026-09-10)** I computed myself this run against
`v9/output/bets_ledger.csv`, `v9/output/book_odds_snapshots.csv` and the live source files, using
`v9/.venv/Scripts/python.exe` (pandas 3.0.3). Everything else is attributed.

---

## 1. Executive Summary — lead with the money

### 1.1 What the money actually is

The seed's headline (`1,159 settled, 41% win, -91.63 units`) is the **whole-file** figure and it
pools paper backtest rows with real tips. Measured 2026-09-10:

| population | n settled | win % | P&L (flat 1u) | ROI |
|---|---|---|---|---|
| entire `bets_ledger.csv` | 1,052 | 40.59% | **−92.33u** | −8.8% |
| `source=live` (actual tips) | 792 | 40.66% | **−72.75u** | −9.2% |
| `source=backtest` (never money) | 260 | — | −19.58u | — |
| live, staked tiers only (SNIPER+MARKSMAN) | 376 | 40.96% | −25.10u | −6.7% |
| live, VALUABLE (never staked) | 416 | 40.38% | −47.65u | −11.5% |
| **standard SNIPER — the only real-money tier** | **7** | 42.9% | **−0.10u** | **−1.4%** |

**PROVEN.** Two consequences that should change how this is discussed. First, 57.6% of the headline
loss sits in a tier that was never staked, so the dollar loss is far smaller than the unit loss
implies. Second — and this is the one that matters — **the track carrying real money has n=7 settled
bets.** Nothing about real-money performance has been measured. The user's statement that "it is not
currently worth it" is correct, but it is correct because the *evidence* is not worth it, not because
$3,000 has been burned.

### 1.2 What is causing the loss

Not leakage. Not the thresholds. Not the drift guard. Four independent measurements, three of them
mine this run, converge on one cause: **the model is badly miscalibrated and the decision variable
carries no information, so every bet pays the spread for nothing.**

| measurement | value | mine? |
|---|---|---|
| claimed win prob vs realised, live settled | 0.5430 vs 0.4066 = **+13.64pp, z=7.81** | yes |
| same gap, staked tiers | +16.80pp, z=6.63 | yes |
| same gap, VALUABLE (never staked) | +10.78pp, z=4.48 | yes |
| Brier: model vs the **vigged** book price | 0.2583 vs **0.2368** | yes |
| corr(edge_pct, pnl) | +0.0132 (Spearman p=0.53) | yes |
| corr(edge_pct, clv_pct), post-cutoff | **−0.2011, p=4.2e-05** | yes |
| measured OU25 single-book overround | 1.0696 | Agent 4/6 |

Read those five rows together and the mechanism is unambiguous:

1. **The book's own margin-loaded price is a better forecast than the model** on the bets the model
   itself selected (Brier 0.2368 vs 0.2583). `edge = p_model − 1/odds` therefore subtracts the
   stronger estimator from the weaker one. Agent 10 confirms externally: the closing price scores
   0.68000 logloss / 0.5848 AUC against v9's best base learner at 0.68833 / 0.5484 on the same
   n=4,450.
2. **The calibration gap is the same size in staked and never-staked tiers** (+16.80 vs +10.78, both
   z>4). A tier ladder that sorted by real edge would show the gap shrinking as the tier rises. It
   does not. This is the cleanest single proof that the ladder is decorative.
3. **Higher claimed edge buys a worse price.** corr(edge, CLV) = −0.2011 post-cutoff. The decision
   variable is not merely uninformative, it is mildly anti-informative about the one pre-outcome
   quantity we can measure.
4. **The residual arithmetic closes.** A zero-skill bettor paying the measured 6.96% overround loses
   ≈5.2–7.0%. Realised live ROI is −9.2%. The gap between them is inside one standard error at
   n=792. There is nothing left over for skill to explain, in either direction.

**PROVEN: v9 has no measured edge on either track, and the tier ladder adds no information.**

The Red Team attacked the calibration finding hardest — simulating selection-on-the-difference with
outcomes drawn from `p_over25` itself, 400 iterations — and found apparent overconfidence of +0.12pp
at edge≥0.03 and −0.45pp at edge≥0.08. Selecting on `p_model − 1/odds` is unbiased. The +13.64pp is
real, not an artefact of conditioning on the bets we took.

### 1.3 The one thing the model does know, and why it does not help

The seed's flagship result — three zero-information predictors beating the model, mean reversion at
0.995 toward-rate — **is a one-line bug.** `wowza-v11/scripts/v11_momentum_control.py:141` and `:158`
both end `return out.sort_index()["..."]`, and `pd.merge_asof` returns a fresh RangeIndex.
Reproduced from scratch this run in pandas 3.0.3:

```
left target_ts  = [03:00, 01:00, 02:00]   right = {01:00:0.1, 02:00:0.2, 03:00:0.3}
index after merge_asof: [0, 1, 2]
values as the code returns them: [0.1, 0.2, 0.3]
correct answer:                  [0.3, 0.1, 0.2]
```

Because `target_ts = snapshot_ts ± 60min` is monotone, the backward and forward calls sort into the
*identical* order and draw the same wrong row, making `future_move ≡ −prev_move` by construction.
That is where 0.995 came from. Corrected (Agent 7, replicated by the Red Team): mean reversion
collapses 0.9960 → 0.2508, exactly-zero forward moves rise from 0.2% to 85.9%, and the surviving
result is a fixture-clustered orthogonalised OLS coefficient on `p_model` of **+0.01117, CI
[+0.00362,+0.01950], P(≤0)=0.005**.

So: **the model does carry non-zero information about where the price goes next — worth 0.38pp of
price movement across its entire output range, against a 6.96% spread.** Two orders of magnitude
short of bettable. That is the most honest sentence in this audit, and it is a much better foundation
than either "the model is a placebo" (false, it was a bug) or "we have an edge" (false, it is 0.38pp).

### 1.4 What to fix first

In order, and the order is not negotiable because each step makes the next one legible:

1. **Fix the four lines in `v11_momentum_control.py`** and persist the two output files the workflow
   destroys. Without this the estate's only residual instrument is scrambled. ~2 hours.
2. **Register the current champion in `v10/registry/`** (which today holds only `.gitkeep`) and wire
   `Registry.promote()` → `evaluate_gate()` into a weekly Pro job. Expected first verdict:
   **KEEP_CHAMPION**, and say so before the first run so it reads as working rather than broken.
   ~1 day.
3. **Recalibrate on outcomes, in Pro.** Isotonic or Platt on realised results — never a market blend.
   +13.64pp is the largest measured, most fixable defect in the estate. ~2 days.
4. **Delete the pre-2026-08-10 CLV window and label the close honestly.** 63.0% of pre-cutoff CLV
   rows are physically impossible vs **0.2%** post-cutoff (measured 2026-09-10) — the instrument was
   repaired and nobody noticed. ~4 hours.
5. **Ask the account question.** Moving execution from 6.96% to Matchbook's measured 2.76% overround
   is +2.6 to +4.2pp of ROI with zero model risk. It is larger than any effect this audit measured on
   either side of zero, it costs $0, and no one has asked whether the accounts are reachable from this
   jurisdiction. That is the single highest-value hour available.

### 1.5 What to stop paying for

API-Football credits (15.0% mean utilisation of 75,000/day — Agent 12 measured this; the seed's 3% is
a partial-day artefact). Any OddsAPI plan upgrade. Any new feature for the pre-match O/U model. Any
threshold optimiser. Any props path. Detail in §5.

---

## 2. Wowza Maturity Scorecard

Graded against what a funded quantitative betting operation would have, not against a hobby project.

| dimension | grade | evidence |
|---|---|---|
| Data collection breadth | **B+** | 1.6M rows / 21 tables in Pro; 24 real bookmakers, 145,835 rows in `book_odds_snapshots` (measured); API-Football at 15% utilisation with headroom |
| Data collection timing | **D** | 32.0% of OU25 fixtures have any observation inside T-30m; median last observation T-91m (measured). Near-kickoff coverage fell −55.4pp at the 2026-08-27..30 schedule cut (Agent 5, replicated by Red Team) |
| Warehouse design | **B** | partitioned, append-only, provenance-stamped, `data_quality` as its own series; 4.86% full-row duplication (Red Team, refuting 95.7%) |
| Feature engineering correctness | **A−** | Agent 2 verified `shift(1)` before `rolling` and `expanding().shift(1)` everywhere — no lookahead. The one real leak is 21 rows (0.11%) from a league-major sort |
| Model quality | **F** | +13.64pp overconfident; Brier worse than the vigged price; 23 of 65 declared features silently dropped; the deployed meta-blend has `metrics = {}` and has never been scored |
| Decision rule quality | **F** | `edge = p_model − 1/odds` on a raw vigged quote, never de-vigged; corr(edge, pnl)=+0.013; corr(edge, CLV)=−0.201 |
| Execution / price-taking | **D** | takes the first-listed book (`v9/src/predict.py:136-139`); best price captured on 44.3–46.6% of bets; +1.99 to +2.03pp left on the table |
| CLV measurement | **C** (was F) | pre-cutoff 63.0% impossible, post-cutoff 0.2% (measured). The instrument reads clean *now*. Still-live defect: 18.3% of rows have `closing_odds == odds` exactly |
| Retrain governance | **F** | `retrain.py:371` saves before `:393` backtests; `_print_comparison` at `:407` only prints; last `backtest_metrics_history.json` entry 2026-06-17 across 4 model changes |
| Champion/challenger | **F→C** | `v10/src/models/registry.py::evaluate_gate()` is complete, thresholded and unit-tested — and `v10/registry/` holds only `.gitkeep`. The gap is registration, not statistics |
| Statistical hygiene in research | **B+** | `v10/docs/PREREGISTERED_HYPOTHESES.md` fixes statistic, cut points and falsification before data exists, and forbids recomputing quartiles on new samples. Genuinely top-decile |
| Statistical hygiene in production | **F** | two retrospective-tuning loops read live: `best_params_standard.json` ahead of config at `betting.py:154-157`; `optimize_side_market_thresholds` with no train/test split at all |
| Test infrastructure | **D** | 6 of 10 Pro test files contain zero `def test_`; no `conftest.py`/`pytest.ini`; the documented `python -m pytest tests/` collects 18 tests from 3 files and runs none of market/validation/registry/season-store/calibration/drift |
| Observability | **C** | `props_health.json`, `data_quality`, `api_usage_log.csv` all exist and are real; the binding API (OddsAPI, ~90k/100k) has **zero** telemetry — `grep x-requests-remaining` over v9 returns nothing |
| Kill discipline | **A** | six documented, honoured kills: weather, Understat xG, corners/cards, prop edge, combos, 1X2. This is the estate's strongest cultural asset and it is why this audit is possible |
| Live/in-play | **F** | live prices key on `fixture_id`, live signals on `fixture_key`; fixture intersection **0**. The scanner has never observed a market price; `MIN_LIVE_EDGE` is referenced nowhere |
| Player props | **C** (correctly parked) | invariant 2 holds; `n_prev_games` trained on 1–157 and served as constant 5; Fantasy never graded (`gw` NULL on 3,920 rows) |
| Freeze discipline | **B−** | v9 is frozen and largely respected — but `predict.yml:190-192` reverted three thresholds in workflow env, which is a strategy change wearing a config change's clothes |

**Overall: a data-collection and research organisation of genuine quality, bolted to a betting
decision rule with no measured edge and no gate between the two.**

---

## 3. Top 20 Gaps (ranked)

Ranked by *decision blocked × measurement quality × inverse cost*. Impact is in ROI points, units, or
"blocks decision X" — never in vibes.

| # | Gap | Tag | Impact | Fix cost |
|---|---|---|---|---|
| 1 | **The model is +13.64pp overconfident and its Brier is worse than the vigged price** (0.2583 vs 0.2368), identically in staked and unstaked tiers | PROVEN (mine) | The whole loss. Blocks every staking decision | 2 days (isotonic on outcomes, in Pro) |
| 2 | **`edge_pct` has no relationship to P&L (+0.013) and a negative one to CLV (−0.201, p=4e-05)** | PROVEN (mine) | The decision variable is the defect. No threshold can repair it | Cannot be "fixed" — must be replaced by a market-anchored rule in Pro |
| 3 | **v11's `_asof` merge_asof index bug** (`v11_momentum_control.py:141,158`) voids the placebo battery, momentum roles, chronological folds, and Agent 11 F5 | PROVEN (reproduced) | Voids the estate's only residual instrument | **4 lines**, then recompute downstream |
| 4 | **No retrain gate.** `retrain.py:371` save before `:393` backtest; `_print_comparison` prints only; `backtest_metrics_history.json` frozen at 2026-06-17 across 4 model changes | PROVEN | No record of whether any retrain since June helped or hurt | 1 day in Pro (gate exists) |
| 5 | **`v10/registry/` is empty.** `evaluate_gate()` is complete, thresholded (`min_clv_n=150`, `min_mean_clv_pct=0`, `max_ece=0.05`), unit-tested — and has never had a baseline to compare against | PROVEN (read) | Champion/challenger is 90% built and 0% wired | 1 day |
| 6 | **Two retrospective-tuning loops live in production.** `best_params_standard.json` read *ahead of* config at `betting.py:154-157`; `optimize_side_market_thresholds` (`backtest.py:422-486`) has no split at all | PROVEN | Championship SNIPER=0.07 vs hand-set 0.15; Bundesliga 2 sniper_th 0.04→0.19 in 7 days; `approved` flipped in 3 of 7 leagues. Invariant 6 breached in the money path | Deletion in Pro's copy — hours |
| 7 | **`over15` backtest prices are 99.99% a constant 1.40** (12,186/12,187 rows) and certified 4 live-approved markets in `league_roi_config.json` | PROVEN | A bare probability threshold sold as a market edge | Withdraw the market: 1 hour |
| 8 | **Best price is discarded at `v9/src/predict.py:136-139`** (`if ... and not ov25`) — the panel was already inside responses we paid for | PROVEN (Agent 4 +2.03pp; Red Team +1.99pp contemporaneous) | **+2pp ROI, largest positive effect in the audit.** Cannot be done in v9 — it re-tiers the live book | 1 week in Pro (paper) |
| 9 | **`predict.yml:190-192` reverts three thresholds in workflow env** (`MARKSMAN 0.14→0.08`, `VALUABLE 0.04→0.03`, `LEAGUE_SNIPER_CAP 0.12`), silently undoing a documented 2026-06-17 decision | PROVEN (read) | Every "threshold violation" statistic in this audit is measured against a floor not in force since 2026-08-21 | 1 hour to document; **do not change it mid-season** |
| 10 | **The `closing_odds == odds` defect is still live and era-invariant** (18.5% pre-cutoff, 18.3% post — measured). `update_results.py:330` takes `snapshots[-1]` with no kickoff filter | PROVEN (mine) | 18% of CLV rows are a non-observation reported as a zero | Bug fix in Pro's importer; permissible in v9 only as a read-side filter |
| 11 | **Near-kickoff capture collapsed −55.4pp** at the 2026-08-27..30 cut, in 17 of 17 leagues; the 09-07 NEAR fix did not restore it | PROVEN (Agent 5, replicated) | We do not have a closing line: median last observation T-91m; 32.0% of fixtures inside T-30m (mine) | Days in Pro; **fund as instrumentation, never as revenue** |
| 12 | **The "close" is a T-90m reference line called a closing line** | PROVEN (mine) | Every CLV number, and `evaluate_gate`'s `min_mean_clv_pct`, inherits the mislabel | Rename the column + add `panel_definition`: hours |
| 13 | **23 of 65 declared features never reach the trained model** (all 6 api_implied_*, all 3 h2h, all 5 formation) because `model.py:126` drops columns absent from the *training* frame | PROVEN | We pay ~10–14k API-Football calls/day for enrichments no team model can contain | Decision, not code: stop paying or fix the loader in Pro |
| 14 | **The deployed predictor has never been honestly scored.** `model.py:252` writes `metrics['__meta__'] = {}`; the meta is fitted on `y_test` and scored on the same rows | PROVEN | There is nothing for any gate to read | Days in Pro |
| 15 | **Live prices and live signals are in disjoint key spaces** — `fixture_id` vs `fixture_key`, intersection **0**. The scanner has never seen a market price; `MIN_LIVE_EDGE=0.12` is referenced nowhere | PROVEN (Agent 9) | The entire live programme has no entry price, no edge, no P&L | 2 lines if the resolver applies; a project if the payload lacks the fields |
| 16 | **6 of 10 Pro test files have zero collectable tests**, no pytest config; the promotion gate lives in that dead set | PROVEN (Agent 11) | A green pytest job today would be a new false-assurance surface | 4 hours (rename entry points first) |
| 17 | **`min_periods=1` guts the blind-fixture guard** — one prior match yields a "last-5", passing invariant 8's `isna()` test. Compounded by `REQUIRE_FORM_DATA=0` until 2026-09-15 | PROVEN | Unknown share of the 792 settled bets tiered on a 1-match average. **Measure the `no_form_data` split before 2026-09-15** | 2 hours to measure; fix in Pro |
| 18 | **The ledger tier is a max-ratchet over ~40 re-sightings** (`ledger.py:169`), and `odds` stays at first sighting while `edge_pct` advances | PROVEN | Any EV computed from the (edge, odds) pair mixes snapshots; single rows straddle 2–3 threshold regimes | Schema change in Pro: 1 day |
| 19 | **`n_prev_games` train/serve skew in props** — trained on 1–157 (median 28), served as constant 5 on 863/863 rows; Fantasy has never been graded (`gw` NULL on 3,920 rows) | PROVEN (Agent 8) | Props stay paper by invariant 2, but Fantasy is the sanctioned monetisation and it has no feedback loop at all | Days in Pro |
| 20 | **The push epilogue is duplicated ~30× in 3 divergent conflict policies** across 3 repos; v10/v11 variants lack `-X theirs`, so one conflict wedges all retries | PROVEN (Agent 1) | Explains v11's ~58h silence; every new workflow inherits whichever variant was nearest | 1 day: one reusable workflow |

**Deliberately excluded from this list, with the number that excludes it:**

- *Asymmetric drift guard* (`betting.py:211-213`, no edge floor on VALUABLE→MARKSMAN). Agents 7 and 12
  both measured the drift-promoted rows as the **better** half (−28.7% vs −35.8% standard; −13.4% vs
  −49.9% overall). Fixing it removes the better bets. **The seed's flagship mechanism is not a gap.**
- *Pro settlements "23x inflation"*. Full-row duplication is **4.86%**; the store holds ~25.8
  legitimate revisions per bet, and `registry.py` never reads that table (Red Team).
- *Zero-fill imputation OOD*. Structurally real, worth 0.84pp mean / 2.59pp max on `p_over25`, 0 of 77
  fixtures crossing 4pp (Agent 2's own downgrade).
- *Rolling-feature leakage*. Verified correct. 21 leaking rows = 0.11% of the frame.

---

## 4. Top 10 Improvements (ranked by expected value)

EV, not interest. Several of the highest-EV items are deletions or questions, and one is a phone call.

| # | Improvement | Expected value | Cost | Confidence |
|---|---|---|---|---|
| 1 | **Ask whether Matchbook and/or Pinnacle are reachable at size from this jurisdiction, and at what commission** | Median OU25 overround: matchbook **2.76%**, pinnacle **4.17%**, best-of-24 synthetic 5.52%, single-book 6.96%. Moving execution to Matchbook is **+2.6 to +4.2pp ROI with zero model risk** — larger than any effect this audit measured on either side of zero | **1 hour, $0** | PROVEN effect size; SPECULATIVE feasibility |
| 2 | **Fix v11's two `_asof` calls; persist `v11_placebo_table.csv` and `v11_chronological_folds.csv`** (absent from `v11_collect.yml:148-160`'s staging list) | Restores the estate's only residual instrument. Everything in §9 depends on it | **4 lines + 1 staging block, ~2h** | PROVEN (reproduced) |
| 3 | **Register the champion in `v10/registry/` and wire `Registry.promote()` into a weekly Pro job** | Turns a 90%-built gate into a working one. Expected verdict **KEEP_CHAMPION every week** — state this before the first run. Clean closes reach 764/785 OU25 fixtures (**97.3%**, measured), so `min_clv_n=150` is reachable in 1–3 weeks per segment, not 35–55 days | 1 day | PROVEN |
| 4 | **Recalibrate on realised outcomes in Pro** — isotonic or Platt, fitted on results, never on odds | Closes the +13.64pp gap, the largest measured defect. Pro already owns the fitters (`tests/test_imputers_calibration.py`). Does **not** create edge; makes every subsequent measurement honest | 2 days | PROVEN defect; PLAUSIBLE that calibration alone moves ROI |
| 5 | **Delete the pre-2026-08-10 CLV window; add a kickoff filter and drop the substring name fallback in Pro's importer** | Pre-cutoff 63.0% impossible vs post-cutoff **0.2%** (measured). Deleting one era converts a discredited metric into a usable one at zero engineering risk. Do **not** repair — the past cannot be repurchased | 4 hours | PROVEN |
| 6 | **Unwire `best_params_standard.json` from tiering in Pro's copy; delete `optimize_side_market_thresholds` from any production path** | Removes the only invariant-6 breach in a money path. Its own output moves 160–375% between consecutive monthly fits and flips `approved` in 3 of 7 leagues | Hours (a deletion) | PROVEN |
| 7 | **Build one canonical de-vigged consensus close in `v10/src/market/`, reading `book_odds_snapshots` as the change-log it is (LOCF), with `panel_definition` as a column** | Read as a panel: median 2 books, 34.9% ≥3. Read with LOCF: median 12 books, **97.3% of fixtures with a ≥3-book two-sided close** (measured). Same file, 6× the depth. This is the input to every honest CLV, residual and EV number | 3 days | PROVEN |
| 8 | **Stage best-price selection in Pro as paper** (fixed decision set, contemporaneous panel) | +1.99pp (Red Team) / +2.03pp (Agent 4) on the *same bets*. Cannot touch v9: `odds → edge_pct → tier`, so it re-tiers the whole live book and destroys the prospective validation the freeze exists to produce | 1 week | PROVEN effect; OPEN whether attainable at size |
| 9 | **Withdraw `over15` from `league_roi_config.json`'s approved markets and from `notifier.py:338`** | Its four approvals (Bundesliga2 +13.5%, Championship +7.86%, League Two +9.97%, Serie B +4.21%) were computed on a constant 1.40 price on 99.99% of rows. A certified-false positive still visible to the operator | 1 hour | PROVEN |
| 10 | **Replace `min_clv_n=150` with an anytime-valid confidence sequence** (Waudby-Smith & Ramdas, arXiv 2010.09686 — per-bet returns are bounded, so it applies directly) | Removes the peeking that manufactures cells like `new_format btts SNIPER` (n=29, +35.3%, permutation P=0.204). Promotes on "lower bound clears zero" rather than an arbitrary n | 2 days | SUPPORTED |

**Honourable mention, not top 10:** measure the `no_form_data` split on all 792 settled bets *before
2026-09-15*, when the guard self-re-arms and the population changes. It costs nothing (the flag is
already written to every row) and it is the strongest live alternative explanation for the
calibration gap. Agent 12 raised it and nobody measured it.

---

## 5. DO NOT BUILD

Generous by design. Every entry carries the number that kills it.

### 5.1 Do not tune anything

- **Any threshold re-tune** — `MARKSMAN_THRESHOLD`, `LEAGUE_SNIPER_THRESHOLDS`,
  `LEAGUE_MARKSMAN_THRESHOLDS`, `best_params_*.json`, `LEAGUE_SNIPER_CAP`. corr(edge_pct, pnl) =
  +0.0132 over 792 real bets; Spearman p=0.53. **The ordering variable does not order.** No cut point
  on a non-ordering variable can separate winners. Also invariant 6, also invariant 3.
- **Restoring `MARKSMAN_THRESHOLD` to 0.14.** The Red Team's band table: [0.14,0.20) = −3.09% (n=319),
  [0.20,1.00) = −14.58% (n=38). You would move the book into bands that are also negative.
- **Adding an edge floor to the VALUABLE→MARKSMAN drift promotion.** Triple-blocked: it targets the
  *better* half (−13.4% vs −49.9%), n=21 with CI ±48.5pp, and it is a tier rule in a frozen repo.
  Worst of all it would *look* like a fix while leaving 79% of the loss untouched, closing the
  investigation. **This was the seed's headline mechanism and it is wrong.**
- **A fifth threshold optimiser, or "better regularisation" for the two that exist.** The
  invariant-6-clean action is unwiring — a deletion.

### 5.2 Do not change v9

- **`v9/src/predict.py:136-139` to take the best price.** Largest measured effect in the audit, and
  `odds → edge_pct → tier`, so it re-tiers every bet in flight. A strategy change wearing a bug fix's
  clothes. Invariant 3. Stage in Pro.
- **`_OVER_COLS` reorder to `PC>2.5`** (Agent 10's proposal). `odds_over25` feeds
  `bookmaker_overround`, a model feature at `src/model.py:88`, and every backtest price. Not a config
  fix.
- **Loosening HT thresholds to "wake up" the HT model.** `p_ht_over05` spans [0.632,0.730] with
  sd 0.0218 across a whole board; 0 of 77 rows can cross any threshold. Loosening converts a silent
  no-op into confident noise. And `output/ht_ledger.csv` has never existed while three workflows stage
  it and two dashboard pages read it.
- **Any live-scanner constant** (`lam_total/2`, `MIN_FAIR_UNDER`, the SOT-null handling). All are real
  bugs — Agent 9 measured H1 goal share at 0.4473 on 21,026 matches, so `lam/2` overstates by 11.8% —
  and all belong in Pro's live layer.

### 5.3 Do not buy

- **API-Football credits.** 15.0% mean utilisation of 75,000/day, max ever 56.8%. Already paying for
  ~64,000 unused calls/day.
- **A larger OddsAPI plan for prop coverage.** The calls came back *empty*, not rate-limited —
  `soccer_efl_champ`, `soccer_england_league1` and `soccer_germany_bundesliga2` are parked on 23–24
  consecutive empty events. Plan size is not the constraint.
- **A larger OddsAPI plan for book depth.** The 24-book panel was already inside responses we paid for
  and discarded at `predict.py:136`. Fix the discard.
- **The Odds API $119 historical plan.** Both the price and the endpoint rest on one un-corroborated
  vendor page, the credit estimate carries a stated factor-of-two error bar, and it contradicts a
  CLAUDE.md conclusion established at ~830 calls of real cost. **One hour probing the endpoint, not a
  purchase.**
- **A direct Betfair feed.** `betfair_ex_uk` is already in the data (456 rows, 3.8% of fixtures) and
  `pinnacle` covers 56.1%. This is a ~4h region/market config probe.
- **A paid lineup/injury feed.** Already collected at `v10/data/season_2026_27/team_news` via
  `pro_team_news.yml`. The gap is usage.
- **A paid xG feed, or any xG backfill.** Proven null locally (133k Understat shots, segmented +
  5-fold CV, zero AUC gain) and externally (arXiv 2608.11505: a shots-on-target variant earns pooling
  weight 0.35 against the goals model and **0.000** against the market). FBref lost its Opta licence
  in January 2026, so the free supply is gone anyway.
- **Historical API-Football odds backfill.** Settled 2026-08-19 for ~830 calls: `/odds` is pre-match
  only, 0 of 3 in every season 2019–2025, 770 consecutive empty fetches.
  `scripts/backfill_af_odds.py` will burn 20,000 calls writing empty results. Do not run it.

### 5.4 Do not model

- **Any new football feature for the pre-match O/U model** (xG, lineups, weather, referee, travel,
  Elo, dynamic team strength, Bayesian hierarchical Dixon-Coles). Features that improve a model
  relative to other models are already in the price. Two local NULLs are instances of a general
  regularity, not bad luck.
- **A better estimator** (XGBoost, CatBoost, NN, stacking, HPO). The residual CI spans zero at
  n=12,187 and the *subtrahend* is the better forecast (market AUC 0.5848 vs model 0.5484). Lifting
  the model to 0.56 does not cross 0.5848.
- **Blending market probability into the model output** to close the calibration gap. It closes the
  +13.64pp by construction and destroys the only quantity being measured. Isotonic on **outcomes**
  achieves the same calibration without touching odds. (Brief §3.)
- **Trading Pro's Dixon-Coles on 1X2.** Best model asset in the estate and it has never met a price;
  at n=30 it is losing to uniform (logloss 1.1195 vs 1.0986). Measure the residual on
  `v10/output/paper_1x2.csv` at n≈250 first.
- **Any player-props betting path.** Invariant 2. Agent 8's de-vig correction leaves `edge_rel` median
  around −0.28. External literature now supplies the mechanism: accuracy is orthogonal to edge.

### 5.5 Do not measure again

- **De-vig refinement** (Shin, log-margin, OO-EPC, overround-weighted consensus). Worth 0.0002 Brier
  at OU25 (n=291). Power is already correct for a near-symmetric two-way market.
- **Trimmed/winsorised/mean consensus.** All within 0.00024 Brier of the median. Settled.
- **More than five bookmakers.** `{betsson, onexbet, unibet_se, matchbook}` recover 99.36% of the best
  OU25 price at 99.96% instant coverage.
- **Dispersion-as-opportunity.** n=97 per tercile, non-monotone (0.215/0.253/0.241), base rates differ
  0.68/0.41/0.63 so the differences are confounded with probability level. INSUFFICIENT_DATA.
- **Switching the CLV closing reference to a sharp book.** Pinnacle-present subsample n=77.
- **More placebo variants in v11's battery** before the `_asof` fix. Nine variants against a scrambled
  target is nine wrong answers.
- **Rolling/expanding feature leakage.** Verified correct.
- **Fitting `BLEND_K_MINS` or live game-state multipliers.** 66.7% of match-days have exactly one
  in-play frame; median elapsed span 0 minutes. The parameter is not identifiable.

### 5.6 Do not promote

- **Anything on the side-market +18.10u.** Four agents killed it independently: CI [−3.1%,+27.7%] at
  n=147, 96/147 rows one Argentine league, 88/147 one market, tier ordering *inverted* (VALUABLE
  +21.4% > SNIPER +14.2% > MARKSMAN −12.2%), halves +30.8% then −5.9%, four target leagues with zero
  settled rows, mean CLV −2.51%, and `source=live` means "not backtest", not "in-play".
- **Anything on the +35.3% `new_format btts SNIPER` cell.** Permutation P=0.204, binomial p=0.075,
  25/29 rows one league, second half +5.4%, n=29.
- **Anything on `new_format OU25 MARKSMAN +2.5%`.** Drop the top winner → +0.26%; top three → −4.11%.
  P(random 142-bet subset ≥ +0.69%) = 0.294.
- **Stake increases or new real-money leagues.** Scaling a measured −3.85pp/bet disadvantage against
  the book's own price, with a 58-year readout on the only real-money tier.
- **More leagues or more markets as growth.** Adds n to a metric with zero measured information.

### 5.7 Do not build infrastructure

- **A pytest CI job on the current `v10/tests/`** without renaming entry points first. 6 of 10 files
  have no collectable test; a green job would be a new false-assurance surface.
- **A coverage or CLV dashboard.** The consumers that exist are `evaluate_gate`'s `min_clv_n` and
  v11's residual test. A heartbeat row in Pro's `data_quality` table costs an hour and catches the
  failure that actually occurred (9 days of silent NEAR-branch outage).
- **A new capture/commit workflow cloned from an existing one.** The epilogue is duplicated ~30× in 3
  divergent variants. Extract a reusable workflow first.
- **An always-on worker sold as revenue.** Fund at $0–5/month as instrumentation only, and only after
  the gate is registered — because the gate wants `mean_clv_pct > 0`, measured CLV is −0.031%
  (n=409, mine), so a fresher close makes the gate's answer *honest* and the honest answer is REJECT.
- **An in-play capture path on the back of that worker.** Invariant 5.
- **A dedup project on Pro's settlements.** 4.86% full-row duplication; dedup at the `read()` boundary
  and move on.
- **Deleting the 137 ghost prop rows.** Flag them in `notes` — the record of the bug is the evidence
  that the fix held.

---

## 6. Missing Data — what we do not have and cannot currently get

**Cannot get at any price:**

1. **Closing prices for fixtures already played.** API-Football `/odds` is pre-match only (established
   2026-08-19 at ~830 calls). The Odds API historical endpoint is an unverified vendor claim — probe
   it, do not budget for it. Every CLV number before 2026-08-10 is therefore unrepairable and should
   be **deleted, not fixed**.
2. **An opening line.** Only 12.6% of fixtures have any observation at or before T-7d;
   `NEXT_N = 20` look-ahead fixtures per league is a structural ceiling. Widening it forward is a real
   option; reconstructing OPEN for played fixtures is not.
3. **Sub-10-minute appearances in props training.** `data_fetcher.py:514` returns `None` below 10
   minutes, so `minutes.min() == 10` across 302,456 rows and P(play) — Fantasy's dominant risk — is
   structurally unobservable. The 3,650 DNP-void ledger rows hold the labels the parquet cannot.

**Cannot get today, obtainable forward:**

4. **A true closing line.** Median last observation is T-91m; 32.0% of OU25 fixtures have any
   observation inside T-30m (measured). This is a collection-cadence problem and it degraded −55.4pp
   at the 2026-08-27..30 schedule cut. Forward-only.
5. **Book presence separated from price change.** Every archive stores consecutive-distinct changes,
   so "no row" conflates "did not move", "withdrew the market" and "was never asked". This is why the
   same file reads as median-2-books or median-12-books depending on how you group it.
6. **The bookmaker a bet was actually struck with.** Neither `bets_ledger` nor `side_bets_ledger`
   records it; `market_snapshots.bookmaker` holds two synthetic values and `book_count` is entirely
   null. No book-level attribution is possible on any historical bet.
7. **Kickoff time on struck bets.** `bets_ledger` records `match_date` (a date) with no time, so every
   time-to-kickoff band rests on a 15:00 proxy.
8. **`kickoff_utc` on the BTTS slice** of `book_odds_snapshots` — 100% null on 52,574 rows, i.e. on the
   only market with a positive P&L line. No timing question can be asked of it.
9. **A live signal joined to a live price.** `live_odds_snapshots` keys on `fixture_id`,
   `live_signals` on `fixture_key`, **intersection 0**. No live signal has ever had an entry price.
10. **Realised Fantasy points.** `gw` is NULL on all 3,920 rows of `fantasy_projection_log.csv` and no
    actuals column exists anywhere. The sanctioned monetisation of the props model has never been
    graded once.
11. **The effective threshold table for any past week.** The ledger max-ratchet + the 2026-08-21 env
    widening + the 2026-09-01 optimizer commit mean a single row can straddle three regimes.
    `best_params_standard.json` is overwritten in place with no version history. Every historical
    threshold claim in this audit, mine included, is ambiguous.
12. **An honest metric for the deployed predictor.** `model.py:252` writes
    `metrics['__meta__'] = {}` and the meta is fitted on `y_test`. There has never been anything for a
    gate to read.

---

## 7. Infrastructure Recommendation

**Principle: v9 finishes the season untouched. Every fix in this document lands in Pro.** The one
exception remains production-down. Note explicitly that the two changes most tempting to call "bug
fixes" — best-price selection at `predict.py:136-139` and the drift-guard floor at
`betting.py:211-213` — are **tier rules**, because `odds → edge_pct → tier`. Changing either
re-tiers the live book and destroys the prospective validation the freeze exists to produce.

**Do, in order:**

1. **Register the champion** (`v10/registry/`, today `.gitkeep` only) and add
   `v10/.github/workflows/pro_promote.yml` calling `Registry.promote()` → `evaluate_gate()`. No
   schedule trigger on the promote workflow — `workflow_dispatch` only — so a weekly job has no code
   path to a parameter file.
2. **Fix Pro's test collection before adding a CI job.** Rename the `main()`/`check()` entry points in
   `test_market.py`, `test_validation.py`, `test_registry_gates.py`, `test_season_store.py`,
   `test_imputers_calibration.py`, `test_drift_experiment.py` to `test_*` functions, add a
   `pyproject.toml` pytest section, *then* wire `python -m pytest tests/` into CI.
3. **Extract one reusable commit/push workflow** and migrate all 30 call sites. Standardise on v9's
   variant (`-X theirs` + `pushed=1` + explicit `exit 1`); the v10/v11 variant wedges every retry on
   one conflict, which is the signature of v11's ~58h silence.
4. **Dedup at `season_store.read()`**, not in the partitions. Append-only is deliberate.
5. **Add a heartbeat row to Pro's `data_quality` table** for near-kickoff capture and for each
   collector's branch taken. This catches the failure that actually happened — nine days of silent
   NEAR-branch outage behind a green workflow — at ~1 hour. Not a dashboard.
6. **Ban cron-string branching.** `player_props.yml:294` tests for `"0-7"` against five crons that
   contain no such string; `props_health.json` records an unset `PROPS_SCHEDULE`. Same construction as
   the NEAR outage. Branch on an explicit workflow input.
7. **Stop asking GitHub for 57 runs/day.** Workflows asking ≥26/day get 8–38%; ≤8/day get ~100%. The
   pattern that works is one firing that loops internally, which `std_odds_capture.yml:191-231`
   already does. `pro_live_odds.yml` abandoned it and should adopt it.
8. **Instrument the binding API.** `grep x-requests-remaining` over v9 returns nothing, and OddsAPI is
   at ~90k/100k. API-Football, at 15% utilisation, is polled every 30 minutes. Exactly inverted.
9. **Only then, and only as instrumentation:** an always-on near-kickoff worker in Pro on API-Football
   credits. Spec (Agent 5): 28.4 fixtures/day × 60 polls = 1,704 calls/day, taking utilisation
   15.0% → 17%; $0 (Oracle Always Free) to ~$5/month. Not on The Odds API — `markets × regions`
   billing makes the same cadence ~204,000 credits/month against a 100,000 plan.

**Do not** clone another workflow, add a coverage dashboard, or buy compute.

---

## 8. Market Data Recommendation

**`v9/output/book_odds_snapshots.csv` is the best asset in the estate and it is read by nothing in
v9.** 145,835 rows, 24 real bookmakers, 4 markets, real per-book `snapshot_ts` and
`minutes_to_kickoff`, 99.4% fixture-key join rate, **0.0% post-kickoff contamination**.

**Read it as a change-log, never as a panel.** This single decision changes the conclusion by 6×:

| grouping | book depth | ≥3 books |
|---|---|---|
| raw `(fixture, market, snapshot_ts)` groups | median 2 | 34.9% |
| LOCF forward-filled panel | median 12 (OU25) | **97.3% of fixtures** (measured 2026-09-10) |

`v9/src/predict.py:199-204` confirms the consecutive-distinct filtering that makes this so. Every
auditor who grouped raw got a pessimistic answer, and the seed's 34.9% is that answer.

**Build exactly one thing:** a canonical de-vigged consensus close series in `v10/src/market/`, with:

- LOCF per `(fixture, book, side)` to the last quote before kickoff;
- power de-vig per book (already correct in `v10/src/market/devig.py` — do not refine it);
- median across books as the consensus (do not trim, do not mean — worth 0.00024 Brier);
- **`panel_definition` and `minutes_to_kickoff` as columns**, because the three price-shopping
  estimates in this audit (+0.72pp, +1.99pp, +4.35pp) disagree by 6× purely on panel definition and
  the attribution table must carry the definition rather than pick a winner;
- **the column named `ref_price_t90`, not `closing_odds`**, until near-kickoff coverage is restored.
  Median last observation is T-91m and 32.0% of fixtures have anything inside T-30m. Calling a T-90m
  line a close is how `evaluate_gate`'s `min_mean_clv_pct` gets a wrong answer with a straight face.

**The largest market-data finding is not a data problem at all.** Measured median OU25 overround per
book: matchbook 2.76%, pinnacle 4.17%, onexbet 6.11%, williamhill 7.61%, pmu_fr 13.71%; best-of-24
synthetic 5.52%; what v9 actually takes, 6.96%. **Margin reduction is worth +2.6 to +4.2pp of ROI
with zero model risk**, which exceeds every other measured effect in this audit in absolute value.
It is blocked entirely on an unasked business question: are those accounts reachable, at size, from
this jurisdiction, at what commission? Ask it this week.

**Leader/follower, sharpness, staleness weighting:** collect, do not interpret. Pinnacle leads the
consensus (+0.120 sign-agreement differential, z≈2.5) and covers 56.1% of fixtures — but at a median
1,518 minutes to kickoff, with only 3.79% inside T-60m. **The sharp anchor exists; the sharp close
does not.** Five books are frozen ~75% of the times consensus moves, and the entire achievable prize
from staleness weighting is ~0.0008 Brier. Not now.

---

## 9. Scientific Validation Framework

The estate already has the hard parts. What it lacks is a wire between them.

**Keep, unchanged — these are genuinely top-decile:**

- `v10/docs/PREREGISTERED_HYPOTHESES.md`. Fixes statistic, cut points, sample definition, decision
  threshold and falsification condition before data exists, and *mandates that cut points be literals
  read from the file, never recomputed on the new sample*. It records its own wrong reading and labels
  its stratification post-hoc. Nothing in this audit improves on it.
- `v9/src/provenance.py` — `generated_at` + `git_sha` + `model_sha` on every prediction row.
- Six documented, honoured kills. This is why the audit was possible at all.

**Adopt:**

1. **The residual test is the only model metric that counts.** Does the model improve logloss/Brier
   *after* the de-vigged consensus price is known? Not AUC. `v10/output/paper_1x2.csv` already carries
   the full schema (`p_*`, `o_*`, `m_*`, `c_*`, `result`) and answers the 1X2 version at ~250 settled
   rows for free.
2. **Placebo battery, post-`_asof`-fix, with paired fixture-clustered bootstrap of the *difference*.**
   Not of each arm. Agent 7's correction shows why: the "fixed anchor" placebo is +0.7667 correlated
   with the treatment, because `sd(p_model)=0.0492 < sd(p_market)=0.0765` makes the residual
   ≈ `const − p_market` ≈ the placebo. Unpaired comparison of two 0.77-correlated series is not a
   test. Report the floor (arXiv 2606.09473).
3. **Anytime-valid confidence sequences** (arXiv 2010.09686) in place of `min_clv_n=150`. Per-bet
   returns are bounded, so the betting-martingale construction applies directly. Promote when the
   lower bound clears zero — which removes the peeking that manufactured the n=29 BTTS cell.
4. **`evaluate_gate()` as the only promotion authority**, with `min_rows_holdout=1000`,
   `min_logloss_improvement>0` **vs market-only**, `min_brier_improvement>0`, `max_ece≤0.05`,
   `min_clv_n=150`, `min_mean_clv_pct>0`. Two of those nine checks fail today on measured data
   (mean CLV −0.031% at n=409, mine; corrected residual economically ~0.38pp). **The gate is correct
   and the honest verdict is REJECT.** Publish that expectation before the first run.
5. **Sample discipline as a hard rule, not a preference.** n<50 is not evidence. n<250 does not
   justify a parameter change. A CI spanning zero means "we do not know". Every promoted cell in this
   estate's history — +35.3% BTTS SNIPER, +18.10u side markets, +2.5% NF MARKSMAN — violates this and
   every one of them died under permutation, chronological split, or leave-out-top-winner.
6. **Never fit a cut point on the sample that evaluates it** (invariant 6) and **never train on odds**
   (brief §3). Both are currently breached: the first in production at `betting.py:154-157`, the
   second partly by construction, since `odds_over25` is sourced from the *closing average*
   (`data_loader.py:49`) and `bookmaker_overround` is a model feature at `model.py:88`. The published
   objective is the opposite — explicitly **decorrelate** from the market (arXiv 2010.12508).
7. **Two-track firewall (invariant 1) applies to validation too.** The Red Team showed the
   standard/new-format split reverses conclusions: standard median `var_model/var_edge` = 0.159
   (edge is a longshot selector), new-format = 1.1246 (the model contributes *more* variance than the
   edge). 79% of live bets are new-format. Never pool them in a headline again — including in the
   −92.33u figure.

---

## 10. 30 / 60 / 90 Day Plan

All work in `v10/` (Pro) unless stated. v9 continues untouched to season end.

### Days 0–30 — make the instruments honest

| # | Task | Repo | Owner artefact | Done when |
|---|---|---|---|---|
| 1 | Ask the Matchbook/Pinnacle account question | — | one answer | answered YES/NO with commission |
| 2 | Fix `_asof` at `v11_momentum_control.py:141,158`; add `v11_placebo_table.csv` and `v11_chronological_folds.csv` to `v11_collect.yml` staging | v11 | corrected placebo table | committed table shows corrected toward-rates |
| 3 | Register the champion in `v10/registry/`; add `pro_promote.yml` (`workflow_dispatch` only) | v10 | first `ModelRecord` | `evaluate_gate()` returns a verdict with reasons |
| 4 | Measure the `no_form_data` split on all 792 settled bets — **before 2026-09-15** | read-only | one number | measured |
| 5 | Delete pre-2026-08-10 CLV rows from Pro's derived views; add kickoff filter + drop substring name fallback in Pro's importer | v10 | `clv_enriched` v2 | 0 rows with `abs(clv)>25` |
| 6 | Build `ref_price_t90` de-vigged consensus close from `book_odds_snapshots` (LOCF, power de-vig, `panel_definition` column) | v10 | `src/market/close.py` | ≥3-book two-sided close on ≥95% of OU25 fixtures |
| 7 | Withdraw `over15` from `league_roi_config.json` approvals and `notifier.py:338` | v10 | config | market absent |
| 8 | Rename 6 test entry points; add pytest config; wire one CI job | v10 | `pro_tests.yml` | all 10 files collect |
| 9 | Extract the reusable commit/push workflow; migrate v10 + v11 | v10/v11 | `.github/workflows/_push.yml` | 0 divergent variants |

### Days 31–60 — make the model honest

| # | Task | Done when |
|---|---|---|
| 10 | Isotonic/Platt recalibration on realised outcomes, in Pro, firewalled per track | ECE ≤0.05 on a chronological holdout, both tracks |
| 11 | Unwire `best_params_standard.json` from tiering; delete `optimize_side_market_thresholds` from any production path in Pro's copy | grep finds no read from a fitted-threshold file in the decision path |
| 12 | Honest metrics for the deployed predictor: fix the meta fitted-on-`y_test` leak; populate `metrics['__meta__']` | `metrics_model_*.json` carries a real OOS number |
| 13 | Residual test vs `ref_price_t90` on both tracks; anytime-valid CI | signed verdict with a lower bound |
| 14 | Best-price selection staged in Pro as paper (fixed decision set, contemporaneous panel) | paper series accruing, +2pp reproduced forward |
| 15 | Near-kickoff worker as instrumentation, $0–5/month, API-Football only | T-30m per-fixture coverage back above 60% |
| 16 | `fixture_key` on `live_odds_snapshots` (2 lines if the resolver applies) | live signal↔price intersection > 0 |
| 17 | 1X2 residual test on `paper_1x2.csv` at n≥250 | Dixon-Coles vs de-vigged price, verdict recorded |

### Days 61–90 — decide

| # | Task | Decision it produces |
|---|---|---|
| 18 | First four weekly gate runs complete, all expected KEEP_CHAMPION | Is the weekly loop real, or theatre? |
| 19 | Recalibrated model's residual vs `ref_price_t90`, both tracks, anytime-valid | **Does any edge exist?** If the lower bound has not cleared zero by day 90, the correct action is to stop staking real money and continue as a research programme |
| 20 | Fantasy grading loop: populate `gw`, add realised points, backfill from FPL | Is the sanctioned monetisation measurable at all? |
| 21 | Answer the account question with a live account or a documented NO | **Is +2.6 to +4.2pp of margin reduction reachable?** |
| 22 | Season-end v9 retrospective on the frozen book, split by track and by effective-threshold regime | What did the freeze actually buy? |

**Explicit non-goals for 90 days:** no new features, no new estimator, no threshold change, no market
expansion, no stake increase, no props, no purchase.

---

## 11. Weekly Improvement Architecture

How **Monday data** becomes **Sunday learning** becomes **next week's challenger** — with real repos
and real file names. Structural separation, not discipline: *the weekly job must have no code path to
a parameter file.*

### Monday–Saturday: accumulate (no decisions)

| when | workflow | writes |
|---|---|---|
| every 5–10 min, 08–23 UTC | `v9/.github/workflows/predict.yml` (frozen) | `v9/output/bets_ledger.csv`, `predictions.csv`, `book_odds_snapshots.csv`, `odds_history_v9.json` |
| 8×/day | `v9/.github/workflows/std_odds_capture.yml`, `nf_odds_capture.yml` (frozen) | side-market forward captures |
| every 2h + daily sweep | `v10/.github/workflows/pro_collect.yml` | `v10/data/season_2026_27/{fixtures,market_snapshots,book_odds_snapshots,settlements,team_news,...}` |
| every 6h | `v10/.github/workflows/pro_backfill_results.yml` | `settlements` (dedup at `read()`, not in the partition) |
| 2×/hour | `wowza-v11/.github/workflows/v11_collect.yml` | `v11_shadow_snapshots.csv`, `v11_placebo_table.csv`, `v11_chronological_folds.csv` **(both newly staged)** |

Nothing here reads a threshold, fits a parameter, or promotes anything.

### Sunday 06:00 UTC — learn (`pro_weekly_learning.yml`, new)

Runs, in this order, and **writes exactly one artefact**:

1. `python -m src.market.close --write` → `ref_price_t90` for every fixture settled this week
   (LOCF, power de-vig, `panel_definition` recorded).
2. `python -m src.market.clv_schema --write` → CLV against `ref_price_t90`, with
   `CLOSE_NOT_PROVEN_PRE_KICKOFF` / `CLOSE_EQUALS_ENTRY` / `CLV_IMPLAUSIBLE` flags preserved. Rows
   before 2026-08-10 are excluded, not repaired.
3. `python -m src.validation.residual` → residual test of champion vs `ref_price_t90`, per track,
   fixture-clustered, with an anytime-valid lower bound.
4. `python -m src.validation.placebo` → the corrected battery (league baseline, fixed anchor, shuffled
   residual, market midpoint, favourite bias), paired clustered bootstrap **of the difference**.
5. `python -m src.monitoring.weekly_audit --days 7` → calibration (ECE), coverage, drift.
6. Append one row to `v10/output/weekly_learning_log.csv`:
   `week, champion_sha, n_settled, clv_n, mean_clv_pct, residual_lower_bound, ece, placebo_margin, verdict`.

**No fitting. No parameter file. No promotion.** The Sunday job cannot promote by construction: the
promote workflow has no schedule trigger.

### Sunday 08:00 UTC — challenge (`pro_challenger.yml`, new)

Trains challengers under a **category firewall** so a result is attributable:

| model | feature categories | question it answers |
|---|---|---|
| A | current champion, unchanged | baseline |
| B | A + recalibration on outcomes only | how much of the gap is calibration? |
| C | B + form/rolling features only | does football history add anything? |
| D | B + de-vigged consensus price only | how much is the market? |
| E | B + form + price | **δ(C,E) is the go/no-go on the entire modelling programme** |

Writes each as a `ModelRecord` into `v10/registry/`. `Registry.promote()` calls `evaluate_gate()`
and records verdict + reasons. **Every challenger is expected to be refused for the foreseeable
future**, because `min_mean_clv_pct > 0` fails at a measured −0.031% and the corrected residual is
~0.38pp of price movement. That is the system working.

`MARKET_CONFIRMATION_SCORE`, if it is ever built, is **veto-only** — never a stake multiplier. v9's
existing movement consumer is an unfloored stake multiplier on a signal (mean |drift| 4.32% of price)
that is *half the width* of the instantaneous cross-book range used to read it (median 8.67%).

### Next Monday — deploy nothing, or deploy one thing

The only path from a Sunday verdict to production is a human running `pro_promote.yml` with a
`ModelRecord` id that passed the gate. On a PASS, Pro's own predictor swaps; **v9 is never touched.**
Model identity is Pro's content hash of the fitted artefact — not v9's `model_sha`, which is a run
identifier.

### What makes this real rather than theatre

- `weekly_learning_log.csv` accrues a verdict every week whether or not anything improves, so
  "is Wowza improving?" becomes a query instead of an argument.
- Clean closes reach 764/785 OU25 fixtures per capture era (97.3%, measured), i.e. roughly
  170–220/week, so `min_clv_n=150` is reachable per segment in **1–3 weeks** — not the 35–55 days
  concluded from the raw-panel reading.
- **A weekly *refit* is explicitly not part of this.** At ~1.4% new training data per week a weekly
  refit cannot move a metric; it only adds variance and a promotion opportunity. The weekly loop
  evaluates; retraining is triggered (see answers below).

---

## Direct Answers

**Does Wowza currently learn from its newest data efficiently enough?**
No — it barely learns at all. It *collects* superbly (1.6M rows, 21 tables, 145,835 real book quotes)
and converts almost none of it into a decision. `backtest_metrics_history.json` has no entry since
2026-06-17 across four model changes; `v10/registry/` holds only `.gitkeep`; the retrain saves before
it backtests and only prints the comparison. The estate has no memory of whether it is getting better.

**Which components are static that should become adaptive?**
Calibration (the +13.64pp gap is the single most fixable defect). The closing-price reference
(`ref_price_t90` should track capture quality, not be assumed). The consensus panel definition (should
be a recorded column, not an implicit choice). Book selection at execution time. Conversely, three
things that are adaptive and **must become static**: `best_params_standard.json` (unwire it),
`optimize_side_market_thresholds` (delete it), and the ledger's tier max-ratchet (record every
sighting, never overwrite).

**Should models retrain weekly, periodically, or only on triggers?**
**TRIGGERED_ONLY.** A weekly refit changes the training set by ~1.4% and cannot move any metric; it
only manufactures promotion opportunities. Triggers: (a) ECE > 0.05 on a rolling 4-week window,
(b) residual lower bound crossing zero in either direction, (c) a data-quality break like the
2026-08-27 capture cut, (d) season roll. Evaluate weekly; retrain on a trigger; promote only through
`evaluate_gate()`.

**Do odds snapshots contain predictive information beyond static prices?**
**UNPROVEN, and smaller than it looks.** The corrected series has 85.9% of one-hour windows at
*exactly* zero movement and a median of 3 distinct odds pairs per fixture — the constraint is that
`v11_p_market` is a step function, not sample size. What is proven: the closing consensus beats the
opening consensus (Brier 0.23622 vs 0.23948, n=291), so the price series does carry information over
time. What is not proven: that *we* can extract any of it, given a T-90m median observation and a
signal (4.32% of price) half the width of the cross-book range used to measure it (8.67%).

**Does odds movement improve outcome prediction? Does it improve betting SELECTION?**
Outcome prediction: marginally yes — closing beats opening at a 56.4% toward-rate. Selection: **no,
and the seed's evidence for it was a bug.** The 0.995 mean-reversion toward-rate was
`future_move ≡ −prev_move` by construction (I reproduced it). Corrected, every placebo margin spans
zero and the surviving model coefficient is worth 0.38pp of price movement against a 6.96% spread.
Meanwhile v9's actual movement consumer — the drift tier upgrade — is measured as the *better* half
of its own bets, which is evidence of noise, not signal.

**Should Wowza's probability change when the market confirms or contradicts it?**
**CONDITIONAL — veto only, never a stake multiplier, and not yet.** Two measurements forbid the
multiplier: the drift signal is half the width of its own ruler, and 18.11% of fixtures have the
*selected book* switch between open and close, contributing 56.1% of the measured drift on those
fixtures with 21.05% sign disagreement. Until movement is measured on a stable de-vigged consensus
panel with `panel_definition` recorded, market confirmation may suppress a bet and must never enlarge
one.

**Which snapshot horizon carries the most information?**
Unanswerable at the end that matters. T-6h to T-3h is where we have coverage (71.2% / 66.2%) and
T-10m is where the information is (17.7% coverage, n=136 fixtures). The market's own evidence says
later is better — closing consensus Brier 0.23622 < opening 0.23948 — so the honest answer is
"the horizon we do not collect". Restore near-kickoff density as instrumentation, then ask again.

**Are current league thresholds supported by real results?**
**No.** The backtest that sets them has 50.0% sign agreement with live per-league ROI (k=18 leagues,
Spearman +0.325, p=0.188), and it inverts on exactly the trusted leagues: La Liga 2 backtest +0.13 →
live −32.24; League One +4.11 → −37.53; Championship +5.04 → −20.48. Not one league has a confidence
interval excluding zero. And the thresholds actually in force since 2026-08-21 are workflow-env
overrides (`MARKSMAN 0.08`, `VALUABLE 0.03`, `LEAGUE_SNIPER_CAP 0.12`), not the documented ones — so
every threshold claim, including every one in this audit, is measured against a moving bar.

**Which leagues need higher thresholds? Which need lower?**
**INSUFFICIENT_DATA, in both directions, for every league.** Largest staked cell is USA MLS at n=72
(−1.42%). Every CI spans zero. And answering it at all would be invariant 6 — fitting a cut point on
the results that evaluate it. This question must stay unanswerable by design: the design in §11 gives
the weekly job no code path to a parameter file precisely so this counter is unreachable rather than
merely discouraged.

**Which markets should be disabled from trusted betting?**
- **`over15` — disable now.** Its four league approvals were computed on a constant 1.40 price on
  99.99% of backtest rows. Certified false positive.
- **HT O/U — already dead, formalise it.** 0 of 77 board rows can cross any threshold;
  `ht_ledger.csv` has never existed while three workflows stage it.
- **Side markets (BTTS/over35) — keep on paper, do not promote.** The +18.10u is one league (96/147),
  one market (88/147), one month, CI [−3.1%,+27.7%], tier ordering inverted, mean CLV −2.51%, and
  four target leagues with zero settled rows.
- **Player props — permanently paper (invariant 2).**
- **Standard O/U 2.5 — the real-money track — stays enabled only because n=7 settled means nothing
  has been tested.** It should not carry increased stakes until the residual lower bound clears zero.

**Which bookmaker movements carry the most information?**
Pinnacle leads the consensus (+0.120 sign-agreement differential, z≈2.5) and Matchbook second
(+0.068); `gtbets` (−0.189) and `betonlineag` (−0.138) are pure followers. **But this is not
actionable:** Pinnacle's median quote is 1,518 minutes from kickoff with only 3.79% inside T-60m, it
covers 34.3–56.1% of fixtures depending on market, and the measurement is confounded by repricing
frequency and by each book sitting inside the consensus it is compared against. Answering it properly
needs ~300 settled fixtures with Pinnacle present; we have 77.

**Is Wowza improving week to week right now? If not, exactly what prevents it?**
**No, and it cannot currently tell.** Four specific blockers: (1) no baseline — `v10/registry/` is
empty, so there is nothing to compare a challenger to; (2) no record —
`backtest_metrics_history.json` is written on the runner and destroyed, last entry 2026-06-17;
(3) no gate — `retrain.py:371` saves before `:393` backtests and `_print_comparison` only prints;
(4) no honest metric — the deployed meta-blend carries `metrics = {}` and was fitted on its own test
set. Wire (1) and (3) and the question becomes a query against `weekly_learning_log.csv`.

**Where would you spend the next $100?**
**Nowhere. Keep it.** At $30/stake it buys 3.3 bets on a track with a 58-year readout, and there is
no dataset in this audit that $100 improves: API-Football is at 15% utilisation, more OddsAPI credits
buy books we already receive and discard, and the past cannot be repurchased. The one thing worth
buying is the near-kickoff worker at $0–5/month — and only *after* the gate is registered, because
today it would buy an honest REJECT rather than a better bet. If you must spend, spend it there.

**The next 100 engineering hours?**
In order: 2h fix v11's `_asof` and stage its two dropped outputs → 8h register the champion and wire
`Registry.promote()` → 2h measure the `no_form_data` split before 2026-09-15 → 4h delete the
pre-2026-08-10 CLV era and add the kickoff filter in Pro's importer → 24h build `ref_price_t90`
(LOCF de-vigged consensus with `panel_definition`) → 16h recalibrate on outcomes, per track → 4h
unwire `best_params_standard.json` and delete `optimize_side_market_thresholds` from production →
1h withdraw `over15` → 4h fix Pro's test collection and wire one CI job → 8h the reusable push
workflow → 27h stage best-price selection in Pro as paper.

**What would you NOT spend another dollar on yet?**
API-Football credits. Any OddsAPI plan tier. Any historical-odds purchase. Any xG or advanced-stats
feed. Any lineup/injury feed. Any Betfair or exchange integration as a purchase. Any new model
estimator. Any threshold optimiser. Any player-props path. Any new league or market. Any increase in
real-money stakes. Compute of any kind beyond $5/month of instrumentation.

---

WOWZA_ARCHITECTURE_HEALTH = C+ — excellent collection and warehousing, no wire between research and decision; ~30 duplicated push epilogues in 3 divergent conflict policies
WOWZA_DATA_QUALITY = B− — feature engineering verified leak-free; the defects are all in the *derived* layer (CLV era, closing-price join, 23 of 65 features silently dropped, ledger max-ratchet)
WOWZA_MARKET_DATA_QUALITY = B for breadth (24 books, 145,835 rows, 0% post-kickoff), D for timing (median last quote T-91m, 32.0% of fixtures inside T-30m)
WOWZA_MODEL_ADAPTIVENESS = F — no gate, no registry baseline, no honest metric, no record since 2026-06-17; the only adaptive loop wired to money is a retrospective threshold fit
WOWZA_WEEKLY_LEARNING_READY = NEARLY — every component exists in Pro (gate, calibrators, de-vig, consensus, preregistration, 97.3% close coverage); the gap is registration and wiring, ~2 weeks
WOWZA_RESEARCH_RIGOR = B+ in the research harness (preregistration, honoured kills, provenance), F in production (two live retrospective-tuning loops)
WOWZA_EDGE_STATUS = NO MEASURED EDGE. +13.64pp overconfident (z=7.81); Brier 0.2583 vs the vigged book's 0.2368; corr(edge,pnl)=+0.013; corr(edge,CLV)=−0.201. The corrected v11 residual is non-zero (+0.0112, CI excludes zero) but worth 0.38pp of price against a 6.96% spread
CURRENT_CHAMPION_STATUS = UNGATED AND UNREGISTERED — would be REFUSED by Pro's own `evaluate_gate()` on at least two checks (`min_mean_clv_pct` at a measured −0.031%, and logloss improvement vs market-only)
CHALLENGER_SYSTEM_READY = NO
WEEKLY_RETRAINING_RECOMMENDED = TRIGGERED_ONLY
MARKET_MOVEMENT_ADDS_INFORMATION = UNPROVEN
SNAPSHOTS_SHOULD_AFFECT_SCORE = CONDITIONAL
LEAGUE_THRESHOLDS_VALIDATED = NO
PRIMARY_BOTTLENECK = The decision rule. `edge = p_model − 1/odds` subtracts a better forecast from a worse one on a raw vigged quote, and nothing gates it — no registry baseline, no accept/reject on retrain, no honest metric on the deployed predictor
BEST_NEXT_INVESTMENT = One hour and $0 asking whether Matchbook (2.76% overround) and/or Pinnacle (4.17%) are reachable at size from this jurisdiction — worth +2.6 to +4.2pp of ROI with zero model risk, larger than any effect this audit measured on either side of zero
BEST_NEXT_ENGINEERING_TASK = Fix the two `_asof` returns at `wowza-v11/scripts/v11_momentum_control.py:141,158` and stage `v11_placebo_table.csv` + `v11_chronological_folds.csv` in `v11_collect.yml` — 4 lines and one staging block that restore the estate's only residual instrument
BIGGEST_WASTE_TO_AVOID = "Fixing" a threshold or the drift guard. It is invariant 3 and invariant 6, it targets the measurably *better* half of the bets (−13.4% vs −49.9%), it addresses at most 21% of the loss — and it would look like a fix, which is how the real cause (a +13.64pp calibration gap on a decision variable with zero information) stays unaddressed for another season
READY_FOR_PRODUCTION_STAKING = NO
READY_TO_CONTINUE_PROSPECTIVE_RESEARCH = YES

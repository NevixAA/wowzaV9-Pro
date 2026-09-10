# AGENT 7 — False-Discovery Red Team

**Date:** 2026-09-10 · **Remit:** try to prove every apparent edge is fake · **Mode:** read-only on `v9/` and `wowza-v11/`
**Data state:** `v9/output/*.csv` as pulled 2026-09-10 10:31; `wowza-v11/output/v11_shadow_snapshots.csv` (49,539 rows, 956 fixtures, 2026-08-10 → 2026-09-08)
**Python:** `v9/.venv/Scripts/python.exe` (pandas 3.0.3)

---

## HEADLINE

**Every apparent edge in the system dies, but not for the reasons the seed brief gives.** The seed's
two flagship diagnoses are both artefacts of reading the wrong file: the "staked-tier defect" reads
`config.py` defaults that production overrides (`predict.yml` runs MARKSMAN at **0.08**, not 0.14, and
clamps every per-league SNIPER threshold to **0.12**), and the "three information-free predictors beat
the model" placebo result is produced by a **one-line index-alignment bug** in v11's momentum control
that makes every price-movement column compare *one fixture's price to a different fixture's price*.
What survives after both are corrected is worse than either: over 405 post-cutoff settled O/U bets,
the tiers the system **stakes** have significantly **negative** closing-line value (−1.227%) while the
tier it deliberately does **not** stake has positive CLV (+0.907%) — difference −2.139pp,
fixture-clustered 95% CI **[−3.584, −0.653]**, excludes zero. The tiering function is anti-predictive
of the market, and `edge_pct` has a Spearman correlation with realised P&L of **−0.0052**.

---

## FINDINGS

| # | Finding | Evidence | Conf. | Cat. | Impact | Fix |
|---|---|---|---|---|---|---|
| 1 | v11 momentum control's `_asof` misaligns every movement column — all momentum/movement results void | `v11_momentum_control.py:158` `return out.sort_index()["p_at"]`; corr(prev,future) = **−0.9995**; median \|future_move\| 9.56pp vs true **0.00pp** (85.9% exactly zero) | PROVEN | STATISTICAL | CRITICAL | HOURS |
| 2 | Staked tiers have significantly WORSE CLV than the unstaked tier | staked (n=178) **−1.227%** vs VALUABLE (n=227) **+0.907%**; diff −2.139pp, clustered CI **[−3.584, −0.653]** | PROVEN | EXECUTION | CRITICAL | DAYS |
| 3 | Production thresholds are NOT the config defaults — the seed's tier defect is misdiagnosed | `predict.yml:190-192` `LEAGUE_SNIPER_CAP: "0.12"`, `MARKSMAN_THRESHOLD: "0.08"`, `VALUABLE_THRESHOLD: "0.03"` | PROVEN | PROCESS | CRITICAL | HOURS |
| 4 | OPEN QUESTION ANSWERED: `edge_pct` IS the tip-time edge | `kelly_pct` reproduces `edge_pct` on **1060/1061** live rows; tier reproduced from edge+league+drift on **432/433** rows (**127/127** staked) under production env | PROVEN | DATA_QUALITY | HIGH | — |
| 5 | `edge_pct` carries no information about P&L | Spearman(edge_pct, pnl) = **−0.0052** over 184 staked bets; largest bucket (8,10]% n=41 is **−32.1%** ROI; (14,100]% is **−10.2%** | PROVEN | STATISTICAL | HIGH | DAYS |
| 6 | The +35.3% new_format BTTS SNIPER cell is not distinguishable from noise | tier-label permutation **P = 0.204**; exact binomial **p = 0.075**; H1 +67.4% / H2 +5.4%; 25/29 rows one league; drop 5 winners → +11.7% | PROVEN | STATISTICAL | HIGH | — |
| 7 | The +18.1u side/BTTS track is entirely front-loaded | H1 (08-09..08-29) n=73 **+30.8%**; H2 (08-30..09-09) n=74 **−5.9%** | PROVEN | STATISTICAL | HIGH | — |
| 8 | side_bets_ledger settlement is selective, not random | 107/254 never settled; **La Liga 2 (23), Ligue 2 (13), League One (6), League Two (6) have ZERO settled rows**; `over35` 5 rows / 0 settled; 96/147 settled rows are one league | PROVEN | DATA_QUALITY | HIGH | DAYS |
| 9 | side-market CLV is corrupt and unusable | 9/135 rows with BTTS `closing_odds` **6.00–8.00** against bet prices 1.97–2.50; `clv_pct` min **−68.75** | PROVEN | MARKET_DATA | MEDIUM | HOURS |
| 10 | new_format OU25 MARKSMAN "+2.5%" is one winner deep | drop top 1 winner → **+0.26%**, top 3 → **−4.11%**; permutation P=0.652; random 142-subset CI [−16.5, +10.6] | PROVEN | STATISTICAL | MEDIUM | — |
| 11 | Corrected placebo battery: the residual is indistinguishable from a shuffled residual | v9 0.5257 [0.5068,0.5431]; **v9 − shuffled = +0.78pp CI [−1.01,+2.48]**; vs anchor +0.71 [−0.88,2.17]; vs league baseline −0.25 [−2.02,1.46] | PROVEN | STATISTICAL | HIGH | — |
| 12 | `fix_ledger_tiers.py` promotes rows to MARKSMAN off a Telegram log, ignoring edge | `fix_ledger_tiers.py:69-70` `new_tier = "SNIPER" if rederived=="SNIPER" else "MARKSMAN"`; rewrote 42 live tiers (27 without touching edge) | PROVEN | PROCESS | MEDIUM | HOURS |
| 13 | Drift-manufactured tiers are *less* bad than tiers earned on edge | standard: drift-manufactured n=19 ROI **−28.7%** vs earned-on-edge n=20 ROI **−35.8%** | PROVEN (but INSUFFICIENT_DATA for direction) | STATISTICAL | MEDIUM | — |
| 14 | `backtest_metrics_history.json` holds 4 entries, newest 2026-06-17 | keys: `2026-05-21_standard`, `2026-05-21_newformat`, `2026-06-17_standard`, `2026-06-17_newformat` | PROVEN | PROCESS | HIGH | HOURS |

---

## 1. The v11 placebo battery is measuring a bug, not a market

**PROVEN.** `wowza-v11/scripts/v11_momentum_control.py` builds every momentum and target column
through two helpers, `_asof` (line 144) and `_asof_col` (line 126). Both end with:

```python
out = pd.merge_asof(left.sort_values("target_ts"), right.sort_values("match_ts"), ...)
return out.sort_index()["p_at"]        # line 158  (and line 141 for _asof_col)
```

`pd.merge_asof` **does not preserve the left frame's index** — it returns a fresh `RangeIndex`.
So `out.sort_index()` returns the matched prices in **`target_ts` order**, which is then assigned
back to `d` in **original row order**. Every value lands on the wrong row.

Minimal reproduction (two fixtures at 0.10–0.13 and 0.90–0.93, true forward move +1.0pp on every row):

| fixture | p_market | p_next (v11 code) | p_next (correct) | future_move v11 | future_move correct |
|---|---|---|---|---|---|
| 1 | 0.10 | 0.11 | 0.11 | +1.0 | +1.0 |
| 2 | 0.90 | 0.13 | 0.91 | **−77.0** | +1.0 |
| 1 | 0.11 | 0.91 | 0.12 | **+80.0** | +1.0 |
| 2 | 0.91 | 0.93 | 0.92 | +2.0 | +1.0 |

`merge_asof preserves left index? False`.

### Why this produces exactly the reported numbers

`prev_move` and `future_move` are joined at `t−60m` and `t+60m`. Sorting by `t−60` and by `t+60`
gives the **same permutation**, so both columns are scrambled identically. For row *i* receiving
row *j*'s prices, and given that the real price series barely moves:

```
prev_move[i]   ≈ p[i] − p[j]
future_move[i] ≈ p[j] − p[i]   =  −prev_move[i]
```

Measured on the real snapshots through `mc.build(60,60)`:

* `corr(prev_move_pp, future_move_pp)` = **−0.9995**
* `P(sign(future) = −sign(prev))` = **0.996**
* median `|future_move_pp|` = **9.555pp** — that is the *cross-fixture spread* of `p_market`, not a price move

Against the actual snapshot series:

* **81.9%** of consecutive snapshot pairs have `Δp_market` **exactly 0**; median `|Δ|` = 0.000pp, p90 = 0.250pp
* median **3** distinct (over, under) odds pairs per fixture (example: Brøndby–Silkeborg, **192 snapshots, 4 distinct odds pairs**)
* real lag-1 autocorrelation of consecutive deltas = **−0.10**, not −0.9995

So the "mean reversion toward-rate of 0.995 / +29.2pp over v9" in the seed brief is not a verdict on
the price series — it is the arithmetic identity `future_move = −prev_move` created by the join.

**Everything downstream of `build()` is void:** `v11_momentum_control.csv` (the "+ momentum" and
"+ full controls" residual coefficients, the `velocity_pp_h` −0.248 that "absorbs" the raw
coefficient), `v11_momentum_roles.csv` (WOWZA_OPPOSES_MARKET 99.6% toward / AGREES 0.5% is the same
identity), the placebo table, and the chronological folds. `src/movement.py` — the source of the
separate 57.9% headline — does **not** contain this pattern (`grep merge_asof` hits only this one
script), so that number is untouched by this bug and remains to be re-tested on its own terms.

## 2. The corrected placebo battery — the edge thesis is UNPROVEN, not disproven

Re-ran `build()`'s joins with the index carried through (`left.reset_index()` → `out.set_index("_orig")`).
The correction shrinks the usable sample by a third in fixtures — the bug was **manufacturing
matches** for rows that had no real ±60m neighbour:

| | buggy | corrected |
|---|---|---|
| rows with prev+future | 33,661 | 33,661 (same count, permuted) |
| **fixtures** | **566** | **367** |
| median `\|future_move\|` | 9.555pp | **0.000pp** |
| exactly-zero forward moves | 51 (0.2%) | **28,905 (85.9%)** |
| moved rows / fixtures | — | **4,756 / 341** |

Battery on moved rows only, toward-rates with fixture-clustered bootstrap (1,000 resamples), plus a
**paired** clustered bootstrap of the difference against v9 — the test the existing script does not do
(it compares point estimates only):

| variant | toward | 95% CI | v9 − this (pp) | diff CI | verdict |
|---|---|---|---|---|---|
| PLACEBO_league_baseline | 0.5282 | [.5114,.5443] | −0.25 | [−2.02, +1.46] | **tie** |
| **v9_residual** | **0.5257** | **[.5068,.5431]** | 0.00 | — | — |
| PLACEBO_fixed_anchor | 0.5185 | [.5006,.5351] | +0.71 | [−0.88, +2.17] | **tie** |
| PLACEBO_shuffled_residual | 0.5179 | [.5023,.5331] | +0.78 | [−1.01, +2.48] | **tie** |
| PLACEBO_market_midpoint_0.50 | 0.5156 | [.4973,.5323] | +1.01 | [−0.45, +2.50] | **tie** |
| PLACEBO_random_direction | 0.4916 | [.4773,.5046] | +3.41 | [+1.01, +5.77] | v9 better |
| PLACEBO_favourite_bias | 0.4773 | [.4602,.4953] | +4.84 | [+1.69, +7.98] | v9 better |
| PLACEBO_mean_reversion | **0.2508** | [.2328,.2689] | +27.48 | [+25.15, +30.03] | v9 better |
| PLACEBO_momentum_continuation | 0.1806 | [.1678,.1917] | +34.50 | [+32.30, +36.60] | v9 better |

Chronological quarters of the v9 toward-rate (moved rows span 2026-08-17..08-26 only):
0.5046 / 0.5172 / 0.5408 / 0.5399.

**Read this correctly, in both directions.**

* The seed's claim that *"three predictors with zero football information beat the model"* is
  **REFUTED**. Mean reversion falls from 0.996 to 0.2508 once the join is fixed; the fixed anchor and
  the market midpoint drop from 0.752/0.741 to 0.5185/0.5156 and no longer beat v9.
* But the edge is **not** established either. A model probability **drawn from a different fixture**
  scores 0.5179 against v9's 0.5257, and the paired difference CI is **[−1.01, +2.48]** — spanning
  zero. Same for the constant anchor, the 0.50 midpoint, and the league mean. On 341 fixtures and
  4,756 moved observations this is **INSUFFICIENT_DATA**: the honest statement is "we do not know",
  and the corrected dataset is an order of magnitude thinner than anyone has been budgeting for.
* The only things v9 provably beats are a random sign, a favourite bias, and momentum — none of which
  anyone proposed betting.

## 3. The staked-tier defect: the seed read the wrong file

**PROVEN.** `v9/.github/workflows/predict.yml:190-192`:

```yaml
LEAGUE_SNIPER_CAP: "0.12"
MARKSMAN_THRESHOLD: "0.08"
VALUABLE_THRESHOLD: "0.03"
```

Production therefore runs **MARKSMAN at 0.08 and VALUABLE at 0.03**, and `LEAGUE_SNIPER_CAP` clamps
`LEAGUE_SNIPER_THRESHOLDS` and `LEAGUE_MARKSMAN_THRESHOLDS` through the `min(v, _SNIPER_CAP)` at
`config.py:329` and `:342`. Consequences, none of which the seed's framing captures:

* **The entire per-league calibration is switched off by one env line.** League One 0.25 → 0.12,
  Ligue 2 0.25 → 0.12, La Liga 2 0.20 → 0.12, Bundesliga 2 0.20 → 0.12, Greek 0.25 → 0.12,
  Championship/Serie B 0.15 → 0.12, League Two 0.14 → 0.12. Those numbers carry documented backtest
  ROIs beside them in `config.py:317-325` ("La Liga 2 0.20 → ROI +53.5%", "League One 0.25 →
  ROI +21.4%", "Ligue 2 0.25 → ROI +45.2%"). None of them is in force.
* **A documented decision is silently reverted.** `config.py:277-279`: *"MARKSMAN raised 8%→14% on
  2026-06-17: sweep showed 8–14% zone is −1.6% ROI; 14%+ zone is +6.5% ROI."* The workflow puts it
  back to 0.08.
* **Bundesliga 2's MARKSMAN exclusion is defeated twice** — once by the cap (0.20 → 0.12), once by
  the drift rule. `config.py:337` says "match SNIPER — no MARKSMAN; 8-20% = −10.8% ROI". Bundesliga 2
  nonetheless has 8 staked MARKSMAN bets post-cutoff at −3.23u.
* The seed's specific claim *"LEAGUE_MARKSMAN_THRESHOLDS covers ONLY {Bundesliga 2: .20, League Two:
  .14} — everything else falls back to global .14. Worst leagues are exactly the mismatched ones"* is
  **REFUTED**: with the cap in force nothing falls back to 0.14, and La Liga 2 / League One are not
  "mismatched" — their calibrated thresholds were cut from 0.20/0.25 to 0.12, which is the opposite
  problem and a better-supported causal story for those two leagues being the worst.
* The count changes too. Of the 38 staked standard MARKSMAN bets, **37 are below 0.14** (the seed's
  number, correct against the wrong threshold) but only **24 of 35** are below the real 0.08 floor —
  and the 11 at or above 0.08 are **−8.86u at a 9.1% win rate**, worse than the 24 below it
  (−4.27u, 37.5%).

## 4. OPEN QUESTION ANSWERED — `edge_pct` is the tip-time edge

The seed asked whether `edge_pct` is recorded at settlement or whether tiering uses a different
`best_edge`. **Neither. It is the edge at tip time, and the tier is consistent with it.**

Three independent proofs:

1. **No settlement writer exists.** `edge_pct` is written in exactly two places, both in
   `src/ledger.py:175` and `:198`, both inside `append_tips`, both from `row["best_edge"]` of the
   same run that supplies `signal_tier`. `update_results.py` contains no `signal_tier` or `edge_pct`
   assignment.
2. **`kelly_pct` corroborates it arithmetically.** `_kelly_pct(edge, odds) = edge/(odds−1)·0.25·100`
   (`ledger.py:71-76`). Inverting it from the stored `kelly_pct` and `odds` reproduces the stored
   `edge_pct` to within 0.15pp on **1,060 of 1,061** live rows. A later-overwritten edge would break
   this pairing.
3. **The tier is reproducible from the edge.** Re-implementing `_base_tier` + `_apply_drift_adjustment`
   under the **production** env (cap 0.12 / MM 0.08 / VAL 0.03) plus `models/best_params_standard.json`
   reproduces `signal_tier` on **432 of 433** live rows generated on/after 2026-08-16, and on
   **127 of 127** post-cutoff staked settled rows. Under the `config.py` defaults the same test scores
   only 774/1061 (73%) — which is precisely the illusion that generated the open question.

So **the 6.11% median IS the edge the decision was made on.** The sub-4% "MARKSMAN" rows the seed
found impossible (edge 3.03–3.98%, all `drift_signal = Confirmed`) are simply `VALUABLE` under
`VALUABLE_THRESHOLD = 0.03` promoted by the `VALUABLE + Confirmed → MARKSMAN` rule at
`betting.py:211-213`. The lowest observed is 3.03% and none is below 3.00% — the floor is visible in
the data.

`models/best_params_standard.json` supplies the rest: **Championship `sniper_th` 0.07 / `marksman_th`
0.05, `approved: true`** and **Serie B 0.12 / 0.10, `approved: true`**. That is why a Championship
row carries `signal_tier = SNIPER` at an 8.74% edge — it is a base SNIPER under an auto-optimised
threshold of 0.07, not a drift artefact.

**One live landmine found while answering this.** `v9/scripts/fix_ledger_tiers.py:69-70`:

```python
rederived = _base_tier(edge, str(r.get("side","")), str(r.get("league","")))
new_tier  = "SNIPER" if rederived == "SNIPER" else "MARKSMAN"
```

Any ledger row whose key appears in `telegram_bot/notified.json` and is not already SNIPER/MARKSMAN
is **forced to MARKSMAN regardless of its edge**, and `edge_pct` is deliberately left alone (the
docstring: *"the peak edge was never stored, so we cannot prove SNIPER"*). Diffing
`bets_ledger.csv.pre_tierfix_bak` against the live ledger: **42 live rows rewritten** (27
VALUABLE→MARKSMAN, 15 VALUABLE→SNIPER), 15 with an edge change. This is selection on *having been
notified*, which is downstream of the tier being evaluated. **It happens not to contaminate the
current numbers** — 0 of the 184 post-cutoff staked settled rows were rewritten (they are all newer
than the backup) — but re-running that script would silently redefine the staked population.

## 5. `edge_pct` has no relationship with P&L

**PROVEN.** All 184 post-cutoff staked settled bets:

| edge bucket | n | win | P/L | ROI |
|---|---|---|---|---|
| (0, 4] | 23 | 0.391 | −1.88 | −8.2% |
| (4, 6] | 24 | 0.375 | −1.83 | −7.6% |
| (6, 8] | 10 | 0.700 | +6.26 | +62.6% |
| **(8, 10]** | **41** | **0.293** | **−13.17** | **−32.1%** |
| (10, 14] | 51 | 0.451 | +1.88 | +3.7% |
| (14, 100] | 35 | 0.371 | −3.56 | −10.2% |

`Spearman(edge_pct, pnl) = −0.0052`. The largest bucket is the worst; the top bucket is negative.

This kills the natural remedy the seed's framing implies. **Raising the MARKSMAN floor to 14% would
not have helped** — the ≥14% bucket returns −10.2%. And on the drift mechanism specifically:

| model | origin | n | win | P/L | ROI | median edge |
|---|---|---|---|---|---|---|
| standard | drift_manufactured (base VALUABLE/AVOID) | 19 | 0.316 | −5.46 | −28.7% | 4.27% |
| standard | earned_on_edge | 20 | 0.300 | −7.17 | −35.8% | 8.71% |
| new_format | drift_manufactured | 25 | 0.440 | +1.63 | +6.5% | 3.84% |
| new_format | earned_on_edge | 63 | 0.397 | −2.90 | −4.6% | 10.19% |

The drift-manufactured half is **less bad** in both model tracks. n=19/20 is far below the
evidentiary bar — call it **INSUFFICIENT_DATA** — but the seed's causal claim that the asymmetric
drift guard is what is losing the money is **not supported by the sign of the effect**.

## 6. CLV: the tiering function is significantly anti-predictive

**PROVEN, and this is the strongest result in the audit** because CLV has far less outcome variance
than ROI and the closing prices here are clean (405 rows with CLV; `closing_odds/odds` ratio spans
0.816–1.419, **zero** outliers outside [0.66, 1.5]; 18.3% exact zeros).

Post-cutoff settled O/U 2.5, mean `clv_pct` by tier:

| tier | n | mean CLV |
|---|---|---|
| SNIPER | 53 | **−1.755%** |
| MARKSMAN | 125 | −1.003% |
| VALUABLE (**not staked**) | 227 | **+0.907%** |

Fixture-clustered bootstrap (5,000 resamples, clustered on date|home|away):

* staked (SNIPER+MARKSMAN) − VALUABLE = **−2.139pp**, 95% CI **[−3.584, −0.653]** — excludes zero
* SNIPER − VALUABLE = **−2.654pp**, 95% CI **[−5.167, −0.045]** — excludes zero

**CLV is monotonically decreasing in tier.** The market moves against the bets the system stakes and
with the bets it declines to stake. Every ROI cell in this audit has a CI spanning zero; this one does
not. It is also the only result consistent across both the economic and the market-microstructure
evidence: a residual indistinguishable from a shuffled residual (§2) is exactly what produces
negative CLV on the rows where the residual is largest.

Note the direction is a **within-system contrast** and therefore robust to the usual excuses — vig
level, league mix, sample period and staking are all shared between the two arms.

## 7. Killing the +35.3% BTTS SNIPER cell

`side_bets_ledger.csv` as of 2026-09-10 10:31 holds **254 rows / 147 settled / 88W-59L / +18.10u**
(the seed's 246 / 143 / 86-57 / +18.56u is an earlier file state).

The cell: `model_type=new_format, market=btts, signal_tier=SNIPER`, n=29, +10.245u, ROI +35.3%.
Five independent attacks, all of which it fails:

1. **Tier-label permutation, multiplicity-corrected.** Permuting `signal_tier` within
   (model_type, market) 20,000 times: `P(some cell with n≥25 reaches ROI ≥ 35.3%) = **0.2044**`.
   One in five shuffles produces a cell this good. The label carries nothing.
2. **Exact binomial against the market's own price.** 17/29 wins, mean odds 2.301, mean implied
   probability 0.436. One-sided **p = 0.0751** — not significant *before* any multiplicity correction.
3. **Chronological.** H1 (08-22..08-31) n=14 → +9.43u, **+67.4%**. H2 (09-01..09-07) n=15 → +0.81u,
   **+5.4%**. The result is 92% first-fortnight.
4. **Winner concentration.** Drop top 1 → +30.9%; top 2 → +26.5%; top 3 → +21.8%; **top 5 → +11.7%**.
5. **Single-league.** 25 of 29 rows are Argentina Primera Division (+7.795u), 3 Brazil Serie A
   (+3.450u, 3/3 wins), 1 Japan (−1.0u). Two thirds of the profit is 3 Brazilian bets and a
   25-bet Argentine sample.

And the tier ordering is **non-monotone**, which is what you expect if the tier is noise:
new_format BTTS **VALUABLE +27.4% (n=26)**, **SNIPER +35.3% (n=29)**, **MARKSMAN −0.3% (n=13)**.
MARKSMAN sits between the other two by construction and is the worst by outcome.

## 8. Killing the +18.1u side/BTTS track

1. **Chronological split destroys it.** H1 (2026-08-09..08-29) n=73 → **+22.45u, ROI +30.8%,
   win 71.2%**. H2 (2026-08-30..09-09) n=74 → **−4.35u, ROI −5.9%, win 48.6%**. The entire
   headline is three weeks in August; the three weeks since are negative.
2. **Settlement is selective.** 107 of 254 rows never settle. Broken down by league, the settled
   column is **empty** for La Liga 2 (23 rows), Ligue 2 (13), League One (6), League Two (6),
   Sweden (3), Ireland (3), Norway (2), Denmark (1) — **57 rows in leagues where results are never
   filled in**, and those are the standard-format second divisions the system actually targets for
   real money. `over35` has 5 rows and **0** settled: a market that cannot be graded at all.
   96 of 147 settled rows (65%) are Argentina Primera Division. The `+18.1u` is an Argentine number
   wearing a system-wide label.
3. **CLV cannot arbitrate.** 9 of 135 rows carry a BTTS `closing_odds` of **6.00–8.00** against a bet
   price of 1.97–2.50 (`clv_pct` down to −68.75). A BTTS market does not close at 8.00; those are
   cross-market or cross-line mismatches. Until they are fixed, side-market CLV is unusable in either
   direction — including as evidence *for* the track.
4. **Standard-format contribution is ~zero**: btts VALUABLE +1.875u (n=16), btts MARKSMAN −1.03u
   (n=3), btts SNIPER −1.00u (n=1), over15 SNIPER −1.00u (n=1).

## 9. Killing the remaining bets_ledger cells

new_format pool, 286 post-cutoff settled rows (ROI −3.06%), against selectors that use **no model
information**:

| selector | n | P/L | ROI |
|---|---|---|---|
| V9 STAKED (SNIPER+MARKSMAN) | 142 | +0.98 | **+0.69%** |
| V9 MARKSMAN only | 87 | +2.14 | +2.46% |
| V9 SNIPER only | 55 | −1.16 | −2.11% |
| V9 VALUABLE (not staked) | 144 | −9.72 | −6.75% |
| PLACEBO all rows | 286 | −8.74 | −3.06% |
| PLACEBO always UNDER | 199 | −4.90 | −2.46% |
| PLACEBO longshot side (odds ≥ 2.0) | 245 | −6.87 | −2.80% |
| PLACEBO always OVER | 87 | −3.84 | −4.41% |
| PLACEBO favourite side (odds < 2.0) | 41 | −1.87 | −4.56% |

Random 142-bet subsets of the same pool: mean ROI −3.04%, 2.5–97.5% band **[−16.51%, +10.56%]**,
`P(random ≥ +0.69%) = 0.294`. The staked selection sits comfortably inside the noise band; every
placebo selector lands in a 2.1pp range and the staked set beats the pool by 3.7pp against a ±13pp
sampling band.

Tier-label permutation across the whole post-cutoff settled pool (20,000 draws):
`P(some cell with n≥40 reaches ROI ≥ +2.46%) = **0.6518**`.

`new_format MARKSMAN +2.46%` specifically: H1 (08-15..08-29) n=43 **+7.09%**, H2 (08-29..09-08) n=44
**−2.07%**; drop top 1 winner → **+0.26%**, top 2 → −1.92%, top 3 → **−4.11%**.

`new_format over15 SNIPER` (the +2.2% cell) is n=52 → +3.54u → **+6.8%** in the current file, but
it lives in the same side ledger whose second half is −5.9% and whose settlement is Argentine.

## 10. Confirmations of the seed

Verified this run, no dispute:

* `v9/output/backtest_metrics_history.json` contains exactly **4 entries**, keys
  `2026-05-21_standard`, `2026-05-21_newformat`, `2026-06-17_standard`, `2026-06-17_newformat`.
  There is no record of any retrain since 2026-06-17.
* All-live-settled P/L is **−68.75u over 788 bets** in the current file (seed: −91.63u over 1,159
  settled — the seed's figure includes the `source=backtest` rows or an earlier file state; the
  `live` subset is what matters and it is negative either way).
* The seed's uncorrected placebo table reproduces to three decimals: mean reversion 0.9960 (seed
  0.995), fixed anchor 0.7523 (0.753), shuffled residual 0.7106 (0.711), v9_residual 0.7034 (0.703),
  market-only 0.5048. The battery was run correctly; its **input** was broken.

---

## RECOMMENDATIONS

Ordered by evidence, not by appeal.

1. **Fix `_asof` / `_asof_col` in `v11_momentum_control.py` (HOURS) and re-run everything downstream.**
   Carry the left index through the merge (`left.reset_index()` → `out.set_index("_orig")`). Then
   delete `v11_momentum_control.csv`, `v11_momentum_roles.csv` and any report quoting them, and
   re-derive. Until this is done, no v11 momentum number should appear in any decision.
   This is a bug fix in v11, which is not frozen.
2. **Re-audit `src/movement.py`'s 57.9% headline for the same class of error.** It does not contain
   this bug, but it was never validated against a corrected momentum control, and the corrected
   dataset has only 341 fixtures with any observable price movement.
3. **Treat the CLV contrast as the live decision, not the ROI.** Staked-vs-unstaked CLV is
   −2.139pp [−3.584, −0.653]. That is the one result with a CI excluding zero, and it says the tier
   is anti-predictive. Under the v9 freeze the correct response is not a threshold change but to
   stop staking on tier until the contrast reverses — i.e. move standard O/U to paper, which is a
   staking decision and not a code change.
4. **Reconcile `predict.yml`'s env block with `config.py` (HOURS, bug-fix class).** Three lines in a
   workflow silently override a documented backtest calibration. Whatever the intended values are,
   they must live in one place, and the `config.py` comments that assert +53.5% / +45.2% / +21.4%
   per-league ROIs must be marked as not-in-force.
5. **Do not run `fix_ledger_tiers.py` again.** It promotes on notification, forces MARKSMAN
   regardless of edge, and calls `_base_tier` with today's thresholds against a historical edge.
   If the send record is worth keeping, add a separate `sent_as_tier` column at send time; never
   overwrite `signal_tier`.
6. **Fix side-market closing-odds capture before any side/BTTS conclusion (HOURS).** Nine rows with
   BTTS closes at 6.00–8.00 is a market/line mismatch, and it currently biases side CLV downward by
   an unknown amount.
7. **Fix side-market settlement coverage (DAYS).** Four target leagues have zero settled rows.
   Any ROI computed on that ledger is a survivorship number until this is closed.
8. **Wire `v10/src/models/registry.py::evaluate_gate()` and commit `backtest_metrics_history.json`
   from the runner (HOURS).** Confirmed: nothing calls the gate and the metrics file dies on the
   runner. This is the cheapest structural fix in the system.

## WHAT NOT TO BUILD

* **Do not re-tune any threshold on this data.** Invariant 6, and the numbers make it pointless:
  Spearman(edge, pnl) = −0.005 over 184 bets, and the ≥14% bucket is −10.2%. There is no threshold
  that separates the winners here because the ordering variable does not order.
* **Do not build a "fix the drift guard" change.** The drift-manufactured bets are the *better* half
  (−28.7% vs −35.8% standard; +6.5% vs −4.6% new_format). Adding an edge floor to
  `VALUABLE → MARKSMAN` would remove the less-bad bets. n=19/20, so it is not evidence for the
  opposite either — it is evidence the intervention is unmotivated.
* **Do not chase the BTTS SNIPER cell into a strategy.** Permutation P=0.204, binomial p=0.075,
  25/29 one league, second half +5.4%. n=29 is below the n<50 bar; this is not a candidate.
* **Do not add more placebo variants to the battery until the join is fixed.** Nine variants scored
  against a scrambled target is nine wrong answers. My extension added market midpoint, league
  baseline and favourite bias plus paired clustered CIs — all three are only meaningful post-fix.
* **Do not buy more market data to rescue the movement analysis.** The corrected series shows 85.9%
  of one-hour windows with **exactly zero** movement and a median of 3 distinct odds pairs per
  fixture. The constraint is not sample size, it is that `v11_p_market` is a step function.
  `book_odds_snapshots` (143,799 rows, 24 real books) is the right place to look for a genuine
  price series — but only 34.9% of groups have ≥3 books, so a consensus series is thinner than the
  row count suggests.
* **Do not read `v11_momentum_roles.csv` as a price-discovery result, ever.** WOWZA_OPPOSES_MARKET at
  99.6% toward and WOWZA_AGREES at 0.5% are two halves of `future = −prev`. They are not two market
  states.

## OPEN QUESTIONS

1. Does `src/movement.py`'s 57.9% toward-rate survive on the corrected 4,756-observation moved-rows
   sample? It uses a different join, so it is not automatically void — but it has never been checked
   against a series where 85.9% of windows are flat.
2. Why do moved rows cluster in 2026-08-17..08-26 when the snapshot range is 08-10..09-08? Either
   price capture degraded, or the ±60m tolerance pairing fails outside that window. Both are
   collection questions with a bearing on every forward-looking market claim.
3. `predict.yml`'s three threshold overrides: intentional (a deliberate widening for the
   data-gathering season) or inherited? The answer changes whether §3 is a bug or a policy, and it is
   the difference between a fix and a documentation change.
4. Is the negative staked-CLV contrast stable when split by model track and by league, or is it
   carried by new_format (SNIPER −2.226, MARKSMAN −1.697) while standard is mildly positive
   (SNIPER +4.012 on n=4, MARKSMAN +0.586 on n=38)? n=4 is nothing; the new_format arm is where the
   n is and where the sign is negative.
5. `bets_ledger.csv` holds 4,115 `source=backtest` rows against 3,792 unique keys — **323
   duplicate-key rows** that `append_tips`'s dedup should have prevented. Harmless for the live
   analysis (I excluded them throughout) but it means some backtest table somewhere is
   double-counting.

---

## METHOD NOTES

* All ROI figures are flat-1u P/L over settled rows only; no Kelly, no compounding.
* Every bootstrap resamples **fixtures**, not rows, except where stated. The side ledger has at most
  2 rows per fixture (113 fixtures / 147 settled rows), so clustering there changes little; the v11
  snapshot data has ~32 rows per fixture, where it changes everything.
* Permutation tests permute the **tier label** within the natural strata and re-score the whole grid,
  so the reported P is already multiplicity-corrected over the cells examined.
* "Post-cutoff" means `match_date >= 2026-08-10` (`config.PERFORMANCE_CUTOFF_DATE`).
* Scripts were written to the session scratchpad and are not part of any repo. Nothing in `v9/`,
  `wowza-v11/` or any `data/` partition was modified; this report is the only file written.

# AGENT 13 — RED TEAM
## Attack on the twelve audit reports, 2026-09-10

Everything below was recomputed this run with `v9/.venv/Scripts/python.exe` (pandas 3.0.3).
Where I failed to break a finding, I say so.

---

## 0. Headline

**The seed's central result — "three predictors with zero football information beat the model,
mean reversion 0.995" — is a one-line indexing bug, and I reproduced both the bug and its
correction end to end.** But Agent 7, who found it, then overshot: the corrected v9 residual
predicts the direction of the next hour's price move at **0.5257, fixture-clustered CI
[0.5071, 0.5427], P(<=0.50) = 0.0015**, and in an orthogonalised regression `p_model` carries a
coefficient of **+0.0112, CI [+0.0036, +0.0195], P(<=0) = 0.005**. The estate's real,
sample-adequate, un-breakable finding is none of the placebo work: it is **Agent 6's
calibration gap** — claimed win probability 0.5430 vs realised 0.4066 on n=792 (**+13.64pp,
z = 7.81**) — which I attacked with a selection-bias simulation and could not dent.

---

## 1. Agent 7's `merge_asof` bug: CONFIRMED, and it voids the seed

`wowza-v11/scripts/v11_momentum_control.py:141,158` — `return out.sort_index()["p_at"]`.
`pd.merge_asof` returns a fresh `RangeIndex`, so values land in `target_ts` order on rows held
in `d`'s order.

Minimal repro (pandas 3.0.3): true `p_prev` = `[nan, 0.50, 0.51, nan, 0.80, 0.81]`, the code
produces `[nan, nan, 0.80, 0.50, 0.81, 0.51]`. `merge_asof preserves left index: False`.

Why the corruption is *perfectly* adversarial, which Agent 7 did not spell out:
`target_ts = snapshot_ts -/+ 60min` is a monotone transform, so `left.sort_values("target_ts")`
yields the **identical row order for the backward and the forward call**. Both `p_prev` and
`p_next` therefore come from the *same* wrong row. With 85.9% of one-hour windows flat,
`p_prev ~= p_next`, so `future_move === -prev_move` by construction.

Reproduced on `v11_shadow_snapshots.csv` (48,825 usable rows, 802 fixtures), toward-rates:

| variant | buggy (mine) | seed | corrected (mine) | Agent 7 |
|---|---|---|---|---|
| v9_residual | 0.7076 | 0.703 | **0.5257** | 0.5257 |
| fixed_anchor | 0.7553 | 0.753 | 0.5190 | 0.5185 |
| shuffled_residual | 0.7109 | 0.711 | 0.5085 | 0.5179 |
| mean_reversion | **0.9961** | 0.995 | 0.2528 | 0.2508 |
| corr(prev, future) | -0.9995 | — | -0.0294 | -0.9995 (buggy) |
| exact-zero forward move | 0.2% | — | **85.9%** | 85.9% |

`v11_placebo_table.csv` and every momentum / movement / role number derived from that script are
void. **PROVEN.**

### 1b. …but Agent 7 and Agent 11 overshoot in the other direction

Two attacks on the corrected battery.

**(a) The "placebo" is collinear with the treatment.** On the corrected moved-rows sample
(n=4,482, 339 fixtures): `corr(residual_pp, fixed_anchor) = +0.7667`, sign agreement **75.9%**.
That is arithmetic, not coincidence — `p_model_over` has sd 0.0492 against `v11_p_market`
sd 0.0765, so `residual === const - p_market === fixed_anchor`. A control 0.77-correlated with
the treatment cannot discriminate between them. Reporting "the fixed anchor ties v9" as evidence
of no skill is a **weak comparison**: the two are largely the same variable. The seed made the
same error at 0.753 vs 0.703, and Agent 7 inherited the framing while correcting the arithmetic.

**(b) The clean test was never run.** Orthogonalised, fixture-clustered OLS on the corrected
data, `future_move_pp ~ p_market + p_model` (n=4,482 moved rows, 1,000 cluster bootstraps):

```
p_market  -0.00916  CI [-0.01610, -0.00287]  P(<=0)=0.997
p_model   +0.01117  CI [+0.00362, +0.01950]  P(<=0)=0.005
```

`p_model` is not zero. It is *economically* nothing — its full 33.7 -> 68.0 output range buys
0.38pp of one-hour price movement — but "statistically indistinguishable from a shuffled
residual" (Agent 7 F6) and "+0.00089, p=0.232, a ~1,300x collapse" (Agent 11 F5) are both wrong.
Agent 11's is worse than downgraded: its coefficients are read straight out of
`v11_momentum_control.csv`, i.e. the corrupt output, so F5's headline number is an artifact of
the bug it never noticed. **DOWNGRADE Agent 7 F6 to SUPPORTED; DOWNGRADE Agent 11 F5 to VOID
pending recomputation.**

---

## 2. Agent 6's calibration gap survives my best attack — UPGRADE to the audit's lead finding

I hypothesised a winner's curse: selecting on `p_model - 1/odds` should make `p_model` look
overconfident on the selected set even if it were perfectly calibrated. **Simulation refutes my
own hypothesis.** Pooling 383 unique fixtures recovered from 60 committed `predictions.csv`
versions, drawing outcomes from `p_over25` (i.e. assuming perfect calibration), 400 iterations:

| selection | apparent overconfidence | Brier model vs 1/odds |
|---|---|---|
| edge >= 0.03 | **+0.12pp** | 0.24657 vs 0.25160 (model better) |
| edge >= 0.08 | **-0.45pp** | 0.24631 vs 0.25838 (model better) |

Selection on the *difference* is unbiased, because a high-edge row can be a low-`p_model` row at
a long price. So the observed gap is real, and it is the largest signal-to-noise ratio anywhere
in this audit:

| cut | n | claimed | realised | gap | z |
|---|---|---|---|---|---|
| all live settled | 792 | 0.5430 | 0.4066 | **+13.64pp** | **7.81** |
| post-cutoff | 420 | 0.5080 | 0.3952 | +11.28pp | 4.73 |
| post-cutoff standard | 130 | 0.5172 | 0.3538 | **+16.34pp** | 3.90 |
| post-cutoff new_format | 290 | 0.5039 | 0.4138 | +9.01pp | 3.11 |
| post-cutoff staked | 184 | 0.5199 | 0.3967 | +12.32pp | 3.42 |
| post-cutoff VALUABLE | 236 | 0.4987 | 0.3941 | +10.46pp | 3.29 |

Brier: model 0.2583 vs `1/odds` 0.2368 on the full set. Two things nobody said. The gap is **the
same size in the staked and the never-staked tier** (+12.3 vs +10.5pp), which is a cleaner proof
that the tier ladder carries no information than either Agent 7's CLV contrast or Agent 12's
correlation. And it is **larger on the standard track** — the one that takes real money — than
on new_format. **PROVEN. This, not the placebo battery, is the finding that should drive the
season.**

---

## 3. Agent 6 F3 is a look-ahead. Agent 4 F1 is right. Agent 11 F6 is deflated.

Four agents produced four incompatible execution numbers off the same table. I built the
counterfactual both ways — 323 settled live O/U bets joined to `book_odds_snapshots` (OU25),
decision set held fixed:

| method | n | entry >= best | mean shortfall | ROI delta |
|---|---|---|---|---|
| **contemporaneous** (best quote per book as of `generated_at`, forward-filled; median 8 books) | 221 | **44.3%** | +2.06% | **+1.99pp** |
| any-time pre-kickoff best (look-ahead) | 323 | 8.4% | +7.78% | **+6.51pp** |

- **Agent 4** reported 46.6% / +1.909% / **+2.03pp, CI [+1.41,+2.73]**. Replicates. **PROVEN.**
- **Agent 6 F3** reported 74.6% below best and **+4.35pp**, computed from "each book's LAST
  pre-kickoff quote" — which lands between my two rows, exactly where a partial look-ahead
  belongs. It prices a decision made at time *t* against quotes that existed only later.
  Agent 6 filed this as their own OPEN question and still tagged the finding PROVEN/HIGH and put
  the number in the headline. **DOWNGRADE to SPECULATIVE as an execution figure.**
- **Agent 11 F6** (+0.72pp/side today, and "predict.yml:163 overstates the reachable uplift by
  ~2.5x") is computed on the raw change-log as a panel. `v9/src/predict.py:199-204` drops any
  quote equal to the prior observation of the same (fixture, market, side, book) — confirmed in
  code — so raw groups have median 2 books while the real tip-time panel has median **8**.
  **DOWNGRADE by ~2.7x.** Agent 11's "overstates by 2.5x" is itself the change-log-as-panel
  error that Agent 4 F2 had already named.

**Invariant-3 warning nobody issued.** The +2pp is the largest measured effect in the audit and
it is *not* implementable in v9. `predict.py:136-139`
(`if pt == 2.5 and nm == "Over" and not ov25: ov25 = pr`) sets `odds`, which sets `edge_pct`,
which sets the tier of **every** bet. Changing it mid-season re-tiers the entire book and
destroys the prospective validation the freeze exists to produce. It is a strategy change
wearing a bug fix's clothes. Note also the code's own comment — *"Bookmakers are already ordered
by preference, so the 2.5 price still comes from the same book as before"* — is an assumption
both Agent 4's 46.6% and my 44.3% falsify. That falsification, staged in Pro, is the deliverable.

---

## 4. The CLV headlines are era-confounded. Agent 4 got it right; Agents 1 and 11 did not.

`bets_ledger.csv`, live settled rows carrying a closing price:

| window | n | mean CLV | median | ratio range | abs(clv)>25 | clv == 0 |
|---|---|---|---|---|---|---|
| all | 681 | **+12.275%** | 0.000 | 0.258-3.017 | 175 (25.7%) | 125 (18.4%) |
| **pre-cutoff (<2026-08-10)** | 276 | +30.333% | +12.960 | 0.258-3.017 | **174 (63.0%)** | 51 (18.5%) |
| **post-cutoff (>=2026-08-10)** | 405 | **-0.031%** | 0.000 | 0.816-1.419 | **1 (0.2%)** | 74 (18.3%) |
| July 2026 | 115 | +42.125% | +60.660 | — | 95 (82.6%) | 10 (8.7%) |
| September 2026 | 115 | -0.683% | 0.000 | 0.824-1.255 | 0 (0.0%) | 25 (21.7%) |

**174 of the 175 impossible rows are pre-cutoff.** Agent 1 F1 ("CLV is 50% fabricated, 25.7% of
rows physically impossible") and Agent 11 F1 ("contaminated ~70x in the flattering direction")
both describe a pool that is 41% July-and-earlier, and both are phrased as claims about the
*current* instrument — Agent 11's headline calls it "the estate's only pre-P&L edge KPI [is]
broken in its own favour". Agent 4 F3 reported precisely the era split (Jul +42.1, Aug +11.8,
Sep +0.1; verifiable era n=319, 100% in-range) and is the correct version. **DOWNGRADE Agent 1
F1 and Agent 11 F1** from "the KPI is broken" to: *the KPI was broken up to ~2026-08-10 and
reads clean since; delete the pre-cutoff series rather than repair it* — which is exactly
Agent 4's DO-NOT-BUILD.

The one defect that is **era-invariant** is the 18.3% of rows where `closing_odds == odds`
exactly: 18.5% pre-cutoff, 18.3% post. That is a different mechanism
(`update_results.py:330` `snapshots[-1]` on a single-snapshot fixture) from the July blow-up,
and only the July one has gone away by itself. That is the fix worth scoping, and it is a
measurement bug, so it is invariant-3 legal.

---

## 5. Agent 7 F2 — "the only CI excluding zero" — reverses sign on the real-money track

Replicated unadjusted on post-cutoff settled rows with CLV (n=405, 401 fixtures): staked
(SNIPER+MARKSMAN) mean **-1.227%** vs VALUABLE **+0.907%**, diff **-2.135pp**, fixture-clustered
CI [-3.584, -0.653], P(>=0) = 0.0016. Agent 7's number is exact.

Then I controlled it:

```
OLS (excluding the 74 mechanical clv==0 rows, n=331), fixture-clustered bootstrap:
  side_UNDER          -2.995
  odds                -2.125   per unit of decimal odds
  model_type_standard -0.123
  staked              -1.712   CI [-3.544, +0.158]   P(>=0)=0.034
```

CLV measured in odds-percent is strongly price-dependent, and the staked tiers sit at longer
prices (SNIPER mean 2.527 vs VALUABLE 2.252). Adjusting for price and side moves the 95%
interval across zero. Stratified, the sign **flips**:

| stratum | staked | VALUABLE | diff |
|---|---|---|---|
| UNDER | -2.407 (n=133) | +0.549 (n=139) | **-2.955** |
| OVER | +2.258 (n=45) | +1.474 (n=88) | **+0.785** |
| new_format | -1.888 (n=136) | +1.411 (n=139) | **-3.299** |
| **standard** | **+0.912 (n=42)** | +0.112 (n=88) | **+0.800** |

49 of 53 SNIPER rows are UNDER and 49 of 53 are new_format. The finding is therefore
*"new-format UNDER tips take prices that drift against us"*, not *"the staked tier is adversely
selected"* — and pooling the two tracks to reach the headline breaches **invariant 1**. Agent 7
raised exactly this as an OPEN question and then headlined the pooled number anyway.
**DOWNGRADE PROVEN/CRITICAL -> SUPPORTED/HIGH, new_format-only.**

**And it is not independent of Agent 12 F1.** `corr(edge_pct, clv_pct) = -0.2011` replicates
(Agent 12: -0.2022); partial correlation controlling odds/side/model_type is **-0.1437**; within
strata it is +0.117 (OVER/standard, n=49), -0.241, -0.243, -0.186. Tier is a step function of
edge, so Agents 7 and 12 measured one phenomenon twice. The audit currently reads as two
independent CRITICAL confirmations of adverse selection. It is one, at about -0.14.

---

## 6. Agent 1 F3: I refuted it, then refuted myself. It is right, and it is standard-only.

First pass, on today's `predictions.csv` (standard, n=77): sd(p_over25) = **0.0534**,
var_model/var_edge = **0.823**, corr(edge, p_model) = **+0.215** — against Agent 1's 0.0227 /
0.14 / -0.285. That looked like a one-board artifact on their side.

It was a one-board artifact on **mine**. I recovered 60 committed versions of
`output/predictions.csv` from git (2026-09-01 -> 2026-09-10); 0.0534 is the **maximum of 60**:

| standard, median of 60 boards | value | p10-p90 |
|---|---|---|
| sd(p_model) | **0.0230** | 0.0221-0.0269 |
| sd(1/odds) | 0.0649 | 0.0624-0.0696 |
| var_model / var_edge | **0.159** | 0.144-0.189 |
| corr(edge, -1/odds) | **+0.933** | 0.907-0.950 |
| corr(edge, p_model) | -0.057 | -0.291 to +0.190 |

**This answers Agent 1's own OPEN question: the compression is the steady state, not a
transient** — 36 of 60 boards sit at sd <= 0.025 and none exceeds 0.054. Two qualifications:

- corr(edge, p_model) is negative on only **31 of 60** boards. Agent 1's -0.285 is a p10 tail
  value; "corr(edge, p_model) is NEGATIVE" is not a stable property. The stable claims are the
  variance share (~16%) and corr(edge, -1/odds) (~+0.93).
- **New-format is a different animal**: median var_model/var_edge = **1.1246** [1.03, 1.23],
  sd(p_model) 0.0714, corr(edge, p_model) -0.111 (negative on 56/59 boards). On new-format the
  model contributes *more* variance than the edge itself.

Since **79% of live settled bets are new_format**, Agent 3 F2 ("edge is structurally an
anti-signal: it ranks by longest price") and Agent 1 F3 ("the staked edge is the reciprocal of
the price") are **true on the standard track and not established on the track that places most
of the bets**. Both are tagged CRITICAL without that split. Agent 3's own version, computed on
4,278 backtest rows rather than one board, is the more defensible statement of the same effect
and should be the one that survives.

---

## 7. Agent 2: four downgrades

**F1 (predict.yml band, CRITICAL).** The numbers replicate to the decimal —
[0.03,0.08) n=3,419 **-6.49%** CI [-10.16,-2.83]; [0.08,0.14) n=1,537 -5.36% CI [-11.34,+0.62].
But the rows Agent 2 omitted change the conclusion:

```
[0.00,0.03)  n=3047   -8.76%  CI[-12.40, -5.13]   <- also excludes zero, and WORSE
[0.03,0.08)  n=3419   -6.49%  CI[-10.16, -2.83]
[0.08,0.14)  n=1537   -5.36%  CI[-11.34, +0.62]
[0.14,0.20)  n= 319   -3.09%  CI[-17.80,+11.62]
[0.20,1.00)  n=  38  -14.58%  CI[-56.72,+27.56]
```

Every band is negative and the sequence is non-monotone (-8.76, -6.49, -5.36, -3.09, -14.58).
The table says *the entire edge axis is negative in this backtest*, not *the widened band is the
cause of the losses*. Restoring the 0.14 floor moves the book into bands measuring -3.09%
(n=319) and -14.58% (n=38). **DOWNGRADE the causal claim in the headline; the measurement
stands.** Note also that these prices are `AvgC>2.5` — the closing *average* (`data_loader.py:49`)
— so the band ROIs are struck at a single-book-grade overround (median 6.28% excess) while
production takes a best-of-panel price. Bands measured on the wrong price cannot attribute live
P&L either way.

**F3 (Pro settlements "95.7% duplicate, 23.0x inflation") — the evidence is wrong.** Recomputed
on the current store (52 files, 131,689 rows): deduping on Agent 2's key
`(fixture_key, market, result)` reproduces their figure (**95.80%**), but that key discards
`side`, `signal_tier`, `odds`, `closing_odds` and `clv_pct`. Deduping on the **full row**
excluding ingest metadata gives **4.86% duplicates**. The store holds ~25.8 *revisions* per
(fixture_key, market, side) — 5,107 distinct bets, 1,065 settled fixtures — which is what an
append-only store is for. Their OPEN question also resolves negative:
`grep settlements v10/src/models/registry.py` returns **no hits**, so `evaluate_gate` never
reads that table and the "clv_n inflates 23x, every CI narrows by ~4.8x" warning is misstated.
The practical advice (dedup at the `read()` boundary) is unchanged; the "23x" number should not
be quoted again.

**F5/F6 (batch-noise ratchet, "+7.1pp of pure noise") — magnitude ~3x overstated.** F5's
sd = 2.6pp comes from scoring a fixture **alone**, a batch of one where the median *is* the row,
so nothing is imputed at all — a counterfactual production never runs. The realistic quantity,
measured across the 60 committed boards:

| track | fixtures seen >=5x | run-to-run sd of p_over25 | median lifetime range | p90 |
|---|---|---|---|---|
| standard | 162 | **0.0101** (median 0.0084) | **4.06pp** | 8.00pp |
| new_format | 220 | 0.0083 (median 0.0068) | 2.68pp | 7.22pp |

F6's `E[max] = mu + sd*sqrt(2 ln 40)` additionally assumes 40 **independent** draws; consecutive
predict runs score the same board minutes apart. With the measured sd = 1.01pp the formula gives
+2.7pp, and the observed median lifetime range of 4.06pp implies max - mean ~= 2pp. **The
mechanism is real; "+7.1pp against an 8pp floor" is not.** DOWNGRADE F5 and F6 to MEDIUM.

**F4 (over15 backtest 100% fabricated) — CONFIRMED and unweakened.** `odds_over15 == 1.40` on
12,186/12,187 rows (99.99%), `nunique = 2`, against `odds_over25` 0.14%, `odds_btts` 0.05%,
`odds_over35` 0.00% at that value. This is Agent 2's strongest finding and the only one of the
four I could not dent.

---

## 8. Agent 5 replicates exactly. Agent 12 F14 must not be used to de-fund it.

Recomputed per-fixture T-30m coverage on `book_odds_snapshots` (785 timestamped fixtures):

| window (kickoff) | n_fx | T-30m | T-1h | median last obs | Agent 5's T-30m |
|---|---|---|---|---|---|
| A 08-19..08-26 | 175 | **84.6%** | 91.4% | 11 min | 84.7% |
| C 08-31..09-06 | 227 | **25.1%** | 33.9% | 78 min | 29.4% |
| D 09-07..09-09 | 34 | 8.8% | 8.8% | 101 min | 8.8% |

**Agent 5 F1 is PROVEN.** Agent 12 F14 ("REFUTES SEED: near-kickoff coverage is ~2x better than
stated... Downgrades the always-on collector to MEDIUM") has two problems. First, units: their
figures (T-1h 40.2%, T-30m 32.7%, T-10m 17.4%) match my **per-fixture** coverage
(40.9 / 33.2 / 17.7), not observation shares — the true observation shares are
**6.0% / 3.6% / 1.5%** — yet they are presented as "92,746 timestamped obs ... inside T-1h
40.2%". Second and worse, they pooled the whole 08-19 -> 09-10 range, which straddles the
schedule cut Agent 5 dated to 08-27..08-30. A pooled 32.7% describes neither an 84.6% regime nor
a 25.1% one, and **the current regime is worse than the seed's figure for the same metric**.
**DOWNGRADE Agent 12 F14; do not let it de-prioritise the collector.**

Two things Agents 4 and 12 got right and the seed did not: post-kickoff observation share is
**0.0000** (seed: 5.4%), and BTTS `kickoff_utc` is **100% null** while OU15/25/35 are 0% null.

---

## 9. Agent 6 F1 is an argument from insufficient power

The Monte-Carlo null is arithmetically fine (H0 mean -37.60u, sd 31.9, observed -68.75u,
p = 0.164 at overround 1.05, 0.294 at 1.07). But at n=788 with per-bet sd ~= 1.13 the standard
error is ~4pp, so the same test also cannot reject *modest positive* skill. "Statistically
indistinguishable from betting the same prices at random and paying the spread" is a statement
about the width of the interval, not about skill, and it is quoted in the headline as the
latter. The verdict Agent 6 wanted is carried by their own **F5** at z = 3 to 8 (section 2
above), not by a p = 0.16. **DOWNGRADE F1 from CRITICAL to a power note; promote F5 to the
audit's lead finding.**

---

## 10. Verified without qualification — stop re-litigating these

- `predict.yml:188-192`: `REQUIRE_FORM_DATA "0"`, `REQUIRE_FORM_DATA_UNTIL "2026-09-15"`,
  `LEAGUE_SNIPER_CAP "0.12"`, `MARKSMAN_THRESHOLD "0.08"`, `VALUABLE_THRESHOLD "0.03"` —
  verbatim. Agents 2, 3, 6, 7, 10, 11 and 12 converged independently. The seed's open question
  is closed and the seed's "everything else falls back to global .14" framing is dead. Eight
  agents also independently found `models/best_params_standard.json` read ahead of config at
  `src/betting.py:154-157`; that is the most reliable consensus in the audit.
- `output/ht_ledger.csv` does not exist. Current board: `p_ht_over05` in [0.6324, 0.7302]
  sd 0.0218 (needs >=0.75 or <=0.30 -> 0 rows); `p_ht_over15` in [0.3271, 0.3687] sd 0.0094
  (needs >=0.60 or <=0.25 -> 0 rows). Agent 1 F6 confirmed on a fresh board.
- `player_tips.csv`: `n_games` mean 5.0, **sd 0.0**, min = max = 5 over 863 rows. Agent 8 F1
  confirmed.
- `v10/tests/`: 6 of 10 files contain zero `def test_` / `class Test` (`test_market`,
  `test_validation`, `test_registry_gates`, `test_season_store`, `test_imputers_calibration`,
  `test_drift_experiment`); no `conftest.py`, `pytest.ini`, `pyproject.toml` or `setup.cfg`.
  18 collectable tests from 3 files. Agent 11 F7 confirmed exactly.
- `src/data_loader.py:49-52` `_OVER_COLS = ["AvgC>2.5", "MaxC>2.5", "B365C>2.5", "PC>2.5", ...]`
  with `_pick_odds` returning the first column at >10% coverage. Agent 10 F3 confirmed:
  Pinnacle closing is on disk and structurally unreachable.
- `src/predict.py:199-204` is a change-log filter (`_bn[_bn["odds"].ne(_prev)]`). Agent 4 F2
  confirmed; the seed's panel statistics (median 2 books, 34.9% with >=3) are an artifact of
  reading a change-log as a panel, and every downstream claim built on them inherits it.

---

## 11. Recommendations that would waste money

1. **Agent 5's always-on worker sold as "unblocks the promotion gate."** The gate wants
   `mean_clv_pct > 0` and `clv_n >= 150`; measured post-cutoff CLV is **-0.031% on n=405**. A
   fresher close makes the gate's answer honest, and the honest answer is *reject* — Agent 12 F7
   says so explicitly. $0-5/month is cheap and the instrumentation case is sound, so fund it as
   instrumentation and expect no revenue. Agent 5's own PLAUSIBLE caveat (recovered yield may
   land between the 60.3% and the 27.3% regimes) is the load-bearing assumption in their ROI
   arithmetic, and it is unmeasured.
2. **Agent 10's The Odds API $119 plan.** Both the price and the historical-snapshot endpoint
   rest on a single un-corroborated vendor-page read (WebSearch was unavailable to them, and to
   me this run), and their own credit estimate carries a stated factor-of-two error bar. Do not
   authorise a plan change on that evidence; a one-hour probe of the endpoint is the next step,
   not a purchase. The claim also contradicts a CLAUDE.md conclusion established at ~830 calls
   of real cost, so the bar should be higher than one web page, not lower.
3. **Any spend justified by the side-market +18.10u.** Agents 6, 7, 9 and 12 independently
   found: bootstrap CI [-3.1%, +27.7%] spanning zero at n=147; 96 of 147 rows in one Argentine
   league; 88 of 147 in one market; tier ordering inverted (VALUABLE +21.4% > SNIPER +14.2% >
   MARKSMAN -12.2%); chronological halves +30.8% then -5.9%; four target leagues with zero
   settled rows; and Agent 9 additionally proving the "all source=live" line means "not
   backtest", not "in-play". Four agents converging on noise is the audit's most reliable
   negative consensus.
4. **More API-Football credits.** Agent 12 F11 measures 15.0% of 75,000/day mean utilisation,
   max ever 56.8%. The seed's "3%" is a partial-day artifact. Either way there is nothing to buy.
5. **A fifth threshold optimiser, or "better regularisation" for the two that exist.** Agent 11
   F4 is the finding to act on: `best_params_standard.json` moved Bundesliga 2's sniper threshold
   0.04 -> 0.19 in seven days and flipped `approved` in 3 of 7 leagues. The intervention is a
   deletion, not an improvement.

---

## 12. Invariant violations if implemented as written

**Invariant 3 (v9 frozen).**

- **Agent 4's `predict.py:136-139` best-price change** — the audit's largest measured effect, and
  it re-tiers every bet in flight (section 3). Belongs in Pro. Agent 4 never says where.
- **Agent 10's `_OVER_COLS` reorder to `PC>2.5`** — `odds_over25` feeds `bookmaker_overround`,
  which is a *model feature* (`src/model.py:88`), plus every backtest price. Not a config fix.
- **Agent 2's implied "restore MARKSMAN to 0.14"** — an env change to a live decision rule, and
  section 7 shows the bands above the floor are negative too, so it is unmotivated as well as
  frozen.
- **Agent 6's list of "the two items that ARE permissible in v9" is half wrong.** The missing
  kickoff filter in `update_results.py:329` is a genuine bug fix — it corrupts a *measurement*,
  not a decision. The asymmetric drift guard at `src/betting.py:212` is a **tier rule**, and
  changing it changes which bets get staked. That is invariant 3; and Agents 7 and 12 both
  measured that the drift-promoted rows are the *better* half (-28.7% vs -35.8% standard;
  -13.4% vs -49.9% overall), so the change is negative-EV on the only evidence available.
- Agents 3 and 9 propose `live_scanner` constant changes (`lam_total/2 -> 0.447`, a
  `MIN_FAIR_UNDER` ceiling, SOT-null handling) and correctly route them to Pro. That is the
  pattern the others should follow.

**Invariant 6 (no retrospective tuning).** No agent proposes an explicit re-tune — all twelve
list it DO-NOT-BUILD, which is the audit's best collective behaviour. But two retrospective
loops are **live in production right now**: `models/best_params_standard.json`, read ahead of
config at `src/betting.py:154-157` and rewritten by `optimize_standard_thresholds` on every
backtest; and `optimize_side_market_thresholds` (`src/backtest.py:422-486`) with no train/test
split at all. Unwiring them is a deletion and is invariant-6-clean. Only Agent 11 says this
explicitly; the others document the violation and then leave it running.

**Invariant 1 (tracks never mix).** Breached in the *analysis*, not the code: by the seed's
-91.63u headline, by Agent 7 F2 (section 5 — the sign flips between tracks), and by Agent 1 F3
/ Agent 3 F2 (section 6 — the variance decomposition inverts between tracks).

---

## 13. What I could not break

Listed so the next reader does not spend budget here. Agent 6 F5 (the calibration gap — I
attacked it with a simulation and ended up strengthening it). Agent 2 F4 (over15 constant 1.40).
Agent 2 F15 (the *refutation* of leakage: `shift(1)` before `rolling`, `expanding().shift(1)`
throughout — correct, and Agent 3 independently reached the same verdict). Agent 5 F1 (the
coverage collapse). Agent 4 F1 (the contemporaneous best price) and Agent 4 F2 (change-log vs
panel). Agent 8 F1 (`n_prev_games` train/serve skew). Agent 11 F7 (uncollectable tests).
Agent 1 F6 (the HT model is dead end to end). Agent 1 F3 on the standard track — now confirmed
as the steady state across 60 boards rather than one.

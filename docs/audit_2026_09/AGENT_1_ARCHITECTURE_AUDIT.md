# AGENT 1 — REPOSITORY ARCHITECTURE AUDIT
**Date:** 2026-09-10 · **Scope:** v9 (HEAD `05ddbe65`), v10/wowzaV9-Pro, wowza-v11
**Method:** read-only. Every number below was computed this session with `v9/.venv/Scripts/python.exe`
(pandas 3.0.3) or read at the cited `file:line`. Nothing was committed, edited or fetched.

---

## HEADLINE

**CLV — the one metric this entire architecture gates real money on — is half fabricated, and once
cleaned it is statistically zero.** `bets_ledger.csv` reports a mean `clv_pct` of **+12.28%** over 681
live rows. 25.7% of those rows are physically impossible (|clv| > 25%, max **+287.1%**) and 24.7% of
the survivors have `closing_odds` set exactly equal to the entry odds — an invented number, not a
measurement. What is left is **n=381, mean +0.162%, 95% CI [−0.68%, +1.00%]**. The +12.28% headline
is an artefact of a name-join in `update_results.py:320-327` that never compares the fixture date.

Everything downstream inherits this. v11's `BET` gate (`MIN_CLV_N=150`, positive) reads this column;
on the contaminated version new-format would have looked strongly positive with n=521 — the corruption
points **toward** betting. And on the cleaned version no league reaches 41 observations, so the gate is
unreachable for another **362 days** and every `PAPER` verdict this season is arithmetic, not judgement.

Second-order but equally structural: on the standard track — the only real-money market — the model is
a near-constant. `corr(edge, p_model) = −0.285`, `corr(edge, −1/odds) = +0.951`. The staked "edge" is
the reciprocal of the price. That is the v11 placebo verdict re-derived from the live board with no
backtest involved.

---

## FINDINGS TABLE

| # | Finding | Cat | Conf | Impact | Fix |
|---|---|---|---|---|---|
| 1 | CLV is 50% fabricated; cleaned mean is 0 (CI spans 0) | DATA_QUALITY | PROVEN | CRITICAL | DAYS |
| 2 | v11 `BET` gate unreachable (362 more days) and was aimed at the corrupt number | ARCHITECTURE | PROVEN | CRITICAL | DAYS |
| 3 | Staked edge ≈ −1/odds, not the model (`corr = +0.951` vs `−0.285`) | STATISTICAL | PROVEN | CRITICAL | WEEKS |
| 4 | 46.2% of ledger tiers cannot be reproduced from the recorded edge; no config provenance | PROCESS | PROVEN | HIGH | DAYS |
| 5 | `best_params_standard.json` is retrospective tuning in production; ceiling disabled where we stake | STATISTICAL | PROVEN | HIGH | HOURS |
| 6 | HT model is dead end-to-end: 0 of 77 rows can cross any threshold; `ht_ledger.csv` never existed | ARCHITECTURE | PROVEN | HIGH | HOURS |
| 7 | Weekly retrain runs no evaluation at all; `retrain.py` is orphaned from CI | PROCESS | PROVEN | HIGH | DAYS |
| 8 | v11 placebo battery + chronological folds computed hourly, never persisted | PROCESS | PROVEN | HIGH | HOURS |
| 9 | v11 has persisted nothing for ~58h; delivery rate does not explain it | PROCESS | SUPPORTED | HIGH | HOURS |
| 10 | `side_bets_ledger` is the predict path (not live); `side` col 100% null; CLV −2.51% | DATA_QUALITY | PROVEN | HIGH | HOURS |
| 11 | `bets_ledger.csv` whole-file rewritten + force-resolved by 3 ungrouped workflows | EXECUTION | PROVEN | HIGH | DAYS |
| 12 | Push epilogue copy-pasted ~30× in 3 divergent variants; v10/v11 lack `-X theirs` | ARCHITECTURE | PROVEN | MEDIUM | DAYS |
| 13 | `league_roi_config.json` assembled from a mix of fresh and 30-day-stale inputs | DATA_QUALITY | SUPPORTED | MEDIUM | HOURS |
| 14 | Cron-string branching still live in `player_props.yml`; `PROPS_SCHEDULE` never set | PROCESS | PROVEN | MEDIUM | HOURS |
| 15 | Live scanner notifies nothing (`LIVE_ALERTS: ''`), 16 runs/day | ARCHITECTURE | PROVEN | MEDIUM | HOURS |
| 16 | `CLAUDE.md` cron table + invariant 7 both factually wrong | PROCESS | PROVEN | MEDIUM | HOURS |
| 17 | 10 live tips in leagues outside `ENABLED_LEAGUES` (invariant 7 leak) | DATA_QUALITY | PROVEN | LOW | HOURS |

---

## 1. CLV IS FABRICATED — PROVEN — CRITICAL

`output/bets_ledger.csv`, `source == live`:

```
rows with clv_pct                        681
mean clv_pct                          +12.275 %
median clv_pct                         +0.000 %
% positive                               47.3 %
closing_odds EXACTLY == entry odds        125  (18.4 %)
clv_pct == 0 exactly                      125  (18.4 %)
|clv_pct| > 25 %                          175  (25.7 %)
clv_pct > +100 %                           22
max clv_pct                            +287.1 %
```

A distribution with median exactly 0.000 and mean +12.3% is not a price series. Split by track and
side, the impossibility is explicit:

```
new_format OVER   n=150  mean clv −13.80 %
new_format UNDER  n=371  mean clv +27.87 %      <-- +41.7 pp gap on two sides of one market
standard   OVER   n= 52  mean clv  +2.37 %
standard   UNDER  n=105  mean clv  −0.30 %
```

A +41.7 pp asymmetry between OVER and UNDER inside the same model track and the same market is a
measurement error, not a market. And if new-format really beat the close by 27.9% on 371 selections,
its ROI would be enormous; measured ROI on those same rows is **−3.65%**.

**Mechanism A — the join ignores the date.** `update_results.py:307-334`, `_closing_odds_json`:

```python
key = f"{home} vs {away} | {match_date}"
snapshots = history.get(key, [])
if not snapshots:
    norm_key = next((k for k in history
                     if _norm(k.split(" vs ")[0]) == _norm(home)
                     and _norm(k.split(" vs ")[1].split(" | ")[0]) == _norm(away)), None)
```

The fallback compares the home name and the away name and **never compares the date** that is part of
the same key, then takes `next(...)` — the first arbitrary match in dict order. Two teams that meet
twice a season silently share a closing price. Directly visible in the ledger:

```
league    home                  away              side  odds  close   clv_pct
USA MLS   San Jose Earthquakes  Orlando City SC   UNDER 3.35  1.44   +132.64
USA MLS   New York Red Bulls    Orlando City SC   UNDER 3.35  1.44   +132.64
```

Two different fixtures, identical entry and identical close to the cent. The close is not
fixture-specific. Note also that 1/3.35 + 1/1.44 = 0.99 — the "close" is the complementary side of the
market, so for these rows both the fixture and the side are wrong.

**Mechanism B — the "close" is often the entry.** Same function: `last = snapshots[-1]` with no
kickoff filter, and `src/drift.py` stores **price changes only**. A fixture whose price never moved has
exactly one snapshot, so `snapshots[-1]` is the price we entered at → `closing_odds == odds` →
`clv_pct = 0.0`, written as a number. That is 125 rows and it violates invariant 9
(*"Write NaN, never an invented number"*) in the one column the architecture is gated on.

**What the evidence actually says once cleaned** (|clv| ≤ 25% and clv ≠ 0):

```
new_format  n=266  mean −0.098 %   95% CI [−1.156, +0.960]
standard    n=114  mean +0.806 %   95% CI [−0.522, +2.133]
ALL         n=381  mean +0.162 %   95% CI [−0.677, +1.000]
```

Both intervals span zero. Per the rules of engagement that reads **INSUFFICIENT_DATA — we do not know**.
It is not evidence of edge and it is not evidence of anti-edge. It is 136 days of collection that has
produced no usable CLV signal on either track.

---

## 2. THE v11 BET GATE IS UNREACHABLE, AND WAS AIMED AT THE CORRUPT NUMBER — PROVEN — CRITICAL

`wowza-v11/config.py:22` → `MIN_CLV_N = 150`. `wowza-v11/scripts/v11_shadow.py:202`:

```python
clv_ok = (rclv is not None and rclv > 0 and rclv_n is not None and rclv_n >= config.MIN_CLV_N)
```

fed by `_rolling_clv_stats(_load_v9("bets_ledger.csv"))` at `v11_shadow.py:357`.

**Credit where due:** `CLV_PLAUSIBLE_ABS = 25.0` (`v11_shadow.py:267`) rejects the |clv|>25% garbage —
on today's ledger it drops 175 of 681 rows (25.7%) and prints that it did. That defence works.

**What it does not catch:** the 125 fabricated zeros survive the filter (they are 24.7% of what remains)
because 0 is plausible. So `clean_n` overstates real observations by a third.

Simulating the gate exactly as written, per league, on today's ledger:

```
best-covered leagues (clean obs):  USA MLS 57 · Sweden Allsvenskan 38 · Argentina Primera 37
                                   Bundesliga 2 34 · La Liga 2 32 · China Super League 32
LEAGUES PASSING n>=150 AND mean>0:  none
```

After also removing the fabricated zeros, the best league is **USA MLS with 41 clean non-zero
observations in 136 days** — 0.30/day. Reaching 150 takes **362 more days**. Estate-wide the rate is
2.80 clean observations/day across 23 leagues.

Two consequences the chief scientist should hold onto:

1. **Every `PAPER` verdict v11 has issued is a bootstrap artefact, not a finding.** The gate cannot
   open regardless of what the model does, so `PAPER` carries no information about the edge.
2. **The failure mode was pointed the wrong way.** Before the plausibility filter existed, new-format
   had n=521 with mean +15.88% — comfortably past `MIN_CLV_N` and strongly positive. The corruption
   manufactured a **false authorisation to bet**, not a false refusal. That is the direction that costs
   money, and it survived only because someone independently added a 25% sanity cap.

---

## 3. THE STAKED EDGE IS THE RECIPROCAL OF THE PRICE — PROVEN — CRITICAL

Decomposed on the live board (`output/predictions.csv`, 184 fixtures, 151 columns):

```
market       n    std(p_model)  std(1/odds)  var_model/var_edge  corr(edge,p_model)  corr(edge,−1/odds)
OU2.5      184      0.0574        0.0902           0.696              −0.014              +0.771
BTTS       184      0.0154        0.0686           0.058              −0.192              +0.975
Over1.5     10      0.0233        0.0300           0.804              +0.260              +0.663
Over3.5     44      0.0601        0.0404           1.094              +0.765              +0.285
```

Restricted to the **standard track — the only market carrying real money** (n=77):

```
std(p_over25) = 0.0227      std(1/odds_over25) = 0.0707
model share of edge variance = 14 %
corr(edge, p_model)  = −0.285          <-- NEGATIVE
corr(edge, −1/odds)  = +0.951
```

The standard model's output spans 0.0227 in standard deviation across the entire board. The price spans
three times that. So `edge = p_model − 1/odds` is, to a correlation of 0.951, just `−1/odds`: the tier
ranks fixtures by how long the price is. And the model's own contribution is *negatively* correlated
with the resulting decision.

BTTS is the extreme case: the model contributes **5.8%** of edge variance and `corr(edge, −1/odds) =
+0.975`. A BTTS "edge" is the longest price on the board with a rounding error attached.

This is the same conclusion as the v11 placebo battery ("a fixed anchor beats the model by +5.0pp"),
reached from the opposite direction and with no backtest, no fold structure and no residual regression.
A model whose live output has σ=0.023 **is** a fixed anchor. The two results are one result.

I will be adversarial about my own number: n=77 is one board, not a season, and the compression could be
a transient of early-season feature sparsity. But `p_ht_over05` (σ=0.0142) and `p_btts` (σ=0.0154) show
the same signature on the same board, and the direction of `corr(edge, p_model)` is what matters, not
its magnitude. A follow-up on 30 days of committed `predictions.csv` from git history would settle it
and costs an hour.

---

## 4. ANSWERING THE OPEN QUESTION: `edge_pct` IS THE DECISION EDGE — PROVEN — HIGH

The brief asked whether the 6.11% median edge on staked standard MARKSMAN rows is the edge the decision
was made on, or a settlement-time artefact. **It is the decision edge. The tier is simply not a function
of it.** Three lines settle it:

- `src/ledger.py:198` — on first log: `"edge_pct": round(edge * 100, 2)` where
  `edge = float(row.get("best_edge", 0.0))` (`ledger.py:164`), i.e. the tip-time board value.
- `src/ledger.py:175-178` — on re-observation at a strictly higher tier, `signal_tier` **and**
  `edge_pct` are overwritten *together*. They can never drift apart within one config generation.
- `src/betting.py:423` — `df["signal_tier"] = adjusted`. `_apply_drift_adjustment` mutates the tier and
  **never touches `best_edge`**.

So a row can legitimately read `edge_pct = 6.11, signal_tier = MARKSMAN`. The tier is
`f(edge, league_thresholds, drift_signal)`, and the edge alone does not determine it.

### But the ledger is worse than "decoupled" — 46.2% of its tiers are unreproducible

I re-ran `_base_tier()` then `_apply_drift_adjustment()` on the recorded `edge_pct`, `league`, `side` and
`drift_signal` of all 210 live standard rows and compared to the recorded tier:

```
recorded \ today   AVOID  MARKSMAN  SNIPER  VALUABLE
MARKSMAN               9        28       1        16
SNIPER                 0         2       4         6
VALUABLE              58         4       1        81

MISMATCH: 97 of 210 = 46.2 %
```

Nine rows recorded MARKSMAN would today be **AVOID**. Six recorded SNIPER would be **VALUABLE**
(Bundesliga 2 at 11.58%, La Liga 2 at 13.31%, Belgian First Division A at 10.31%). The ledger's tier is
a *ratchet* (`_TIER_RANK`, `ledger.py:143`) over a threshold configuration that has been edited
repeatedly during the season, and `LEDGER_COLS` (`ledger.py:52-70`) carries **no config, threshold, git
or model provenance** — while `predictions.csv` does carry `git_sha`/`model_sha` via `src/provenance`
(`pipeline.py:299-300`).

**This bounds what the brief's own numbers can support.** The `n=38, ROI −36.3%, CI [−69%, −4%]` on
standard MARKSMAN pools decisions taken under at least two different rule sets. The loss is real. The
attribution to `MARKSMAN_THRESHOLD = 0.14` is not available from this file.

### And the mechanism is mostly not the drift hole

The brief attributes the sub-threshold MARKSMAN rows to the floorless `VALUABLE → MARKSMAN` hop.
Measured, on recorded MARKSMAN rows whose base tier today is VALUABLE and which only reach MARKSMAN via
that hop:

```
n = 16 of 54 recorded MARKSMAN  (30 %),  median edge 5.55 %
```

**30%, not 97%.** The drift hole is real and it is floorless (`betting.py:211-213`: no edge condition,
against `betting.py:208` which requires `best_edge >= DRIFT_UPGRADE_EDGE` for the upgrade one tier
higher). But the larger cause is finding 5.

Per-league detail on settled live standard SNIPER+MARKSMAN (n=46):

```
league                     tier      n  med_edge   min    max     pnl
Bundesliga 2               MARKSMAN  8    5.70    3.61  13.72   −3.23
Championship               MARKSMAN  7    5.58    3.36   9.12   −0.81
La Liga 2                  MARKSMAN 10    8.50    3.59  14.08   −6.30
League One                 MARKSMAN  6    8.19    3.26  11.43   −3.86
Serie B                    MARKSMAN  7    5.58    3.62  12.54   +2.04
La Liga 2                  SNIPER    2   11.91   10.51  13.31   +0.40
Belgian First Division A   SNIPER    1   10.31                  −1.00
Turkish Super Lig          SNIPER    1   13.52                  −1.00
```

Standard SNIPER across all 12 live rows: min 8.40%, **max 13.70%, 100% below 14%**. New-format SNIPER
for contrast: n=258, median 17.32%, max 42.88%. The two tracks' "SNIPER" labels describe different
things, which matters because they are pooled in the ledger headline.

---

## 5. RETROSPECTIVE TUNING IS IN PRODUCTION — PROVEN — HIGH

`v9/models/best_params_standard.json` (committed, last 2026-09-01), read by
`src/betting.py:124-137` and applied in `_base_tier` at `:154-157`:

```json
"Championship": {"sniper_th": 0.07, "marksman_th": 0.05, "roi_insample":  2.59, "bets_insample": 308, "roi_oos":  3.32, "bets_oos": 164, "approved": true},
"Serie B":      {"sniper_th": 0.12, "marksman_th": 0.10, "roi_insample": 45.67, "bets_insample":  52, "roi_oos": 17.02, "bets_oos": 100, "approved": true},
"La Liga 2":    {"sniper_th": 0.17, "marksman_th": 0.15, "roi_insample": 14.39, "bets_insample":  31, "roi_oos": −5.84, "bets_oos":  94, "approved": false},
"League One":   {"sniper_th": 0.14, "marksman_th": 0.12, "roi_insample":  4.11, "bets_insample":  36, "roi_oos": −59.0, "bets_oos":   7, "approved": false},
"League Two":   {"sniper_th": 0.07, "marksman_th": 0.05, "roi_insample": −1.33, "bets_insample": 175, "roi_oos": −19.15,"bets_oos":  54, "approved": false}
```

Three things, all readable off the file:

1. **`approved` is a function of `roi_oos`.** Every league with `roi_oos < 0` is `approved: false`;
   both leagues with `roi_oos > 0` are `approved: true`. Selecting on the out-of-sample result makes it
   in-sample. This is invariant 6 (*no retrospective tuning*) violated in the file that governs live
   tiering, not in a research notebook.
2. **`Serie B: roi_insample 45.67% on 52 bets`** is the threshold that was chosen by maximising it. A
   45.67% ROI on 52 bets is a textbook overfit; `n<250 does not justify a parameter change`, and this
   changed two.
3. **This is the real explanation of the sub-14% MARKSMAN rows.** For the Championship the effective
   `marksman_th` is **0.05** and `sniper_th` is **0.07** — by design, not by defect. A 5.58% edge
   Championship MARKSMAN is the system working as configured. `MARKSMAN_THRESHOLD = 0.14` is not the
   binding constant for the two leagues we most rely on.

**And the overconfidence guard is disabled exactly where we stake.** `betting.py:174-179`:

```python
if not has_per_league:
    ceiling = config.LEAGUE_EDGE_CEILING.get(league, config.EDGE_CEILING) ...
    if edge > ceiling: return "MARKSMAN"
```

`has_per_league` is True for any league in `LEAGUE_SNIPER_THRESHOLDS` or with an approved optimizer
entry — i.e. Championship, Serie B, La Liga 2, League One, League Two, Bundesliga 2, Ligue 2, Greek
Super League. `config.py:274` documents the ceiling as *"above 19% the model is overconfident (backtest
shows −20% ROI)"*. The guard therefore protects only the leagues we do not stake, and is switched off
for all eight we do. The justification in the comment — *"per-league thresholds are backtest-optimised
— no ceiling needed there"* — is the same in-sample optimisation the ceiling exists to distrust.

---

## 6. THE HT MODEL IS DEAD END TO END — PROVEN — HIGH

Two HT models are trained and committed weekly: `models/model_ht_over05.pkl` (18 commits, last
**2026-08-30**), `models/model_ht_over15.pkl`, plus their metrics and feature importances.

Live board output, `output/predictions.csv`:

```
p_ht_over05   n=77   min 0.6642   max 0.7451   std 0.0142
p_ht_over15   n=77   min 0.3267   max 0.3778   std 0.0110
```

Tip thresholds, `src/ledger.py:346-356` (`notify_ht_tips` mirrors them):

```
p05 >= 0.75  ->  ht_over05 OVER      rows qualifying:  0
p05 <= 0.30  ->  ht_under05 UNDER    rows qualifying:  0
p15 >= 0.60  ->  ht_over15 OVER      rows qualifying:  0
p15 <= 0.25  ->  ht_under15 UNDER    rows qualifying:  0
```

**Zero of 77 rows can satisfy any branch.** The model's entire live output range sits inside the dead
band. `append_ht_tips` returns at `ledger.py:369` (`if not new_rows: return`) on every run.

Consequences, all verified:

- `output/ht_ledger.csv` **does not exist on disk** and appears in no commit (`git ls-files output/`
  returns bets/side_bets/player/sharp/clv only). It is not gitignored — it has simply never been created.
- Three workflows stage it every run: `predict.yml:249`, `update_results.yml:59`,
  `daily_summary.yml:39`. All three swallow the absence (`|| true`).
- Two dashboard pages read it: `pages/5_🎯_Success_Rates.py:80` renders a "half-time" section from it,
  `pages/1_📊_Dashboard.py:176` lists it as a market. Both render an empty market as an absent one.
- `update_results.py:936-1011` contains a full HT grading path against `af_ht_history.parquet` that has
  never had an input row.

Note the diagnosis order that matters: the thresholds are not "too tight". A model whose output has
σ=0.014 across 77 fixtures is not discriminating, so loosening the thresholds would convert a silent
no-op into confident noise. **Measure the HT model's discrimination before touching its thresholds.**

---

## 7. THE WEEKLY RETRAIN EVALUATES NOTHING, AND `retrain.py` IS ORPHANED — PROVEN — HIGH

This partially **refutes** the brief. The brief describes `retrain.py:370 save_models` running before
`:393 run_backtest`, with `_print_comparison()` at `:407` only printing. All of that is accurate about
the file. **But `retrain.yml` never runs that file.** The whole workflow is 82 lines
(`v9/.github/workflows/retrain.yml`) and its only compute step is:

```yaml
46:        run: python pipeline.py --mode train
```

There is no backtest step, no comparison step, no gate and no print. The situation is not "the
comparison is computed and discarded" — **the comparison is never computed.** `retrain.py` is reachable
only by a human typing `python retrain.py` locally, which is what `CLAUDE.md` documents.

Confirmed downstream effects:

```
output/backtest_metrics_history.json    last commit 2026-06-17   (matches the brief)
models/feature_importances_standard.csv last commit 2026-06-24   (17 commits, none since)
models/feature_importances_newformat.csv last commit 2026-06-24  (16 commits, none since)
models/model_v9_standard.pkl            last commit 2026-08-30   (19 commits)
```

`pipeline.py:158-164` (`_train_one`) writes `models/feature_importances_{label}.csv` on **every** train,
for `standard` and `newformat` among others. `retrain.yml:63-65` stages the `btts`, `over15`, `over35`,
`ht_over05` and `ht_over15` variants and **omits standard and newformat**. Those two are recomputed every
Sunday and destroyed — 11 weeks of it. The `.gitignore` even carries `!models/feature_importances_standard.csv`
at line 36, an un-ignore for a file nothing stages.

**Pro already has the gate and nothing calls it.** `v10/src/models/registry.py:133 evaluate_gate` and
`:225 Registry.promote` (chronological blocks, logloss/brier improvement, ECE, `clv_n`, plus a
`beats_champion` check at `:241-251`) are imported by exactly one file: `v10/tests/test_registry_gates.py`.
`src/pipelines/shadow.py:44` imports only `hash_manifest` from it. Meanwhile `pro_collect.yml:148` runs
`python -m src.pipelines.registry` — **a different module with the same name** that regenerates
`output/system_registry.json` from `season_store.stats()`. Two modules named `registry`, one of which is
a complete, tested, unused promotion gate.

---

## 8. THE PLACEBO BATTERY IS COMPUTED HOURLY AND THROWN AWAY — PROVEN — HIGH

The estate's signature failure pattern, in the most important file in this audit.

`wowza-v11/scripts/v11_momentum_control.py` writes four outputs:

```
635:  coefs.to_csv(... "v11_momentum_control.csv")        <-- staged
637:  roles.to_csv(... "v11_momentum_roles.csv")          <-- staged
643:  plc.to_csv(... "v11_placebo_table.csv")             <-- NOT STAGED
647:  chrono.to_csv(... "v11_chronological_folds.csv")    <-- NOT STAGED
```

`v11_collect.yml:148-160` stages 18 files. Neither of the last two is in the list.
`git ls-files output/` in wowza-v11 does not contain them. They are not on disk
(`output/` holds `v11_momentum_control.csv` and `v11_momentum_roles.csv`, both 2026-09-08 14:48).

So the two results the brief cites as the verdict on the edge thesis — the placebo table
(mean reversion 0.995, fixed anchor 0.753 vs v9_residual 0.703) and "significant in 0 of 4
chronological folds" — **exist nowhere in the repository.** They are recomputed 16 times a day and
discarded, and the workflow goes green.

Same file, two related defects:

- `output/v11_market_movement.csv` is still **tracked**, last commit **2026-08-23** — the dead filename
  the workflow's own comment says the rewritten script no longer produces. 18 days stale and it reads
  as current to anyone who opens it.
- `output/research_state.json` is described in the workflow comment as *"the guard against forgetting
  again: it records every derived file's `generated_at`, and the freshness contract fails when one lags
  its source."* It does not cover `v11_placebo_table.csv` or `v11_chronological_folds.csv`. The guard
  was built and then not pointed at the two files that most needed it.

---

## 9. v11 HAS PERSISTED NOTHING FOR ~58 HOURS — SUPPORTED — HIGH

Last commit touching any `wowza-v11/output/` path: **2026-09-08 00:30 +0300** = 2026-09-07 21:30 UTC.
v9 HEAD is 2026-09-10 10:31. Cron is `25 8-23 * * *` = **16 runs/day requested**.
`output/v11_shadow_snapshots.csv` is documented as *"the append-only research history … the season's
actual product"* and has not moved. `output/v11_evidence.json` is a further day behind (2026-09-07 14:19),
so `v11_fit_evidence.py` was already lagging before the stall.

This **refutes the brief's delivery model as the explanation.** The brief's rule is that workflows asking
≤8 runs/day get ~100% delivery and ≥26/day get 8–38%. v11 asks 16/day — the middle of the healthy band —
and has landed nothing in 58 hours. Whatever is wrong is not GitHub dropping schedule events. Candidates,
unmeasured from here (no run-log access): the job is failing at the push epilogue, or `v11_shadow.py` is
finding no new fixtures. Note that the v11 epilogue has **no** `-X theirs` (finding 12), so a single
conflict leaves the rebase in progress and all five retries then fail on "rebase in progress" — which
would produce exactly this signature. Checking the v11 Actions run list resolves it in two minutes.

---

## 10. `side_bets_ledger` IS THE PREDICT PATH, NOT THE LIVE SCANNER — PROVEN — HIGH

The brief reads `side_bets_ledger: 246 rows … all source=live` as live-scanner output. That is a
misreading of the field. `src/ledger.py:120-126`:

```
source="live"     → real prediction tips
source="backtest" → walk-forward simulation bets
```

`pipeline.py:317-320` calls `append_side_market_tips(side_bets)` with the default `source="live"`.
So all 254 rows are **predict-generated side-market tips**. The live scanner writes
`output/live_signals_history.csv` and `output/live_tips.csv`, not this file. Measured composition:

```
source: {live: 254}
market: {btts: 175, over15: 74, over35: 5}
tier:   {SNIPER: 114, VALUABLE: 109, MARKSMAN: 31}

settled 147:   SNIPER   n=83  52W  +11.785 u
               VALUABLE n=42  26W   +8.990 u
               MARKSMAN n=22  10W   −2.675 u
```

Two defects in the same file:

**(a) The `side` column is 100% null.** `SIDE_LEDGER_COLS` (`ledger.py:227`) includes `"side"`, added
2026-08-22 with the comment *"a stored `btts` row did not say YES or NO, so a settled BTTS tip could not
be graded unambiguously from the ledger alone."* `append_side_market_tips` (`ledger.py:276-300`) never
writes the `side` key. All 254 rows are NaN. The disambiguation field added to fix an ambiguity was
never wired, so settlement still assumes YES/OVER for every one of the 175 BTTS rows.

**(b) Its CLV is negative.** `clv_pct` over the 135 settled rows carrying a close: **mean −2.507%**.
The `+18.56u` is being earned while systematically taking worse-than-closing prices. Convention is
confirmed at `scripts/backfill_clv.py:38` — *"percent, positive = beat the close."* With n=135 that is
a meaningful sample, and it is the opposite sign to what a real edge produces. The side-market profit is
the estate's only positive line and it is **not** supported by CLV. Also: `over35` has 5 tips and
**0 settled** — that market has never been graded.

---

## 11. `bets_ledger.csv` IS RACED BY THREE WORKFLOWS UNDER `-X theirs` — PROVEN mechanism — HIGH

Three workflows stage and push `output/bets_ledger.csv`:

| workflow | cron | requested/day | concurrency group |
|---|---|---|---|
| `predict.yml` | 4 crons, `9-59/15 8-23 * * 5,6,0` etc. | **57.1** | `predict` |
| `update_results.yml` | `30 7,9,11,...,23 * * *` | 9.0 | **none** |
| `daily_summary.yml` | `0 7 * * *` | 1.0 | **none** |

`src/ledger.py:216` (`updated.to_csv(LEDGER_FILE)`) and `update_results.py:1343` both rewrite the
**entire file**, not a delta. All three epilogues end with:

```
git pull --rebase --autostash -X theirs origin main && git push
```

In a rebase, `theirs` is the commit being replayed — this run. So on a conflicting whole-file rewrite the
**later pusher's copy wins entirely** and the earlier pusher's rows vanish, with both runs green. The
comment in `predict.yml:270-275` explains the `-X ours → -X theirs` change correctly for *append-only
capture files*, where "keep this run's data" is right. It is exactly wrong for a file two jobs rewrite
with different information: predict appends new tips, `update_results` fills `result`/`pnl`/
`closing_odds`/`clv_pct`. Whichever loses the race loses its whole contribution.

I have not measured a specific lost row (that needs run timestamps I cannot read here), so the loss is
PLAUSIBLE while the mechanism and the overlap opportunity are PROVEN: 57 + 9 + 1 = 67 requested pushes
a day against files with no shared group.

**Related, and by design:** `predict.yml:268` runs `git restore .` after committing. Every file the
pipeline wrote that is not one of the 24 staged paths is discarded. `output/side_bets.csv`
(`pipeline.py:318-319`) is one such file — computed every run, never persisted, while its ledger is.

---

## 12–17. THE REST, WITH NUMBERS

**12 · Push epilogue duplicated ~30× in three variants — PROVEN — MEDIUM.**
21 of 21 v9 workflows with a push: `-X theirs`, a `pushed=1` flag, explicit `exit 1` on exhaustion.
8 of 8 v10 workflows and 1 of 1 v11: **no `-X theirs`**, no flag (`&& exit 0`). A real conflict in Pro or
v11 aborts mid-rebase; the next retry then fails on "rebase in progress" and all five burn. Staging style
diverges too: per-file loop (v9, v11, part of v10) vs `git add -A data` (v10 collect, team_news,
team_stats, bet_builder, backfill_results). Three repos, three conflict policies, one copy-pasted body.

**13 · `league_roi_config.json` mixes fresh and stale inputs — SUPPORTED — MEDIUM.**
`backtest_matrix.yml:91-113` rebuilds `roi_by_league` and `approved_markets_by_league` from
`output/backtest_by_league_{btts,over15,over35}.csv`, taking whatever is in the tree — flattened from
`_artifacts`, or, if a matrix leg failed, the version restored by `actions/checkout`. Measured on the
2026-09-01 run:

```
output/backtest_by_league_btts.csv    last commit 2026-09-01
output/backtest_by_league_over15.csv  last commit 2026-09-01
output/backtest_by_league_over35.csv  last commit 2026-08-02   <-- 30 days stale
output/backtest_results_over35.csv    last commit 2026-09-01   <-- but its results DID update
```

So September's `league_roi_config.json` carries an over35 section computed on 2 August, silently, with no
provenance field and no warning. The `approved_markets_by_league` gate that consumes it cannot tell.

**14 · Cron-string branching is still live — PROVEN — MEDIUM.**
The NEAR bug is fixed in both capture workflows (`std_odds_capture.yml:145-149`,
`nf_odds_capture.yml:150-154`) and correctly inverted to match the WIDE cron so it fails safe. Good.
But the antipattern survives elsewhere:

- `player_props.yml:294` — `if [[ "$SCHEDULE" == *"0-7"* ]] && [ "$TODAY" -gt "20260719" ]; then exit 0`.
  The file's crons are `2 */2 * * 5,6,0`, `2 */6 * * 1-4`, `30 23 * * *`, `0 5 * * 0`, `0 5 * * 1-6`.
  **None contains "0-7".** Dead branch. Currently harmless (the WC night cron it guarded is gone), but it
  is the identical construction that cost two weeks of closing lines.
- `player_props.yml:338` — the committed health record writes `"schedule": os.getenv("PROPS_SCHEDULE","")`
  and `PROPS_SCHEDULE` is set **nowhere in the repo** (single grep hit: that line). The observability file
  built specifically because *"this workflow has reported SUCCESS on every hourly run since 2026-08-15
  while `player_tips.csv` never changed"* cannot say which cadence produced any of its 322 commits.
- `nf_odds_capture.yml:142` asserts *"it keys on a `NEXT_KO_MIN` line that only
  `capture_std_sidemarket_odds_forward.py` prints. `capture_nf_odds_forward.py` emits no such signal"* —
  while `:171-174` in the same file reads it and `scripts/capture_nf_odds_forward.py:290,310` prints it.
  The comment contradicts the code 30 lines below it, on the branch whose unreachability already cost
  two weeks.

**15 · The live scanner notifies nothing — PROVEN — MEDIUM.**
`live_scanner.yml:103-104`: `LIVE_ALERTS: ''` with *"Set LIVE_ALERTS: '1' to resume sending."*
16 runs/day collect in-play snapshots and send zero alerts. `output/live_games.csv` last commit
2026-09-10 00:50 (422 commits) while `output/live_tips.csv` sits at 2026-09-05 21:54 and
`output/live_signals_history.csv` at 2026-09-06 01:16. Collection is healthy; the product is switched
off. Whether that is intentional is a decision, but nothing in the repo records it as one.

**16 · `CLAUDE.md` is wrong about its own estate — PROVEN — MEDIUM.**
The Pro cron table lists `pro_team_news.yml` as `*/30 * * * *`; actual is `15 */3 * * *` (8/day, not 48).
It lists `pro_backfill_results.yml` as `25 * * * *`; actual is `25 */6 * * *` (4/day, not 24).
`pro_team_stats.yml` (`35 4,16 * * *`) and `pro_paper_1x2.yml` (`41 7 * * *`) are absent from the table.
Invariant 7 states *"`STANDARD_FORMAT_LEAGUES` is a superset of `ENABLED_LEAGUES`"*; measured
`len(STANDARD)=17, len(NEW)=15, len(ENABLED)=20` and `ENABLED − STANDARD − NEW = ∅` — the true statement
is `STANDARD ∪ NEW ⊇ ENABLED`, with 10 training-only standard leagues. This matters because the invariants
file is the artefact everyone is told to read first.

**17 · Invariant-7 leak into live tips — PROVEN — LOW.**
10 of 1,061 live `bets_ledger` rows (0.9%) are in leagues outside `ENABLED_LEAGUES`:

```
Turkish Super Lig         3 rows  3 settled  −1.12 u
Poland Ekstraklasa        3 rows  3 settled  −3.00 u
Dutch Eredivisie          2 rows  2 settled  +0.90 u
Belgian First Division A  2 rows  1 settled  −1.00 u    (2 of the 10 are SNIPER/MARKSMAN)
```

Three of the four are training-only standard leagues excluded on measured-negative-ROI grounds.
**Poland Ekstraklasa is in neither `STANDARD_FORMAT_LEAGUES` nor `NEW_FORMAT_LEAGUES`** — it should not
be scoreable by either model track at all. Net −4.22u; the concern is the leak path, not the money.
`side_bets_ledger` has 0 such rows (0.0%), so the leak is specific to the main O/U path.

---

## WORKFLOW CENSUS — 264 SCHEDULED RUNS/DAY REQUESTED

Computed by expanding every cron field in all 30 workflow files and averaging over the week.

### v9 — 205 requested runs/day

| workflow | cron(s) | req/day | commits |
|---|---|---|---|
| `predict.yml` | `9-59/15 8-23 * * 5,6,0`; `9-59/30 0-7 * * 5,6,0`; `9-59/30 8-23 * * 1-4`; `9 0-7 * * 1-4` | **57.1** | 24 paths incl. bets, bets_ledger, predictions, odds_history_v9.json, side_bets_ledger, book_odds_snapshots, notified.json, sharp_history/ · then **`git restore .`** |
| `nf_odds_capture.yml` | `35 1,7,13,19 * * *` (WIDE); `20,50 0-3,9-23 * * *` (NEAR) | **42.0** | `newformat_odds_history.csv` |
| `std_odds_capture.yml` | `5 0,6,12,18 * * *` (WIDE); `23,52 0-3,9-23 * * *` (NEAR) | **42.0** | `standard_sidemarket_odds_history.csv` |
| `live_scanner.yml` | `4 8-23 * * *` | 16.0 | live_tips, live_games, live_signals_history, inplay_snapshots, live_notified · **alerts disabled** |
| `player_props.yml` | `2 */2 * * 5,6,0`; `2 */6 * * 1-4`; `30 23 * * *`; `0 5 * * 0`; `0 5 * * 1-6` | 9.4 | player_tips, player_ledger, props_health, prop_odds_coverage, player_notified |
| `update_results.yml` | `30 7,9,11,13,15,17,19,21,23 * * *` | 9.0 | 5 ledgers + live_signals_history (**no concurrency group**) |
| `sharp_tracker.yml` | `0 8,10,...,22 * * *` | 8.0 | sharp_tips, sharp_ledger, sharp_history/, sharp_notified |
| `prop_odds_snapshot.yml` | `20 */4 * * *` | 6.0 | player_prop_odds_history, **clv_records.csv** |
| `af_usage_monitor.yml` | `51 1,7,13,19 * * *` | 4.0 | api_usage_log.csv · *no alert at 45k / abort at 60k yet* |
| `sharp_move_alert.yml` | `0 7,13,19 * * *` | 3.0 | sharp_move_notified.json |
| `af_history_extend.yml` | `0 6 * * *` | 1.0 | af_history.parquet |
| `daily_summary.yml` | `0 7 * * *` | 1.0 | 5 ledgers, notified.json, player_notified.json (**no concurrency group**) |
| `fantasy_refresh.yml` | `30 6 * * *` | 1.0 | fantasy_tips, fantasy_projection_log, pl_squads* |
| `injury_refresh.yml` | `0 4 * * *` | 1.0 | player_history.parquet (Saturday-gated) |
| `player_history_extend.yml` | `40 3 * * *` | 1.0 | player_history.parquet, history_extend_health.json |
| `warm_nf_shot_cache.yml` | `0 3 * * *` | 1.0 | **NOTHING — no commit step at all** |
| `backtest_matrix.yml` | `0 3 1 * *` | 1.0 | backtest_results_*, backtest_by_league_*, league_roi_config, best_params_* |
| `preseason_retrain.yml` | `0 2 1 8 *` | 1.0 | models + metrics |
| `retrain.yml` | `0 3 * * 0` | 0.14 | 7 .pkl + 7 metrics + 5 feature_importances — **omits standard/newformat FI, omits every backtest artefact** |
| `weekly_summary.yml` | `0 9 * * 1` | 0.14 | **NOTHING — Telegram only** |
| `backtest.yml` | manual only | — | backtest_results_*, league_roi_config |
| `worldcup.yml` | manual only | — | worldcup_* (dead since 2026-07-13) |

### v10 / Pro — 43 requested runs/day

| workflow | cron | req/day | commits |
|---|---|---|---|
| `pro_collect.yml` | `40 */2 * * *`; `15 6 * * *` | 13.0 | `git add -A data` + collect_health, import_watermarks |
| `pro_live_odds.yml` | `9 11-23 * * *` | 13.0 | `data/season_*/live_odds_snapshots` |
| `pro_team_news.yml` | `15 */3 * * *` | 8.0 | `git add -A data` |
| `pro_backfill_results.yml` | `25 */6 * * *` | 4.0 | `git add -A data experiments` |
| `pro_team_stats.yml` | `35 4,16 * * *` | 2.0 | `git add -A data` |
| `pro_bet_builder.yml` | `17 9,15,20 * * 5,6,0`; `17 15 * * 1-4` | 1.9 | `git add -A data` + per-file |
| `pro_paper_1x2.yml` | `41 7 * * *` | 1.0 | `output/paper_1x2.csv` |
| `pro_weekly_audit.yml` | `15 6 * * 1` | 0.14 | audit outputs |

### wowza-v11 — 16 requested runs/day

| workflow | cron | req/day | commits |
|---|---|---|---|
| `v11_collect.yml` | `25 8-23 * * *` | 16.0 | 18 paths — **omits `v11_placebo_table.csv` and `v11_chronological_folds.csv`** |

**Allocation observation.** v9's two odds captures request 84/day — **41% of the repo's entire scheduled
budget** — and `predict` a further 57 (28%). Three workflows account for 141 of 205. Since throttling is
per repository, the captures and predict are competing for the same dropped-event budget inside v9, while
the captures run on API-Football (3% of a 75,000/day cap) and predict on The Odds API (89,842/100,000,
no headroom). The two are coupled by nothing but the repo they happen to live in.

---

## DEAD OUTPUTS AND ORPHANED CODE

Last-commit dates for all 108 tracked files under `v9/output`, `v9/models`, `v9/telegram_bot`
(one `git log --name-only` pass since 2026-05-01). Everything older than 30 days:

```
2026-05-21  models/feature_importances_v9.csv, models/metrics_v8.json,
            output/backtest_all_leagues.csv, backtest_all_leagues_by_league.csv,
            backtest_by_league.csv, backtest_season_breakdown.csv        (pre-split era, 1 commit each)
2026-06-15  output/weekly_research_2026-06-15.md
2026-06-17  output/backtest_metrics_history.json                          <-- the retrain record
2026-06-22  output/backtest_results.csv                                   (superseded by _standard/_newformat)
2026-06-24  models/feature_importances_standard.csv   (17 commits, then never again)
2026-06-24  models/feature_importances_newformat.csv  (16 commits, then never again)
2026-06-24  output/player_props_calibration.json
2026-07-11  telegram_bot/wc_notified.json, output/worldcup_tips.csv
2026-07-13  output/worldcup_model_tips.csv, output/worldcup_history.json
2026-07-27  output/fpl_bootstrap.json, output/fpl_fixtures.json
2026-08-02  models/best_params_over35.json, output/backtest_by_league_over35.csv   <-- feeds finding 13
2026-08-18  output/sharp_history.json.migrated, sharp_history/2026-06.json, 2026-07.json
```

`predict.yml` still stages `output/worldcup_tips.csv`, `output/worldcup_history.json` and
`output/sharp_history.json` (the last is not even tracked — only `.migrated` is). Harmless, but it is
seven dead paths in the hot loop's add list.

Orphaned code confirmed this session:

- `v9/retrain.py` — 440+ lines including the only backtest-comparison logic in v9. Called by no workflow.
- `v10/src/models/registry.py` `evaluate_gate` / `promote` — a complete champion/challenger gate, called
  only by its own test file.
- `v9/scripts/backfill_af_odds.py` — cannot work (documented in `CLAUDE.md`); would spend 20,000 calls
  writing empty results. Also reads `APIFOOTBALL_KEY` at import with no `.env` load.
- `v9/src/sharp_tracker_v1.py` — superseded by `sharp_tracker.py`; both write `SHARP_TIPS_FILE`.
- `v9/scheduler/git_push_outputs.py` — pre-Actions push helper, references the ledgers.
- `v9/src/clv_capture.py` — imported **only** by `player_model/clv_tracker.py`. Its docstring calls CLV
  *"the go/no-go gate before any real stake"*, and no team-model path uses it. Team CLV is computed by a
  completely separate implementation in `update_results.py` — the one in finding 1. Two CLV
  implementations, and the broken one is the one guarding real money.

---

## WHAT I WOULD NOT BUILD

1. **Do not tune `MARKSMAN_THRESHOLD` (or any threshold) on the 38 staked rows.** 46.2% of that ledger's
   tiers cannot be reproduced from their own recorded edge, the sample pools ≥2 rule regimes, and doing so
   is invariant 6. The threshold is also not the binding constant for the two leagues that matter
   (Championship `marksman_th=0.05`).
2. **Do not add odds-capture cadence before fixing the closing-price join.** More snapshots feeding
   `_closing_odds_json`'s date-blind fallback produce more contaminated CLV, not better CLV. The capture
   cadence work is already good; the consumer is broken.
3. **Do not wire Pro's `evaluate_gate` into v9.** v9 is frozen and its retrain workflow does not even
   produce the metrics the gate needs. Point the gate at Pro's own training, where `registry.py` already
   lives and `tests/test_registry_gates.py` already passes.
4. **Do not loosen the HT thresholds.** σ=0.014 across 77 fixtures is a non-discriminating model;
   loosening converts a silent no-op into confident noise. Measure discrimination first, then decide
   whether the model should exist.
5. **Do not build a props betting path.** Invariant 2, and nothing here touches it.
6. **Do not buy a larger OddsAPI plan on the strength of the side-market `+18.56u`.** Its CLV is −2.51%
   over 135 settled rows; the profit is not supported by the price evidence.
7. **Do not write a new capture/commit workflow from the existing template.** The epilogue is already
   duplicated ~30 times in three divergent variants. Extract it to a composite action or reusable
   workflow first, or the next copy inherits whichever variant was nearest.

---

## OPEN QUESTIONS

1. **Is the `p_model` compression a transient or the steady state?** One board (n=77, σ=0.023) drives
   finding 3. Thirty days of committed `predictions.csv` recovered from git history would settle whether
   the standard model has ever discriminated in production. ~1 hour.
2. **Why has v11 not committed since 2026-09-07 21:30 UTC?** The run list distinguishes a push-epilogue
   failure (likely, given no `-X theirs`) from an empty shadow. Two minutes with Actions access.
3. **How much of the ledger's `result`/`pnl` has been lost to the three-way `bets_ledger` race?**
   Needs workflow run timestamps cross-referenced with commit SHAs touching that file.
4. **What fraction of `clv_records.csv` (150 commits, props path) shares the date-blind join defect?**
   It uses a different implementation (`src/clv_capture.py`) and may be clean — which would make it the
   template for fixing the team path.
5. **Was `approved: true` in `best_params_standard.json` ever set by anything other than the sign of
   `roi_oos`?** If the writer is deterministic on that field, the invariant-6 violation is mechanical and
   fixable in one function.
6. **`book_odds_snapshots.csv` (143,799 rows, 24 real books) is committed by `predict.yml` and read by
   nothing in v9.** Pro imported it on 2026-09-09. Two-sided in 80.1% of groups — enough to compute a
   real de-vigged close and replace the broken `_closing_odds` path entirely. That is the one genuinely
   unexploited asset in the estate and it is the natural fix for finding 1, not a new feature.

# AGENT 10 — External Research Scout

**Date:** 2026-09-10
**Remit:** find what is publicly known (2023–2026) about football modelling and betting-market
efficiency, prioritising *evidence about beating closing lines* over modelling novelty; identify
data sources credible practitioners treat as essential.
**Rules of engagement honoured:** read-only on `v9/` and `wowza-v11/`; one file written (this one);
nothing committed, no source edited, no data partition touched.

**Tool note, stated plainly:** `WebSearch` worked for the first six queries of this session and then
returned `Web search error: unavailable` on every subsequent attempt (8 consecutive failures across
~40 minutes). All research after that point was done with `WebFetch` against known URLs and against
the **arXiv API** (`export.arxiv.org/api/query`) and **Semantic Scholar** (which returned HTTP 429).
Three source PDFs could not be parsed by the fetch tool and were extracted locally with a
throwaway zlib/FlateDecode text extractor in the scratchpad. Two sites
(`football-data.co.uk`, `historicdata.betfair.com`) failed TLS verification from this machine
("unable to verify the first certificate") and were **not** fetched; where I needed
football-data.co.uk facts I read the CSVs already cached on disk instead, which is better evidence
anyway. Nothing below is cited that I did not fetch or compute.

---

## HEADLINE

The closing price beats v9's own model on v9's own metric, and I measured it on the same sample
size: **market log loss 0.68000 / AUC 0.5848 against v9's best estimator at 0.68833 / 0.5484
(n = 4,450 each)** — which means `edge = model_prob − 1/odds` subtracts a *stronger* estimator from a
*weaker* one, so the ledger's −91.63u is not a bug to fix but the arithmetic of paying a
5.23% margin for noise; and the published literature reached the identical result independently
this year (fitted pooling weight on a structural model against a margin-free closing price:
**0.000**).

---

## FINDINGS TABLE

| # | Finding | Evidence | Conf. | Cat. | Impact | Fix |
|---|---|---|---|---|---|---|
| F1 | The closing price is a strictly better O/U 2.5 forecast than v9's model | market 0.68000 logloss / 0.5848 AUC vs v9 logistic 0.68833 / 0.5484, both n=4,450 | PROVEN | STATISTICAL | CRITICAL | WEEKS |
| F2 | The ledger loss is fully explained by margin; no evidence of skill either way | best-price OU25 overround median 5.52% (n=12,655) → −5.23% floor; ledger −7.91%, SE 2.79pp | PROVEN | STATISTICAL | CRITICAL | DAYS |
| F3 | A free Pinnacle **closing** line for our exact leagues is on disk and discarded | `data_loader.py:49` picks `AvgC>2.5` first, so `PC>2.5` is never read; 13,216 matches have it | PROVEN | MARKET_DATA | HIGH | HOURS |
| F4 | The model is trained on closing odds and served pre-match odds; the market is already inside it | `data_loader.py:49`; `model.py:88,101–107` (6 market features) | PROVEN | ARCHITECTURE | HIGH | WEEKS |
| F5 | Answer to the seed's open question: `edge_pct` **is** the decision edge; the ~9–12% SNIPERs come from two named paths | `ledger.py:175,198`; `betting.py:154–157,208–213`; `best_params_standard.json` | PROVEN | EXECUTION | HIGH | DAYS |
| F6 | `best_params_standard.json` is retrospective tuning in the live path (Championship SNIPER = 0.07) | file contents; `betting.py:154–157`; no `n`/`roi` recorded | PROVEN | PROCESS | HIGH | DAYS |
| F7 | "No OddsAPI headroom" is a $60/month problem, and historical odds ARE purchasable | 5M plan $119/mo vs 100K $59/mo; history from 2020-06-06, 5-min snapshots, 10 credits/region/market | PROVEN | PROCESS | HIGH | HOURS |
| F8 | The strongest external profit result is in-play, and our only positive ledger is in-play | 4.5% ROI / Sharpe 5.94 over 17,458 bets vs Betfair in-play; side_bets +18.56u, all `source=live` | SUPPORTED | MARKET_DATA | HIGH | WEEKS |
| F9 | The one replicated profitable football strategy is cross-book consensus, not forecasting | Kaunitz et al: 10-yr sim + 6-mo minute sim + 5 mo real money, then accounts limited | SUPPORTED | ARCHITECTURE | HIGH | WEEKS |
| F10 | "More features" is externally closed for this market | shots-on-target variant: weight 0.35 vs goals model, **0.000** vs market | SUPPORTED | STATISTICAL | MEDIUM | — |
| F11 | Retrain-without-a-gate is a documented anti-pattern; the external standard is explicit | Google MLOps: "ensure that the new model produces better performance than the current model before promoting it" | PROVEN | PROCESS | HIGH | HOURS |
| F12 | Fixed-n significance is the wrong instrument for a live ledger; use anytime-valid confidence sequences | Waudby-Smith & Ramdas 2010.09686; Shekhar & Ramdas 2310.01547 | PROVEN | STATISTICAL | MEDIUM | DAYS |
| F13 | Power de-vig is the right default (v11 already uses it); OO-EPC is a marginal upgrade | Clarke/penaltyblog; Goto et al, 90,014 matches, 5 books | SUPPORTED | STATISTICAL | LOW | DAYS |
| F14 | The literature *disagrees* about whether the sharp two-way market is efficient — record the tension | Whelan & Hegarty: 3.61% ex-ante vs 3.63% realized, n=168,460, no FLB. Constantinou: AH "shares the inefficiencies" | SUPPORTED | STATISTICAL | MEDIUM | — |
| F15 | FBref lost its Opta licence in Jan 2026 — the main free advanced-stats feed no longer updates | liamhenshaw.com football-data survey | SUPPORTED | DATA_QUALITY | LOW | — |

---

## F1 — The closing price beats the model. Measured, same n, same leagues. (PROVEN)

This is the finding everything else hangs off, so here is the whole computation.

**v9's own recorded metrics**, `v9/models/metrics_model_v9_standard.json`:

| estimator | log loss | AUC | accuracy | n_test |
|---|---|---|---|---|
| logistic | 0.68833 | 0.5484 | 0.5364 | 4,450 |
| gradient_boost | 0.69153 | 0.5232 | 0.5272 | 4,450 |
| lightgbm | 0.69052 | 0.5288 | 0.5290 | 4,450 |

**The market on the same market, computed this run** from the football-data.co.uk CSVs already
cached at `data/football_data/<code>/*.csv` (16,655 standard-format matches with results,
2019-07-26 → 2026-05-18, 15 league codes matching `v9/src/data_loader.py:158–166`), de-vigged with
the **power method** (solve `(1/o_over)^k + (1/o_under)^k = 1`):

| predictor | n | log loss | AUC | Brier | median overround |
|---|---|---|---|---|---|
| Pinnacle **closing** (`PC>2.5`/`PC<2.5`) | 13,216 | **0.67274** | **0.6100** | 0.24008 | 3.57% |
| Average closing (`AvgC`) | 16,626 | 0.67438 | 0.6044 | 0.24088 | 6.16% |
| Best closing (`MaxC`) | 16,626 | 0.67441 | 0.6046 | 0.24088 | 1.70% |
| Pinnacle pre-close (`P>2.5`) | 13,124 | 0.67575 | 0.6011 | 0.24152 | 4.15% |
| Average pre-close (`Avg>2.5`) | 16,613 | 0.67706 | 0.5961 | 0.24215 | 6.33% |
| constant base rate (0.5211) | 16,626 | 0.69226 | 0.5000 | — | — |

On the **most recent 4,450 matches**, chosen to mirror the model's own `n_test=4450`
(2025-09-23 → 2026-05-18):

| predictor | n | log loss | AUC |
|---|---|---|---|
| Average closing | 4,450 | **0.68000** | **0.5848** |
| Pinnacle closing | 1,046 | 0.68061 | 0.5836 |
| v9 logistic (recorded) | 4,450 | 0.68833 | 0.5484 |
| constant base rate | 4,450 | 0.69227 | 0.5000 |

Read it as skill score against the constant base rate:

* market closing price: (0.69227 − 0.68000)/0.69227 = **1.77%** log-loss reduction
* v9 logistic: (0.69227 − 0.68833)/0.69227 = **0.57%**
* on the full 7 seasons, Pinnacle closing = **2.83%**, i.e. **5x** the model

So the market captures roughly three to five times as much of the available signal as the model
does, and it does so on the same fixtures. `edge = model_prob − 1/odds` therefore differences a
0.57%-skill estimator against a 1.77%-skill estimator. The disagreement is dominated by the weaker
side's error. Betting that disagreement has a null expectation of *minus the margin* — which is F2.

**Caveats I owe you.** The 4,450-match tail is the most recent 4,450 rows of my pooled frame; I do
not know that it is byte-identical to the chronological tail `src/model.py` held out (that split is
made after feature engineering drops rows with missing form, per invariant 8). The window overlaps
and the n matches, and the full-sample numbers point the same way with 3.7x the data, so the
direction is not in doubt even if the third decimal moves. Pinnacle closing has 79% coverage
(13,216/16,655), so its column is a slightly different fixture set — `AvgC` at 99.8% coverage is the
apples-to-apples row and it still wins by 0.0083 nats and 3.6 AUC points.

**This is the published result.** Yannik Pitcan, *"Does a Structural Model Add Anything to the
Closing Price?"*, arXiv **2608.11505** (11 Aug 2026),
<https://arxiv.org/abs/2608.11505> — nineteen complete Serie A seasons, 7,220 matches:

> Dixon-Coles with tuned exponential decay: 53.4% accuracy, RPS **0.1972** vs the market's
> **0.1905**; paired difference +0.0067, 95% CI [0.0046, 0.0088]; **the market wins in all seven
> test seasons**. The fitted pooling weight on the structural model in a logarithmic opinion pool
> is **0.000** — a boundary solution, with the log-loss profile monotone increasing in that weight
> on validation and test alike.

And the sentence that should be pinned above the whiteboard:

> "The structural model is better calibrated than the market on the home-win margin (slope 0.995
> versus 1.103) while clearly less sharp: the market's advantage is discrimination rather than
> honesty, which accuracy alone cannot distinguish."

That is v11's residual test (controlled coefficient +0.0002, p=0.90; significant in 0 of 4
chronological folds) reproduced on a different league, a different model class, and 7,220 matches.
v11's null result is not an embarrassment or a measurement failure. **It is the expected result and
it now has an external replication.** Treat it as settled and stop paying to re-discover it.

## F2 — The −91.63u is the margin, and the data cannot distinguish it from zero skill (PROVEN)

I measured our own margin from `v10/data/season_2026_27/book_odds_snapshots` (143,799 rows,
5 parquet files, 24 real bookmakers, 2026-08-19 → 2026-09-16). Overround per two-sided
`(snapshot_ts, fixture_key, market, bookmaker)` group, `OU25`:

| bookmaker | n two-sided | median overround |
|---|---|---|
| matchbook | 3,309 | **2.76%** |
| pinnacle | 1,343 | **4.17%** |
| gtbets | 543 | 6.01% |
| coolbet | 1,410 | 6.06% |
| onexbet | 5,351 | 6.11% |
| betonlineag | 847 | 6.12% |
| betanysports | 277 | 6.40% |
| betsson / nordicbet | 3,563 / 3,551 | 6.90% |
| williamhill | 1,558 | 7.61% |
| mybookieag | 272 | 7.89% |
| tipico_de | 2,357 | 8.24% |
| unibet_se / unibet_nl | 1,897 / 1,746 | 8.30% / 8.46% |
| leovegas_se | 1,912 | 8.78% |
| codere_it | 1,839 | 9.06% |
| pmu_fr | 1,508 | **13.71%** |

Pooled OU25 median 6.96%. BTTS 7.95% (betfair_ex_uk 2.02%, matchbook 2.56%, pinnacle 4.65%).
OU35 6.50%.

**Best price across all 24 books**, which is what `v9_selected_best` takes: synthetic overround
median **5.52%**, mean 5.25%, n = 12,655 snapshot-fixture pairs; only 0.3% of pairs are negative
(true arbs). For a two-way market with inverse-sum `1+m`, a bettor with *zero* information taking
best price has expected return `1/(1+m) − 1` = **−5.23% per unit staked**. That is the floor, and it
is unavoidable while we bet at these books.

Against that floor, the ledger: −91.63u on 1,159 settled = **−7.91%** of bet count. Stakes are
1 / ¾ / ½ by tier, so turnover < 1,159 and the true ROI is *worse* than −7.91% (at an average
0.8u stake it is −9.9%). Per-bet return SD at ~1.90 odds ≈ 0.95, so SE = 0.95/√1159 = **2.79pp**.

* 95% CI on ledger ROI ≈ [−13.4%, −2.4%] → the loss is **real**; zero is excluded.
* Distance from the −5.23% margin floor: **0.96 SD** → the loss is **statistically
  indistinguishable from "no information at all, paying the market's margin."**

So the honest statement is not "the model is losing money because it is bad." It is: **the model is
uninformative, and we pay 5.2% per bet to find that out.** Both the "we have an edge" and the "we
are adversely selected" readings are unsupported by n=1,159; only "we pay the margin" survives.

The external anchor for this is exact. Tadgh Hegarty & Karl Whelan, *"Forecasting Soccer Matches
With Betting Odds: A Tale of Two Markets"* (MPRA 116925, 23 Feb 2023; *International Journal of
Forecasting* 41(2) 2025, 803–820) — <https://mpra.ub.uni-muenchen.de/116925/>, PDF
<https://mpra.ub.uni-muenchen.de/116925/1/MPRA_paper_116925.pdf> — 84,230 matches, 22 European
leagues across 11 nations:

| market | n bets | ex-ante expected loss | realized loss | favourite–longshot bias? |
|---|---|---|---|---|
| home/away/draw | 252,690 | (lower) | **7.83%** | yes: longshot decile 9.4% vs favourite decile 6.1% |
| Asian handicap | 168,460 | **3.61%** | **3.63%** | no: longshot 3.5% vs favourite 4.1% |

For the AH market, *t*-tests **cannot reject** equality of the ex-ante and ex-post loss means, for
the full sample and for sub-samples. In a low-margin two-way soccer market the average bettor's
realized loss equals the priced margin, to two decimal places, over 168,460 bets. That is what
"efficient" looks like numerically, and it is the market family we bet in.

**The actionable half of F2.** The single largest measured improvement available anywhere in this
audit is not a model change. It is the margin: **5.52% best-of-soft → 2.76% at matchbook** is
**+2.6pp of ROI** with zero modelling risk, larger in magnitude than any effect the audit has
measured on either side of zero. It is also the one that turns on a question I cannot answer from
here (see Open Question 1).

## F3 — A free sharp closing line for our exact leagues is on disk and thrown away (PROVEN)

The CSVs already cached at `data/football_data/E1/E1_2526.csv` (etc.) carry these columns:

```
B365>2.5,B365<2.5,P>2.5,P<2.5,Max>2.5,Max<2.5,Avg>2.5,Avg<2.5,BFE>2.5,BFE<2.5,
...
B365C>2.5,B365C<2.5,PC>2.5,PC<2.5,MaxC>2.5,MaxC<2.5,AvgC>2.5,AvgC<2.5,BFEC>2.5,BFEC<2.5,
AHCh,B365CAHH,B365CAHA,PCAHH,PCAHA,MaxCAHH,MaxCAHA,AvgCAHH,AvgCAHA,BFECAHH,BFECAHA
```

The `C` infix is **closing**. So `PC>2.5` / `PC<2.5` is **Pinnacle's closing over/under 2.5** and
`BFEC>2.5` is **Betfair Exchange's closing** price — for Championship, League One, League Two,
Bundesliga 2, La Liga 2, Ligue 2, Serie B, and the rest of `std_leagues`
(`v9/src/data_loader.py:158–166`). I measured 13,216 matches with a two-sided Pinnacle closing
quote, median overround 3.57%.

`v9/src/data_loader.py:49–52`:

```python
_OVER_COLS  = ["AvgC>2.5", "MaxC>2.5", "B365C>2.5", "PC>2.5",
               "Avg>2.5",  "Max>2.5",  "B365>2.5",  "P>2.5"]
```

`_pick_odds` (line 112) returns the **first** column with >10% coverage. `AvgC>2.5` has 99.8%
coverage, so `PC>2.5` is **never reached** — the sharp closing line is present in every file and
read by nothing.

Why this matters: per the seed, CLV is computed against `v9_selected_best`, a best-of-soft
selection, and `market_snapshots.bookmaker` holds only two synthetic values, so no book-level
question can be asked of it. Meanwhile the entire external literature uses **Pinnacle's closing
line** as *the* efficiency benchmark, precisely because of its margin (4.17% live in our own
snapshots, 3.57% at the close in football-data) and its limits. Joseph Buchdahl's efficiency work
on football-data.co.uk is the canonical practitioner reference here, and his stated bar is worth
quoting because we have now crossed his sample threshold with the wrong sign: he recommends **no
serious interpretation of skill below ~1,000 bets and wants p < 0.001** before taking a record
seriously (<https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl>).
We are at 1,159 settled bets, −91.63u.

**A CLV benchmark against Pinnacle's close is a HOURS-scale job in Pro**, entirely read-only with
respect to v9: join `bets_ledger` rows to `data/football_data/<code>/<season>.csv` on
league + date + resolved team names, take `PC>2.5`/`PC<2.5`, power de-vig, and compare to the price
we actually took. That converts CLV from "did we beat a soft book's later price" to "did we beat the
sharpest closing estimate available", which is the only version of the metric the literature treats
as evidence.

Note also `AHCh` + `PCAHH`/`PCAHA`: the Asian-handicap closing line is in the same files, which is
the market Hegarty & Whelan measured as efficient. If we ever want to test the goals-supremacy
thesis against the sharpest available two-way price, the data is sitting there.

## F4 — The model is trained on closing odds, served pre-match odds, and already contains the market (PROVEN)

Two facts compose badly.

**(a)** `_OVER_COLS[0] = "AvgC>2.5"` — training's `odds_over25`/`odds_under25` are the **closing**
average (`data_loader.py:49–52,214–215`).

**(b)** `v9/src/model.py:55–121` lists these among `FEATURE_COLS`:

```python
    # Market microstructure
    "bookmaker_overround",    # over-round tightness signals market confidence
    "p_over25_poisson_dc",
    ...
    # Phase 7: API-Football cross-validated odds (Bet365 via /odds, TTL 6h)
    "api_implied_over25",     # line 101
    "api_overround",          # line 102
    "api_implied_btts",       # line 104
    "api_implied_over35",     # line 105
    "api_implied_over15",     # line 106
    "api_implied_draw",       # line 107
```

So:

1. **The brief's §3 rule "DO NOT retrain to the market" is not a future risk — it is the current
   state.** Six of the model's features are market prices, and `bookmaker_overround` is derived
   from the closing average itself. The residual v11 measures is being taken from a model that
   already has the price partly inside it.
2. **Train/serve skew on exactly those features.** Training sees the *closing average* overround
   (median 6.16% full-sample, 7.72% on the recent tail). Serving sees a *live best-of-24* quote
   (median 5.52%, measured F2) hours before kickoff. The learned coefficient on
   `bookmaker_overround` is fitted on a distribution production never presents.
3. **It gives the placebo battery its mechanism.** If `model_prob` is partly a function of one
   book's implied probability and `edge = model_prob − 1/(best of 24 books)`, then a large part of
   "edge" is a **cross-book price spread**, not a football opinion. Cross-book spreads mean-revert.
   That is why `−prev_move` scores 0.995 and a *constant* scores 0.753 while `v9_residual` scores
   0.703: the placebo table is reading the price series because the "signal" largely *is* the price
   series. The seed says "a mean-reversion score of 0.995 is a verdict on the PRICE SERIES, not the
   market" — agreed, and F4 identifies how the price series got into the residual.

**Adversarial caveat, and it matters.** Root `CLAUDE.md` records that the API-Football enrichments
"had been silently dead for months" and that `api_implied_btts=0.5` was among 29 hardcoded
stand-ins. If `api_implied_*` is mostly NaN → median-imputed across the training frame, then in
practice the model has *almost no* market input, mechanism (1) is mild, and the real story is (2)
plus the fact that a model *nominally* containing the price still scores 0.5484 AUC where the price
alone scores 0.5848 — i.e. 60+ weak features diluting the one informative input. Either reading is
bad; they need different fixes. Deciding between them is one measurement on the training frame
(Open Question 3) and I did not make it.

## F5 — Answer to the seed's open question (PROVEN)

> *"why is edge_pct ~9% on rows tiered SNIPER (needs 0.15–0.25)? Either edge_pct is recorded at
> settlement not at tip time, or tiering uses a different best_edge. ANSWER THIS."*

**Neither. `edge_pct` is recorded at tip time, from the same `best_edge` the tiering used, and the
(tier, edge_pct) pair is always internally consistent.** `v9/src/ledger.py`:

```python
163:        edge       = float(row.get("best_edge", 0.0))
...
169:            if _TIER_RANK.get(tier, 0) > _TIER_RANK.get(cur, 0):
...
174:                existing.at[i, "signal_tier"]  = tier
175:                existing.at[i, "edge_pct"]     = round(edge * 100, 2)
...
198:            "edge_pct":     round(edge * 100, 2),
199:            "signal_tier":  tier,
```

Line 198 writes the edge at first sighting; lines 174–177 overwrite tier **and** edge together from
the *same run's* `best_edge` when the tier climbs. There is no settlement-time write. **So the
6.11% median on the staked standard MARKSMAN bets is the edge the decision was actually made on.**
The seed's defect is real, not a recording artefact.

The ~9–12% SNIPERs come from **two** distinct paths, and I measured which one carries the loss.

**Path A — the config table the audit read is dead for two leagues.** `v9/src/betting.py:154–157`:

```python
    _opt = _load_standard_thresholds().get(str(league)) if league else None
    if _opt and _opt.get("approved") and _opt.get("sniper_th") is not None:
        has_per_league = True
        sniper_thresh  = float(_opt["sniper_th"])
```

`v9/models/best_params_standard.json` (mtime 2026-09-02) is the live source, and it says:

| league | approved | sniper_th | marksman_th |
|---|---|---|---|
| **Championship** | **True** | **0.07** | **0.05** |
| **Serie B** | **True** | **0.12** | **0.10** |
| Bundesliga 2 | False | 0.18 | 0.16 |
| La Liga 2 | False | 0.17 | 0.15 |
| League One | False | 0.14 | 0.12 |
| League Two | False | 0.07 | 0.05 |
| Ligue 2 | False | 0.12 | 0.10 |

`config.LEAGUE_SNIPER_THRESHOLDS[Championship] = 0.15` is a **fallback that never executes** for
Championship. A Championship bet at 7.0% edge is SNIPER at full stake, by design, today.

**Path B — for every other league, MARKSMAN is structurally unreachable except via the drift path.**
`v9/config.py:281–287`:

```
281: VALUABLE_THRESHOLD = 0.04
282: MARKSMAN_THRESHOLD = 0.14
283: SNIPER_THRESHOLD   = 0.12
284: SNIPER_THRESHOLD_OVER  = 0.12
285: SNIPER_THRESHOLD_UNDER = 0.12
287: DRIFT_UPGRADE_EDGE = 0.10
```

`MARKSMAN_THRESHOLD (0.14) > every global SNIPER threshold (0.12)`, and `_base_tier` tests SNIPER
first (`betting.py:171`). So for any league with no per-league entry, `edge >= 0.12` returns SNIPER
and `edge >= 0.14` is then unreachable: **`_base_tier` can never emit MARKSMAN for a
globally-thresholded league.** Every such MARKSMAN row is therefore produced by
`_apply_drift_adjustment` — and that function's guards are asymmetric exactly as the seed says
(`betting.py:205–213`): `MARKSMAN→SNIPER` requires `best_edge >= 0.10`, `VALUABLE→MARKSMAN`
requires **nothing**.

The fingerprint is in the data. Splitting the 70 settled staked standard bets in
`v9/output/bets_ledger.csv` by which threshold table actually bound:

| threshold source | tier | n | median edge | min edge | P/L |
|---|---|---|---|---|---|
| config fallback | MARKSMAN | 25 | 7.22% | **3.26%** | **−14.39u** |
| config fallback | SNIPER | 29 | 12.18% | **10.02%** | −2.44u |
| optimized (approved) | MARKSMAN | 14 | 5.58% | 3.36% | +1.23u |
| optimized (approved) | SNIPER | 2 | 10.19% | 8.74% | +2.50u |

That `min_edge = 10.02%` on the fallback SNIPERs is `DRIFT_UPGRADE_EDGE = 0.10` leaving its
signature: those are MARKSMAN rows promoted to **full stake at 10% edge in leagues whose own SNIPER
threshold is 0.14–0.25**. The drift path bypasses the per-league threshold in *both* directions.

**Where I disagree with the seed:** the seed reads the sub-14% MARKSMAN staking as one defect. It is
two, and they land differently. The 14 sub-threshold MARKSMAN bets in *approved* leagues are
correctly tiered under the live table (marksman_th = 0.05) and are **+1.23u**; the 25 in *fallback*
leagues are drift leakage and are **−14.39u**. Fixing "MARKSMAN below 0.14" as a single rule would
change the wrong 14 rows.

**And per the rules of engagement: n=70 is INSUFFICIENT_DATA to justify a threshold change.** The
structural claim (drift bypasses per-league thresholds; MARKSMAN is unreachable from `_base_tier`
globally) is code-proven and does not need n. The economic sizing does need n and does not have it.

## F6 — `best_params_standard.json` is retrospective tuning in the live money path (PROVEN)

`_load_standard_thresholds` (`betting.py:124–137`) reads
`config.MODELS_DIR / "best_params_standard.json"`, described in its own docstring as
"Auto-optimized per-league standard O/U thresholds … **written by optimize_standard_thresholds each
backtest**". `_base_tier` then uses it live for `approved` leagues. So a threshold is fitted on
backtest results and immediately used to stake real money on the same market — which is invariant 6
("the strategy is frozen before the backtest; thresholds are never changed after seeing results")
being violated *in the production decision path*, not in the research harness.

Two aggravating details I read in the file: it records **no `n` and no `roi`** (every such field is
`None` for all 7 leagues), so nothing downstream can apply a sample-size floor to a threshold it
trusts with full stakes; and the value it produced for the league we bet most is **0.07** — half the
hand-set 0.15 — which is exactly the "least-bad threshold on a thin sample" failure the code's own
comment at `betting.py:150–153` warns about for *non*-approved leagues while exempting approved ones.

External standard, same shape as F11: this is the missing "model validation" gate applied one layer
down, at the threshold rather than the estimator.

## F7 — "No OddsAPI headroom" costs $60/month to delete, and history IS buyable (PROVEN)

Fetched from <https://the-odds-api.com/#get-access>:

| plan | cost | credits/month |
|---|---|---|
| Starter | free | 500 |
| 20K | $30/mo | 20,000 |
| **100K** | **$59/mo** | **100,000** |
| **5M** | **$119/mo** | **5,000,000** |
| 15M | $249/mo | 15,000,000 |

The seed records "The Odds API projects 89,842/100,000 this month (NO headroom)". That is the
$59 plan. **The next tier up is +$60/month for 50x the credits.** Every collection finding in this
audit — T-1h per-fixture coverage 32.6%, T-30m 14.5%, T-10m ~7%, 0.6% of odds observations inside
the final hour, 81% spent on fixtures >24h out — is currently framed as a budget-constrained
allocation problem on the API-Football side while the *OddsAPI* side is one $60 line item from
being unconstrained. Fix cost: HOURS (change a plan, raise a cadence).

**And the historical claim needs narrowing.** From
<https://the-odds-api.com/liveapi/guides/v4/#get-historical-odds>: historical odds are available on
**all plans** from **2020-06-06**, at **10-minute snapshots** initially and **5-minute snapshots
from September 2022**, billed at **10 credits per region per market** (vs 1 live). Root `CLAUDE.md`
concludes, after a well-run 830-call experiment on API-Football, that "**there is no historical-odds
purchase available at any price. The quota cannot buy back the past.**" The experiment is right and
the conclusion is right *for API-Football's `/odds` endpoint*. It is **false for The Odds API**,
which is a different vendor with a paid historical-snapshot product covering exactly the window we
care about.

Order-of-magnitude cost for one season of true closing snapshots across our leagues, shown so it can
be checked rather than believed: ~40 distinct kickoff slots/week × ~8 sport keys × 3 markets ×
1 region × 10 credits ≈ 9,600 credits/week ≈ **~385,000 credits for a 40-week season ≈ 8% of one
month on the $119 plan**. That is an estimate with a factor-of-two error bar, not a measurement
(Open Question 2). But it is the difference between "closing lines are unobtainable" and "closing
lines cost roughly one month's subscription", and it is the input the CLV gate, the retrain gate and
the residual test all need.

## F8 — The literature's strongest profit result is in-play, and so is our only positive ledger (SUPPORTED)

Lawrence Clegg, Zixing Song, John Cartlidge, *"A market-calibrated accelerated failure time model
for in-play football forecasting"*, arXiv **2605.16066** (15 May 2026),
<https://arxiv.org/abs/2605.16066>:

> Weibull AFT with team strengths **calibrated to Betfair Exchange prices at kick-off** plus
> post-shot xG as a time-varying covariate. Across 140 EPL matches at minute intervals it "almost
> matches Betfair's classification accuracy (**70.2% versus 70.6%**)". A betting simulation against
> Betfair in-play odds yields **4.5% ROI (Sharpe 5.94) over 17,458 bets**. "A comparison with two
> alternative continuous-time scoring models, both calibrated to the same pre-match odds, confirms
> that **market calibration is the dominant driver of predictive accuracy**."

Three things to take from it. First, the model is **less accurate than the market and still
profitable** — accuracy is not the currency, which is the same lesson as invariant 2 (props
accurate, no edge) arriving from the opposite direction. Second, "market calibration is the dominant
driver" is v11's architecture (de-vig → consensus → small capped residual) endorsed by
measurement. Third, the inefficiency they find is **in-play**, not pre-match.

Our own numbers point the same way: `side_bets_ledger` is 246 rows, 143 settled, 86W/57L,
**+18.56u flat, all `source=live`** — the only positive segment in the system. n=143 is
INSUFFICIENT_DATA to act on and I will not pretend otherwise; a CI on 143 bets at ~1.9 odds spans
roughly ±16pp. But it is the only place where the internal evidence and the strongest external
evidence agree on a direction, and it is where I would spend the next unit of research effort.

Corroborating in-play microstructure work, both from the Bielefeld/Deutscher group: *"Do Betting
Markets Sense a Goal Coming?"* (arXiv 2505.21275) finds **no** significant anticipatory behaviour in
1 Hz Bundesliga data — i.e. the in-play price does not see goals coming, which is where an
intensity-based model can add something; and *"Gambling on Momentum"* (arXiv 2211.06052) finds
bettors overestimate momentum after equalisers **but do not profit from it** — the exploitable side
of the same bias.

## F9 — The one replicated profitable football strategy is cross-book consensus, not forecasting (SUPPORTED)

Lisandro Kaunitz, Shenjun Zhong, Javier Kreiner, *"Beating the bookies with their own numbers — and
how the online sports betting market is rigged"*, arXiv **1710.02824**,
<https://arxiv.org/abs/1710.02824>:

> "Instead of building a forecasting model to compete with bookmakers predictions, we exploited the
> probability information implicit in the odds publicly available in the marketplace to find bets
> with mispriced odds. Our strategy proved profitable in a 10-year historical simulation using
> **closing odds**, a 6-month historical simulation using **minute to minute odds**, and a 5-month
> period during which we **staked real money** … We provide a detailed description of our betting
> experience to illustrate how the sports gambling industry compensates these market inefficiencies
> with **discriminatory practices against successful clients**."

Code, data and models are public per the abstract. Note what the profitable object is: **an
outlier book against the consensus of many books.** That is a market-data problem, not a football
problem, and `book_odds_snapshots` is precisely its input — 24 real bookmakers, 143,799 rows,
markets OU15/OU25/OU35/BTTS, 99.4% fixture_key join rate, and per the seed "**largely
unexploited**".

The binding constraints are measurable and I measured two of them:

* **Depth.** Per the seed, median 2 books per (snapshot, fixture, market) group, p90 5, max 17, and
  only 34.9% of groups have ≥3. A consensus from 2 books is not a consensus. My own overround table
  shows why depth matters more than it looks: the spread between books is enormous
  (matchbook 2.76% → pmu_fr 13.71%), so an "outlier" against a 2-book mean is usually just the
  wide book being wide.
* **Sharp coverage is better than expected.** Pinnacle two-sided quotes cover **447 of 798
  fixtures (56%)**, matchbook **637/798 (80%)**, betfair_ex_uk 30/798. Pinnacle's leagues in this
  table are our leagues: Championship 1,318 rows, League Two 859, League One 758, Ligue 2 201,
  La Liga 2 194, Serie B 147, Bundesliga 2 25. **We already have a sharp anchor for the majority of
  our board and are computing CLV against a soft best-price instead.**
* **But not at the close.** Pinnacle rows have median **1,518 minutes** (25h) to kickoff; only
  **3.79%** are within 60 minutes and **7.9%** within 180. So the sharp *closing* line is not being
  captured forward — which is exactly what F3 (football-data `PC>2.5`, retrospective) and F7
  (historical snapshots, purchasable) each solve independently.

**And the failure mode is the finding.** Kaunitz's strategy worked and the accounts were limited.
Any plan built on beating soft books at best price has account survival as its real constraint, and
that is a business-process problem no model change addresses.

## F10 — "More features" is closed for this market, externally (SUPPORTED)

From Pitcan (2608.11505), the result that should end the feature roadmap for the pre-match O/U
model:

> "Refitting the same machinery to **shots on target** yields a variant earning weight **0.35
> against the goals model** — it carries information the goals model lacks — and **0.000 against the
> market**. Two structural signals, each informative about the other, both priced."

That is the general form of what this project already found twice locally and recorded as
`project_understat_xg_null` (133k shots scraped, zero AUC gain, redundant with goals/shots) and
`project_weather_null` (delta −0.004, corr ~0). Those were not unlucky choices of feature. They are
instances of a measured regularity: features that improve a football model relative to *other
football models* do not improve it relative to the *price*, because the price already has them.

Second, independent instance — Edward Wheatcroft & Ewelina Sienkiewicz, *"A Probabilistic Model for
Predicting Shot Success in Football"*, arXiv **2101.02104**, <https://arxiv.org/abs/2101.02104>:
a shot-success model improves forecast accuracy for match outcomes **and over/under 2.5 goals**,
"though evidence for improved betting performance was **mixed**." Accuracy up, betting flat.

**The honest counter-example**, reported because it exists: Wheatcroft, *"Forecasting football
matches by predicting match statistics"*, arXiv **2001.09097**,
<https://arxiv.org/abs/2001.09097> — GAP ratings, "results indicate the forecasts provide value
beyond conventional betting odds, with demonstrated long-term profitability when paired with
specific betting strategies." I weight this low: single author, single method, and "when paired with
specific betting strategies" is where in-sample strategy selection lives. But it is a published
positive claim on the pre-match market and I am not going to pretend the literature is unanimous.

## F11 — Retrain-without-a-gate, and the external standard (PROVEN)

The seed establishes the internal facts (retrain.py:370 saves before :393 backtests;
`_print_comparison()` only prints; `backtest_metrics_history.json` isn't staged so it dies on the
runner; last real entry 2026-06-17; Pro's `evaluate_gate()` exists and nothing calls it). What I add
is that this is a named anti-pattern with an explicit external prescription, so the fix has a
reference design rather than needing invention.

Google Cloud, *"MLOps: Continuous delivery and automation pipelines in machine learning"*,
<https://docs.cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning>:

> "Comparing the evaluation metric values produced by your newly trained model to the current model,
> for example, production model, baseline model, or other business-requirement models" … ensure
> "that the new model produces better performance than the current model before promoting it to
> production."

and it explicitly warns to validate "consistent on various segments of the data" — which in our
terms is *per league × market × model_type*, because a pooled improvement that degrades La Liga 2 is
exactly the shape of failure the ledger shows.

The guide places automated model validation at **MLOps Level 1**, i.e. it is the *first* maturity
step past manual, not an advanced practice. `v10/src/models/registry.py::evaluate_gate()` already
implements the hard part (chronological_4block, logloss/brier improvement, ECE, clv_n). Wiring a
caller is HOURS. Given invariant 3 (v9 frozen), the caller belongs in Pro, where a challenger can be
rejected before it ever becomes a v9 candidate for next season.

## F12 — The right statistical instrument for a live ledger (PROVEN, methodological)

The audit is repeatedly forced into a bad position: it must judge "is there an edge?" from a ledger
that is *still accumulating*, using fixed-n confidence intervals computed after choosing which
segments to look at. That is peeking, and it inflates type-I error in exactly the direction that
manufactures "promising" segments (new_format btts SNIPER, n=29, +35.3% ROI, CI −7%..+78%).

The published tool for this is **anytime-valid inference**, and its canonical form is — fittingly —
built on betting:

* Ian Waudby-Smith & Aaditya Ramdas, *"Estimating means of bounded random variables by betting"*,
  arXiv **2010.09686**, <https://arxiv.org/abs/2010.09686> — confidence intervals and
  **time-uniform confidence sequences** for the mean of a bounded random variable via composite
  martingales. Per-bet returns are bounded, so this applies directly to ROI.
* Shubhanshu Shekhar & Aaditya Ramdas, *"On the near-optimality of betting confidence sets for
  bounded means"*, arXiv **2310.01547**, <https://arxiv.org/abs/2310.01547> — those intervals are
  asymptotically optimal in width, so the anytime-validity is nearly free.
* Aaditya Ramdas, Peter Grünwald, Vladimir Vovk, Glenn Shafer, *"Game-theoretic statistics and safe
  anytime-valid inference"*, arXiv **2210.01948**, <https://arxiv.org/abs/2210.01948> — the
  framework review.
* Václav Voráček & Francesco Orabona, *"STaR-Bets"*, arXiv **2505.22422** — tighter adaptive variant.

Practical consequence: a confidence sequence on cumulative ROI per segment can be **monitored
continuously and stopped at any time** without alpha inflation, which is what a paper-then-stake
promotion rule actually needs. It also gives the v11 `MIN_CLV_N = 150` gate a principled
replacement: instead of a fixed count, promote when the confidence sequence's lower bound clears
zero, whenever that happens.

Adjacent and worth one line: Valery Manokhin, *"Report the Floor: A Training-Free Conformal Interval
Is a Mandatory Baseline for Probabilistic Time-Series Forecasting"*, arXiv **2606.09473** — the
argument that a trivial baseline must be reported alongside any learned method, because the trivial
one frequently wins. v11's placebo battery (mean reversion 0.995, fixed anchor 0.753, shuffled
residual 0.711, v9_residual 0.703) is that discipline, correctly applied. **It is the most
methodologically sound thing in this codebase and it should be a required artefact of every future
signal claim, not a one-off audit.**

## F13 — De-vig: power is right; a 2026 alternative exists (SUPPORTED)

v11 uses the power method. That is the correct default and it is the one I used for every market
number in this report.

* penaltyblog, *"From Biased Odds to Fair Probabilities"* (14 Sep 2025),
  <https://pena.lt/y/2025/09/14/from-biased-odds-to-fair-probabilities/> — the multiplicative model
  "was the worst performing on all measures"; the **power method universally outperforms
  multiplicative and outperforms or is comparable to Shin**. For a highly efficient market, several
  margin models produce similarly accurate probabilities.
* Stephen Clarke et al., *"Adjusting Bookmaker's Odds to Allow for Overround"*,
  <https://outlier.bet/wp-content/uploads/2023/08/2017-clarke-adjusting_bookmakers_odds.pdf> — the
  underlying comparison.
* Kaito Goto, Naoya Takeishi, Takehisa Yairi, *"Forecast Sports Outcomes under Efficient Market
  Hypothesis"*, arXiv **2604.17194** (19 Apr 2026), <https://arxiv.org/abs/2604.17194> — 90,014
  football matches, 5 bookmakers. Their **OO-EPC** odds-only method (align to the bookmaker's
  objective of equal profitability-confidence per outcome) "outperforms the existing odds-only
  methods" for the majority of bookmakers; their **FL-GLM** fits *one* parameter for
  favourite-longshot bias and beats multinomial/logistic GLMs for all bookmakers.

For a two-way goals market the choice barely matters — margin is close to symmetric — so this is a
LOW-impact refinement. I flag it only so nobody spends a week on de-vig thinking it is the problem.

## F14 — Record the disagreement in the literature (SUPPORTED)

Do not let F2's clean numbers harden into "the market is efficient, full stop." The literature does
not agree with itself:

* **Efficient:** Hegarty & Whelan (above) — AH ex-ante 3.61% vs realized 3.63%, *t*-tests cannot
  reject equality, no favourite-longshot bias, n=168,460.
* **Not efficient:** Anthony Constantinou, *"Investigating the efficiency of the Asian handicap
  football betting market with ratings and Bayesian networks"*, arXiv **2003.09384**,
  <https://arxiv.org/abs/2003.09384> — 13 EPL seasons; "the AH market is found to **share the
  inefficiencies** of the traditional market", examined at both average and maximum odds and across
  all decision thresholds.
* **Not weak-form efficient, other sports:** the MLB line-movement work (3,681 games, four
  sportsbooks, open→close) finds forecasts "mostly reliable, but there are simple betting strategies
  that would have yielded significant profit" —
  <https://www.researchgate.net/publication/372441761_Inefficient_Forecasts_at_the_Sportsbook_An_Analysis_of_Real-Time_Betting_Line_Movement>.
* **Efficient at the sharp close, with a number:** football-data.co.uk's Pinnacle analysis reports
  r² = 0.997 between closing lines and observed frequencies over 397,935 football games
  (<https://www.football-data.co.uk/blog/pinnacle_efficiency.php> — **not fetched, TLS verification
  failed from this machine**; the figure is as reported in search-result text, so treat it as
  second-hand until someone opens the page).

Where we sit: our market is a **two-way goals total at low-margin books**, which is the family
Hegarty & Whelan measured as efficient and *not* the 1X2 market where the favourite-longshot bias
lives. The inefficiency that is repeatedly replicated is **complexity- and bias-driven** (longshots,
refund structures, in-play overreaction), not "the price is wrong about goals".

**Which bears directly on Bet Builder.** Hegarty & Whelan, *"Returns on Complex Bets: Evidence From
Asian Handicap Betting on Soccer"* (Nov 2023),
<https://www.karlwhelan.com/Papers/ComplexBets.pdf> — loss rates by handicap type, with ex-ante
prediction alongside:

| handicap type | ex-ante loss | realized loss | avg odds |
|---|---|---|---|
| (by type, Football-Data set) | 0.0317 / 0.0356 / 0.0421 / 0.0361 | 0.0324 / 0.0361 / 0.0416 / 0.0357 | ~1.923 |
| (Pinnacle samples) | 0.0293 / 0.0396 / 0.0473 / 0.0399 | 0.0297 / 0.0384 / 0.0482 / 0.0400 | — |

Two readings, both against us: loss rates vary systematically with **pricing complexity**, and the
authors "argue the evidence points more towards gamblers **incorrectly calculating expected loss
rates**" under complexity rather than preferring refund structures. The ex-ante column predicts the
ex-post column to within ~0.001 throughout — the bookmaker's price already knows. Combined with the
existing `project_combo_bets_findings` memory ("structure can't create edge"), the external evidence
says complex bets are where bettors **misestimate** their own loss rate, which is a reason to keep
Bet Builder as a research object and never as an edge source.

## F15 — Data-supply note (SUPPORTED, single source)

Per Liam Henshaw's football-data survey, <https://www.liamhenshaw.com/writing/where-to-find-football-data>:
**FBref lost its Opta data licence in January 2026** — history remains, but the advanced stats no
longer update. Understat covers only the top five leagues plus RFPL, i.e. **none of our bet
leagues**. So any future xG-feature plan for Championship/League One/League Two now requires a paid
vendor, on top of F10's finding that it would not pay. Single source; I could not corroborate it
with a second fetch (WebSearch down).

Vendor landscape, for the record (from <https://the-odds-api.com/sports-odds-data/bookmaker-apis.html>
and the pricing pages fetched above): The Odds API lists **Pinnacle in the `eu` region** and
**Matchbook in `uk` and `eu`**, with the caveat that Pinnacle "odds are from public website which
may incur a delay"; it does not list SBObet or Singbet. That delay caveat is worth knowing before
building a latency-sensitive strategy on it — but it does not affect using Pinnacle as a *benchmark*,
which is F3's use.

---

## WHAT THE EVIDENCE CONSISTENTLY SAYS

**Consistently reported to work**
1. **Start from the price.** Market calibration is "the dominant driver of predictive accuracy"
   (2605.16066). Every profitable published result begins at the price and adds a small correction.
2. **Cross-book price dispersion**, i.e. an outlier against a *deep* consensus (1710.02824).
   Replicated in simulation and with real money, and killed by account limiting rather than by the
   market.
3. **In-play**, where information arrives faster than the price adjusts (2605.16066: 4.5% ROI /
   17,458 bets; 2505.21275: no goal anticipation; 2211.06052: momentum overreaction).
4. **Margin reduction.** The most reliable positive-expectation action in the entire literature is
   paying 2.8% instead of 5.5%. It requires no model.
5. **Complexity-driven biases** — favourite-longshot in 1X2 (7.83% vs 3.63%), refund structures in
   AH, parlays. All are "the bettor misprices, not the book" effects.

**Consistently reported NOT to work**
1. **A structural/statistical model differenced against the price.** Pooling weight 0.000, market
   wins all 7 test seasons (2608.11505). Reproduced here on v9's own metrics (F1).
2. **New football features.** Informative about other models, priced by the market
   (2608.11505 shots-on-target: 0.35 vs goals model, 0.000 vs market; 2101.02104 "mixed").
3. **Accuracy as a proxy for edge.** A model *less* accurate than the market can profit
   (2605.16066); a model *more* accurate can lose (invariant 2, props).
4. **Three-way 1X2 in the traditional market for an unbiased-probability strategy** — it is the
   biased market, which cuts both ways: 7.83% average loss but the bias is at least *known and
   directional*.
5. **Complex/multi-leg bets as an edge source** (ComplexBets: ex-ante predicts ex-post to 0.001).

**Data a credible practitioner would treat as essential, and our status**

| data | why essential | we have it? |
|---|---|---|
| Sharp **closing** line (Pinnacle / exchange) | the benchmark every efficiency test uses; the only credible CLV denominator | **Yes, twice over, unused.** `PC>2.5`/`BFEC>2.5` on disk (F3); purchasable at 5-min resolution from 2020 (F7) |
| Deep multi-book snapshot near kickoff | the input to the one replicated profitable strategy | Partly: 24 books but median 2 per group, 34.9% with ≥3, only 3.79% of Pinnacle rows inside T-60m |
| Exchange/low-margin execution | halves the hurdle rate | Data yes (matchbook 2.76%). Accounts unknown — Open Question 1 |
| Lineups/team news at T-60m | the last big pre-match information event; the market prices it | Features exist (`model.py:91–95`) but collection is 0.6% inside the final hour |
| xG for 2nd divisions | commonly assumed essential | **No** — and F10 says it would not pay, F15 says supply just got worse |

---

## DO NOT BUILD

* **Any new football feature for the pre-match O/U model** — xG, lineup-derived, weather, referee,
  travel. F1 + F10: informative about other models, already in the price. Two local NULLs already
  agree.
* **A "better" pre-match estimator to widen `model_prob − 1/odds`.** F1 shows the subtrahend is the
  better forecast. Improving the minuend from 0.5484 to 0.56 AUC does not cross 0.5848.
* **Any threshold re-tune on the current staked sample.** n=70 settled staked standard bets
  (F5) is INSUFFICIENT_DATA, and re-tuning on observed results is precisely the mechanism (F6) that
  produced Championship SNIPER = 0.07.
* **Bet Builder / combos as an edge source.** ComplexBets: ex-ante loss predicts ex-post loss to
  within 0.001 across four bet types; complexity is where *bettors* misestimate. Keep it as
  research, never as a stake.
* **Player-prop betting.** Invariant 2, and F10/2605.16066 explain the mechanism: prop accuracy is
  real and orthogonal to edge.
* **Backfilling API-Football historical odds.** Established, correct, and unchanged. But do not let
  it generalise to "no history is buyable" — F7.
* **Training on odds to "go market-first".** The residual collapses by construction (brief §3), and
  per F4 six market features are *already* in the model. The correct published objective is the
  opposite: Ondřej Hubáček & Gustav Šír, *"Beating the market with a bad predictive model"*, arXiv
  **2010.12508**, <https://arxiv.org/abs/2010.12508> — "alter the training objective of the
  predictive models to explicitly **decorrelate** them from the market". Blending a *decorrelated*
  residual onto a de-vigged consensus (v11's design) is right; *fitting to* the price is not. These
  are opposite operations and the words "market-first" hide the difference.
* **A bigger OddsAPI plan to fix prop coverage.** Root `CLAUDE.md` is right — those calls came back
  *empty*, not rate-limited. Buy the bigger plan for cadence and history (F7); that is a different
  reason and it should not be conflated.

---

## OPEN QUESTIONS

1. **Can we actually bet matchbook and/or Pinnacle at size from this jurisdiction, and at what
   commission?** F2 says moving from 5.52% best-of-soft to 2.76% is +2.6pp of ROI — larger than any
   effect measured anywhere in this audit, on either side of zero. It is also worthless if the
   accounts do not exist. Matchbook charges commission on net winnings, which must be netted off.
   **This is a business question that dominates a season of modelling work and nobody has asked it.**
2. **Exactly what does a season of true closing snapshots cost from The Odds API for our sport
   keys?** My ~385k-credit estimate has a factor-of-two error bar. One hour with the historical
   endpoint and a real sport-key list settles it, and it decides whether CLV grading becomes
   retrospective-complete.
3. **What is the actual non-NaN coverage of `api_implied_over25` / `api_implied_btts` /
   `bookmaker_overround` in the training matrix?** This decides between F4's two readings — "the
   market is inside the model" vs "60+ weak features dilute the one informative input" — and they
   need opposite fixes. One measurement on the training frame.
4. **What fraction of tips are generated more than 24h before kickoff?** The lineup/formation
   features (`model.py:91–95`) only exist inside ~T-60m, and 81% of odds observations are on
   fixtures >24h out. Either those features are NaN at decision time, or we are deciding before the
   market's most informative event. Both are findings; I could not tell which from here.
5. **Does `side_bets_ledger`'s +18.56u survive a Pinnacle-closing CLV check?** Now computable from
   `PC>2.5` (F3) for the standard leagues. It is the one segment where our data and the strongest
   external result agree, and it deserves the sharpest available test rather than the softest.

---

## SOURCES

Academic / preprint
* Pitcan, *Does a Structural Model Add Anything to the Closing Price?* — <https://arxiv.org/abs/2608.11505>
* Clegg, Song & Cartlidge, *A market-calibrated AFT model for in-play football forecasting* — <https://arxiv.org/abs/2605.16066>
* Goto, Takeishi & Yairi, *Forecast Sports Outcomes under EMH* — <https://arxiv.org/abs/2604.17194>
* Kaunitz, Zhong & Kreiner, *Beating the bookies with their own numbers* — <https://arxiv.org/abs/1710.02824>
* Hubáček & Šír, *Beating the market with a bad predictive model* — <https://arxiv.org/abs/2010.12508>
* Constantinou, *Efficiency of the Asian handicap market* — <https://arxiv.org/abs/2003.09384>
* Wheatcroft & Sienkiewicz, *Predicting Shot Success in Football* — <https://arxiv.org/abs/2101.02104>
* Wheatcroft, *Forecasting football matches by predicting match statistics* — <https://arxiv.org/abs/2001.09097>
* Winkelmann & Deutscher, *Do Betting Markets Sense a Goal Coming?* — <https://arxiv.org/abs/2505.21275>
* Ötting, Deutscher, Singleton & De Angelis, *Gambling on Momentum* — <https://arxiv.org/abs/2211.06052>
* Hegarty & Whelan, *A Tale of Two Markets* — <https://mpra.ub.uni-muenchen.de/116925/> · PDF <https://mpra.ub.uni-muenchen.de/116925/1/MPRA_paper_116925.pdf> · IJF listing <https://ideas.repec.org/a/eee/intfor/v41y2025i2p803-820.html>
* Hegarty & Whelan, *Returns on Complex Bets* — <https://www.karlwhelan.com/Papers/ComplexBets.pdf>
* Hegarty & Whelan, *Comparing two methods for testing the efficiency of sports betting markets* — <https://mpra.ub.uni-muenchen.de/121382/>
* Waudby-Smith & Ramdas, *Estimating means of bounded random variables by betting* — <https://arxiv.org/abs/2010.09686>
* Shekhar & Ramdas, *Near-optimality of betting confidence sets* — <https://arxiv.org/abs/2310.01547>
* Ramdas, Grünwald, Vovk & Shafer, *Game-theoretic statistics and safe anytime-valid inference* — <https://arxiv.org/abs/2210.01948>
* Voráček & Orabona, *STaR-Bets* — <https://arxiv.org/abs/2505.22422>
* Manokhin, *Report the Floor* — <https://arxiv.org/abs/2606.09473>
* *Inefficient Forecasts at the Sportsbook* (MLB line movement) — <https://www.researchgate.net/publication/372441761_Inefficient_Forecasts_at_the_Sportsbook_An_Analysis_of_Real-Time_Betting_Line_Movement>

Methods / practitioner
* Google Cloud, *MLOps: Continuous delivery and automation pipelines in ML* — <https://docs.cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning>
* penaltyblog, *From Biased Odds to Fair Probabilities* — <https://pena.lt/y/2025/09/14/from-biased-odds-to-fair-probabilities/>
* Clarke et al., *Adjusting Bookmaker's Odds to Allow for Overround* — <https://outlier.bet/wp-content/uploads/2023/08/2017-clarke-adjusting_bookmakers_odds.pdf>
* Buchdahl on CLV (≥1,000 bets, p<0.001) — <https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl>
* football-data.co.uk Pinnacle efficiency (**not fetched — TLS failure; second-hand**) — <https://www.football-data.co.uk/blog/pinnacle_efficiency.php>

Vendors
* The Odds API pricing — <https://the-odds-api.com/#get-access>
* The Odds API historical odds guide — <https://the-odds-api.com/liveapi/guides/v4/#get-historical-odds>
* The Odds API bookmaker coverage — <https://the-odds-api.com/sports-odds-data/bookmaker-apis.html>
* Henshaw, *Where to find football data* — <https://www.liamhenshaw.com/writing/where-to-find-football-data>
* LSports, *How much does sports data cost in 2026* — <https://www.lsports.eu/blog/sports-data-cost/>

Local evidence computed or read this run
* `v9/models/metrics_model_v9_standard.json` — logistic 0.68833/0.5484, gbm 0.69153/0.5232, lgbm 0.69052/0.5288, n_test 4450
* `v9/models/best_params_standard.json` — Championship approved sniper_th 0.07 / marksman_th 0.05; Serie B 0.12/0.10
* `v9/src/betting.py:124–137, 140–195, 198–213`; `v9/config.py:281–287`; `v9/src/ledger.py:163–208`
* `v9/src/data_loader.py:49–52, 112–118, 143–166, 214–218`; `v9/src/model.py:55–121`
* `v9/output/bets_ledger.csv` — 5,176 rows; 70 settled staked standard bets, split in F5
* `data/football_data/*/*.csv` — 16,655 standard matches 2019-07-26→2026-05-18; market baselines in F1
* `v10/data/season_2026_27/book_odds_snapshots` — 143,799 rows, 24 books; overrounds and sharp coverage in F2/F9

# AGENT 4 — Market / Microstructure Audit

**Date:** 2026-09-10
**Scope:** de-vig, best-price selection, consensus, opening/closing, dispersion, line movement,
CLV, stale books, soft-vs-sharp, panel churn.
**Primary data:** `v10/data/season_2026_27/book_odds_snapshots/` (143,799 rows) and the live
`v9/output/book_odds_snapshots.csv` (144,982 rows, 24 bookmakers, 2026-08-19 → 2026-09-10),
joined to `v9/output/bets_ledger.csv`, `v9/odds_history_v9.json`,
`v10/data/season_2026_27/settlements/`.
**Rules honoured:** read-only on v9 and wowza-v11; nothing fitted on the outcomes it is
evaluated against; every decision set held fixed in every counterfactual.

---

## HEADLINE

**v9 prices every bet off whichever bookmaker OddsAPI happens to list first in the response.
It captures the best available price on only 46.6% of bets and gives away a mean 1.91% of the
price. Taking the best of a four-book fixed panel — on exactly the same bets, same tiers, same
decisions — is worth +2.03 ROI points (95% CI +1.41 to +2.73pp, n=217 settled). That is larger
than the entire measured edge of every profitable segment in the ledger (+2.5%, +2.2%), which
means the best-documented positive number in this whole system is currently being paid to
bookmakers rather than earned by the model.**

Second-order but nearly as important: `book_odds_snapshots` is a **change-log, not a snapshot
panel**. Read as a panel it says "median 2 books, 34.9% with ≥3" (the audit seed's numbers).
Forward-filled correctly it is a **median 12-book panel on OU25 with 97.4% of instants at ≥3
books**. Every conclusion about consensus feasibility and about how much of "movement" is noise
flips on this distinction.

---

## FINDINGS TABLE

| # | Finding | Evidence | Conf | Impact | Fix |
|---|---|---|---|---|---|
| F1 | v9 takes the first-listed book's price, not the best; 2.03pp ROI given away | `v9/src/predict.py:136-139`; best-price on 46.6% of 311 matched bets; paired delta +0.0203u/bet CI [+0.0141,+0.0273], n=217 | PROVEN | CRITICAL | DAYS |
| F2 | `book_odds_snapshots` is a change-log; read as a panel it understates books 6× | `v9/src/predict.py:199-200`; 0 of 143,799 rows equal the prior obs of the same series; ffill panel median 12 books (OU25) vs 2 raw | PROVEN | CRITICAL | HOURS |
| F3 | Panel churn is 18.1% of consensus-movement variance — not the dominant term, once F2 is fixed | var(churn)/var(measured)=0.1814 on 29,261 ffill transitions; 0.4205 and 42% zero-common-books on the raw change-log | PROVEN | HIGH | — |
| F4 | The movement series is not robust to panel definition: fixed vs changing panel corr 0.747 | var(diff)/var(changing)=0.4903, mean\|diff\| = 64.4% of mean\|movement\|, n=29,261 | PROVEN | HIGH | DAYS |
| F5 | CLV history is corrupt before September 2026 and worthless where it exists | mean `clv_pct`: NF Jul +42.1%, Aug +11.8%, Sep +0.1%; mean\|clv\| 23.1% against a market spanning 8.7%; in the verifiable era n=319 closing is 100% in-range and CLV = −0.26%/+0.18% | PROVEN | CRITICAL | DAYS |
| F6 | The "closing line" is not the close: 42.6% of series stop >30 min before KO, 16.2% stop >24h before | last captured price per (fixture,market), n=1,847: p25 26 min, median 109 min, p75 2,253 min | PROVEN | HIGH | DAYS |
| F7 | v9's drift signal misclassifies Confirmed/Conflicted through book switching | selected book changes open→close on 18.1% of 265 fixtures; on those 56.1% of drift magnitude is the switch and 21.1% of signs flip | PROVEN | MEDIUM | DAYS |
| F8 | The drift signal is half the size of the cross-sectional noise it is read through | mean\|over_drift\| = 4.32% of price vs median single-instant cross-book range 8.67% on OU25 | PROVEN | HIGH | — |
| F9 | A 4-book fixed panel recovers 99.4% of the best OU25 price | greedy panel {betsson, onexbet, unibet_se, matchbook}: 0.9936 best-price recovery, 0.9996 instant coverage, 15,264 instants | PROVEN | HIGH | DAYS |
| F10 | De-vig sophistication buys nothing at OU25 — do not invest there | median consensus Brier 0.23622 vs `1/best_odds` with **no de-vig** 0.23641 (Δ 0.0002); median vs mean vs trimmed all within 0.00024; n=291 | PROVEN | MEDIUM | — |
| F11 | The market does carry information, and its movement is weakly directional — nothing like 0.995 | close 0.23622 < open 0.23948 < base-rate 0.24454 Brier; open→close toward-rate 56.4%, corr(move,y)=0.088, n=291 | PROVEN | HIGH | — |
| F12 | 5 of 16 OU25 books are frozen ~75% of the time the consensus moves, yet enter the median at equal weight | williamhill 0.762, leovegas_se 0.754, unibet_se 0.752, unibet_nl 0.740, betonlineag 0.781 vs betsson/nordicbet 0.251 | PROVEN | MEDIUM | DAYS |
| F13 | Pinnacle leads, gtbets/betonlineag follow — but Pinnacle covers only 34.3% of OU25 fixtures | lead−follow: pinnacle +0.120 (n≈212 each, z≈2.5), matchbook +0.068, gtbets −0.189, betonlineag −0.138 | SUPPORTED | MEDIUM | WEEKS |
| F14 | BTTS and O/U are priced by nearly disjoint book sets; the only exchange is effectively absent | 7 books quote BTTS only, 10 quote O/U only; `betfair_ex_uk` on 4.0% of BTTS and 0% of OU → `consensus.py` "exchange first" branch is dead | PROVEN | MEDIUM | HOURS |
| F15 | Mixed-book Over/Under pairs — my own hypothesis — do **not** occur | 0 of 2,490 `odds_history_v9.json` snapshots had Over and Under from different books | PROVEN | LOW | — |
| F16 | `bets_ledger` mixes 260 backtest rows into the headline loss | settled: live n=788 −68.75u (ROI −8.7%), backtest n=260 −19.58u; the −91.63u headline is a blend | PROVEN | MEDIUM | HOURS |

---

## F1 — Best-price execution: the largest measured number in this audit

`v9/src/predict.py:136-139`:

```python
if pt == 2.5 and nm == "Over"  and not ov25:  ov25 = pr
if pt == 2.5 and nm == "Under" and not un25:  un25 = pr
```

The comment at `predict.py:117` is explicit that "the `not ov25` guards below keep only the
FIRST book and discard the rest". `regions=eu` (`predict.py:65`). So the price behind every
edge, tier, stake, drift reading and CLV number is *the first bookmaker OddsAPI happened to
list*. Not the best price. Not a consensus. Not a chosen book.

Which book that is, measured by matching all 2,490 `odds_history_v9.json` snapshots against the
per-book panel (every one resolved to exactly one book's two-sided pair):

| book | share of v9's prices |
|---|---|
| onexbet | 40.0% |
| codere_it | 18.4% |
| coolbet | 12.7% |
| williamhill | 8.1% |
| pinnacle | 7.2% |
| pmu_fr | 4.9% |
| 8 others | 8.7% |

**Execution quality**, at tip time, against the forward-filled per-book panel:

- v9's odds equalled the best available on **46.6%** of 311 matched ledger bets.
- Mean shortfall **1.909%** of price (median 0.847%, p90 5.991%).
- On 2,490 history snapshots the OVER side alone: v9 = best 32.5% of the time, mean gap 0.055
  decimal = **3.07%** of price.

**Counterfactual, decision set held completely fixed** (same bets, same sides, same tiers —
only the price replaced by the best in the panel at that same instant), flat 1u, settled only:

| segment | n | as-is | best-price | delta |
|---|---|---|---|---|
| ALL | 217 | −20.90u (−9.63%) | −16.50u (−7.60%) | **+4.40u** |
| SNIPER | 10 | +2.41u | +2.51u | +0.10u |
| MARKSMAN | 66 | −15.10u (−22.88%) | −13.56u (−20.55%) | +1.54u |
| VALUABLE | 141 | −8.21u (−5.82%) | −5.45u (−3.87%) | +2.76u |
| standard | 95 | −18.76u (−19.75%) | −17.02u (−17.92%) | +1.74u |
| new_format | 122 | −2.14u (−1.75%) | **+0.52u (+0.43%)** | +2.66u |

Paired bootstrap on the per-bet delta (4,000 resamples): **+0.02028 u/bet, 95% CI
[+0.01406, +0.02733]**, i.e. **+2.03 ROI points, CI [+1.41, +2.73]pp**.

Adversarial notes on my own number, in order of seriousness:

1. n=217 is below the seed's 250 bar. But this is **not a parameter change and not a threshold
   fitted on these results** — it is an execution measurement. `best ≥ entry` on every single
   row by construction, so the sign is certain; only the magnitude has sampling error, and the
   *paired* CI is tight because the outcome noise cancels. The shortfall distribution itself is
   measured on n=311.
2. The delta is an upper bound on realised benefit: a real account cannot always get the
   headline price, and taking the best price would also *raise* `edge_pct` and therefore change
   which bets qualify. I deliberately did not model that — changing the decision set would be
   retrospective tuning (invariant 6). The number quoted is "same bets, better price".
3. Only 448 of 5,176 ledger rows join the panel (per-book capture starts 2026-08-19 and covers
   OU25 only). This is an August–September estimate, not a season one.

**F9 makes this cheap.** A greedy fixed panel needs only four accounts:

| panel size | added book | best-price recovery | instant coverage |
|---|---|---|---|
| 1 | betsson | 0.9633 | 0.9397 |
| 2 | + onexbet | 0.9761 | 0.9903 |
| 3 | + unibet_se | 0.9821 | 0.9996 |
| 4 | + matchbook | **0.9936** | 0.9996 |
| 5 | + pinnacle | 0.9956 | 1.0000 |

Nothing beyond five books is worth an account. Note the tension with F13: the four
best-*price* books are not the four best-*information* books (pinnacle and matchbook lead;
betsson and onexbet are volume books that simply post longer prices). Consensus and execution
must be sourced separately — which is exactly what `v10/src/market/consensus.py:20-24` already
insists on in its docstring, and which v9 does not do at all.

---

## F2 — The table is a change-log. This invalidates the seed's panel statistics.

`v9/src/predict.py:196-202`:

```python
_key = ["match_date", "match", "market", "side", "bookmaker"]
_bn = _bn.sort_values(_key + ["snapshot_ts"])
_prev = _bn.groupby(_key)["odds"].shift()
_bn = _bn[_bn["odds"].ne(_prev)].sort_values("snapshot_ts")
```

A book that re-quotes the same price has the observation **deleted**. Confirmed empirically:
**0 of 143,799 rows** equal the previous observation of the same
(fixture, market, side, bookmaker). `snapshot_ts` therefore does **not** mean "this book was
quoting this price at this instant" — it means "this book changed to this price at this
instant". The field name and the table name both say the opposite.

Consequences, all of which look like data poverty and are not:

| statistic | read as a panel (the seed) | forward-filled (correct) |
|---|---|---|
| median de-viggable books per instant, OU25 | 2 | **12** |
| share of instants with ≥3 books | 34.9% | **97.4%** |
| share with ≥5 books | — | 89.9% |
| share with ≥8 books | — | 71.1% |
| mean panel size, all markets | 2.47 | 9.39 |
| transitions with zero books in common | 42.4% | **0.000%** |

Distinct books ever seen per fixture-market: median 9 overall, **12 for OU25**, 9 for BTTS.
The panel is not thin. The **change-log is sparse and the panel is dense**, and reading one for
the other is the single largest interpretive trap in this dataset.

Two caveats on forward-fill, stated so nobody over-trusts it: (a) a book that *withdraws* a
market is indistinguishable from a book that holds its price, so ffill will carry dead quotes
forward — this is the same limitation that makes F12's staleness numbers an upper bound; (b)
the change-log genuinely loses the information needed to fix (a), and no reprocessing can
recover it. **The fix is upstream: capture presence, not just change.**

**Recommended action (Pro-side, v9 untouched):** a single loader in `v10/src/market/` that
forward-fills to a presence-aware panel, plus one added column at capture time on the Pro side
(`last_seen_ts` per book-series) so presence and price are separable going forward. Until that
loader exists, every consumer of `book_odds_snapshots` will reproduce the seed's error.

---

## F3, F4, F8 — How much of "movement" is measurement, not market

The remit asked for this single number. It has three honest values depending on which series
you mean.

**(a) The correctly reconstructed consensus** (29,261 consecutive-snapshot transitions,
ffill panel, per-book power de-vig, median across books):

| series | sd measured | sd common-panel | sd churn | var(churn)/var(meas) | churn share of \|movement\| |
|---|---|---|---|---|---|
| median consensus | 0.00626 | 0.00565 | 0.00267 | **0.1814** | 17.1% |
| mean consensus | 0.00531 | 0.00491 | 0.00191 | 0.1292 | 14.9% |
| best over odds | 0.03477 | 0.03180 | 0.01488 | 0.1833 | 13.2% |

So **~18% of consensus-movement variance is panel churn** — material, worth correcting, not
fatal. The seed's implied "our price series is dominated by measurement noise" is
**not supported at the consensus level**.

**(b) The raw change-log read as a panel** — which is what any naive consumer computes:
var(churn)/var(measured) = **0.4205** for the median and **0.5337** for the best price, with
42.4% of transitions sharing no book at all. Here the seed's characterisation is right, and it
is right *because of F2*.

**(c) v9's actual series**, which is neither of the above. Measured directly on
`odds_history_v9.json` against the per-book panel, 265 fixtures with a reconstructable
same-book close:

- The selected book **changes between open and close on 18.1%** of fixtures.
- Overall var(book-switch component)/var(v9 drift) = **0.1288**; corr(v9 drift, same-book
  drift) = 0.934.
- On switched fixtures: mean|v9 drift| 0.1310 of which **56.1% is the book switch**, not price
  movement.
- **Sign disagreement** (v9 says shortened, the same book says lengthened, or vice versa):
  3.4% of all fixtures with material drift, **21.1% of switched fixtures**.

Since `drift_signal` is Confirmed/Conflicted purely from the sign of `over_drift`/`under_drift`
(`v9/src/drift.py:178`), roughly **3.8% of fixtures carry an inverted drift verdict** — and
per the audit seed, `VALUABLE → MARKSMAN` promotion via `_apply_drift_adjustment` has **no edge
floor at all**, so an inverted verdict promotes a real bet with real money. I want to be
adversarial about my own finding here: 3.8% is **not** the explanation for the −13.8u on
standard MARKSMAN. The missing edge floor is. Book switching is a second-order contaminant of
a signal whose first-order problem is that it can promote a 3.26%-edge bet at all.

**(d) The scale comparison that matters most (F8).** Mean|v9 over_drift| over a fixture's whole
life is **4.32% of the opening price**. The median cross-book *range* at a **single instant** on
OU25 is **8.67%** of price (p90 13.76%), sd across books 2.49%.

> The entire signal v9 extracts from line movement is **half the size of the disagreement
> between bookmakers at one moment in time.** Measuring it through one arbitrarily-chosen book
> is measuring a 4% effect with an 9%-wide ruler.

This is the microstructure reason the seed's placebo battery came out the way it did. It does
not require the market to be uninformative — see F11, where the market clearly *is*
informative. It requires only that v9's *observation* of the market be noisier than the thing
observed.

**F4 — the movement series is not robust to panel definition.** Holding the panel fixed to the
books valid at *every* snapshot of a fixture (mean 5.91 books) versus the growing panel (mean
9.39): correlation of the two median-movement series is only **0.747**, var(difference)/var =
**0.4903**, mean|difference| = **64.4%** of mean|movement|. Two defensible definitions of "the
market moved" share barely half their variance. Any regression whose regressor is "line
movement" therefore has a specification choice with as much leverage as the coefficient being
estimated — which is a much stronger form of the seed's warning, and it is measured rather than
asserted.

---

## F5 — CLV: corrupt before September, and zero where it is verifiable

`v9/src/clv_capture.py:13-14` defines `clv_pct = odds_bet / odds_close − 1`. `odds_close` comes
from `update_results._closing_odds` (`v9/update_results.py:298`), which tries
`odds_history_v9.json`'s last snapshot then falls back to the four CSV archives
(`update_results.py:227-232`), taking `sort_values("snapshot_ts").iloc[-1]` and resolving team
names with the substring/first-word matcher `_names_match` — the exact matcher root
`CLAUDE.md` invariant 11 warns about.

`bets_ledger.clv_pct`, n=685: mean **+12.19%**, sd **39.28%**, mean|clv| **23.08%**.

**That is physically impossible.** The whole 11-book market on OU25 spans a median 8.67% of
price at any instant, and the mean absolute consensus movement per transition is 0.28
probability points. A mean |CLV| of 23% cannot be a property of the market. It is a property of
the measurement.

Where the corruption lives:

| month | new_format n / mean clv | standard n / mean clv |
|---|---|---|
| 2026-05 | 26 / −2.4% | 24 / +0.2% |
| 2026-06 | 23 / −0.2% | 1 / 0.0% |
| **2026-07** | **115 / +42.1%** | — |
| **2026-08** | **295 / +11.8%** | 82 / +2.0% |
| 2026-09 | 61 / +0.1% | 54 / −1.5% |

Worked examples (`side=UNDER`, entry vs stored close): New York Red Bulls v Orlando City
3.35→1.44 (clv +132.6%); San Jose v Orlando City 3.35→1.44 (+132.6%); FC Cincinnati v Vancouver
3.15→1.40 (+125.0%); Viking FK v Sarpsborg FK 3.15→1.40 (+125.0%). The archive for FC Cincinnati
v Vancouver actually holds `under25` 1.44→1.40 and `over25` 2.62→2.75 — a coherent market in
which an Under 2.5 at 3.15 does not exist. The sign pattern is systematic and diagnostic:
new_format OVER mean **−13.80%**, new_format UNDER mean **+27.87%**, standard OVER +2.24%,
standard UNDER −0.32%. A single mis-resolution would not produce opposite systematic signs on
the two sides of the same market in one model track only.

**The falsification test that settles it.** For every ledger row with a CLV and a per-book panel
for the same fixture and side (n=319, i.e. the 2026-08-19-onward era):

- stored `closing_odds` inside the observed per-book [min, max] over the whole life of the
  fixture: **100.0%** (0 exceptions).
- entry `odds` inside range: 97.8% (100% for standard, 96.6% for new_format).
- mean CLV in that era: new_format **−0.26%** (n=204), standard **+0.18%** (n=115).

So the pipeline is sound *now*, and the July–August numbers are unrecoverable garbage from
before it was. Two consequences:

1. **410 of 521 new-format CLV rows (78.7%) sit in the corrupt window.** `wowza-v11`'s
   `BET`/`PAPER` gate requires a segment's clean CLV count ≥ `MIN_CLV_N` (150) **and positive**.
   Fed this history, the gate would flip a new-format segment to `BET` on a +42% mean CLV that
   is an artefact. The gate that exists to prevent betting without evidence would authorise
   betting *because of* corrupt evidence. **Quarantine all CLV records with `match_date` before
   2026-09-01 before any CLV gate is wired to anything.**
2. In the only period where the closing price is independently verifiable, **v9 beats the close
   by −0.26% / +0.18% — i.e. by nothing.** There is no CLV edge to find in the current record.
   Combined with F1, the interpretation is unpleasant and clean: v9 is not beating the close
   *and* is not taking the best price, which are the two independent ways a value bettor can be
   right.

Also worth recording, since it will otherwise be rediscovered: `_closing_for_market`
(`update_results.py:258`) iterates the archives in `_ARCHIVE_FILES` order and **returns on the
first hit**, so which archive supplies a close is file order, not recency. The comment at
`update_results.py:233` claims the ordering makes the dense archive win, which is true only
when the fixture is present there — and the six worst-CLV fixtures I traced had **zero**
exact-name rows in `newformat_odds_dense.csv`. Only 53.8% of new-format ledger rows have an
exact-name archive row at all.

---

## F6 — The "closing line" is not the close

Recency of the last captured price per (fixture, market), n=1,847:

| percentile | minutes before kickoff |
|---|---|
| p10 | 6 |
| p25 | 26 |
| median | **109** |
| p75 | **2,253** (37.5 h) |
| p90 | 4,802 (80 h) |

| threshold | share of series whose "close" is older than that |
|---|---|
| >30 min | **42.6%** |
| >1 h | 38.0% |
| >3 h | 24.3% |
| >24 h | **16.2%** |

Reassuringly, **0.0%** of the 143,799 observations are post-kickoff (`is_post_kickoff` all
False; minimum `minutes_to_kickoff` of a last observation is ≥0 across all 3,694 series), so the
in-play contamination risk that `predict.py:88-91` guards against does not leak into this table.
The problem is the other end: for a sixth of fixtures the price called "closing" predates
kickoff by more than a day, which is before team news. CLV computed against a T−37h price is
not CLV. This compounds F5: even the September-era CLV of ≈0 is measured against a reference
that is frequently not the close.

This also reframes the seed's near-kickoff coverage numbers (T−1h 32.6%, T−30m 14.5%). Those
are not merely a data-completeness issue — they are the direct cause of a CLV metric that
cannot mean what its name says, on a quarter of the book.

---

## F10, F11 — What the market is actually worth, and where not to spend effort

Estimator horse race at the **last pre-kickoff snapshot**, scored against realised outcomes
derived from `v10/data/season_2026_27/settlements/` (1,153 labelled fixture-markets; 291 OU25
and 85 BTTS had ≥3 de-viggable books). No estimator was tuned; all are fixed formulas.

**OU25, n=291, base rate 0.5739:**

| estimator | Brier | LogLoss | mean p |
|---|---|---|---|
| **median consensus (power de-vig)** | **0.23622** | **0.66437** | 0.5575 |
| trimmed mean (drop min & max) | 0.23639 | 0.66471 | 0.5571 |
| `1/best_odds`, **no de-vig at all** | 0.23641 | 0.66467 | 0.5629 |
| mean consensus | 0.23646 | 0.66487 | 0.5573 |
| **OPENING** median consensus | 0.23948 | 0.67119 | 0.5472 |
| base-rate constant | 0.24454 | 0.68219 | 0.5739 |
| matchbook only (n=212, base 0.533) | 0.24629 | — | 0.5249 |
| pinnacle only (n=77, base 0.533) | 0.24836 | — | 0.4990 |

**Three results, in descending order of how much money they save:**

1. **De-vig sophistication is worth 0.0002 Brier.** Properly power-de-vigged 12-book median
   consensus (0.23622) versus the reciprocal of the single best price with **no de-vig
   whatsoever** (0.23641). Median vs mean vs trimmed spans 0.00024. Per-book, power and
   proportional de-vig differ by 0.003–0.012 in probability, and only **0.19%** of two-sided
   quotes are rejected by `MAX_OVERROUND = 1.25` (`v10/src/market/devig.py:31`). At a 2.5-goal
   line the market sits near 50/50, where every margin-allocation method converges. **Do not
   build de-vig refinements, trimmed-consensus variants, or overround-weighted estimators.**
   The existing `v10/src/market/devig.py` and `consensus.py` are already better than the
   problem requires.
2. **The market carries real information and the close carries more than the open.** Closing
   consensus 0.23622 < opening consensus 0.23948 < base-rate 0.24454. The market beats the base
   rate by 0.0083 Brier and the close beats the open by 0.0033.
3. **But the movement is only weakly directional.** Open→close consensus: mean move +0.0103
   (drifts toward Over), corr(move, outcome) = **0.088**, **toward-rate 56.4%** (n=291).

Point 3 is the direct microstructure counterpart to the seed's placebo battery. The honest
toward-rate of the *actual* consensus price series, computed over 291 settled fixture-markets,
is **0.564**. Any construct that scores **0.995** — mean reversion, a constant, a shuffled
residual — is not measuring the market; a real price series cannot be predicted at 99.5%
directional accuracy by its own negated lag. **F11 therefore corroborates the seed's verdict
that the 0.995 is an artefact of `p_market(t)` appearing on both sides with opposite signs, and
supplies the missing benchmark: the number a real market-movement predictor should be compared
against is 0.564, not 0.5.**

**Book-specific close vs panel close** (the remit's explicit question), on the common
pinnacle-present subsample, n=77, base 0.5325: panel median 0.24363, trimmed 0.24465,
matchbook 0.24530, `1/best_odds` 0.24681, pinnacle 0.24836. The panel median is nominally best
but **n=77 → INSUFFICIENT_DATA**. There is no evidence that a sharp-book close beats the panel
close, and no evidence against it. Do not switch the closing reference on this.

**Dispersion as a signal** (n=97 per tercile, OU25): tight range → base rate 0.680, Brier 0.215;
mid → 0.412, 0.253; wide → 0.629, 0.241. The base rates differ wildly across terciles, so the
Brier differences are confounded by where in probability space each bucket sits. **n<250,
non-monotone, confounded → INSUFFICIENT_DATA.** `consensus.py:33-35` already says dispersion is
"collected but NOT interpreted"; that remains the correct posture and this audit adds no reason
to change it.

---

## F12, F13, F14 — Stale books, leaders, and the panel that isn't one panel

**F12 — staleness.** Share of occasions on which a book did **not** move while the median
consensus moved more than 0.4 probability points (OU25):

| book | frozen when consensus moves | mean \|deviation from consensus\| | n |
|---|---|---|---|
| betonlineag | 0.781 | 0.0114 | 305 |
| williamhill | 0.762 | 0.0085 | 1,506 |
| leovegas_se | 0.754 | 0.0146 | 981 |
| unibet_se | 0.752 | 0.0142 | 981 |
| unibet_nl | 0.740 | 0.0141 | 846 |
| pmu_fr | 0.709 | 0.0176 | 663 |
| pinnacle | 0.616 | 0.0096 | 386 |
| tipico_de | 0.549 | 0.0118 | 799 |
| onexbet | 0.396 | 0.0083 | 1,209 |
| matchbook | 0.309 | 0.0086 | 404 |
| nordicbet | 0.251 | 0.0039 | 1,567 |
| betsson | 0.251 | 0.0039 | 1,567 |

Five books are frozen roughly three times in four when the market moves, and they enter the
median with **the same weight** as betsson and nordicbet, which move three times in four. This
is a mechanism, and it is the most plausible remaining explanation for the 18% churn variance in
F3 having any structure at all. It is **PLAUSIBLE, not proven**, that a staleness-weighted
consensus would be a better probability estimate — and F10 sets the ceiling on how much that
could possibly be worth (≈0.0008 Brier, the whole gap from base rate to best estimator), so
this is a small prize. Note also the ffill caveat from F2: "frozen" and "withdrew the market"
are indistinguishable in this data, so these are **upper bounds on staleness**.

**F13 — leader/follower.** Sign agreement between a book's move at *t* and the consensus move
at *t+1* (lead) versus at *t−1* (follow), OU25, both n≥80:

| book | n lead | lead rate | n follow | follow rate | lead − follow |
|---|---|---|---|---|---|
| pinnacle | 214 | 0.682 | 210 | 0.562 | **+0.120** |
| matchbook | 728 | 0.607 | 669 | 0.540 | +0.068 |
| tipico_de | 556 | 0.678 | 540 | 0.643 | +0.036 |
| coolbet | 273 | 0.700 | 286 | 0.678 | +0.021 |
| onexbet | 1,352 | 0.601 | 1,344 | 0.583 | +0.018 |
| betsson | 1,335 | 0.523 | 1,321 | 0.509 | +0.014 |
| nordicbet | 1,328 | 0.523 | 1,313 | 0.510 | +0.012 |
| williamhill | 393 | 0.735 | 352 | 0.778 | −0.043 |
| betonlineag | 99 | 0.626 | 106 | 0.764 | −0.138 |
| gtbets | 175 | 0.697 | 210 | 0.886 | **−0.189** |

Pinnacle leads (z ≈ 2.5 on the difference of two independent proportions), matchbook second —
the textbook result, and reassuring for data quality. gtbets and betonlineag are pure followers.
**Two caveats I cannot remove:** each book is inside the consensus it is being compared to, and
books differ enormously in how often they reprice (F12), so both rates are confounded by
repricing frequency — which is why I report lead−follow rather than either rate alone. And
Pinnacle is present on only **34.3%** of OU25 fixtures and **37.7%** of BTTS, so a
Pinnacle-anchored consensus would have two-thirds coverage. SUPPORTED, and the natural next
test is whether a Pinnacle move at *t* predicts the *outcome* rather than the consensus — that
needs more settled fixtures than exist yet.

**F14 — "24 bookmakers" is not 24 per market.** The panel is market-segmented, almost
disjointly:

- **BTTS only** (7): leovegas, virginbet, livescorebet, ladbrokes_uk, coral, betfred_uk,
  betfair_ex_uk — all UK books, consistent with `CLAUDE.md`'s note that UK books are where
  English football depth lives.
- **O/U only** (10): betsson, nordicbet, tipico_de, unibet_se, unibet_nl, leovegas_se,
  codere_it, pmu_fr, coolbet, betonlineag, gtbets, betanysports.
- **Both** (4): onexbet, matchbook, pinnacle, williamhill (williamhill: BTTS + OU25 only).

Per-market medians of books-ever-seen: **OU25 12, BTTS 9, OU35 8, OU15 4**. OU15 at 4 books is
genuinely thin and should not be treated as having a consensus.

`betfair_ex_uk` — the **only exchange** in the feed — appears on 4.0% of BTTS fixtures and 0% of
O/U, and 13.6% of its two-sided quotes are rejected by the overround bounds (p95 overround
1.98, i.e. mispaired quotes). `v10/src/market/consensus.py:154-158` prefers an exchange price
above everything else, on the sound reasoning that a traded price carries no margin to guess at.
**That branch is effectively dead code** — it can fire on at most 4% of BTTS fixtures and never
on O/U. Either source a real exchange feed or stop reasoning as though one is available.

**Margin ladder** (median overround per book across all two-sided quotes, n in table) — useful
for picking the sharp anchor and worth committing somewhere durable:

matchbook 1.0257 · pinnacle 1.0431 · gtbets 1.0602 · coolbet 1.0604 · betanysports 1.0610 ·
betonlineag 1.0611 · onexbet 1.0627 · nordicbet/betsson 1.0690/1.0699 · williamhill 1.0761 ·
betfred_uk 1.0780 · mybookieag/coral/ladbrokes_uk ≈1.079 · unibet_se 1.0807 · tipico_de 1.0824 ·
unibet_nl 1.0837 · leovegas_se 1.0875 · virginbet/livescorebet ≈1.089 · codere_it 1.0905 ·
leovegas 1.1011 · **pmu_fr 1.1371**.

Market-level overround: BTTS 1.0766 mean, OU25 1.0706, OU35 1.0687, OU15 1.0680. There is a
**4.6-percentage-point spread in margin** between matchbook and pmu_fr on the same market —
which is another way of stating F1: 12.7% of v9's prices came from coolbet and 4.9% from pmu_fr,
picked by API response order rather than by margin.

---

## F16 — The headline loss is a blend of live and backtest

`bets_ledger.csv` `source`: **backtest 4,115 / live 1,061** rows. Settled:

| source | n | win rate | P/L |
|---|---|---|---|
| live | 788 | 40.86% | **−68.75u** |
| backtest | 260 | 40.38% | −19.58u |
| total | 1,048 | 40.84% | −88.33u |

The seed's "1,159 settled, 41% win, −91.63 units" is this total (the file has been appended
since). **The live-money-shaped number is −68.75u on 788 bets, ROI −8.7%**; a quarter of the
headline loss is simulated. Live splits new_format −35.92u (n=626) / standard −29.83u (n=159).
This does not make the picture better — it makes it *narrower*, and it matters because the
backtest rows have no drift history, no per-book panel and no CLV, so mixing them dilutes every
diagnostic computed off the ledger.

I did **not** resolve the seed's open question (why `edge_pct` ≈ 9% appears on rows tiered
SNIPER). One lead for whoever takes it: `v10/data/season_2026_27/settlements/` carries
`edge_pct` as NaN on all `v9:git_backfill` rows while `bets_ledger` carries a value, so the two
stores disagree about what the field is, and `settlements_backfill` exposes both `best_edge` and
`edge_over`/`edge_under` as separate columns — the tiering path and the recording path may
simply be reading different ones.

---

## RECOMMENDATIONS, RANKED BY MEASURED VALUE

Nothing here touches v9 (invariant 3). All of it is Pro-side or account-side.

1. **Take the best price of a fixed four-book panel** {betsson, onexbet, unibet_se, matchbook}
   for O/U execution. Measured +2.03pp ROI, CI [+1.41, +2.73], on the decisions already being
   made. 99.4% best-price recovery. This is the only change in this report whose value exceeds
   the noise in the P&L it would improve. (F1, F9)
2. **Quarantine all CLV records with `match_date` < 2026-09-01** and block any CLV-conditioned
   gate — v11's `MIN_CLV_N=150` `BET` gate above all — from reading them. 78.7% of new-format
   CLV rows are in the corrupt window, and the corruption has a **positive** mean, so it fails
   toward betting. (F5)
3. **Write the presence-aware panel loader** in `v10/src/market/` and add a `last_seen_ts` to
   Pro's capture, then re-run every analysis that has touched `book_odds_snapshots`. Until then
   every consumer reproduces the seed's 6× understatement of panel depth. (F2)
4. **Redefine the closing reference** as "last price inside T−60min" and report coverage
   alongside every CLV figure, rather than "last row we happen to have". 42.6% of series
   currently close more than 30 minutes early and 16.2% more than a day early. (F6)
5. **Separate consensus from execution in the Pro schema**, and price edge against the
   forward-filled median consensus rather than against any single book.
   `v10/src/market/consensus.py` already draws this distinction correctly in code and prose; it
   simply has no producer feeding it a real panel. (F1, F14)
6. **Report every movement statistic under two panel definitions** (fixed and growing). Two
   defensible definitions share only 56% of variance; a result that survives only one of them
   is a specification artefact. (F4)
7. **Consider a Pinnacle-anchored consensus** for the 34% of fixtures where Pinnacle quotes, as
   a *research* series only. Then test whether its move predicts the outcome, not the consensus.
   Ceiling on the prize is small (F10) and coverage is two-thirds missing. (F13)

## DO NOT BUILD

- **De-vig refinement of any kind** — Shin, log-margin, favourite-longshot weighting,
  overround-weighted consensus. Worth 0.0002 Brier at OU25 against no de-vig at all. The
  existing power method is already past the point of diminishing return.
- **Trimmed / winsorised / mean-instead-of-median consensus.** All three within 0.00024 Brier
  of each other on n=291. This is a settled question; do not reopen it.
- **More bookmaker accounts beyond five.** Four recover 99.4% of best price, five recover 99.6%.
- **A bigger OddsAPI plan for book breadth.** The 24-book panel was already inside responses
  v9 had paid for and was discarding at `predict.py:136`. The Odds API is at 89,842/100,000 this
  month with no headroom; the fix is to stop throwing away what arrives, not to buy more.
- **Dispersion-as-opportunity signal.** n=97/tercile, non-monotone, confounded with the
  probability level. INSUFFICIENT_DATA.
- **Switching the CLV closing reference to a sharp book.** Panel median already nominally beats
  Pinnacle-only, on n=77. No basis to move either way.
- **Backfilling CLV before 2026-09.** Per `CLAUDE.md`, historical odds cannot be repurchased at
  any price; and the archive rows that do exist are what produced the +42% artefact. Delete,
  don't repair.
- **Reading `market_snapshots` for anything book-level.** Two synthetic bookmaker values and a
  null `book_count`, per the seed — confirmed unusable and now superseded by
  `book_odds_snapshots`.

## OPEN QUESTIONS

1. Does a Pinnacle or matchbook move predict the **realised outcome** (not the consensus)?
   Needs ≳300 settled fixtures with Pinnacle present; currently 77.
2. Would staleness-weighting the consensus beat the flat median? Mechanism measured (F12),
   effect unmeasured, and F10 caps the prize at ≈0.0008 Brier.
3. Is the +2.03pp execution uplift attainable in practice, given stake limits and account
   longevity at the four best-price books? This is an operational question no dataset here can
   answer.
4. Once presence is captured separately from price change, does the 18% churn variance (F3)
   shrink further, or is it irreducible book entry?
5. Why does new-format CLV specifically break in July–August with opposite systematic signs on
   OVER and UNDER? The falsification (F5) proves the closing prices were wrong and proves they
   are right now; it does not identify the line that changed.
6. Unanswered from the seed: why `edge_pct` ≈ 9% appears on SNIPER-tiered rows. See the lead in
   F16.

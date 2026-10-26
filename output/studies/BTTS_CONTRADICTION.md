# New-format BTTS: why ROI looks strong while CLV looks poor

_Generated 2026-10-26 12:28 UTC by `python -m src.studies.btts_contradiction`. Research only: nothing here changes a stake, tier, threshold or filter. All CIs are 90% bootstraps over matchdays._

## Verdict

**concentrated league regime**, not model skill. The 253 settled new-format BTTS-YES tips returned +13.9% [+2.7%, +25.7%], +35.05u, n=253 at the price first logged. Argentina made 95% of those units; without Argentina the tips made +1.4% [-11.0%, +13.6%], +1.88u, n=131.

The profit is real money on real prices: entry odds match the books available at that minute. But it came from BTTS landing far more often than **any** price implied, not from the model reading fixtures better than the market. In Argentina BTTS landed 58% of the time against a market price of 42%. Backing YES on every Argentina fixture blind earned +27.3% [+9.4%, +45.8%], +31.14u, n=114. Argentina's BTTS rate was 38% in 2025, and the market is still pricing roughly that level.

The model is compressed: its probabilities have an SD of 0.034, against 0.085 for the market. So its 'edge' is almost entirely 'the market price is low' (correlation of edge with market probability: -0.92). A rule with no model, backing the 223 lowest-priced BTTS-YES fixtures, earned +16.3% [+5.9%, +27.3%], +36.34u, n=223 and overlapped 81% with Wowza's picks. Wowza minus that rule: -4.4% [-10.4%, +1.5%].

The poor CLV is mostly the bookmaker's margin, not a line moving against us. Entries sit at the cross-book median with about 8.0% overround. Price movement to the certified close is about zero (-0.53% [-2.00%, +1.14%], n=44). EV against the de-vigged close is -8.39% [-9.96%, -6.71%], n=44, which is the margin. So the market never moved toward Wowza's view. The profit came from outcomes, not from information.

The regime is cooling. First half +33.9% [+18.8%, +49.0%], +40.32u, n=119; second half -3.9% [-16.4%, +10.6%], -5.28u, n=134; difference -37.8% [-58.1%, -17.0%]; last 14 days -22.9% [-40.6%, -3.1%], -14.91u, n=65.

| question | answer |
|---|---|
| Genuine market inefficiency found by the model? | **No.** Residual z = 0.37; certified CLV positive: NO; beats a model-free price rule: NO |
| Timing / price artifact? | **No.** 99.6% of entries equal the cross-book median at that minute, and none are above the best available book. The ledger overwrite flattered NF BTTS by only +1.60u |
| Concentrated league effect? | **Yes.** Argentina = 95% of units; ex-Argentina +1.4% [-11.0%, +13.6%], +1.88u, n=131 |
| Variance? | **Not against the market's own odds** (p = 0.0003): outcomes really did beat the price. **But it is variance of the regime**: one league, one period, now cooling |

**No stake change is recommended from this analysis.** The forward evidence that would justify one is listed at the end.

## Headline numbers (first-logged price, flat 1u)

| set | n | hit | break-even | ROI (first logged) | ROI (ledger, overwritten) |
|---|---|---|---|---|---|
| all NF BTTS | 253 | 56.9% | 50.9% | +13.9% [+2.7%, +25.7%], +35.05u, n=253 | +14.5% [+2.8%, +26.3%], +36.64u, n=253 |
| staked (first tier SNIPER/MARKSMAN) | 82 | 59.8% | 46.1% | +30.6% [+9.6%, +51.8%], +25.09u, n=82 | +30.8% [+8.5%, +52.1%], +25.22u, n=82 |
| SNIPER (first tier) | 49 | 65.3% | 44.5% | +49.1% [+22.4%, +75.3%], +24.06u, n=49 | +49.1% [+23.0%, +75.7%], +24.06u, n=49 |
| standard track (contrast) | 162 | 53.7% | 53.9% | -0.5% [-13.2%, +13.3%], -0.84u, n=162 | -0.3% [-14.3%, +14.0%], -0.43u, n=162 |

## A. Entry price

- Entry odds are v9's **cross-book median** YES (src/btts_odds.py), not one bookmaker's price. 99.6% of tips reproduce the median of the books carried forward to the generated_at minute (median 5 books). Above best available: 0%. Below worst: 0%.
- ROI at the median: +13.9% [+2.5%, +25.2%], +35.05u, n=253. At the best book: +16.7% [+5.2%, +28.6%], +42.19u, n=253. At the worst book: +10.2% [-0.6%, +22.0%], +25.73u, n=253.
- First-logged vs ledger: the ledger overwrote odds on 52 settled NF BTTS rows (+5.27u first, +6.86u ledger, +1.60u flattering). The brief's 88-row figure covers all side markets.
- Time to kickoff at entry: median 156.9h (IQR 92.6-166.6h). 68% of tips were taken on the very first quote ever captured, so entries are early, at opening prices, not stale.

| hours to kickoff | ROI |
|---|---|
| 144h+ | +26.0% [+11.6%, +40.2%], +36.44u, n=140 |
| 24-72h | +54.0% [+16.1%, +85.3%], +13.50u, n=25 |
| 72-144h | -27.6% [-47.2%, -7.3%], -17.68u, n=64 |
| <24h | +11.7% [-14.4%, +45.8%], +2.79u, n=24 |

There is no monotonic timing pattern: the bands either side of 72-144h are positive while 72-144h is negative. Four bands were tested and no mechanism explains a middle band losing, so treat this as a lead to watch forward, not a finding.

## B. Closing price

- Coverage: certified close (the book's own quote within 30 min of kickoff, at least 3 books): 44 of 253 tips. Last pre-kickoff quote, not certified: 253. The two are never mixed.
- Certified, same construction (median to median): price CLV -0.53% [-2.00%, +1.14%], n=44; EV at the de-vigged close -8.39% [-9.96%, -6.71%], n=44; beat the close 45%.
- Not certified, last pre-kickoff: price CLV +0.06% [-0.55%, +0.61%], n=253; EV at the de-vigged close -7.92% [-8.57%, -7.34%], n=253.
- Same book, certified (entry YES vs that book's own close): -1.05% [-2.63%, +0.64%], n=223. Every book is negative or flat: betfred_uk -0.1% (n=16), coral -1.4% (n=11), ladbrokes_uk -0.8% (n=33), leovegas -1.4% (n=10), livescorebet -0.7% (n=42), matchbook -4.6% (n=7), onexbet +0.3% (n=47), virginbet -0.5% (n=41), williamhill -2.3% (n=9).
- CLV does not predict profit here. Tips that beat the close: +12.3% [-7.1%, +33.0%], +14.06u, n=114. Tips that did not: +15.1% [+3.1%, +26.6%], +20.98u, n=139.
- v9 ledger clv_pct, as recorded (not certified): mean -1.79% (n=209).

## C. First-sight tier vs upgraded rows

| first logged tier | ROI |
|---|---|
| MARKSMAN | +3.1% [-29.2%, +34.3%], +1.03u, n=33 |
| SNIPER | +49.1% [+23.1%, +75.8%], +24.06u, n=49 |
| VALUABLE | +5.8% [-6.2%, +17.7%], +9.95u, n=171 |

| ledger tier (after in-place upgrades) | ROI |
|---|---|
| MARKSMAN | +15.3% [-12.1%, +41.1%], +7.94u, n=52 |
| SNIPER | +21.5% [+3.6%, +38.4%], +18.46u, n=86 |
| VALUABLE | +8.9% [-3.7%, +23.0%], +10.25u, n=115 |

Upgraded later: -8.4% [-26.4%, +10.7%], -6.06u, n=72. Never upgraded: +22.7% [+8.0%, +39.6%], +41.11u, n=181. Upgrades blurred the tier ladder. First-sight SNIPER is the strongest cell, and it is also the cell with the lowest market prices (see G).

## D. League concentration and regime

Argentina: 48% of tips, 95% of units. Ex-Argentina: +1.4% [-11.0%, +13.6%], +1.88u, n=131.

| league | ROI |
|---|---|
| Argentina Primera Division | +27.2% [+11.0%, +44.1%], +33.17u, n=122 |
| Brazil Serie A | +25.6% [+9.0%, +40.3%], +11.00u, n=43 |
| Mexico Liga MX | +22.5% [-2.3%, +49.5%], +2.70u, n=12 |
| Norway Eliteserien | +23.1% [-30.0%, +63.8%], +1.85u, n=8 |
| Austrian Bundesliga | +24.6% [-15.2%, +73.2%], +1.72u, n=7 |
| Ireland Premier Division | -0.3% [-58.2%, +73.2%], -0.02u, n=7 |
| China Super League | -100.0%, -1.00u, n=1 |
| Denmark Superliga | -42.3% [-100.0%, +15.3%], -1.27u, n=3 |
| Japan J-League | -6.0% [-34.8%, +24.8%], -1.62u, n=27 |
| USA MLS | -24.8% [-61.0%, +13.6%], -1.99u, n=8 |
| Sweden Allsvenskan | -41.7% [-100.0%, +16.7%], -2.50u, n=6 |
| Finland Veikkausliiga | -77.8% [-100.0%, -33.3%], -7.00u, n=9 |

Leave one league out (ROI of the rest): Argentina Primera Division +1.4%; Brazil Serie A +11.5%; Japan J-League +16.2%; Mexico Liga MX +13.4%; Finland Veikkausliiga +17.2%; USA MLS +15.1%; Norway Eliteserien +13.6%; Ireland Premier Division +14.2%; Austrian Bundesliga +13.6%; Sweden Allsvenskan +15.2%; Denmark Superliga +14.5%; China Super League +14.3%.

- First half (to 2026-09-20): +33.9% [+18.8%, +49.0%], +40.32u, n=119. Second half: -3.9% [-16.4%, +10.6%], -5.28u, n=134. Second minus first: -37.8% [-58.1%, -17.0%].
- Last 14 days -22.9% [-40.6%, -3.1%], -14.91u, n=65; last 30 days -4.6% [-18.8%, +11.5%], -5.45u, n=118; last 60 days +11.4% [-0.3%, +24.0%], +27.09u, n=237.
- By month: 2026-08 +35.8% [+10.4%, +65.3%], +13.59u, n=38; 2026-09 +24.7% [+9.4%, +40.7%], +26.67u, n=108; 2026-10 -4.9% [-20.6%, +13.7%], -5.22u, n=107.

## E. Odds band and favourite strength

| entry odds | ROI |
|---|---|
| 1.80-1.99 | -10.1% [-26.8%, +7.8%], -6.85u, n=68 |
| 2.00-2.19 | +21.9% [+1.5%, +42.1%], +17.98u, n=82 |
| 2.20-2.49 | +43.1% [+10.0%, +73.5%], +18.11u, n=42 |
| 2.50+ | +28.7% [-47.2%, +120.6%], +2.29u, n=8 |
| <1.80 | +6.6% [-10.9%, +22.7%], +3.51u, n=53 |

| favourite strength (1X2, 97 tips with a capture) | ROI |
|---|---|
| balanced (<45%) | +22.9% [-3.2%, +50.5%], +7.78u, n=34 |
| moderate fav (45-60%) | +23.8% [-2.5%, +48.3%], +7.38u, n=31 |
| strong fav (60%+) | -7.8% [-33.5%, +18.0%], -2.49u, n=32 |

The profit sits at the longer YES prices (2.00-2.49), which is where the market thinks BTTS is least likely. That is the same price-level effect described in G.

## F. Vig handling

- Actual overround at entry: median 1.0804 (p10 1.078, p90 1.0878). Production assumes a fixed 1.08, so the assumption is accurate on average for these books.
- Mean edge with the fixed 1.08: +7.23%. De-vigged (power, YES/NO pair): +7.65%. YES carries 51% of the margin.
- Still at least 4% edge after de-vig: +17.1% [+5.5%, +29.1%], +38.94u, n=228. Below 4%: -15.6% [-44.4%, +13.0%], -3.89u, n=25. Vig handling does not explain the result.

## G. YES-only structure and the naive control

Every priced BTTS fixture in the NF tip leagues, inside each league's tip window: 557 fixtures, 223 of them Wowza picks (73 fixtures could not be matched to a result).

| league | n | BTTS rate | market fair YES (close) | gap | blind YES at close |
|---|---|---|---|---|---|
| Argentina Primera Division | 114 | 57.9% | 41.8% | +16.1pp | +27.3% [+9.4%, +45.8%], +31.14u, n=114 |
| Austrian Bundesliga | 6 | 66.7% | 58.2% | +8.4pp | +9.8% [-67.5%, +63.7%], +0.59u, n=6 |
| Brazil Serie A | 73 | 61.6% | 51.8% | +9.9pp | +13.2% [-2.6%, +27.4%], +9.67u, n=73 |
| China Super League | 2 | 100.0% | 69.3% | +30.7pp | +37.0%, +0.74u, n=2 |
| Denmark Superliga | 29 | 69.0% | 61.7% | +7.2pp | +5.5% [-17.4%, +22.0%], +1.59u, n=29 |
| Finland Veikkausliiga | 33 | 48.5% | 55.3% | -6.8pp | -18.5% [-41.6%, +2.5%], -6.10u, n=33 |
| Ireland Premier Division | 31 | 61.3% | 55.9% | +5.4pp | +0.0% [-16.9%, +22.4%], +0.01u, n=31 |
| Japan J-League | 90 | 54.4% | 54.0% | +0.5pp | -5.8% [-18.3%, +6.5%], -5.24u, n=90 |
| Mexico Liga MX | 66 | 57.6% | 57.9% | -0.4pp | -7.0% [-24.1%, +8.9%], -4.64u, n=66 |
| Norway Eliteserien | 23 | 73.9% | 61.9% | +12.0pp | +14.1% [-12.1%, +36.7%], +3.24u, n=23 |
| Sweden Allsvenskan | 46 | 47.8% | 57.5% | -9.7pp | -21.3% [-37.2%, -3.6%], -9.79u, n=46 |
| USA MLS | 44 | 70.5% | 65.3% | +5.2pp | +2.1% [-14.4%, +21.1%], +0.90u, n=44 |
| ALL tip leagues | 557 | 59.1% | 53.9% | +5.2pp | +4.0% [-1.2%, +9.1%], +22.11u, n=557 |

At the median price, at Wowza's typical lead time (156.9h):
- Blind, every YES: +3.2% [-1.8%, +8.4%], +17.60u, n=557
- Wowza's picks: +11.9% [+0.9%, +23.7%], +26.60u, n=223. Not picked: -2.7% [-8.4%, +3.1%], -9.00u, n=334. Picked minus not picked: +14.6% [+1.1%, +29.0%].
- **Model-free control**, the 223 lowest market probabilities: +16.3% [+5.9%, +27.3%], +36.34u, n=223, 81% overlap with Wowza. Wowza minus control: -4.4% [-10.4%, +1.5%].
- Within league: Argentina Primera Division +27.9% [-34.6%, +93.2%]; Brazil Serie A +17.9% [-8.3%, +46.7%]; ex_argentina_pooled -0.4% [-11.6%, +11.1%].
- Argentina BTTS rate by season: 2025 38.0% (n=510); 2026 43.6% (n=312); 2026 since Aug 10 54.0% (n=150).
- Blind YES by half. First half: all leagues +9.4% [+3.2%, +15.8%], +26.07u, n=276, Argentina +39.8% [+17.7%, +62.1%], +25.87u, n=65. Second half: all leagues -3.0% [-10.3%, +5.0%], -8.47u, n=281, Argentina +9.1% [-17.4%, +40.2%], +4.48u, n=49.

Picked minus not picked looks positive, but the picked fixtures are the ones the market priced lowest. A rule with no model, using price level alone, matches Wowza's picks or beats them. Ex-Argentina, Wowza's picks do no better than the fixtures it skipped (-0.4% [-11.6%, +11.1%]).

## H. Calibration

- On the tips: mean model probability 54.3%, hit rate 56.9%, market de-vigged 46.7% at entry and 46.9% at close.
- On all 556 priced fixtures: Brier model 0.2427 vs market 0.2442; log-loss 0.6785 vs 0.6811. Model on top of market: coefficient 0.289, z = 0.37, so it adds nothing measurable.
- Market calibration slope 0.53 (ex-Argentina 1.25). Model slope 0.974. A slope below 1 means low-priced YES landed more often than priced. Outside Argentina the market slope is at or above 1, so the market's miscalibration in this window is an Argentina effect, not a market-wide BTTS bias. One period is not enough to say whether this is a lasting market bias or this season's scoring.

| market fair p bin | n | mean p | hit |
|---|---|---|---|
| [0.0, 0.45) | 101 | 40.6% | 57.4% |
| [0.45, 0.5) | 74 | 47.7% | 52.7% |
| [0.5, 0.55) | 97 | 52.7% | 52.6% |
| [0.55, 0.6) | 141 | 57.6% | 62.4% |
| [0.6, 0.65) | 106 | 61.9% | 60.4% |
| [0.65, 1.01) | 37 | 68.8% | 78.4% |

| model p bin | n | mean p | hit |
|---|---|---|---|
| [0.45, 0.5) | 49 | 48.6% | 61.2% |
| [0.5, 0.55) | 263 | 52.8% | 56.6% |
| [0.55, 0.6) | 216 | 56.9% | 59.7% |
| [0.6, 0.65) | 26 | 61.7% | 73.1% |
| [0.65, 1.01) | 2 | 66.4% | 100.0% |

## I. Variance

If the market's own de-vigged probability were the truth, how often would flat YES at the entry price earn the observed ROI? (20,000 simulations)

| set | observed | expected if market right | 90% range if market right | p |
|---|---|---|---|---|
| all_nf_vs_entry_market (n=253) | +13.9% | -8.4% | [-18.7%, +1.8%] | 0.0003 |
| all_nf_vs_last_close_market (n=253) | +13.9% | -7.9% | [-18.2%, +2.2%] | 0.0003 |
| staked_first_vs_last_close_market (n=82) | +30.6% | -9.0% | [-28.4%, +10.9%] | 0.0006 |
| certified_subset_vs_certified_close (n=44) | +21.0% | -8.4% | [-33.2%, +16.7%] | 0.0263 |

Luck alone, with the market's odds being right, does not explain the result: YES really did land more often than priced. The naive control (G) shows that this happened to every YES in Argentina and Brazil, picked or not. So it is a property of the period and the league, not of the selection.

## What forward evidence would justify a change

No stake, tier or threshold change follows from this study. Each of these should be pre-registered and measured forward on first-logged prices:

1. **Selection beats price level.** Wowza's NF BTTS picks beat the model-free 'lowest market probability, same count' control. Required: the 90% CI of the difference above zero over at least 150 forward bets.
2. **Certified CLV.** Same-book CLV to a close certified within 30 minutes of kickoff has a mean above zero, with the CI above zero, at n >= 150. This needs near-kickoff BTTS capture for NF leagues first: today only 44 of 253 tips have a certified close.
3. **Not one league.** Ex-Argentina ROI has a CI lower bound above zero, and the Argentina-only result holds after its blind-YES baseline is subtracted.
4. **Model adds to market.** Residual z > 2 for the model given the de-vigged price, on forward fixtures.
5. **Regime check.** If Argentina's BTTS rate returns toward its 2025 level (about 38%), expect the blind baseline, and with it most of the NF BTTS profit, to disappear. Track blind YES ROI per league as the regime monitor.

## Method notes

- First-logged rows come from v9's git history of `output/side_bets_ledger.csv`: the first commit containing each row. They are cached at `output/studies/btts_contradiction_first_logged.csv`.
- Book quotes are Pro's `book_odds_snapshots`, which is a change-log, so every price at a given time is last-observation-carried-forward per book.
- Results come from API-Football. Model probabilities come from Pro's `model_snapshots` (last pre-kickoff). 1X2 comes from Pro's `market_snapshots` h2h captures.
- Observation, not a recommendation: v9 trains one BTTS model on standard and new-format rows pooled (pipeline.py side-market block). That may be why its probabilities are compressed.

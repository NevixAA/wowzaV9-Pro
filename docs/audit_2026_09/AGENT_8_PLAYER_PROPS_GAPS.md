# AGENT 8 — Player Props / Fantasy: data, settlement and current-club audit

Date: 2026-09-10. Scope: projections, minutes, starting probability, injuries, lineup status,
role, shots, substitutions, formation, market prices, book identity, close, voids, settlement.
Constraint respected: **props are paper-only, permanently (invariant 2)**. Nothing below proposes
betting a prop. Every question is asked in service of (a) is the props DATA pipeline sound enough
for the Fantasy family, (b) is settlement correct, (c) does the current-club rule hold now.

All numbers computed this run from `v9/output/*`, `v9/player_history.parquet`,
`v10/data/season_2026_27/player_props/`, using `v9/.venv/Scripts/python.exe`.

---

## HEADLINE

**The props model is served a feature at a value it never saw in training, and the one product
that is supposed to monetize it cannot be graded.** `n_prev_games` is a live model input
(`player_model/config.py:149`) whose training distribution is mean 35.6 / median 28 / max 157,
and `feature_engineering.py:1458` hardcodes the served value to `min(career_games, 5)` — so every
one of the 863 tips in the current file carries `n_games = 5`, exactly (std = 0.0). Meanwhile the
Fantasy projection log (3,920 rows over 14 days) has `gw` NULL on 100% of rows and no realised-points
column at all, so the accuracy of the Fantasy family has never been measured once.

---

## FINDINGS TABLE

| # | Finding | Evidence | Conf | Cat | Impact | Fix |
|---|---|---|---|---|---|---|
| 1 | `n_prev_games` train/serve skew: trained on 1–157 (median 28), served as constant 5 | `feature_engineering.py:1152,1458`; train median 28, p10 = 4.0, 12.5% of 302,456 rows ≤5; serve std = 0.0 over 863 tips | PROVEN | DATA_QUALITY | CRITICAL | HOURS |
| 2 | Fantasy projections cannot be graded: `gw` NULL 3,920/3,920, no actuals column | `fantasy_projection_log.csv` | PROVEN | PROCESS | CRITICAL | DAYS |
| 3 | `sot2`/`sot3`/`sot4` are structurally unsettleable — 0 WIN and 0 LOSS ever | `update_results.py:447-457` returns `""`, `:603` `continue`; 289 v9 rows → 156 VOID / 133 pending; Pro 3,245 rows → 1,820 PENDING / 1,425 VOID / 0 graded | PROVEN | EXECUTION | HIGH | HOURS |
| 4 | Props training table excludes every sub-10-minute appearance, so P(play) is unobservable | `data_fetcher.py:514 if minutes < 10: return None`; `minutes.min() == 10`, zero 0-minute rows in 302,456 | PROVEN | DATA_QUALITY | HIGH | WEEKS |
| 5 | Settlement blocked on 29 whole fixtures (321 rows) by club-name mismatch; canonical resolver not used | `_team_match('Hertha Berlin','Hertha BSC')=False`, `('Austria Wien','Austria Vienna')=False`, `('Queens Park Rangers','QPR')=False`, `('Wolverhampton Wanderers','Wolves')=False` | PROVEN | DATA_QUALITY | HIGH | HOURS |
| 6 | Invariant 12 was violated 137 times (Jul–Aug); the fix works but the ledger was never cleaned | 137 GHOST rows by strict `_same_club`; 86/118 rows in exposed leagues in Aug vs 0/74 in Sep; 9 ghosts carry a graded WIN/LOSS + price | PROVEN | DATA_QUALITY | HIGH | HOURS |
| 7 | Book identity absent on 61% of the prop-odds archive, 100% of the OddsAPI half; effective market is 2 books | `player_prop_odds_history.csv`: 111,408/182,694 `bookmaker` NULL; api_football side = Bet365 42,772 + Betano 28,205 + 1xBet 309 | PROVEN | MARKET_DATA | HIGH | WEEKS |
| 8 | "Closing" price is the last snapshot from *any* book, so props CLV measures book disagreement | `clv_tracker.py:100`; `p_bet_novig` non-null on 0/1,756; `under_odds_bet` non-null on 0/1,756 | PROVEN | STATISTICAL | HIGH | DAYS |
| 9 | CLV verdict "POSITIVE CLV — genuine edge signal" is printed off a median of exactly 0.000 | mean +0.357%, median 0.000%, moved-median −0.93%, p05 −32.8% / p95 +34.0%, 29.2% exact ties | PROVEN | STATISTICAL | HIGH | HOURS |
| 10 | De-vig is an assumed constant, not a de-vig; `fair_implied` is an invented number in a shipped CSV | `predict.py:98-112`, `config.py:112 OVERROUND_BY_ODDS = {3.0:1.06, 5.0:1.10, 99.0:1.15}` vs real prop overround 1.20–1.45 | PROVEN | STATISTICAL | MEDIUM | DAYS |
| 11 | Confidence score is advertised as 5-component; 3 components are constants and it takes 3 values | `predict.py:184,187,193`; 863 tips → confidence ∈ {0.623, 0.698, 0.772}, perfect 1:1 with lazy-factor count | PROVEN | ARCHITECTURE | MEDIUM | HOURS |
| 12 | Lineup status is never available at tip time: 0 confirmed starters on 863 rows | `props_health.json` run 1240: `[lineup] 0 confirmed starters | 863 lineup TBC` | PROVEN | EXECUTION | MEDIUM | DAYS |
| 13 | Props predict on 24-day-stale history while its own health file says `stale: true` | `props_health.json`: `newest_match 2026-08-17, age_days 24`, `collect_club: skipped` | PROVEN | PROCESS | HIGH | HOURS |
| 14 | The prop-odds archive is not joinable to the model's own tips: 0/829 keys match exactly | `player|market` exact join = 0; player-name intersect 37/638, 113/638 normalized; archive has no `player_id`, no `fixture_id` | PROVEN | MARKET_DATA | HIGH | DAYS |
| 15 | Fantasy's signal is p_start, not the props model | corr(p_start, fpl_ep_next)=0.646; corr(fantasy_pts, fpl_ep_next)=0.116; n=280 | SUPPORTED | STATISTICAL | HIGH | — |
| 16 | Pro replicates every v9 props defect ~14.6× and drops the join key | 106,238 rows / 7,289 distinct keys; no `player_id` column; `source = v9:player_props#0` | PROVEN | ARCHITECTURE | MEDIUM | DAYS |
| 17 | Championship / League One / Bundesliga 2 prop coverage question is ANSWERED | OddsAPI parked all three (23–24 consecutive empty events); API-Football prices all three, +2,734 quotes/run | PROVEN | MARKET_DATA | MEDIUM | — |

---

## 1. `n_prev_games` — a live feature served at a value the model never trained on

`PLAYER_FEATURE_COLS` includes `n_prev_games` (`v9/player_model/config.py:149`). It is therefore
an input to every per-market LogReg+GBM ensemble.

At **train** time it is the true career appearance index:

```
feature_engineering.py:135   df["n_prev_games"] = grp["date"].transform("cumcount")
```

Measured on `player_history.parquet` (302,456 rows, 2022-08-12 → 2026-08-17):

```
n_prev_games   mean 35.59   std 29.21   min 1   p25 12   median 28   p75 53   p90 79   max 157
pct <= 5 : 12.5%     p10 = 4.0
```

At **serve** time it is the rolling-window length, not a career count:

```
feature_engineering.py:1147   phist = phist_all.tail(n)          # n = ROLLING_N = 5
feature_engineering.py:1152   n_games = len(phist)
feature_engineering.py:1457   "n_games":      n_games,
feature_engineering.py:1458   "n_prev_games": n_games,           # <-- overwrites the model feature
```

Measured on the live tips file: `n_games` over 863 rows → **mean 5.0, std 0.0, min 5, max 5**.

So every live prediction presents an established professional at the **10th percentile** of the
training distribution. Two consequences, and the second is the one that matters:

* Rank order is largely preserved, because a constant feature contributes no cross-sectional
  variance at serve time. This is consistent with the reported AUC 0.62–0.85 being real.
* **Probability levels are not.** Platt calibration was fitted where the feature varied; at serve
  it is pinned to one end. Any monotone dependence on "appearance count" becomes a uniform
  one-sided offset that calibration cannot absorb. That reconciles "genuinely accurate and
  calibrated" with "every framework with a meaningful bet count is significantly negative":
  the ordering is informative, the level is biased.

For the Fantasy family this is the load-bearing defect, because Fantasy consumes **levels**
(`fantasy_pts` is a weighted sum of `p_goal`, `p_assist`, `p_sot2`), not ranks.

Adversarial note: I have not measured the size of the level shift. Doing so requires re-scoring the
current slate twice with `n_prev_games` at its true career value and at 5 — which is a model
change and is forbidden by invariant 3 in v9. It belongs in Pro, offline, as a diagnostic.
Until it is measured, the *direction* is unknown; only the *existence* of the skew is proven.

Same file, same shape, lower stakes: `n_games` also drives the "data volume" component of
`_confidence_score`, whose docstring promises a 0→20 scale (`predict.py:180-181`). Its input is
capped at 5, so that component is a constant too. See finding 11.

## 2. Fantasy cannot be graded

`fantasy_projection_log.csv` — 3,920 rows, `snapshot_date` 2026-08-27 → 2026-09-09, exactly 280
rows/day for 14 days.

* `gw` is **NULL on all 3,920 rows.** The gameweek is the only key that joins a projection to the
  points it was predicting.
* There is no realised column of any kind: the 21 columns are all inputs and projections
  (`proj_pts_per_game`, `proj_fixture_adj`, `proj_total_next`, `p_start`, `minutes_pg`, FPL
  reference fields). No actual points, no actual minutes, no appearance flag.

So the designated monetization path for an accurate-but-un-bettable model has **zero measured
accuracy**, 14 days in. Props at least have a ledger with WIN/LOSS. Fantasy has none.

Second-order: the 14 daily snapshots are near-duplicates. Per-player std of
`proj_pts_per_game` across the 14 days: median 0.00094, mean 0.0055, max 0.152; 13 of 280 players
never moved at all. That is the expected consequence of finding 13 — the underlying history is
frozen at 2026-08-17 — so the log is 3,920 rows carrying roughly 280 distinct facts.

`n_fixtures_next` is a constant 5 on all 280 rows, and `fixture_adj_pts` correlates 0.117 with
`fpl_ep_next` — the fixture-difficulty adjustment is currently doing nothing measurable.

## 3. `sot2` / `sot3` / `sot4` never settle

```
update_results.py:447  def _resolve_player_market(market, stats):
              449-456    handles ONLY goals, sot, cards, assists
              457        return ""
update_results.py:603  if not result: continue
```

v9 ledger, `result` × `market`:

| market | LOSS | UNSETTLED | VOID | WIN |
|---|---|---|---|---|
| sot | 938 | 699 | 2262 | 557 |
| goals | 423 | 186 | 589 | 108 |
| cards | 363 | 261 | 583 | 59 |
| assists | 24 | 11 | 66 | 7 |
| **sot2** | **0** | **131** | **156** | **0** |
| **sot3** | **0** | **2** | **0** | **0** |

Every settled sot2/sot3 row reached VOID through the DNP branch (`:589`/`:597`), which fires
*before* `_resolve_player_market`. Notes on those 156 rows: `DNP` 150, `DNP (0 min)` 6. Not one
row where the player actually played has ever been graded.

Independent confirmation from the fixture side: of the 388 currently-unsettled past-fixture rows,
67 sit inside fixtures where every other row settled — and **67 of 67 are sot2/sot3**.

These 133 rows are also re-fetched on every `update_results` run forever, since `pending_mask`
(`:499-501`) only tests `result` blank and `match_date < today`.

Pro inherits it verbatim: 3,245 sot2/sot3 rows → 1,820 `PENDING`, 1,425 `VOID`, **0 WIN, 0 LOSS**.

Note these markets are already capped at VALUABLE by `config.py:133 VALUABLE_ONLY_MARKETS`, so no
tip is affected — but 289 rows of "did a 2+ SOT prop hit" evidence is being discarded, and that is
exactly the kind of distributional evidence the Fantasy `p_sot2` term needs.

## 4. The props training table cannot see non-appearance

```
data_fetcher.py:514   if minutes < 10: return None
```

Verified in the parquet: `minutes.min() == 10`, `(minutes == 0).sum() == 0` over 302,456 rows.

So the model estimates **P(event | played ≥ 10 minutes)**, not P(event). For props that is
harmless: the book voids a DNP, and the ledger agrees — **3,650 of 7,425 ledger rows (49.2%)
settled VOID with note `DNP` (3,328) or `DNP (0 min)` (322)**. Half of every props slate never
happened, and the model was never trained on those rows because they never enter the parquet.

For **Fantasy this is wrong**, because FPL pays 0 for a non-appearance and 1–2 points for the
appearance itself. `fantasy.py:277 xpts_rot = fantasy_pts * p_start` treats it as separable:
P(points) ≈ P(points | played) × P(start). That holds only if event probability is independent of
minutes, and it is not — a 20-minute substitute has materially lower P(goal) than a starter, and
the training set contains no rows below 10 minutes to estimate the gradient from.

Within the surviving rows, `started` is 228,423 / 74,033 → **24.5% of ≥10-minute appearances are
substitute appearances**, and that is already the censored figure.

`starter_rate` (the rolling start rate, and a live model feature) correlates 0.436 with `started`.
That is the honest ceiling on start prediction from the current features.

## 5. Settlement fails on whole fixtures because of club names

388 past-fixture rows are unsettled (median age 25 days, max 78). They split cleanly:

* **67 rows** = sot2/sot3 stragglers inside otherwise-settled fixtures (finding 3).
* **321 rows across 29 fixtures** where *no* row settled — the fixture lookup itself failed.

`find_fixture_id` (`api_football.py:346-359`) matches on `_team_match`. Tested this run against
the 969 team names in `v9/api_football_cache/` (25,267 cached fixtures):

```
False  ratio=0.696  'Hertha Berlin'           vs 'Hertha BSC'
False  ratio=0.846  'Austria Wien'            vs 'Austria Vienna'
False  ratio=0.273  'Queens Park Rangers'     vs 'QPR'
False  ratio=0.414  'Wolverhampton Wanderers' vs 'Wolves'
True   ratio=0.800  'Hartberg'                vs 'TSV Hartberg'
True   ratio=0.769  'Cádiz CF'                vs 'Cadiz'
```

`_team_match` uses identity-token prefixes plus a 0.90 `difflib` fallback. `Hertha Berlin` vs
`Hertha BSC` gives 0.696; `Austria Wien` vs `Austria Vienna` gives 0.846 — both below the 0.90
floor, so both return False. `QPR` and `Wolves` are pure abbreviations with no shared token.

**Three of those four pairs are named verbatim in root `CLAUDE.md` invariant 11**
(`QPR`/`Queens Park Rangers`, `1. FC Kaiserslautern`/`Kaiserslautern`, `Cádiz CF`/`Cadiz`), and the
invariant's prescribed remedy — `src/team_names.resolve`, league-scoped, refuses ambiguity — is
**not used anywhere on the props settlement path.**

Rows attributable to these pairs: Hertha 36, Hartberg/Austria Wien 14, QPR/Wolves 20 ≈ 70 of 321.

One separate case worth naming because it is not a matcher bug: `Cádiz CF v Celta Vigo 2026-08-15`
(La Liga 2, 23 rows). API-Football's fixture that day is `Cadiz` v **`Celta de Vigo II`**. The
reserve-token guard (`api_football.py:281-284`) correctly refuses to match a senior squad to a
reserve side — so 23 props were generated for a **reserve-team fixture using senior-squad
players**, and settlement is right to refuse them. That is a source-slate defect, not a settler
defect.

Also confirmed non-issues, so nobody re-chases them: tip `date` equals `kickoff_utc` date on
782/782 rows with a kickoff (no timezone boundary bug), and every unsettled league is present in
`PROP_LEAGUES` (no missing-league skip). Calendar-year leagues settle at 84.1% (264/314) vs
95.6% (5,715/5,978) for European-season leagues — the `season = yr-1 if month < 7` rule
(`update_results.py:545-547`) is wrong for MLS/Brazil/Argentina/Nordics in Jan–Jun, but no
Jan–Jun rows exist yet, so this is a **latent** bug, not a current one.

## 6. Invariant 12 — the current-club rule holds now, but the ledger was never cleaned

Classified all 7,425 ledger rows with the codebase's own strict matcher (`_same_club`):

```
exact    6996      team string == home or away
variant   133      accent/case/suffix only  (Cadiz/Cádiz CF, HJK helsinki/HJK Helsinki)
loose     178      generous _team_match only (Derby/Derby County, Birmingham/Birmingham City)
GHOST     137      neither team is the player's club          <-- 1.84%
```

The 137 ghosts are precisely the collision set predicted in `api_football.py:300-302`:

| league | fixture | player's club |
|---|---|---|
| China Super League | Zhejiang v Chengdu Rongcheng | Borussia **Mönchengladbach** |
| USA MLS | Los Angeles FC v **Real** Salt Lake | **Real** Madrid |
| Brazil Serie A | **Atletico** Mineiro v Bahia | **Atletico** Madrid |
| Austrian Bundesliga | **Austria** Lustenau v **Wolfs**berger AC | VfL **Wolfs**burg / **Australia** |
| Argentina Primera | Sarmiento v Argentinos Juniors | **Argentina** (national team) |
| Conference League | Flora Tallinn v **Inter** Club d'Escaldes | **Inter** Turku |
| USA MLS | **Charlot**te FC v Columbus Crew | **Charlton** |
| Norway Eliteserien | Fredrikstad v **Lille**strom | **Lille** |

`Australia` mapped onto `Austria Lustenau` and `Austria Wien` is the exact example invariant 12
cites. Messi tipped in Sarmiento v Argentinos Juniors is the exact example the `predict.py:591`
comment cites.

**The fix works.** `predict.py:596-606` replaced a 5-character-prefix test with
`_same_club` + `_club_name_subset` gated on "do we hold history for this club in THIS
competition". In the ghost-prone leagues (Austrian, Argentina, China, MLS, Conference, Brazil):

```
2026-08  118 rows exposed →  86 ghosts (72.9%)
2026-09   74 rows exposed →   0 ghosts
```

Under the August rate, P(0 of 74) is effectively zero, so the improvement is real and not an
artifact of missing exposure. Sample discipline: n=74 is not enough to claim the rate is now
*zero*; it is enough to claim the August rate is gone. China Super League and Conference League
have no September exposure and remain untested.

**But the ledger was never cleaned.** All 137 ghost rows are still in `player_ledger.csv`, with no
flag distinguishing them. 96 settled VOID, 32 are pending — and **9 carry a graded outcome with a
real price (1 WIN, 8 LOSS)**, so any accuracy, calibration or CLV computation over the ledger
includes fixtures the player was never in. The squad overlay is now doing enormous work
(`props_health.json`: *"18982 live squad entries; ... 75545 history row(s) corrected where the
latest appearance was a former club"* — 25.0% of 302,456 rows), which is exactly the 25% figure
the `predict.py:483-486` comment measured. That machinery is sound; the historical residue is not.

## 7–10. Market data: no book, no other side, no real close, no real de-vig

`player_prop_odds_history.csv` — 182,694 rows, 2026-06-28 → 2026-09-10.

```
source        oddsapi 111,103   api_football 71,591
bookmaker     NULL 111,408 (61.0%)   Bet365 42,772   Betano 28,205   1xBet 309
bookmaker NULL rate by source:  oddsapi 100.0%   api_football 0.4%
columns       snapshot_date, snapshot_ts, match_date, league, match, player, market, odds, source, bookmaker
```

Four structural consequences, all proven:

1. **No book identity on the OddsAPI half.** Same defect the seed found in
   `market_snapshots.bookmaker` (two synthetic values), reproduced independently in props. It
   cannot be repaired retroactively.
2. **No opposite side and no line column.** There is one `odds` per (player, market) — the OVER.
   Two-sided de-vig is structurally impossible, unlike `book_odds_snapshots` (80.1% two-sided).
   Confirmed downstream: `clv_records.csv` has `under_odds_bet` non-null on **0 of 1,756** rows and
   `p_bet_novig` non-null on **0 of 1,756**. `clv_prob` — the only vig-free CLV metric — is
   uncomputable for 100% of props, which `clv_tracker.py`'s own docstring admits.
3. **The "close" is book-mixed.** `clv_tracker.py:100`
   `closing = float(m.sort_values("snapshot_ts").iloc[-1]["odds"])` selects the last snapshot for
   `(player, market, date)` with **no bookmaker filter and no pre-kickoff filter**. Entry can be
   Bet365 and close can be Betano. So `clv_pct = odds_entry/odds_close − 1` measures book
   disagreement, not price movement. The `_bet_id` (`clv_tracker.py:27`)
   `PLAYER|date|player|market` carries no fixture, so same-name collisions on a date are possible.
4. **De-vig is a constant haircut.** `predict.py:98-112` divides raw implied probability by an
   *assumed* overround from `config.py:112 OVERROUND_BY_ODDS = {3.0: 1.06, 5.0: 1.10, 99.0: 1.15}`.
   Player-prop overround is routinely 1.20–1.45. So `fair_implied` — written into
   `player_tips.csv` as if measured — is systematically too high, and
   `edge_rel = (p_model − fair_prob)/fair_prob` is systematically too negative. Measured on the
   204 priced rows in the current file: `edge_rel` mean **−0.342**, median −0.362, p75 −0.209.
   Correcting a 1.15 assumption to a realistic 1.30 moves the median to roughly −0.28 — **still
   firmly negative, so invariant 2 survives intact**; only the magnitude and the tier gates
   (`REL_EDGE_SNIPER = 0.20`) are calibrated against a fiction.

### The CLV verdict is not a result

`props_health.json` run 1240 prints:

```
[clv_tracker] CLV report: {'n': 1447, 'mean_clv_pct': 0.0036,
                           'beat_close_rate': 0.337, 'verdict': 'POSITIVE CLV — genuine edge signal'}
```

Recomputed from `clv_records.csv` (1,756 rows, 1,447 closed):

```
clv == 0 EXACTLY (entry price == close price)   422   29.2%
clv >  0   487        clv < 0   538
mean +0.357%       median  0.000%
beat_close_rate (as reported, ties count as losses)  0.3366
among the 1,025 records that ACTUALLY MOVED:
   beat rate 0.4751   z vs 0.5 = -1.59  (not significant)
   mean +0.504%   median -0.926%
   p05 -32.8%   p25 -8.8%   p75 +7.1%   p95 +34.0%
```

Two things, and I am correcting my own first read of this:

* The reported 33.7% beat rate is a **metric artifact**, not negative CLV. 29.2% of closed records
  have entry == close exactly and are silently counted as failures to beat. On the 1,025 records
  that moved, the beat rate is 47.5% with z = −1.59 — **the interval spans 50%, so we do not know**.
* The **verdict is the real defect.** "POSITIVE CLV — genuine edge signal" is fired off a mean of
  +0.357% over a distribution whose median is exactly 0.000 and whose moved-median is −0.93%, with
  ±33% tails. On one-sided, book-mixed prop prices a "move" from Bet365 5.75 to Betano 7.50 is
  recorded as +30% CLV. The mean is a tail statistic here and carries no information about edge.
  This is a live false positive being reported to the operator on a market that invariant 2 has
  already ruled out.

Two more facts about that dataset: 1,618 of 1,756 records (92.1%) are tier `AVOID` (only 1 is
MARKSMAN), and `result` is NULL on **1,724 of 1,756 (98.2%)** — 12 WIN / 20 LOSS graded. The
year-long paper track record the module was built to produce is 98% ungraded.

## 11–12. Confidence, lineup, minutes

`_confidence_score` (`predict.py:176-204`) is documented as a "5-component confidence score" and
gates every tier via `CONFIDENCE_FLOORS = {SNIPER 0.72, MARKSMAN 0.62, VALUABLE 0.50}`. Three of
the five components are literals:

```
predict.py:184   recency     = 0.8   # "default when no per-match data"  → always
predict.py:187   model_agree = 1.0   # "always 1.0 for single model"
predict.py:193   p_start     = row.get("p_start", 0.8)   # p_start is not a props feature
```

`p_start` exists only in the Fantasy module (`fantasy.py:271`); it is not in
`player_history.parquet`'s 211 columns and is not produced by `build_upcoming_features`. So the
"minutes certainty" component is the constant 0.8 for every player. Combined with finding 1
(`vol_score` constant because `n_games` is pinned at 5), the score reduces to
`0.623 + 0.075 × lazy_factor_count`.

Measured on 863 tips: confidence takes **exactly three values** — 0.623, 0.698, 0.772 — in a
perfect 1:1 crosstab with lazy-factor count 0/1/2 (799 / 61 / 3 rows). Since SNIPER requires
`lazy_count >= 2` *and* `confidence >= 0.72`, and only 3 of 863 rows reach two factors, the props
SNIPER tier is effectively unreachable by construction. The live output is `SNIPER:0 MARKSMAN:0
VALUABLE:3` — which is correct behaviour for a paper model, but it is being produced by a dead
gate rather than by a judgment about edge, and that distinction matters if Fantasy ever reuses
`confidence`.

I retract one thing I initially believed: the `MINUTES` lazy factor is **not** dead.
`minutes_est` is populated at `feature_engineering.py:1456` and the factor fires on 31 of 863 rows.
It is, however, `p.get("minutes", int(minutes_pg))` — the minutes the player played in his most
recent historical match, used as a forecast for the next one. A lagged single observation, not a
projection.

**Lineup status never arrives.** `predict.py:557-575` fetches the confirmed XI and requires
`len(lineup_starters) >= 18` before trusting it. `props_health.json` run 1240:
`[lineup] 0 confirmed starters | 863 lineup TBC`. So `lineup_available` is False for 100% of rows:
the "skip players not in the confirmed XI" filter (`:651`) never fires, the `STARTER` confidence
boost (`:727`) never fires, and the operative start filter is always the
`minutes_pg >= MIN_STARTER_MINUTES` proxy (`:656-659`). This is the props-side instance of the
near-kickoff coverage collapse the seed measured for team markets (T-1h 32.6%, T-30m 14.5%):
official lineups post ~60 minutes before kickoff, and props runs every 2h Fri–Sun / 6h Mon–Thu
(`player_props.yml:68-69`).

Injuries do arrive: `[predict] Injury filter: 140 injured/suspended players loaded`
(`api_football.py:388-404`, `/injuries`, 4h cache). Fantasy's own availability field is populated
(254 available / 12 injured / 11 doubtful / 3 suspended of 280) but FPL's
`chance_of_playing` is NULL on **253 of 280 (90.4%)**, so `p_start` falls back to
`0.6 × starter_rate + 0.4 × season_start_rate` for nine players in ten.

**Nothing in the pipeline models substitutions or formation.** Neither appears in
`player_history.parquet`'s 211 columns, in the feature list, or in the Fantasy module. Stated
because the remit asks: they are absent, not broken.

## 13. Props predicts on 24-day-stale history and says so

`v9/output/props_health.json`, written 2026-09-10T10:45:13Z (run 1240, event `schedule`):

```json
"history_freshness": {"newest_match": "2026-08-17", "age_days": "24", "stale": "true"},
"step_outcomes":     {"collect_club": "skipped", "predict": "success", "notify": "success"}
```

The parquet's own max date confirms 2026-08-17. Git says the file was last written 2026-09-05, but
by `auto: injury refresh` — a rewrite that adds no matches while resetting the commit timestamp
that `player_history_extend.yml`'s cooldown gate reads (`hours >= 20` from
`git log -1 --format=%cI -- player_history.parquet`). That gate is therefore reading a clock the
injury refresh keeps bumping.

Meanwhile `props_health.json` records `"event": "schedule"` with `"schedule": ""` — the same
empty-schedule-string shape as the NEAR-capture outage in root `CLAUDE.md` (both collectors
string-matched a cron that no longer existed, 2026-08-29..09-07). `player_props.yml` gates its
collect step on `github.event.schedule == '...'` comparisons at lines 203-204 and 229-230. I did
not confirm whether the empty value is the gate's input or only the health file's
(`player_props.yml:338` reads `os.getenv("PROPS_SCHEDULE","")`, which may simply be unset). What is
proven is the outcome: **history 24 days stale, `collect_club: skipped`, `predict: success`** — a
green run producing tips from month-old form. This is the exact failure signature root `CLAUDE.md`
records for `COLLECT_SEASONS`: "the daily collect ran the whole time and reported success."

Fantasy is downstream of the same parquet, which is why its 14 daily projections are identical.

## 14. The prop-odds archive cannot be joined to the model's own predictions

Same-day test (snapshot 2026-09-10, 2,529 archive rows / 2,000 distinct `player|market` keys, vs
863 tips / 829 distinct keys):

```
tip keys matched by EXACT player|market   :     0  of 829
distinct players  tips 638   archive 1,757
  exact intersection        :  37
  normalized intersection   : 113   (accent/case fold gains 76)
tips actually carrying odds :  204
```

The archive stores the **raw source spelling** of `player`, while `match_odds_to_tips`
(`odds_fetcher.py:764-776`) joins on `_norm(player)|market`. So enrichment works at runtime, and
the persisted archive is unjoinable to the file it enriched. The archive carries **no `player_id`
and no `fixture_id`**, although `predict.py:748-749` deliberately carries both into `player_tips.csv`
precisely to end name-based joins. 113/638 = 17.7% is the coverage ceiling for today's slate even
after normalization.

Two further mismatches in the same join: the archive contains `sot4` quotes (39 today, 3,213
all-time) that `config.MARKETS` never emits, so they are unusable; and the archive had **zero
`cards` quotes today** against 1,266 `cards` rows in the ledger.

Separately, the enrichment key itself (`predict.py:802`, `odds_fetcher.py:629,740`) is
`player|market` with **no fixture and no league**. A price fetched for one fixture attaches to any
row with the same player and market in the same run. Low practical risk for unique names — but it
is the mechanism that let a priced ghost row (finding 6) inherit a real price.

## 15. Fantasy's signal is starting probability, not the props model

`fantasy_tips.csv`, n=280, 20 PL clubs, `fpl_matched` True on 280/280:

```
corr(p_start,          fpl_ep_next)   = 0.646
corr(xpts_rot,         fpl_ep_next)   = 0.572
corr(fantasy_pts,      fpl_ep_next)   = 0.116
corr(fixture_adj_pts,  fpl_ep_next)   = 0.117
corr(fantasy_pts,      fpl_ppg)       = 0.438
corr(xpts_rot,         fpl_ppg)       = 0.357
corr(fantasy_pts,      total_points)  = 0.420
```

`p_start` **alone** agrees with FPL's own expected-points more than our full projection does
(0.646 vs 0.116). Since `p_start` is built from `starter_rate` + FPL availability
(`fantasy.py:271-276`) and contains no output of the props model, the ranking signal is currently a
rotation ranking.

Adversarial reading, because this is easy to over-claim: `fpl_ep_next` is FPL's model, not truth.
Against quasi-truth (season-to-date realised), `fantasy_pts` correlates 0.438 with `fpl_ppg` and
0.420 with `total_points` — a real but modest relationship, and *higher* than `xpts_rot`'s 0.357.
That ordering is internally consistent: FPL's `ppg` is conditional on appearing, so the
unconditional `xpts_rot` should agree with it less. n=280, one snapshot, no out-of-sample split —
this is a **description of one file, not a validated result**, and it stays SUPPORTED. It cannot be
promoted without finding 2 being fixed first.

## 16. Pro is a faithful mirror, including the faults

`v10/data/season_2026_27/player_props/` — 24 daily files, 106,238 rows, **7,289 distinct
`(fixture_key, player_name, market)`**, mean 14.6 copies per key (max 24). `source` is
`v9:player_props#0` on 100% of rows, `deployment_mode` is `PAPER` on 100% (invariant 2 respected).

Pro is genuinely better than v9 in two ways worth keeping:

* It has an explicit `PENDING` state (27,181 rows) where v9 writes a blank.
* It labels the unpriced case: `never_priced = True` on 72,065 of 106,238 (67.8%), with
  `quality_flags = MISSING_OPPOSITE_SIDE` on exactly those rows, and `odds_band = UNKNOWN` on
  72,303. That is invariant 13 encoded in data rather than in a dashboard comment.

And worse in one way that blocks everything downstream: **`player_props` has no `player_id`
column.** v9's ledger carries `player_id` (`ledger.py:28`) and Pro drops it on import. So the
canonical evidence store cannot join props to players, to `player_history`, or to the Fantasy log
except by name — the exact weakness that produced findings 6 and 14.

## 17. The Championship / League One / Bundesliga 2 prop question is answered

Root `CLAUDE.md` leaves this open: *"the open question is Championship / League One / Bundesliga 2,
the leagues we actually target."* From run 1240's log:

```
soccer_efl_champ         : parked — 24 consecutive events with no bookmaker
soccer_england_league1   : parked — 23 consecutive events with no bookmaker
soccer_germany_bundesliga2: parked — 24 consecutive events with no bookmaker
api-football second source: +2734 quote(s)
leagues with any prop coverage: [... apifootball:Championship, apifootball:League One,
   apifootball:League Two, apifootball:Bundesliga 2, apifootball:La Liga 2, apifootball:Serie B ...]
```

Answer: **OddsAPI does not price props in our target divisions** (parked on evidence, 23–24
consecutive empty events, retry every 7d) — and the API-Football second source does, at ~2,734
quotes per run, on a key with ~71,000/75,000 daily headroom. All-time archive coverage for those
leagues: Championship 5,456 distinct player-market-fixtures, League One 2,774, League Two 1,747,
Bundesliga 2 1,288, La Liga 2 3,187, Serie B 2,113.

So the tension `CLAUDE.md` flags is resolved in the *un*interesting direction: the deep, sharp prop
market is in the top five, and our soft divisions are priced thinly by two books. It stays paper.
The useful consequence is a data one: those quotes are a free forward-only stream in the leagues we
bet, on the API-Football budget, and they are being archived without book labels on the OddsAPI
side and without player ids anywhere.

---

## WHAT I WOULD FIX, IN ORDER

All of it is Pro or tooling work; **none of it is a v9 model change** (invariant 3), and none of it
proposes betting a prop (invariant 2).

1. **Stop `feature_engineering.py:1458` overwriting `n_prev_games`.** This is a bug fix, not a
   feature change — the served value contradicts the trained one. Measure the level shift in Pro
   first, offline, by re-scoring one frozen slate both ways. That measurement is the prerequisite
   for trusting `p_goal`/`p_assist`/`p_sot2` as Fantasy inputs at all.
2. **Add `gw` and a realised-points column to the Fantasy log**, and grade it. Until this exists
   the Fantasy family has no evidence, and finding 15 cannot be promoted or dismissed.
3. **Add the four missing markets to `_resolve_player_market`** (`sot2`/`sot3`/`sot4`, and
   `goals2`/`goals3` which `clv_tracker._MARKET_HIT` already knows how to grade). Recovers 289 v9
   rows and 3,245 Pro rows, and stops an infinite re-fetch loop.
4. **Route props settlement through `src/team_names.resolve`** instead of `_team_match`. Unblocks
   ~70 of 321 rows immediately and closes an invariant-11 violation.
5. **Flag the 137 ghost rows in the ledger** (a `notes` value, not a deletion — the record of the
   bug is worth keeping) so accuracy and CLV computations can exclude them.
6. **Delete the CLV verdict string, or gate it.** Replace `mean_clv_pct` with the moved-record
   median and an interval, report the tie count explicitly, and require a bookmaker match between
   entry and close before a record counts. Until then props CLV is uninterpretable and should say so.
7. **Carry `player_id` and `fixture_id` into `player_prop_odds_history.csv` and into Pro's
   `player_props`.** Everything downstream is currently name-joined.

## DO NOT BUILD

* **A props betting proposal of any kind.** Invariant 2. Nothing here changes it — and the two
  findings that could look like an argument for revisiting it (the fake de-vig understating edge,
  the missing-book CLV) both leave `edge_rel` median at roughly −0.28 after correction.
* **A prop-odds de-vig from the existing archive.** There is no opposite side and no line column;
  `under_odds_bet` is non-null on 0 of 1,756 records. This needs new collection, not new code.
* **A near-kickoff lineup fetch inside the props loop.** Confirmed XIs post ~60 minutes out; props
  runs every 2h at best. Chasing lineups means a new high-cadence workflow, and the seed's own
  delivery finding says workflows asking ≥26 runs/day get 8–38% of them. Fix the freshness of the
  history first — a 24-day-stale form window costs far more than an unconfirmed XI.
* **More OddsAPI plan for props.** The Odds API projects 89,842/100,000 this month with no
  headroom, and the target-division calls come back *empty*, not rate-limited. API-Football already
  covers those leagues at 3% utilisation.
* **Backfilling props odds history.** Same wall as team odds (root `CLAUDE.md`): the endpoint is
  pre-match only. Forward-only or nothing.
* **A per-league props threshold tune.** 863 tips, 204 priced, 3 VALUABLE, and a confidence gate
  with three possible values. Invariant 6 and sample discipline both forbid it.

## OPEN QUESTIONS

1. What is the magnitude and sign of the `n_prev_games` level shift? Requires re-scoring one frozen
   slate twice in Pro. Everything about Fantasy's usability hangs on it.
2. Is `player_props.yml`'s collect step gated on an empty `github.event.schedule`, the same shape as
   the NEAR-capture outage? I proved the outcome (24-day staleness, `collect_club: skipped`,
   `predict: success`) but not the mechanism; it needs the workflow-run logs, not the repo.
3. Why does `player_history_extend.yml`'s cooldown not fire at age 24 days? Its gate reads the git
   commit time of `player_history.parquet`, which `auto: injury refresh` bumps without adding
   matches — is the injury refresh writing the same file the collector owns?
4. Do the 3,650 DNP-void rows contain a learnable start signal? They are the half of every slate
   the ≥10-minute filter erases from training, and they are exactly what Fantasy needs. The ledger
   holds the labels the parquet does not.
5. Is the ghost rate genuinely zero now, or only below detection at n=74? China Super League and
   Conference League — two of the six ghost-prone leagues — had no September exposure.

# Props matchup research: specification

Approved by the owner on 2026-11-04. This document is the design. No model has been fitted and no edge
or ROI has been computed. Code: `src/props_matchup/`. Tests: `tests/test_props_matchup.py`.
Branch: `research/props-matchup`.

---

## In plain language

**The idea.** A bookmaker prices "Player X has 1+ shot on target" or "Player X scores" mainly from
the player and his team. When the opponent is missing its first-choice goalkeeper or a key defender
through injury or suspension, the player's real chance should go up. If the bookmaker's price does
not move enough, there is an edge. The size of that edge, and the bar a tip has to clear, will differ
by player, league and market. This research is meant to find those bars.

**Can it run today? No.** It is blocked on data, for four reasons:

1. **Player counts are not verified yet.** All 876,130 rows of v9's `player_history` are still marked
   `zeros_unverified`, because the re-fetch that separates a real 0 from a missing value has not run.
   Every shots and SoT number in the history is therefore still suspect.
2. **We cannot yet show when an absence was known.** Injury and lineup collection in v9 starts on
   2026-11-05. The only injury lists stamped before kickoff are Pro's own snapshots: 111 fixtures in 5
   leagues since 2026-10-19. Pro's forward check found that **18.8% of a fixture's final injury list
   was added after kickoff** (82 fixtures compared). So an injury list downloaded after the match
   contains hindsight and cannot be used to test the bookmaker.
3. **The props prices cannot be placed before and after the team news.** The props price history has
   629,862 prices and half of its player/market keys moved at least once. But the history has no
   fixture id, no player id and no kickoff time, and it is polled every 4 hours. Without those, no
   price can be placed before or after the lineup announcement. This is the core of the "does the
   bookmaker miss it?" test, so that test **cannot be run on today's data**.
4. **Thresholds are not set.** The gate's thresholds are your decisions (section E). Until you set
   them, the gate says `OWNER_DECISION_PENDING` and the research does not run.

**What was built.** The data readers, the matchup feature builder with a strict "known before the
decision" clock, the readiness gate, and the statistics (walk-forward splits, shrinkage bars,
false-discovery control, CLV and line-move tests). Synthetic tests show they behave correctly. The
readiness command runs on the real data and correctly answers NOT READY.

**What you need to decide** is listed in section F.

---

## A. Matchup features (real data only)

All features are computed **as of a decision time** `decision_ts`, the moment a tip would be made.
Each target row (fixture, attacker) carries its own `decision_ts`. Nothing is inferred.

| Feature | Source | Known before kickoff? |
|---|---|---|
| Opponent's absent players: count, defenders (`D`), goalkeeper (`G`) | Pre-match injury list (Pro `injury_snapshots` with `pre_kickoff=True`, v9 `injuries.parquet` only for rows fetched before kickoff); confirmed XI (lineups, about 60 min before kickoff) | **Yes, but only when the observation time is at or before `decision_ts`**. An absence with no observation time is dropped and counted. |
| Absentee importance: minutes share (player minutes ÷ team minutes × 11) and start share over the opponent's last `lookback_matches` matches | v9 `player_history` (minutes, started) | Yes. It uses matches dated strictly before the fixture date. |
| Opponent's shots and SoT conceded per match **with** and **without** the absentee in the starting XI, plus how many matches each figure rests on (`n_with`, `n_without`) | v9 `af_history_fullstats_fill` (team shots / SoT per fixture) + `player_history` (who started) | Yes. Strictly earlier matches only. |
| Attacker form: SoT, shots and goals per 90, mean minutes and start share over his last `form_matches` appearances | v9 `player_history` | Yes. Strictly earlier matches only. |
| Outcome (SoT ≥ k, scored) | `player_history` after full time / props settlement | **No.** Used only as the label. |

### Rules that make this point-in-time correct (implemented in `features.py` and tested)

* An absence counts only if `observed_at <= decision_ts`.
* Sources stamped by **our own poll before kickoff** (`observed_pre_kickoff`) are allowed. Sources
  **collected after the match** (`fetched_after_the_fact`: v9's injury and lineup backfill, sidelined
  spells) are refused by default. The caller can opt in for exploration only (`allow_after_the_fact=True`),
  and every row this touches is labelled `absence_clock='assumed'`. Assumed rows are **never** used in
  the edge test. Reason: the measured 18.8% of injury listings added after kickoff.
* Outcome-derived numbers use matches dated **strictly before** the fixture date. Same-day matches are
  excluded because `player_history` has a date but no kickoff time, so the order within one day
  cannot be proven.
* **Missing stays missing.** Counts from rows whose `count_source` is not `provider_rule` / `refetched`
  are treated as missing. A window with any missing count gives a missing feature, never the average
  of the rest. An absentee never seen for his team has unknown importance (NaN), not 0. If the
  opponent's absence list was never observed by the decision time, every absence feature is NaN and
  `absence_clock='none'`. An **observed empty** list is a real zero.
* `lookback_matches` and `form_matches` have no default. They are fixed in the pre-registration
  (section C) before any real data is looked at.

### Identity: no name matching

* The bridge from `player_history` to `fullstats` must be `(fixture_id, home/away side)`, not the club
  name. `fullstats` has 27,596 rows that share a fixture id with another row (13,076 ids, club-name
  aliases); their shots and SoT agree, but a name join would double-count them.
* Pro `team_news` stores the confirmed XI as **names only**. Matching names to player ids would be a
  proxy, so it is not done. Lineups count only once provider ids are stored: v9's lineups collector
  stores `player_id`, and Pro `team_news` must store ids too.
* Props prices are keyed by a player name and a "Home vs Away" string. Joining them to provider ids
  is required, and is **UNIDENTIFIABLE** today.

---

## B. The edge test: does the bookmaker already price the absence?

Prices needed per (fixture, player, market, book): `p_open` (first price), `p_decision` (the price we
could actually take at `decision_ts`), `p_post` (the first price after the team news is public), and
`p_close` (the last price before kickoff). All are de-vigged. `our_shift` is our model's probability
with the observed absences minus the same model with no absence (same inputs otherwise).

1. **Line-move test** (`evaluation.line_move_test`): regress `p_post − p_pre` on `our_shift`, with
   bootstrap resampling of whole matchdays. A slope near 1 means the market absorbs the news fully;
   a slope near 0 means it ignores it. This is descriptive: a slope below 1 is not yet an edge.
2. **Residual test, the deciding one** (`evaluation.residual_test`):
   `y − p_close = a + b·our_shift + c·prior_move + e`, with `prior_move = p_decision − p_open` (the
   market's own move up to our decision).
   **Null hypothesis H0: b ≤ 0**, meaning the closing price already contains everything our absence
   signal knows. The p-value is one-sided, from a matchday-cluster bootstrap.
   *The control is the move **before** the decision, not after.* The move after the decision shares
   `p_close` with the left-hand side, so it pushes `b` up even when the market prices the absence
   perfectly. A synthetic test demonstrates this bias (`test_controlling_for_the_post_decision_move_would_be_biased`).
3. **Takeable CLV** (`evaluation.takeable_clv`): mean `ln(odds_at_decision / odds_close)` at the
   **same book** at the price actually available at `decision_ts`, not a best-of-books close.
   (v9's `clv_records.csv` closes on the best of several books, so it cannot be used as is.)
   H0: mean CLV ≤ 0.
4. **Money check at takeable prices**: realised return at `odds_at_decision`, reported beside CLV,
   never alone.

**Minimum samples.** `evaluation.min_n_for_mean(sd, delta, alpha, power, design_effect)`, where:

* `sd` is the per-bet standard deviation measured on the first clean data;
* `delta` is the smallest effect worth acting on (owner decision);
* `design_effect = 1 + (m − 1)·ICC` is measured from matchday clustering.

No sample size is typed in here. Existing Pro gates are a precedent the owner may adopt:
`src/studies/evidence.py` uses `min_n` 150, and at least 10 bets and 5 matchdays before a cell is tested;
`src/player_v3/forward.py` uses 150 per market.

---

## C. Bars per player × league × market

* **Hierarchy and shrinkage** (`evaluation.nested_shrinkage`): an empirical-Bayes normal-normal model
  down market → league → role → player. Each node's raw mean is pulled toward its parent's posterior
  with `B = se² / (se² + τ²)`, where τ² is estimated by DerSimonian-Laird across that level's nodes with
  `n ≥ min_n`. A node below `min_n` takes its parent's value exactly. A player with few matches
  therefore stays at his role's number (tested).
* **The quantity shrunk** is the out-of-sample *realised − predicted edge* per bet, from walk-forward
  folds only. The **bar** (`evaluation.cell_bars`) is the smallest predicted edge whose shrunk
  realised edge is still above 0 with probability `confidence`:
  `bar = max(0, −posterior_mean + z_confidence · posterior_sd)`. `confidence` is an owner decision. While it
  is unset, every bar is NaN and its permission is `BLOCKED`.
* **Validation** (`evaluation.walk_forward_blocks`): walk-forward by matchday block. Train on blocks
  strictly before the test block, minus an embargo of `embargo_blocks`. The first `min_train_blocks`
  blocks are never tested. Nothing is tuned on a test block.
* **Multiple testing**: thousands of player cells will produce false edges by chance. On 5,000
  synthetic null cells, raw p < 0.05 "finds" hundreds of edges; BH finds at most a handful and BY finds
  none (tested). The rule is **Benjamini-Yekutieli** (`by_qvalues`), which stays valid when cells share
  matches. BH and Holm are reported beside it. Before deployment, the best cell also needs a White
  reality check, as `src/studies/evidence.py` already does.
* **Minimum n and matchdays before a bar counts**: owner decision, with the evidence.py precedent above.
  A cell below the minimum inherits its parent's bar and can never be more permissive than the parent.
* **Fail closed**: no bar means no tip. A cell with a bar is PAPER at most.
* **Pre-registration**: before the first real run, fix in a commit `lookback_matches`, `form_matches`,
  the decision lead time, the markets (SoT 1+/2+, anytime goalscorer), the hierarchy, `min_n`,
  `confidence`, the embargo and the q threshold. Anything changed after seeing results is a new
  hypothesis.

---

## D. How it would feed v9 props tiers later

* **Output contract**: one table per run with columns `src.props_matchup.BAR_COLUMNS`:
  `market, league, role, player_id, n_bets, n_matchdays, posterior_mean, posterior_sd, bar, q_value,
  permission, built_at, data_gate_sha`. Permission is `BLOCKED` or `PAPER` only. **There is no LIVE
  value in this package.**
* v9 would read the table read-only, the way Pro reads v9. A tip is shown only if
  `model_edge ≥ bar`, `q_value` is below the pre-registered threshold, and permission is PAPER, and it
  is labelled PAPER.
* v9's own invariant says player props are **PAPER ONLY, PERMANENTLY** (root CLAUDE.md invariant 2,
  quoted in `player_model/odds_fetcher.py`). Any step beyond paper needs the owner to change that
  invariant explicitly. It also needs the Clean Record milestone evidence (milestone/2): two months of
  results on repaired data from go-live. Until both, no real money.

---

## E. Data readiness gate

`python -m src.props_matchup --check-readiness` (exits 1 while not ready). Every threshold ships as
`None`. `None` gives `OWNER_DECISION_PENDING`, which blocks. A missing input gives `MISSING_INPUT`,
which blocks. The gate is READY only when every check is PASS.

| Check | Threshold key (owner sets) | Measured 2026-11-04 (v9 `data-truth-100` @ 76a2de5b, Pro @ 78580b42) |
|---|---|---|
| counts_verified | `max_unverified_count_share` | **1.0**: 876,130 of 876,130 rows `zeros_unverified` (no `count_source` column, no re-fetch file) |
| injury_lists_pre_kickoff | `min_injury_list_coverage` | **0.1694**: 82 of 484 finished fixtures in player_history's leagues, 2026-10-19 to 2026-10-31 |
| lineups_with_ids_pre_kickoff | `min_lineup_id_coverage` | **0.0**: v9 lineups absent; Pro team_news has 282 fixtures seen pre-kickoff, names only |
| fullstats_concessions | `min_fullstats_coverage` | **0.5263**: 16,043 of 30,482 player_history fixtures |
| prices_pre_and_post_news | `min_keys_priced_pre_and_post_news` | **0**: UNIDENTIFIABLE, because there is no fixture_id, player_id or kickoff time in the props prices |
| prop_odds_identity | `min_prop_odds_identity_share` | **0.0**: the columns are absent |
| settlement_identity | `min_settlement_identity_share` | **0.7376**: 15,466 of 20,967 WIN/LOSS ledger rows have player_id and fixture_id |

Result: **NOT READY** (7 of 7 checks `OWNER_DECISION_PENDING`; at least 4 would fail under any
reasonable threshold: counts 100% unverified, no lineup ids, no pre/post-news prices, no props-price
identity).

---

## F. Owner decisions

1. **The seven gate thresholds** in section E.
2. **Timestamped props prices: collect them.** The current history cannot support the test. The minimum
   needed per (fixture, player, market, book):
   * provider `fixture_id` and kickoff time on every price row;
   * a provider `player_id`, or a reviewed id map;
   * one snapshot shortly before lineups (about T−75 min) and one after (about T−15 min), plus the
     existing open snapshots.

   The source is the existing ones: OddsAPI (uk,eu regions) and API-Football odds (Bet365 / Betano).
   OddsAPI bills markets × regions per event call (`player_model/odds_fetcher.py`), so two extra
   snapshots cost about 2 × markets × regions credits per fixture. **The money cost is UNIDENTIFIABLE
   from the repos**, because the plan price and remaining quota are not stored. That code also records
   that widening props regions exhausted the OddsAPI quota on 2026-09-04 and stopped the staked tips.
   Any extra props polling must be budgeted against the staked O/U product first. API-Football calls used
   per day are logged in v9 `output/collect/af_budget.json` (30,800 to 53,590 a day on 2026-11-02 to 04),
   but the plan limit is not in the repo.
3. **Store provider ids in Pro team_news** (or rely on v9 lineups with a pre-kickoff poll). Without ids,
   lineup absences cannot be used.
4. **The pre-registration values** in section C: `confidence`, `min_n`, minimum matchdays, the q threshold,
   the decision lead time, `lookback_matches` and `form_matches`.

---

## G. Hypotheses to test once the data is ready (pre-register before looking)

1. **Backup goalkeeper → anytime goalscorer.** A first-choice keeper (high start share) out, confirmed
   pre-match, raises opposing goal probability more than SoT probability. The test is the residual on
   the goals market vs the SoT 1+ market.
2. **Late defensive news is under-priced, known news is not.** Centre-back absences that first appear in
   the confirmed XI (not on the pre-match injury list) show a line-move slope below 1 and a positive
   residual. Long-known absences (spells started well before) show slope near 1.
3. **Concession delta carries the signal.** The size of the opponent's SoT-conceded difference with/without
   the absentee (`top_def_sot_against_delta`, with enough `n_without`) predicts the residual. Absence
   counts alone do not.
4. **Thin markets absorb less.** League-level shrinkage of `b` is larger in leagues with fewer books
   (Austrian Bundesliga, Championship, Scandinavian leagues) than in top-five leagues.
5. **High-volume shooters gain most.** The interaction of attacker `form_sot_p90` with defensive absence
   predicts the SoT 2+ residual more than the SoT 1+ residual.

---

## Inventory of real inputs (v9 `origin/data-truth-100` @ 76a2de5b, Pro `origin/data-truth-100` @ 78580b42)

| Input | Rows | Range | Key columns | Verification / clock |
|---|---|---|---|---|
| `player_history.parquet` (monthly parts) | 876,130 | 2022-08-12 to 2026-10-31; 30,482 fixtures; 21,232 players; 31 leagues | fixture_id, player_id, team, is_home, position (M 344,904 / D 271,363 / F 199,343 / G 60,009 / blank 511), minutes, started, shots_total, shots_on_target, goals | **100% zeros_unverified**; no nulls in minutes or SoT, which is the zero-fill signature |
| `output/collect/player_history_refetch*`, `player_refetch_fixtures.parquet` | absent | | | re-fetch not run yet |
| `output/collect/sidelined_players.parquet` | 21,231 players | fetched 2026-11-02 12:14 to 15:54 UTC | player_id, n_spells, fetched_at | after the fact |
| `output/collect/sidelined_spells.parquet` | 52,014 spells, 11,726 players | start 2009-08-21 to 2026-09-17; 1,531 with no end | player_id, type (Injury 4,431, Knock 4,295, Suspended 3,564, ...), start, end | after the fact: when each spell was known is unproven |
| `output/collect/injuries*.parquet` | absent | | | collection from 2026-11-05 |
| `output/collect/lineups/`, `lineups_fixtures.parquet` | absent | | | collection from 2026-11-05 |
| Pro `output/studies/injury_snapshots.parquet` | 14,782 (7,226 pre-kickoff) | captured 2026-10-19 to 2026-11-01; 111 fixtures pre-kickoff; 5 leagues | captured_at, af_fixture_id, team_id, player_id, type, pre_kickoff | **pre-kickoff clock proven** |
| Pro `data/season_2026_27/team_news` | 564 | first seen 2026-08-30 to 2026-11-01; 282 fixtures | fixture_id, kickoff_utc, first_seen_ts, starters (**names**) | pre-kickoff clock proven; no player ids |
| `output/collect/af_history_fullstats_fill.parquet` | 63,805 (49,285 fixture ids) | 2019-02-22 to 2026-11-04; 28 leagues | fixture_id, home/away shots, SoT | outcome; 414 team rows lack shots or SoT; 13,076 ids duplicated (consistent) |
| `output/collect/player_profiles.parquet` | 51,722 (20,989 players) | | player_id, season, height_cm (5,533 rows missing), birth_date | after the fact |
| `output/player_prop_odds_history.csv` + `_archive/` | 629,862 | snapshots 2026-06-28 to 2026-11-02; matches to 2026-11-14 | snapshot_ts, match_date, match (string), player (name), market, odds, source, bookmaker | timestamps yes; **no fixture/player id, no kickoff**; distinct-price append every 4 h; 214,260 keys, 109,216 with 2+ prices; 259,241 rows (OddsAPI) have no bookmaker |
| `output/clv_records.csv` | 8,471 | | odds_bet, odds_close (best of books), clv_pct | close is not same-book |
| `output/player_ledger.csv` | 33,677 | signal 2026-06-14 onward | market_odds at signal, result (WIN 6,702 / LOSS 14,265 / VOID 8,606), player_id, fixture_id | 73.8% of settled rows carry both ids |

Reproduce: `V9_LOCAL=<wowza-betting checkout at data-truth-100> python -m src.props_matchup --inventory`.

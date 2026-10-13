# Player Model — CURRENT STATE (audit for Player Model V3 / Player-vs-Player Edge Lab)

Audited 2026-10-13 against the live code and data (v9 `main` at 2ba8ebe7 and later, Pro `main`).
Every number below was measured from code or data in this session, not taken from comments.

## 1. Data

| Item | Value |
|---|---|
| `player_history.parquet` | directory of 5 season parts (2022–2026), **857,450 rows**, 21,100 players, 29,821 fixtures, 31 leagues, 2022-08-12 → 2026-10-13 |
| Columns | 212: 47 raw per-match stats + identifiers, 138 model features, 8 targets |
| Who is in it | **only players who appeared** (no 0-minute rows): 75.9% starts, 24.1% sub appearances |
| Players per team-fixture | median 15; team shots per fixture median 9 (summable from player rows) |
| Positions | G/D/M/F only (M 337k, D 266k, F 196k, G 59k, blank 398). **No LW/RB/CB/DM labels, no formation, no lineup grid** |
| Lineup timing | **not stored**: predict reads API-Football lineups at run time (`player_model/predict.py:590-604`) but the publication time is not logged |
| Substitution timing | not stored; only `minutes` + `started` (bench minutes are inferable: started=0, minutes>0) |

**Raw primitives available per player-match** (all ~100% non-null): minutes, started, goals, assists,
shots_total, shots_on_target, yellow/red cards, key_passes, rating, fouls_committed, fouls_drawn,
duels_total, duels_won, passes_total, offsides, tackles_total, interceptions, dribbles_attempted,
dribbles_success, dribbles_past, goals_conceded, saves, penalties (scored/missed/won/saved), set-piece
goals/assists, headed goals, team_corners, height_cm, weight_kg, age, referee, injury fields.
**Not available:** aerial duels specifically (only all duels), touches in box, xG, passes into box,
positional heatmaps.

## 2. Current model (v9 `player_model`)

| Item | Value |
|---|---|
| Features | **138** (`config.PLAYER_FEATURE_COLS`), all present in history. Roughly 76 rate/form primitives, 39 opponent/matchup, 24 handcrafted composites (`*_score/_index/_composite/_edge`) — families overlap |
| Targets | goals, goals2, assists, sot (1+), sot2, sot3, sot4, cards — **8 independent binary models** |
| Learner | logistic + **HistGradientBoosting** (switched from classic GB 2026-10-13, validated in `output/studies/PROPS_LEARNER.md`), averaged at predict |
| Split | chronological: first 68% fit, next 12% Platt calibration, last 20% test (`model.train`) |
| Calibration | one **global Platt** per market per learner |
| Filter | `n_prev_games >= 1`; rows with no label dropped (fix 2026-10-12) |
| Retrain | weekly, `player_props_train.yml`, ~7 min; promotion gate = log-loss rise <= 0.03 |

Held-out metrics stored in the live pickles (test n = 171,490; HGB):

| Market | AUC | Log loss |
|---|---|---|
| goals | 0.744 | 0.2589 |
| goals2 | 0.842 | 0.0425 |
| assists | 0.681 | 0.2173 |
| sot (1+) | 0.737 | 0.4734 |
| sot2 | 0.804 | 0.1813 |
| sot3 | 0.851 | 0.0594 |
| sot4 | 0.888 | 0.0176 |
| cards | 0.622 | 0.3734 |

These are measured on **appearing players** only, so they describe P(event | appears), not P(event)
for a pre-match squad member who may not play.

## 3. Prices and CLV

| Item | Value |
|---|---|
| `player_prop_odds_history.csv` | 387,447 rows, **2026-06-28 → now** (3.5 months) |
| Sources / books | OddsAPI + API-Football; **3 books only** (Bet365 104k, Betano 92k, 1xBet 0.8k) |
| Depth | 156,340 player-market-fixtures; **median 1 book**, p90 2; **median 2 snapshots** |
| Sides | **OVER only.** `odds_fetcher._best_price` keeps `Over`; Under prices are discarded at fetch. **Two-way de-vig is impossible from stored data** |
| Markets | goals 256k, sot 37k, cards 32k, sot2 29k, sot3 16k, assists 12k, sot4 6k |
| Attachment to tips | exact-name only until ea9858c4 (2026-10-13); on that day 72 → 182 priced after the initial+surname fix |
| Priced share of settled tips | 785 of 3,631 settled goals/SOT/assist tips since 08-15 (21.6%); falling: Aug 487, Sep 262, Oct 36 |
| CLV (`clv_records.csv`) | 3,071 player rows, 2,867 with a close; **0 two-sided** |

**Model vs price, priced settled props since 08-15:** model mean 28.8%, book implied 47.1%, actual hit
~35%. Book implied exceeds reality by ~12 pts (one-sided prop margin); the model under-shoots
reality by ~6 pts (it is trained on all appearances incl. 24% sub cameos; bets are typically on
starters). "Model > price" therefore fires on 6% of priced props — mostly a minutes artefact, not skill.

## 4. "Player-vs-player" today — verified

All 39 opponent/matchup features are **opponent-TEAM or opponent-UNIT aggregates**. None pairs an
attacker with an individual defender or a projected marker:
* `opp_def_aerial_win_rate / fouls_pg / cards_pg`: rolling mean of the opponent's defenders as a group,
  shifted (`feature_engineering.py:483-517`). Note "aerial" is **all duels**, not aerial duels.
* `opp_gk_save_rate`, `opp_*_conceded_vs_fwd/mid_pg`: opponent team/unit rolling averages.
* composites (`forward_matchup_score`, `tackle_dribble_clash`, ...) multiply a player rate by one of these.

## 5. Train/serve gaps and leaks found

1. **`opp_def_mean_height` uses the defenders who actually played in the target fixture**
   (`feature_engineering.py:525-537`, grouped by the same `fixture_id`, no shift). Training sees the real
   lineup; serving does not know it unless lineups are confirmed. Height is static, so the leak is mild,
   but it is post-match information.
2. Model trained on appearances; served on a pre-match squad (lineup guard only when both XIs are posted).
3. Prices are one-sided, single-book; the "edge" field compares a played-only model with a margin-laden
   one-sided price.

## 6. Prior evidence to respect

* `PROPS_LEARNER.md`: HGB ≥ classic GB on all 8 markets (2026-10-12).
* Pro Prediction Lab player track: goalscorer models discriminate (AUC ~0.74) — accuracy, not edge.
* Eight earlier props-edge tests (memory: props paper-only, no repeatable edge).
* `PROPS_SEGMENTS.md`: pre-registered forward test of attacking D/M, window from 2026-10-14.
* v11 methodology to reuse: market baseline first, residual learner on top, CLV gate, de-vig before compare.

## 7. Consequences for V3 (what can be tested, and how well)

| Hypothesis | Testable now? | Constraint |
|---|---|---|
| H1 expected minutes | **Yes** — 4 seasons of starts/minutes | no lineup timestamps → "confirmed lineup" arm cannot be backtested honestly |
| H2 count distribution (SOT) | **Yes** | — |
| H3 usage/share | **Yes** — team totals summable per fixture | shift before use |
| H4 opponent personnel | **Partly** — projected from opponent's recent appearances | no fine positions |
| H5 attacker × defender | **Weakly** — no LW/RB labels, so no side-specific marker; role must be inferred | |
| H6 Wowza adds to market | **Weakly** — one-sided, mostly single-book, 3.5 months | small n per market |
| H7 edge cells | **Insufficient data** expected for most cells | |

Recommended minimal v9 logging hooks (NOT done in this task, need owner approval): store Under prices
and per-book quotes in `player_prop_odds_history`; store the lineup fetch time in predict.

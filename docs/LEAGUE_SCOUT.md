# League scout

**Question:** which leagues outside Wowza's current set have a market soft enough to beat in
O/U 1.5 / 2.5 / 3.5 and BTTS?

**Why forward collection:** API-Football's `/odds` is pre-match only. Odds for a finished match
cannot be fetched at any price, so no new league can be backtested on betting results. The only
way to judge a market is to record its prices from now on. Started 2026-10-08.

## What runs

`pro_scout.yml`, every 2 hours, `python -m src.scout.collect` then `python -m src.scout.report`.

| Table | What | Grain |
|---|---|---|
| `scout_odds` | Pinnacle, Bet365 and cross-book median, O/U 1.5/2.5/3.5 and BTTS | change-log per (fixture, market, side, book); every observation in the last 3 h before kickoff |
| `scout_results` | finished matches: 4 past seasons + the current one | one row per fixture (dedupe on `fixture_id`) |
| `scout_model` | baseline goals model probabilities | frozen once per fixture at first sight of odds |

Watch list: `registry/scout_leagues.json`: 200 leagues, the owner's 30 lower tiers as priority 1.
Rebuilt only on purpose (`python -m src.scout.leagues --build <probe csv>`).

## How a league is judged (`output/scout/REPORT.md`)

1. **Market skill.** Brier of the de-vigged closing price compared with the league's base rate.
   A market barely better than the base rate is pricing little beyond the league average.
2. **Residual test.** Does the frozen model add information to the closing price? A logistic
   regression of the result on logit(market) and logit(model) gives the model's coefficient and z.
3. **Paper bets.** Model edge > 5 points against Bet365 at freeze time: flat ROI, and the share of
   bets on one side (a single-sided book is the failure signature v9's MLS showed).

The reference price is Pinnacle where it quotes the market. Pinnacle does not offer BTTS through
API-Football, so BTTS uses the cross-book median.

Status per league × market: COLLECTING (< 100 settled), EARLY (100–299), READABLE (≥ 300). A league
moves toward v9 only as a paper league first (`PAPER_LEAGUES`), and only on READABLE evidence.

## Known limits

- The baseline model is independent Poisson with per-league calibration-in-the-large. It is a
  probe for signal, not a production model. Leagues that pass would get a proper model.
- The closing price is the last price observed before kickoff. Inside 3 hours every observation is
  kept, but runs land on GitHub's schedule, so "close" can be up to a few hours early. The stored
  `minutes_to_kickoff` says how early.
- Odds tables are change-logs: carry forward per key before aggregating.

## Data Truth rules (2026-11-10)

Audit of 2026-11-10 against v9's five data-truth rules; every scout number now goes through
`src/scout/truth.py`. Raw tables stay append-only and are never rewritten: corrections live beside
them and are applied by the reader.

| Rule | What the scout does now |
|---|---|
| 90-minute settlement | AET / PEN results use the provider's `score.fulltime`. New rows carry it (`goals_basis = fulltime_90`, the 120-minute `goals` kept in `goals_home_api` / `goals_away_api`); older rows get it from `scout_results_ft90`, fetched by id. Without it the goals are missing, never the 120-minute total. |
| Missing results | Priced or frozen fixtures past kickoff + 3 h without a result are re-fetched by id (within `--history-budget` and the quota floor). The provider's reason for an unfinished fixture (PST, CANC, ABD, AWD, WO, ...) is stored in `scout_fixture_status`. |
| One match, one row | One fixture per `/odds` answer before the median; one row per (fixture, market, selection, book, snapshot) before an append; history skips fixture ids already stored. Readers collapse identical repeats and drop a key with two different prices. |
| Genuine close everywhere | The hypotheses rule: last quote before the ACTUAL kickoff, at most 60 min old; Pinnacle, else a median of at least 3 books. Report, league status, promotion gate and `market_matrix` all use it. |
| Bet-time price | Paper bets use Bet365 at freeze time, observed at most 60 min before the freeze (the same age limit). |
| Identity and reschedules | Model rows count only with the result's league, home and away ids, frozen before the actual kickoff. A kickoff moved more than 48 h is void (owner settlement rule). |
| No stand-ins | No prediction for a team the league fit never saw (`UNKNOWN_TEAM`, probabilities missing); `FEATURE_DEGRADED` rows are never scored. Missing kickoff stays missing. Base rates use only results before each freeze. The regression harness drops rows with missing features. |
| Names | Latest provider name per team id, trimmed. The specials `fixture_key` carries the country and league id. |
| v9 leagues | Promotion compares by `api_football_id` with v9 `config/leagues.json` and blocks when it cannot read it. v9-enabled leagues are not watched (`removed_v9_enabled` in the watch list: France Ligue 2, id 62). |
| Coverage | `output/scout/scout_health.json` and REPORT.md list per league: odds and genuine-close coverage, last price, stale (in season, no price for more than 10 days), and `NO_ODDS_OFFERED` where every recorded poll came back empty. |

### Research gates, never staking bars

`EDGE_BAR` (report), `CRITERIA` and the BH family (hypotheses), `GATE`, the score bands and
`MAX_DEFECT_SHARE` (promotion), and the regression harness's pooled margin are PRE-REGISTERED
RESEARCH GATES (owner, 2026-11-10). They decide what to study and what to propose for onboarding,
never what to bet or how much. No staking or betting code may read them
(`tests/test_scout_data_truth.py`). Any bar that bets is per league, like v9's.

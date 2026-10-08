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

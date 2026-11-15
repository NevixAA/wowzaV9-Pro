"""1X2 review (src/studies/onex2_review.py): no look-ahead, honest de-vig, Holm, bet rules."""
import numpy as np
import pandas as pd

from src.studies import onex2_review as R


def _league(n_days=700, teams=10, seed=0, league="L"):
    rng = np.random.default_rng(seed)
    names = [f"T{i}" for i in range(teams)]
    rows = []
    d0 = pd.Timestamp("2023-01-01")
    for k in range(n_days):
        day = d0 + pd.Timedelta(days=3 * k)
        h, a = rng.choice(names, 2, replace=False)
        hg, ag = rng.poisson(1.5), rng.poisson(1.1)
        rows.append({"date": day, "league": league, "home_team": h, "away_team": a,
                     "home_goals": hg, "away_goals": ag,
                     "row_id": f"{day:%Y-%m-%d}|{league}|{h}|{a}"})
    m = pd.DataFrame(rows).drop_duplicates("row_id")
    m["y"] = np.where(m.home_goals > m.away_goals, 0, np.where(m.home_goals == m.away_goals, 1, 2))
    return m


def test_power_devig3_sums_to_one_and_refuses_non_prices():
    p = R.power_devig3(np.array([[2.0, 3.4, 3.8], [1.5, 4.0, np.nan], [1.0, 3.0, 5.0]]))
    assert abs(p[0].sum() - 1) < 1e-9 and p[0, 0] > p[0, 1] > p[0, 2]
    assert np.isnan(p[1]).all() and np.isnan(p[2]).all()          # nothing assumed


def test_dc_month_prediction_ignores_later_results():
    m = _league()
    mo = pd.Timestamp("2026-01-01")
    a = R._dc_job(("L", m, mo, 180.0, None))
    later = m.copy()
    late = later["date"] >= mo + pd.offsets.MonthBegin(1)
    later.loc[late, "home_goals"] = 9                              # future results changed
    b = R._dc_job(("L", later, mo, 180.0, None))
    assert a and a == b


def test_dc_frozen_fit_does_not_learn_from_the_holdout():
    m = _league()
    fz = pd.Timestamp("2025-12-01")
    a = R._dc_job(("L", m, pd.Timestamp("2026-03-01"), 180.0, fz))
    assert a
    changed = m.copy()
    changed.loc[changed["date"] >= fz, "away_goals"] = 7
    b = R._dc_job(("L", changed, pd.Timestamp("2026-03-01"), 180.0, fz))
    assert [x[0] for x in a] == [x[0] for x in b]
    assert np.allclose([x[1:] for x in a], [x[1:] for x in b])


def test_elo_is_pre_match_and_same_day_results_do_not_leak():
    m = _league()
    e1 = R.elo_pre_match(m, 25.0, 50.0)
    cut = m["date"].iloc[200]
    changed = m.copy()
    changed.loc[changed["date"] >= cut, "home_goals"] = 8         # this day and later
    e2 = R.elo_pre_match(changed, 25.0, 50.0)
    upto = m.loc[m["date"] <= cut, "row_id"]
    assert np.allclose(e1[upto], e2[upto])                         # same-day value unchanged too


def test_holm_matches_the_textbook_example():
    p = np.array([0.01, 0.04, 0.03, np.nan])
    h = R.holm(p)
    assert np.allclose(h[:3], [0.03, 0.06, 0.06]) and np.isnan(h[3])


def test_paired_bootstrap_detects_a_clear_improvement():
    rng = np.random.default_rng(1)
    dates = np.repeat(np.arange(60), 10)
    pv, ci = R.paired_bootstrap(-0.05 + rng.normal(0, 0.01, 600), dates, 2000, 7)
    assert pv < 0.01 and ci[1] < 0


def test_league_wide_rule_bets_every_priced_match_of_that_league_only():
    p = pd.DataFrame({"row_id": list("abcd"), "date": pd.to_datetime(["2025-01-01"] * 4),
                      "league": ["X", "X", "Y", "X"], "y": [1, 0, 1, 1],
                      "p_home": .4, "p_draw": .3, "p_away": .3,
                      "bet_home": [2.0, 2.0, 2.0, 2.0], "bet_draw": [3.2, 3.3, 3.4, np.nan],
                      "bet_away": [3.5, 3.5, 3.5, 3.5]})
    b = R.candidate_bets(p, {"family": "league_wide", "league": "X", "outcome": "draw"})
    assert list(b["row_id"]) == ["a", "b"]                         # d has no draw price
    assert np.allclose(b["pnl"], [2.2, -1.0])


def test_best_ev_rule_uses_the_price_with_the_vig():
    p = pd.DataFrame({"row_id": ["a"], "date": pd.to_datetime(["2025-01-01"]), "league": ["X"],
                      "y": [0], "p_home": [0.5], "p_draw": [0.3], "p_away": [0.2],
                      "bet_home": [2.1], "bet_draw": [3.0], "bet_away": [4.0]})
    b = R.candidate_bets(p, {"family": "best_ev", "t": 0.04})
    assert list(b["pick"]) == [0] and abs(b["pnl"].iloc[0] - 1.1) < 1e-12
    assert R.candidate_bets(p, {"family": "best_ev", "t": 0.06}).empty

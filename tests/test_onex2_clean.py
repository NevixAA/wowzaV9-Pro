"""The served 1X2 model (src/models/onex2_clean.py) and its monthly retrain (owner 2026-11-09)."""
import json

import numpy as np
import pandas as pd
import pytest

from src.models import onex2_clean as C


def _extract(tmp_path, n_days=1500, leagues=("L1", "L2"), seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    d0 = pd.Timestamp("2022-01-01")
    for lg in leagues:
        teams = [f"{lg}_T{i}" for i in range(10)]
        strength = {t: rng.normal(0, 0.3) for t in teams}
        for k in range(n_days):
            day = d0 + pd.Timedelta(days=k)
            h, a = rng.choice(teams, 2, replace=False)
            hg = rng.poisson(np.exp(0.3 + strength[h] - strength[a]))
            ag = rng.poisson(np.exp(0.1 + strength[a] - strength[h]))
            rows.append({"date": day, "league": lg, "home_team": h, "away_team": a,
                         "home_goals": hg, "away_goals": ag,
                         "f1": strength[h] + rng.normal(0, .1), "f2": strength[a] + rng.normal(0, .1)})
    m = pd.DataFrame(rows)
    m["row_id"] = (m["date"].dt.strftime("%Y-%m-%d") + "|" + m["league"] + "|" + m["home_team"]
                   + "|" + m["away_team"])
    m = m.drop_duplicates("row_id")
    m[["date", "league", "home_team", "away_team", "home_goals", "away_goals", "row_id"]].to_parquet(
        tmp_path / "matches.parquet")
    m.to_parquet(tmp_path / "features.parquet")
    p = m[["row_id"]].assign(**{"class": "FD_ENTRY", "o_home": 2.2, "o_draw": 3.3, "o_away": 3.4})
    p.to_parquet(tmp_path / "prices.parquet")
    (tmp_path / "meta.json").write_text(json.dumps({"feature_columns": ["f1", "f2"], "require_present": [],
                                                    "feature_fingerprint": "fp1", "v9_commit": "abc",
                                                    "frame_hash": "h"}), encoding="utf-8")
    return m


def test_elo_state_matches_the_review_and_keeps_final_ratings():
    from src.studies import onex2_review as R
    m = pd.DataFrame({"date": pd.to_datetime(["2025-01-01", "2025-01-01", "2025-01-08"]),
                      "league": "L", "home_team": ["A", "C", "A"], "away_team": ["B", "D", "C"],
                      "home_goals": [2, 0, 1], "away_goals": [0, 0, 1], "row_id": ["r1", "r2", "r3"]})
    pre, final = C.elo_state(m, 25.0, 0.0)
    assert pre.equals(R.elo_pre_match(m, 25.0, 0.0))
    assert pre["r1"] == 0 and pre["r2"] == 0                    # same day: nobody updated yet
    assert final["L"]["A"] > final["L"]["B"]


def test_an_unseen_club_enters_at_the_league_mean_like_training():
    final = {"L": {"A": 40.0, "B": -40.0}}
    assert C.elo_diff_upcoming(final, "L", "A", "NEW", 0.0) == 40.0
    assert C.elo_diff_upcoming(final, "OTHER", "A", "B", 0.0) is None


def test_training_ignores_everything_on_or_after_asof(tmp_path):
    m = _extract(tmp_path)
    asof = pd.Timestamp("2025-06-01")
    art1, _ = C.train(tmp_path, asof)
    fut = m["date"] >= asof
    m2 = m.copy()
    m2.loc[fut, "home_goals"] = 9                                # future results changed
    m2[["date", "league", "home_team", "away_team", "home_goals", "away_goals", "row_id"]].to_parquet(
        tmp_path / "matches.parquet")
    m2.to_parquet(tmp_path / "features.parquet")
    art2, _ = C.train(tmp_path, asof)
    X = m[m["date"] < asof].tail(50).assign(elo_diff=0.0)
    p1 = C.predict_mnlogit(art1["model"], X)[["p_home", "p_draw", "p_away"]].to_numpy()
    p2 = C.predict_mnlogit(art2["model"], X)[["p_home", "p_draw", "p_away"]].to_numpy()
    assert np.allclose(p1, p2)
    assert art1["blend"] is not None and art1["model"]["window"][1] == "2025-06-01"


def test_a_league_the_model_never_saw_is_not_served(tmp_path):
    m = _extract(tmp_path)
    art, _ = C.train(tmp_path, pd.Timestamp("2025-06-01"))
    X = m.head(5).assign(elo_diff=0.0)
    X.loc[X.index[:2], "league"] = "UNKNOWN"
    p = C.predict_mnlogit(art["model"], X)
    assert len(p) == 3 and np.allclose(p[["p_home", "p_draw", "p_away"]].sum(axis=1), 1)


def _upcoming(tmp_path, art, fingerprint):
    up = tmp_path / "up"
    up.mkdir()
    pd.DataFrame({"fixture_key": ["k1"], "league": ["L1"], "home_team": ["L1_T1"],
                  "away_team": ["L1_T2"], "f1": [0.1], "f2": [-0.1]}).to_parquet(up / "upcoming_features.parquet")
    pd.read_parquet(tmp_path / "matches.parquet").to_parquet(up / "matches.parquet")
    (up / "meta.json").write_text(json.dumps({"feature_fingerprint": fingerprint, "reasons": {}}),
                                  encoding="utf-8")
    return up


def test_serving_refuses_a_different_v9_feature_code(tmp_path):
    _extract(tmp_path)
    art, _ = C.train(tmp_path, pd.Timestamp("2025-06-01"))
    p, info = C.serve(art, _upcoming(tmp_path, art, "OTHER"))
    assert p.empty and info["refused"].startswith("FEATURE_CODE_CHANGED")


def test_serving_refuses_a_different_sklearn_version(tmp_path):
    _extract(tmp_path)
    art, _ = C.train(tmp_path, pd.Timestamp("2025-06-01"))
    art["sklearn_version"] = "0.1.0"
    p, info = C.serve(art, _upcoming(tmp_path, art, "fp1"))
    assert p.empty and info["refused"].startswith("SKLEARN_VERSION_CHANGED")


def test_serving_gives_probabilities_and_the_blend_needs_a_real_price(tmp_path):
    _extract(tmp_path)
    art, _ = C.train(tmp_path, pd.Timestamp("2025-06-01"))
    p, info = C.serve(art, _upcoming(tmp_path, art, "fp1"))
    assert len(p) == 1 and abs(p[["p_home", "p_draw", "p_away"]].sum(axis=1).iloc[0] - 1) < 1e-9
    trio = p[["p_home", "p_draw", "p_away"]].iloc[0].tolist()
    assert C.blend_row(art, trio, [2.0, 3.4, 3.8]) is not None
    assert C.blend_row(art, trio, [2.0, np.nan, 3.8]) is None      # nothing assumed


def test_research_cell_needs_live_bets_for_a_verdict(tmp_path, monkeypatch):
    from src.pipelines import train_1x2_clean as T
    m = _extract(tmp_path, leagues=("Dutch Eredivisie",))
    P = pd.read_parquet(tmp_path / "prices.parquet")
    pd.concat([P.assign(**{"class": "FD_BET365_ENTRY"}), P.assign(**{"class": "FD_CLOSE"})]).to_parquet(
        tmp_path / "prices.parquet")
    r = T.evaluate_cells(tmp_path, pd.Timestamp("2025-06-01"), None)
    cell = r["cells"][0]
    assert cell["history"]["n"] > 100 and cell["verdict"].startswith("ACCRUING")
    paper = pd.DataFrame({"research_cell": [cell["id"]] * 3, "result": [1, 0, 1],
                          "research_odds": [3.4, 3.4, 3.4], "match_date": ["2025-07-01"] * 3})
    r2 = T.evaluate_cells(tmp_path, pd.Timestamp("2025-06-01"), paper)
    live = r2["cells"][0]["live"]
    assert live["n"] == 3 and abs(live["roi"] - (2 * 2.4 - 1) / 3) < 1e-12
    assert r2["cells"][0]["verdict"] != "PROVEN"                  # 3 bets can never prove anything


def test_paper_log_refuses_without_a_clean_model(monkeypatch, capsys):
    from src.pipelines import paper_1x2 as pp
    monkeypatch.setattr(C, "load", lambda: None)
    assert pp.log_picks().empty
    assert "no clean 1X2 model" in capsys.readouterr().out


def test_paper_log_never_falls_back_to_the_stale_dixon_coles_file():
    import inspect
    from src.pipelines import paper_1x2 as pp
    src = inspect.getsource(pp)
    assert "model_1x2.json\"" not in src and "_models()" not in src


@pytest.mark.parametrize("name", ["MODEL_FILE", "TOP_PCT"])
def test_retired_paper_settings_are_gone(name):
    from src.pipelines import paper_1x2 as pp
    assert not hasattr(pp, name)


def test_logged_row_carries_model_blend_and_research_cell(monkeypatch, tmp_path):
    import datetime as dt
    from src.data import season_store as store
    from src.data import v9_config
    from src.pipelines import paper_1x2 as pp
    now = dt.datetime(2026, 11, 5, 12, tzinfo=dt.timezone.utc)
    fx = pd.DataFrame({"fixture_key": ["k1", "k2"], "league": ["Dutch Eredivisie", "Championship"],
                       "kickoff_utc": ["2026-11-06T19:00:00+00:00", "2026-11-06T19:45:00+00:00"],
                       "match_date": ["2026-11-06", "2026-11-06"],
                       "home_team": ["Ajax", "Derby County"], "away_team": ["PSV", "Bolton Wanderers"]})
    art = {"name": "mnlogit_clean", "calc_version": "2.0.0", "asof": "2026-11-01", "v9_commit": "x",
           "blend": None}
    monkeypatch.setattr(C, "load", lambda: art)
    monkeypatch.setattr(pp, "_v9_root", lambda: tmp_path)
    monkeypatch.setattr(store, "read", lambda t: fx if t == "fixtures" else pd.DataFrame())
    monkeypatch.setattr(v9_config, "canonical_league", lambda x: x)
    monkeypatch.setattr(C, "run_bridge", lambda *a, **k: {})
    probs = pd.DataFrame({"fixture_key": ["k1", "k2"], "league": ["Dutch Eredivisie", "Championship"],
                          "home_team": ["Ajax", "Derby"], "away_team": ["PSV", "Bolton"],
                          "p_home": [.5, .4], "p_draw": [.25, .3], "p_away": [.25, .3]})
    monkeypatch.setattr(C, "serve", lambda a, d: (probs, {}))
    monkeypatch.setattr(C, "blend_row", lambda a, p, o: [0.45, 0.30, 0.25])
    monkeypatch.setattr(pp, "_latest_prices", lambda: pd.DataFrame({"x": [1]}))
    snap = pd.Series({"o_home": 2.0, "o_draw": 3.6, "o_away": 3.5, "m_home": .48, "m_draw": .27,
                      "m_away": .25, "overround": 1.05, "snapshot_at": pd.Timestamp("2026-11-05 08:00")})
    monkeypatch.setattr(pp, "_one_fixture", lambda *a, **k: snap)
    d = pp.log_picks(now=now)
    a = d.set_index("fixture_key")
    assert a.loc["k1", "research_cell"] == "LEAGUE_WIDE|Dutch Eredivisie|draw"
    assert a.loc["k1", "research_pick"] == "DRAW" and a.loc["k1", "research_odds"] == 3.6
    assert pd.isna(a.loc["k2", "research_cell"])                   # only the cell's league
    assert a.loc["k2", "pb_home"] == 0.45 and a.loc["k2", "blend_price_class"] == "SHARP_LATEST_PRE_KICKOFF"
    assert a.loc["k2", "model_home_team"] == "Derby" and a.loc["k2", "home_team"] == "Derby County"
    assert (a["calc_version"] == "2.0.0").all()

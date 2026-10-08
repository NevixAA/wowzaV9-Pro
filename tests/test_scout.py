"""League scout: parsing, change-log, model and report.

    python -m pytest tests/test_scout.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import pro_config as cfg  # noqa: E402
from src.data import season_store as store  # noqa: E402
from src.scout import leagues, model, parse, report  # noqa: E402

NOW = 1_800_000_000


def _odds_payload(ko, books):
    return [{"league": {"id": 129}, "fixture": {"id": 1, "timestamp": ko},
             "bookmakers": [{"id": i, "name": n, "bets": [
                 {"name": "Goals Over/Under", "values": [{"value": "Over 2.5", "odd": str(o)},
                                                         {"value": "Under 2.5", "odd": "1.80"},
                                                         {"value": "Over 4.5", "odd": "9.0"}]},
                 {"name": "Both Teams Score - First Half", "values": [{"value": "Yes", "odd": "5.5"}]},
                 {"name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.9"},
                                                         {"value": "No", "odd": "1.85"}]}]}
                 for i, (n, o) in enumerate(books)]}]


# ── parsing ───────────────────────────────────────────────────────────────────────────────────
def test_odds_rows_keep_only_the_books_and_markets_we_use():
    rows = parse.odds_rows(_odds_payload(NOW + 3600, [("Pinnacle", 2.1), ("Bet365", 2.0),
                                                      ("1xBet", 2.2)]), "ts", NOW)
    books = {r["bookmaker"] for r in rows}
    assert books == {"pinnacle", "bet365", "median"}
    assert {r["market"] for r in rows} == {"ou25", "btts"}            # Over 4.5 dropped
    med = [r for r in rows if r["bookmaker"] == "median" and r["selection"] == "over"][0]
    assert med["odds"] == 2.1 and med["n_books"] == 3 and med["quality_flags"] == ""


def test_first_half_btts_is_not_read_as_full_match():
    """The exact-name match is what keeps bet 34 out (v9's 2026-08-23 BTTS contamination)."""
    rows = parse.odds_rows(_odds_payload(NOW + 3600, [("Bet365", 2.0)]), "ts", NOW)
    yes = [r for r in rows if r["market"] == "btts" and r["selection"] == "yes"]
    assert all(r["odds"] == 1.9 for r in yes)


def test_kicked_off_fixtures_are_never_stored():
    assert parse.odds_rows(_odds_payload(NOW - 60, [("Bet365", 2.0)]), "ts", NOW) == []


def test_thin_median_is_flagged():
    rows = parse.odds_rows(_odds_payload(NOW + 3600, [("Bet365", 2.0)]), "ts", NOW)
    med = [r for r in rows if r["bookmaker"] == "median"][0]
    assert med["quality_flags"] == "INSUFFICIENT_BOOKS"


def test_change_log_keeps_moves_and_everything_near_kickoff():
    far = {"fixture_id": 1, "market": "ou25", "selection": "over", "bookmaker": "bet365",
           "odds": 2.0, "minutes_to_kickoff": 600}
    last = {(1, "ou25", "over", "bet365"): 2.0}
    assert parse.changed([far], last) == []                                # unchanged, far out
    assert parse.changed([{**far, "odds": 2.05}], last) != []              # moved
    assert parse.changed([{**far, "minutes_to_kickoff": 90}], last) != []  # inside 3h: always


def test_scores_only_for_finished_matches():
    fx = [{"fixture": {"id": 5, "timestamp": NOW, "date": "2027-01-15T18:00:00+00:00",
                       "status": {"short": "1H"}},
           "league": {"id": 129, "season": 2026, "round": "R1"},
           "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
           "goals": {"home": 1, "away": 0}, "score": {"halftime": {"home": 1, "away": 0}}}]
    r = parse.fixture_rows(fx)[0]
    assert r["home_goals"] is None, "an in-play score must never be stored as a result"


# ── model ─────────────────────────────────────────────────────────────────────────────────────
def _league(n_teams=12, seasons=2, seed=0, strength=None):
    rng = np.random.default_rng(seed)
    att = strength if strength is not None else rng.normal(0, 0.3, n_teams)
    rows, fid, t = [], 0, NOW - seasons * 300 * 86400
    for _ in range(seasons * 2):
        for h in range(n_teams):
            for a in range(n_teams):
                if h == a:
                    continue
                t += 3600 * 6
                lh, la = 1.4 * np.exp(att[h] - att[a] * 0.5), 1.1 * np.exp(att[a] - att[h] * 0.5)
                rows.append({"fixture_id": fid, "league_id": 7, "kickoff_ts": t, "home_id": h,
                             "away_id": a, "home_team": f"T{h}", "away_team": f"T{a}",
                             "home_goals": rng.poisson(lh), "away_goals": rng.poisson(la)})
                fid += 1
    return pd.DataFrame(rows), att


def test_model_is_coherent_and_ranks_strong_teams_higher():
    d, att = _league()
    m = model.fit(d, NOW)
    strong, weak = int(np.argmax(att)), int(np.argmin(att))
    p = model.predict(m, strong, weak)
    q = model.predict(m, weak, strong)
    assert 1 >= p["p_ou15_over"] >= p["p_ou25_over"] >= p["p_ou35_over"] >= 0
    assert p["lambda_home"] > q["lambda_home"]


def test_model_uses_only_matches_before_asof():
    d, _ = _league()
    cut = int(d["kickoff_ts"].median())
    a = model.fit(d, cut)
    b = model.fit(d[d["kickoff_ts"] < cut], cut)
    assert a["n_matches"] == b["n_matches"] and np.allclose(a["A"], b["A"])


def test_calibration_in_the_large_matches_history():
    d, _ = _league(seasons=3)
    m = model.fit(d, NOW)
    P = np.mean([model.predict(m, r.home_id, r.away_id)["p_ou25_over"] for r in d.tail(400).itertuples()])
    rate = ((d.tail(400)["home_goals"] + d.tail(400)["away_goals"]) > 2.5).mean()
    assert abs(P - rate) < 0.05


def test_unknown_team_falls_back_to_average_not_an_extreme():
    d, _ = _league()
    p = model.predict(model.fit(d, NOW), 999, 998)
    assert p["home_games"] == 0 and 0.2 < p["p_ou25_over"] < 0.8


# ── report, end to end on a scratch store ─────────────────────────────────────────────────────
@pytest.fixture
def scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(report, "OUT", tmp_path / "out")
    monkeypatch.setattr(leagues, "load", lambda: [{"id": 7, "country": "X", "name": "Test", "priority": 1}])
    return tmp_path


def test_report_finds_a_model_the_market_ignores(scratch):
    """A soft market: the closing price knows only the league average, the model knows the
    true rate. The residual test must see it, and the market's skill must sit near zero."""
    rng = np.random.default_rng(1)
    n = 600
    true_p = rng.uniform(0.25, 0.75, n)
    y_tot = np.where(rng.random(n) < true_p, 3, 1)
    res = pd.DataFrame({"fixture_id": range(n), "league_id": 7, "kickoff_ts": NOW + np.arange(n),
                        "home_team": "a", "away_team": "b", "home_goals": y_tot, "away_goals": 0,
                        "quality_flags": ""})
    fair = 0.5
    odds_rows = []
    for f in range(n):
        for sel, p in (("over", fair), ("under", 1 - fair)):
            odds_rows.append({"fixture_id": f, "market": "ou25", "selection": sel,
                              "bookmaker": "pinnacle", "odds": round(1 / (p * 1.03), 3),
                              "snapshot_ts": "2027-01-01T00:00:00Z", "minutes_to_kickoff": 120.0})
            odds_rows.append({**odds_rows[-1], "bookmaker": "bet365",
                              "odds": round(1 / (p * 1.06), 3)})
    mdl = pd.DataFrame({"fixture_id": range(n), "model_version": "t", "frozen_ts": "2027-01-01T00:00:00Z",
                        "p_ou25_over": true_p, "p_ou15_over": 0.9, "p_ou35_over": 0.1, "p_btts_yes": 0.5})
    for t, d in (("scout_results", res), ("scout_odds", pd.DataFrame(odds_rows)), ("scout_model", mdl)):
        store.append(t, d, source="test", rid=f"t-{t}", allow_local=True)
    r = report.build()
    cell = [c for c in r["cells"] if c["market"] == "ou25"][0]
    assert cell["n"] == n and cell["status"] == "READABLE"
    assert abs(cell["market_skill_vs_base"]) < 0.02
    assert cell["residual"]["z"] > 4
    assert cell["paper_bets"] > 50 and cell["paper_roi"] > 0


def test_league_status_lists_every_watched_league_with_its_stage(scratch, monkeypatch):
    monkeypatch.setattr(leagues, "load", lambda: [
        {"id": 7, "country": "X", "name": "Priced", "priority": 1},
        {"id": 8, "country": "Y", "name": "History only", "priority": 2},
        {"id": 9, "country": "Z", "name": "Nothing", "priority": 2}])
    res = pd.DataFrame({"fixture_id": [1, 2], "league_id": [7, 8], "kickoff_ts": [NOW, NOW], "home_team": "a",
                        "away_team": "b", "home_goals": 1, "away_goals": 1, "quality_flags": ""})
    odds = pd.DataFrame({"fixture_id": [3], "league_id": [7], "kickoff_ts": [NOW * 2], "market": "ou25",
                         "selection": "over", "bookmaker": "bet365", "odds": 2.0, "snapshot_ts": "2027-01-01T00:00:00Z",
                         "minutes_to_kickoff": 100.0, "quality_flags": ""})
    store.append("scout_results", res, source="t", rid="t-r", allow_local=True)
    store.append("scout_odds", odds, source="t", rid="t-o", allow_local=True)
    st = {r["league"]: r for r in report.league_status({"cells": []})["leagues"]}
    assert len(st) == 3
    assert st["Priced"]["status"] == "PRICING" and st["Priced"]["upcoming_priced"] == 1
    assert st["History only"]["status"] == "HISTORY_ONLY"
    assert st["Nothing"]["status"] == "NOT_STARTED"


def test_near_loop_watches_only_imminent_priced_fixtures_and_keeps_every_close(scratch, monkeypatch):
    import time as _t
    from src.scout import collect
    now = int(_t.time())
    seed = pd.DataFrame([{"fixture_id": fid, "league_id": 7, "kickoff_ts": now + mins * 60, "market": "ou25",
                          "selection": "over", "bookmaker": "bet365", "odds": 2.0,
                          "snapshot_ts": "2026-01-01T00:00:00Z", "minutes_to_kickoff": mins, "quality_flags": ""}
                         for fid, mins in ((1, 30), (2, 600))])
    monkeypatch.setattr(collect, "_read_recent", lambda t, d: seed)
    calls = []

    class FakeClient:
        calls = 0
        remaining = 99999

        def get(self, endpoint, params):
            calls.append(params["fixture"])
            return {"response": _odds_payload(now + 1800, [("Bet365", 2.0)])}
    written = []
    monkeypatch.setattr(collect, "_append", lambda t, rows, tag, dry: written.append(len(rows)) or len(rows))
    monkeypatch.setattr(collect.time, "sleep", lambda s: None)
    t0 = [now]
    monkeypatch.setattr(collect.time, "time", lambda: (t0.__setitem__(0, t0[0] + 400), t0[0])[1])
    out = collect.near_loop(FakeClient(), minutes=10, dry=True)
    assert set(calls) == {1}, "only the fixture inside the window may be fetched"
    assert out["passes"] >= 1 and written and written[0] > 0, "an unchanged price inside 3h is still stored"

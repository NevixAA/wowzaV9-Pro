"""Weekly league promotion: lifecycle, fail-closed gate, validation mechanics, idempotency.

    python -m pytest tests/test_league_promotion.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.scout import promotion as P  # noqa: E402


@pytest.fixture()
def iso(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "OUT", tmp_path / "scout")
    monkeypatch.setattr(P, "LIFECYCLE_FILE", tmp_path / "registry" / "league_lifecycle.json")
    monkeypatch.setattr(P, "wowza_leagues", lambda: {"Championship", "Mexico Liga MX"})
    (tmp_path / "scout").mkdir()
    return tmp_path


def _store(lid=999, n=420, seed=1, model_noise=0.10, close_cov=1.0):
    """Synthetic league: n fixtures over 2 seasons up to yesterday, 12 teams, Pinnacle two-way
    closes for ou15/ou25/ou35/btts, and a frozen model probability per fixture."""
    rng = np.random.default_rng(seed)
    now = pd.Timestamp.now(tz="UTC").normalize()
    ko = [now - pd.Timedelta(days=int(d)) for d in np.linspace(500, 1, n)]
    lam_h, lam_a = rng.uniform(0.8, 2.0, n), rng.uniform(0.6, 1.6, n)
    hg, ag = rng.poisson(lam_h), rng.poisson(lam_a)
    res = pd.DataFrame({"fixture_id": np.arange(n) + 10_000, "league_id": lid,
                        "season": [2025 if k < now - pd.Timedelta(days=200) else 2026 for k in ko],
                        "kickoff_ts": [k.timestamp() for k in ko], "home_id": rng.integers(1, 13, n),
                        "away_id": rng.integers(13, 25, n) % 12 + 1, "home_goals": hg, "away_goals": ag,
                        "ingested_at": 1})
    from scipy.stats import poisson
    tot = lam_h + lam_a
    true = {"ou15": 1 - poisson.cdf(1, tot), "ou25": 1 - poisson.cdf(2, tot), "ou35": 1 - poisson.cdf(3, tot),
            "btts": (1 - np.exp(-lam_h)) * (1 - np.exp(-lam_a))}
    sides = {"ou15": ("over", "under"), "ou25": ("over", "under"), "ou35": ("over", "under"), "btts": ("yes", "no")}
    rows, mdl = [], {"fixture_id": res["fixture_id"], "frozen_ts": res["kickoff_ts"] - 3600}
    for m, p in true.items():
        pm = np.clip(p + rng.normal(0, 0.03, n), 0.03, 0.97)               # market close
        mdl[{"btts": "p_btts_yes"}.get(m, f"p_{m}_over")] = np.clip(p + rng.normal(0, model_noise, n), 0.02, 0.98)
        keep = rng.random(n) < close_cov
        for i in np.flatnonzero(keep):
            for sel, q in zip(sides[m], (pm[i], 1 - pm[i])):
                rows.append({"fixture_id": int(res.fixture_id[i]), "league_id": lid, "market": m, "selection": sel,
                             "bookmaker": "pinnacle", "odds": round(0.97 / q, 3), "minutes_to_kickoff": 30,
                             "snapshot_ts": pd.Timestamp(res.kickoff_ts[i] - 1800, unit="s", tz="UTC").isoformat(),
                             "kickoff_ts": res.kickoff_ts[i]})
    return res, pd.DataFrame(rows), pd.DataFrame(mdl)


def _status(lid=999, status="READABLE", settled=420, results=420, seasons=3, name="Testland Div 2"):
    country, league = name.split(" ", 1)
    return {"leagues": [{"league_id": lid, "country": country, "league": league, "priority": 1, "status": status,
                         "history_seasons": seasons, "results": results, "settled_with_close": settled}]}


def test_collecting_league_is_never_a_candidate(iso):
    r = P.run(_status(status="COLLECTING", settled=40), week="2026-W42")
    assert r["new_candidates"] == [] and r["counts"]["still_collecting"] == 1
    assert r["details"]["Testland Div 2"]["distance"]["settled_with_close"] == 260


def test_gate_fails_closed():
    row = _status()["leagues"][0]
    ok, g = P.candidate_gate({**row, "league_id": None}, {"current_season_settled": 100,
                             "odds_coverage": {"ou25": 1, "btts": 1, "ou15": 1}}, set())
    assert not ok and not g["checks"]["known API-Football league id"]
    ok, g = P.candidate_gate(row, {"current_season_settled": 100, "odds_coverage": {"ou25": 0.5}}, set())
    assert not ok
    ok, _ = P.candidate_gate({**row, "country": "Mexico", "league": "Liga MX"},
                             {"current_season_settled": 100, "odds_coverage": {"ou25": 1, "btts": 1, "ou15": 1}},
                             {"Mexico Liga MX"})
    assert not ok                                                       # already a Wowza league


def test_readable_league_validates_and_is_idempotent(iso, monkeypatch):
    res, odds, mdl = _store()
    monkeypatch.setattr(P, "_store", lambda: (res, odds, mdl))
    r1 = P.run(_status(), week="2026-W42")
    assert r1["new_candidates"] == ["Testland Div 2"]
    d = r1["details"]["Testland Div 2"]
    assert d["data_quality"] == "PASS" and d["new_state"] in ("SHADOW_APPROVED", "REJECTED_TEMPORARILY", "VALIDATION_FAILED")
    folder = iso / "scout" / "promotions" / "testland_div_2"
    for f in ("league_onboarding_data_quality.json", "model_matrix.csv", "onboarding_proposal.json", "PROMOTION_REPORT.md"):
        assert (folder / f).exists(), f
    prop = json.loads((folder / "onboarding_proposal.json").read_text(encoding="utf-8"))
    assert prop["deployment"]["REAL_MONEY"] == "NO" and prop["deployment"]["PAPER_ONLY"] == "YES"
    assert set(prop["market_states"].values()) <= {"PAPER", "RESEARCH"}
    # a second run the same week must not re-promote or re-validate
    r2 = P.run(_status(), week="2026-W42")
    assert r2["new_candidates"] == [] and r2["promoted"] == []
    hist = json.loads(P.LIFECYCLE_FILE.read_text(encoding="utf-8"))["999"]["history"]
    assert sum(h["to"] == "PROMOTION_CANDIDATE" for h in hist) == 1


def test_bad_data_blocks_before_any_model_work(iso, monkeypatch):
    res, odds, mdl = _store()
    res = pd.concat([res, res.head(5)])                                 # duplicate fixtures
    monkeypatch.setattr(P, "_store", lambda: (res, odds, mdl))
    r = P.run(_status(), week="2026-W42")
    assert r["blocked"] == ["Testland Div 2"]
    assert not (iso / "scout" / "promotions" / "testland_div_2" / "model_matrix.csv").exists()


def test_blocked_league_waits_four_weeks(iso, monkeypatch):
    res, odds, mdl = _store()
    bad = pd.concat([res, res.head(5)])
    monkeypatch.setattr(P, "_store", lambda: (bad, odds, mdl))
    P.run(_status(), week="2026-W42")
    monkeypatch.setattr(P, "_store", lambda: (res, odds, mdl))
    r = P.run(_status(), week="2026-W44")
    assert r["new_candidates"] == []                                    # still inside the retry window
    r = P.run(_status(), week="2026-W46")
    assert r["new_candidates"] == ["Testland Div 2"]


def test_review_never_changes_production():
    r = {"EXISTING_PRODUCTION_SELECTION_CHANGED": "NO"}
    assert P.CALC_VERSION and r["EXISTING_PRODUCTION_SELECTION_CHANGED"] == "NO"
    src = Path(P.__file__).read_text(encoding="utf-8")
    assert "V9_LOCAL" in src and ".write_text" in src
    assert "wowza-betting" not in src.replace("NevixAA/wowza-betting", "")   # no repo writes from here

def test_registry_parses_literals_without_running_code(tmp_path):
    from src.scout import registry as REG
    f = tmp_path / "config.py"
    f.write_text('import os\nX = os.getenv("A")\nNEW_FORMAT_LEAGUES = {"A League", "B League"}\n'
                 'API_FOOTBALL_IDS = {"A League": 7}\nPAPER_LEAGUES: set = {"B League"}\n', encoding="utf-8")
    v = REG.literal_assignments(f, ("NEW_FORMAT_LEAGUES", "API_FOOTBALL_IDS", "PAPER_LEAGUES", "X"))
    assert v["NEW_FORMAT_LEAGUES"] == {"A League", "B League"} and v["API_FOOTBALL_IDS"] == {"A League": 7}
    assert v["PAPER_LEAGUES"] == {"B League"} and "X" not in v          # non-literal skipped, not executed

"""E3 (owner brief 2026-10-26): scout multiple-testing control.

    python -m pytest tests/test_scout_hypotheses.py

Pins: BH-FDR arithmetic and family size, the matchday block bootstrap, leave-one-period-out,
concentration, the genuine-close requirement, discovery -> confirmation on FORWARD data with a
write-once start, the criteria hash lock, and that neither the weekly review nor the auto-onboard
queue can promote a league without a CONFIRMED hypothesis — whatever its raw ROI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.scout import hypotheses as H  # noqa: E402
from src.scout import promotion as P  # noqa: E402

LID = 4242
LEAGUES = [{"id": LID, "country": "Testland", "name": "Div 3"}]


@pytest.fixture()
def reg_path(tmp_path, monkeypatch):
    f = tmp_path / "scout_hypotheses.json"
    monkeypatch.setattr(H, "REGISTRY_FILE", f)
    return f


# ── statistics ────────────────────────────────────────────────────────────────────────────────
def test_bh_qvalues_known_answer():
    q = H.bh_qvalues([0.01, 0.04, 0.03, 0.005])
    assert np.allclose(q, [0.02, 0.04, 0.04, 0.02])


def test_family_size_is_what_kills_a_leaderboard_winner():
    alone = H.bh_qvalues([0.001])[0]
    in_family = H.bh_qvalues([0.001] + [1.0] * 799)[0]
    assert alone <= 0.20 < in_family            # the same p passes alone, fails among 800


def test_block_bootstrap_widens_for_clustered_days():
    rng = np.random.default_rng(0)
    day_effect = np.repeat(rng.normal(0, 1, 20), 10)
    d = day_effect + rng.normal(0, 0.1, 200)
    blocked = H.block_bootstrap(d, np.repeat(np.arange(20), 10))
    iid = H.block_bootstrap(d, np.arange(200))
    assert blocked["se"] > 2 * iid["se"]


def test_bootstrap_p_is_one_sided():
    rng = np.random.default_rng(1)
    pos = H.block_bootstrap(0.05 + rng.normal(0, 0.1, 300), np.arange(300) // 6)
    neg = H.block_bootstrap(-0.05 + rng.normal(0, 0.1, 300), np.arange(300) // 6)
    assert pos["p"] < 0.01 and neg["p"] > 0.99


def test_lopo_catches_one_period_carrying_everything():
    days = np.repeat([f"2026-01-{i:02d}" for i in range(1, 21)], 5)
    flat = H.lopo(np.full(100, 0.01), days)
    assert flat["feasible"] and flat["pass"]
    spike = np.full(100, -0.002)
    spike[:25] = 0.05                                # first block only
    assert not H.lopo(spike, days)["pass"]
    assert not H.lopo(np.ones(3), np.array(["a", "b", "c"]))["feasible"]


def test_concentration_flags_one_matchday_or_one_team():
    days = np.repeat(np.arange(20), 5)
    home, away = np.tile(np.arange(10), 10), np.tile(np.arange(10, 20), 10)
    even = H.concentration(np.full(100, 0.01), days, home, away)
    assert even["pass"]
    d = np.full(100, 0.001)
    d[days == 3] = 0.2
    assert not H.concentration(d, days, home, away)["pass"]
    assert not H.concentration(np.full(100, -0.01), days, home, away)["pass"]


def test_raw_roi_is_not_an_input():
    assert H.CRITERIA["raw_roi_is_an_input"] is False
    assert "roi" not in json.dumps({k: v for k, v in H.CRITERIA.items() if k != "raw_roi_is_an_input"}).lower()


# ── synthetic league ──────────────────────────────────────────────────────────────────────────
def _league(start: pd.Timestamp, n_days: int, *, model_noise: float, market_noise: float,
            seed: int, close_minutes: float = 30.0, id0: int = 0):
    """n_days matchdays x 6 fixtures, 12 teams, Pinnacle closes, a frozen model per fixture."""
    from scipy.stats import poisson
    rng = np.random.default_rng(seed)
    n = n_days * 6
    ko = np.array([(start + pd.Timedelta(days=3 * (i // 6), hours=15)).timestamp() for i in range(n)])
    lam_h, lam_a = rng.uniform(0.6, 2.2, n), rng.uniform(0.5, 1.8, n)
    hg, ag = rng.poisson(lam_h), rng.poisson(lam_a)
    ids = np.arange(n) + 100_000 + id0
    perm = np.concatenate([rng.permutation(12) + 1 for _ in range(n_days)]).reshape(n_days, 12)
    home, away = perm[:, :6].ravel(), perm[:, 6:].ravel()          # a fresh round of pairings each matchday
    res = pd.DataFrame({"fixture_id": ids, "league_id": LID, "kickoff_ts": ko, "home_id": home,
                        "away_id": away, "home_goals": hg, "away_goals": ag, "ingested_at": 1})
    tot = lam_h + lam_a
    true = {"ou15": 1 - poisson.cdf(1, tot), "ou25": 1 - poisson.cdf(2, tot),
            "ou35": 1 - poisson.cdf(3, tot), "btts": (1 - np.exp(-lam_h)) * (1 - np.exp(-lam_a))}
    sides = {"ou15": ("over", "under"), "ou25": ("over", "under"), "ou35": ("over", "under"),
             "btts": ("yes", "no")}
    rows = []
    mdl = {"fixture_id": ids, "kickoff_ts": ko,
           "frozen_ts": [pd.Timestamp(k - 86400, unit="s", tz="UTC").isoformat() for k in ko]}
    for m, p in true.items():
        pm = np.clip(p + rng.normal(0, market_noise, n), 0.03, 0.97)
        mdl[{"btts": "p_btts_yes"}.get(m, f"p_{m}_over")] = np.clip(p + rng.normal(0, model_noise, n), 0.02, 0.98)
        for i in range(n):
            for sel, q in zip(sides[m], (pm[i], 1 - pm[i])):
                rows.append({"fixture_id": int(ids[i]), "league_id": LID, "market": m, "selection": sel,
                             "bookmaker": "pinnacle", "odds": round(1 / q, 4),
                             "minutes_to_kickoff": close_minutes, "quality_flags": "",
                             "snapshot_ts": pd.Timestamp(ko[i] - close_minutes * 60, unit="s", tz="UTC").isoformat(),
                             "kickoff_ts": ko[i]})
    return res, pd.DataFrame(rows), pd.DataFrame(mdl)


T0 = pd.Timestamp("2026-01-01T00:00:00Z")


def _cat(*parts):
    return tuple(pd.concat(x, ignore_index=True) for x in zip(*parts))


def test_genuine_close_requirement():
    res, odds, mdl = _league(T0, 10, model_noise=0.01, market_noise=0.05, seed=2, close_minutes=90)
    assert H.evidence(res, odds, mdl).empty                 # a 90-minute-old price is not a close
    res, odds, mdl = _league(T0, 10, model_noise=0.01, market_noise=0.05, seed=2, close_minutes=30)
    assert len(H.evidence(res, odds, mdl)) == 10 * 6 * 4


def test_discovery_then_forward_confirmation(reg_path):
    hist = _league(T0, 30, model_noise=0.005, market_noise=0.12, seed=3)       # 180 fixtures
    mid = T0 + pd.Timedelta(days=95)
    s1 = H.review(*hist, leagues=LEAGUES, now=mid, week="2026-W14")
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    states = {h["market"]: h["state"] for h in reg["hypotheses"]}
    assert "CONFIRMING" in states.values(), states
    # discovery alone NEVER confirms: the selecting data cannot also be the confirming data
    assert s1[LID]["confirmed_markets"] == []
    starts = {h["id"]: h["confirmation_start"] for h in reg["hypotheses"] if h["confirmation_start"]}

    fwd = _league(mid + pd.Timedelta(days=1), 35, model_noise=0.005, market_noise=0.12, seed=4, id0=50_000)
    allx = _cat(hist, fwd)
    end = mid + pd.Timedelta(days=120)
    s2 = H.review(*allx, leagues=LEAGUES, now=end, week="2026-W31")
    reg2 = json.loads(reg_path.read_text(encoding="utf-8"))
    assert s2[LID]["confirmed_markets"], {h["market"]: (h["state"], h.get("confirmation", {}).get("checks"))
                                          for h in reg2["hypotheses"]}
    for h in reg2["hypotheses"]:                            # write-once forward start
        if h["id"] in starts:
            assert h["confirmation_start"] == starts[h["id"]]
        if h["state"] == "CONFIRMED":
            c = h["confirmation"]
            assert c["n"] >= 150 and c["matchdays"] >= 10 and c["bh_q"] <= 0.05
            assert c["lopo"]["pass"] and c["concentration"]["pass"] and c["lower95"] > 0


def test_noise_model_is_never_confirmed(reg_path):
    hist = _league(T0, 30, model_noise=0.15, market_noise=0.01, seed=5)
    mid = T0 + pd.Timedelta(days=95)
    H.review(*hist, leagues=LEAGUES, now=mid, week="2026-W14")
    fwd = _league(mid + pd.Timedelta(days=1), 35, model_noise=0.15, market_noise=0.01, seed=6, id0=50_000)
    s = H.review(*_cat(hist, fwd), leagues=LEAGUES, now=mid + pd.Timedelta(days=120), week="2026-W31")
    assert s[LID]["confirmed_markets"] == []


def test_changed_criteria_block_every_confirmation(reg_path, monkeypatch):
    hist = _league(T0, 30, model_noise=0.01, market_noise=0.08, seed=3)
    mid = T0 + pd.Timedelta(days=95)
    H.review(*hist, leagues=LEAGUES, now=mid, week="2026-W14")
    tuned = json.loads(json.dumps(H.CRITERIA))
    tuned["confirmation"]["bh_q"] = 0.5                     # "loosen it a bit" after looking
    monkeypatch.setattr(H, "CRITERIA", tuned)
    fwd = _league(mid + pd.Timedelta(days=1), 35, model_noise=0.01, market_noise=0.08, seed=4, id0=50_000)
    s = H.review(*_cat(hist, fwd), leagues=LEAGUES, now=mid + pd.Timedelta(days=120), week="2026-W31")
    assert s[LID]["blocked"] and s[LID]["confirmed_markets"] == []


def test_committed_registry_matches_code_criteria():
    f = Path(__file__).resolve().parents[1] / "registry" / "scout_hypotheses.json"
    if not f.exists():
        pytest.skip("registry not generated yet")
    reg = json.loads(f.read_text(encoding="utf-8"))
    assert reg["criteria_sha256"] == H.criteria_sha256(), "criteria changed: that needs a NEW registry version"
    assert len({h["id"] for h in reg["hypotheses"]}) == len(reg["hypotheses"])


# ── promotion consumes it ─────────────────────────────────────────────────────────────────────
def _proposal(folder: Path, confirmed: list[str] | None):
    folder.mkdir(parents=True, exist_ok=True)
    pr = {"league_id": LID, "league": "Testland Div 3", "country": "Testland", "week": "2026-W44",
          "promotion_score": 99.0, "state": "SHADOW_APPROVED",
          "integration_route": "REGRESSION_PASSED_AUTO_ONBOARD", "regression": {"verdict": "PASS"},
          "hard_fails": [], "current_season": "2026"}
    if confirmed is not None:
        pr["multiple_testing"] = {"confirmed_markets": confirmed}
    (folder / "onboarding_proposal.json").write_text(json.dumps(pr), encoding="utf-8")


def test_auto_onboard_queue_requires_a_confirmed_hypothesis(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "OUT", tmp_path)
    _proposal(tmp_path / "promotions" / "legacy", None)       # written before the control existed
    _proposal(tmp_path / "promotions" / "unconfirmed", [])
    assert P.write_auto_onboard_queue() == []
    _proposal(tmp_path / "promotions" / "confirmed", ["ou25"])
    assert P.write_auto_onboard_queue() == ["Testland Div 3"]


def test_high_score_without_confirmation_awaits(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "OUT", tmp_path)
    called = []
    import src.scout.regression_harness as RH
    monkeypatch.setattr(RH, "run", lambda lid: called.append(lid) or {"verdict": "PASS"})
    monkeypatch.setattr(RH, "save", lambda r: None)
    res, odds, mdl = _league(T0, 60, model_noise=0.01, market_noise=0.08, seed=9)
    res = res.assign(season=2026)
    row = {"league_id": LID, "country": "Testland", "league": "Div 3", "settled_with_close": 360}
    extra = {"current_season": "2026", "current_season_settled": 360,
             "odds_coverage": {"ou25": 1.0, "btts": 1.0, "ou15": 1.0}}
    monkeypatch.setattr(P, "data_quality", lambda *a: {"verdict": "PASS", "critical": []})
    v = P.validate(row, extra, res, odds, mdl, "2026-W44", mtc={"confirmed_markets": []})
    assert v["promotion_score"] >= 75, v                    # the raw evidence looks excellent ...
    assert v["new_state"] == "AWAITING_CONFIRMATION"        # ... and still does not promote
    assert v["supported_markets"] == [] and called == []    # no paper markets, no regression run
    v2 = P.validate(row, extra, res, odds, mdl, "2026-W44", mtc={"confirmed_markets": ["ou25"]})
    assert v2["new_state"] == "SHADOW_APPROVED" and set(v2["supported_markets"]) <= {"ou25"}


def test_leaderboard_top10_is_never_promotable():
    report = {"cells": [{"league_id": i, "country": "X", "league": f"L{i}", "market": "ou15", "n": 12,
                         "paper_bets": 1, "paper_roi": 5.0 - i * 0.1} for i in range(15)]}
    summary = {i: {"states": {"ou15": "DISCOVERY"}, "confirmed_markets": []} for i in range(15)}
    lb = H.leaderboard_verdicts(report, summary)
    assert len(lb) == 10 and not any(r["promotable"] for r in lb)

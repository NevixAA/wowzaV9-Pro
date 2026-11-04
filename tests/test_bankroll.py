"""Bankroll system: v9's reader rules, the allocator's asymmetry and bounds, and no look-ahead.

    python -m pytest tests/test_bankroll.py      (needs V9_LOCAL -> a wowza-betting checkout)
"""
from __future__ import annotations

import copy
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import pro_config as cfg  # noqa: E402

pytestmark = pytest.mark.skipif(not (cfg.V9_LOCAL / "src" / "bankroll_policy.py").exists(),
                                reason="needs a v9 checkout with src/bankroll_policy.py")


@pytest.fixture(scope="module")
def R():
    from src.bankroll.data import v9_reader
    return v9_reader()


@pytest.fixture(scope="module")
def pol(R):
    return R.load_policy(cfg.V9_LOCAL / "config" / "bankroll_policy.json")


def sel(**kw):
    base = {"fixture": "F1", "league": "Liga", "model_type": "new_format", "market": "BTTS", "side": "YES",
            "signal_tier": "SNIPER", "odds": 2.0}
    return {**base, **kw}


def _nf_ou25_over() -> str:
    """The NF O/U 2.5 OVER track key under the checked-out v9 (per side since 2026-10-26)."""
    from src.bankroll.data import track_key_fn
    return track_key_fn()("new_format", "OU25", "OVER")


def test_balanced_base_and_tier(R, pol):
    r = R.size_day(pd.DataFrame([sel()]), pol, 100, 100)
    assert r.loc[0, "final_fraction"] == pytest.approx(0.0125 * 1.10)
    r = R.size_day(pd.DataFrame([sel(signal_tier="MARKSMAN")]), pol, 100, 100)
    assert r.loc[0, "final_fraction"] == pytest.approx(0.0125 * 0.90)


def test_blocked_paper_and_odds(R, pol):
    rows = pd.DataFrame([sel(fixture="a", market="OVER35"), sel(fixture="b", model_type="standard", market="OU25", side="UNDER"),
                         sel(fixture="c", league="USA MLS"), sel(fixture="d", odds=2.61),
                         sel(fixture="e", market="OVER15", odds=1.40), sel(fixture="f", odds=3.2)])
    r = R.size_day(rows, pol, 100, 100)
    assert (r["final_fraction"] == 0).all()
    assert list(r["reason"]) == ["NO_REAL_STAKE_BLOCKED", "NO_REAL_STAKE_PAPER", "PAPER_LEAGUE",
                                 "ODDS_ABOVE_TRACK_CAP", "ODDS_BELOW_TRACK_FLOOR", "ODDS_BLOCKED"]


def test_one_position_per_fixture_uses_evidence_not_edge(R, pol):
    """The rule itself, when a policy switches it on. v9's committed policy has it OFF since
    2026-11-04 (owner: several bets on one match are fine unless they point in opposite goal
    directions), so the rule is exercised on a copy with the flag set back to true."""
    one = copy.deepcopy(pol)
    one["portfolio"]["one_position_per_fixture"] = True
    rows = pd.DataFrame([sel(market="OU25", side="OVER", odds=2.4), sel(market="BTTS", odds=1.9)])
    r = R.size_day(rows, one, 100, 100)
    kept = r[r["final_fraction"] > 0]
    assert len(kept) == 1 and kept.iloc[0]["market"] == "BTTS"       # higher evidence_score
    assert r[r["market"] == "OU25"].iloc[0]["reason"] == "ONE_POSITION_PER_FIXTURE"


def test_same_direction_positions_share_a_fixture_opposites_do_not(R, pol):
    """v9 policy 2026-11-04: one_position_per_fixture false; BTTS YES counts as OVER and BTTS NO as
    UNDER (bankroll_policy.goal_direction). Over 2.5 + BTTS Yes are both staked; Over 2.5 + BTTS No
    point in opposite directions, so the O/U 2.5 position stands and the BTTS No stake is zeroed."""
    assert pol["portfolio"]["one_position_per_fixture"] is False
    rows = pd.DataFrame([sel(market="OU25", side="OVER", odds=2.4), sel(market="BTTS", odds=1.9)])
    r = R.size_day(rows, pol, 100, 100)
    assert (r["final_fraction"] > 0).all() and list(r["reason"]) == ["OK", "OK"]
    assert r["final_fraction"].sum() <= pol["portfolio"]["fixture_cap"] + 1e-12
    rows = pd.DataFrame([sel(market="OU25", side="OVER", odds=2.4), sel(market="BTTS", side="NO", odds=1.9)])
    r = R.size_day(rows, pol, 100, 100)
    assert r.loc[0, "final_fraction"] > 0 and r.loc[0, "reason"] == "OK"
    assert r.loc[1, "final_fraction"] == 0 and r.loc[1, "reason"] == "OPPOSITE_DIRECTION_ON_FIXTURE"


def test_daily_cap_scales_everything_proportionally(R, pol):
    rows = pd.DataFrame([sel(fixture=f"F{i}", league=f"L{i}") for i in range(10)])   # 10 x 1.375%
    r = R.size_day(rows, pol, 100, 100)
    assert r["final_fraction"].sum() == pytest.approx(0.06)
    assert r["daily_scale"].iloc[0] == pytest.approx(0.06 / (10 * 0.01375))


def test_league_cap(R, pol):
    rows = pd.DataFrame([sel(fixture=f"F{i}") for i in range(4)])                    # same league
    r = R.size_day(rows, pol, 100, 100)
    assert r["final_fraction"].sum() == pytest.approx(0.03)


def test_drawdown_throttle_and_stop(R, pol):
    one = pd.DataFrame([sel()])
    assert R.size_day(one, pol, 91, 100).loc[0, "final_fraction"] == pytest.approx(0.01375 * 0.75, abs=1e-6)
    assert R.size_day(one, pol, 87, 100).loc[0, "final_fraction"] == pytest.approx(0.01375 * 0.50, abs=1e-6)
    r = R.size_day(one, pol, 80, 100)
    assert r.loc[0, "final_fraction"] == 0 and "PAPER_REVIEW" in r.loc[0, "reason"]


def test_reader_enforces_hard_bounds_whatever_the_file_says(R, pol):
    p = copy.deepcopy(pol)
    p["tracks"]["new_format|BTTS"].update(base_fraction=0.05, max_odds=9.0)
    p["portfolio"].update(daily_cap=0.5, single_bet_cap=0.5, fixture_cap=0.5)
    r = R.size_day(pd.DataFrame([sel(odds=2.9)]), p, 100, 100)
    assert r.loc[0, "reason"] == "ODDS_ABOVE_TRACK_CAP"                               # 2.75 hard
    r = R.size_day(pd.DataFrame([sel()]), p, 100, 100)
    assert r.loc[0, "final_fraction"] <= 0.02 + 1e-12


def _bets(n_days=90, roi_bias=0.0, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_days):
        d = pd.Timestamp("2026-08-10") + pd.Timedelta(days=i)
        for j in range(3):
            win = rng.random() < 0.52 + roi_bias
            rows.append({"date": d, "fixture": f"{d:%F}|{j}", "league": ["A", "B", "C"][j],
                         "model_type": "new_format", "market": "OU25", "side": "OVER",
                         "signal_tier": "SNIPER", "odds": 2.0, "result": "WIN" if win else "LOSS",
                         "unit": 1.0 if win else -1.0, "clv": 0.01, "track": _nf_ou25_over(),
                         "month": d.strftime("%Y-%m")})
    return pd.DataFrame(rows)


def test_step_up_at_most_one_band(pol):
    from src.bankroll import allocator as A
    b = _bets(120, roi_bias=0.15)
    p, dec, _ = A.propose(pol, b, "2026-12-15")
    d = {x["track"]: x for x in dec}[_nf_ou25_over()]
    assert d["proposed_fraction"] - d["previous_fraction"] <= 0.0025 + 1e-12
    assert A.validate(p) == []


def test_fast_reduction(pol):
    from src.bankroll import allocator as A
    b = _bets(90, roi_bias=-0.25)
    p, dec, _ = A.propose(pol, b, "2026-11-10")
    d = {x["track"]: x for x in dec}[_nf_ou25_over()]
    assert d["decision"] in ("REDUCE", "STOP") and d["proposed_fraction"] < d["previous_fraction"]


def test_no_look_ahead(pol):
    """Rewriting every result on/after the review date cannot change the proposal."""
    from src.bankroll import allocator as A
    b = _bets(90)
    as_of = pd.Timestamp("2026-10-01")
    b2 = b.copy()
    late = b2["date"] >= as_of
    b2.loc[late, ["unit", "result"]] = [-1.0, "LOSS"]
    p1, d1, _ = A.propose(pol, b, as_of)
    p2, d2, _ = A.propose(pol, b2, as_of)
    p1.pop("generated_at"); p2.pop("generated_at")
    assert p1 == p2


def test_validate_catches_forbidden(pol):
    from src.bankroll import allocator as A
    p = copy.deepcopy(pol)
    p["tracks"]["player_props"]["base_fraction"] = 0.005
    p["portfolio"]["daily_cap"] = 0.10
    p["paper_leagues"] = []
    v = A.validate(p)
    assert any("player props" in x for x in v) and any("daily cap" in x for x in v) and any("MLS" in x for x in v)


# ── Data Truth 2026-11-01: missing evidence is missing, never a stand-in number ─────────────────

def test_shrink_without_evidence_is_none_not_the_prior():
    from src.bankroll.evidence import shrink
    assert shrink(None, None) is None and shrink(0.05, None) is None
    assert shrink(0.05, 0.1) is not None


def test_missing_30d_roi_fails_the_increase_gate(pol):
    """No bets in the last 30 days: 'last 30d not below -5%' used to read the gap as 0% and pass."""
    from src.bankroll import allocator as A
    from src.bankroll.evidence import track_evidence
    b = _bets(120, roi_bias=0.15)
    ev = track_evidence(b, "2026-12-15")[_nf_ou25_over()]
    ev["horizons"]["LAST_30D"] = {"n": 0, "roi": None, "units": 0.0}
    _, rec = A.decide_track(_nf_ou25_over(), pol["tracks"][_nf_ou25_over()], ev, "2026-12-08", False)
    assert rec["decision"] != "INCREASE_ONE_STEP"
    assert any("last 30d" in r for r in rec["reasons"])


def test_missing_recent_clv_sends_a_heavy_loss_to_review_not_keep(pol):
    from src.bankroll import allocator as A
    b = _bets(90, roi_bias=-0.25)
    b["clv"] = np.nan                                    # no CLV recorded at all
    p, dec, _ = A.propose(pol, b, "2026-11-10")
    d = {x["track"]: x for x in dec}[_nf_ou25_over()]
    assert d["decision"] in ("REDUCE", "STOP", "REVIEW")
    if d["decision"] == "REVIEW":
        assert any("input missing" in r for r in d["reasons"])


def test_convergence_multiplier_is_carried_never_invented(pol):
    from src.bankroll import allocator as A
    prev = copy.deepcopy(pol)
    prev.pop("convergence", None)
    p, _, _ = A.propose(prev, _bets(30), "2026-09-15")
    assert p["convergence"]["multiplier"] is None
    assert "convergence multiplier missing" in A.validate(p)


def test_paper_leagues_come_from_the_registry():
    from src.bankroll.data import _paper_leagues
    from src.data import v9_config
    assert _paper_leagues() == set(v9_config.paper_leagues()) and _paper_leagues()

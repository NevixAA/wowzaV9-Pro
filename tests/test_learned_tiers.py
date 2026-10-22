"""Learned per-league tiers: walk-forward never sees the week it scores; tiers follow predicted EV; leagues differ."""
import numpy as np
import pandas as pd

from src.studies import learned_tiers as L


def _data(n_weeks=6, per_week=80, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for w in range(n_weeks):
        for i in range(per_week):
            lg = "Good League" if i % 2 else "Bad League"
            odds = rng.uniform(1.7, 2.6)
            p_fair = 1 / odds * 0.95
            p_win = p_fair + (0.08 if lg == "Good League" else -0.08)
            won = float(rng.random() < p_win)
            rows.append({"fx": f"{w}-{i}", "league": lg, "model_type": "standard", "market": "ou25", "side": "OVER",
                         "gen": pd.Timestamp("2026-08-17", tz="UTC") + pd.Timedelta(weeks=w),
                         "md": pd.Timestamp("2026-08-17") + pd.Timedelta(weeks=w), "p_model": p_fair + 0.05,
                         "p_fair": p_fair, "odds": odds, "raw_edge": 0.05, "prod_tier": "VALUABLE",
                         "won": won, "pnl": odds - 1 if won else -1.0, "source": "TEST"})
    d = pd.DataFrame(rows)
    d["week"] = d["md"].dt.to_period("W").dt.start_time
    return d


def test_walk_forward_scores_only_weeks_after_enough_history():
    d = _data()
    wf = L.walk_forward(d)
    first_week = d["week"].min()
    assert len(wf) and (wf["week"] > first_week).all()                   # week 1 is never scored by itself


def test_tiers_follow_predicted_ev_cutoffs():
    t = L.tier_of(np.array([0.10, 0.06, 0.04, 0.01, -0.02]))
    assert list(t) == ["SNIPER", "SNIPER", "MARKSMAN", "VALUABLE", "AVOID"]


def test_league_effect_gives_leagues_different_gates():
    d = _data(n_weeks=8)
    m, lg = L.fit(d)
    probe = d.groupby("league").head(1).copy()
    ev = dict(zip(probe["league"], L.predict_ev(m, lg, probe)))
    assert ev["Good League"] > ev["Bad League"]


def test_registration_is_frozen_with_a_prospective_only_swap_rule():
    import json
    reg = json.loads((L.cfg.BASE_DIR / "registry" / "learned_tiers" / "registration_v1.json").read_text(encoding="utf-8"))
    assert reg["prospective_start"] == "2026-10-21" and "never trigger a swap" in reg["swap_rule"]
    assert L.CUTS == {"SNIPER": 0.06, "MARKSMAN": 0.03, "VALUABLE": 0.0} and L.C == 0.5

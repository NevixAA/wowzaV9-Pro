"""Fantasy benchmark: walk-forward arms only ever learn from earlier gameweeks."""
import numpy as np
import pandas as pd

from src.studies import fantasy_benchmark as F


def _ledger(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for gw in (1, 2, 3):
        for i in range(150):
            ep = rng.uniform(0, 8)
            rows.append({"gw": gw, "player_name": f"p{i}", "fpl_ep_next": ep, "proj_fixture_adj": ep + 1,
                         "p_start": 1.0, "actual_points": ep + rng.normal()})
    return pd.DataFrame(rows)


def test_first_gameweek_has_no_walk_forward_prediction():
    d = F.arms(_ledger())
    assert d.loc[d["gw"] == 1, ["BLEND_WF", "RESIDUAL_WF"]].isna().all().all()


def test_future_gameweek_cannot_change_an_earlier_forecast():
    a = F.arms(_ledger())
    L = _ledger()
    L.loc[L["gw"] == 3, "actual_points"] = 100.0          # wildly different future
    b = F.arms(L)
    g2a = a.loc[a["gw"] == 2, "RESIDUAL_WF"].to_numpy()
    g2b = b.loc[b["gw"] == 2, "RESIDUAL_WF"].to_numpy()
    assert np.allclose(g2a, g2b)


def test_wowza_scored_like_v9_settle():
    L = _ledger()
    L["p_start"] = 0.5
    d = F.arms(L)
    assert np.allclose(d["WOWZA"], (L["fpl_ep_next"] + 1) * 0.5)

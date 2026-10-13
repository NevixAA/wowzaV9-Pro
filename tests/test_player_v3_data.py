"""Player V3 data layer: as-of features must never see the match they describe, or any later one.

    python -m pytest tests/test_player_v3_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.player_v3 import VERDICT_KEYS, VERDICT_VALUES  # noqa: E402
from src.player_v3 import data as D  # noqa: E402


def _synthetic(seed=0, n_fix=60):
    rng = np.random.default_rng(seed)
    rows = []
    for f in range(n_fix):
        date = pd.Timestamp("2025-01-01") + pd.Timedelta(days=3 * f)
        for team, opp in (("A", "B"), ("B", "A")):
            for p in range(5):
                pid = (1 if team == "A" else 2) * 100 + p
                rows.append({"fixture_id": 1000 + f, "player_id": pid, "date": date, "team": team,
                             "opponent": opp, "league": "L", "minutes": int(rng.integers(1, 91)),
                             "started": int(rng.random() < 0.7),
                             "shots_on_target": int(rng.poisson(0.6)),
                             "shots_total": int(rng.poisson(1.4)), "goals": int(rng.poisson(0.15))})
    return pd.DataFrame(rows).sort_values(["date", "fixture_id", "player_id"]).reset_index(drop=True)


def _features(h):
    a = D.asof_rolling(h, "player_id", ["shots_on_target", "minutes"], windows=(3, 5),
                       ewm_spans=(4,), expanding=True)
    tt = D.team_totals(h)
    tr = D.asof_rolling(tt, "team", ["team_sot", "opp_sot"], windows=(3,))
    return a, tr, tt


def test_future_outcomes_cannot_change_past_features():
    h = _synthetic()
    cut = pd.Timestamp("2025-04-01")
    a0, t0, tt0 = _features(h)
    h2 = h.copy()
    late = h2["date"] >= cut
    rng = np.random.default_rng(99)
    for c in ("shots_on_target", "minutes", "shots_total", "goals"):
        h2.loc[late, c] = rng.integers(0, 9, int(late.sum()))
    a1, t1, tt1 = _features(h2)
    early = h["date"] < cut
    pd.testing.assert_frame_equal(a0[early], a1[early])
    # the first match ON the cutoff also may not see itself: its features use only earlier rows
    on_cut = h["date"] == h.loc[late, "date"].min()
    pd.testing.assert_frame_equal(a0[on_cut], a1[on_cut])
    early_t = tt0["date"] <= cut
    pd.testing.assert_frame_equal(t0[early_t], t1[early_t])


def test_first_appearance_has_no_history():
    h = _synthetic()
    a, _, _ = _features(h)
    first = h.groupby("player_id").head(1).index
    assert a.loc[first].isna().all().all()


def test_team_totals_and_opponent_mirror():
    h = _synthetic()
    tt = D.team_totals(h)
    one = tt[tt["fixture_id"] == 1000].set_index("team")
    assert one.loc["A", "team_sot"] == h[(h.fixture_id == 1000) & (h.team == "A")].shots_on_target.sum()
    assert one.loc["A", "opp_sot"] == one.loc["B", "team_sot"]


def test_contract_vocabulary():
    assert "PRODUCTION_PLAYER_SELECTION_CHANGED" in VERDICT_KEYS and len(VERDICT_KEYS) == 16
    assert VERDICT_VALUES == ("YES", "NO", "UNCLEAR", "INSUFFICIENT_DATA")

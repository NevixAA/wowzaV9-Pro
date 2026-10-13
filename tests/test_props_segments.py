"""Props segments: the frozen rules and the verdict logic, without v9 data.

    python -m pytest tests/test_props_segments.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.studies import props_segments as P  # noqa: E402


def test_registration_is_frozen():
    """Changing any of these after 2026-10-13 is a NEW registration, not an edit."""
    assert P.REGISTERED_ON == "2026-10-13" and P.WINDOW_FROM == "2026-10-14"
    assert P.SEGMENTS["ATT_DEF"] == {"position": "D", "min_minutes_pg": 45, "shots_pg": 0.6,
                                     "key_passes_pg": 0.6}
    assert P.SEGMENTS["ATT_MID"] == {"position": "M", "min_minutes_pg": 45, "shots_pg": 1.0,
                                     "key_passes_pg": 1.2}
    assert P.N_MIN == 150 and abs(P.ALPHA_ONE_SIDED - 0.05 / 6) < 1e-12


def _cell(n, win_rate, odds, clv, days=40):
    rng = np.random.default_rng(0)
    won = rng.random(n) < win_rate
    return pd.DataFrame({"result": np.where(won, "WIN", "LOSS"), "market_odds": odds,
                         "model_prob": 0.5, "pnl": np.where(won, odds - 1, -1.0),
                         "match_date": [f"2026-11-{1 + i % days:02d}" if i % days < 30 else
                                        f"2026-12-{1 + i % days - 30:02d}" for i in range(n)],
                         "clv": clv})


def test_small_sample_is_collecting_never_edge():
    c = P.cell(_cell(40, 0.9, 2.0, 0.05))
    assert c["verdict"] == "COLLECTING (40/150)"


def test_edge_needs_profit_and_clv():
    assert P.cell(_cell(400, 0.75, 2.0, 0.05))["verdict"] == "EDGE"
    # profitable but never beat the close -> not an edge
    assert P.cell(_cell(400, 0.75, 2.0, -0.02))["verdict"].startswith("COLLECTING")


def test_clear_loser_is_no_edge():
    assert P.cell(_cell(400, 0.25, 2.0, -0.03))["verdict"] == "NO EDGE"


def test_initial_surname_key():
    assert P._ini_sur("K. Viveros") == P._ini_sur("Kevin Viveros") == ("k", "viveros")
    assert P._ini_sur("Vitinho") is None

"""Player V3 expected-minutes panel: absences become 0-minute rows inside a club tenure.

    python -m pytest tests/test_player_v3_minutes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.player_v3 import minutes as M  # noqa: E402


def _h():
    rows = []
    for f in range(8):
        date = pd.Timestamp("2025-01-01") + pd.Timedelta(days=7 * f)
        for team, opp, pids in (("A", "B", (9, 7)), ("B", "A", (8,))):
            for pid in pids:          # player 7 = a team-mate who always plays, as in a real squad
                rows.append({"fixture_id": 100 + f, "player_id": pid, "date": date,
                             "team": team, "opponent": opp, "league": "L", "is_home": team == "A",
                             "position": "M", "age": 25, "minutes": 90, "started": 1,
                             "shots_total": 1, "shots_on_target": 0, "goals": 0})
    h = pd.DataFrame(rows)
    # player 9 misses fixtures 102 and 104 but plays before and after -> two absences in tenure
    return h[~((h.player_id == 9) & h.fixture_id.isin([102, 104]))].reset_index(drop=True)


def test_absences_inside_tenure_are_zero_minute_rows():
    p = M.build_panel(_h())
    p9 = p[p.player_id == 9].set_index("fixture_id")
    assert len(p9) == 8
    assert p9.loc[102, "minutes"] == 0 and p9.loc[102, "appeared"] == 0 and p9.loc[102, "started"] == 0
    assert p9.loc[103, "minutes"] == 90 and p9.loc[103, "appeared"] == 1


def test_features_use_only_prior_fixtures():
    p = M.add_features(M.build_panel(_h()))
    r = p[(p.player_id == 9)].set_index("fixture_id")
    # fixture 103 follows the absence at 102: last-1 minutes must be 0, not its own 90
    assert r.loc[103, "minutes_l1"] == 0
    assert r.loc[103, "days_since_app"] == 14          # last appearance 101

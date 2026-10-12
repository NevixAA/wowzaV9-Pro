"""The prediction lab must find v9's data where CI puts it (V9_LOCAL), not only beside a laptop
checkout. The player track silently never ran in CI because it looked for ../v9 only.

    python -m pytest tests/test_prediction_lab_paths.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.prediction_lab import experiments as E  # noqa: E402
from src.prediction_lab import player_goals as PG  # noqa: E402


def test_player_history_is_found_through_v9_local(tmp_path, monkeypatch):
    v9 = tmp_path / "ci_checkout" / "_v9"
    part = v9 / "player_history.parquet"
    part.mkdir(parents=True)                       # a DIRECTORY of season parts, as in v9
    pd.DataFrame({"date": ["2026-09-01"], "player_id": [1], "goals": [1], "minutes": [90],
                  "started": [1], "league": ["L"], "home_team": ["A"], "away_team": ["B"]}).to_parquet(part / "season=2026.parquet", index=False)
    elsewhere = tmp_path / "somewhere_without_a_sibling_v9"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("V9_LOCAL", str(v9))
    d = PG.load_players()
    assert len(d) == 1 and int(d["player_id"].iloc[0]) == 1


def test_empty_or_constant_columns_are_unusable():
    """The guard goal_dist now shares with experiments: these crash sklearn 1.9's HGB binner."""
    assert not E._usable(np.full(500, np.nan))
    assert not E._usable(np.ones(500))
    assert E._usable(np.random.default_rng(0).normal(size=500))

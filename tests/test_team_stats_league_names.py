"""team_match_stats files every league under its ONE canonical name (Data Truth audit finding 55).

    python -m pytest tests/test_team_stats_league_names.py -q
"""
from __future__ import annotations

import pytest

from config import pro_config as cfg
from src.pipelines import team_stats as TS

pytestmark = pytest.mark.skipif(not (cfg.V9_LOCAL / "config" / "leagues.json").exists(),
                                reason="no v9 checkout")


def test_provider_names_map_to_canonical():
    m = TS.canonical_league_map()
    assert m["Eredivisie"] == "Dutch Eredivisie"
    assert m["Belgian Pro League"] == "Belgian First Division A"
    assert m["Primeira Liga"] == "Portuguese Primeira Liga"
    assert m["Championship"] == "Championship"


def test_stored_rows_carry_canonical_league_names():
    from src.data import season_store as store
    d = store.read(TS.TABLE)
    if d.empty:
        pytest.skip("no stored team_match_stats")
    canon = set(TS.canonical_league_map().values())
    assert set(d["league"].astype(str)) <= canon

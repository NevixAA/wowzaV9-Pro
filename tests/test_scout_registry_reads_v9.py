"""The Pro league registry reads v9's tables as v9 computes them (Data Truth audit finding 49).

    python -m pytest tests/test_scout_registry_reads_v9.py -q
"""
from __future__ import annotations

import pytest

from config import pro_config as cfg
from src.scout import registry as R

pytestmark = pytest.mark.skipif(not (cfg.V9_LOCAL / "config.py").exists(), reason="no v9 checkout")


def test_registry_sees_every_v9_league_and_live_leagues_are_live():
    r = R.build()
    rows = {x["league_name"]: x for x in r["leagues"] if not x["league_name"].startswith("scout:")}
    assert len(rows) >= R.MIN_V9_LEAGUES
    for lg in ("Championship", "Bundesliga 2", "Norway Eliteserien"):
        assert rows[lg]["deployment_state"] == "LIVE", lg
        assert rows[lg]["standard_supported"] or rows[lg]["new_format_supported"]


def test_a_tiny_read_fails_loudly(monkeypatch):
    from src.data import v9_config

    class Empty:
        pass
    monkeypatch.setattr(v9_config, "load", lambda *a, **k: Empty())
    with pytest.raises(RuntimeError):
        R.build()

"""Phase 2 Part 10 (cross-repository contracts): a v9 ledger whose schema changed must be REJECTED by
Pro's importer, never imported with the renamed column silently turned into NaN.

Before this test, `from_ledgers` read every column with `d.get(col, <empty Series>)`: if v9 renamed
`edge_pct`, `odds` or `pnl`, every settlement row was written with that field blank and every study
that reads it (threshold curves, model-vs-market, track evidence) silently lost the rows. The
importer runner (src/pipelines/pro_collect.py) records a raising importer in collect_health.json
and does not advance watermarks, so raising is the loud, recoverable failure.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.data import v9_source
from src.importers import current_wowza as cw

MAIN = {"source": "live", "generated_at": "2026-10-20 10:00", "match_date": "2026-10-21",
        "league": "England Premier League", "home_team": "Arsenal", "away_team": "Chelsea",
        "side": "OVER", "odds": "2.0", "edge_pct": "5.0", "signal_tier": "SNIPER", "result": "WIN",
        "pnl": "1.0", "model_type": "standard"}
SIDE = {**MAIN, "market": "btts", "side": "YES", "model_prob": "0.55"}


def _serve(monkeypatch, main: dict | None, side: dict | None):
    frames = {"output/bets_ledger.csv": pd.DataFrame([main]) if main else pd.DataFrame(),
              "output/side_bets_ledger.csv": pd.DataFrame([side]) if side else pd.DataFrame()}
    monkeypatch.setattr(cw, "fetch_csv", lambda rel, required=True: frames[rel].copy())
    # keep the test offline and independent of v9's registry: identity keys are not under test here
    monkeypatch.setattr(cw.ent, "add_fixture_key", lambda d, **k: d.assign(fixture_key="k"))


@pytest.mark.parametrize("col", ["edge_pct", "odds", "pnl", "result", "side", "match_date", "league",
                                 "home_team", "away_team", "model_type", "signal_tier"])
def test_main_ledger_missing_a_contract_column_is_rejected(monkeypatch, col):
    m = dict(MAIN)
    m.pop(col)
    _serve(monkeypatch, m, None)
    with pytest.raises(v9_source.SchemaIncompatible, match=col):
        cw.from_ledgers()


@pytest.mark.parametrize("col", ["edge_pct", "odds", "pnl", "result", "market", "model_type"])
def test_side_ledger_missing_a_contract_column_is_rejected(monkeypatch, col):
    s = dict(SIDE)
    s.pop(col)
    _serve(monkeypatch, None, s)
    with pytest.raises(v9_source.SchemaIncompatible, match=col):
        cw.from_ledgers()


def test_schema_incompatible_is_a_source_failure():
    # pro_collect and every caller already treat SourceUnavailable as "do not trust this read"
    assert issubclass(v9_source.SchemaIncompatible, v9_source.SourceUnavailable)

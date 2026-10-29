"""Serie B BTTS league-vs-model forward test: price rule and verdict logic.

    python -m pytest tests/test_btts_league_regime.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.studies import btts_league_regime as B  # noqa: E402

REG = json.loads(B.REG.read_text(encoding="utf-8"))


def _q(ts, mkt, odds, ko="2026-11-01T14:00:00Z", match="Bari vs Pisa", lg="Serie B"):
    return {"snapshot_date": ts[:10], "snapshot_ts": ts, "match_date": "2026-11-01", "kickoff_utc": ko,
            "league": lg, "match": match, "market": mkt, "odds": str(odds)}


def test_entry_is_first_and_close_is_last_prekickoff_two_sided_quote():
    raw = pd.DataFrame([
        _q("2026-10-30T08:00:00Z", "btts_yes", 1.95), _q("2026-10-30T08:00:00Z", "btts_no", 1.90),
        _q("2026-10-31T08:00:00Z", "btts_yes", 1.80),                       # one-sided -> ignored
        _q("2026-11-01T12:00:00Z", "btts_yes", 1.85), _q("2026-11-01T12:00:00Z", "btts_no", 2.00),
        _q("2026-11-01T15:00:00Z", "btts_yes", 1.20), _q("2026-11-01T15:00:00Z", "btts_no", 4.50),   # in-play
        _q("2026-10-30T08:00:00Z", "btts_yes", 1.95, lg="La Liga 2"),
    ])
    p = B.prices(raw, "Serie B", "2026-10-30")
    assert len(p) == 1
    assert p.loc[0, "btts_yes"] == 1.95 and p.loc[0, "btts_yes_close"] == 1.85
    assert (p.loc[0, "home_team"], p.loc[0, "away_team"]) == ("Bari", "Pisa")


def test_first_half_style_quotes_are_dropped():
    raw = pd.DataFrame([_q("2026-10-30T08:00:00Z", "btts_yes", 4.0), _q("2026-10-30T08:00:00Z", "btts_no", 1.25)])
    assert B.prices(raw, "Serie B", "2026-10-30").empty


def _board(n, hit, odds=1.95, days=20, seed=0):
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < hit).astype(float)
    return pd.DataFrame({"match_date": [f"2026-11-{1 + i % days:02d}" for i in range(n)], "y": y,
                         "btts_yes": odds, "pnl": np.where(y == 1, odds - 1, -1.0), "clv": 0.01})


def test_verdicts_need_the_registered_sample_size():
    ev = B.evaluate(REG, _board(40, 0.9), pd.Series([True] * 40))
    assert ev["H-BTTS-REGIME-SB"]["status"] == "ACCRUING", "40 < 150 can never pass, however good"
    ev = B.evaluate(REG, _board(200, 0.75), pd.Series([True] * 200))
    assert ev["H-BTTS-REGIME-SB"]["status"] == "FORWARD_SUPPORTED"
    ev = B.evaluate(REG, _board(200, 0.30), pd.Series([True] * 200))
    assert ev["H-BTTS-REGIME-SB"]["status"] == "REJECTED"


def test_model_arm_compares_picked_with_not_picked():
    b = _board(200, 0.55, seed=3)
    same = B.evaluate(REG, b, pd.Series(np.arange(200) % 2 == 0))["H-BTTS-MODEL-SB"]
    assert same["status"] in ("ACCRUING", "MODEL_ADDS_NOTHING") and same["status"] != "MODEL_ADDS"
    b.loc[b.index % 2 == 0, ["y", "pnl"]] = [1.0, 0.95]                 # picked rows all win
    b.loc[b.index % 2 == 1, ["y", "pnl"]] = [0.0, -1.0]
    assert B.evaluate(REG, b, pd.Series(b.index % 2 == 0))["H-BTTS-MODEL-SB"]["status"] == "MODEL_ADDS"


def test_registration_is_research_only():
    assert REG["production_behaviour"].startswith("UNCHANGED")
    assert [h["id"] for h in REG["hypotheses"]] == ["H-BTTS-REGIME-SB", "H-BTTS-MODEL-SB"]

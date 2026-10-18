"""Deep analytics core (brief section 59): first sight, conflicts, flat PnL, windows, projections, policy."""
import numpy as np
import pandas as pd
import pytest

from src.analytics import core as C


def _raw(rows):
    d = pd.DataFrame(rows)
    base = {"source": "live", "league": "L", "home_team": "H", "away_team": "A", "market": "OU25", "side": "OVER",
            "tier": "SNIPER", "odds": 2.0, "edge": 0.05, "model_p": 0.55, "kelly": np.nan, "clv": np.nan,
            "closing_odds": np.nan, "model": "new_format", "result": "WIN", "ledger_pnl": 1.0,
            "generated_at": pd.Timestamp("2026-09-01T06:00", tz="UTC"), "day": "2026-09-02"}
    for k, v in base.items():
        if k not in d.columns:
            d[k] = v
        elif k not in ("model",):                     # a column set on SOME rows: default the others
            d[k] = d[k].where(d[k].notna(), v)
    return d


def test_first_sight_keeps_earliest_and_counts_conflicts():
    d = _raw([{"generated_at": pd.Timestamp("2026-09-01T08:00", tz="UTC"), "side": "UNDER", "result": "LOSS"},
              {"generated_at": pd.Timestamp("2026-09-01T06:00", tz="UTC"), "side": "OVER", "result": "WIN"},
              {"market": "BTTS", "side": "YES"}])                                  # different market = separate bet
    fs, st = C.first_sight(d)
    assert st["UNIQUE_FIRST_SIGHT_ROWS"] == 2 and st["DUPLICATES_REMOVED"] == 1
    assert st["CONFLICTING_SIDE_ROWS_FOUND"] == 1                                  # the later flip
    assert fs[fs.market == "OU25"]["side"].iloc[0] == "OVER"                       # first tip stands


def test_flat_pnl_roi_hit_and_voids():
    d = _raw([{"home_team": "a", "result": "WIN", "odds": 2.5}, {"home_team": "b", "result": "LOSS"},
              {"home_team": "c", "result": "VOID"}, {"home_team": "d", "result": ""}])  # pending dropped
    s = C.settle(C.first_sight(d)[0])
    m = C.summarize(s, ci=False)
    assert m["N"] == 3 and m["W"] == 1 and m["L"] == 1 and m["void"] == 1
    assert m["pnl_units"] == pytest.approx(0.5) and m["roi"] == pytest.approx(0.5 / 3)
    assert m["hit_rate"] == pytest.approx(0.5)                                     # voids not in hit
    assert m["break_even_hit_rate"] == pytest.approx(np.mean([1 / 2.5, 1 / 2.0, 1 / 2.0]))   # mean(1/odds)


def test_universes_and_policy_filter():
    d = _raw([{"home_team": "a", "tier": "SNIPER", "market": "BTTS", "league": "L"},
              {"home_team": "b", "tier": "VALUABLE", "market": "BTTS"},
              {"home_team": "c", "tier": "SNIPER", "league": "USA MLS"},
              {"home_team": "e", "tier": "MARKSMAN", "market": "OVER35"}])
    s = C.settle(C.first_sight(d)[0])
    pol = {"tracks": {"new_format|BTTS": {"state": "ACTIVE"}, "new_format|OVER35": {"state": "BLOCKED"}}}
    U = C.universes(s, ["USA MLS"], pol)
    assert len(U["ALL_LIVE"]) == 4 and len(U["NON_MLS"]) == 3
    assert len(U["CORE"]) == 2 and len(U["VALUABLE"]) == 1
    assert len(U["CURRENT_ACTIVE_POLICY"]) == 1 and len(U["BLOCKED_TRACKS"]) == 1
    assert U["CORE"]["pnl"].sum() == U["CORE"].groupby("market")["pnl"].sum().sum()   # no double counting


def test_windows_and_projection_math():
    end = pd.Timestamp("2026-10-17")
    W = C.windows(end)
    assert W["last_7_days"] == (pd.Timestamp("2026-10-11"), end)
    assert W["previous_month"] == (pd.Timestamp("2026-09-01"), pd.Timestamp("2026-09-30"))
    g = pd.DataFrame({"date": pd.date_range("2026-10-08", periods=10), "pnl": [0.1] * 10})
    p = C.projection(g, "2026-10-08", "2026-10-13", end)
    assert p["current_N"] == 10 and p["days_observed"] == 10
    assert p["full_window_projected_tips"] == pytest.approx(10 / 10 * C.SEASON_DAYS)
    assert p["full_window_projected_PnL"] == pytest.approx(C.SEASON_DAYS * 0.1)
    assert p["shrunk_ROI"] == pytest.approx(10 / (10 + C.SHRINK_K) * 0.1)


def test_empty_and_missing_values():
    assert C.summarize(pd.DataFrame(columns=["pnl"]))["N"] == 0
    d = _raw([{"model": None}])
    d["model"] = d["model"].fillna("unknown")
    s = C.settle(C.first_sight(d)[0])
    assert s["model"].iloc[0] == "unknown"
    assert C.confidence_label(9) == "VERY_SMALL" and C.confidence_label(200) == "MATURE"

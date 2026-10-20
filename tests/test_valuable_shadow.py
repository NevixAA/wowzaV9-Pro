"""VALUABLE low-edge shadow: every candidate kept, first sight only, pre-kickoff only, graded correctly."""
import json

import numpy as np
import pandas as pd

from src.studies.valuable import shadow as S

GATES = {"League One": {"valuable": 0.03, "marksman": 0.08, "sniper": 0.12, "sniper_source": "test"}}


def _snap(gen, p=0.55, o=2.0, u=1.9, sha="abc"):
    return {"league": "League One", "date": "2026-10-25", "kickoff_utc": "2026-10-25 15:00:00",
            "home_team": "Luton", "away_team": "Barnsley", "model_type": "standard", "model_version": "v1",
            "p_over25": p, "odds_over25": o, "odds_under25": u, "tier_over": "VALUABLE", "tier_under": "AVOID",
            "p_btts": 0.5, "odds_btts": 1.9, "odds_btts_no": 1.9, "p_over15": np.nan, "odds_over15": np.nan,
            "p_over35": np.nan, "odds_over35": np.nan, "snapshot_sha": sha,
            "gen": pd.Timestamp(gen, tz="UTC"), "kick": pd.Timestamp("2026-10-25 15:00", tz="UTC")}


def test_both_sides_and_below_floor_candidates_are_kept():
    c = S.candidates(pd.DataFrame([_snap("2026-10-22 09:00", p=0.52)]), GATES)
    ou = c[c.market == "over25"].set_index("side")
    assert set(ou.index) == {"OVER", "UNDER"}
    assert abs(ou.loc["OVER", "raw_edge"] - 2.0) < 1e-9                     # 0.52 - 1/2.0
    assert not ou.loc["OVER", "would_have_been_valuable"]                     # 2% < 3% floor: kept anyway
    fair = (0.5 / (0.5 + 1 / 1.9))
    assert abs(ou.loc["OVER", "fair_edge"] - (0.52 - fair) * 100) < 1e-9
    assert set(c[c.market == "btts"].side) == {"YES", "NO"}


def test_fair_edge_unavailable_without_opposite_price():
    s = _snap("2026-10-22 09:00")
    s.update({"p_over15": 0.75, "odds_over15": 1.30})
    c = S.candidates(pd.DataFrame([s]), GATES)
    o15 = c[c.market == "over15"].iloc[0]
    assert o15.FAIR_EDGE_AVAILABLE == "NO" and np.isnan(o15.fair_edge)


def test_first_sight_wins_and_production_thresholds_are_recorded():
    c = S.candidates(pd.DataFrame([_snap("2026-10-22 09:00", p=0.60, sha="first"),
                                   _snap("2026-10-23 09:00", p=0.70, sha="later")]), GATES)
    first = c.sort_values("generated_at").drop_duplicates(["fixture_id", "market", "side"])
    row = first[(first.market == "over25") & (first.side == "OVER")].iloc[0]
    assert row.snapshot_sha == "first" and abs(row.model_probability - 0.60) < 1e-12
    assert json.loads(row.production_thresholds)["valuable"] == 0.03


def test_registered_start_is_after_the_study_period():
    assert pd.Timestamp(S.REGISTERED_START) >= pd.Timestamp("2026-10-21", tz="UTC")

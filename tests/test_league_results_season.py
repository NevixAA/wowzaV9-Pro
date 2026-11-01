"""League ratings use each league's OWN current season (Data Truth audit finding 13).

    python -m pytest tests/test_league_results_season.py -q
"""
from __future__ import annotations

import pandas as pd

from src.studies import league_results as L


def _tips(rows):
    return pd.DataFrame([{"league": lg, "day": day, "win": 1, "odds": 2.0, "market": "btts"} for lg, day in rows])


def test_next_season_does_not_pool_the_previous_one():
    d = _tips([("Championship", "2026-09-01"), ("Championship", "2027-09-01")])
    got = L.current_season_rows(d, pd.Timestamp("2027-10-01", tz="UTC"))
    assert got["day"].tolist() == ["2027-09-01"]


def test_calendar_year_league_rolls_on_january_first():
    d = _tips([("USA MLS", "2026-10-01"), ("USA MLS", "2027-03-01")])
    got = L.current_season_rows(d, pd.Timestamp("2027-04-01", tz="UTC"))
    assert got["day"].tolist() == ["2027-03-01"]


def test_unknown_league_is_left_out_not_guessed():
    d = _tips([("Mystery League", "2026-10-01"), ("Championship", "2026-10-01")])
    got = L.current_season_rows(d, pd.Timestamp("2026-11-01", tz="UTC"))
    assert got["league"].tolist() == ["Championship"]

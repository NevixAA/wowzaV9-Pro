"""Collectors ask API-Football for each league's OWN live season (Data Truth 34, 50, 51, 54).

    python -m pytest tests/test_collector_seasons.py -q
"""
from __future__ import annotations

from src.pipelines import team_stats as TS


def test_current_means_each_leagues_own_season():
    assert TS._league_seasons(("current",), "Japan J-League", "2026-11-01") == ["2027"]
    assert TS._league_seasons(("current",), "Championship", "2026-11-01") == ["2026"]
    assert TS._league_seasons(("current",), "USA MLS", "2027-03-01") == ["2027"]


def test_explicit_years_are_kept_for_backfills_and_deduplicated():
    assert TS._league_seasons(("current", "2025", "2026"), "Championship", "2026-11-01") == ["2026", "2025"]


def test_unknown_league_gets_no_current_season():
    assert TS._league_seasons(("current",), "Mystery League", "2026-11-01") == []

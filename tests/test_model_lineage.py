"""Pro model-lineage evaluation: era attribution, h2h grading, shadow comparison."""
import numpy as np
import pandas as pd

from src.analytics import model_lineage as ml

NOW = pd.Timestamp("2026-10-20", tz="UTC")


def _history():
    return pd.DataFrame({
        "model_type": ["standard", "standard", "btts"],
        "champion_version": ["standard_A", "standard_B", "btts_A"],
        "start_at": ["2026-10-01T09:00:00Z", "2026-10-10T09:00:00Z", "2026-10-01T09:00:00Z"],
        "reconstructed": [True, True, True]})


def _bets(rows):
    d = pd.DataFrame(rows)
    d["generated_at"] = pd.to_datetime(d["generated_at"], utc=True)
    return d


def test_eras_end_where_the_next_champion_starts():
    er = ml.eras(_history(), NOW)
    s = er[er.model_type == "standard"].sort_values("start")
    assert s.iloc[0]["end"] == s.iloc[1]["start"]
    assert s.iloc[1]["end"] == NOW


def test_attribution_methods():
    er = ml.eras(_history(), NOW)
    b = ml.attribute(_bets([
        {"market": "OU25", "model": "standard", "generated_at": "2026-10-05 12:00", "model_version": ""},
        {"market": "OU25", "model": "standard", "generated_at": "2026-10-10 09:20", "model_version": ""},
        {"market": "OU25", "model": "standard", "generated_at": "2026-10-12 12:00", "model_version": ""},
        {"market": "OU25", "model": "standard", "generated_at": "2026-09-01 12:00", "model_version": ""},
        {"market": "OU25", "model": "standard", "generated_at": "2026-10-19 12:00",
         "model_version": "standard_C"},
        {"market": "BTTS", "model": "standard", "generated_at": "2026-10-05 12:00", "model_version": ""},
    ]), er)
    assert list(b["attribution_method"]) == ["RECONSTRUCTED_BY_TIME", "AMBIGUOUS_BOUNDARY",
                                             "RECONSTRUCTED_BY_TIME", "UNKNOWN_LEGACY",
                                             "RECORDED", "RECONSTRUCTED_BY_TIME"]
    assert list(b["version"]) == ["standard_A", "standard_B", "standard_B", "", "standard_C", "btts_A"]


def test_recorded_version_is_never_overridden_by_time():
    er = ml.eras(_history(), NOW)
    b = ml.attribute(_bets([{"market": "OU25", "model": "standard",
                             "generated_at": "2026-10-05 12:00", "model_version": "standard_X"}]), er)
    assert b.iloc[0]["version"] == "standard_X" and b.iloc[0]["attribution_method"] == "RECORDED"


def test_model_routing():
    assert ml.model_of("OU25", "new_format") == "newformat"
    assert ml.model_of("OU25", "unknown") == "standard"
    assert ml.model_of("BTTS", "new_format") == "btts"
    assert ml.model_of("HT_HT_UNDER15", "standard") == "ht_over15"


def test_h2h_grading_is_league_scoped_and_unmatched_stays_ungraded():
    h2h = pd.DataFrame([
        {"league": "L1", "match_date": "2026-10-19", "home_team": "Wolfsburg", "away_team": "Mainz",
         "market": "over25"},
        {"league": "L2", "match_date": "2026-10-19", "home_team": "Wolfsburg", "away_team": "Mainz",
         "market": "btts"},
        {"league": "L1", "match_date": "2026-10-19", "home_team": "Nobody", "away_team": "Mainz",
         "market": "over25"}])
    res = pd.DataFrame([{"league": "L1", "match_date": "2026-10-19", "home_team": "VfL Wolfsburg",
                         "away_team": "1. FSV Mainz 05", "home_goals": 2, "away_goals": 1}])
    g = ml.grade_h2h(h2h, res)
    assert g["y"].iloc[0] == 1.0
    assert g["graded"].tolist() == [True, False, False]


def test_shadow_results_compare_same_fixtures():
    rng = np.random.default_rng(0)
    n = 400
    t = rng.uniform(0.3, 0.7, n)
    y = (rng.uniform(size=n) < t).astype(float)
    h = pd.DataFrame({"model_type": "btts", "challenger_version": "btts_C",
                      "champion_version": "btts_A",
                      "match_date": pd.date_range("2026-10-01", periods=n, freq="6h").strftime("%Y-%m-%d"),
                      "p_champion_raw": np.full(n, 0.5), "p_challenger": t, "y": y, "graded": True})
    r = ml.shadow_results(h)
    assert r.iloc[0]["graded_n"] == n
    assert r.iloc[0]["delta_logloss"] < 0
    assert r.iloc[0]["verdict_so_far"] in ("CHALLENGER_AHEAD", "UNRESOLVED")

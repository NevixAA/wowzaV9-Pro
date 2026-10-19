"""Weather surprise: the match window and the call weights are what the registration says."""
import json
from pathlib import Path

import pandas as pd
import pytest

from src.studies import weather_surprise as W

ROOT = Path(__file__).resolve().parents[1]


def _hourly():
    t = pd.date_range("2026-10-20 12:00", periods=6, freq="h", tz="UTC")
    return {"time": [x.strftime("%Y-%m-%dT%H:%M") for x in t],
            "precipitation": [0, 1, 2, 3, 4, 5], "precipitation_previous_day1": [0, 0, 0, 0, 0, 0],
            "temperature_2m": [10, 11, 12, 13, 14, 15], "temperature_2m_previous_day1": [9] * 6,
            "wind_speed_10m": [5, 5, 5, 5, 5, 5], "wind_speed_10m_previous_day1": [None] * 6}


def test_window_is_kickoff_hour_to_plus_two():
    v = W._window(_hourly(), pd.Timestamp("2026-10-20 13:30", tz="UTC"))
    assert v["actual_precipitation"] == pytest.approx(1 + 2 + 3)       # 13:00, 14:00, 15:00 summed
    assert v["actual_temperature_2m"] == pytest.approx(12.0)             # mean of 11, 12, 13
    assert v["expected_precipitation"] == 0.0
    assert pd.isna(v["expected_wind_speed_10m"])                         # missing stays missing, never 0


def test_weight_counts_long_ranges_as_several_calls():
    assert W._weight(14, 6) == 1.0
    assert W._weight(31, 6) == pytest.approx(31 / 14)


def test_registration_frozen_before_data():
    r = json.loads((ROOT / "registry/weather/registration_v1.json").read_text(encoding="utf-8"))
    assert r["registered_before_any_forecast_data_was_seen"] is True
    assert set(r["questions"]) == {"Q1_forecast_as_pre_match_input", "Q2_actual_weather_upper_bound",
                                   "Q3_surprise_beyond_the_price"}

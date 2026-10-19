"""WEATHER: forecast vs actual — does an UNEXPECTED change in the weather move the scoring? (owner 2026-10-19)

    python -m src.studies.weather_surprise fetch     # resumable; one Open-Meteo budget per run
    python -m src.studies.weather_surprise status

The owner's hypothesis: teams (and the price) prepare for the FORECAST. If heavy rain was expected and
the day turned out dry — or the reverse — tactics are set for the wrong match, and the result may differ
from what the closing price expected.

THE TWO NUMBERS COME FROM THE SAME FORECAST SERVICE (Open-Meteo Previous Runs API):
    expected = the forecast for kickoff hour as it stood ONE DAY BEFORE   (`*_previous_day1`)
    actual   = the same service's day-of value                            (no suffix)
    surprise = actual - expected
Mixing a reanalysis "actual" with a model forecast would make part of the surprise a model-vs-model
difference, not weather. The match window is kickoff hour .. +2h (precipitation is summed; Open-Meteo
precipitation at hour h covers the PRECEDING hour, so the window runs from ~1h before kickoff to ~75').

Input: output/studies/weather/match_venues.csv (league, date, clubs, kickoff UTC, stadium lat/lon), built
from the 2026-10-19 weather table (geocoded home venues; matches not at the home venue are flagged there).
Output: output/studies/weather/match_weather_forecast.csv — one row per match, appended as venues
complete, so every run resumes where the last one stopped. Data before the API's archive start is NaN,
never filled.

Budget: Open-Meteo bills > 2 weeks or > 10 variables per location as several calls. Requests are one
venue x one calendar month (6 variables); each run spends at most BUDGET weighted calls and stops
cleanly on a daily-limit 429. The test design is frozen in registry/weather/registration_v1.json.
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np
import pandas as pd

from config import pro_config as cfg

DIR = cfg.OUTPUT_DIR / "studies" / "weather"
VENUES = DIR / "match_venues.csv"
OUT = DIR / "match_weather_forecast.csv"
STATE = DIR / "fetch_state.json"
API = "https://previous-runs-api.open-meteo.com/v1/forecast"
VARS = ["temperature_2m", "precipitation", "wind_speed_10m"]
HOURLY = VARS + [f"{v}_previous_day1" for v in VARS]
BUDGET = 8000                      # weighted calls per run (free tier: 10,000/day per IP)
SLEEP = 0.25
CALC = "weather_surprise-1.0.0"


def _weight(days: int, n_vars: int) -> float:
    return max(1.0, days / 14.0) * max(1.0, n_vars / 10.0)


def _venue_key(lat, lon) -> str:
    return f"{round(float(lat), 3)}|{round(float(lon), 3)}"


def _window(hourly: dict, kickoff: pd.Timestamp) -> dict:
    """Kickoff hour .. +2h. Temperature and wind are averaged, precipitation summed."""
    t = pd.to_datetime(hourly["time"], utc=True)
    k = kickoff.floor("h")
    m = (t >= k) & (t <= k + pd.Timedelta(hours=2))
    if not m.any():
        return {}
    out = {}
    for v in VARS:
        for suffix, tag in (("", "actual"), ("_previous_day1", "expected")):
            arr = np.array(hourly.get(v + suffix, [None] * len(t)), dtype=float)[m]
            if np.isnan(arr).all():
                out[f"{tag}_{v}"] = np.nan
            else:
                out[f"{tag}_{v}"] = float(np.nansum(arr)) if v == "precipitation" else float(np.nanmean(arr))
    return out


def fetch(budget: float = BUDGET) -> dict:
    import requests
    mv = pd.read_csv(VENUES)
    mv["kickoff_utc"] = pd.to_datetime(mv["kickoff_utc"], utc=True, errors="coerce")
    mv = mv.dropna(subset=["kickoff_utc", "lat", "lon"])
    mv["venue"] = [_venue_key(a, b) for a, b in zip(mv["lat"], mv["lon"])]
    mv["month"] = mv["kickoff_utc"].dt.strftime("%Y-%m")
    done = set()
    if OUT.exists():
        prev = pd.read_csv(OUT, usecols=["venue", "month"])
        done = set(zip(prev["venue"], prev["month"]))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"weighted_calls": 0, "runs": 0}
    spent, rows, stop_reason = 0.0, [], "budget"
    todo = mv.groupby(["venue", "month"])
    for (venue, month), g in todo:
        if (venue, month) in done:
            continue
        start = g["kickoff_utc"].min().strftime("%Y-%m-%d")
        end = (g["kickoff_utc"].max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        days = (pd.Timestamp(end) - pd.Timestamp(start)).days + 1
        w = _weight(days, len(HOURLY))
        if spent + w > budget:
            break
        lat, lon = g["lat"].iloc[0], g["lon"].iloc[0]
        try:
            r = requests.get(API, params={"latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
                                          "hourly": ",".join(HOURLY), "timezone": "UTC"}, timeout=60)
            body = r.json()
        except Exception as e:                                         # noqa: BLE001
            stop_reason = f"network error: {e}"
            break
        if r.status_code == 429:
            reason = str(body.get("reason", ""))
            stop_reason = f"429: {reason}"
            if "minutely" in reason.lower():
                time.sleep(65)
                continue
            break
        spent += w
        hourly = body.get("hourly") or {}
        for rr in g.itertuples(index=False):
            vals = _window(hourly, rr.kickoff_utc) if hourly else {}
            rows.append({"league": rr.league, "date": rr.date, "home_team": rr.home_team, "away_team": rr.away_team,
                         "kickoff_utc": rr.kickoff_utc.isoformat(), "venue": venue, "month": month,
                         "api_error": "" if hourly else str(body.get("reason", "no hourly data"))[:120], **vals})
        time.sleep(SLEEP)
    else:
        stop_reason = "complete"
    if rows:
        DIR.mkdir(parents=True, exist_ok=True)
        new = pd.DataFrame(rows)
        if OUT.exists():
            new = pd.concat([pd.read_csv(OUT), new], ignore_index=True)
        new.to_csv(OUT, index=False)
    state["weighted_calls"] = round(state["weighted_calls"] + spent, 1)
    state["runs"] += 1
    state["last_run"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")
    state["last_stop_reason"] = stop_reason
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
    return {**state, "rows_added": len(rows), "spent_this_run": round(spent, 1), **status()}


def status() -> dict:
    total = len(pd.read_csv(VENUES)) if VENUES.exists() else 0
    got = pd.read_csv(OUT) if OUT.exists() else pd.DataFrame()
    have = int(got["expected_precipitation"].notna().sum()) if "expected_precipitation" in got else 0
    return {"matches_total": total, "matches_fetched": int(len(got)), "matches_with_forecast": have,
            "complete": bool(total and len(got) >= total), "calculation_version": CALC}


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "status"
    print(json.dumps({"fetch": fetch, "status": status}[step](), indent=1, default=str))

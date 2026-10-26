"""E1 (owner brief 2026-10-26): the monthly API budget status must be able to leave OK.

The bug: scheduler_health.json reported an estimated month-end usage of ~107,500 against an
allowance of 100,000 with "status": "OK", because the status was a literal. These tests pin the
thresholds at their boundaries, the projection formula, and that the verdict reaches the
top-level `status` field — the only field v9's dashboard reads.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.monitoring import scheduler as sch  # noqa: E402

A = 100_000


# ── thresholds: OK <= 100% < WARN <= 110% < RED ───────────────────────────────────────────────
@pytest.mark.parametrize("projected,expected", [
    (0, "OK"),
    (90_000, "OK"),
    (100_000, "OK"),            # exactly the allowance is still OK
    (100_001, "WARN"),          # one call over -> WARN
    (107_523, "WARN"),          # the figure the bug reported as OK
    (110_000, "WARN"),          # exactly 110% is still WARN
    (110_001, "RED"),           # materially above -> RED
    (150_000, "RED"),
])
def test_status_boundaries(projected, expected):
    status, pct = sch.budget_status(projected, used_mtd=50_000, allowance=A)
    assert status == expected, (projected, status, pct)


def test_exhausted_allowance_is_red_even_if_projection_is_low():
    # Month-to-date already at the allowance: the plan is spent, whatever the projection says.
    assert sch.budget_status(100_000, used_mtd=100_000, allowance=A)[0] == "RED"


def test_unknown_when_unmeasurable():
    assert sch.budget_status(None, 10, A)[0] == "UNKNOWN"
    assert sch.budget_status(50_000, 10, None)[0] == "UNKNOWN"
    assert sch.budget_status(50_000, 10, 0)[0] == "UNKNOWN"


def test_thresholds_are_the_documented_ones():
    assert sch.BUDGET_WARN_PCT == 100.0 and sch.BUDGET_RED_PCT == 110.0


# ── projection formula ────────────────────────────────────────────────────────────────────────
def test_projection_uses_fractional_elapsed_time():
    # 06:00 on the 26th of a 31-day month: 25.25 days elapsed, 5.75 remaining.
    now = pd.Timestamp("2026-10-26T06:00:00Z")
    p = sch.project_month_end(90_000, now)
    assert p["days_in_month"] == 31
    assert abs(p["elapsed_days"] - 25.25) < 1e-6
    expected = 90_000 + 90_000 / 25.25 * 5.75
    assert abs(p["projected_month_end"] - expected) <= 1
    # The old formula (used / now.day * days_in_month) under-projected by counting the partial
    # day as whole.
    assert p["projected_month_end"] > int(90_000 / 26 * 31)


def test_projection_takes_the_faster_trailing_rate():
    now = pd.Timestamp("2026-10-15T00:00:00Z")
    slow = sch.project_month_end(14_000, now)                    # 1,000/day month-to-date
    fast = sch.project_month_end(14_000, now, trailing_used=21_000)  # 3,000/day last 7 days
    assert fast["rate_basis"] == "trailing"
    assert fast["projected_month_end"] == 14_000 + 3_000 * 17
    assert slow["projected_month_end"] == 14_000 + 1_000 * 17
    # a slower trailing rate never lowers the projection
    calm = sch.project_month_end(14_000, now, trailing_used=700)
    assert calm["projected_month_end"] == slow["projected_month_end"]


def test_first_hours_of_month_do_not_explode():
    # 500 calls in the first hour must not project to 500*24*31.
    p = sch.project_month_end(500, pd.Timestamp("2026-11-01T01:00:00Z"))
    assert p["projected_month_end"] < 500 * 31 + 1
    assert sch.budget_status(p["projected_month_end"], 500, A)[0] == "OK"


# ── the estimator end to end, from recorded observed_at (never mtime) ─────────────────────────
def _snaps(n_units: int, now: pd.Timestamp) -> pd.DataFrame:
    start = now.normalize().replace(day=1)
    span = (now - start).total_seconds()
    ts = [start + pd.Timedelta(seconds=span * i / max(n_units, 1)) for i in range(n_units)]
    return pd.DataFrame({"fixture_key": [f"f{i}" for i in range(n_units)],
                         "market": "OU25", "league": "L",
                         "observed_at": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in ts]})


def test_odds_budget_no_longer_hardcodes_ok(monkeypatch):
    now = pd.Timestamp.now(tz="UTC")
    start = now.normalize().replace(day=1)
    elapsed = max(1.0, (now - start).total_seconds() / 86400)
    dim = pd.Period(now.strftime("%Y-%m")).days_in_month
    # Choose a month-to-date count that projects to ~120% of the allowance.
    n = int(1.2 * A * elapsed / dim) + 1
    if n >= A:                       # end of month: just exceed the allowance outright
        n = A
    b = sch._odds_api_budget(_snaps(n, now))
    assert b["status"] == "RED", b
    assert b["is_billed_credit_count"] is False
    assert "projection" in b and "formula" in b["projection"]


def test_budget_verdict_reaches_top_level_status():
    fresh = {"market_snapshots": {"status": "OK"}, "model_snapshots": {"status": "OK"}}
    cad = {"market_snapshots": {"active_p90_gap_min": 10},
           "model_snapshots": {"active_p90_gap_min": 10}}
    api = {"status": "OK"}
    assert sch._status(cad, fresh, 30, api, {"odds_api_budget": {"status": "OK"}}) == "PASS"
    assert sch._status(cad, fresh, 30, api, {"odds_api_budget": {"status": "WARN"}}) == "WARN"
    assert sch._status(cad, fresh, 30, api, {"odds_api_budget": {"status": "RED"}}) == "FAIL"
    # an unmeasured budget neither alarms nor reassures
    assert sch._status(cad, fresh, 30, api, {"odds_api_budget": {"status": "NO_DATA"}}) == "PASS"
    assert sch.overall_budget_status({"a": {"status": "WARN"}, "b": {"status": "RED"}}) == "RED"

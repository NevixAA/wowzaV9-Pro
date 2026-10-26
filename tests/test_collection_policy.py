"""E2 (owner brief 2026-10-26): cost-aware cadence policy for Pro's own collectors.

Pins the priority order, the horizon-band re-poll intervals, the near-kickoff close bands, the
duplicate-poll planner and the budget guard's shedding order — near-close is never shed by the
monthly guard; far-horizon is shed first.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.monitoring import collection_policy as pol  # noqa: E402


# ── priority classes ──────────────────────────────────────────────────────────────────────────
def test_near_close_outranks_everything():
    assert pol.priority_class(30) == 1
    assert pol.priority_class(359, production=False) == 1
    assert pol.priority_class(30, production=True, experiment=True, candidate=True) == 1


def test_priority_order_beyond_near_close():
    far = 3000
    assert pol.priority_class(far, production=True) == 2
    assert pol.priority_class(far, experiment=True) == 3
    assert pol.priority_class(far, candidate=True) == 4
    assert pol.priority_class(far) == 5
    assert pol.priority_class(far, production=True, experiment=True) == 2


def test_post_kickoff_is_not_near_close():
    assert pol.priority_class(-5) == 5


# ── re-poll intervals by horizon ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("mtk,expected", [(30, 0), (360, 0), (361, 180), (1440, 180),
                                          (1441, 480), (4320, 480), (4321, 1440)])
def test_repoll_bands(mtk, expected):
    assert pol.repoll_minutes(mtk, 5) == expected


def test_experiments_poll_twice_as_often_far_out():
    assert pol.repoll_minutes(2000, 3) == 240
    assert pol.repoll_minutes(2000, 2) == 240
    assert pol.repoll_minutes(2000, 4) == 480


def test_unchanged_backoff_only_beyond_a_day():
    assert pol.repoll_minutes(5000, 5, unchanged_streak=2) == 2880
    assert pol.repoll_minutes(5000, 5, unchanged_streak=1) == 1440
    # inside T-24h an unchanged market is still worth re-reading
    assert pol.repoll_minutes(1000, 5, unchanged_streak=5) == 180
    assert pol.repoll_minutes(100, 5, unchanged_streak=5) == 0


def test_due_logic():
    assert pol.is_due(5000, None, 5)                  # never polled -> due
    assert not pol.is_due(5000, 600, 5)               # polled 10h ago, needs 24h
    assert pol.is_due(5000, 1440, 5)
    assert pol.is_due(100, 1, 1)                      # near-close: every opportunity


# ── near-kickoff close bands ──────────────────────────────────────────────────────────────────
# (lo, hi] like scheduler's coverage bands: exactly 30 min out is T-30m, exactly 60 is T-1h.
@pytest.mark.parametrize("mtk,band", [(120, "T-3h"), (60.5, "T-3h"), (60, "T-1h"), (30.1, "T-1h"),
                                      (30, "T-30m"), (10.1, "T-30m"), (10, "T-10m"),
                                      (1.01, "T-10m"), (1, None), (121, None), (0, None)])
def test_near_bands(mtk, band):
    assert pol.near_band(mtk) == band


def test_near_bands_match_coverage_bands():
    cov = {name: (lo, hi) for lo, hi, name in pol.COVERAGE_BANDS}
    for hi, lo, name in pol.NEAR_BANDS:
        if name == "T-3h":
            assert cov[name][0] <= lo and hi <= cov[name][1]
        else:
            assert (cov[name][0], cov[name][1]) == (0 if name == "T-10m" else lo, hi)


def test_near_band_spacing_is_finer_than_every_band():
    for hi, lo, _ in pol.NEAR_BANDS:
        assert (hi - lo) * 60 > pol.NEAR_PASS_SECONDS


# ── duplicate-poll planner ────────────────────────────────────────────────────────────────────
def test_league_call_used_only_when_cheaper_and_never_drops_a_fixture():
    due = pd.DataFrame({"fixture_id": [1, 2, 3, 4, 5], "league_id": [10, 10, 10, 20, 30]})
    plan = pol.plan_near_calls(due, {10: 8, 20: 1, 30: 25})
    kinds = {(k, i) for k, i, _ in plan}
    assert ("league", 10) in kinds                    # 3 due fixtures, 1 page -> one call
    assert ("fixture", 4) in kinds and ("fixture", 5) in kinds   # 30 has 3 pages for 1 fixture
    assert sum(c for _, _, c in plan) == 3


def test_league_pages():
    assert pol.league_pages(0) == 1 and pol.league_pages(10) == 1 and pol.league_pages(11) == 2


# ── ledger + budget guard ─────────────────────────────────────────────────────────────────────
def _runs(per_day: int, days: int, now: pd.Timestamp) -> pd.DataFrame:
    ts = [now - pd.Timedelta(days=d) for d in range(days)]
    return pd.DataFrame({"collector": "scout_sweep", "ts": ts,
                         "started": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in ts],
                         "api_calls": per_day})


NOW = pd.Timestamp("2026-10-20T12:00:00Z")


def test_guard_ok_allows_everything():
    g = pol.Guard(NOW, _runs(1000, 19, NOW), allowance=100_000)
    assert g.b["status"] == "OK"
    assert all(g.allowed(p) for p in range(1, 6))


def test_guard_warn_sheds_far_horizon_first():
    # ~3,400/day -> ~105k projected: WARN
    g = pol.Guard(NOW, _runs(3400, 19, NOW), allowance=100_000)
    assert g.b["status"] == "WARN", g.b
    assert [g.allowed(p) for p in range(1, 6)] == [True, True, True, True, False]


def test_guard_red_keeps_only_near_close_and_production():
    g = pol.Guard(NOW, _runs(5000, 19, NOW), allowance=100_000)
    assert g.b["status"] == "RED"
    assert [g.allowed(p) for p in range(1, 6)] == [True, True, False, False, False]


def test_near_close_survives_a_spent_day_cap():
    g = pol.Guard(NOW, _runs(1000, 19, NOW), allowance=100_000)
    g.spend(10 ** 6)
    assert g.allowed(1) and g.allowed(2) and not g.allowed(3)


def test_no_ledger_is_no_data_not_ok():
    b = pol.budget(NOW, pd.DataFrame(columns=["collector", "started", "api_calls", "ts"]))
    assert b["status"] == "NO_DATA"


def test_ledger_round_trip_uses_recorded_timestamps_not_mtime(tmp_path, monkeypatch):
    monkeypatch.setattr(pol, "LEDGER_DIR", tmp_path)
    p = pol.record_run("scout_sweep", "2026-10-20T10:00:00Z", "2026-10-20T10:02:00Z", 250,
                       detail={"leagues_polled": {"5": 3}})
    # a file touched "now" must still be read as a 2026-10-20 run
    os.utime(p, (0, 0))
    lst = tmp_path / "2026-10" / "backfill.json"
    lst.write_text(json.dumps([{"collector": "scout_near", "started": "2026-10-19T10:00:00Z",
                                "api_calls": 40}]), encoding="utf-8")
    d = pol.load_runs(root=tmp_path)
    assert list(d["collector"]) == ["scout_near", "scout_sweep"]
    assert str(d["ts"].iloc[1]) == "2026-10-20 10:00:00+00:00"
    assert int(d["api_calls"].sum()) == 290


def test_dry_run_writes_no_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(pol, "LEDGER_DIR", tmp_path)
    assert pol.record_run("scout_near", "2026-10-20T10:00:00Z", None, 5, dry=True) is None
    assert not any(tmp_path.rglob("*.json"))


# ── scout near loop: bands already observed are not re-bought ─────────────────────────────────
def test_sampled_bands_from_store_rows():
    from src.scout import collect
    o = pd.DataFrame({"fixture_id": [1, 1, 2, 3], "minutes_to_kickoff": [95.0, 25.0, 5.0, 400.0]})
    assert collect.sampled_bands(o) == {(1, "T-3h"), (1, "T-30m"), (2, "T-10m")}


# ── scout sweep integration: a league polled recently and far from kickoff is skipped ─────────
class _FakeClient:
    def __init__(self):
        self.calls, self.remaining = 0, 50_000

    def get_all_pages(self, endpoint, params):
        self.calls += 1
        return []


def test_sweep_skips_far_leagues_polled_recently(tmp_path, monkeypatch):
    import time
    from src.scout import collect
    monkeypatch.setattr(pol, "LEDGER_DIR", tmp_path)
    monkeypatch.setattr(pol, "league_flags", lambda: {})
    monkeypatch.setattr(collect, "_read_recent", lambda table, days: pd.DataFrame())
    now = int(time.time())
    watch = [{"id": 1}, {"id": 2}, {"id": 3}]
    fx = pd.DataFrame([
        {"fixture_id": 11, "league_id": 1, "season": "2026", "kickoff_ts": now + 2 * 3600, "status": "NS"},
        {"fixture_id": 12, "league_id": 2, "season": "2026", "kickoff_ts": now + 100 * 3600, "status": "NS"},
        {"fixture_id": 13, "league_id": 3, "season": "2026", "kickoff_ts": now + 100 * 3600, "status": "NS"},
    ])
    one_hour_ago = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pol.record_run("scout_sweep", one_hour_ago, one_hour_ago, 30,
                   detail={"leagues_polled": {"1": 5, "2": 0}})
    s: dict = {}
    c = _FakeClient()
    collect.step_odds(c, watch, fx, True, s)
    # league 1: near close (T-2h) -> polled every sweep; league 2: >T-72h, polled 1h ago -> not
    # due; league 3: never polled -> due
    assert set(s["leagues_polled"]) == {"1", "3"}
    assert s["leagues_skipped"] == {"not_due": 1, "budget": 0}
    assert c.calls == 2

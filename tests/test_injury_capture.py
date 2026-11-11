"""Injury list capture (ou_info_inputs.forward): rows when fixtures are due, a LOUD failure when
fixtures are due and the provider returns no list, and an explicit NO_FIXTURES_DUE otherwise.
All HTTP is mocked; nothing is written outside tmp_path.

    python -m pytest tests/test_injury_capture.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.studies import ou_info_inputs as O

NOW = pd.Timestamp("2026-11-13T10:00:00Z")
IDS = {"Championship": 40, "Denmark Superliga": 119, "Norway Eliteserien": 103,
       "Sweden Allsvenskan": 113, "Brazil Serie A": 71, "League One": 41}


class _Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.headers = body, status, {"x-ratelimit-requests-remaining": "70000"}

    def json(self):
        return self.body


class FakeAF:
    """Answers /leagues, /fixtures and /injuries?ids= from in-memory tables; records every call."""

    def __init__(self, fixtures, injuries, coverage=None, errors_on=None):
        self.fixtures, self.injuries = fixtures, injuries          # {league_id: [(fid, iso, status)]}
        self.coverage = coverage or {}                             # {league_id: bool}, default True
        self.errors_on = errors_on
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        ep = url.rsplit("/", 1)[1]
        self.calls.append((ep, dict(params)))
        if ep == self.errors_on:
            return _Resp({"errors": {"requests": "limit reached"}, "response": []})
        if ep == "leagues":
            lid = params["id"]
            return _Resp({"errors": [], "paging": {"current": 1, "total": 1}, "response": [
                {"league": {"id": lid}, "seasons": [{"year": int(params["season"]),
                 "coverage": {"injuries": self.coverage.get(lid, True)}}]}]})
        if ep == "fixtures":
            rows = [{"fixture": {"id": f, "date": d, "status": {"short": st}}}
                    for f, d, st in self.fixtures.get(params["league"], [])]
            return _Resp({"errors": [], "paging": {"current": 1, "total": 1}, "response": rows})
        if ep == "injuries":
            asked = [int(x) for x in params["ids"].split("-")]
            assert len(asked) <= O.IDS_PER_CALL
            rows = [{"fixture": {"id": f}, "team": {"id": t}, "player": {"id": p, "type": ty}}
                    for f, t, p, ty in self.injuries if f in asked]
            return _Resp({"errors": [], "paging": {"current": 1, "total": 1}, "response": rows})
        raise AssertionError(ep)


@pytest.fixture
def env(tmp_path, monkeypatch):
    from src.data import v9_config
    from src.monitoring import collection_policy as pol
    monkeypatch.setattr(O, "SNAP", tmp_path / "injury_snapshots.parquet")
    monkeypatch.setattr(O, "OUT", tmp_path)
    monkeypatch.setattr(O, "_league_ids", lambda: dict(IDS))
    monkeypatch.setattr(O.time, "sleep", lambda s: None)
    monkeypatch.setattr(O.common, "_af_key", lambda: "test-key")
    monkeypatch.setattr(v9_config, "api_season", lambda lg, d: "2026")
    monkeypatch.setattr(pol, "LEDGER_DIR", tmp_path / "ledger")
    monkeypatch.setattr(pol, "load_runs", lambda *a, **k: pd.DataFrame(columns=["collector", "started", "api_calls"]))
    return tmp_path


def _iso(hours):
    return (NOW + pd.Timedelta(hours=hours)).isoformat()


def test_fixtures_due_provider_answers_rows_written(env):
    fx = {40: [(1, _iso(30), "NS"), (2, _iso(30), "NS"), (3, _iso(-40), "FT")],
          71: [(10, _iso(80), "NS")]}
    inj = [(1, 100, 501, "Missing Fixture"), (1, 100, 502, "Questionable"), (2, 200, 601, "Missing Fixture"),
           (3, 100, 501, "Missing Fixture"), (10, 300, 701, "Missing Fixture")]
    af = FakeAF(fx, inj)
    res = O.forward(now=NOW, session=af)
    assert res["status"] == "OK"
    assert res["fixtures_due_48h_covered"] == 2 and res["due_fixtures_with_list"] == 2
    assert res["pre_kickoff_rows"] == 4 and res["captured"] == 5
    ch = res["per_league"]["Championship"]
    assert ch["due_48h"] == 2 and ch["pre_kickoff_rows"] == 3 and ch["post_kickoff_rows"] == 1
    assert ch["all_pre_kickoff_rows_before_kickoff"]
    snap = pd.read_parquet(env / "injury_snapshots.parquet")
    assert len(snap) == 5 and set(snap.columns) == set(O.SNAP_COLS)
    pre = snap[snap["pre_kickoff"]]
    assert (pre["fixture_ts"] > pre["captured_at"]).all()
    # fixture times come from /fixtures, never a placeholder
    assert snap["fixture_ts"].notna().all()
    # 6 /leagues + 6 /fixtures + 1 /injuries (4 fixtures fit in one ids call)
    assert [c[0] for c in af.calls].count("injuries") == 1 and res["api_calls"] == 13
    ledger = list((env / "ledger").glob("*/*.json"))
    assert len(ledger) == 1 and "injury_capture" in ledger[0].name


def test_fixtures_due_zero_rows_fails_loudly_but_keeps_post_rows(env):
    fx = {40: [(1, _iso(20), "NS"), (2, _iso(25), "NS"), (3, _iso(-10), "FT")]}
    inj = [(3, 100, 501, "Missing Fixture")]          # only the finished match has a list
    with pytest.raises(O.CaptureFailure, match="due within 48h"):
        O.forward(now=NOW, session=FakeAF(fx, inj))
    snap = pd.read_parquet(env / "injury_snapshots.parquet")
    assert len(snap) == 1 and not snap["pre_kickoff"].any()     # written before the failure
    assert len(list((env / "ledger").glob("*/*.json"))) == 1


def test_one_covered_league_silent_with_enough_due_fails_even_if_another_answers(env):
    fx = {40: [(i, _iso(24), "NS") for i in range(1, 5)], 71: [(10, _iso(24), "NS")]}
    inj = [(10, 300, 701, "Missing Fixture")]
    with pytest.raises(O.CaptureFailure, match="Championship: 4 fixtures due"):
        O.forward(now=NOW, session=FakeAF(fx, inj))


def test_no_fixtures_due_is_reported_not_success_by_silence(env):
    fx = {71: [(10, _iso(80), "NS")], 40: [(3, _iso(-30), "FT")]}   # break: nothing within 48h
    res = O.forward(now=NOW, session=FakeAF(fx, [(3, 100, 501, "Missing Fixture")]))
    assert res["status"] == "NO_FIXTURES_DUE" and res["fixtures_due_48h_covered"] == 0
    assert res["pre_kickoff_rows"] == 0


def test_league_without_provider_injury_coverage_is_not_expected_to_answer(env):
    fx = {41: [(i, _iso(24), "NS") for i in range(20, 32)], 71: [(10, _iso(24), "NS")]}
    res = O.forward(now=NOW, session=FakeAF(fx, [(10, 300, 701, "Missing Fixture")], coverage={41: False}))
    assert res["status"] == "OK"
    assert res["per_league"]["League One"]["injury_coverage"] is False
    assert res["per_league"]["League One"]["due_48h"] == 12


def test_postponed_fixture_is_not_due(env):
    fx = {40: [(1, _iso(20), "PST")]}
    res = O.forward(now=NOW, session=FakeAF(fx, []))
    assert res["status"] == "NO_FIXTURES_DUE"


def test_provider_error_body_raises_instead_of_reading_as_empty(env):
    fx = {40: [(1, _iso(20), "NS")]}
    with pytest.raises(RuntimeError, match="limit reached"):
        O.forward(now=NOW, session=FakeAF(fx, [], errors_on="injuries"))
    import json
    (rec,) = list((env / "ledger").glob("*/*.json"))        # the calls spent are still metered
    r = json.loads(rec.read_text(encoding="utf-8"))
    assert r["detail"]["status"] == "ERROR" and r["api_calls"] == 13


def test_ids_are_chunked_at_20(env):
    fx = {40: [(i, _iso(20), "NS") for i in range(1, 46)]}
    inj = [(i, 100, 500 + i, "Missing Fixture") for i in range(1, 46)]
    af = FakeAF(fx, inj)
    res = O.forward(now=NOW, session=af)
    assert [c[0] for c in af.calls].count("injuries") == 3 and res["pre_kickoff_rows"] == 45


def test_league_missing_from_v9_map_fails(env, monkeypatch):
    monkeypatch.setattr(O, "_league_ids", lambda: {k: v for k, v in IDS.items() if k != "League One"})
    with pytest.raises(O.CaptureFailure, match="League One"):
        O.forward(now=NOW, session=FakeAF({}, []))


def test_budget_guard_shed_makes_no_calls(env, monkeypatch):
    from src.monitoring import collection_policy as pol

    class Red:
        def __init__(self, *a, **k):
            self.b = {"status": "RED"}

        def allowed(self, prio):
            return prio <= 2
    monkeypatch.setattr(pol, "Guard", Red)
    af = FakeAF({40: [(1, _iso(20), "NS")]}, [])
    res = O.forward(now=NOW, session=af)
    assert res["status"] == "SHED_BUDGET" and af.calls == []


def test_dry_run_writes_nothing(env):
    fx = {40: [(1, _iso(20), "NS")]}
    res = O.forward(now=NOW, session=FakeAF(fx, [(1, 100, 501, "Missing Fixture")]), dry_run=True)
    assert res["status"] == "OK" and res["snapshot_rows"] is None
    assert not (env / "injury_snapshots.parquet").exists() and not (env / "ledger").exists()

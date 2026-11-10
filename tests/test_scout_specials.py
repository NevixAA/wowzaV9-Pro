"""Scout special-market quotes (src/scout/specials.py): zero extra calls, existing outputs unchanged,
same rules as v9 src/specials_quotes.py."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

from src.monitoring import collection_policy as pol
from src.scout import collect
from src.scout import specials as SS

NOW = pd.Timestamp("2030-01-01T12:00:00Z")
KO = NOW + pd.Timedelta(hours=5)


def _entry(fid=1001, ko=KO, lid=7):
    return {
        "league": {"id": lid, "name": "Provider League", "country": "Nowhere", "season": 2029},
        "fixture": {"id": fid, "timestamp": int(ko.timestamp()), "date": ko.isoformat()},
        "update": "2030-01-01T11:55:00+00:00",
        "bookmakers": [
            {"id": 8, "name": "Bet365", "bets": [
                {"id": 5, "name": "Goals Over/Under", "values": [
                    {"value": "Over 0.5", "odd": "1.06"}, {"value": "Under 0.5", "odd": "10.00"},
                    {"value": "Over 2.5", "odd": "1.90"}, {"value": "Under 2.5", "odd": "1.90"},
                    {"value": "Over 1.5", "odd": "1.30"}, {"value": "Under 1.5", "odd": "3.40"},
                    {"value": "Over 3.5", "odd": "3.10"}, {"value": "Under 3.5", "odd": "1.36"},
                    {"value": "Over 4.5", "odd": "6.50"}, {"value": "Under 4.5", "odd": "1.10"},
                    {"value": "Over 6.5", "odd": "26.00"}]},
                {"id": 6, "name": "Goals Over/Under First Half", "values": [{"value": "Over 0.5", "odd": "1.40"}]},
                {"id": 8, "name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.80"},
                                                                {"value": "No", "odd": "1.95"}]},
                {"id": 10, "name": "Exact Score", "values": [
                    {"value": "1:0", "odd": "7.00"}, {"value": "0:0", "odd": "11.00"},
                    {"value": "2:1", "odd": "N/A"}]},
                {"id": 62, "name": "Exact Score - First Half", "values": [{"value": "1:0", "odd": "3.60"}]},
                {"id": 16, "name": "Total - Home", "values": [{"value": "Over 3.5", "odd": "17.00"},
                                                             {"value": "Over 1.5", "odd": "2.40"}]},
                {"id": 17, "name": "Total - Away", "values": [{"value": "Over 3.5", "odd": "34.00"}]}]},
            {"id": 4, "name": "Pinnacle", "bets": [
                {"id": 5, "name": "Goals Over/Under", "values": [{"value": "Over 2.5", "odd": "1.93"},
                                                                 {"value": "Under 2.5", "odd": "1.95"}]},
                {"id": 10, "name": "Exact Score", "values": [{"value": "1:0", "odd": "7.40"},
                                                             {"value": "0:0", "odd": "1.00"}]}]}]}


KEPT = {("Bet365", "Goals Over/Under", "Over 0.5", 1.06), ("Bet365", "Goals Over/Under", "Under 0.5", 10.0),
        ("Bet365", "Goals Over/Under", "Over 4.5", 6.5), ("Bet365", "Goals Over/Under", "Under 4.5", 1.1),
        ("Bet365", "Goals Over/Under", "Over 6.5", 26.0), ("Bet365", "Exact Score", "1:0", 7.0),
        ("Bet365", "Exact Score", "0:0", 11.0), ("Bet365", "Total - Home", "Over 3.5", 17.0),
        ("Bet365", "Total - Away", "Over 3.5", 34.0), ("Pinnacle", "Exact Score", "1:0", 7.4)}


def _parse(resp=None, **kw):
    a = dict(capture="scout_sweep", captured_at=NOW, names={1001: ("Home FC", "Away FC")},
             leagues={7: ("Registry League", "Somewhere")})
    a.update(kw)
    return SS.parse([_entry()] if resp is None else resp, **a)


def test_keeps_exactly_the_requested_full_time_quotes():
    rows = _parse()
    assert {(r["bookmaker"], r["bet"], r["selection"], r["odds"]) for r in rows} == KEPT
    r = rows[0]
    assert r["league"] == "Registry League" and r["league_id"] == 7 and r["home_team"] == "Home FC"
    assert r["fixture_key"] == "Somewhere Registry League [7]|2030-01-01|Home FC|Away FC"
    assert r["kickoff_utc"] == "2030-01-01T17:00:00Z" and r["provider_update"] == "2030-01-01T11:55:00Z"
    assert r["ladder_band"] == "T-6h" and r["minutes_to_kickoff"] == 300.0


def test_pre_kickoff_only_and_names_never_guessed():
    assert _parse(captured_at=KO) == []
    e = _entry()
    e["fixture"] = {"id": 1001}
    assert _parse(resp=[e]) == []
    rows = _parse(names={}, leagues={})
    assert all(r["home_team"] is None and r["fixture_key"] is None for r in rows)
    assert {r["league"] for r in rows} == {"Provider League"}          # the answer's own league block


def test_append_open_change_heartbeat_dry_and_rollover(tmp_path, monkeypatch):
    SS._STATE.clear()
    assert SS.append(_parse(), base=tmp_path, dry=True) == len(KEPT)
    assert not any(tmp_path.rglob("*.csv"))                            # dry writes nothing
    assert SS.append(_parse(), base=tmp_path) == len(KEPT)
    assert SS.append(_parse(captured_at=NOW + pd.Timedelta(minutes=30)), base=tmp_path) == 0
    t30 = KO - pd.Timedelta(minutes=25)
    assert SS.append(_parse(captured_at=t30), base=tmp_path) == len(KEPT)   # one heartbeat each
    assert SS.append(_parse(captured_at=t30 + pd.Timedelta(minutes=3)), base=tmp_path) == 0
    f = tmp_path / "2030-01" / "2030-01-01_sweep.csv"
    d = pd.read_csv(f)
    assert d["obs_reason"].value_counts().to_dict() == {"open": len(KEPT), "heartbeat": len(KEPT)}
    assert list(d.columns) == SS.COLUMNS
    # a fresh process re-reads the stored state: nothing is written twice
    SS._STATE.clear()
    assert SS.append(_parse(captured_at=t30 + pd.Timedelta(minutes=4)), base=tmp_path) == 0
    # rollover: a part at the size limit is closed and the next rows start _p2
    monkeypatch.setattr(SS, "MAX_PART_MB", 0)
    e = _entry()
    e["bookmakers"][0]["bets"][3]["values"][0]["odd"] = "7.50"
    assert SS.append(_parse(resp=[e], captured_at=t30 + pd.Timedelta(minutes=5)), base=tmp_path) == 1
    assert (tmp_path / "2030-01" / "2030-01-01_sweep_p2.csv").exists()
    assert len(pd.read_csv(f)) == 2 * len(KEPT)                        # the closed part is untouched


def test_near_rows_take_names_from_earlier_sidecar_rows(tmp_path):
    SS._STATE.clear()
    SS.append(_parse(), base=tmp_path)
    assert SS.known_names([1001, 5], base=tmp_path) == {1001: ("Home FC", "Away FC")}


# ── mock HTTP: identical existing outputs and the same number of calls ────────────────────────

def _sweep(tmp_path, monkeypatch, with_specials):
    now = int(time.time())
    ko = pd.Timestamp(now + 3 * 3600, unit="s", tz="UTC")
    monkeypatch.setattr(pol, "LEDGER_DIR", tmp_path / "ledger")
    monkeypatch.setattr(pol, "league_flags", lambda: {})
    monkeypatch.setattr(collect, "_read_recent", lambda table, days: pd.DataFrame())
    monkeypatch.setattr(SS, "base_dir", lambda: tmp_path / "side")
    SS._STATE.clear()
    if not with_specials:
        monkeypatch.setattr(SS, "parse", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))
    written = []
    monkeypatch.setattr(collect, "_append", lambda t, rows, tag, dry: written.append((t, pd.DataFrame(rows))) or len(rows))

    class C:
        calls, remaining = 0, 50_000

        def get_all_pages(self, endpoint, params):
            self.calls += 1
            return [_entry(fid=1001, ko=ko, lid=params["league"]), _entry(fid=1002, ko=ko, lid=params["league"])]
    fx = pd.DataFrame([{"fixture_id": f, "league_id": 7, "season": "2026", "kickoff_ts": int(ko.timestamp()),
                        "status": "NS", "home_team": h, "away_team": a}
                       for f, h, a in ((1001, "Home FC", "Away FC"), (1002, "X", "Y"))])
    c, s = C(), {}
    quotes = collect.step_odds(c, [{"id": 7, "name": "Reg", "country": "Z"}], fx, False, s)
    return c.calls, quotes, written, s


def _norm(df):
    return df.drop(columns=["snapshot_ts"]).reset_index(drop=True)


def test_sweep_same_calls_and_same_outputs(tmp_path, monkeypatch):
    calls_on, q_on, w_on, s_on = _sweep(tmp_path / "on", monkeypatch, True)
    monkeypatch.undo()
    calls_off, q_off, w_off, s_off = _sweep(tmp_path / "off", monkeypatch, False)
    assert calls_on == calls_off == 1
    pd.testing.assert_frame_equal(_norm(q_on), _norm(q_off))
    assert [t for t, _ in w_on] == [t for t, _ in w_off] == ["scout_odds"]
    pd.testing.assert_frame_equal(_norm(w_on[0][1]), _norm(w_off[0][1]))
    assert s_on == s_off                                               # last_run summary unchanged
    files = list((tmp_path / "on" / "side").rglob("*_sweep.csv"))
    assert len(files) == 1
    d = pd.read_csv(files[0])
    assert sorted(d["af_fixture_id"].unique()) == [1001, 1002] and set(d["capture"]) == {"scout_sweep"}
    assert set(d[d["af_fixture_id"] == 1002]["home_team"]) == {"X"}
    assert not (tmp_path / "off" / "side").exists()


def _near(tmp_path, monkeypatch, with_specials):
    now = int(time.time())
    seed = pd.DataFrame([{"fixture_id": 1001, "league_id": 7, "kickoff_ts": now + 1800, "market": "ou25",
                          "selection": "over", "bookmaker": "bet365", "odds": 2.0,
                          "snapshot_ts": "2026-01-01T00:00:00Z", "minutes_to_kickoff": 30.0,
                          "quality_flags": ""}])
    monkeypatch.setattr(collect, "_read_recent", lambda t, d: seed)
    monkeypatch.setattr(collect, "_league_seasons", lambda: {})
    monkeypatch.setattr(SS, "base_dir", lambda: tmp_path / "side")
    SS._STATE.clear()
    if not with_specials:
        monkeypatch.setattr(SS, "parse", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("off")))
    calls, written = [], []

    class C:
        calls = 0
        remaining = 99999

        def get(self, endpoint, params):
            calls.append((endpoint, params["fixture"]))
            return {"response": [_entry(fid=1001, ko=pd.Timestamp(now + 1800, unit="s", tz="UTC"))]}
    monkeypatch.setattr(collect, "_append", lambda t, rows, tag, dry: written.append(pd.DataFrame(rows)) or len(rows))
    monkeypatch.setattr(collect.time, "sleep", lambda s: None)
    t0 = [now]
    monkeypatch.setattr(collect.time, "time", lambda: (t0.__setitem__(0, t0[0] + 400), t0[0])[1])
    out = collect.near_loop(C(), minutes=10, dry=False)
    return calls, written, out


def test_near_loop_same_calls_and_same_outputs(tmp_path, monkeypatch):
    calls_on, w_on, o_on = _near(tmp_path / "on", monkeypatch, True)
    monkeypatch.undo()
    calls_off, w_off, o_off = _near(tmp_path / "off", monkeypatch, False)
    assert calls_on == calls_off and len(calls_on) >= 1
    assert len(w_on) == len(w_off)
    for a, b in zip(w_on, w_off):
        pd.testing.assert_frame_equal(_norm(a), _norm(b))
    assert {k: v for k, v in o_on.items()} == {k: v for k, v in o_off.items()}
    d = pd.concat(pd.read_csv(f) for f in (tmp_path / "on" / "side").rglob("*_near.csv"))
    assert set(d["capture"]) == {"scout_near"} and (d["bet"] == "Exact Score").any()


def test_workflows_stage_the_sidecar():
    root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for wf in ("pro_scout.yml", "pro_scout_near.yml"):
        assert "data/season_*/scout_specials_quotes" in (root / wf).read_text(encoding="utf-8")


# ── same rules as v9 (no fork) ───────────────────────────────────────────────────────────────

def _v9_root():
    try:
        from config import pro_config as cfg
        r = Path(cfg.V9_LOCAL)
    except Exception:                                                 # noqa: BLE001
        return None
    return r if (r / "src" / "specials_quotes.py").exists() else None


@pytest.mark.skipif(_v9_root() is None, reason="v9 checkout with src/specials_quotes.py not available")
def test_kept_quotes_identical_to_v9_parser(tmp_path):
    v9 = _v9_root()
    payload = {"response": [_entry()]}
    (tmp_path / "p.json").write_text(json.dumps(payload), encoding="utf-8")
    code = ("import json,sys; from src import specials_quotes as SQ; "
            "p=json.load(open(sys.argv[1])); "
            "r=SQ.parse_specials(p, capture='std', af_fixture_id=1001, league='L', kickoff_utc='', "
            "home='H', away='A', captured_at='2030-01-01T12:00:00Z'); "
            "print(json.dumps(sorted([r_['bookmaker'], r_['bet'], r_['selection'], r_['odds'], "
            "r_['ladder_band'], r_['provider_update']] for r_ in r)))")
    env = {**os.environ, "PYTHONPATH": str(v9)}
    out = subprocess.run([sys.executable, "-c", code, str(tmp_path / "p.json")], cwd=v9, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    v9_rows = json.loads(out.stdout.strip().splitlines()[-1])
    pro_rows = sorted([r["bookmaker"], r["bet"], r["selection"], r["odds"], r["ladder_band"],
                       r["provider_update"]] for r in _parse())
    assert pro_rows == v9_rows

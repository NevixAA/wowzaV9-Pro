"""Scout corners/cards quotes (src/scout/side_odds.py), owner 2026-11-16 (audit gap G1): zero extra calls,
existing scout outputs unchanged, written ONLY to the private store, the same file as v9's
src/side_odds_quotes.py. Plus the team cards kept by src/pipelines/team_stats.py (audit gap G6a)."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pandas as pd
import pytest

from src.monitoring import collection_policy as pol
from src.pipelines import team_stats as TS
from src.scout import collect
from src.scout import side_odds as SO
from src.scout import specials as SS

ROOT = Path(__file__).resolve().parents[1]
#: sha256 (LF line endings) of the shared file; v9's tests pin the same value for src/side_odds_quotes.py
SHARED_SHA256 = "058316def2ba7bb68b37707253ad30baf3b5cfd34a613b5867dbb897baf41491"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_shared_file_is_the_pinned_version():
    assert _sha(ROOT / "src" / "scout" / "side_odds.py") == SHARED_SHA256


def _v9_file():
    try:
        from config import pro_config as cfg
        p = Path(cfg.V9_LOCAL) / "src" / "side_odds_quotes.py"
    except Exception:                                                 # noqa: BLE001
        return None
    return p if p.exists() else None


@pytest.mark.skipif(_v9_file() is None, reason="v9 checkout with src/side_odds_quotes.py not available")
def test_identical_to_v9_file():
    assert _sha(_v9_file()) == _sha(ROOT / "src" / "scout" / "side_odds.py")


def _entry(fid, ko, lid=7):
    return {"league": {"id": lid, "name": "Provider League", "country": "Nowhere", "season": 2029},
            "fixture": {"id": fid, "timestamp": int(ko.timestamp()), "date": ko.isoformat()},
            "update": "2030-01-01T11:55:00+00:00",
            "bookmakers": [{"id": 8, "name": "Bet365", "bets": [
                {"id": 45, "name": "Corners Over Under", "values": [
                    {"value": "Over 9.5", "odd": "1.90"}, {"value": "Under 9.5", "odd": "1.90"}]},
                {"id": 57, "name": "Home Corners Over/Under", "values": [{"value": "Over 4.5", "odd": "1.80"}]},
                {"id": 80, "name": "Cards Over/Under", "values": [{"value": "Over 3.5", "odd": "1.85"}]},
                {"id": 77, "name": "Total Corners (1st Half)", "values": [{"value": "Over 4.5", "odd": "2.00"}]},
                {"id": 10, "name": "Exact Score", "values": [{"value": "1:0", "odd": "7.00"}]},
                {"id": 5, "name": "Goals Over/Under", "values": [{"value": "Over 2.5", "odd": "1.90"},
                                                                 {"value": "Over 4.5", "odd": "6.50"}]}]}]}


#: one clock for both runs of a comparison (two now() calls can straddle a second)
NOW_S = int(time.time())


def _store(tmp_path):
    d = tmp_path / "store"
    d.mkdir(parents=True)
    (d / SO.MARKER).write_text("private", encoding="utf-8")
    return d


def _norm(df):
    return df.drop(columns=["snapshot_ts"]).reset_index(drop=True)


def _sweep(tmp_path, monkeypatch, store, now):
    ko = pd.Timestamp(now + 3 * 3600, unit="s", tz="UTC")
    monkeypatch.setattr(pol, "LEDGER_DIR", tmp_path / "ledger")
    monkeypatch.setattr(pol, "league_flags", lambda: {})
    monkeypatch.setattr(collect, "_read_recent", lambda table, days: pd.DataFrame())
    monkeypatch.setattr(SS, "base_dir", lambda: tmp_path / "specials")
    SS._STATE.clear(); SO._STATE.clear()
    if store is None:
        monkeypatch.delenv(SO.ENV, raising=False)
    else:
        monkeypatch.setenv(SO.ENV, str(store))
    written = []
    monkeypatch.setattr(collect, "_append",
                        lambda t, rows, tag, dry: written.append((t, pd.DataFrame(rows))) or len(rows))

    class C:
        calls, remaining = 0, 50_000

        def get_all_pages(self, endpoint, params):
            self.calls += 1
            return [_entry(1001, ko, params["league"]), _entry(1002, ko, params["league"])]
    fx = pd.DataFrame([{"fixture_id": f, "league_id": 7, "season": "2029", "kickoff_ts": int(ko.timestamp()),
                        "status": "NS", "home_team": h, "away_team": a}
                       for f, h, a in ((1001, "Home FC", "Away FC"), (1002, "X", "Y"))])
    c, s = C(), {}
    q = collect.step_odds(c, [{"id": 7, "name": "Reg", "country": "Z"}], fx, False, s)
    return c.calls, q, written, s


def test_sweep_zero_extra_calls_outputs_unchanged(tmp_path, monkeypatch, capsys):
    store = _store(tmp_path)
    calls_on, q_on, w_on, s_on = _sweep(tmp_path / "on", monkeypatch, store, NOW_S)
    out = capsys.readouterr().out
    monkeypatch.undo()
    calls_off, q_off, w_off, s_off = _sweep(tmp_path / "off", monkeypatch, None, NOW_S)
    assert calls_on == calls_off == 1
    pd.testing.assert_frame_equal(_norm(q_on), _norm(q_off))
    assert [t for t, _ in w_on] == [t for t, _ in w_off] == ["scout_odds"]
    pd.testing.assert_frame_equal(_norm(w_on[0][1]), _norm(w_off[0][1]))
    assert s_on == s_off
    for f in (tmp_path / "on" / "specials").rglob("*.csv"):        # specials sidecar unchanged in kind
        assert "Corners" not in f.read_text(encoding="utf-8")
    files = list((store / "data").rglob("*_sweep.csv"))
    assert len(files) == 1
    d = pd.read_csv(files[0])
    assert len(d) == 2 * 4 and set(d["capture"]) == {"scout_sweep"}
    assert set(d["league"]) == {"Reg"} and set(d[d["af_fixture_id"] == 1002]["home_team"]) == {"X"}
    assert set(d["market"]) == {"corners_ou_match", "corners_ou_home", "cards_ou_match"}
    assert "[side_odds] +8 row(s)" in out and "1.85" not in out


def _near(tmp_path, monkeypatch, store, now):
    seed = pd.DataFrame([{"fixture_id": 1001, "league_id": 7, "kickoff_ts": now + 1800, "market": "ou25",
                          "selection": "over", "bookmaker": "bet365", "odds": 2.0,
                          "snapshot_ts": "2026-01-01T00:00:00Z", "minutes_to_kickoff": 30.0,
                          "quality_flags": ""}])
    monkeypatch.setattr(collect, "_read_recent", lambda t, d: seed)
    monkeypatch.setattr(collect, "_league_seasons", lambda: {})
    monkeypatch.setattr(SS, "base_dir", lambda: tmp_path / "specials")
    SS._STATE.clear(); SO._STATE.clear()
    if store is None:
        monkeypatch.delenv(SO.ENV, raising=False)
    else:
        monkeypatch.setenv(SO.ENV, str(store))
    calls, written = [], []

    class C:
        calls = 0
        remaining = 99999

        def get(self, endpoint, params):
            calls.append((endpoint, params["fixture"]))
            return {"response": [_entry(1001, pd.Timestamp(now + 1800, unit="s", tz="UTC"))]}
    monkeypatch.setattr(collect, "_append", lambda t, rows, tag, dry: written.append(pd.DataFrame(rows)) or len(rows))
    monkeypatch.setattr(collect.time, "sleep", lambda s: None)
    t0 = [now]
    monkeypatch.setattr(collect.time, "time", lambda: (t0.__setitem__(0, t0[0] + 400), t0[0])[1])
    return calls, written, collect.near_loop(C(), minutes=10, dry=False)


def test_near_zero_extra_calls_outputs_unchanged(tmp_path, monkeypatch):
    store = _store(tmp_path)
    calls_on, w_on, o_on = _near(tmp_path / "on", monkeypatch, store, NOW_S)
    monkeypatch.undo()
    calls_off, w_off, o_off = _near(tmp_path / "off", monkeypatch, None, NOW_S)
    assert calls_on == calls_off and len(calls_on) >= 1
    assert len(w_on) == len(w_off)
    for a, b in zip(w_on, w_off):
        pd.testing.assert_frame_equal(_norm(a), _norm(b))
    assert o_on == o_off
    d = pd.concat(pd.read_csv(f) for f in (store / "data").rglob("*_near.csv"))
    assert set(d["capture"]) == {"scout_near"} and set(d["bet_id"]) == {45, 57, 80}


def test_nothing_written_without_the_private_store(tmp_path, monkeypatch):
    _sweep(tmp_path, monkeypatch, None, NOW_S)
    assert not any("corners_ou" in f.read_text(encoding="utf-8") or "Corners" in f.read_text(encoding="utf-8")
                   for f in tmp_path.rglob("*.csv"))


def test_workflows_gate_and_push_the_private_store():
    for wf, prod in (("pro_scout.yml", "sweep"), ("pro_scout_near.yml", "near")):
        t = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert t.count("vars.SIDE_ODDS_ENABLED == 'true'") == 2
        assert "bash .github/scripts/side_odds_store.sh open" in t
        assert f"bash .github/scripts/side_odds_store.sh push {prod}" in t
        assert "side_odds" not in t.split("- name: Commit")[1].split("Push corners/cards")[0]


# ── team cards (audit G6a) ───────────────────────────────────────────────────────────────────────

def _fx():
    return {"fixture": {"id": 5, "date": "2026-11-15T15:00:00+00:00"}, "league": {"season": 2026},
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}}, "goals": {"home": 1, "away": 0}}


def test_team_cards_follow_the_owner_null_rule():
    home = {"statistics": [{"type": "Yellow Cards", "value": 3}, {"type": "Red Cards", "value": None},
                           {"type": "Corner Kicks", "value": 6}]}
    away = {"statistics": [{"type": "Yellow Cards", "value": None}, {"type": "Red Cards", "value": 1},
                           {"type": "Corner Kicks", "value": None}]}
    r = TS._parse_stats(_fx(), [home, away], "Championship", "2026-11-16T04:35:00Z")
    assert (r["home_yellow"], r["home_red"], r["away_yellow"], r["away_red"]) == (3.0, 0.0, 0.0, 1.0)
    assert r["fetched_at"] == "2026-11-16T04:35:00Z"
    assert pd.isna(r["away_corners"])                  # existing columns keep their reading


def test_team_cards_missing_when_not_answered_or_not_listed():
    empty = {"statistics": [{"type": "Yellow Cards", "value": None}, {"type": "Red Cards", "value": None}]}
    unlisted = {"statistics": [{"type": "Corner Kicks", "value": 4}]}
    r = TS._parse_stats(_fx(), [empty, unlisted], "Championship")
    assert all(pd.isna(r[c]) for c in ("home_yellow", "home_red", "away_yellow", "away_red"))
    assert r["fetched_at"] is None                     # a cached answer: fetch time unknown, not guessed

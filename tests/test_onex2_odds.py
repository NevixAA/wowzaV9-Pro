"""1X2 price collection for K League 1, Romania Liga I and the Saudi Pro League (owner 2026-11-09)."""
import importlib
import json
import time

import pandas as pd

from src.scout import collect, parse


def _fx(lid, fid, ko, home="A", away="B", books=(("Pinnacle", 2.1, 3.4, 3.6), ("Bet365", 2.0, 3.3, 3.7))):
    return {"fixture": {"id": fid, "timestamp": ko}, "league": {"id": lid},
            "bookmakers": [{"name": n, "bets": [
                {"name": "Match Winner", "values": [{"value": "Home", "odd": str(h)},
                                                    {"value": "Draw", "odd": str(d)},
                                                    {"value": "Away", "odd": str(a)}]},
                {"name": "Goals Over/Under", "values": [{"value": "Over 2.5", "odd": "1.9"},
                                                        {"value": "Under 2.5", "odd": "1.9"}]}]}
                for n, h, d, a in books]}


def test_1x2_is_kept_only_for_the_configured_leagues():
    now = 1_000_000
    resp = [_fx(283, 1, now + 3600), _fx(39, 2, now + 3600)]
    rows = parse.odds_rows(resp, "2026-11-09T12:00:00Z", now, frozenset({283}))
    x = pd.DataFrame(rows)
    one = x[x["market"] == "1x2"]
    assert set(one["fixture_id"]) == {1}                              # league 39 never gets 1X2
    assert set(one["selection"]) == {"home", "draw", "away"}
    assert set(one["bookmaker"]) == {"pinnacle", "bet365", "median"}
    med = one[(one["bookmaker"] == "median") & (one["selection"] == "home")].iloc[0]
    assert med["odds"] == 2.05 and med["n_books"] == 2
    assert (x[x["fixture_id"] == 2]["market"] == "ou25").all()       # other markets unchanged
    assert parse.odds_rows(resp, "t", now) == [r for r in parse.odds_rows(resp, "t", now)
                                               if r["market"] != "1x2"]  # default: no 1X2 at all


def test_a_kicked_off_fixture_never_yields_a_1x2_price():
    now = 1_000_000
    assert parse.odds_rows([_fx(283, 1, now - 60)], "t", now, frozenset({283})) == []


def test_config_names_the_three_leagues_and_only_romania_is_called_per_fixture():
    ox = collect.onex2_leagues()
    assert ox["all"] == frozenset({292, 283, 307}) and ox["first_sight"] == frozenset({283})
    assert ox["retry_h"] == 12.0


class _FakeClient:
    def __init__(self, answers):
        self.answers, self.asked, self.calls, self.remaining = answers, [], 0, 70000

    def get(self, endpoint, params):
        assert endpoint == "/odds"
        self.asked.append(params["fixture"])
        self.calls += 1
        return {"response": self.answers.get(params["fixture"], [])}


def test_first_sight_calls_only_unpriced_upcoming_fixtures_and_respects_the_retry_journal(
        monkeypatch, tmp_path):
    now = int(time.time())
    fx = pd.DataFrame({"fixture_id": [10, 11, 12, 13, 14],
                       "league_id": [283, 283, 283, 283, 39],
                       "kickoff_ts": [now + 2 * 86400, now + 3 * 86400, now + 86400, now + 9 * 86400,
                                      now + 2 * 86400],
                       "status": ["NS"] * 5})
    appended = []
    # the store: 12 priced before this test, plus whatever the step itself appends
    monkeypatch.setattr(collect, "_read_recent", lambda t, d: pd.DataFrame(
        {"fixture_id": [12] + [r["fixture_id"] for r in appended]}))
    monkeypatch.setattr(collect, "_append", lambda t, rows, tag, dry: appended.extend(rows) or len(rows))
    monkeypatch.setattr(collect, "ONEX2_JOURNAL", tmp_path / "j.json")
    monkeypatch.setattr(collect, "OUT", tmp_path)
    ox = {"all": frozenset({283, 292, 307}), "first_sight": frozenset({283}), "retry_h": 12.0}
    c = _FakeClient({10: [_fx(283, 10, now + 2 * 86400)]})            # 11: odds not published yet
    s = {}
    assert collect.step_onex2_first_sight(c, fx, ox, False, s, now=now) == 2
    assert sorted(c.asked) == [10, 11]                               # not 12 (priced), 13 (>7d), 14 (league)
    assert s == {"onex2_first_sight_calls": 2, "onex2_first_sight_empty": 1}
    assert {r["market"] for r in appended} >= {"1x2"}
    c2 = _FakeClient({})
    assert collect.step_onex2_first_sight(c2, fx, ox, False, {}, now=now + 3600) == 0  # within 12h
    c3 = _FakeClient({})
    assert collect.step_onex2_first_sight(c3, fx, ox, False, {}, now=now + 13 * 3600) == 1
    assert c3.asked == [11]                                          # 10 is priced now; 11 retried
    assert json.loads((tmp_path / "j.json").read_text(encoding="utf-8"))


def test_the_scout_stops_at_the_owners_25k_floor(monkeypatch):
    from src.scout import af
    monkeypatch.delenv("SCOUT_MIN_QUOTA", raising=False)
    importlib.reload(af)
    assert af.MIN_QUOTA == 25_000


def test_romania_closing_benchmark_is_parsed_closing_only():
    from src.pipelines import onex2_v9_bridge as B
    df = pd.DataFrame({"Date": ["02/11/2026", "03/11/2026", "04/11/2026"],
                       "Home": ["FCSB", "CFR Cluj", "Rapid"], "Away": ["Dinamo", "U Cluj", "Petrolul"],
                       "AvgCH": [1.8, None, 2.2], "AvgCD": [3.6, None, 3.2], "AvgCA": [4.5, None, 3.3],
                       "PSCH": [1.85, 2.1, None], "PSCD": [3.7, 3.3, None], "PSCA": [4.6, 3.5, None],
                       "AvgH": [9.0, 9.0, 9.0]})                     # an entry column is never read
    r = B.newfmt_close_rows(df)
    assert [x["book"] for x in r] == ["AvgC", "PSC", "AvgC"]
    assert r[1]["o"] == [2.1, 3.3, 3.5] and r[0]["date"] == pd.Timestamp("2026-11-02")
    assert B.newfmt_close_rows(pd.DataFrame({"Date": ["x"]})) == []


def test_a_fixture_without_a_kickoff_stays_missing_not_epoch_zero():
    r = parse.fixture_rows([{"fixture": {"id": 5, "status": {"short": "NS"}}, "league": {"id": 283, "season": 2026},
                             "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
                             "goals": {}}])[0]
    assert r["kickoff_ts"] is None and r["quality_flags"] == "MISSING_KICKOFF"

"""League scout Data Truth (audit 2026-11-10, findings R1-R15): every rule is pinned, and every
promotion data-quality check is shown to be ABLE TO FAIL.

    python -m pytest tests/test_scout_data_truth.py -q
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import pro_config as cfg  # noqa: E402
from src.scout import collect, model, parse, promotion as P, report, truth as T  # noqa: E402

NOW = pd.Timestamp("2026-11-10T12:00:00Z")
LID = 4242


# ── a clean synthetic league ──────────────────────────────────────────────────────────────────
def league(n=200, lid=LID, seed=0, close_min=30.0):
    """n fixtures, one every 12 h up to two days ago, 12 teams, Pinnacle closes `close_min` before
    kickoff, a frozen model a day before, all identities consistent."""
    rng = np.random.default_rng(seed)
    end = (NOW - pd.Timedelta(days=2)).timestamp()
    ko = end - np.arange(n)[::-1] * 43200.0
    home = rng.integers(1, 13, n)
    away = home % 12 + 1
    hg, ag = rng.poisson(1.4, n), rng.poisson(1.1, n)
    fid = np.arange(n) + lid * 10_000
    res = pd.DataFrame({"fixture_id": fid, "league_id": lid, "season": "2026", "kickoff_ts": ko,
                        "home_id": home, "away_id": away, "home_team": [f"T{h}" for h in home],
                        "away_team": [f"T{a}" for a in away], "home_goals": hg, "away_goals": ag,
                        "status": "FT", "ingested_at": "2026-11-01T00:00:00Z"})
    rows = []
    for i in range(n):
        p = float(np.clip(rng.uniform(0.35, 0.65), 0.05, 0.95))
        for m, (a, b) in T.SIDE.items():
            for sel, q in ((a, p), (b, 1 - p)):
                rows.append({"fixture_id": int(fid[i]), "league_id": lid, "market": m, "selection": sel,
                             "bookmaker": "pinnacle", "odds": round(1 / (q * 1.02), 3), "n_books": None,
                             "kickoff_ts": ko[i], "quality_flags": "", "minutes_to_kickoff": close_min,
                             "snapshot_ts": pd.Timestamp(ko[i] - close_min * 60, unit="s", tz="UTC").isoformat()})
    mdl = pd.DataFrame({"fixture_id": fid, "league_id": lid, "home_id": home, "away_id": away, "kickoff_ts": ko,
                        "home_games": 20, "away_games": 20, "quality_flags": "",
                        "frozen_ts": [pd.Timestamp(k - 86400, unit="s", tz="UTC").isoformat() for k in ko],
                        "p_ou15_over": 0.75, "p_ou25_over": 0.5, "p_ou35_over": 0.3, "p_btts_yes": 0.5})
    return res, pd.DataFrame(rows), mdl


def dq(res, odds, mdl, ft90=None, status=None):
    return P.data_quality(LID, res, odds, mdl, ft90, status, now=NOW)


# ── R1 v9 leagues by id, fail closed ─────────────────────────────────────────────────────────
def test_v9_ids_read_from_leagues_json_and_block_when_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "V9_LOCAL", tmp_path)
    assert P.v9_league_ids() is None                                   # missing -> None -> gate blocks
    (tmp_path / "config").mkdir()
    recs = [{"name": f"L{i}", "api_football_id": 100 + i, "enabled": i % 2 == 0} for i in range(30)]
    (tmp_path / "config" / "leagues.json").write_text(json.dumps({"leagues": recs}), encoding="utf-8")
    assert P.v9_league_ids() == {100 + i for i in range(30)}
    (tmp_path / "config" / "leagues.json").write_text(json.dumps({"leagues": recs[:3]}), encoding="utf-8")
    assert P.v9_league_ids() is None                                   # implausibly small -> blocks


def test_watch_list_holds_no_v9_enabled_league():
    w = json.loads((ROOT / "registry" / "scout_leagues.json").read_text(encoding="utf-8"))
    ids = {x["id"] for x in w["leagues"]}
    assert 62 not in ids and {x["id"] for x in w["removed_v9_enabled"]} == {62}
    f = cfg.V9_LOCAL / "config" / "leagues.json"
    if f.exists():
        lg = json.loads(f.read_text(encoding="utf-8"))["leagues"]
        recs = lg.values() if isinstance(lg, dict) else lg
        enabled = {int(x["api_football_id"]) for x in recs if x.get("enabled") and x.get("api_football_id")}
        assert not ids & enabled


# ── R2 every data-quality check can fail ──────────────────────────────────────────────────────
def test_clean_league_passes():
    d = dq(*league())
    assert d["verdict"] == "PASS", d["critical"]


def test_conflicting_duplicate_results_fail():
    res, odds, mdl = league()
    bad = pd.concat([res, res.head(3).assign(home_goals=lambda x: x["home_goals"] + 1)])
    assert "duplicate fixtures with conflicting content" in dq(bad, odds, mdl)["critical"]
    same = pd.concat([res, res.head(3)])                               # identical copies: counted, served once
    d = dq(same, odds, mdl)
    assert d["duplicate_fixtures"] == 3 and d["verdict"] == "PASS"


def test_unexplained_missing_results_fail_and_a_reason_explains_them():
    res, odds, mdl = league()
    gone = res.head(10)["fixture_id"]
    cut = res[~res["fixture_id"].isin(gone)]
    d = dq(cut, odds, mdl)
    assert d["due_without_result_unexplained"] == 10 and any("no recorded reason" in c for c in d["critical"])
    st = pd.DataFrame({"fixture_id": gone, "league_id": LID, "status": "PST"})
    assert dq(cut, odds, mdl, status=st)["due_without_result_unexplained"] == 0


def test_missing_90_minute_scores_fail():
    res, odds, mdl = league()
    res.loc[res.index[:10], "status"] = "AET"                          # old rows: no goals_basis
    d = dq(res, odds, mdl)
    assert d["aet_pen_missing_90"] == 10 and any("90-minute" in c for c in d["critical"])


def test_conflicting_odds_fail():
    res, odds, mdl = league()
    dup = odds[odds["fixture_id"].isin(res["fixture_id"].head(10))].assign(odds=lambda x: x["odds"] + 0.05)
    d = dq(res, pd.concat([odds, dup]), mdl)
    assert d["odds_conflict_fixtures"] == 10 and any("conflicting duplicate quotes" in c for c in d["critical"])


def test_reschedules_fail_and_are_void():
    res, odds, mdl = league()
    moved = res["fixture_id"].head(10)
    mdl.loc[mdl["fixture_id"].isin(moved), "kickoff_ts"] -= 3 * 86400  # priced/frozen 3 days earlier
    d = dq(res, odds, mdl)
    assert d["rescheduled_void"] == 10 and any("moved >" in c for c in d["critical"])
    s = T.settled(res, odds, mdl)
    assert not s["fixture_id"].isin(moved).any()


def test_team_id_mismatch_fails_and_is_never_scored():
    res, odds, mdl = league()
    ids = res["fixture_id"].head(10)
    mdl.loc[mdl["fixture_id"].isin(ids), "home_id"] = 999
    d = dq(res, odds, mdl)
    assert d["team_id_mismatches"] == 10 and any("teams" in c for c in d["critical"])
    s = T.settled(res, odds, mdl)
    assert s[s["fixture_id"].isin(ids)]["p_model"].isna().all()


def test_frozen_after_actual_kickoff_fails():
    res, odds, mdl = league()
    late = res.head(1)
    mdl.loc[mdl["fixture_id"].isin(late["fixture_id"]), "frozen_ts"] = \
        pd.Timestamp(late["kickoff_ts"].iloc[0] + 60, unit="s", tz="UTC").isoformat()
    assert "model frozen after the actual kickoff" in dq(res, odds, mdl)["critical"]


def test_stale_closes_fail():
    res, odds, mdl = league(close_min=240.0)                           # every "close" 4 h old
    d = dq(res, odds, mdl)
    assert d["stale_or_thin_close"] == d["settled_priced"] > 0
    assert any("genuine close" in c for c in d["critical"])


# ── R3 statuses recorded, backfill by id ─────────────────────────────────────────────────────
def _fx(fid, status, goals=(None, None), ft=(None, None), et=(None, None), ko=1_700_000_000):
    return {"fixture": {"id": fid, "timestamp": ko, "date": "2023-11-14T22:13:20+00:00",
                        "status": {"short": status, "long": status}},
            "league": {"id": LID, "season": 2023, "round": "R1"},
            "teams": {"home": {"id": 1, "name": " Home FC"}, "away": {"id": 2, "name": "Away\t"}},
            "goals": {"home": goals[0], "away": goals[1]},
            "score": {"halftime": {"home": 0, "away": 0}, "fulltime": {"home": ft[0], "away": ft[1]},
                      "extratime": {"home": et[0], "away": et[1]}, "penalty": {"home": None, "away": None}}}


def test_backfill_by_id_records_results_reasons_and_90_minute_scores(monkeypatch):
    raw = pd.DataFrame({"fixture_id": [1], "league_id": [LID], "status": ["AET"], "home_goals": [3.0],
                        "away_goals": [2.0], "kickoff_ts": [1_700_000_000], "home_id": [1], "away_id": [2],
                        "home_team": ["Home FC"], "away_team": ["Away"], "ingested_at": ["2026-11-01T00:00:00Z"]})
    odds = pd.DataFrame({"fixture_id": [2, 3, 4], "kickoff_ts": [1_700_000_000] * 3})
    tables = {"scout_results": raw, "scout_odds": odds, "scout_model": pd.DataFrame(),
              "scout_results_ft90": pd.DataFrame(), "scout_fixture_status": pd.DataFrame()}
    monkeypatch.setattr(collect.store, "read", lambda t, *a, **k: tables.get(t, pd.DataFrame()))
    written = {}
    monkeypatch.setattr(collect, "_append",
                        lambda t, rows, tag, dry: written.setdefault(t, []).extend(
                            rows.to_dict("records") if isinstance(rows, pd.DataFrame) else rows) or len(rows))
    asked = []

    class C:
        calls, remaining = 0, 99999

        def get(self, endpoint, params):
            asked.append(params["ids"])
            return {"response": [_fx(1, "AET", goals=(3, 2), ft=(2, 2), et=(1, 0)),
                                 _fx(2, "FT", goals=(1, 0)), _fx(3, "PST")]}
    used = collect.step_backfill(C(), budget=5, dry=False)
    assert used == 1 and asked == ["1-2-3-4"]
    assert [r["fixture_id"] for r in written["scout_results"]] == [2]          # 1 is stored already
    f9 = written["scout_results_ft90"][0]
    assert (f9["ft90_home"], f9["ft90_away"], f9["goals_home_api"]) == (2, 2, 3)
    assert f9["et_check"] == "goals_eq_ft90_plus_et" and f9["goals_include_extra_time"] is True
    st = {r["fixture_id"]: r["status"] for r in written["scout_fixture_status"]}
    assert st == {3: "PST", 4: "NOT_RETURNED"}
    served = T.results(raw, pd.DataFrame(written["scout_results_ft90"]))
    assert served.iloc[0][["home_goals", "away_goals"]].tolist() == [2, 2]       # 90 minutes, not 3-2


def test_backfill_stops_at_its_budget(monkeypatch):
    odds = pd.DataFrame({"fixture_id": list(range(100, 160)), "kickoff_ts": [1_700_000_000] * 60})
    tables = {"scout_odds": odds}
    monkeypatch.setattr(collect.store, "read", lambda t, *a, **k: tables.get(t, pd.DataFrame()))
    monkeypatch.setattr(collect, "_append", lambda t, rows, tag, dry: 0)

    class C:
        calls, remaining, n = 0, 99999, 0

        def get(self, endpoint, params):
            C.n += 1
            return {"response": []}
    assert collect.step_backfill(C(), budget=2, dry=True) == 2 and C.n == 2


def test_step_history_skips_stored_fixtures(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "HISTORY_DONE", tmp_path / "done.json")
    monkeypatch.setattr(collect, "_stored_result_ids", lambda: {1})
    got = []
    monkeypatch.setattr(collect, "_append", lambda t, rows, tag, dry: got.extend(rows) or len(rows))

    class C:
        calls, remaining = 0, 99999

        def get(self, endpoint, params):
            return {"response": [{"league": {"id": LID}, "seasons": [{"year": 2026, "current": True}]}]}

        def get_all_pages(self, endpoint, params):
            return [_fx(1, "FT", goals=(1, 0)), _fx(5, "FT", goals=(2, 2))]
    collect.step_history(C(), [{"id": LID}], budget=5, dry=True)
    assert [r["fixture_id"] for r in got] == [5]


# ── R4 / R10 / R14 parsing ───────────────────────────────────────────────────────────────────
def test_extra_time_takes_the_90_minute_score_or_stays_missing():
    r = parse.fixture_rows([_fx(1, "AET", goals=(3, 2), ft=(2, 2), et=(1, 0))])[0]
    assert (r["home_goals"], r["away_goals"], r["goals_basis"]) == (2, 2, "fulltime_90")
    assert (r["goals_home_api"], r["goals_away_api"]) == (3, 2)
    m = parse.fixture_rows([_fx(1, "PEN", goals=(1, 1))])[0]            # no score.fulltime
    assert m["home_goals"] is None and m["goals_basis"] == "missing_90"
    ft = parse.fixture_rows([_fx(1, "FT", goals=(1, 0))])[0]
    assert (ft["home_goals"], ft["goals_basis"]) == (1, "goals")


def test_missing_kickoff_stays_missing_and_names_are_trimmed():
    e = _fx(1, "NS")
    e["fixture"]["timestamp"] = None
    r = parse.fixture_rows([e])[0]
    assert r["kickoff_ts"] is None and r["quality_flags"] == "MISSING_KICKOFF"
    assert (r["home_team"], r["away_team"]) == ("Home FC", "Away")


def test_old_aet_rows_are_served_missing_without_a_correction():
    raw = pd.DataFrame({"fixture_id": [1, 2], "league_id": LID, "status": ["AET", "FT"], "home_goals": [3, 1],
                        "away_goals": [2, 0], "kickoff_ts": [1, 2], "home_id": 1, "away_id": 2,
                        "home_team": "A", "away_team": "B"})
    s = T.results(raw).set_index("fixture_id")
    assert pd.isna(s.loc[1, "home_goals"]) and s.loc[1, "goals_basis"] == "missing_90"
    assert s.loc[1, "goals_home_api"] == 3 and s.loc[2, "home_goals"] == 1


def test_latest_provider_name_per_team_id_trimmed():
    raw = pd.DataFrame({"fixture_id": [1, 2], "league_id": LID, "kickoff_ts": [1, 2], "home_id": [7, 7],
                        "away_id": [8, 8], "home_team": ["Preussen Munster", " Preußen Münster "],
                        "away_team": ["X", "X"], "home_goals": 1, "away_goals": 0, "status": "FT"})
    assert set(T.results(raw)["home_team"]) == {"Preußen Münster"}


# ── R5 / R6 one match, one row ───────────────────────────────────────────────────────────────
def _odds_answer(fid, books, ko=2_000_000_000):
    return {"league": {"id": LID}, "fixture": {"id": fid, "timestamp": ko},
            "bookmakers": [{"id": i, "name": n, "bets": [{"name": "Goals Over/Under", "values": [
                {"value": "Over 2.5", "odd": str(o)}, {"value": "Under 2.5", "odd": "1.9"}]}]}
                for i, (n, o) in enumerate(books)]}


def test_a_fixture_twice_in_one_answer_gives_one_median():
    a = _odds_answer(1, [("Pinnacle", 2.0), ("Bet365", 2.1), ("1xBet", 2.2)])
    rows = parse.odds_rows([a, a], "ts", 1_000)
    meds = [r for r in rows if r["bookmaker"] == "median" and r["selection"] == "over"]
    assert len(meds) == 1 and meds[0]["n_books"] == 3
    b = _odds_answer(1, [("Pinnacle", 2.05), ("Bet365", 2.1), ("1xBet", 2.2)])
    rows = parse.odds_rows([a, b], "ts", 1_000)                        # Pinnacle quotes two prices: dropped
    assert not [r for r in rows if r["bookmaker"] == "pinnacle" and r["selection"] == "over"]
    assert [r["n_books"] for r in rows if r["bookmaker"] == "median" and r["selection"] == "over"] == [2]
    assert len({tuple(r[c] for c in parse.ODDS_KEY) for r in rows}) == len(rows)


def test_unique_odds_before_append():
    r = {"fixture_id": 1, "market": "ou25", "selection": "over", "bookmaker": "median", "snapshot_ts": "t", "odds": 2.0}
    assert len(parse.unique_odds([r, dict(r)])) == 1
    assert parse.unique_odds([r, {**r, "odds": 2.1}]) == []


# ── R7 / R8 / R9 / R11 evaluation ────────────────────────────────────────────────────────────
def test_close_is_measured_against_the_actual_kickoff():
    res, odds, mdl = league(n=20)
    res = res.assign(kickoff_ts=res["kickoff_ts"] + 7200)              # kicked off 2 h later than priced
    s = T.settled(res, odds, mdl)
    assert s.empty                                                     # the 30-min quote is 150 min old now


def test_degraded_and_unknown_team_rows_are_never_scored():
    res, odds, mdl = league(n=20)
    mdl.loc[mdl.index[:5], "quality_flags"] = "FEATURE_DEGRADED"
    mdl.loc[mdl.index[5:8], "quality_flags"] = model.UNKNOWN_TEAM
    mdl.loc[mdl.index[8:10], "home_games"] = 0                         # pre-fix 1.0 stand-in rows
    s = T.settled(res, odds, mdl)
    scored = set(s[s["p_model"].notna()]["fixture_id"])
    assert scored == set(mdl["fixture_id"].iloc[10:])


def test_base_rate_uses_only_earlier_results():
    r = pd.DataFrame({"league_id": LID, "kickoff_ts": [1, 2, 3, 4], "home_goals": [3, 0, 3, 3],
                      "away_goals": [0, 0, 0, 0]})
    b = T.base_rate_before(r, LID, "ou25", pd.Series([1, 2, 3, 5]))
    assert np.isnan(b.iloc[0]) and b.iloc[1] == 1.0 and b.iloc[2] == 0.5 and b.iloc[3] == 0.75


def test_paper_price_older_than_the_close_limit_is_not_a_bet_price():
    when = pd.DataFrame({"fixture_id": [1], "frozen_ts": ["2026-01-01T12:00:00Z"]})
    o = pd.DataFrame({"fixture_id": [1, 1], "market": "ou25", "selection": ["over", "under"], "bookmaker": "bet365",
                      "odds": [2.0, 1.8], "snapshot_ts": ["2026-01-01T09:00:00Z", "2026-01-01T11:30:00Z"]})
    lim = T.close_max_minutes()
    got = report.asof(o, when, lim)
    assert list(got["selection"]) == ["under"]                         # the 3 h old over price is dropped
    assert len(report.asof(o, when)) == 2


def test_close_limit_is_the_hypotheses_rule():
    from src.scout.hypotheses import CRITERIA
    assert T.close_max_minutes() == CRITERIA["genuine_close"]["max_minutes_before_kickoff"] == 60


# ── R12 harness never fills ──────────────────────────────────────────────────────────────────
def test_harness_refuses_missing_features():
    from src.scout import regression_harness as RH
    X = pd.DataFrame({"a": [1.0, np.nan, 2.0] * 20, "b": [0.0, 1.0, 2.0] * 20})
    with pytest.raises(ValueError):
        RH._fit_predict(X, np.array([0, 1, 0] * 20), X)
    src = Path(RH.__file__).read_text(encoding="utf-8")
    assert ".fillna(med)" not in src and "rows_dropped_missing_features" in src


# ── R13 research gates are never staking bars ────────────────────────────────────────────────
def test_research_gates_are_marked_and_unread_by_betting_code():
    from src.scout import hypotheses as H
    assert report.RESEARCH_GATE_ONLY and H.RESEARCH_GATE_ONLY and P.RESEARCH_GATE_ONLY
    bad = []
    for f in (ROOT / "src").rglob("*.py"):
        rel = f.relative_to(ROOT).as_posix()
        if rel.startswith("src/scout/"):
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"(from|import)\s+src\.scout\b|src\.scout\.(report|hypotheses|promotion)", txt):
            bad.append(rel)
        if rel.startswith(("src/bankroll/", "src/betting/", "src/price_trader/")) and \
                re.search(r"\b(EDGE_BAR|MAX_DEFECT_SHARE|POOLED_MARGIN)\b|scout", txt):
            bad.append(rel)
    assert bad == [], f"research gates must never reach staking / betting code: {bad}"


# ── R15 coverage and staleness ───────────────────────────────────────────────────────────────
def test_health_flags_stale_and_no_odds_offered(monkeypatch):
    res, odds, mdl = league(n=40)
    other = res.assign(league_id=LID + 1, fixture_id=res["fixture_id"] + 500_000)
    old = odds.assign(snapshot_ts="2026-10-01T00:00:00Z")              # league priced, then nothing for weeks
    monkeypatch.setattr(report.reg, "load", lambda: [
        {"id": LID, "country": "X", "name": "Fresh", "priority": 1},
        {"id": LID + 1, "country": "Y", "name": "Dark", "priority": 2}])
    runs = pd.DataFrame([{"collector": "scout_sweep", "detail": {"leagues_polled": {str(LID + 1): 0},
                                                                "leagues_empty": [str(LID + 1)]}}])
    h = report.health((pd.concat([res, other]), pd.concat([odds, old.head(0)]), mdl, pd.DataFrame(), pd.DataFrame()),
                      now=NOW, runs=runs)
    lines = {x["league_id"]: x for x in h["leagues"]}
    assert lines[LID + 1]["stale"] and lines[LID + 1]["odds_offered"] == "NO_ODDS_OFFERED"
    assert "NO_ODDS_CAPTURED" in lines[LID + 1]["flags"]
    assert not lines[LID]["stale"] and lines[LID]["odds_offered"] == "OFFERED"
    assert h["stale_leagues"] == [LID + 1] and h["no_odds_offered"] == [LID + 1]

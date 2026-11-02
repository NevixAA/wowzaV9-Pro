"""Data Truth round 3 (Pro, 2026-11-02): one focused test per finding; each failed on the code at
origin/data-truth-100 4410959d before its fix."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

NOW = dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.timezone.utc)


# ── Bet Builder: symmetric score fit -> side legs on the record are INVALID_MODEL ──────────────
def test_score_fit_is_home_away_symmetric_and_side_legs_are_marked_invalid():
    from src.combo import record_audit as ra
    from src.combo import score_model as sm
    t = {"O15": 0.75, "O25": 0.52, "O35": 0.28, "BTTS": 0.50}
    a, b = sm.score_matrix(1.6, 0.9, -0.05), sm.score_matrix(0.9, 1.6, -0.05)
    # every fit target is identical under the swap -> the fit cannot tell which side is stronger
    for k in t:
        assert sm.prob(a, k) == pytest.approx(sm.prob(b, k))
    assert sm.prob(a, "HOME") != pytest.approx(sm.prob(b, "HOME"))
    rec = pd.DataFrame({"leg1_market": ["HOME", "O25"], "leg2_market": ["player_goals", "player_sot"],
                        "leg1_p": [0.5, 0.5], "leg2_p": [0.4, 0.4], "joint_probability": [0.2, 0.2],
                        "combo_result": ["WON", "WON"],
                        "leg_results": ["HOME=WON | player_goals=WON", "O25=WON | player_sot=WON"]})
    out = ra.annotate(rec)
    assert list(out["model_validity"]) == ["INVALID_MODEL", "OK"]
    assert list(out["scoreboard_result"]) == [ra.EXCLUDED_INVALID_MODEL, "WON"]
    assert list(out["combo_result"]) == ["WON", "WON"]               # original kept beside


# ── Bet Builder: a combo WON on its remaining legs is not a headline win ────────────────────────
def test_performance_does_not_count_void_leg_combos_as_wins():
    from src.combo import settle as cs
    rec = pd.DataFrame({"leg1_market": ["O25", "O25"], "leg2_market": ["player_goals", "player_goals"],
                        "leg1_p": [0.5, 0.5], "leg2_p": [0.4, 0.4], "joint_probability": [0.25, 0.25],
                        "fair_odds": [4.0, 4.0], "combo_result": ["WON", "LOST"],
                        "leg_results": ["O25=WON | player_goals=VOID", "O25=LOST | player_goals=WON"]})
    p = cs.performance(rec)
    assert p["won"] == 0 and p["lost"] == 1 and p["settled"] == 1
    assert p["excluded_void_leg_won"] == 1
    assert p["pnl_at_fair_odds"] == -1.0


# ── Bet Builder: a joint above its smaller leg is refused (Frechet) ─────────────────────────────
def test_joint_outside_frechet_bound_is_refused():
    from src.combo import match_picture as mp
    from src.combo import score_model as sm
    m = sm.fit({"O15": 0.75, "O25": 0.52, "O35": 0.28, "BTTS": 0.50})["matrix"]
    g = mp.goal_legs(m, ["O15", "O25", "O35", "BTTS"])["O25"]
    goal = {"kind": "goal", "key": "O25", "p": g[0], "mask": g[1], "label": g[2]}
    pl = {"kind": "player", "player": "A", "market": "sot", "p": 0.90, "label": "A 1+ SOT"}
    pj, src, _ = mp._joint([goal, pl], m, {("sot", "O25"): 1.45})      # 0.52*0.9*1.45 > 0.52
    assert pj is None and src == "OUTSIDE_FRECHET_BOUND"
    pj, src, _ = mp._joint([goal, pl], m, {("sot", "O25"): 1.05})
    assert src == "SCORE_MATRIX_PLUS_MEASURED_DEPENDENCE" and pj <= min(g[0], 0.9)


def test_record_marks_frechet_violations_beside_the_record():
    from src.combo import record_audit as ra
    rec = pd.DataFrame({"leg1_market": ["O25"], "leg2_market": ["player_sot"], "leg1_p": [0.52],
                        "leg2_p": [0.9], "joint_probability": [0.68], "combo_result": ["LOST"],
                        "leg_results": ["O25=LOST | player_sot=WON"]})
    out = ra.annotate(rec)
    assert bool(out["frechet_violation"].iloc[0]) and out["joint_probability"].iloc[0] == 0.68
    assert out["scoreboard_result"].iloc[0] == ra.EXCLUDED_FRECHET


def test_tip_scoreboard_finds_sent_combos_after_fixture_key_rekey(monkeypatch):
    from src.data import v9_config
    from src.pipelines import tip_scoreboard as t
    monkeypatch.setattr(v9_config, "is_paper", lambda lg: False)
    rows = [{"combo_id": f"new{i}", "old_combo_id": f"old{i}", "league": "L", "joint_probability": 0.2,
             "combo_result": r, "leg_results": "O25=WON | player_goals=WON", "n_legs": 2,
             "settle_note": "OK:FIXTURE_KEY",
             "leg1_market": m, "leg2_market": "player_goals", "leg1_p": 0.5, "leg2_p": 0.4}
            for i, (r, m) in enumerate([("WON", "O25"), ("LOST", "O25"), ("LOST", "AWAY")])]
    b = t.bet_builder(pd.DataFrame(rows), {"old0": {}, "old1": {}, "old2": {}})
    assert b["found_in_settled"] == 3
    assert b["headline"]["settled"] == 2 and b["headline"]["won"] == 1
    assert b["invalid_model_or_frechet"]["settled"] == 1


# ── Bet Builder: the daily selection never offers a match that has kicked off ──────────────────
def _combo_row(kickoff: str, match_date: str, cid: str) -> dict:
    return {"combo_id": cid, "fixture_key": cid, "match": f"A{cid} vs B{cid}", "match_date": match_date,
            "kickoff_utc": kickoff, "n_legs": 2, "leg1_market": "O25", "leg1_label": "Over 2.5",
            "leg1_p": 0.5, "leg2_market": "player_goals", "leg2_label": "X to score", "leg2_p": 0.4,
            "joint_probability": 0.30, "independence_probability": 0.20, "fair_odds": 3.33}


def test_daily_selection_drops_started_matches(monkeypatch):
    from src.combo import notify as cn
    from src.data import v9_config
    monkeypatch.setattr(v9_config, "drop_paper_leagues", lambda d, col="league": d)
    cand = pd.DataFrame([_combo_row("2026-11-01T15:00:00Z", "2026-11-01", "past"),
                         _combo_row("2026-11-02T11:00:00Z", "2026-11-02", "today_started"),
                         _combo_row("2026-11-03T18:00:00Z", "2026-11-03", "future")])
    sel = cn.daily_selection(cand, now=pd.Timestamp(NOW))
    assert list(sel["combo_id"]) == ["future"]


# ── kickoff guard: a score stored before its kickoff never settles ──────────────────────────────
def test_result_guard_flags_scores_observed_before_kickoff():
    from src.data import result_guard as rg
    r = pd.DataFrame({"kickoff_utc": ["2026-11-28T17:00:00+00:00", "2026-10-25T15:30:00+00:00"],
                      "observed_at": ["2026-10-25T19:19:02Z", "2026-10-25T19:19:02Z"],
                      "home_goals": [0, 0], "away_goals": [0, 0]})
    assert list(rg.unplayed_mask(r, now=pd.Timestamp(NOW))) == [True, False]
    s = pd.DataFrame({"kickoff_ts": [1793304000], "observed_at": ["2026-10-29T19:54:46Z"]})
    assert bool(rg.unplayed_mask(s, kickoff_col="kickoff_ts", kickoff_unit="s",
                                 now=pd.Timestamp(NOW)).iloc[0])


def _paper_row(**kw) -> dict:
    base = {"row_id": "r1", "fixture_key": "fk1", "league": "X", "match_date": "2026-10-25",
            "kickoff_utc": "2026-10-25T15:30:00Z", "home_team": "Grasshoppers",
            "away_team": "FC Basel 1893", "p_home": 0.4, "p_draw": 0.3, "p_away": 0.3}
    base.update(kw)
    return base


def _patch_store(monkeypatch, results: pd.DataFrame):
    from src.data import season_store as store
    from src.pipelines import paper_1x2 as pp
    monkeypatch.setattr(store, "read", lambda t: results if t == "team_match_stats" else pd.DataFrame())
    monkeypatch.setattr(pp, "_market_snapshots", lambda: pd.DataFrame())
    monkeypatch.setattr(pp, "_one_fixture", lambda *a, **k: None)     # no v9 name resolver needed


def test_paper_1x2_settle_skips_result_stored_before_kickoff(monkeypatch):
    from src.pipelines import paper_1x2 as pp
    res = pd.DataFrame({"fixture_key": ["fk1"], "match_date": ["2026-11-28"],
                        "kickoff_utc": ["2026-11-28T17:00:00+00:00"], "observed_at": ["2026-10-25T19:19:02Z"],
                        "home_team": ["Grasshoppers"], "away_team": ["FC Basel 1893"],
                        "home_goals": [0], "away_goals": [0]})
    _patch_store(monkeypatch, res)
    out = pp.settle(pd.DataFrame([_paper_row(kickoff_utc="2026-11-28T17:00:00Z", match_date="2026-11-28")]),
                    now=NOW)
    assert out["result"].isna().all()


def test_paper_1x2_rescheduled_beyond_48h_is_void(monkeypatch):
    from src.data import result_guard as rg
    from src.pipelines import paper_1x2 as pp
    res = pd.DataFrame({"fixture_key": ["fk1", "fk2"], "match_date": ["2026-10-28", "2026-10-26"],
                        "kickoff_utc": ["2026-10-28T18:00:00+00:00", "2026-10-26T18:00:00+00:00"],
                        "observed_at": ["2026-10-28T21:00:00Z", "2026-10-26T21:00:00Z"],
                        "home_team": ["A", "C"], "away_team": ["B", "D"],
                        "home_goals": [2, 1], "away_goals": [0, 1]})
    _patch_store(monkeypatch, res)
    d = pd.DataFrame([_paper_row(fixture_key="fk1"),                       # played 75h later
                      _paper_row(row_id="r2", fixture_key="fk2", home_team="C", away_team="D")])  # 27h
    out = pp.settle(d, now=NOW)
    assert out.loc[0, "settle_note"] == rg.VOID_RESCHEDULED and pd.isna(out.loc[0, "result"])
    assert out.loc[1, "settle_note"] == rg.SETTLE_ON_ACTUAL and out.loc[1, "result"] == 1


def test_bet_builder_settle_voids_combo_rescheduled_beyond_48h():
    from src.combo import settle as cs
    cand = pd.DataFrame([{"fixture_key": "fk1", "match": "A vs B", "match_date": "2026-10-25",
                          "kickoff_utc": "2026-10-25T15:00:00Z", "leg1_market": "O25"}])
    sc = pd.DataFrame({"fixture_key": ["fk1"], "match_date": ["2026-10-29"], "home_team": ["A"],
                       "away_team": ["B"], "home_goals": [3], "away_goals": [1],
                       "kickoff_utc": ["2026-10-29T15:00:00+00:00"]})
    out = cs.settle(cand, sc, pd.DataFrame())
    assert out["combo_result"].iloc[0] == "VOID" and out["settle_note"].iloc[0].startswith("VOID_RESCHEDULED")


# ── 1X2: re-priced at notify time, never sent on a stale price ──────────────────────────────────
def test_paper_1x2_notify_refuses_stale_price_and_records_fresh_one(monkeypatch):
    from src.data import v9_config
    from src.pipelines import paper_1x2 as pp
    monkeypatch.setattr(v9_config, "drop_paper_leagues", lambda d, col="league": d)
    snap = {"o_home": 3.0, "o_draw": 3.4, "o_away": 2.4, "snapshot_at": pd.Timestamp("2026-11-01 16:00:00")}
    monkeypatch.setattr(pp, "_one_fixture", lambda *a, **k: pd.Series(snap))
    d = pd.DataFrame([_paper_row(kickoff_utc="2026-11-03T18:00:00Z", match_date="2026-11-03",
                                 o_home=2.0, o_draw=3.0, o_away=4.0)])
    r = pp.notify(d.copy(), dry_run=False, now=NOW, latest=pd.DataFrame({"x": [1]}))   # 20h old
    assert r["sent"] == 0 and r["reasons"].get("STALE_PRICE") == 1
    snap["snapshot_at"] = pd.Timestamp("2026-11-02 09:00:00")                            # 3h old
    d2 = d.copy()
    r = pp.notify(d2, dry_run=False, now=NOW, latest=pd.DataFrame({"x": [1]}))
    assert r["sent"] == 1
    assert d2.loc[0, "notified_odds"] in (3.0, 3.4, 2.4) and d2.loc[0, "o_home"] == 2.0
    assert str(d2.loc[0, "notified_price_at"]).startswith("2026-11-02 09:00")


# ── re-collect rule: a fixture stored before its kickoff is not "already collected" ─────────────
def test_team_stats_recollects_fixture_stored_before_kickoff(monkeypatch):
    from src.data import season_store as store
    from src.pipelines import team_stats as ts
    prev = pd.DataFrame({"fixture_id": ["1555431", "1555407"],
                         "kickoff_utc": ["2026-11-28T17:00:00+00:00", "2026-10-25T15:30:00+00:00"],
                         "observed_at": ["2026-10-25T19:19:02Z", "2026-10-25T19:19:02Z"]})
    monkeypatch.setattr(store, "read", lambda t: prev)
    assert ts._already_collected() == {"1555407"}
    assert ts._not_yet_played({"fixture": {"date": "2099-01-01T00:00:00+00:00"}}, pd.Timestamp(NOW))
    assert not ts._not_yet_played({"fixture": {"date": "2026-10-25T15:30:00+00:00"}}, pd.Timestamp(NOW))


# ── scout: "already a Wowza league" by API-Football id, fail closed ─────────────────────────────
def _readable_row(lid: int, country: str, name: str) -> dict:
    return {"league_id": lid, "country": country, "league": name, "status": "READABLE",
            "settled_with_close": 999, "results": 9999, "history_seasons": 5}


def test_scout_gate_refuses_a_league_v9_already_has():
    from src.scout import promotion as P
    extra = {"current_season_settled": 100, "odds_coverage": {m: 1.0 for m in P.KEY_MARKETS}}
    ok, gate = P.candidate_gate(_readable_row(62, "France", "Ligue 2"), extra, {62, "Ligue 2"})
    assert not ok and gate["checks"]["not already a Wowza league"] is False
    ok, gate = P.candidate_gate(_readable_row(62, "France", "Ligue 2"), extra, set())   # registry unread
    assert gate["checks"]["not already a Wowza league"] is False
    ok, gate = P.candidate_gate(_readable_row(333, "Ukraine", "Premier League"), extra,
                                {39, "Premier League"})   # same bare name, different league
    assert gate["checks"]["not already a Wowza league"] is True


def test_scout_wowza_leagues_raises_when_registry_unreadable(monkeypatch):
    from src.data import v9_config
    from src.scout import promotion as P

    class _Reg:
        @staticmethod
        def leagues():
            return []
    monkeypatch.setattr(v9_config, "league_ids", lambda: {})
    monkeypatch.setattr(v9_config, "league_registry", lambda: _Reg)
    with pytest.raises(RuntimeError):
        P.wowza_leagues()


# ── registry season_type comes from v9's season rule, not from the model format ─────────────────
def test_registry_season_type_derived_from_v9_season_rule():
    from src.scout import registry as R
    assert R.season_type_from_rule({"type": "start_year", "start_month": 7}) == "split_season"
    assert R.season_type_from_rule({"type": "calendar_year"}) == "calendar_year"
    j1 = {"eras": [{"until": "2026-07-01", "type": "calendar_year"},
                   {"from": "2026-07-01", "type": "end_year", "start_month": 7}]}
    assert R.season_type_from_rule(j1, "2026-11-02") == "split_season"
    assert R.season_type_from_rule(j1, "2026-03-01") == "calendar_year"
    assert R.season_type_from_rule(None) is None


# ── CLV: clean means evidenced; the audit fails otherwise ───────────────────────────────────────
def _clv_store_frame() -> pd.DataFrame:
    return pd.DataFrame({"fixture_key": ["a", "b", "c"], "match_date": ["2026-10-01"] * 3,
                         "market": ["sot"] * 3, "player": ["P1", "P2", "P3"], "side": ["OVER"] * 3,
                         "ts_bet": ["2026-09-30T10:00:00Z"] * 3, "odds_bet": [2.0, 2.0, 2.0],
                         "odds_close": [1.9, 2.0, None], "clv_pct": [0.0526, 0.0, None],
                         "result": ["WIN"] * 3, "league": ["L"] * 3})


def test_clean_clv_is_null_unless_the_close_is_evidenced(monkeypatch):
    from src.data import season_store as store
    from src.market import clv_schema as cs
    props = pd.DataFrame({"fixture_key": ["z"], "player_name": ["P3"], "market": ["sot"],
                          "market_odds": [1.8], "observed_at": ["2026-10-01T09:00:00Z"],
                          "match_date": ["2026-10-01"]})
    monkeypatch.setattr(store, "read", lambda t: _clv_store_frame() if t == "clv" else props)
    d = cs.build(quiet=True)
    q = dict(zip(d["player"], d["clv_quality"]))
    assert q == {"P1": cs.Q_OK, "P2": cs.Q_CLOSE_EQUALS_ENTRY, "P3": cs.Q_UNPROVEN_PREKICKOFF}
    c = dict(zip(d["player"], d["clean_clv_pct"]))
    assert c["P1"] == pytest.approx(5.2632, abs=1e-3)
    assert pd.isna(c["P2"]) and pd.isna(c["P3"])
    assert d.loc[d["player"] == "P2", "clv_pct"].iloc[0] == 0.0               # raw kept


def test_weekly_audit_fails_when_clean_clv_carries_unevidenced_rows(monkeypatch):
    from src.market import clv_schema as cs
    from src.monitoring import weekly_audit as wa
    bad = pd.DataFrame({"clv_pct": [0.0, 0.05], "clv_pct_normalised": [0.0, 5.0],
                        "clean_clv_pct": [0.0, 5.0], "entry_odds": [2.0, 2.1], "close_odds": [2.0, 2.0],
                        "clv_quality": [cs.Q_CLOSE_EQUALS_ENTRY, cs.Q_OK]})
    monkeypatch.setattr(cs, "build", lambda quiet=True: bad)
    a = wa.Audit()
    wa.audit_clv_schema(a, None, 7)
    chk = [c for c in a.checks if c.name == "clean_clv_pct only on evidenced closes"]
    assert chk and chk[0].status == wa.FAIL and chk[0].value == 1


def test_first_half_contaminated_rows_are_matched_from_v9_list():
    from src.data import v9_corrections as v9c
    lst = pd.DataFrame({"match_date": ["2026-07-16"], "league": ["Brazil Serie A"], "home_team": ["Botafogo"],
                        "away_team": ["Santos"], "side": ["UNDER"]})
    led = pd.DataFrame({"match_date": ["2026-07-16", "2026-07-16"], "league": ["Brazil Serie A"] * 2,
                        "home_team": ["Botafogo", "Botafogo"], "away_team": ["Santos", "Santos"],
                        "side": ["Under", "OVER"]})
    assert list(v9c.first_half_contaminated_mask(led, lst)) == [True, False]

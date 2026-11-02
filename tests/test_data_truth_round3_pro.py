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


# ── ML learning health: a shallow v9 clone cannot date a model ──────────────────────────────────
def test_ml_health_does_not_date_models_from_a_shallow_clone(tmp_path):
    import os
    import shutil
    import subprocess
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    from src.monitoring import ml_learning_health as mh
    src = tmp_path / "src"
    src.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}

    def git(*a, cwd=src, date=None):
        e = dict(env, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {}))
        subprocess.run(["git", *a], cwd=cwd, env=e, check=True, capture_output=True)
    git("init", "-q")
    (src / "model.pkl").write_bytes(b"m1")
    git("add", "-A")
    git("commit", "-qm", "model", date="2026-10-18T08:00:00+00:00")
    (src / "other.txt").write_text("x")
    git("add", "-A")
    git("commit", "-qm", "later", date="2026-11-01T11:24:09+00:00")
    assert mh._last_change(src, "model.pkl").startswith("2026-10-18")          # full history: right
    shallow = tmp_path / "shallow"
    git("clone", "-q", "--depth", "1", src.as_uri(), str(shallow), cwd=tmp_path)
    assert mh._is_shallow(shallow)
    assert mh._last_change(shallow, "model.pkl") is None                        # unknown, never HEAD's date


# ── v11 movement archive: append only what is new ───────────────────────────────────────────────
def test_movement_import_archives_only_new_rows(monkeypatch):
    from src.data import season_store as store
    from src.importers import v11_research as v
    raw = pd.DataFrame({"fixture_id": ["1", "2"], "snapshot_id": ["s1", "s2"], "bet_side": ["OVER", "UNDER"],
                        "clv_pct": ["1.5", ""], "clv_quality": ["OK", "NO_CLOSE"], "result": ["WIN", ""]})
    monkeypatch.setattr(v, "_fetch", lambda: raw)
    monkeypatch.setattr(v, "_read_v11_json", lambda rel: {"overall": "PASS", "movement": {}})
    monkeypatch.setattr(v, "_calc_version", lambda: "1.0.0")
    monkeypatch.setattr(v, "_v11_sha", lambda: "abc")
    stored = pd.DataFrame({"fixture_id": ["1"], "snapshot_id": ["s1"], "bet_side": ["OVER"],
                           "calculation_version": ["1.0.0"], "clv_pct": [1.5], "clv_quality": ["OK"],
                           "result": ["WIN"]})
    monkeypatch.setattr(store, "read", lambda t, season=None, columns=None: stored)
    out = v.from_v11_movement()
    assert len(out) == 1 and list(out[0][1]["fixture_id"]) == ["2"]
    monkeypatch.setattr(store, "read", lambda t, season=None, columns=None:
                        pd.concat([stored, stored.assign(fixture_id="2", snapshot_id="s2", bet_side="UNDER",
                                                         clv_pct=np.nan, clv_quality="NO_CLOSE",
                                                         result=None)]))
    assert v.from_v11_movement() == []                                          # nothing new -> nothing stored


# ── contract validator: repo paths come from config, not a hardcoded 'wowza-v11' ────────────────
def test_contract_validator_uses_configured_repo_paths(monkeypatch, tmp_path):
    from config import pro_config as cfg
    from src.validation import validate_system_contract as vc
    paths = vc.repo_paths()
    assert paths["v11"] == Path(cfg.V11_LOCAL) and paths["v9"] == Path(cfg.V9_LOCAL)
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path / "pro")
    (tmp_path / "wowza_v11").mkdir()
    assert cfg._sibling_checkout("wowza_v11", "wowza-v11") == tmp_path / "wowza_v11"
    (tmp_path / "wowza_v11").rmdir()
    (tmp_path / "wowza-v11").mkdir()
    assert cfg._sibling_checkout("wowza_v11", "wowza-v11") == tmp_path / "wowza-v11"


# ── registries: frozen = hash-checked and unwritable; live = append-only ─────────────────────────
def test_frozen_registrations_are_pinned_intact_and_unwritable():
    from config import pro_config as cfg
    from src import registry_guard as rgd
    assert "registry/price_trader/registration_v1.json" in rgd.frozen()
    assert rgd.verify() == []
    with pytest.raises(rgd.RegistryViolation):
        rgd.write_json(cfg.REGISTRY_DIR / "price_trader" / "registration_v1.json", {"edited": True})


def test_scout_hypothesis_registry_is_append_only(monkeypatch, tmp_path):
    import json
    from src import registry_guard as rgd
    from src.scout import hypotheses as H
    f = tmp_path / "scout_hypotheses.json"
    monkeypatch.setattr(H, "REGISTRY_FILE", f)
    reg = {"registry": "scout_hypotheses", "version": 1, "criteria": {"a": 1}, "criteria_sha256": "x",
           "created_at": "t", "hypotheses": [
               {"id": "H1", "league_id": 1, "league": "L", "market": "ou15", "registered_at": "t0",
                "state": "DISCOVERY", "confirmation_start": None, "history": [{"to": "DISCOVERY"}]}]}
    H.save_registry(reg)
    grown = json.loads(json.dumps(reg))
    grown["hypotheses"][0]["history"].append({"to": "CONFIRMING"})
    grown["hypotheses"][0]["confirmation_start"] = "2026-11-02"
    grown["hypotheses"].append({**reg["hypotheses"][0], "id": "H2"})
    H.save_registry(grown)                                                   # growth is allowed
    for mutate in (lambda r: r["hypotheses"].pop(0),
                   lambda r: r["hypotheses"][0].update(market="ou25"),
                   lambda r: r["hypotheses"][0].update(confirmation_start="2026-12-01"),
                   lambda r: r["hypotheses"][0].update(history=[{"to": "CONFIRMING"}]),
                   lambda r: r.update(criteria={"a": 2})):
        bad = json.loads(json.dumps(grown))
        mutate(bad)
        with pytest.raises(rgd.RegistryViolation):
            H.save_registry(bad)
    assert json.loads(f.read_text(encoding="utf-8")) == grown


# ── snapshots: provider observation time, never ingest time ────────────────────────────────────
def test_provider_observed_at_never_uses_a_date_only_stamp():
    from src.data import observation_time as otm
    r = otm.provider_observed_at(pd.Series(["2026-10-24T03:46:39Z", "2025-06-23T00:00:00Z", None,
                                            "2026-08-09T10:55:35"]), "v9_snapshot_ts")
    assert list(r["observed_at"]) == ["2026-10-24T03:46:39Z", None, None, "2026-08-09T10:55:35Z"]
    assert list(r["observed_at_source"]) == ["provider:v9_snapshot_ts", "ingest_time", "ingest_time",
                                             "provider:v9_snapshot_ts"]


def test_near_kickoff_coverage_uses_provider_time_not_ingest_time():
    from src.monitoring import scheduler as sch
    fx = pd.DataFrame({"fixture_key": ["f1"], "kickoff_utc": ["2026-10-01T12:00:00Z"], "league": ["L"]})
    # ingested 11:55 (inside T-10m) but the price was captured at 08:00 (T-4h)
    snaps = pd.DataFrame({"fixture_key": ["f1"], "observed_at": ["2026-10-01T11:55:00Z"],
                          "snapshot_ts": ["2026-10-01T08:00:00Z"]})
    r = sch._near_kickoff(snaps, fx)
    assert r["T-10m"]["fixtures_covered"] == 0 and r["T-6h"]["fixtures_covered"] == 1
    only_ingest = pd.DataFrame({"fixture_key": ["f1"], "observed_at": ["2026-10-01T11:55:00Z"]})
    r = sch._near_kickoff(only_ingest, fx)
    assert r["status"] == "NO_JOINED_OBSERVATIONS" and r["rows_with_ingest_time_only"] == 1


# ── consensus: exchange placeholders and 46% margins never enter it ─────────────────────────────
def test_consensus_devig_is_gated():
    from src.market import devig
    from src.studies import common as C
    assert devig.fair_prob(1.01, 1.01) is None                       # placeholder pair
    assert devig.fair_prob(1.56, 1.22) is None                       # Matchbook, 46% margin
    assert devig.fair_prob(1.95, 1.95) == pytest.approx(0.5, abs=1e-6)
    assert C.power_devig(1.56, 1.22) is None                         # what the study panels call


# ── VALUABLE history: a close after the earliest known kickoff is not a pre-kickoff close ──────
def test_valuable_close_after_earliest_kickoff_is_not_valid():
    from src.studies import edge_reassessment as er
    gen = pd.to_datetime(["2026-08-15 15:31:48+00:00"] * 2)
    close = pd.to_datetime(["2026-08-22 16:56:49+00:00", "2026-08-22 14:56:49+00:00"])
    kick = pd.to_datetime(["2026-08-22 15:00:00+00:00"] * 2)
    st = er.close_status(close, gen, [0.05, 0.05], kick)
    assert list(st) == ["CLOSE_NOT_PROVEN_PRE_KICKOFF", "VALID_PRE_KICKOFF_CLOSE"]

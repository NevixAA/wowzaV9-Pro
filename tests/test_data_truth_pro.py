"""Data Truth 2026-11-01 (Pro): a missing input is missing - never a stand-in value.

One focused test per behaviour change outside the bankroll (tests/test_bankroll.py) and identity
(tests/test_identity_bray.py) suites.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import pro_config as cfg  # noqa: E402

needs_v9 = pytest.mark.skipif(not (cfg.V9_LOCAL / "config" / "leagues.json").exists(),
                              reason="needs a v9 checkout (league registry + team_names)")


# ── score fit: no side-specific market without a side-specific input ─────────────────────────
def test_score_fit_never_reports_1x2_or_team_goals():
    from src.combo import match_picture as mp
    from src.combo import score_model as sm
    f = sm.fit({"O15": 0.75, "O25": 0.52, "O35": 0.28, "BTTS": 0.50})
    legs = mp.goal_legs(f["matrix"], f["targets_used"])
    assert {"O25", "BTTS", "DRAW"} <= set(legs)
    assert not {"HOME", "AWAY", "1X", "X2", "HOME_O05", "AWAY_O15"} & set(legs)
    # totals only (no BTTS target): the split is unidentified, so BTTS/DRAW are not read either
    g = sm.fit({"O25": 0.52})
    assert sm.identified_markets(g["targets_used"]) == sm.TOTAL_MARKETS


# ── builder joint: unmeasured dependence is refused, not priced at 1.0 ───────────────────────
def test_unmeasured_dependence_is_refused():
    from src.combo import match_picture as mp
    from src.combo import score_model as sm
    m = sm.fit({"O15": 0.75, "O25": 0.52, "O35": 0.28, "BTTS": 0.50})["matrix"]
    g = mp.goal_legs(m, ["O15", "O25", "O35", "BTTS"])["O25"]
    goal = {"kind": "goal", "key": "O25", "p": g[0], "mask": g[1], "label": g[2]}
    pl = {"kind": "player", "player": "A", "market": "goals", "p": 0.3, "label": "A to score"}
    pj, src, _ = mp._joint([goal, pl], m, {})
    assert pj is None and src == "UNMEASURED_DEPENDENCE"
    pj, src, _ = mp._joint([goal, pl], m, {("goals", "O25"): 1.45})
    assert src == "SCORE_MATRIX_PLUS_MEASURED_DEPENDENCE" and pj == pytest.approx(g[0] * 0.3 * 1.45)
    pl2 = {**pl, "player": "B", "label": "B to score"}
    assert mp._joint([goal, pl, pl2], m, {("goals", "O25"): 1.45})[1] == "UNMEASURED_DEPENDENCE"


def test_score_or_assist_has_no_default_overlap():
    import inspect

    from src.combo import team_markets as tm
    assert inspect.signature(tm.score_or_assist).parameters["overlap_rate"].default is inspect._empty


# ── settlement: a join miss is UNKNOWN, never VOID / did-not-play ─────────────────────────────
def test_missing_player_row_is_unknown_not_void():
    from src.combo import settle as cs
    assert cs.settle_player_leg("goals", None) == cs.LEG_UNKNOWN
    assert cs.settle_player_leg("goals", pd.Series({"minutes": 0, "goals": 0})) == cs.LEG_VOID
    # carded: one count missing and the other 0 is undecidable
    assert cs.settle_player_leg("cards", pd.Series({"minutes": 90, "yellow_cards": 0,
                                                    "red_cards": np.nan})) == cs.LEG_UNKNOWN


@needs_v9
def test_unparseable_player_label_is_unknown():
    from src.combo import settle as cs
    cand = pd.DataFrame([{"fixture_key": "k1", "match_date": "2026-09-01", "league": "Championship",
                          "match": "A vs B", "leg1_market": "player_sot",
                          "leg1_label": "R. Karjalainen 1+ shot on target"}])
    sc = pd.DataFrame([{"fixture_key": "k1", "league": "Championship", "match_date": "2026-09-01",
                        "home_team": "A", "away_team": "B", "home_goals": 1, "away_goals": 0}])
    out = cs.settle(cand, sc, pd.DataFrame())
    assert out.loc[0, "combo_result"] == cs.COMBO_UNKNOWN


# ── v9 direction gate: unreadable gate is held, not shipped ungated ──────────────────────────
def test_unreadable_v9_gate_marks_and_holds_the_board(monkeypatch):
    from src.combo import notify as cn
    from src.combo import v9_direction as gate
    monkeypatch.setattr(gate, "directions", lambda: None)
    cand = pd.DataFrame([{"league": "Championship", "match_date": "2026-09-01", "match": "A vs B",
                          "leg1_market": "O25", "combo_id": "x"}])
    out = gate.apply(cand)
    assert (out["v9_gate"] == gate.GATE_UNAVAILABLE).all()
    assert cn._hold_ungated(out).empty


# ── paper leagues: registry list, alias spelling dropped too ─────────────────────────────────
@needs_v9
def test_paper_leagues_come_from_registry_and_match_aliases(monkeypatch):
    from src.data import v9_config
    paper = v9_config.paper_leagues()
    assert paper and set(cfg.PAPER_LEAGUES) == set(paper)
    lg = sorted(paper)[0]
    alias = next((a for a, c in v9_config.league_registry().alias_map().items() if c == lg), None)
    rows = pd.DataFrame({"league": [lg, "Championship"] + ([alias] if alias else [])})
    kept = v9_config.drop_paper_leagues(rows)
    assert list(kept["league"]) == ["Championship"]


# ── importer: blank tier / result / side stay missing and are flagged ────────────────────────
def test_blank_to_na_and_flags_are_registered():
    from src import quality as q
    from src.importers import current_wowza as W
    s = W._blank_to_na(pd.Series(["SNIPER", "", None, "  "]))
    assert s.iloc[0] == "SNIPER" and s.iloc[1:].isna().all()
    for f in ("TIER_MISSING", "RESULT_MISSING", "SIDE_UNKNOWN", "LEAGUE_MISSING", "DATE_MISSING"):
        assert f in q.FLAGS


# ── scout + league strength: unrated -> no prediction ────────────────────────────────────────
def test_league_strength_refuses_unfitted_league():
    from src.combo import league_strength as ls
    cal = {"ok": True, "strength": {"A": 0.1, "B": -0.1}, "home_adv": 0.2, "rho": 0.0}
    row = pd.Series({"home_league": "A", "away_league": "C", "att_h": 0, "def_h": 0,
                     "att_a": 0, "def_a": 0})
    assert ls.predict(row, cal) is None                 # 'C' has no fitted strength
    ok = row.copy()
    ok["away_league"] = "B"
    assert ls.predict(ok, cal) is not None


def test_scout_unrated_team_has_no_prediction():
    from src.scout import model
    m = {"teams": {1: 0}, "A": [1.1], "D": [0.9], "mu_h": 1.4, "mu_a": 1.1, "games": [10],
         "offset": {}, "n_matches": 10}
    assert model.predict(m, 1, 2) is None and model.predict(m, 2, 1) is None


# ── live collector: a failed call is an error, not "nothing live" ────────────────────────────
def test_live_fetch_failure_is_raised_not_empty():
    from src.live import collector as lc
    with pytest.raises(RuntimeError):
        lc.fetch(lambda *a, **k: None)
    assert lc.fetch(lambda *a, **k: {"response": []}).empty


# ── research targets: unknown market / outcome stays NaN ─────────────────────────────────────
def test_known_target_keeps_missing_outcomes_out():
    from src.player_v3 import data as D
    y, known = D.known_target(pd.DataFrame({"t": [1, 0, np.nan]}), "t")
    assert known.tolist() == [True, True, False] and np.isnan(y[2])

"""Pro prediction ledger (src/prediction_ledger_pro.py) - owner rule 2026-11-17. Learning only.

The shared core (src/prediction_ledger.py) is identical to v9's and is pinned there in full
(tests/test_prediction_ledger.py, NevixAA/wowza-betting). This file pins Pro's writers: the grid
markets read off the Dixon-Coles score grid, every board fixture recorded (gridded or with the reason
it could not be), combos before the v9 gate, the flag, and settlement on Pro scorelines.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import prediction_ledger as PL
from src import prediction_ledger_pro as PP
from src.combo import score_model as sm

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
LEAGUES = {"leagues": [{"id": "championship", "name": "Championship", "aliases": [],
                        "production_state": "ENABLED", "season_rule": {"type": "start_year", "start_month": 7}},
                       {"id": "serie_b", "name": "Serie B", "aliases": [],
                        "production_state": "ENABLED", "season_rule": {"type": "start_year", "start_month": 7}}]}


@pytest.fixture
def v9dir(tmp_path, monkeypatch):
    d = tmp_path / "v9"
    (d / "config").mkdir(parents=True)
    (d / "output").mkdir()
    (d / "config" / "leagues.json").write_text(json.dumps(LEAGUES), encoding="utf-8")
    pd.DataFrame([{"league": "Championship", "date": "2026-11-21", "home_team": "Norwich City",
                   "away_team": "Cardiff City", "_oa_event_id": "8e1abc"}]).to_csv(d / "output" / "predictions.csv",
                                                                                   index=False)
    monkeypatch.setenv("PREDICTION_LEDGER_V9_DIR", str(d))
    monkeypatch.setenv(PL.FLAG_ENV, "true")
    monkeypatch.setattr(PL, "LEDGER_DIR", tmp_path / "L")
    monkeypatch.setattr(PP, "_REC", None)
    return d


def _key():
    from src.data import entities as ent
    return ent.fixture_key("Championship", "2026-11-21", "Norwich City", "Cardiff City")


def _fx(**kw):
    r = {"fixture_key": _key(), "league": "Championship", "match_date": "2026-11-21",
         "home_team": "Norwich City", "away_team": "Cardiff City",
         "_ko": pd.Timestamp("2026-11-21T15:00:00Z")}
    r.update(kw)
    return r


def test_grid_markets_are_coherent():
    m = sm.score_matrix(1.4, 1.1, -0.05)
    g = PP.grid_markets(m)
    assert abs(sum(g["1x2"].values()) - 1) < 1e-9
    assert abs(sum(g["correct_score"].values()) - 1) < 1e-9 and len(g["correct_score"]) == 50
    assert g["goals_le1"]["YES"] >= g["goals_exact_0"]["YES"]
    assert g["goals_ge5"]["YES"] >= g["goals_ge6"]["YES"] >= g["goals_ge7"]["YES"]
    assert abs(g["1x2"]["H"] - sm.prob(m, "HOME")) < 1e-12
    cfg = {e["market"]: e for e in PL.load_markets()["entries"] if e["model_id"] == "pro_bb_dc"}
    for market, sels in g.items():
        assert set(sels) == set(cfg[market]["selections"]), market


def test_flag_off_records_nothing(monkeypatch):
    monkeypatch.delenv(PL.FLAG_ENV, raising=False)
    monkeypatch.setattr(PP, "_REC", None)
    assert PP.recorder() is None


def test_every_board_fixture_is_recorded_gridded_or_with_a_reason(v9dir, tmp_path):
    rec = PP.recorder(NOW)
    assert rec.oa == {next(iter(rec.oa)): "8e1abc"}
    fit = sm.fit({"O15": 0.75, "O25": 0.5, "O35": 0.27, "BTTS": 0.52})
    rec.grid(pd.Series(_fx()), _key(), fit, {"O15": 0.75, "O25": 0.5, "O35": 0.27, "BTTS": 0.52})
    fx = pd.DataFrame([_fx(), _fx(fixture_key="k2", league="Serie B", home_team="Bari", away_team="Pisa")])
    probs = pd.DataFrame({"OU25": [0.5]}, index=["k2"])                    # one marginal only
    st = rec.board_done(fx, probs)
    assert st["refused"] == 0 and st["written"] > 0
    assert PL.validate(tmp_path / "L", slugs=rec.slugs) == []
    d = pd.read_csv(tmp_path / "L" / "pro" / "pro_bb_dc" / "1x2" / "championship" / "2026.csv", dtype=str,
                    keep_default_na=False)
    assert d["fixture_ref"].tolist() == ["oa:8e1abc"] * 3
    assert abs(d["probability"].astype(float).sum() - 1) < 1e-5
    u = pd.read_csv(tmp_path / "L" / "pro" / "pro_bb_dc" / "correct_score" / "serie_b" / "2026.csv", dtype=str,
                    keep_default_na=False)
    assert len(u) == 50 and (u["scored"] == "0").all()
    assert u["not_scored_reason"].str.contains("fewer than 2").all()
    assert u["fixture_ref"].iloc[0] == "nk:serie_b|2026-11-21|Bari|Pisa"


def test_combos_are_recorded_and_settle_on_the_builder_record(v9dir, tmp_path):
    rec = PP.recorder(NOW)
    d = pd.DataFrame([{"fixture_key": _key(), "joint_probability": 0.2555, "calc_version": "1.0.0",
                       "leg1_market": "BTTS", "leg1_label": "Both teams to score",
                       "leg2_market": "player_goals", "leg2_label": "Neymar to score"}])
    st = rec.combos(d, pd.DataFrame([_fx()]))
    assert st["written"] == 1
    p = tmp_path / "L" / "pro" / "pro_bb_combo" / "combo" / "championship" / "2026.csv"
    row = pd.read_csv(p, dtype=str, keep_default_na=False).iloc[0]
    assert row["selection"] == "BTTS:Both teams to score|player_goals:Neymar to score"
    from src.data import entities as ent
    fkey = ent.fixture_key("Championship", "2026-11-21", "Norwich City", "Cardiff City")
    cid = f"{fkey}|" + hashlib.sha1(row["selection"].encode("utf-8")).hexdigest()[:12]
    scores = pd.DataFrame([{"fixture_key": fkey, "home_goals": 2, "away_goals": 1}])
    fn = PP.outcome_fn(now=datetime(2026, 11, 22, tzinfo=timezone.utc), scores=scores,
                       combos=pd.DataFrame([{"combo_id": cid, "combo_result": "WON"}]))
    out = fn(row.to_dict())
    assert out["outcome_status"] == "SETTLED" and out["y"] == 1
    r1x2 = dict(row.to_dict(), model_id="pro_bb_dc", market="1x2", selection="H")
    assert fn(r1x2)["y"] == 1 and fn(dict(r1x2, selection="D"))["y"] == 0
    cs = dict(row.to_dict(), model_id="pro_bb_dc", market="correct_score", selection="2-1")
    assert fn(cs)["y"] == 1


# ── ledger-only leagues (owner 2026-11-19): grids from v9's ledger-only board, no combo, no album ───

LO_LEAGUES = {"leagues": [{"id": "scottish_premiership", "name": "Scottish Premiership", "aliases": [],
                           "production_state": "TRAINING_ONLY",
                           "season_rule": {"type": "start_year", "start_month": 7}}]}


@pytest.fixture
def v9lo(tmp_path, monkeypatch):
    d = tmp_path / "v9lo"
    (d / "config").mkdir(parents=True)
    (d / "output" / "ledger_only").mkdir(parents=True)
    (d / "config" / "leagues.json").write_text(json.dumps(LO_LEAGUES), encoding="utf-8")
    pd.DataFrame([
        {"fixture_id": "9001", "league": "Scottish Premiership", "league_state": "TRAINING_ONLY",
         "kickoff_utc": "2026-11-21T15:00:00Z", "home_team": "Hearts", "away_team": "St Mirren",
         "af_home_name": "Heart Of Midlothian", "af_away_name": "ST Mirren", "p_over15": 0.78,
         "p_over25": 0.55, "p_over35": 0.30, "p_btts": 0.52, "not_scored_reason": ""},
        {"fixture_id": "9002", "league": "Scottish Premiership", "league_state": "TRAINING_ONLY",
         "kickoff_utc": "2026-11-21T17:30:00Z", "home_team": "X", "away_team": "Y",
         "af_home_name": "X FC", "af_away_name": "Y FC", "p_over15": None, "p_over25": None,
         "p_over35": None, "p_btts": None, "not_scored_reason": "home team: identity not proven"},
    ]).to_csv(d / "output" / "ledger_only" / "board.csv", index=False)
    monkeypatch.setenv("PREDICTION_LEDGER_V9_DIR", str(d))
    monkeypatch.setenv(PL.FLAG_ENV, "true")
    return d


def test_ledger_only_grids_record_every_board_fixture(v9lo, tmp_path):
    before = {f: (Path(PP.ROOT) / "output" / f).read_bytes() if (Path(PP.ROOT) / "output" / f).exists() else b""
              for f in ("bet_builder_candidates.csv", "bet_builder_daily.csv")}
    st = PP.ledger_only_grids(now=NOW, root=tmp_path / "L")
    assert st["refused"] == 0 and st["written"] > 0
    parts = PL.partitions(tmp_path / "L")
    d = pd.concat([PL.read_partition(p) for p in parts])
    assert set(d["model_id"]) == {PP.GRID_MODEL}
    assert set(d["fixture_ref"]) == {"af:9001", "af:9002"}
    assert d["payload_version"].str.endswith("ledger_only:TRAINING_ONLY").all()
    a = d[d["fixture_ref"] == "af:9001"]
    assert (a["scored"].astype(str) == "1").all() and set(a["home_team"]) == {"Heart Of Midlothian"}
    one = a[a["market"] == "1x2"]["probability"].astype(float).sum()
    assert abs(one - 1.0) < 1e-4
    b = d[d["fixture_ref"] == "af:9002"]
    assert (b["scored"].astype(str) == "0").all() and b["not_scored_reason"].str.contains("identity not proven").all()
    assert PL.validate(tmp_path / "L", slugs=PL.LeagueSlugs(PL.load_leagues(v9lo / "config" / "leagues.json"))) == []
    # learning only: no combo / album file is written
    after = {f: (Path(PP.ROOT) / "output" / f).read_bytes() if (Path(PP.ROOT) / "output" / f).exists() else b""
             for f in before}
    assert after == before
    assert not [p for p in parts if PL.parse_partition(tmp_path / "L", p)["model_id"] == PP.COMBO_MODEL]
    # idempotent
    assert PP.ledger_only_grids(now=NOW, root=tmp_path / "L")["written"] == 0


def test_ledger_only_grids_need_their_own_flag(v9lo, monkeypatch, capsys):
    monkeypatch.delenv(PP.LEDGER_ONLY_FLAG, raising=False)
    monkeypatch.setattr(PP, "ledger_only_grids", lambda **k: pytest.fail("must not run with the flag off"))
    assert PP.main(["ledger-only"]) == 0
    assert "nothing written" in capsys.readouterr().out


def test_bet_builder_never_reads_the_ledger_only_board():
    src = (Path(PP.ROOT) / "src" / "pipelines" / "bet_builder.py").read_text(encoding="utf-8")
    assert "ledger_only" not in src

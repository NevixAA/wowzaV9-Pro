"""Props matchup track: point-in-time features, shrinkage, multiple testing, fail-closed readiness.

    python -m pytest tests/test_props_matchup.py -q

SYNTHETIC DATA ONLY (owner rule: no fitting, backtest or edge on real data until the data is 100%
real). The one test touching v9 compares a constant with v9's own file, when a checkout exists.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import pro_config as cfg  # noqa: E402
from src.props_matchup import evaluation as E  # noqa: E402
from src.props_matchup import features as F  # noqa: E402
from src.props_matchup import inputs as I  # noqa: E402
from src.props_matchup import readiness as R  # noqa: E402

UTC = "UTC"


# ── synthetic world ──────────────────────────────────────────────────────────────────────────────
def _world(n_fix=12, seed=0, source=I.REFETCHED):
    """Two teams, A (attackers) vs B (defence with keeper 900 and defenders 901/902), one match every
    7 days. Defender 901 starts every B match except fixtures 3, 6, 9."""
    rng = np.random.default_rng(seed)
    app, stats = [], []
    for f in range(n_fix):
        date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=7 * f)
        fid = 100 + f
        for pid in (1, 2):                                       # team A attackers
            app.append({"fixture_id": fid, "player_id": pid, "date": date, "team": "A", "opponent": "B",
                        "position": "F", "minutes": 90, "started": 1,
                        "shots_on_target": int(rng.poisson(1)), "shots_total": int(rng.poisson(2)),
                        "goals": int(rng.poisson(0.3)), I.SOURCE_COL: source})
        for pid, pos in ((900, "G"), (901, "D"), (902, "D"), (903, "M")):
            starts = not (pid == 901 and f in (3, 6, 9))
            if pid == 901 and not starts:
                continue                                         # did not play: no row
            app.append({"fixture_id": fid, "player_id": pid, "date": date, "team": "B", "opponent": "A",
                        "position": pos, "minutes": 90, "started": 1, "shots_on_target": 0,
                        "shots_total": 0, "goals": 0, I.SOURCE_COL: source})
        if not any(r["player_id"] == 901 and r["fixture_id"] == fid for r in app):
            app.append({"fixture_id": fid, "player_id": 904, "date": date, "team": "B", "opponent": "A",
                        "position": "D", "minutes": 90, "started": 1, "shots_on_target": 0,
                        "shots_total": 0, "goals": 0, I.SOURCE_COL: source})
        sot_against_b = 6.0 if f in (3, 6, 9) else 3.0          # B concedes more without 901
        stats.append({"fixture_id": fid, "date": date, "team": "B", "opponent": "A",
                      "shots_against": 2 * sot_against_b, "sot_against": sot_against_b,
                      "shots_for": 8.0, "sot_for": 3.0})
        stats.append({"fixture_id": fid, "date": date, "team": "A", "opponent": "B",
                      "shots_against": 8.0, "sot_against": 3.0, "shots_for": 2 * sot_against_b,
                      "sot_for": sot_against_b})
    return pd.DataFrame(app), pd.DataFrame(stats)


def _target(fid=111, date="2026-03-19", kickoff="2026-03-19T15:00:00Z", lead_min=60):
    ko = pd.Timestamp(kickoff)
    return pd.DataFrame([{"fixture_id": fid, "player_id": 1, "team": "A", "opponent": "B",
                          "date": pd.Timestamp(date), "decision_ts": ko - pd.Timedelta(minutes=lead_min)}])


def _absence(fid=111, pid=901, observed="2026-03-19T12:00:00Z", pit=I.PIT_PRE):
    return pd.DataFrame([{"fixture_id": fid, "team": "B", "player_id": pid,
                          "observed_at": pd.Timestamp(observed) if observed else pd.NaT,
                          "pit": pit, "source": "synthetic"}])


def _lists(fid=111, observed="2026-03-19T12:00:00Z", pit=I.PIT_PRE):
    return pd.DataFrame([{"fixture_id": fid, "team": "B", "observed_at": pd.Timestamp(observed), "pit": pit}])


def _build(app, stats, targets, absences, lists, **kw):
    kw.setdefault("lookback_matches", 10)
    kw.setdefault("form_matches", 5)
    return F.build(targets, app, stats, absences, lists, **kw)


# ── point-in-time correctness ────────────────────────────────────────────────────────────────────
def test_absence_known_before_decision_is_used():
    app, st = _world()
    f, a, audit = _build(app, st, _target(), _absence(), _lists())
    r = f.iloc[0]
    assert r["opp_def_absent_n"] == 1 and r["top_def_absentee"] == 901
    assert r["absence_clock"] == "observed" and audit["kept"] == 1


def test_absence_observed_after_decision_is_ignored():
    app, st = _world()
    # observed 30 minutes before kickoff, decision 60 minutes before: too late
    f, _, audit = _build(app, st, _target(), _absence(observed="2026-03-19T14:30:00Z"), _lists())
    assert audit["dropped_observed_after_decision"] == 1
    assert f.iloc[0]["opp_def_absent_n"] == 0


def test_absence_without_observation_time_is_dropped_not_assumed():
    app, st = _world()
    f, _, audit = _build(app, st, _target(), _absence(observed=None), _lists())
    assert audit["dropped_no_observation_time"] == 1
    assert f.iloc[0]["opp_def_absent_n"] == 0


def test_after_the_fact_absence_needs_opt_in_and_is_flagged():
    app, st = _world()
    ab, li = _absence(pit=I.PIT_AFTER), _lists(pit=I.PIT_AFTER)
    f, _, audit = _build(app, st, _target(), ab, li)
    assert audit["dropped_clock_not_allowed"] == 1
    assert f.iloc[0]["absence_clock"] == "none" and np.isnan(f.iloc[0]["opp_def_absent_n"])
    f2, _, _ = _build(app, st, _target(), ab, li, allow_after_the_fact=True)
    assert f2.iloc[0]["opp_def_absent_n"] == 1 and f2.iloc[0]["absence_clock"] == "assumed"


def test_future_outcomes_do_not_change_features():
    app, st = _world()
    base, _, _ = _build(app, st, _target(), _absence(), _lists())
    app2, st2 = app.copy(), st.copy()
    cut = pd.Timestamp("2026-03-19")                     # the target's own date and later
    fut = app2["date"] >= cut
    app2.loc[fut, ["shots_on_target", "shots_total", "goals", "minutes"]] = [9, 9, 9, 1]
    st2.loc[st2["date"] >= cut, ["sot_against", "shots_against"]] = [99.0, 99.0]
    pert, _, _ = _build(app2, st2, _target(), _absence(), _lists())
    pd.testing.assert_frame_equal(base, pert)


def test_same_day_match_is_excluded():
    app, st = _world()
    extra = app[app["fixture_id"] == 110].copy()
    extra["fixture_id"], extra["date"] = 999, pd.Timestamp("2026-03-19")
    extra["shots_on_target"] = 7
    base, _, _ = _build(app, st, _target(), _absence(), _lists())
    with_same_day, _, _ = _build(pd.concat([app, extra]), st, _target(), _absence(), _lists())
    pd.testing.assert_frame_equal(base, with_same_day)


def test_decision_ts_is_required():
    app, st = _world()
    with pytest.raises(ValueError):
        _build(app, st, _target().drop(columns=["decision_ts"]), _absence(), _lists())


# ── missing stays missing ────────────────────────────────────────────────────────────────────────
def test_no_observed_list_means_unknown_not_zero():
    app, st = _world()
    f, _, audit = _build(app, st, _target(), _absence().iloc[0:0], _lists().iloc[0:0])
    assert f.iloc[0]["absence_clock"] == "none"
    assert np.isnan(f.iloc[0]["opp_def_absent_n"]) and audit["targets_without_observed_list"] == 1


def test_observed_empty_list_is_a_real_zero():
    app, st = _world()
    f, _, _ = _build(app, st, _target(), _absence().iloc[0:0], _lists())
    assert f.iloc[0]["opp_def_absent_n"] == 0 and f.iloc[0]["opp_def_absent_minutes_share"] == 0.0


def test_unverified_counts_give_missing_features():
    app, st = _world(source=I.UNVERIFIED)
    f, a, _ = _build(app, st, _target(), _absence(), _lists())
    assert np.isnan(f.iloc[0]["form_sot_p90"])
    assert np.isnan(a.iloc[0]["minutes_share"])
    # the same data, explicitly allowed (exploration only), gives numbers
    f2, _, _ = _build(app, st, _target(), _absence(), _lists(), verified_only=False)
    assert np.isfinite(f2.iloc[0]["form_sot_p90"])


def test_unknown_absentee_has_unknown_importance():
    app, st = _world()
    f, a, _ = _build(app, st, _target(), _absence(pid=12345), _lists())
    assert a.iloc[0]["position"] is None and np.isnan(a.iloc[0]["minutes_share"])
    assert f.iloc[0]["opp_unknown_position_absent_n"] == 1


def test_with_without_concessions():
    app, st = _world()
    _, a, _ = _build(app, st, _target(), _absence(), _lists())
    r = a.iloc[0]
    # lookback = 10 matches before 2026-03-19 = fixtures 101..110; 901 missed 103, 106, 109
    assert (r["n_with"], r["n_without"]) == (7, 3)
    assert r["sot_against_with"] == 3.0 and r["sot_against_without"] == 6.0
    assert r["start_share"] == pytest.approx(0.7)


# ── walk-forward ─────────────────────────────────────────────────────────────────────────────────
def test_walk_forward_trains_only_on_the_past():
    days = pd.Series(pd.to_datetime(["2026-01-01"] * 3 + ["2026-01-08"] * 2 + ["2026-01-15"] * 4
                                    + ["2026-01-22"] * 2))
    folds = E.walk_forward_blocks(days, min_train_blocks=1, embargo_blocks=1)
    assert [str(f.test_block.date()) for f in folds] == ["2026-01-15", "2026-01-22"]
    for f in folds:
        assert days.iloc[f.train_idx].max() < days.iloc[f.test_idx].min() - pd.Timedelta(days=7)
        assert set(f.train_idx).isdisjoint(f.test_idx)
    with pytest.raises(ValueError):
        E.walk_forward_blocks(pd.Series([pd.NaT, pd.Timestamp("2026-01-01")]), min_train_blocks=1)


# ── shrinkage ────────────────────────────────────────────────────────────────────────────────────
def _cells(seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    for league, mu in (("L1", 0.0), ("L2", 0.05)):
        for p in range(30):
            n = 400 if p == 0 else (3 if p == 1 else 40)
            true = mu + (0.2 if p in (0, 1) else rng.normal(0, 0.02))
            for v in rng.normal(true, 0.5, n):
                rows.append({"market": "sot", "league": league, "role": "F", "player_id": f"{league}-{p}",
                             "v": v})
    return pd.DataFrame(rows)


def test_shrinkage_small_player_stays_near_group_large_player_near_own():
    post = E.nested_shrinkage(_cells(), "v", min_n=10)
    pl = post[post["level"] == "player_id"].set_index("player_id")
    role = post[(post["level"] == "role") & (post["league"] == "L1")].iloc[0]
    small, big = pl.loc["L1-1"], pl.loc["L1-0"]
    assert small["B"] == 1.0                                           # below min_n: parent's value
    assert small["posterior_mean"] == pytest.approx(role["posterior_mean"])
    assert big["B"] < 0.5                                              # 400 matches: mostly its own
    assert abs(big["posterior_mean"] - big["raw_mean"]) < abs(big["posterior_mean"] - role["posterior_mean"])
    # every mid-sized cell is pulled toward the group, never past it
    mid = pl[(pl["n"] == 40) & (pl["league"] == "L1")]
    assert ((mid["posterior_mean"] - role["posterior_mean"]).abs()
            <= (mid["raw_mean"] - role["posterior_mean"]).abs() + 1e-12).all()


def test_shrinkage_with_no_between_cell_variance_collapses_to_parent():
    rng = np.random.default_rng(3)
    d = pd.DataFrame({"market": "sot", "league": "L", "role": "F",
                      "player_id": np.repeat(np.arange(20), 50), "v": rng.normal(0, 1, 1000)})
    post = E.nested_shrinkage(d, "v", min_n=10)
    pl = post[post["level"] == "player_id"]
    assert pl["B"].min() > 0.6                                          # pure noise: heavy shrinkage


def test_bars_fail_closed_without_owner_confidence():
    post = E.nested_shrinkage(_cells(), "v", min_n=10)
    b = E.cell_bars(post, confidence=None)
    assert b["bar"].isna().all() and (b["permission"] == "BLOCKED").all()
    b2 = E.cell_bars(post, confidence=0.9)
    assert (b2["bar"] >= 0).all() and (b2["permission"] == "PAPER").all()
    # a wider posterior needs a higher bar at the same mean
    one = pd.DataFrame({"posterior_mean": [0.0, 0.0], "posterior_sd": [0.01, 0.05]})
    bb = E.cell_bars(one, confidence=0.9)["bar"].to_numpy()
    assert bb[1] > bb[0]


# ── multiple testing ─────────────────────────────────────────────────────────────────────────────
def test_bh_known_values_and_nan_kept():
    p = [0.01, 0.04, 0.03, 0.005, np.nan]
    q = E.bh_qvalues(p)
    # sorted 0.005, 0.01, 0.03, 0.04 (m=4): 0.02, 0.02, 0.04, 0.04
    assert np.allclose(q[:4], [0.02, 0.04, 0.04, 0.02]) and np.isnan(q[4])
    assert np.all(E.by_qvalues(p)[:4] >= q[:4])
    h = E.holm_adjust([0.01, 0.04, 0.03, 0.005])
    assert np.allclose(h, [0.03, 0.06, 0.06, 0.02])
    with pytest.raises(ValueError):
        E.bh_qvalues([1.2])


def test_thousands_of_null_cells_give_almost_no_discoveries():
    rng = np.random.default_rng(7)
    p = rng.uniform(size=5000)                       # 5000 player cells, no real edge anywhere
    assert (p < 0.05).sum() > 150                    # raw testing "finds" hundreds
    assert (E.bh_qvalues(p) < 0.10).sum() <= 5
    assert (E.by_qvalues(p) < 0.10).sum() == 0
    # real signal in 50 cells survives BH
    p2 = p.copy()
    p2[:50] = rng.uniform(0, 1e-5, 50)
    assert (E.bh_qvalues(p2)[:50] < 0.10).all()


# ── CLV / line move / residual ───────────────────────────────────────────────────────────────────
def _market(n=6000, absorb=0.0, seed=0):
    """True p = open + d + s. The market has already moved d (other news) by our decision; our shift s
    is real information; by the close the market absorbs `absorb` * s plus its own noise."""
    rng = np.random.default_rng(seed)
    p_open = rng.uniform(0.2, 0.5, n)
    d = rng.normal(0, 0.02, n)
    s = np.where(rng.random(n) < 0.3, rng.uniform(0.02, 0.10, n), 0.0)
    p_dec = p_open + d
    p_close = np.clip(p_dec + absorb * s + rng.normal(0, 0.01, n), 0.01, 0.99)
    y = (rng.random(n) < np.clip(p_open + d + s, 0, 1)).astype(float)
    return y, p_close, s, d, p_close - p_dec, np.repeat(np.arange(n // 30), 30)[:n]


def test_residual_test_detects_an_unpriced_absence():
    y, pc, s, d, _, cl = _market(absorb=0.0)
    r = E.residual_test(y, pc, s, d, cl, n_boot=400)
    assert r["coef"]["our_shift"] > 0 and r["p_one_sided_b_le_0"] < 0.05


def test_residual_test_null_when_market_prices_it():
    p = []
    for seed in range(5):
        y, pc, s, d, _, cl = _market(absorb=1.0, seed=seed)
        p.append(E.residual_test(y, pc, s, d, cl, n_boot=300)["p_one_sided_b_le_0"])
    assert sum(x < 0.05 for x in p) <= 1


def test_controlling_for_the_post_decision_move_would_be_biased():
    # why residual_test controls for the PRIOR move only: with the post-decision move as a control,
    # a market that prices the absence perfectly still shows b ~ 1
    y, pc, s, d, post, cl = _market(n=90000, absorb=1.0, seed=9)
    biased = E.residual_test(y, pc, s, post, cl, n_boot=50)
    proper = E.residual_test(y, pc, s, d, cl, n_boot=50)
    assert biased["coef"]["our_shift"] > 0.5
    assert abs(proper["coef"]["our_shift"]) < 0.3


def test_line_move_slope_tracks_absorption():
    for absorb in (0.0, 1.0):
        _, _, s, _, mv, cl = _market(absorb=absorb, seed=4)
        r = E.line_move_test(s, mv, cl, n_boot=300)
        assert r["slope"] == pytest.approx(absorb, abs=0.1)


def test_clv_and_too_few():
    assert np.isnan(E.clv_log([2.0, 0.0], [1.9, 1.5])[1])
    assert E.clv_log([2.0], [2.0])[0] == 0.0
    assert E.takeable_clv([2.0, 2.1], [1.9, 2.0], [1, 1])["status"] == "TOO_FEW"
    r = E.takeable_clv(np.full(100, 2.1), np.full(100, 2.0), np.repeat(np.arange(10), 10), n_boot=200)
    assert r["mean_clv_log"] > 0 and r["p_one_sided_le_0"] == 0.0


def test_min_n():
    n1 = E.min_n_for_mean(1.0, 0.1, alpha=0.05, power=0.8)
    assert 610 <= n1 <= 625                          # (1.645 + 0.842)^2 / 0.01 = 618.3
    assert E.min_n_for_mean(1.0, 0.1, alpha=0.05, power=0.8, design_effect=2.0) == pytest.approx(2 * n1, abs=2)


# ── readiness gate: fail closed ──────────────────────────────────────────────────────────────────
def _measured(v=0.5):
    return {c: {"value": v} for c in R.CHECKS}


def test_shipped_thresholds_are_all_owner_decisions():
    assert set(R.THRESHOLDS) == {k for k, _ in R.CHECKS.values()}
    assert all(v is None for v in R.THRESHOLDS.values())
    res = R.evaluate(_measured())
    assert not res["ready"]
    assert {c["status"] for c in res["checks"].values()} == {R.PENDING}


def test_gate_ready_only_when_every_check_passes():
    th = {k: (0.9 if d == "max" else 0.1) for k, d in R.CHECKS.values()}
    assert R.evaluate(_measured(), th)["ready"]
    m = _measured()
    m["counts_verified"] = {"value": 0.95}                # too many unverified rows
    res = R.evaluate(m, th)
    assert not res["ready"] and res["checks"]["counts_verified"]["status"] == R.FAIL
    m = _measured()
    m["injury_lists_pre_kickoff"] = {"value": None}       # input missing
    res = R.evaluate(m, th)
    assert not res["ready"] and res["checks"]["injury_lists_pre_kickoff"]["status"] == R.MISSING
    m = _measured()
    del m["prop_odds_identity"]                           # a check nobody measured
    assert not R.evaluate(m, th)["ready"]


def test_cli_exits_nonzero_on_empty_inputs(tmp_path, monkeypatch, capsys):
    from src.props_matchup import __main__ as M
    monkeypatch.setattr(cfg, "V9_LOCAL", tmp_path / "v9")
    monkeypatch.setattr(cfg, "BASE_DIR", tmp_path / "pro")
    assert M.main(["--check-readiness"]) == 1
    out = capsys.readouterr().out
    assert "NOT READY" in out and "MISSING_INPUT" in out


def test_verified_sources_match_v9():
    v = I.v9_verified_sources()
    if v is None:
        pytest.skip("no v9 checkout at V9_LOCAL")
    assert v == I.VERIFIED_SOURCES

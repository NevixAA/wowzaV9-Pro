"""Tests for src/studies/monthly_learning.py (September vs October 2026 learning evidence)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.studies import monthly_learning as M


def _bets(rows):
    df = pd.DataFrame(rows, columns=["match_date", "entry_odds", "result"])
    df["md"] = pd.to_datetime(df["match_date"])
    df["settled"] = df["result"].isin(["WIN", "LOSS"])
    df["pnl_first"] = M._settle_at(df["entry_odds"], df["result"])
    df["pnl_ledger"] = df["pnl_first"]
    df["clv_first"] = 0.0
    df["clv_valid"] = True
    return df


def test_settlement_uses_first_logged_price():
    pnl = M._settle_at([2.0, 1.5, 3.0], ["WIN", "LOSS", "VOID"])
    assert list(pnl) == [1.0, -1.0, 0.0]


def test_bet_metrics_counts_and_roi():
    df = _bets([("2026-09-05", 2.0, "WIN"), ("2026-09-05", 2.0, "LOSS"), ("2026-09-12", 2.5, "LOSS"),
                ("2026-09-12", 2.0, "VOID")])
    m = M.bet_metrics(df)
    assert m["n"] == 3 and m["wins"] == 1 and m["voids"] == 1
    assert m["pnl_u"] == -1.0 and abs(m["roi"] - (-1 / 3)) < 1e-4
    assert m["matchdays"] == 2


def test_matchday_bootstrap_treats_a_day_as_one_draw():
    # one day of 50 identical wins + one day of 50 identical losses: only 2 blocks, so the CI must be wide
    pnl = np.r_[np.ones(50), -np.ones(50)]
    day = np.r_[["d1"] * 50, ["d2"] * 50]
    lo, hi = M.boot_roi(pnl, day)
    assert lo <= -0.9 and hi >= 0.9


def test_category_requires_sample_floor_and_ci():
    big = {"n": 40, "matchdays": 10, "roi": 0.1}
    assert M.category({"sep": {"n": 5, "matchdays": 2}, "oct": big, "delta_roi_ci90": [0.1, 0.5]}) == "TOO_SMALL"
    assert M.category({"sep": big, "oct": big, "delta_roi_ci90": [0.01, 0.3]}) == "IMPROVED"
    assert M.category({"sep": big, "oct": big, "delta_roi_ci90": [-0.3, -0.01]}) == "DETERIORATED"
    assert M.category({"sep": big, "oct": big, "delta_roi_ci90": [-0.1, 0.2]}) == "STABLE"


def test_verdict_only_when_ci_excludes_zero():
    assert M.verdict([0.01, 0.2]) == "IMPROVED"
    assert M.verdict([-0.2, -0.01]) == "DETERIORATED"
    assert M.verdict([-0.1, 0.1]) == "MIXED"
    assert M.verdict([None, None]) == "NOT COMPARABLE"


def test_poisson_binomial_matches_binomial():
    from math import comb
    p, n, k = 0.4, 20, 5
    exact = sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))
    assert abs(M.poisson_binomial_cdf(k, [p] * n) - exact) < 1e-12


def test_ece_and_log_loss_basics():
    p = np.array([0.5, 0.5, 0.5, 0.5])
    y = np.array([1, 0, 1, 0])
    assert M.ece(p, y) == 0.0
    assert abs(M.ll(p, y).mean() - np.log(2)) < 1e-9
    assert abs(M.brier(p, y).mean() - 0.25) < 1e-12


def test_pattern_labels():
    assert M.pattern({"sep": {"roi": 0.1}, "oct": {"roi": -0.1}}) == "POS_TO_NEG"
    assert M.pattern({"sep": {"roi": -0.1}, "oct": {"roi": 0.1}}) == "NEG_TO_POS"


def test_synthetic_and_first_half_constants_match_v9_and_pro():
    from src import quality as q
    assert M.BTTS_YES_MAX == q.BTTS_YES_MAX
    assert M.SYNTHETIC_ODDS == {"btts": 1.85, "over15": 1.40, "over35": 2.60}
    assert M.RELIABLE_FROM == "2026-09-24"

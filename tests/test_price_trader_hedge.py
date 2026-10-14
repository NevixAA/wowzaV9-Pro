"""Hedge maths checked against hand-computed cases.

    python -m pytest tests/test_price_trader_hedge.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.price_trader import hedge as H  # noqa: E402


def test_no_commission_dutch_by_hand():
    # back 1 @ 2.20; opposite later @ 2.00 -> hedge 1.10; both outcomes +0.10
    r = H.outcomes(2.20, 2.00)
    assert r["hedge_stake"] == pytest.approx(1.10)
    assert r["if_selection_wins"] == pytest.approx(1.20 - 1.10)
    assert r["if_selection_loses"] == pytest.approx(1.10 * 1.00 - 1.0)
    assert r["locked"] == pytest.approx(0.10) and r["capital"] == pytest.approx(2.10)


def test_fully_greened_is_result_independent():
    for o, u, c in ((2.04, 1.96, 0.0), (1.85, 2.30, 0.02), (3.1, 1.6, 0.05)):
        r = H.outcomes(o, u, c)
        assert r["if_selection_wins"] == pytest.approx(r["if_selection_loses"], abs=1e-12)


def test_commission_by_hand():
    # back 1 @ 2.10, opposite on exchange @ 2.00, 2% commission:
    # h = 2.10 / (1 + 1*0.98) = 1.060606...; win = 1.10 - h; lose = h*1*0.98 - 1
    h = 2.10 / 1.98
    r = H.outcomes(2.10, 2.00, 0.02)
    assert r["hedge_stake"] == pytest.approx(h)
    assert r["locked"] == pytest.approx(1.10 - h)


def test_losing_hedge_and_lay_equivalence():
    assert H.locked_roi(2.00, 1.90) < 0                       # price moved against us
    assert H.lay_equivalent_back(2.0) == pytest.approx(2.0)   # lay @2 == back opposite @2
    assert H.lay_equivalent_back(1.5) == pytest.approx(3.0)


def test_partial_keeps_exposure():
    r = H.outcomes(2.20, 2.00, fraction=0.5)
    assert r["if_selection_wins"] != pytest.approx(r["if_selection_loses"])
    assert r["if_selection_wins"] == pytest.approx(1.20 - 0.55)
    assert r["if_selection_loses"] == pytest.approx(0.55 - 1.0)


def test_instant_arb_margin():
    assert H.instant_arb_margin(2.10, 2.10) > 0               # 1/2.1 + 1/2.1 < 1
    assert H.instant_arb_margin(1.90, 1.90) < 0

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


@pytest.mark.parametrize("c, s, locked", [
    # Back 2.00 / Lay 1.80: S = 2/(1.8-c); both branches equal (hand-computed)
    (0.00, 2 / 1.80, 1 - (2 / 1.80) * 0.8),
    (0.02, 2 / 1.78, 1 - (2 / 1.78) * 0.8),
    (0.05, 2 / 1.75, 1 - (2 / 1.75) * 0.8),
])
def test_back_to_lay_2_00_lay_1_80(c, s, locked):
    r = H.back_to_lay(1.0, 2.00, 1.80, c)
    assert r["lay_stake"] == pytest.approx(s)
    assert r["profit_if_selection_wins"] == pytest.approx(locked)
    assert r["profit_if_selection_loses"] == pytest.approx(locked)
    assert r["required_exchange_liability"] == pytest.approx(s * 0.8)
    assert r["full_green"] and r["minimum_locked_profit"] > 0


def test_back_to_lay_same_price_is_never_green():
    r0 = H.back_to_lay(1.0, 2.00, 2.00, 0.0)
    assert r0["minimum_locked_profit"] == pytest.approx(0.0) and not r0["full_green"]
    for c in (0.02, 0.05):
        r = H.back_to_lay(1.0, 2.00, 2.00, c)
        assert r["minimum_locked_profit"] == pytest.approx(-c / (2 - c)) and not r["full_green"]


@pytest.mark.parametrize("c", [0.0, 0.02, 0.05])
def test_back_to_lay_adverse_move_loses_both_ways(c):
    r = H.back_to_lay(1.0, 2.00, 2.20, c)
    assert r["profit_if_selection_wins"] < 0 and r["profit_if_selection_loses"] < 0
    assert not r["full_green"]


def test_back_to_lay_3_50_lay_2_80():
    r = H.back_to_lay(1.0, 3.50, 2.80, 0.0)
    assert r["lay_stake"] == pytest.approx(1.25) and r["minimum_locked_profit"] == pytest.approx(0.25)
    r5 = H.back_to_lay(1.0, 3.50, 2.80, 0.05)
    assert r5["lay_stake"] == pytest.approx(3.5 / 2.75)
    assert r5["profit_if_selection_wins"] == pytest.approx(r5["profit_if_selection_loses"])
    assert r5["minimum_locked_profit"] == pytest.approx(2.5 - (3.5 / 2.75) * 1.8)
    assert r5["roi_on_back_stake"] == pytest.approx(r5["minimum_locked_profit"])


@pytest.mark.parametrize("o, lay, c", [(2.0, 1.8, 0.0), (2.0, 1.8, 0.05), (3.5, 2.8, 0.02), (1.7, 1.55, 0.03)])
def test_lay_equals_backing_the_opposite_at_the_equivalent_price(o, lay, c):
    """Laying S at L is the same bet as backing S' at L/(L-1) — both routes must lock the same."""
    assert H.back_to_lay(1.0, o, lay, c)["minimum_locked_profit"] == pytest.approx(
        H.outcomes(o, H.lay_equivalent_back(lay), c)["locked"])


def test_commission_only_on_the_winning_exchange_branch():
    r = H.back_to_lay(10.0, 2.00, 1.80, 0.05)
    s = r["lay_stake"]
    # selection wins: no commission term at all
    assert r["profit_if_selection_wins"] == pytest.approx(10.0 - s * 0.8)
    # selection loses: commission only on the lay's winnings
    assert r["profit_if_selection_loses"] == pytest.approx(s * 0.95 - 10.0)


def test_instant_arb_margin():
    assert H.instant_arb_margin(2.10, 2.10) > 0               # 1/2.1 + 1/2.1 < 1
    assert H.instant_arb_margin(1.90, 1.90) < 0

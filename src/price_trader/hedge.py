"""Back-to-lay / back-to-back hedge arithmetic (decimal odds). Pure functions, unit-tested.

Two ways to green an early BACK of side S at odds O (stake 1):

1. DUTCH at a bookmaker - back the EXACT opposite side S' (Over 2.5 <-> Under 2.5, BTTS Yes <-> No)
   at odds U. Equal payout: hedge stake h = O / U.
       S wins : O - 1 - h            S' wins: h*U - 1 - h... = h(U-1) - 1
   with h = O/U both equal O - 1 - O/U  (= locked profit per 1 unit backed).
2. EXCHANGE - back S' on an exchange (identical to laying S) where commission c is charged on the
   exchange leg's NET winnings only:
       S wins : O - 1 - h                      (exchange leg loses its stake h, no commission)
       S' wins: h(U - 1)(1 - c) - 1            (exchange leg wins, pays commission)
   equal when h = O / (1 + (U - 1)(1 - c)).  With c = 0 this is O/U, i.e. case 1.
   A true LAY of S at lay odds L equals backing S' at U = L / (L - 1); lay liability = h_lay (L - 1).

PARTIAL hedge of fraction f in [0, 1]: hedge stake f*h -> profit if S wins O - 1 - f h, if S' wins
f h (U - 1)(1 - c) - 1. Only f = 1 is "locked"; anything less keeps football exposure.

Capital: a dutch needs 1 + h up front. ROI is reported on the back stake (1) and on capital (1 + h).
"""
from __future__ import annotations


def hedge_stake(o_back: float, u_opposite: float, commission: float = 0.0) -> float:
    if o_back <= 1 or u_opposite <= 1:
        raise ValueError("decimal odds must exceed 1")
    return o_back / (1.0 + (u_opposite - 1.0) * (1.0 - commission))


def outcomes(o_back: float, u_opposite: float, commission: float = 0.0, fraction: float = 1.0,
             stake: float = 1.0) -> dict:
    """P/L in each football outcome for a back of `stake` at o_back, hedged by `fraction`."""
    h = hedge_stake(o_back, u_opposite, commission) * fraction * stake
    win = stake * (o_back - 1.0) - h
    lose = h * (u_opposite - 1.0) * (1.0 - commission) - stake
    return {"hedge_stake": h, "if_selection_wins": win, "if_selection_loses": lose,
            "locked": min(win, lose), "capital": stake + h}


def locked_roi(o_back: float, u_opposite: float, commission: float = 0.0) -> float:
    """Guaranteed profit per 1 unit backed when fully greened (both outcomes equal)."""
    return outcomes(o_back, u_opposite, commission)["locked"]


def lay_equivalent_back(lay_odds: float) -> float:
    """Backing the opposite at U = L/(L-1) is the same bet as laying at L."""
    if lay_odds <= 1:
        raise ValueError("lay odds must exceed 1")
    return lay_odds / (lay_odds - 1.0)


def back_to_lay(back_stake: float, back_odds: float, lay_odds: float, commission: float = 0.0) -> dict:
    """BACK `back_stake` at a bookmaker at `back_odds`, then LAY the SAME selection on an exchange at
    `lay_odds`, with exchange commission charged on NET exchange winnings only (Betfair-style: one bet
    per market, so the lay's net win IS the market's net win).

        selection wins : back wins  B(Ob-1); lay loses its liability S(Ol-1); no commission
        selection loses: back loses B;        lay wins S, commission c on S
        equal when B(Ob-1) - S(Ol-1) = S(1-c) - B   =>   S = B * Ob / (Ol - c)

    No blanket (1-c) on every branch: commission only ever touches the branch where the exchange leg
    WINS. `FULL_GREEN` only when BOTH outcomes are strictly positive after commission.
    """
    if back_odds <= 1 or lay_odds <= 1 or back_stake <= 0:
        raise ValueError("odds must exceed 1 and stake must be positive")
    if not 0 <= commission < 1:
        raise ValueError("commission must be in [0, 1)")
    s = back_stake * back_odds / (lay_odds - commission)
    win = back_stake * (back_odds - 1.0) - s * (lay_odds - 1.0)
    lose = s * (1.0 - commission) - back_stake
    locked = min(win, lose)
    return {"lay_stake": s, "required_exchange_liability": s * (lay_odds - 1.0),
            "profit_if_selection_wins": win, "profit_if_selection_loses": lose,
            "minimum_locked_profit": locked, "roi_on_back_stake": locked / back_stake,
            "full_green": bool(win > 0 and lose > 0)}


def instant_arb_margin(best_side: float, best_opposite: float) -> float:
    """1 - (1/O + 1/U): > 0 means both sides can be covered now for a guaranteed profit
    (before limits and commission). The return on total stake is margin / (1 - margin)."""
    return 1.0 - (1.0 / best_side + 1.0 / best_opposite)

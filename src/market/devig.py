"""
De-vigging: bookmaker odds -> fair probability.
==============================================
Ported from wowza-v11/src/edge_engine.py (Prompt 1 section 9). The algorithm is unchanged —
it is in production and the point of a port is not to reinvent it — but the contract is
tightened in two ways Pro depends on:

  * every function returns None rather than a guess when it cannot answer honestly, and
  * the REASON is available separately, so a row can be quarantined with a cause instead of
    silently dropped (Prompt 2 section 16).

OLD  v11: power_devig(o, u) -> float | None, reason discarded.
NEW  Pro: devig(o, u) -> DevigResult(prob, method, reason, valid).
WHY  Pro must store why a market was unusable; "None" is not a reason, and an unpriced row
     and an invalid row need opposite fixes.
RISK Low. The numeric path is identical; only the wrapper is new. Verified against v11's
     implementation on a grid of odds pairs (see tests/test_market.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# A two-sided market whose implied probabilities sum to less than this is not a real market —
# it would be an arbitrage. Almost always a mapping error (two different lines paired, or an
# Over quoted against the wrong Under).
MIN_OVERROUND = 1.0
# Above this the pair is either a stale quote or a market we should not model against.
MAX_OVERROUND = 1.25


@dataclass(frozen=True)
class DevigResult:
    prob: float | None          # fair probability of the OVER/YES side
    overround: float | None
    method: str                 # "power" | "proportional" | "none"
    valid: bool
    reason: str                 # "" when valid; a QUALITY_FLAGS-style code otherwise


def _implied(odds) -> float | None:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    return 1.0 / o if o > 1.0 else None


def overround(over_odds, under_odds) -> float | None:
    a, b = _implied(over_odds), _implied(under_odds)
    return None if a is None or b is None else a + b


def proportional_devig(over_odds, under_odds) -> float | None:
    """Multiplicative normalisation. Kept for comparison against the power method."""
    a, b = _implied(over_odds), _implied(under_odds)
    if a is None or b is None:
        return None
    return a / (a + b)


def power_devig(over_odds, under_odds, tol: float = 1e-9) -> float | None:
    """Solve alpha such that (1/o_over)^a + (1/o_under)^a = 1, return (1/o_over)^a.

    Preferred over proportional normalisation because bookmaker margin is not applied evenly
    across a favourite–longshot pair: proportional de-vigging systematically overstates the
    longshot. Bisection on [0.5, 5.0] is ample for real football prices.
    """
    ro, ru = _implied(over_odds), _implied(under_odds)
    if ro is None or ru is None:
        return None
    lo, hi = 0.5, 5.0
    for _ in range(100):
        a = (lo + hi) / 2
        s = ro ** a + ru ** a
        if abs(s - 1.0) < tol:
            break
        if s > 1.0:
            lo = a          # sum too large -> raise alpha, which shrinks both probabilities
        else:
            hi = a
    return ro ** ((lo + hi) / 2)


def devig(over_odds, under_odds) -> DevigResult:
    """The function callers should use. Never raises; never guesses.

    A one-sided market is NOT de-vigged. v11's rule, kept deliberately: with only an Over
    price there is no way to separate the bookmaker's margin from the probability, so any
    number produced would be the margin masquerading as an edge.
    """
    ro, ru = _implied(over_odds), _implied(under_odds)
    if ro is None and ru is None:
        return DevigResult(None, None, "none", False, "MARKET_MAPPING_INVALID")
    if ru is None:
        return DevigResult(None, None, "none", False, "MISSING_OPPOSITE_SIDE")
    if ro is None:
        return DevigResult(None, None, "none", False, "MISSING_OPPOSITE_SIDE")

    ovr = ro + ru
    if ovr < MIN_OVERROUND:
        # Sum below 1.0 implies a guaranteed profit; in practice a paired-wrong line.
        return DevigResult(None, ovr, "none", False, "ODDS_ORDER_INVALID")
    if ovr > MAX_OVERROUND:
        return DevigResult(None, ovr, "none", False, "STALE_PRICE")

    p = power_devig(over_odds, under_odds)
    if p is None or not (0.0 < p < 1.0):
        return DevigResult(None, ovr, "none", False, "MARKET_MAPPING_INVALID")
    return DevigResult(round(p, 6), round(ovr, 6), "power", True, "")

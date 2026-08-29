"""
Common market-event schema (bet-builder brief, Phase 1).
========================================================

ONE DEFINITION OF EVERY BETTABLE EVENT, DERIVED FROM ONE SCORELINE.

The bet-builder problem is a joint-probability problem, and the single most dangerous thing
that can happen to it is two markets being settled from two different sources. If `O2.5` comes
from one table and `BTTS` from another, any dependence measured between them is partly an
artefact of the disagreement between those tables rather than football.

So every event here is a pure function of `(home_goals, away_goals)` on one row of
`team_match_stats`, which carries 23,604 settled fixtures with **100% goal coverage** spanning
2023-01-26 to 2026-08-25 across 23 leagues. One scoreline determines, simultaneously and without
any modelling:

    2-1  ->  HOME win, not DRAW, not AWAY, O1.5 yes, O2.5 yes, O3.5 no, BTTS yes

That coherence is the whole point. It is also what makes the 1X2 brief and the builder brief the
same problem underneath: both are questions about a joint distribution over scorelines.

WHY NOT USE THE SETTLEMENTS TABLE

`settlements` holds 63,484 rows but is overwhelmingly OU25 (62,820) with only 469 OVER15 and 195
BTTS, and it records BET outcomes -- so it exists only where a bet existed, which is a selected
subset and useless for measuring unconditional dependence. `team_match_stats` is the unselected
population.

HALF-TIME MARKETS ARE ABSENT ON PURPOSE

`team_match_stats` carries no half-time score, so HT_OU05 / HT_OU15 cannot be derived here. They
are declared in `HT_EVENTS` with `available=False` rather than omitted, so the gap is visible in
the coverage report instead of looking like an oversight. Do not approximate them from full-time
goals.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SCHEMA_VERSION = "1.0.0"


def _tot(h, a):
    return h + a


# Every event: name -> (callable(home_goals, away_goals) -> bool, human label, family).
# Callables take VECTORS so the whole table settles at once.
EVENTS: dict[str, tuple] = {
    # ── Totals ───────────────────────────────────────────────────────────────
    "O15": (lambda h, a: _tot(h, a) >= 2, "Over 1.5", "TOTALS"),
    "U15": (lambda h, a: _tot(h, a) <= 1, "Under 1.5", "TOTALS"),
    "O25": (lambda h, a: _tot(h, a) >= 3, "Over 2.5", "TOTALS"),
    "U25": (lambda h, a: _tot(h, a) <= 2, "Under 2.5", "TOTALS"),
    "O35": (lambda h, a: _tot(h, a) >= 4, "Over 3.5", "TOTALS"),
    "U35": (lambda h, a: _tot(h, a) <= 3, "Under 3.5", "TOTALS"),
    # ── Both teams to score ──────────────────────────────────────────────────
    "BTTS": (lambda h, a: (h >= 1) & (a >= 1), "BTTS Yes", "BTTS"),
    "BTTS_NO": (lambda h, a: (h == 0) | (a == 0), "BTTS No", "BTTS"),
    # ── Match result (1X2) ───────────────────────────────────────────────────
    "HOME": (lambda h, a: h > a, "Home win", "1X2"),
    "DRAW": (lambda h, a: h == a, "Draw", "1X2"),
    "AWAY": (lambda h, a: h < a, "Away win", "1X2"),
    # ── Double chance, DERIVED (brief 62): research only until real DC odds
    #    are collected. Present so the joint model can be checked against them.
    "1X": (lambda h, a: h >= a, "Home or draw", "DOUBLE_CHANCE"),
    "X2": (lambda h, a: h <= a, "Draw or away", "DOUBLE_CHANCE"),
    "12": (lambda h, a: h != a, "Home or away", "DOUBLE_CHANCE"),
}

# Declared but NOT derivable from this table. Kept visible rather than omitted.
HT_EVENTS = {
    "HT_O05": "Half-time Over 0.5 — no half-time score in team_match_stats",
    "HT_O15": "Half-time Over 1.5 — no half-time score in team_match_stats",
}

# Logical complements: exactly one of each pair occurs, so P(A and B) == 0 by construction.
# Pairing them is not a builder, it is a contradiction, and it must never reach a candidate.
COMPLEMENTS = {("O15", "U15"), ("O25", "U25"), ("O35", "U35"), ("BTTS", "BTTS_NO")}

# NESTED pairs: one event implies the other, so the intersection collapses to the stricter leg
# and the "combination" is a single bet wearing two labels (brief section 8). Stored as
# (implier, implied): whenever `implier` is true, `implied` is true.
NESTED = {
    ("O25", "O15"), ("O35", "O15"), ("O35", "O25"),
    ("U15", "U25"), ("U15", "U35"), ("U25", "U35"),
    ("HOME", "1X"), ("DRAW", "1X"), ("DRAW", "X2"), ("AWAY", "X2"),
    ("HOME", "12"), ("AWAY", "12"),
    ("BTTS", "O15"),          # both teams scoring means at least two goals
}

# Monotonic chains that any coherent probability set must respect (brief section 3).
MONOTONE_CHAINS = [("O15", "O25", "O35"), ("U35", "U25", "U15")]


def settle(df: pd.DataFrame, *, home_col: str = "home_goals",
           away_col: str = "away_goals") -> pd.DataFrame:
    """Add one boolean column per event, all from the same scoreline.

    Rows without a complete scoreline are dropped with a count, never settled as False -- a
    missing result and a losing result are different facts and conflating them would bias every
    dependency downward.
    """
    d = df.copy()
    h = pd.to_numeric(d[home_col], errors="coerce")
    a = pd.to_numeric(d[away_col], errors="coerce")
    keep = h.notna() & a.notna()
    dropped = int((~keep).sum())
    d, h, a = d[keep].copy(), h[keep].astype(int), a[keep].astype(int)
    for name, (fn, _lbl, _fam) in EVENTS.items():
        d[f"ev_{name}"] = fn(h, a).astype(bool)
    d["_total_goals"] = (h + a).values
    d.attrs["dropped_no_scoreline"] = dropped
    d.attrs["schema_version"] = SCHEMA_VERSION
    return d


def check_coherence(d: pd.DataFrame) -> list[str]:
    """Sanity-check the settled columns. Returns a list of violations, empty when clean.

    These are checks on OBSERVED outcomes, so any failure is a bug in `settle` or in the source
    data, not a modelling question -- which is exactly why it is worth asserting.
    """
    out = []
    # Complements must partition the sample.
    for a, b in COMPLEMENTS:
        both = int((d[f"ev_{a}"] & d[f"ev_{b}"]).sum())
        neither = int((~d[f"ev_{a}"] & ~d[f"ev_{b}"]).sum())
        if both or neither:
            out.append(f"COMPLEMENT_BROKEN {a}/{b}: both={both} neither={neither}")
    # 1X2 must be exactly one of three.
    n1x2 = (d["ev_HOME"].astype(int) + d["ev_DRAW"].astype(int) + d["ev_AWAY"].astype(int))
    if int((n1x2 != 1).sum()):
        out.append(f"1X2_NOT_EXCLUSIVE: {int((n1x2 != 1).sum())} row(s)")
    # Nesting must hold on every row.
    for imp, ied in NESTED:
        bad = int((d[f"ev_{imp}"] & ~d[f"ev_{ied}"]).sum())
        if bad:
            out.append(f"NESTING_BROKEN {imp}=>{ied}: {bad} row(s)")
    # Empirical monotonicity of the observed rates.
    for chain in MONOTONE_CHAINS:
        rates = [d[f"ev_{c}"].mean() for c in chain]
        if any(rates[i] < rates[i + 1] - 1e-12 for i in range(len(rates) - 1)):
            out.append(f"MONOTONICITY_VIOLATION {chain}: {[round(r, 4) for r in rates]}")
    return out


def frechet_bounds(p_a: float, p_b: float) -> tuple[float, float]:
    """Valid range for P(A and B) given the marginals (brief section 39).

    Any joint estimate outside this is not merely inaccurate, it is impossible, and the
    generator must reject it rather than clamp it silently.
    """
    return (max(0.0, p_a + p_b - 1.0), min(p_a, p_b))


# Every event is a function of (home_goals, away_goals), so logical relationships between events
# are decidable EXACTLY by evaluating them over the space of scorelines. 0-14 goals per side
# covers every result in 23,604 observed fixtures with enormous margin (the highest total is far
# below 28) and the relations are structural, so a wider grid changes nothing.
_MAX_G = 14
_GRID = [(h, a) for h in range(_MAX_G + 1) for a in range(_MAX_G + 1)]


def _support(name: str) -> frozenset:
    """The set of scorelines on which this event is TRUE."""
    fn = EVENTS[name][0]
    return frozenset((h, a) for h, a in _GRID if bool(fn(np.int64(h), np.int64(a))))


_SUPPORT = {k: _support(k) for k in EVENTS}


def is_redundant(a: str, b: str) -> str | None:
    """Why this pair must not be offered as a two-leg builder, or None if it is legitimate.

    DERIVED FROM THE OUTCOME SPACE, not from a hand-written list. The first version enumerated
    the relationships by hand and silently missed four whole classes of them, which the
    dependency matrix then reported as findings:

        U15 + BTTS_NO   ratio 2.14, with p_joint EXACTLY equal to p_a -- U15 implies BTTS_NO,
                        because two teams cannot both score inside one goal
        HOME + X2       phi = -1.0, mutually exclusive by construction
        U15 + O25       ratio 0.0, one says at most one goal and the other at least three
        U25 + O35       ratio 0.0, same contradiction

    None of those are dependencies; they are definitions, and a hand-maintained list will keep
    missing them as markets are added. Set containment over the scoreline grid decides all of it
    exactly and stays correct when a new market is defined.
    """
    if a == b:
        return "IDENTICAL_LEGS"
    sa, sb = _SUPPORT[a], _SUPPORT[b]
    if not (sa & sb):
        return "MUTUALLY_EXCLUSIVE"                 # joint probability is exactly zero
    if sa <= sb:
        return f"NESTED_COLLAPSES_TO_{a}"           # A implies B, so A and B == A
    if sb <= sa:
        return f"NESTED_COLLAPSES_TO_{b}"
    return None

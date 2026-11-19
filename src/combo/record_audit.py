"""
Bet Builder record audit - corrections BESIDE the settled record, never over it.
===============================================================================
Data Truth round 3 (2026-11-02). Three defects in rows already on the record; each is marked in a
new column and `combo_result` / `joint_probability` keep exactly what was written.

1. INVALID_MODEL - side-specific legs read off a fit with no side-specific input.
   score_model.fit() fits lambda_home/lambda_away to O1.5/O2.5/O3.5/BTTS, all symmetric in the two
   rates, so swapping them leaves the fit unchanged and the home/away split is the optimiser's seed
   (1.35/1.15), not data. score_model.identified_markets() has refused those legs since the 2026-11-01
   fix, but 8,370 combos built before it (HOME / AWAY / 1X / X2 / 12 / HOME_O05 / AWAY_O05 /
   HOME_O15 / AWAY_O15) are still on the record. They are marked, kept, and left out of every
   headline.

2. VOID legs. settle.combine() settles a combo on its remaining legs when a player leg voids
   (bookmaker practice), so a combo can be WON while its claimed joint probability covers a leg that
   never ran. tip_scoreboard already reports those apart from the headline; performance() and the
   CSV counted them as plain wins (3,016 such WON rows). Same rule everywhere now: a decided combo
   with a voided leg is EXCLUDED_VOID_LEG in `scoreboard_result`.

3. FRECHET - a recorded joint above its smaller leg (or below p_a + p_b - 1) is impossible.
   match_picture._joint refuses them from now on; the 92 recorded rows are marked.

`scoreboard_result` is the ONE column every headline reads (performance(), tip_scoreboard):
WON / LOST / VOID / UNKNOWN as recorded, or EXCLUDED_<reason> for the three cases above.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

AUDIT_VERSION = "1.0.0"

#: Legs whose probability depends on WHICH side is stronger - unidentified by a symmetric fit.
SIDE_SPECIFIC_MARKETS = frozenset({"HOME", "AWAY", "1X", "X2", "12",
                                   "HOME_O05", "AWAY_O05", "HOME_O15", "AWAY_O15"})

INVALID_MODEL = "INVALID_MODEL"
EXCLUDED_INVALID_MODEL = "EXCLUDED_INVALID_MODEL"
EXCLUDED_FRECHET = "EXCLUDED_FRECHET_VIOLATION"
EXCLUDED_VOID_LEG = "EXCLUDED_VOID_LEG"

_LEG_MARKET = re.compile(r"^leg\d+_market$")
_LEG_P = re.compile(r"^leg\d+_(p|model_p)$")


def _leg_market_cols(d: pd.DataFrame) -> list[str]:
    return sorted(c for c in d.columns if _LEG_MARKET.match(c))


def annotate(settled: pd.DataFrame) -> pd.DataFrame:
    """The record with the audit columns added (recomputed every pass; originals untouched)."""
    if settled is None:
        return settled
    d = settled.copy()
    if d.empty:
        for c in ("model_validity", "frechet_violation", "void_legs", "scoreboard_result",
                  "audit_note", "audit_version"):
            d[c] = pd.Series(dtype=object)
        return d
    mk = _leg_market_cols(d)
    side = (d[mk].astype(str).isin(SIDE_SPECIFIC_MARKETS).any(axis=1) if mk
            else pd.Series(False, index=d.index))
    pc = [c for c in d.columns if _LEG_P.match(c)]
    jp = pd.to_numeric(d.get("joint_probability"), errors="coerce") if "joint_probability" in d else \
        pd.Series(np.nan, index=d.index)
    if pc:
        legp = d[pc].apply(pd.to_numeric, errors="coerce")
        hi = legp.min(axis=1)
        lo = (legp.sum(axis=1) - (legp.notna().sum(axis=1) - 1)).clip(lower=0)
        frechet = jp.notna() & hi.notna() & ((jp > hi + 1e-9) | (jp < lo - 1e-9))
    else:
        frechet = pd.Series(False, index=d.index)
    res = d["combo_result"].astype(str) if "combo_result" in d else pd.Series("", index=d.index)
    n_void = (d["leg_results"].fillna("").astype(str).str.count("=VOID") if "leg_results" in d
              else pd.Series(0, index=d.index))
    decided = res.isin(["WON", "LOST"])

    d["model_validity"] = np.where(side, INVALID_MODEL, "OK")
    d["frechet_violation"] = frechet.astype(bool)
    d["void_legs"] = n_void.astype(int)
    sb = res.copy()
    sb[decided & (n_void > 0)] = EXCLUDED_VOID_LEG
    sb[frechet] = EXCLUDED_FRECHET
    sb[side] = EXCLUDED_INVALID_MODEL
    d["scoreboard_result"] = sb
    notes = []
    for s_, f_, v_, dec in zip(side, frechet, n_void, decided):
        n = []
        if s_:
            n.append("side-specific leg read off a home/away-symmetric score fit (seed split, not data)")
        if f_:
            n.append("joint probability outside the Frechet bound of its legs")
        if dec and v_ > 0:
            n.append(f"{int(v_)} leg(s) voided - settled on the rest; claimed joint covers every leg")
        notes.append("; ".join(n))
    d["audit_note"] = notes
    d["audit_version"] = AUDIT_VERSION
    return d


def headline(settled: pd.DataFrame) -> pd.DataFrame:
    """Rows a headline may count: decided by `scoreboard_result` (WON/LOST only)."""
    a = annotate(settled)
    if a is None or a.empty:
        return a
    return a[a["scoreboard_result"].isin(["WON", "LOST"])]

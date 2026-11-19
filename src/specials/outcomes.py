"""
Outcome definitions for the specials tracker - ONE definition, used by the model side (probability
mass on a score matrix), the history side (league base rates) and the settlement side (did it happen).

Every outcome is a boolean function of the 90-minute score (home_goals, away_goals). The model's
probability is the mass of the Dixon-Coles score matrix (src/combo/dixon_coles, 0..10 a side) on the
scorelines where the outcome holds; the base rate is the share of the league's own past matches where
it held. Because all three read the same mask, they can never disagree about what an outcome means.

GROUPS (owner 2026-11-09)
  grid      exact scores 0-0 .. 6-6 (49 cells) plus cs_other, so the grid sums to 1
  bands     total goals 0-1 / 2-3 / 4-5 / 6+, and the margin bands per side
  specials  the outcomes a candidate can be flagged on:
              high: ge5, ge6, ge7 (total goals), team_ge4 (either side 4+), margin_ge4
              low:  nil_nil (0-0), tot_le1 (0 or 1 goal)
            plus cs_unusual: the fixture's single most over-represented unusual exact score
            (see UNUSUAL_SCORES), handled in study.py / tracker.py because it is a per-fixture argmax.
"""
from __future__ import annotations

import numpy as np

EXACT_MAX = 6                         # owner: the full grid 0-0 .. 6-6, plus an 'other' bucket
GRID_KEYS = [f"cs_{i}_{j}" for i in range(EXACT_MAX + 1) for j in range(EXACT_MAX + 1)]

BAND_FUNCS = {
    "tot_0_1": lambda h, a: h + a <= 1,
    "tot_2_3": lambda h, a: (h + a >= 2) & (h + a <= 3),
    "tot_4_5": lambda h, a: (h + a >= 4) & (h + a <= 5),
    "tot_6p": lambda h, a: h + a >= 6,
    "draw": lambda h, a: h == a,
    "home_by1": lambda h, a: h - a == 1,
    "home_by2_3": lambda h, a: (h - a >= 2) & (h - a <= 3),
    "home_by4p": lambda h, a: h - a >= 4,
    "away_by1": lambda h, a: a - h == 1,
    "away_by2_3": lambda h, a: (a - h >= 2) & (a - h <= 3),
    "away_by4p": lambda h, a: a - h >= 4,
}

SPECIAL_FUNCS = {
    "ge5": lambda h, a: h + a >= 5,
    "ge6": lambda h, a: h + a >= 6,
    "ge7": lambda h, a: h + a >= 7,
    "team_ge4": lambda h, a: (h >= 4) | (a >= 4),
    "margin_ge4": lambda h, a: np.abs(h - a) >= 4,
    "nil_nil": lambda h, a: (h == 0) & (a == 0),
    "tot_le1": lambda h, a: h + a <= 1,
}
HIGH_SPECIALS = ("ge5", "ge6", "ge7", "team_ge4", "margin_ge4")
LOW_SPECIALS = ("nil_nil", "tot_le1")
SPECIALS = HIGH_SPECIALS + LOW_SPECIALS

# 'Unusual' exact scores: inside the stored grid, at least 5 goals, or both sides 3+ (3-3, 4-3 ...).
UNUSUAL_SCORES = [f"cs_{i}_{j}" for i in range(EXACT_MAX + 1) for j in range(EXACT_MAX + 1)
                  if i + j >= 5 or (i >= 3 and j >= 3)]

OUTCOME_KEYS = GRID_KEYS + ["cs_other"] + list(BAND_FUNCS) + list(SPECIAL_FUNCS)


def _grid_hg_ag(n: int):
    g = np.arange(n)
    return np.meshgrid(g, g, indexing="ij")


def matrix_probs(m: np.ndarray) -> dict[str, float]:
    """Probability of every outcome key read off one normalised score matrix m[i, j]."""
    m = np.asarray(m, dtype=float)
    H, A = _grid_hg_ag(m.shape[0])
    out = {}
    for i in range(EXACT_MAX + 1):
        for j in range(EXACT_MAX + 1):
            out[f"cs_{i}_{j}"] = float(m[i, j])
    out["cs_other"] = float(max(0.0, 1.0 - sum(out[k] for k in GRID_KEYS)))
    for k, f in BAND_FUNCS.items():
        out[k] = float(m[f(H, A)].sum())
    for k, f in SPECIAL_FUNCS.items():
        out[k] = float(m[f(H, A)].sum())
    return out


def score_outcomes(hg, ag) -> dict[str, np.ndarray]:
    """0/1 for every outcome key, vectorised over arrays of 90-minute goals."""
    h = np.asarray(hg, dtype=int)
    a = np.asarray(ag, dtype=int)
    out = {}
    in_grid = (h <= EXACT_MAX) & (a <= EXACT_MAX)
    for i in range(EXACT_MAX + 1):
        for j in range(EXACT_MAX + 1):
            out[f"cs_{i}_{j}"] = ((h == i) & (a == j)).astype(int)
    out["cs_other"] = (~in_grid).astype(int)
    for k, f in BAND_FUNCS.items():
        out[k] = f(h, a).astype(int)
    for k, f in SPECIAL_FUNCS.items():
        out[k] = f(h, a).astype(int)
    return out


def base_rates(hg, ag) -> dict[str, float]:
    """Share of the given (one league's, earlier) matches where each outcome held. Empty -> {}."""
    h = np.asarray(hg)
    if len(h) == 0:
        return {}
    o = score_outcomes(hg, ag)
    return {k: float(v.mean()) for k, v in o.items()}


def unusual_pick(p: dict, base: dict) -> tuple[str | None, float]:
    """The unusual exact score with the largest model / league-base ratio, among scores the league
    has actually produced (base > 0; a zero base has no honest ratio and is skipped, never filled)."""
    best, best_r = None, float("nan")
    for k in UNUSUAL_SCORES:
        b = base.get(k)
        if not b or b <= 0 or k not in p:
            continue
        r = p[k] / b
        if best is None or r > best_r:
            best, best_r = k, r
    return best, best_r

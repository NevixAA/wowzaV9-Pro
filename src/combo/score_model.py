"""
Score distribution — the joint-probability engine (brief sections 4, 59, 60).
============================================================================

WHAT IT DOES

Turns v9's four independent goal opinions for a fixture

    P(O1.5)   P(O2.5)   P(O3.5)   P(BTTS)

into ONE coherent distribution over scorelines, and reads every market off that.

    P(2-1) = 0.081, P(1-1) = 0.114, ...
        -> P(HOME), P(DRAW), P(AWAY)          <- 1X2, which v9 does not model at all
        -> P(O1.5), P(O2.5), P(O3.5), P(BTTS) <- reproduced, now mutually consistent
        -> P(A and B) for ANY pair, EXACTLY   <- no independence assumption anywhere

That last line is the point. The empirical matrix showed independence is wrong for 55 of 63
pairs, by up to +65% and down to -74%. A score distribution does not approximate the joint, it
contains it: P(O2.5 and BTTS) is simply the total mass on scorelines where both hold.

IT INHERITS v9's OPINION, IT DOES NOT REPLACE IT

The brief is explicit (sections 4 and 60): do not automatically replace the specialist models.
So the two Poisson rates are FITTED TO v9's OWN PROBABILITIES rather than to raw team strength.
The distribution is a consistency and dependency layer wrapped around existing opinions, not a
competing forecaster. If v9 says O2.5 is 63%, the fitted distribution says close to 63% too --
and then tells you what O2.5 AND BTTS is, which v9 cannot.

WHY DIXON-COLES AND NOT PLAIN POISSON

Independent Poissons systematically misprice the four lowest scorelines -- 0-0, 1-0, 0-1, 1-1 --
which is precisely where draws and BTTS_NO live. Since draws are the outcome the brief singles
out as fragile (section 57) and BTTS is half of every priority pair (section 33), the low-score
correction is not a refinement here, it is the part that matters. `tau` applies it with a single
extra parameter.

FOUR TARGETS, THREE PARAMETERS

lambda_home, lambda_away and rho are fitted against four probabilities, so the system is
over-determined and the fit is a compromise -- deliberately. A perfect reproduction would mean
v9's four numbers were already coherent, and `fit_quality` reports how far they were from it.
A large residual is a real finding about v9's marginals, not a failure of this layer, which is
why it is surfaced per fixture rather than averaged away.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CALC_VERSION = "1.0.0"

MAX_GOALS = 10                 # 11x11 grid; P(>10 goals a side) is negligible and is renormalised
_G = np.arange(MAX_GOALS + 1)


def _poisson_pmf(lam: float) -> np.ndarray:
    lam = max(float(lam), 1e-6)
    logp = -lam + _G * np.log(lam) - np.array([np.sum(np.log(np.arange(1, k + 1))) if k else 0.0
                                               for k in _G])
    return np.exp(logp)


def _tau(rho: float) -> np.ndarray:
    """Dixon-Coles low-score correction, applied to the 2x2 corner only."""
    t = np.ones((MAX_GOALS + 1, MAX_GOALS + 1))
    t[0, 0] = 1.0 - rho
    t[0, 1] = 1.0 + rho
    t[1, 0] = 1.0 + rho
    t[1, 1] = 1.0 - rho
    return t


def score_matrix(lam_home: float, lam_away: float, rho: float = 0.0) -> np.ndarray:
    """P(home_goals=i, away_goals=j) as an (11, 11) matrix that sums to 1."""
    m = np.outer(_poisson_pmf(lam_home), _poisson_pmf(lam_away)) * _tau(rho)
    m = np.clip(m, 0.0, None)
    s = m.sum()
    return m / s if s > 0 else m


# Market -> boolean mask over the score grid. ONE definition, matching src/combo/events.py
# exactly, so the model and the empirical matrix are always speaking about the same events.
def _masks() -> dict[str, np.ndarray]:
    H, A = np.meshgrid(_G, _G, indexing="ij")
    T = H + A
    return {
        "O15": T >= 2, "U15": T <= 1,
        "O25": T >= 3, "U25": T <= 2,
        "O35": T >= 4, "U35": T <= 3,
        "BTTS": (H >= 1) & (A >= 1), "BTTS_NO": (H == 0) | (A == 0),
        "HOME": H > A, "DRAW": H == A, "AWAY": H < A,
        "1X": H >= A, "X2": H <= A, "12": H != A,
    }


MASKS = _masks()


def prob(m: np.ndarray, market: str) -> float:
    return float(m[MASKS[market]].sum())


def joint(m: np.ndarray, a: str, b: str) -> float:
    """P(A and B) read straight off the distribution. Exact, not approximated."""
    return float(m[MASKS[a] & MASKS[b]].sum())


def fit(targets: dict[str, float], *, rho_grid=(-0.15, -0.10, -0.05, 0.0, 0.05, 0.10),
        max_iter: int = 60) -> dict:
    """Fit (lam_home, lam_away, rho) so the distribution reproduces v9's probabilities.

    `targets` may contain any of O15/O25/O35/BTTS; missing ones are simply not fitted, so a
    fixture with a partial opinion still yields a distribution rather than being dropped.

    Coordinate descent on a coarse-to-fine grid. Deliberately not a gradient optimiser: the
    surface is smooth and low-dimensional, this is deterministic, and it cannot wander to a
    degenerate corner the way an unconstrained solve can.
    """
    keys = [k for k in ("O15", "O25", "O35", "BTTS") if k in targets
            and targets[k] == targets[k] and 0.0 < float(targets[k]) < 1.0]
    if not keys:
        return {"ok": False, "reason": "NO_USABLE_TARGETS"}

    def loss(lh, la, rho):
        m = score_matrix(lh, la, rho)
        return float(np.sum([(prob(m, k) - float(targets[k])) ** 2 for k in keys]))

    best = None
    for rho in rho_grid:
        lh, la = 1.35, 1.15                      # league-average-ish starting point
        step = 0.8
        for _ in range(max_iter):
            improved = False
            for _which in (0, 1):
                for delta in (step, -step):
                    cand = (lh + delta, la) if _which == 0 else (lh, la + delta)
                    if cand[0] <= 0.02 or cand[1] <= 0.02:
                        continue
                    if loss(*cand, rho) < loss(lh, la, rho) - 1e-12:
                        lh, la = cand
                        improved = True
            if not improved:
                step /= 2.0
                if step < 1e-4:
                    break
        l = loss(lh, la, rho)
        if best is None or l < best[0]:
            best = (l, lh, la, rho)

    l, lh, la, rho = best
    m = score_matrix(lh, la, rho)
    fitted = {k: prob(m, k) for k in keys}
    worst = max(abs(fitted[k] - float(targets[k])) for k in keys)
    return {
        "ok": True, "lam_home": round(lh, 4), "lam_away": round(la, 4), "rho": rho,
        "sse": round(l, 8),
        # The honest quality signal. A large max error means v9's own marginals were mutually
        # inconsistent and no single distribution can honour all of them at once.
        "max_abs_error": round(worst, 4),
        "fit_quality": "GOOD" if worst <= 0.02 else "FAIR" if worst <= 0.05 else "POOR",
        "targets_used": keys,
        "matrix": m,
        "calc_version": CALC_VERSION,
    }


def monotonicity_violation(t: dict) -> str | None:
    """v9's own marginals must satisfy O1.5 >= O2.5 >= O3.5 (brief section 3).

    Checked BEFORE fitting: a set that violates it is logically impossible, and fitting a
    distribution to impossible targets produces a confident-looking answer to a broken question.
    """
    o15, o25, o35 = (t.get("O15"), t.get("O25"), t.get("O35"))
    vals = [(n, v) for n, v in (("O15", o15), ("O25", o25), ("O35", o35))
            if v is not None and v == v]
    for (na, va), (nb, vb) in zip(vals, vals[1:]):
        if va < vb - 1e-9:
            return f"PROBABILITY_MONOTONICITY_VIOLATION {na}={va:.4f} < {nb}={vb:.4f}"
    if t.get("BTTS") is not None and o15 is not None and t["BTTS"] == t["BTTS"] and o15 == o15:
        # BTTS implies at least two goals, so P(BTTS) can never exceed P(O1.5).
        if t["BTTS"] > o15 + 1e-9:
            return f"BTTS_EXCEEDS_O15 BTTS={t['BTTS']:.4f} > O15={o15:.4f}"
    return None

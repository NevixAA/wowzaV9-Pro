"""
Dixon-Coles 1X2 model (brief sections 49, 50, 57, 71).
======================================================

A MATCH-RESULT MODEL v9 DOES NOT HAVE. `model_snapshots` carries OU25/OU15/OU35/BTTS and
HT markets and no 1X2 at all, so there has never been a `p_wowza_home/draw/away` to compare
against the 1X2 prices now being collected. This supplies one.

WHY DIXON-COLES, AND WHY NOT SOMETHING FANCIER

Section 71 asks for the simplest statistically defensible implementation, not the best one. The
standard reference model for football scorelines is two Poissons driven by team attack and
defence ratings plus home advantage; Dixon-Coles (1997) adds one parameter, `rho`, correcting
the four lowest scorelines -- 0-0, 1-0, 0-1, 1-1 -- where independent Poissons are known to be
wrong.

That correction is not cosmetic here. Those four scorelines are where draws and BTTS_NO live,
and section 57 singles out draws as the outcome simplistic score models misprice. Fitting the
league-average marginals with a plain Poisson already understates the draw rate (24.6% against
an observed 26.1%), so the model that gets draws least wrong is the one worth starting from.

Deliberately NOT attempted: a multiclass classifier on engineered features. It would predict
1X2 without producing a score distribution, and a score distribution is the thing that makes
1X2, totals, BTTS and the bet-builder joints mutually consistent (sections 59-60). Accuracy on
its own is also the wrong target (section 50).

WHAT IT PRODUCES

Per fixture: lambda_home, lambda_away and a full score matrix, from which P(HOME), P(DRAW),
P(AWAY) -- and O1.5/O2.5/O3.5/BTTS, and any joint -- are read exactly.

FITTING NOTES THAT MATTER

* PER LEAGUE. A team's attack rating is only meaningful relative to the opponents it faced;
  pooling leagues would make Boca Juniors and Barnsley comparable, which they are not.
* TIME DECAY. Matches are weighted exp(-xi * days_ago), the standard Dixon-Coles treatment,
  because a rating built on three-year-old form is not a current opinion.
* IDENTIFIABILITY. Attack and defence are only defined up to a constant, so mean attack is
  pinned to zero. Without it the optimiser drifts along a flat ridge and the fit looks unstable
  when it is merely unidentified.
* CHRONOLOGICAL EVALUATION ONLY. Train strictly before a cutoff, score strictly after it. A
  random split would leak future form into past predictions through the team ratings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

CALC_VERSION = "1.0.0"

MAX_GOALS = 10
_G = np.arange(MAX_GOALS + 1)
_LOGFACT = np.array([0.0] + list(np.cumsum(np.log(np.arange(1, MAX_GOALS + 1)))))

# Half-life in days for match weighting. 180 keeps roughly a season of form dominant while
# still letting older matches inform a team that has played little recently.
HALF_LIFE_DAYS = 180.0
MIN_MATCHES_PER_LEAGUE = 300
MIN_MATCHES_PER_TEAM = 8


def _decay(days_ago: np.ndarray, half_life: float = HALF_LIFE_DAYS) -> np.ndarray:
    return np.power(0.5, np.clip(days_ago, 0, None) / half_life)


def _tau(hg, ag, lh, la, rho):
    """Dixon-Coles correction on the four lowest scorelines."""
    t = np.ones_like(lh, dtype=float)
    m00 = (hg == 0) & (ag == 0)
    m01 = (hg == 0) & (ag == 1)
    m10 = (hg == 1) & (ag == 0)
    m11 = (hg == 1) & (ag == 1)
    t[m00] = 1.0 - lh[m00] * la[m00] * rho
    t[m01] = 1.0 + lh[m01] * rho
    t[m10] = 1.0 + la[m10] * rho
    t[m11] = 1.0 - rho
    return np.clip(t, 1e-9, None)


def fit_league(df: pd.DataFrame, *, half_life: float = HALF_LIFE_DAYS) -> dict | None:
    """Fit attack/defence/home-advantage/rho for one league by weighted maximum likelihood."""
    d = df.dropna(subset=["home_goals", "away_goals", "home_team", "away_team"]).copy()
    if len(d) < MIN_MATCHES_PER_LEAGUE:
        return None
    teams = sorted(set(d["home_team"]) | set(d["away_team"]))
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = d["home_team"].map(idx).to_numpy()
    ai = d["away_team"].map(idx).to_numpy()
    hg = pd.to_numeric(d["home_goals"], errors="coerce").to_numpy().astype(int)
    ag = pd.to_numeric(d["away_goals"], errors="coerce").to_numpy().astype(int)
    days = (d["_d"].max() - d["_d"]).dt.days.to_numpy().astype(float)
    w = _decay(days, half_life)

    def unpack(p):
        att = np.concatenate([p[:n - 1], [-np.sum(p[:n - 1])]])   # mean attack pinned to 0
        dfn = p[n - 1:2 * n - 1]
        return att, dfn, p[-2], p[-1]

    def nll(p):
        att, dfn, hadv, rho = unpack(p)
        lh = np.exp(att[hi] - dfn[ai] + hadv)
        la = np.exp(att[ai] - dfn[hi])
        lh = np.clip(lh, 1e-6, 30); la = np.clip(la, 1e-6, 30)
        ll = (-lh + hg * np.log(lh) - _LOGFACT[np.clip(hg, 0, MAX_GOALS)]
              - la + ag * np.log(la) - _LOGFACT[np.clip(ag, 0, MAX_GOALS)])
        ll = ll + np.log(_tau(hg, ag, lh, la, rho))
        return -float(np.sum(w * ll))

    p0 = np.concatenate([np.zeros(n - 1), np.zeros(n), [0.25], [-0.05]])
    bounds = [(-3, 3)] * (n - 1) + [(-3, 3)] * n + [(-1, 1.5), (-0.2, 0.2)]
    res = minimize(nll, p0, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 400, "maxfun": 40000})
    att, dfn, hadv, rho = unpack(res.x)
    played = pd.concat([d["home_team"], d["away_team"]]).value_counts()
    return {
        "teams": teams, "attack": dict(zip(teams, att)), "defence": dict(zip(teams, dfn)),
        "home_adv": float(hadv), "rho": float(rho),
        "n_matches": len(d), "converged": bool(res.success),
        "matches_per_team": {t: int(played.get(t, 0)) for t in teams},
        "calc_version": CALC_VERSION, "half_life_days": half_life,
    }


def _matrix(lh: float, la: float, rho: float) -> np.ndarray:
    ph = np.exp(-lh + _G * np.log(max(lh, 1e-9)) - _LOGFACT)
    pa = np.exp(-la + _G * np.log(max(la, 1e-9)) - _LOGFACT)
    m = np.outer(ph, pa)
    m[0, 0] *= 1.0 - lh * la * rho
    m[0, 1] *= 1.0 + lh * rho
    m[1, 0] *= 1.0 + la * rho
    m[1, 1] *= 1.0 - rho
    m = np.clip(m, 0, None)
    return m / m.sum()


def predict(model: dict, home: str, away: str) -> dict | None:
    """P(HOME/DRAW/AWAY) plus totals and BTTS, all from one score matrix."""
    if model is None or home not in model["attack"] or away not in model["attack"]:
        return None
    if (model["matches_per_team"].get(home, 0) < MIN_MATCHES_PER_TEAM
            or model["matches_per_team"].get(away, 0) < MIN_MATCHES_PER_TEAM):
        return None                       # too little history to rate this team honestly
    lh = float(np.exp(model["attack"][home] - model["defence"][away] + model["home_adv"]))
    la = float(np.exp(model["attack"][away] - model["defence"][home]))
    m = _matrix(np.clip(lh, 1e-6, 15), np.clip(la, 1e-6, 15), model["rho"])
    H, A = np.meshgrid(_G, _G, indexing="ij")
    T = H + A
    return {
        "lam_home": round(lh, 4), "lam_away": round(la, 4),
        "p_home": float(m[H > A].sum()), "p_draw": float(m[H == A].sum()),
        "p_away": float(m[H < A].sum()),
        "p_o15": float(m[T >= 2].sum()), "p_o25": float(m[T >= 3].sum()),
        "p_o35": float(m[T >= 4].sum()),
        "p_btts": float(m[(H >= 1) & (A >= 1)].sum()),
        "matrix": m,
    }


# ── Evaluation (brief section 50: never accuracy alone) ──────────────────────
def multiclass_logloss(p: np.ndarray, y: np.ndarray) -> float:
    """y in {0,1,2} for HOME/DRAW/AWAY. p is (n,3) and must sum to 1 per row."""
    q = np.clip(p[np.arange(len(y)), y], 1e-15, 1.0)
    return float(-np.mean(np.log(q)))


def multiclass_brier(p: np.ndarray, y: np.ndarray) -> float:
    oh = np.zeros_like(p)
    oh[np.arange(len(y)), y] = 1.0
    return float(np.mean(np.sum((p - oh) ** 2, axis=1)))


def rps(p: np.ndarray, y: np.ndarray) -> float:
    """Ranked probability score — the standard 1X2 metric, since HOME/DRAW/AWAY is ordered."""
    oh = np.zeros_like(p)
    oh[np.arange(len(y)), y] = 1.0
    cp, co = np.cumsum(p, axis=1), np.cumsum(oh, axis=1)
    return float(np.mean(np.sum((cp - co) ** 2, axis=1)) / (p.shape[1] - 1))


def calibration(p_out: np.ndarray, hit: np.ndarray, bins: int = 5) -> pd.DataFrame:
    """Per-outcome calibration. Section 57 requires draws be reported separately."""
    q = pd.qcut(pd.Series(p_out), bins, duplicates="drop")
    g = pd.DataFrame({"p": p_out, "hit": hit.astype(float), "bin": q}).groupby("bin",
                                                                               observed=True)
    return g.agg(n=("hit", "size"), predicted=("p", "mean"), actual=("hit", "mean")).reset_index(
        drop=True).assign(gap=lambda x: (x.actual - x.predicted).round(4)).round(4)

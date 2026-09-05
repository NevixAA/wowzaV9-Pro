"""
Cross-league strength calibration, for UCL / UEL / UECL.
========================================================

THE PROBLEM THIS SOLVES, AND WHY THE EXISTING MODEL CANNOT

`dixon_coles.fit_league` pins mean attack to zero inside each league, because attack and defence
are only defined up to a constant. That makes ratings meaningful WITHIN a competition and
meaningless ACROSS one: a 0.4 attack rating in the Premier League and a 0.4 in the Cypriot First
Division are the same number describing very different teams. Its own docstring says so -- pooling
leagues "would make Boca Juniors and Barnsley comparable, which they are not".

A European tie is exactly the case that breaks: the two sides come from different leagues. So the
tournament model is not a new goals model, it is the missing SCALE between existing ones.

WHY DOMESTIC FORM AND NOT TOURNAMENT HISTORY

The competition's own past carries almost no weight here. Clubs meet twice a decade, squads turn
over, and half the field changes every season -- a "Champions League history" feature is mostly
noise about different teams. What predicts a tie is how each side is playing in its OWN league
right now, plus how strong that league is. That is what this fits.

THE PARAMETERISATION, AND WHY IT IS ONE NUMBER PER LEAGUE

Each league L gets a single strength offset `s_L`, entering as a difference:

    lam_home = exp(att_home - def_away + home_adv + (s_home - s_away))
    lam_away = exp(att_away - def_home           - (s_home - s_away))

Only differences are identified -- adding a constant to every s changes nothing -- so the mean is
pinned to zero, exactly as attack is inside a league. One parameter per league is deliberate:
384 finished cross-league fixtures is a small anchor set, and a richer model (separate attack and
defence scaling, or per-season drift) would fit that noise happily. Section 71's rule applies --
the simplest defensible thing first.

HOW IT IS FITTED, AND HOW IT IS TESTED

Fitted by maximum likelihood on FINISHED cross-league results, holding the domestic att/def/rho
fixed. Tested chronologically: fit on earlier ties, score later ones, and compare against the
honest null `s = 0` (which is what using domestic ratings naively would do). If the calibration
does not beat that null out of sample it is not carrying information and must not be used --
the same bar the 1X2 model failed against the market.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.combo import dixon_coles as dc

CALC_VERSION = "1.0.0"

# Below this many cross-league results a strength estimate is noise wearing a number.
MIN_ANCHORS = 40
# A league needs its own appearances before it gets a fitted strength; otherwise it inherits 0
# (league-average) rather than a value driven by one lucky qualifier.
MIN_FIXTURES_PER_LEAGUE = 4


def _rating(models: dict, league: str, team: str) -> tuple[float, float] | None:
    """(attack, defence) for a team from its DOMESTIC league fit."""
    m = models.get(league)
    if not m:
        return None
    if team not in m.get("attack", {}) or team not in m.get("defence", {}):
        return None
    if m.get("matches_per_team", {}).get(team, 0) < dc.MIN_MATCHES_PER_TEAM:
        return None                      # too little domestic history to rate honestly
    return float(m["attack"][team]), float(m["defence"][team])


def prepare(fixtures: pd.DataFrame, models: dict) -> pd.DataFrame:
    """Cross-league fixtures both of whose sides have a usable domestic rating.

    `fixtures` needs home_team, away_team, home_league, away_league and (to fit) the scoreline.
    Rows that cannot be rated are DROPPED and counted by the caller -- a tie where one side has
    no domestic form is not a hard case, it is an unanswerable one, and imputing a rating would
    manufacture a confident wrong price (invariant 8).
    """
    rows = []
    for _, r in fixtures.iterrows():
        h = _rating(models, r.get("home_league"), str(r.get("home_team")))
        a = _rating(models, r.get("away_league"), str(r.get("away_team")))
        if h is None or a is None:
            continue
        rows.append({**r.to_dict(),
                     "att_h": h[0], "def_h": h[1], "att_a": a[0], "def_a": a[1]})
    return pd.DataFrame(rows)


def fit(prepared: pd.DataFrame, *, home_adv: float = 0.25, rho: float = -0.05) -> dict:
    """Fit one strength offset per league on finished cross-league results."""
    d = prepared.dropna(subset=["home_goals", "away_goals"])
    if len(d) < MIN_ANCHORS:
        return {"ok": False, "reason": f"only {len(d)} cross-league results (need {MIN_ANCHORS})",
                "strength": {}, "n": len(d)}

    counts = pd.concat([d["home_league"], d["away_league"]]).value_counts()
    leagues = sorted(counts[counts >= MIN_FIXTURES_PER_LEAGUE].index.tolist())
    if len(leagues) < 2:
        return {"ok": False, "reason": "fewer than two leagues with enough anchors",
                "strength": {}, "n": len(d)}
    idx = {lg: i for i, lg in enumerate(leagues)}
    # Leagues below the threshold sit at 0 (league-average) rather than being fitted on noise.
    hi = d["home_league"].map(lambda x: idx.get(x, -1)).to_numpy()
    ai = d["away_league"].map(lambda x: idx.get(x, -1)).to_numpy()
    ah, dh = d["att_h"].to_numpy(), d["def_h"].to_numpy()
    aa, da = d["att_a"].to_numpy(), d["def_a"].to_numpy()
    hg = d["home_goals"].to_numpy().astype(int)
    ag = d["away_goals"].to_numpy().astype(int)
    n = len(leagues)

    def strengths(p):
        s = np.concatenate([p, [-np.sum(p)]])       # mean pinned to 0 — only differences identify
        return s

    def sel(s, i):
        return np.where(i >= 0, s[np.clip(i, 0, n - 1)], 0.0)

    def nll(p):
        s = strengths(p)
        diff = sel(s, hi) - sel(s, ai)
        lh = np.clip(np.exp(ah - da + home_adv + diff), 1e-6, 30)
        la = np.clip(np.exp(aa - dh - diff), 1e-6, 30)
        ll = (-lh + hg * np.log(lh) - dc._LOGFACT[np.clip(hg, 0, dc.MAX_GOALS)]
              - la + ag * np.log(la) - dc._LOGFACT[np.clip(ag, 0, dc.MAX_GOALS)])
        ll = ll + np.log(dc._tau(hg, ag, lh, la, rho))
        return -float(np.sum(ll))

    res = minimize(nll, np.zeros(n - 1), method="L-BFGS-B",
                   bounds=[(-2, 2)] * (n - 1), options={"maxiter": 500})
    s = strengths(res.x)
    return {"ok": True, "strength": {lg: float(s[i]) for lg, i in idx.items()},
            "home_adv": home_adv, "rho": rho, "n": len(d),
            "leagues": len(leagues), "converged": bool(res.success),
            "calc_version": CALC_VERSION}


def predict(row: pd.Series, cal: dict) -> dict | None:
    """P(HOME/DRAW/AWAY) and the goal markets for one cross-league tie."""
    if not cal.get("ok"):
        return None
    s = cal["strength"]
    diff = float(s.get(row.get("home_league"), 0.0)) - float(s.get(row.get("away_league"), 0.0))
    lh = float(np.exp(row["att_h"] - row["def_a"] + cal["home_adv"] + diff))
    la = float(np.exp(row["att_a"] - row["def_h"] - diff))
    m = dc._matrix(np.clip(lh, 1e-6, 15), np.clip(la, 1e-6, 15), cal["rho"])
    H, A = np.meshgrid(dc._G, dc._G, indexing="ij")
    T = H + A
    return {"lam_home": round(lh, 4), "lam_away": round(la, 4),
            "p_home": float(m[H > A].sum()), "p_draw": float(m[H == A].sum()),
            "p_away": float(m[H < A].sum()),
            "p_o15": float(m[T >= 2].sum()), "p_o25": float(m[T >= 3].sum()),
            "p_o35": float(m[T >= 4].sum()),
            "p_btts": float(m[(H >= 1) & (A >= 1)].sum()),
            "league_strength_diff": round(diff, 4)}


def evaluate(prepared: pd.DataFrame, *, test_frac: float = 0.3) -> dict:
    """Chronological fit/score split, against the honest null of no calibration at all.

    The null is `s = 0` for every league — which is what naively using domestic ratings across a
    European tie already does. Beating it is the ONLY evidence that the strength term carries
    information; a lower log-loss on the fitted data would prove nothing.
    """
    d = prepared.dropna(subset=["home_goals", "away_goals"]).sort_values("match_date")
    if len(d) < MIN_ANCHORS * 2:
        return {"ok": False, "reason": f"only {len(d)} rated results — too few to split"}
    cut = int(len(d) * (1 - test_frac))
    tr, te = d.iloc[:cut], d.iloc[cut:]
    cal = fit(tr)
    if not cal.get("ok"):
        return {"ok": False, "reason": cal.get("reason")}
    null = {"ok": True, "strength": {}, "home_adv": cal["home_adv"], "rho": cal["rho"]}

    P, N, Y = [], [], []
    for _, r in te.iterrows():
        a, b = predict(r, cal), predict(r, null)
        if not a or not b:
            continue
        P.append([a["p_home"], a["p_draw"], a["p_away"]])
        N.append([b["p_home"], b["p_draw"], b["p_away"]])
        Y.append(0 if r["home_goals"] > r["away_goals"]
                 else (1 if r["home_goals"] == r["away_goals"] else 2))
    if len(P) < 20:
        return {"ok": False, "reason": f"only {len(P)} scoreable test ties"}
    P, N, Y = np.array(P), np.array(N), np.array(Y)
    ll_c, ll_n = dc.multiclass_logloss(P, Y), dc.multiclass_logloss(N, Y)
    return {"ok": True, "train": len(tr), "test": len(P),
            "logloss_calibrated": round(ll_c, 4), "logloss_uncalibrated": round(ll_n, 4),
            "rps_calibrated": round(dc.rps(P, Y), 4), "rps_uncalibrated": round(dc.rps(N, Y), 4),
            "calibration_helps": bool(ll_c < ll_n),
            "leagues_fitted": cal["leagues"]}

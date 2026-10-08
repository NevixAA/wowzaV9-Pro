"""Baseline goals model for scout leagues: per-league Poisson attack/defence ratings.

A BASELINE, deliberately. It answers "does even a plain goals model find anything the market
misses here?" — if a league's market is soft, a simple model should already show it; if it is
not, a fancier one is unlikely to. Wowza's own models need football-data history these leagues
do not have, so they cannot be run on them without new work.

    lambda_home = mu_home * A[home] * D[away]
    lambda_away = mu_away * A[away] * D[home]

Ratings are fitted by weighted iterative proportional fitting (Maher 1982), with exponential time
decay and `PRIOR_MATCHES` pseudo-matches at league average, so a promoted team with no history
starts at average rather than at an extreme. Scorelines are independent Poisson. That understates
draws and low totals slightly; it is the same for every league, so it does not bias the
league-to-league comparison this exists for.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

VERSION = "scout_poisson_v1_cal"
HALF_LIFE_DAYS = 180.0
WINDOW_DAYS = 730
PRIOR_MATCHES = 3.0
MAX_GOALS = 10
LINES = {"ou15": 1.5, "ou25": 2.5, "ou35": 3.5}


def fit(results: pd.DataFrame, asof_ts: int) -> dict | None:
    """Fit one league on finished matches strictly before `asof_ts` (epoch seconds)."""
    d = results[(results["kickoff_ts"] < asof_ts)
                & (results["kickoff_ts"] >= asof_ts - WINDOW_DAYS * 86400)].dropna(
        subset=["home_goals", "away_goals", "home_id", "away_id"])
    if len(d) < 40:
        return None
    age = (asof_ts - d["kickoff_ts"].to_numpy()) / 86400.0
    w = 0.5 ** (age / HALF_LIFE_DAYS)
    hg, ag = d["home_goals"].to_numpy(float), d["away_goals"].to_numpy(float)
    teams = pd.Index(pd.unique(np.concatenate([d["home_id"].to_numpy(), d["away_id"].to_numpy()])))
    hi, ai = teams.get_indexer(d["home_id"]), teams.get_indexer(d["away_id"])
    n = len(teams)
    A, D = np.ones(n), np.ones(n)
    mu_h = np.average(hg, weights=w)
    mu_a = np.average(ag, weights=w)
    for _ in range(60):
        # attack: goals scored vs goals expected from the opponents' defences
        exp_h, exp_a = mu_h * D[ai], mu_a * D[hi]
        num = np.bincount(hi, w * hg, n) + np.bincount(ai, w * ag, n)
        den = np.bincount(hi, w * exp_h, n) + np.bincount(ai, w * exp_a, n)
        A = (num + PRIOR_MATCHES * (mu_h + mu_a) / 2) / (den + PRIOR_MATCHES * (mu_h + mu_a) / 2)
        A /= A.mean()
        exp_h, exp_a = mu_h * A[hi], mu_a * A[ai]
        num = np.bincount(ai, w * hg, n) + np.bincount(hi, w * ag, n)
        den = np.bincount(ai, w * exp_h, n) + np.bincount(hi, w * exp_a, n)
        D = (num + PRIOR_MATCHES * (mu_h + mu_a) / 2) / (den + PRIOR_MATCHES * (mu_h + mu_a) / 2)
        D /= D.mean()
        mu_h = (w * hg).sum() / (w * A[hi] * D[ai]).sum()
        mu_a = (w * ag).sum() / (w * A[ai] * D[hi]).sum()
    games = np.bincount(hi, minlength=n) + np.bincount(ai, minlength=n)
    # CALIBRATION-IN-THE-LARGE, per market, on the fit window only (no leakage: every match is
    # before asof_ts). Independent Poisson understates the spread of real goal totals, so raw
    # P(over) runs low — measured on Argentina Primera Nacional 2025, 26.2% predicted against
    # 29.5% observed. Uncorrected, that bias reads as an UNDER edge on every fixture, the same
    # one-sided pattern that lost money in v9. One logit shift per market fixes the level and
    # leaves the ranking untouched.
    lh, la = mu_h * A[hi] * D[ai], mu_a * A[ai] * D[hi]
    raw = probs(lh, la)
    y = {"ou15": (hg + ag) > 1.5, "ou25": (hg + ag) > 2.5, "ou35": (hg + ag) > 3.5,
         "btts": (hg > 0) & (ag > 0)}
    offset = {}
    for k, yk in y.items():
        rate = float(np.clip(np.average(yk, weights=w), 0.01, 0.99))
        mean_p = float(np.clip(np.average(raw[k], weights=w), 0.01, 0.99))
        offset[k] = _logit(rate) - _logit(mean_p)
    return {"teams": {int(t): i for i, t in enumerate(teams)}, "A": A, "D": D,
            "mu_h": float(mu_h), "mu_a": float(mu_a), "games": games, "n_matches": int(len(d)),
            "offset": offset}


def _logit(p):
    return np.log(p / (1 - p))


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def probs(lh, la) -> dict:
    """Uncalibrated independent-Poisson probabilities, vectorised over arrays of lambdas."""
    lh, la = np.atleast_1d(np.asarray(lh, float)), np.atleast_1d(np.asarray(la, float))
    k = np.arange(MAX_GOALS + 1)
    lgam = np.array([math.lgamma(x + 1) for x in k])
    ph = np.exp(-lh[:, None] + k * np.log(lh[:, None]) - lgam)
    pa = np.exp(-la[:, None] + k * np.log(la[:, None]) - lgam)
    # P(total <= t) = sum over i+j <= t
    cdf = {t: sum((ph[:, i] * pa[:, : t - i + 1].sum(1)) for i in range(t + 1)) for t in (1, 2, 3)}
    return {"ou15": 1 - cdf[1], "ou25": 1 - cdf[2], "ou35": 1 - cdf[3],
            "btts": (1 - np.exp(-lh)) * (1 - np.exp(-la))}


def predict(m: dict, home_id: int, away_id: int) -> dict:
    """Probabilities for every scout market, plus the inputs that produced them."""
    ih, ia = m["teams"].get(int(home_id)), m["teams"].get(int(away_id))
    Ah = m["A"][ih] if ih is not None else 1.0
    Dh = m["D"][ih] if ih is not None else 1.0
    Aa = m["A"][ia] if ia is not None else 1.0
    Da = m["D"][ia] if ia is not None else 1.0
    lh, la = m["mu_h"] * Ah * Da, m["mu_a"] * Aa * Dh
    raw = probs(lh, la)
    cal = {k: float(_sigmoid(_logit(np.clip(raw[k][0], 1e-6, 1 - 1e-6)) + m["offset"][k]))
           for k in raw}
    out = {"p_ou15_over": cal["ou15"], "p_ou25_over": cal["ou25"], "p_ou35_over": cal["ou35"],
           "p_btts_yes": cal["btts"], "p_ou25_over_raw": float(raw["ou25"][0])}
    out.update({"lambda_home": round(lh, 4), "lambda_away": round(la, 4),
                "home_games": int(m["games"][ih]) if ih is not None else 0,
                "away_games": int(m["games"][ia]) if ia is not None else 0,
                "league_matches": m["n_matches"]})
    return out

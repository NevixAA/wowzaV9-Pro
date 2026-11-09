"""
Calibration of the special probabilities (owner 2026-11-09).

The history study showed the score model RANKS high-scoring and 0-0 matches well but is OVERCONFIDENT
(flagged 6+ goal fixtures: model 15.2%, actual 9.0%). This maps each raw probability p to a calibrated
q, per outcome and per league, fitted on EARLIER data only:

    q = sigmoid(a_k + b_k * logit(p) + delta_{k,L})

  * a_k, b_k   one logistic recalibration per outcome k, fitted on every league's earlier out-of-sample
               rows (the shape of the model's overconfidence is shared across leagues);
  * delta_k,L  the league's OWN intercept adjustment: its maximum-likelihood value given (a_k, b_k),
               shrunk toward 0 with an empirical-Bayes weight w = tau2 / (tau2 + var_L). tau2 (the real
               spread of league adjustments) is LEARNED by the method of moments, so a league with a lot
               of data keeps almost all of its own adjustment and a thin one is pulled in - the weight is
               learned and reported, never typed.
  * A league with fewer than MIN_LEAGUE_ROWS earlier rows gets NO calibrated probability (NaN, status
    NO_LEAGUE_DATA): nothing pooled is served to a league that has not earned its own adjustment.

The calibration is monotone inside a league, so it never changes which fixtures a league flags (flags
rank on the raw probability). Raw and calibrated probabilities are kept side by side.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.specials import outcomes as O

CAL_RULE = {
    "version": "CAL-1",
    "form": "q = sigmoid(a_k + b_k*logit(p) + delta_k,L), delta empirical-Bayes shrunk (weight learned)",
    "refit": "calendar month, earlier out-of-sample rows only",
    "min_pooled_rows": 5000,
    "min_league_rows": 200,
    "clip": 1e-6,
}
CAL_KEYS = list(O.SPECIALS)


def _logit(p):
    p = np.clip(np.asarray(p, float), CAL_RULE["clip"], 1 - CAL_RULE["clip"])
    return np.log(p / (1 - p))


def _sig(z):
    return 1.0 / (1.0 + np.exp(-z))


def fit_pooled(x: np.ndarray, y: np.ndarray, iters: int = 50) -> tuple[float, float]:
    """Logistic regression y ~ a + b*x by Newton (IRLS)."""
    X = np.column_stack([np.ones_like(x), x])
    beta = np.array([0.0, 1.0])
    for _ in range(iters):
        mu = _sig(X @ beta)
        w = np.clip(mu * (1 - mu), 1e-9, None)
        H = X.T @ (X * w[:, None])
        step = np.linalg.solve(H, X.T @ (y - mu))
        beta = beta + step
        if np.max(np.abs(step)) < 1e-9:
            break
    return float(beta[0]), float(beta[1])


def league_delta(z: np.ndarray, y: np.ndarray, iters: int = 30) -> tuple[float, float]:
    """MLE of an intercept offset given the pooled linear predictor z; (delta, variance)."""
    d = 0.0
    info = 0.0
    for _ in range(iters):
        mu = _sig(z + d)
        info = float(np.sum(mu * (1 - mu)))
        if info <= 0:
            return 0.0, float("inf")
        step = float(np.sum(y - mu)) / info
        d += step
        if abs(step) < 1e-10:
            break
    return d, 1.0 / info


def fit(train: pd.DataFrame, key: str) -> dict | None:
    """Fit CAL-1 for outcome `key` on `train` (columns league, p_<key>, y_<key>)."""
    t = train[[ "league", f"p_{key}", f"y_{key}"]].dropna()
    if len(t) < CAL_RULE["min_pooled_rows"]:
        return None
    x, y = _logit(t[f"p_{key}"]), t[f"y_{key}"].to_numpy(float)
    a, b = fit_pooled(x, y)
    raw = {}
    for lg, g in t.groupby("league"):
        if len(g) < CAL_RULE["min_league_rows"]:
            continue
        z = a + b * _logit(g[f"p_{key}"])
        d, v = league_delta(z, g[f"y_{key}"].to_numpy(float))
        if np.isfinite(v):
            raw[lg] = (d, v, len(g))
    if not raw:
        return None
    ds = np.array([r[0] for r in raw.values()])
    vs = np.array([r[1] for r in raw.values()])
    tau2 = float(max(0.0, np.var(ds) - np.mean(vs))) if len(ds) > 1 else 0.0
    leagues = {}
    for lg, (d, v, n) in raw.items():
        w = tau2 / (tau2 + v) if (tau2 + v) > 0 else 0.0
        leagues[lg] = {"delta": float(w * d), "delta_mle": float(d), "weight": float(w), "n": int(n)}
    return {"a": a, "b": b, "tau2": tau2, "n": int(len(t)), "leagues": leagues}


def apply(params: dict | None, league: str, p) -> float:
    """Calibrated probability, or NaN when the league has no fitted adjustment (never a stand-in)."""
    if params is None or league not in params["leagues"] or p is None or p != p:
        return float("nan")
    z = params["a"] + params["b"] * float(_logit(p)) + params["leagues"][league]["delta"]
    return float(_sig(z))


def walk_forward(pred: pd.DataFrame, keys=CAL_KEYS) -> pd.DataFrame:
    """Adds p_cal_<key>: each month calibrated by a fit on the months before it only."""
    d = pred.copy()
    months = sorted(d["month"].unique())
    for k in keys:
        col = np.full(len(d), np.nan)
        for m in months:
            params = fit(d[d["month"] < m], k)
            if params is None:
                continue
            idx = np.flatnonzero((d["month"] == m).to_numpy())
            sub = d.iloc[idx]
            col[idx] = [apply(params, lg, p) for lg, p in zip(sub["league"], sub[f"p_{k}"])]
        d[f"p_cal_{k}"] = col
    return d


def _brier(p, y):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def _ll(p, y):
    p = np.clip(np.asarray(p, float), 1e-12, 1 - 1e-12)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def before_after(d: pd.DataFrame, keys=CAL_KEYS) -> dict:
    """Raw vs calibrated vs league base, on the rows where a calibrated probability exists."""
    out = {}
    for k in keys:
        cols = [f"p_{k}", f"p_cal_{k}", f"base_{k}", f"y_{k}"]
        if any(c not in d for c in cols):
            continue
        t = d[cols + ["league"] + ([f"cand_{k}"] if f"cand_{k}" in d else [])].dropna(subset=cols)
        if t.empty:
            out[k] = {"n": 0}
            continue
        y = t[f"y_{k}"]
        rec = {"n": int(len(t)), "events": int(y.sum()), "actual": float(y.mean()),
               "mean_raw": float(t[f"p_{k}"].mean()), "mean_cal": float(t[f"p_cal_{k}"].mean()),
               "mean_base": float(t[f"base_{k}"].mean()),
               "brier_raw": _brier(t[f"p_{k}"], y), "brier_cal": _brier(t[f"p_cal_{k}"], y),
               "brier_base": _brier(t[f"base_{k}"], y),
               "logloss_raw": _ll(t[f"p_{k}"], y), "logloss_cal": _ll(t[f"p_cal_{k}"], y),
               "logloss_base": _ll(t[f"base_{k}"], y)}
        rec["brier_skill_raw"] = 1 - rec["brier_raw"] / rec["brier_base"] if rec["brier_base"] else None
        rec["brier_skill_cal"] = 1 - rec["brier_cal"] / rec["brier_base"] if rec["brier_base"] else None
        if f"cand_{k}" in t:
            c = t[t[f"cand_{k}"] == 1.0]
            if len(c):
                rec["flagged"] = {"n": int(len(c)), "actual": float(c[f"y_{k}"].mean()),
                                  "mean_raw": float(c[f"p_{k}"].mean()),
                                  "mean_cal": float(c[f"p_cal_{k}"].mean())}
        out[k] = rec
    return out


def final_params(pred: pd.DataFrame, keys=CAL_KEYS) -> dict:
    """The live calibration: CAL-1 fitted on EVERY out-of-sample row of the study."""
    return {k: fit(pred, k) for k in keys}

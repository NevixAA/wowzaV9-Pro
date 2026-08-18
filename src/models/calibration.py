"""
Calibration: global Platt scaling, plus league-aware shrinkage.
==============================================================
Prompt 1 section 7: "Test hierarchical/shrinkage calibration such as
logit(p_final) = a_league + b_league * logit(p_global). Small samples must shrink toward global
calibration."

The tension this resolves. Leagues genuinely differ — a model calibrated across all of them is
systematically off in some. But fitting a free two-parameter correction per league on 40 matches
produces a correction fitted to noise, and applying it makes those leagues WORSE. Prompt 3
section 18 is explicit: "Do not fit unconstrained tiny-sample league corrections."

So the per-league parameters are shrunk toward the global fit by sample size:

    w_league = n_league / (n_league + TAU)
    a = w * a_league_raw + (1 - w) * a_global
    b = w * b_league_raw + (1 - w) * b_global

At n << TAU a league is effectively using the global calibration; at n >> TAU it uses its own.
TAU is a pseudo-count, so the transition is smooth and there is no cliff at an arbitrary
minimum-sample threshold.

Everything is fitted on the CALIBRATION block only (src/validation/splits.py) — never on train
(the base models have already seen it, so their probabilities there are optimistic) and never on
the final holdout.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd

EPS = 1e-6
# Pseudo-count for league shrinkage. 400 means a league needs ~400 calibration rows before it
# is trusted about half on its own account. Deliberately high: a wrong league correction is
# worse than no league correction, because it is applied with confidence.
DEFAULT_TAU = 400.0


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def _fit_platt(y, p, *, iters: int = 200, lr: float = 0.1) -> tuple[float, float]:
    """Fit a + b*logit(p) by gradient descent on log loss.

    Hand-rolled rather than sklearn so the fitted parameters are plain floats that serialise
    into the model registry — a pickled estimator cannot be diffed, audited or compared across
    versions, and Prompt 1 section 13 requires the calibration to be stored WITH the model.
    """
    y = np.asarray(y, dtype=float)
    z = _logit(p)
    a, b = 0.0, 1.0
    n = max(1, len(y))
    for _ in range(iters):
        q = _sigmoid(a + b * z)
        ga = float(np.sum(q - y) / n)
        gb = float(np.sum((q - y) * z) / n)
        a -= lr * ga
        b -= lr * gb
    return float(a), float(b)


@dataclass
class LeagueCalibration:
    league: str
    n: int
    a_raw: float
    b_raw: float
    a: float                # after shrinkage — what is actually applied
    b: float
    shrink_weight: float    # 0 = pure global, 1 = pure league
    label: str              # SHRUNK_TO_GLOBAL | PARTIAL | LEAGUE_TRUSTED


@dataclass
class CalibrationModel:
    a_global: float = 0.0
    b_global: float = 1.0
    n_global: int = 0
    tau: float = DEFAULT_TAU
    fitted_on_dates: tuple[str, str] = ("", "")
    leagues: dict[str, LeagueCalibration] = field(default_factory=dict)

    # ── apply ────────────────────────────────────────────────────────────────
    def apply(self, p, league=None):
        """Calibrate probabilities. An unseen league falls back to the global fit."""
        z = _logit(p)
        if league is None:
            return _sigmoid(self.a_global + self.b_global * z)
        leagues = pd.Series(league).astype(str).to_numpy()
        a = np.full(len(z), self.a_global, dtype=float)
        b = np.full(len(z), self.b_global, dtype=float)
        for i, lg in enumerate(leagues):
            lc = self.leagues.get(lg)
            if lc is not None:
                a[i], b[i] = lc.a, lc.b
        return _sigmoid(a + b * z)

    # ── persistence ──────────────────────────────────────────────────────────
    def to_json(self, path: Path) -> None:
        payload = {"a_global": self.a_global, "b_global": self.b_global,
                   "n_global": self.n_global, "tau": self.tau,
                   "fitted_on_dates": list(self.fitted_on_dates),
                   "leagues": {k: asdict(v) for k, v in self.leagues.items()}}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path) -> "CalibrationModel":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        m = cls(a_global=d["a_global"], b_global=d["b_global"],
                n_global=d.get("n_global", 0), tau=d.get("tau", DEFAULT_TAU),
                fitted_on_dates=tuple(d.get("fitted_on_dates", ["", ""])))
        for k, v in (d.get("leagues") or {}).items():
            m.leagues[k] = LeagueCalibration(**v)
        return m


def fit_calibration(
    cal_df: pd.DataFrame,
    *,
    y_col: str,
    p_col: str,
    league_col: str | None = "league",
    tau: float = DEFAULT_TAU,
    date_col: str = "match_date",
) -> CalibrationModel:
    """Fit global then per-league-with-shrinkage on the CALIBRATION block only."""
    y = pd.to_numeric(cal_df[y_col], errors="coerce")
    p = pd.to_numeric(cal_df[p_col], errors="coerce")
    keep = y.notna() & p.notna()
    y, p = y[keep], p[keep]
    if len(y) == 0:
        raise ValueError("no usable rows to calibrate on")

    a_g, b_g = _fit_platt(y, p)
    m = CalibrationModel(a_global=a_g, b_global=b_g, n_global=int(len(y)), tau=float(tau))
    if date_col in cal_df.columns:
        d = pd.to_datetime(cal_df.loc[keep.index[keep], date_col], errors="coerce")
        if d.notna().any():
            m.fitted_on_dates = (str(d.min())[:10], str(d.max())[:10])

    if not league_col or league_col not in cal_df.columns:
        return m

    lg = cal_df.loc[keep.index[keep], league_col].astype(str)
    for name, idx in lg.groupby(lg).groups.items():
        yy, pp = y.loc[idx], p.loc[idx]
        n = int(len(yy))
        # A single class in a league gives no calibration signal at all — a Platt fit on it
        # would run off to fit the constant. Use the global parameters unchanged.
        if n < 2 or yy.nunique() < 2:
            m.leagues[str(name)] = LeagueCalibration(
                league=str(name), n=n, a_raw=a_g, b_raw=b_g, a=a_g, b=b_g,
                shrink_weight=0.0, label="SHRUNK_TO_GLOBAL")
            continue
        a_r, b_r = _fit_platt(yy, pp)
        w = n / (n + m.tau)
        a = w * a_r + (1 - w) * a_g
        b = w * b_r + (1 - w) * b_g
        m.leagues[str(name)] = LeagueCalibration(
            league=str(name), n=n, a_raw=float(a_r), b_raw=float(b_r),
            a=float(a), b=float(b), shrink_weight=round(float(w), 6),
            label=("LEAGUE_TRUSTED" if w >= 0.5 else
                   "PARTIAL" if w >= 0.1 else "SHRUNK_TO_GLOBAL"))
    return m


def calibration_table(m: CalibrationModel) -> pd.DataFrame:
    """Auditable view: what each league's raw fit was, and how much of it survived shrinkage."""
    rows = [{"league": "__global__", "n": m.n_global, "a_raw": m.a_global, "b_raw": m.b_global,
             "a": m.a_global, "b": m.b_global, "shrink_weight": 1.0, "label": "GLOBAL"}]
    rows += [asdict(v) for v in m.leagues.values()]
    return pd.DataFrame(rows).sort_values("n", ascending=False).reset_index(drop=True)

"""Track evidence as of a date — uses ONLY bets settled before `as_of`.

Per model_type|market track: n, matchdays, ROI over LAST_30D / 60D / 90D / SINCE_RELIABLE_EPOCH /
FULL / CURRENT_MONTH / PREVIOUS_MONTH, a matchday-block 90% interval, a SHRUNK expected ROI, CLV,
month-to-month stability, two independent halves, league concentration and its ex-top-league
ROI. Per league: the convergence test.

SHRINKAGE (fixed before any policy was simulated, 2026-10-13). Normal-normal empirical Bayes:
    prior mean  MU0 = -0.03   (a conservative bettor's prior: you lose the margin)
    prior sd    TAU = 0.05    (real, sustainable track edges are a few percent, not tens)
    se          = block-bootstrap standard error of the track's mean unit return
    shrunk ROI  = (MU0/TAU^2 + roi/se^2) / (1/TAU^2 + 1/se^2)
n=9 at +60% (se ~0.35) shrinks to about -0.02; n=200 over many matchdays (se ~0.07) keeps
about two thirds of its edge. Small cells cannot buy a large stake.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.bankroll import PERFORMANCE_CUTOFF, RELIABLE_FROM

MU0, TAU = -0.03, 0.05
N_BOOT = 2000


def _block(units: np.ndarray, days: np.ndarray, seed: int = 0) -> tuple:
    """(se, lo90, hi90) of the mean unit return, resampling whole matchdays."""
    if len(units) < 2:
        return None, None, None
    u = pd.DataFrame({"x": units, "g": days}).groupby("g")["x"].agg(["sum", "count"])
    if len(u) < 3:
        return None, None, None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(u), size=(N_BOOT, len(u)))
    m = u["sum"].to_numpy()[idx].sum(1) / u["count"].to_numpy()[idx].sum(1)
    return float(m.std()), float(np.quantile(m, 0.05)), float(np.quantile(m, 0.95))


def shrink(roi: float | None, se: float | None) -> float:
    if roi is None or se is None or se <= 0:
        return MU0
    w_d, w_p = 1 / se ** 2, 1 / TAU ** 2
    return (MU0 * w_p + roi * w_d) / (w_p + w_d)


def _roi(x: pd.DataFrame) -> dict:
    return {"n": int(len(x)), "roi": round(float(x["unit"].mean()), 4) if len(x) else None,
            "units": round(float(x["unit"].sum()), 2)}


def track_evidence(bets: pd.DataFrame, as_of) -> dict:
    as_of = pd.Timestamp(as_of)
    b = bets[bets["date"] < as_of]
    out = {}
    cur_m = (as_of - pd.Timedelta(days=1)).to_period("M")
    for track, x in b.groupby("track"):
        x = x.sort_values("date")
        u, days = x["unit"].to_numpy(float), x["date"].dt.strftime("%Y-%m-%d").to_numpy()
        se, lo, hi = _block(u, days)
        roi = float(u.mean()) if len(u) else None
        horizons = {
            "LAST_30D": _roi(x[x["date"] >= as_of - pd.Timedelta(days=30)]),
            "LAST_60D": _roi(x[x["date"] >= as_of - pd.Timedelta(days=60)]),
            "LAST_90D": _roi(x[x["date"] >= as_of - pd.Timedelta(days=90)]),
            "SINCE_RELIABLE_EPOCH": _roi(x[x["date"] >= pd.Timestamp(RELIABLE_FROM)]),
            "FULL_PROSPECTIVE_RECORD": _roi(x),
            "CURRENT_MONTH": _roi(x[x["date"].dt.to_period("M") == cur_m]),
            "PREVIOUS_MONTH": _roi(x[x["date"].dt.to_period("M") == cur_m - 1]),
        }
        half = len(x) // 2
        h1, h2 = x.iloc[:half], x.iloc[half:]
        months = x.groupby("month")["unit"].mean()
        lg = x["league"].value_counts(normalize=True)
        top = lg.index[0] if len(lg) else None
        ex_top = x[x["league"] != top]
        clv = x["clv"].dropna()
        clv_recent = x[x["date"] >= as_of - pd.Timedelta(days=60)]["clv"].dropna()
        # price bands: is the top odds band dragging?
        bands = pd.cut(x["odds"], [1.0, 1.6, 1.9, 2.2, 2.5, 2.75, 9.0])
        band = x.groupby(bands, observed=True)["unit"].agg(["size", "mean"])
        out[track] = {
            "track": track, "n": int(len(x)), "matchdays": int(x["date"].nunique()),
            "roi": None if roi is None else round(roi, 4), "roi_se": None if se is None else round(se, 4),
            "roi_lo90": None if lo is None else round(lo, 4), "roi_hi90": None if hi is None else round(hi, 4),
            "shrunk_roi": round(shrink(roi, se), 4), "horizons": horizons,
            "half1_roi": round(float(h1["unit"].mean()), 4) if len(h1) else None,
            "half2_roi": round(float(h2["unit"].mean()), 4) if len(h2) else None,
            "months_positive": int((months > 0).sum()), "months": int(len(months)),
            "top_league": top, "top_league_share": round(float(lg.iloc[0]), 3) if len(lg) else None,
            "ex_top_league_roi": round(float(ex_top["unit"].mean()), 4) if len(ex_top) else None,
            "clv_n": int(len(clv)), "clv_median": round(float(clv.median()), 4) if len(clv) else None,
            "clv_recent_median": round(float(clv_recent.median()), 4) if len(clv_recent) else None,
            "mean_odds": round(float(x["odds"].mean()), 3),
            "odds_bands": {str(k): {"n": int(r["size"]), "roi": round(float(r["mean"]), 4)}
                           for k, r in band.iterrows()},
            "last_bet": x["date"].max().strftime("%Y-%m-%d"),
        }
    return out


def convergence_leagues(bets: pd.DataFrame, as_of, v11: pd.DataFrame, min_n: int = 20,
                        min_days: int = 8) -> list[dict]:
    """A league qualifies only when FOUR streams agree (owner brief section 3):
    A positive SHRUNK prospective ROI (not raw ROI), B non-negative median CLV,
    C v11 says Wowza adds to the market in that league, D enough observations.
    Raw ROI alone can never qualify a league: A uses the shrunk estimate and B-D must also pass."""
    as_of = pd.Timestamp(as_of)
    b = bets[bets["date"] < as_of]
    v = {} if v11 is None or v11.empty else v11.set_index("scope")["wowza_helps"].to_dict()
    rows = []
    for lg, x in b.groupby("league"):
        u = x["unit"].to_numpy(float)
        se, lo, _ = _block(u, x["date"].dt.strftime("%Y-%m-%d").to_numpy())
        roi = float(u.mean()) if len(u) else None
        clv = x["clv"].dropna()
        A = shrink(roi, se) > 0
        B = len(clv) >= 15 and float(clv.median()) >= 0
        C = bool(v.get(lg, False))
        D = len(x) >= min_n and x["date"].nunique() >= min_days
        rows.append({"league": lg, "n": int(len(x)), "matchdays": int(x["date"].nunique()),
                     "roi": None if roi is None else round(roi, 4), "shrunk_roi": round(shrink(roi, se), 4),
                     "clv_median": round(float(clv.median()), 4) if len(clv) else None,
                     "v11_wowza_helps": C, "A_shrunk_positive": bool(A), "B_clv_ok": bool(B),
                     "C_v11_supports": C, "D_enough_obs": bool(D), "qualifies": bool(A and B and C and D)})
    return sorted(rows, key=lambda r: (-int(r["qualifies"]), -r["n"]))

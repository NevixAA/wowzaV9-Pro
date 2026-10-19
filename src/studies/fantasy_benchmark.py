"""FANTASY vs the free official estimate — does Wowza add anything beyond FPL ep_next? (brief §18)

    python -m src.studies.fantasy_benchmark      # -> output/studies/fantasy_benchmark.json + challenger log

FPL's own `ep_next` is the CHAMPION until Wowza demonstrates otherwise: the live ledger shows it
beating Wowza on MAE every settled gameweek. The question is not "does V3 beat old Wowza" but
"does Wowza add predictive information BEYOND the free official estimate?"

Source: v9 output/fantasy_ledger.csv — one row per (gameweek, player): the last pre-deadline forecast
(Wowza `proj_fixture_adj`, FPL `fpl_ep_next`) and the points actually scored (settled by v9's
fantasy_settle). Nothing here re-forecasts the past.

ARMS (pre-registered 2026-10-19; every arm scored on the same player-gameweeks):
  FPL_EP_NEXT        champion
  WOWZA              Wowza's projection as published
  BLEND_50           0.5 x FPL + 0.5 x Wowza (fixed weight, no fitting)
  BLEND_WF           weight chosen on EARLIER gameweeks only (grid 0..1), applied to the next one
  RESIDUAL_WF        actual ~ a + b*ep_next + c*wowza fitted on EARLIER gameweeks only
  V3_CHALLENGER      NOT_AVAILABLE — v9's fantasy-v3 branch is unmerged and publishes no projection
WOWZA ADDS INFORMATION only if RESIDUAL_WF or BLEND_WF beats FPL_EP_NEXT out of sample with a
CI excluding zero — then, and only then, is a Wowza-informed product better than the free one.

PROSPECTIVE LOG: each newly settled gameweek is appended to output/studies/fantasy_challenger_log.csv
the first time it is scored and never rewritten.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg

OUT = cfg.OUTPUT_DIR / "studies"
LOG = OUT / "fantasy_challenger_log.csv"
CALC = "fantasy_benchmark-1.0.0"

#: Provenance of every xPts component (brief §18). Shown on the dashboard next to the numbers.
COMPONENT_LINEAGE = [
    {"component": "fpl_ep_next", "status": "OFFICIAL_FPL", "source": "FPL bootstrap-static ep_next"},
    {"component": "attack_pts (goals/assists)", "status": "MODELLED",
     "source": "Wowza player model probabilities x FPL scoring"},
    {"component": "p_start / minutes", "status": "MODELLED", "source": "Wowza minutes/availability model"},
    {"component": "cs_pts (clean sheet)", "status": "HEURISTIC", "source": "FDR-derived adjustment, not a "
     "calibrated clean-sheet probability"},
    {"component": "dc_pts (defensive contribution)", "status": "APPROXIMATION",
     "source": "proxy from tackles/interceptions history; not calibrated"},
    {"component": "bonus_pts", "status": "APPROXIMATION", "source": "expected bonus proxy; not calibrated"},
    {"component": "proj_fixture_adj (total)", "status": "MODELLED + APPROXIMATION",
     "source": "sum of the above with fixture difficulty"},
]


def _metrics(pred, act) -> dict:
    p, a = np.asarray(pred, float), np.asarray(act, float)
    ok = np.isfinite(p) & np.isfinite(a)
    p, a = p[ok], a[ok]
    if len(p) < 10:
        return {"n": int(len(p))}
    rho = pd.Series(p).rank().corr(pd.Series(a).rank())
    return {"n": int(len(p)), "mae": round(float(np.abs(p - a).mean()), 4),
            "rmse": round(float(np.sqrt(((p - a) ** 2).mean())), 4),
            "spearman": round(float(rho), 4), "bias": round(float((p - a).mean()), 4)}


def _ols(X, y):
    X1 = np.column_stack([np.ones(len(X)), X])
    return np.linalg.lstsq(X1, y, rcond=None)[0]


def arms(L: pd.DataFrame) -> pd.DataFrame:
    """Every arm's forecast per player-gameweek; walk-forward arms use earlier gameweeks only."""
    d = L.copy()
    # SAME definition v9's fantasy_settle scores (fantasy_settle.py:183-186): the per-fixture
    # projection times the probability of starting. Scoring the raw projection instead would
    # overstate Wowza's error (it assumes every player plays) — caught 2026-10-19 on first run.
    d["proj_fixture_adj"] = (pd.to_numeric(d["proj_fixture_adj"], errors="coerce")
                             * pd.to_numeric(d["p_start"], errors="coerce").clip(0, 1))
    d["FPL_EP_NEXT"] = d["fpl_ep_next"]
    d["WOWZA"] = d["proj_fixture_adj"]
    d["BLEND_50"] = 0.5 * d["fpl_ep_next"] + 0.5 * d["proj_fixture_adj"]
    d["BLEND_WF"] = np.nan
    d["RESIDUAL_WF"] = np.nan
    d["blend_weight_used"] = np.nan
    for gw in sorted(d["gw"].unique()):
        past = d[d["gw"] < gw].dropna(subset=["fpl_ep_next", "proj_fixture_adj", "actual_points"])
        cur = d["gw"] == gw
        if len(past) < 100:
            continue
        grid = np.linspace(0, 1, 21)
        maes = [np.abs(w * past["proj_fixture_adj"] + (1 - w) * past["fpl_ep_next"] - past["actual_points"]).mean()
                for w in grid]
        w = float(grid[int(np.argmin(maes))])
        d.loc[cur, "BLEND_WF"] = w * d.loc[cur, "proj_fixture_adj"] + (1 - w) * d.loc[cur, "fpl_ep_next"]
        d.loc[cur, "blend_weight_used"] = w
        b = _ols(past[["fpl_ep_next", "proj_fixture_adj"]].to_numpy(float), past["actual_points"].to_numpy(float))
        d.loc[cur, "RESIDUAL_WF"] = (b[0] + b[1] * d.loc[cur, "fpl_ep_next"] + b[2] * d.loc[cur, "proj_fixture_adj"])
    return d


def _boot_delta(a, b, act, n=2000, seed=19):
    """90% CI on MAE(a) - MAE(b), resampling player-gameweeks."""
    e = np.abs(np.asarray(a, float) - act) - np.abs(np.asarray(b, float) - act)
    e = e[np.isfinite(e)]
    if len(e) < 30:
        return [None, None]
    rng = np.random.default_rng(seed)
    m = e[rng.integers(0, len(e), size=(n, len(e)))].mean(1)
    return [round(float(np.quantile(m, 0.05)), 4), round(float(np.quantile(m, 0.95)), 4)]


def run() -> dict:
    L = pd.read_csv(cfg.V9_LOCAL / "output" / "fantasy_ledger.csv")
    L = L.dropna(subset=["actual_points"])
    d = arms(L)
    names = ["FPL_EP_NEXT", "WOWZA", "BLEND_50", "BLEND_WF", "RESIDUAL_WF"]
    by_gw = []
    for gw, g in d.groupby("gw"):
        rec = {"gw": int(gw), "n": int(len(g))}
        for a in names:
            rec[a] = _metrics(g[a], g["actual_points"])
        rec["blend_weight_used"] = None if g["blend_weight_used"].isna().all() else float(g["blend_weight_used"].iloc[0])
        by_gw.append(rec)
    # out-of-sample comparison: only gameweeks where the walk-forward arms exist
    oos = d.dropna(subset=["BLEND_WF", "RESIDUAL_WF"])
    act = oos["actual_points"].to_numpy(float)
    pooled = {a: _metrics(d[a], d["actual_points"]) for a in names[:3]}
    pooled_oos = {a: _metrics(oos[a], oos["actual_points"]) for a in names}
    vs_fpl = {a: {"mae_minus_fpl": (round(pooled_oos[a]["mae"] - pooled_oos["FPL_EP_NEXT"]["mae"], 4)
                                    if "mae" in pooled_oos.get(a, {}) and "mae" in pooled_oos["FPL_EP_NEXT"] else None),
                  "ci90": _boot_delta(oos[a], oos["FPL_EP_NEXT"], act)} for a in names[1:]}
    # in-sample residual coefficient (descriptive only, clustered by player)
    full = d.dropna(subset=["fpl_ep_next", "proj_fixture_adj", "actual_points"])
    b = _ols(full[["fpl_ep_next", "proj_fixture_adj"]].to_numpy(float), full["actual_points"].to_numpy(float))
    rng = np.random.default_rng(3)
    players = full["player_name"].unique()
    boots = []
    for _ in range(500):
        pick = rng.choice(players, len(players))
        s = pd.concat([full[full["player_name"] == p] for p in pick[:300]]) if len(players) else full
        if len(s) > 50:
            boots.append(_ols(s[["fpl_ep_next", "proj_fixture_adj"]].to_numpy(float), s["actual_points"].to_numpy(float))[2])
    adds = [x for k, x in vs_fpl.items() if k in ("BLEND_WF", "RESIDUAL_WF") and x["ci90"][1] is not None and x["ci90"][1] < 0]
    res = {"calculation_version": CALC, "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
           "gameweeks": sorted(int(x) for x in d["gw"].unique()), "player_gameweeks": int(len(d)),
           "champion": "FPL_EP_NEXT",
           "pooled_all_gws": pooled, "pooled_out_of_sample": pooled_oos, "vs_fpl_out_of_sample": vs_fpl,
           "residual_coefficient_wowza_in_sample": {"coef": round(float(b[2]), 4),
                                                    "ci90_player_bootstrap": [round(float(np.quantile(boots, .05)), 4),
                                                                              round(float(np.quantile(boots, .95)), 4)]
                                                    if boots else None,
                                                    "note": "descriptive; the out-of-sample rows decide"},
           "V3_CHALLENGER": "NOT_AVAILABLE (fantasy-v3 branch unmerged; no published V3 projection to score)",
           "WOWZA_ADDS_INFORMATION_BEYOND_FPL": "YES (out of sample)" if adds else "NO / NOT SHOWN",
           "by_gameweek": by_gw, "component_lineage": COMPONENT_LINEAGE,
           "sample_note": f"{len(d['gw'].unique())} settled gameweeks — far too few to promote anything"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "fantasy_benchmark.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    # prospective challenger log: append gameweeks never logged before, never rewrite
    old = pd.read_csv(LOG) if LOG.exists() else pd.DataFrame(columns=["gw"])
    seen = set(old["gw"].astype(int)) if len(old) else set()
    rows = []
    for r in by_gw:
        if r["gw"] in seen:
            continue
        for a in names:
            m = r[a]
            rows.append({"gw": r["gw"], "arm": a, "n": m.get("n"), "mae": m.get("mae"), "rmse": m.get("rmse"),
                         "spearman": m.get("spearman"), "logged_at": res["generated_at"], "calc": CALC})
    if rows:
        pd.DataFrame(rows).to_csv(LOG, mode="a", header=not LOG.exists(), index=False)
    return res


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: r[k] for k in ("gameweeks", "pooled_all_gws", "pooled_out_of_sample",
                                        "vs_fpl_out_of_sample", "residual_coefficient_wowza_in_sample",
                                        "WOWZA_ADDS_INFORMATION_BEYOND_FPL")}, indent=1, default=str))

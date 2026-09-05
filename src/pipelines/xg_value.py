"""
Is xG worth wiring into the O/U model? Measure it before changing production.
=============================================================================
    python -m src.pipelines.xg_value [--extra-history GLOB]

THE SITUATION. v9's team model already DECLARES four xG features:

    home_xg_last5, away_xg_last5, home_insidebox_last5, away_insidebox_last5

and its own comment admits what happens to them -- "NaN for standard leagues -> median-imputed".
Checked in the live store: all four exist in feature_snapshots and are 100% NULL, 0 of 27,610
rows, zero distinct values. The pipes are built; no water ever arrived, because af_history.parquet
(the training source) carries no xG at all. Four features in the model that actually takes money,
carrying exactly zero information.

`team_match_stats` now supplies them for the first time -- 23,854 fixtures, xG on 52.3%,
inside-box on 98.7%.

WHY MEASURE RATHER THAN JUST WIRE IT. v9 is frozen (invariant 3) and this would change model
INPUTS, which means a retrain and a revalidation of every per-league threshold. "It should help"
is not a reason to do that mid-season; a measured lift is. And a feature can easily fail to help:
xG is a noisy estimate on 52% of rows, and the model already sees shots and shots-on-target,
which carry much of the same signal.

HOW IT IS MEASURED. Strictly out of sample and strictly chronological -- rolling form is built
from PRIOR matches only (shift before rolling, so a match never sees its own result), then an
early period trains and a later period scores. Baseline is the same model without the xG columns,
so the comparison isolates the feature rather than the fit.
"""
from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ROLL = 5
TEST_FRAC = 0.25


def _load(extra: str) -> pd.DataFrame:
    from src.data import season_store as store
    d = store.read("team_match_stats")
    parts = [d] if not d.empty else []
    for f in glob.glob(extra, recursive=True) if extra else []:
        try:
            parts.append(pd.read_parquet(f))
        except Exception:                                        # noqa: BLE001
            continue
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts, ignore_index=True)
    need = {"fixture_key", "league", "match_date", "home_team", "away_team",
            "home_goals", "away_goals"}
    if not need.issubset(d.columns):
        return pd.DataFrame()
    d = d.drop_duplicates("fixture_key")
    d["_d"] = pd.to_datetime(d["match_date"], errors="coerce")
    return d.dropna(subset=["_d", "home_goals", "away_goals"]).sort_values("_d")


def _team_rows(d: pd.DataFrame) -> pd.DataFrame:
    """One row per (team, match) so rolling form can be computed per team."""
    cols = ["fixture_key", "_d", "league"]
    h = d[cols].copy()
    h["team"] = d["home_team"]; h["is_home"] = 1
    h["goals_for"] = d["home_goals"]; h["goals_against"] = d["away_goals"]
    h["xg"] = d.get("home_xg"); h["insidebox"] = d.get("home_insidebox")
    a = d[cols].copy()
    a["team"] = d["away_team"]; a["is_home"] = 0
    a["goals_for"] = d["away_goals"]; a["goals_against"] = d["home_goals"]
    a["xg"] = d.get("away_xg"); a["insidebox"] = d.get("away_insidebox")
    return pd.concat([h, a], ignore_index=True).sort_values(["team", "_d"])


def _rolling(t: pd.DataFrame) -> pd.DataFrame:
    """Last-5 form from PRIOR matches only.

    `shift(1)` BEFORE rolling is the whole leakage guard: without it a match's own xG and its own
    goals enter the features that predict it, and the model looks superb until it meets a fixture
    it has not already seen the answer to.
    """
    g = t.groupby("team", sort=False)
    for src, dst in (("goals_for", "gf"), ("goals_against", "ga"),
                     ("xg", "xg"), ("insidebox", "ib")):
        t[f"{dst}_last{ROLL}"] = (g[src].shift(1)
                                   .groupby(t["team"], sort=False)
                                   .rolling(ROLL, min_periods=2).mean()
                                   .reset_index(level=0, drop=True))
    return t


def build(d: pd.DataFrame) -> pd.DataFrame:
    t = _rolling(_team_rows(d))
    home = t[t.is_home == 1].set_index("fixture_key")
    away = t[t.is_home == 0].set_index("fixture_key")
    f = pd.DataFrame(index=home.index)
    for dst in ("gf", "ga", "xg", "ib"):
        f[f"home_{dst}"] = home[f"{dst}_last{ROLL}"]
        f[f"away_{dst}"] = away[f"{dst}_last{ROLL}"]
    f["_d"] = home["_d"]
    tot = d.set_index("fixture_key")
    f["y"] = ((tot["home_goals"] + tot["away_goals"]) > 2.5).astype(int)
    return f.dropna(subset=["home_gf", "away_gf", "y"]).sort_values("_d")


def _fit_score(tr: pd.DataFrame, te: pd.DataFrame, cols: list[str]) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss, roc_auc_score, brier_score_loss
    Xtr = tr[cols].apply(pd.to_numeric, errors="coerce")
    Xte = te[cols].apply(pd.to_numeric, errors="coerce")
    med = Xtr.median()
    # Imputed from TRAIN medians only — using the test set's own medians would leak.
    Xtr, Xte = Xtr.fillna(med).fillna(0.0), Xte.fillna(med).fillna(0.0)
    m = LogisticRegression(max_iter=2000).fit(Xtr, tr["y"])
    p = m.predict_proba(Xte)[:, 1]
    return {"logloss": round(log_loss(te["y"], p), 4),
            "auc": round(roc_auc_score(te["y"], p), 4),
            "brier": round(brier_score_loss(te["y"], p), 4)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra-history", default="")
    args = ap.parse_args()

    d = _load(args.extra_history)
    if d.empty:
        print("[xg] no team_match_stats available")
        return 1
    f = build(d)
    n_xg = int(f[["home_xg", "away_xg"]].notna().all(axis=1).sum())
    print(f"[xg] {len(f):,} fixtures with rolling form | both sides have rolling xG: "
          f"{n_xg:,} ({100*n_xg/max(len(f),1):.1f}%)")
    if len(f) < 500:
        print("[xg] too few fixtures to conclude anything")
        return 0

    cut = int(len(f) * (1 - TEST_FRAC))
    tr, te = f.iloc[:cut], f.iloc[cut:]
    base = ["home_gf", "away_gf", "home_ga", "away_ga"]
    with_ib = base + ["home_ib", "away_ib"]
    with_xg = base + ["home_xg", "away_xg"]
    both = base + ["home_ib", "away_ib", "home_xg", "away_xg"]
    print(f"[xg] train {len(tr):,} -> test {len(te):,} (chronological)\n")
    res = {}
    for name, cols in (("goals only (baseline)", base), ("+ inside-box", with_ib),
                       ("+ xG", with_xg), ("+ both", both)):
        res[name] = _fit_score(tr, te, cols)
        print(f"  {name:<24} {res[name]}")
    b = res["goals only (baseline)"]
    print()
    for name in ("+ inside-box", "+ xG", "+ both"):
        d_ll = b["logloss"] - res[name]["logloss"]
        print(f"  {name:<24} log-loss {d_ll:+.4f} vs baseline  "
              f"({'HELPS' if d_ll > 0 else 'does NOT help'})")
    print("\n[xg] NOTE: a lift here is the case for wiring this into v9's training data. v9 is "
          "frozen and this changes model INPUTS, so it needs a retrain and a revalidation of the "
          "per-league thresholds — worth doing for a measured gain, not for an expected one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

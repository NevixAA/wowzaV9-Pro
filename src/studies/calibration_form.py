"""Calibration-form challenger: v9's Platt-on-PROBABILITY vs Platt-on-LOG-ODDS (owner-approved 2026-10-14).

    python -m src.studies.calibration_form      # -> output/studies/calibration_form.json + CALIBRATION_FORM.md

WHY. Player V3 found that v9 fits its Platt calibrator on the raw probability, which on SOT 1+ cost
~0.0066 log loss and over-stated the most confident predictions (65.7% said vs 60.5% real). v9's TEAM
models (src/model.py) use the same form. This study replicates v9's OWN recipes and changes ONLY the
calibration form, so the difference is attributable to it alone.

PLAYER (all 8 markets): v9 player_model.model.train exactly - n_prev_games >= 1, date-sorted, first 68%
  fit / next 12% calibrate / last 20% test, v9's 138 features + median fill, logistic (C=0.5, scaled) and
  HGB (v9's current settings) each calibrated, then AVERAGED as v9's predict_proba does.
TEAM (O/U 1.5 / 2.5 / 3.5, BTTS): v9 src/model.train's recipe - date-sorted 80/20, last 15% of train for
  calibration, logistic (C=0.5) + GradientBoosting (300 trees, depth 4) - on Pro's leakage-proven
  prediction-lab fixture dataset (v9's own team feature table is built at train time and not committed).
For each: holdout log loss, Brier, ECE, top-5% tail, and the CALIBRATION SLOPE (y ~ a + b logit(p) on the
test slice: b > 1 means predictions are COMPRESSED toward the middle, b < 1 over-spread). Paired per-row
log-loss difference with a 95% CI by match date.
Research only: v9 is not changed. A change would be a separate, owner-approved PR.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg

OUT = cfg.OUTPUT_DIR / "studies"
PLAYER_MARKETS = {"goals": "target_goals", "goals2": "target_goals2", "assists": "target_assists",
                  "sot": "target_sot", "sot2": "target_sot2", "sot3": "target_sot3", "sot4": "target_sot4",
                  "cards": "target_cards"}
TEAM_TARGETS = ("over15", "over25", "over35", "btts")


def _lg(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _ece(p, y, bins=10):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    return float(sum((idx == b).mean() * abs(p[idx == b].mean() - y[idx == b].mean()) for b in range(bins) if (idx == b).any()))


def _slope(p, y):
    from sklearn.linear_model import LogisticRegression
    m = LogisticRegression(C=1e6, max_iter=1000).fit(_lg(p).reshape(-1, 1), y)
    return round(float(m.coef_[0][0]), 3)


def _ci(a, b, days, n=2000, seed=0):
    d = pd.DataFrame({"x": a - b, "g": days}).groupby("g")["x"].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(d), size=(n, len(d)))
    m = d["sum"].to_numpy()[i].sum(1) / d["count"].to_numpy()[i].sum(1)
    return [round(float(np.quantile(m, 0.025)), 6), round(float(np.quantile(m, 0.975)), 6)]


def _two_forms(raw_cal, y_cal, raw_test):
    from sklearn.linear_model import LogisticRegression
    v9 = LogisticRegression(C=1.0, max_iter=1000).fit(raw_cal.reshape(-1, 1), y_cal)
    lo = LogisticRegression(C=1.0, max_iter=1000).fit(_lg(raw_cal).reshape(-1, 1), y_cal)
    return (np.clip(v9.predict_proba(raw_test.reshape(-1, 1))[:, 1], 0.001, 0.999),
            np.clip(lo.predict_proba(_lg(raw_test).reshape(-1, 1))[:, 1], 0.001, 0.999))


def _compare(name, y, p_v9, p_lo, days) -> dict:
    l9, ll = _ll(p_v9, y), _ll(p_lo, y)
    top = p_lo >= np.quantile(p_lo, 0.95)
    top9 = p_v9 >= np.quantile(p_v9, 0.95)
    return {"model": name, "n_test": int(len(y)), "base_rate": round(float(y.mean()), 4),
            "logloss_v9_form": round(float(l9.mean()), 6), "logloss_logit_form": round(float(ll.mean()), 6),
            "delta_logit_minus_v9": round(float((ll - l9).mean()), 6), "ci95": _ci(ll, l9, days),
            "brier_v9_form": round(float(((p_v9 - y) ** 2).mean()), 6),
            "brier_logit_form": round(float(((p_lo - y) ** 2).mean()), 6),
            "ece_v9_form": round(_ece(p_v9, y), 5), "ece_logit_form": round(_ece(p_lo, y), 5),
            "slope_v9_form": _slope(p_v9, y), "slope_logit_form": _slope(p_lo, y),
            "spread_sd_v9_form": round(float(p_v9.std()), 4), "spread_sd_logit_form": round(float(p_lo.std()), 4),
            "top5_v9_said": round(float(p_v9[top9].mean()), 4), "top5_v9_real": round(float(y[top9].mean()), 4),
            "top5_logit_said": round(float(p_lo[top].mean()), 4), "top5_logit_real": round(float(y[top].mean()), 4)}


def player() -> list[dict]:
    import importlib.util
    import sys
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    spec = importlib.util.spec_from_file_location("v9_pcfg", cfg.V9_LOCAL / "player_model" / "config.py")
    pc = importlib.util.module_from_spec(spec); sys.modules["v9_pcfg"] = pc; spec.loader.exec_module(pc)
    feats = list(pc.PLAYER_FEATURE_COLS)
    h = pd.read_parquet(cfg.V9_LOCAL / "player_history.parquet",
                        columns=list(dict.fromkeys(feats + ["date", "n_prev_games", *PLAYER_MARKETS.values()])))
    h = h[h["n_prev_games"] >= 1].sort_values("date", kind="mergesort").reset_index(drop=True)
    out = []
    for mk, t in PLAYER_MARKETS.items():
        d = h[h[t].notna()].reset_index(drop=True)
        y = d[t].astype(int).to_numpy()
        X = d[feats].apply(pd.to_numeric, errors="coerce")
        X = X.fillna(X.median().fillna(0.0))
        n = len(d); split = int(n * 0.80); cal = int(split * 0.85)
        fit, cb, te = slice(0, cal), slice(cal, split), slice(split, n)
        keep = [c for c in feats if X[c].iloc[fit].nunique() > 1]
        lr = Pipeline([("s", StandardScaler()), ("c", LogisticRegression(max_iter=2000, C=0.5))]).fit(X.iloc[fit], y[fit])
        hg = HistGradientBoostingClassifier(max_iter=300, max_depth=3, learning_rate=0.05, min_samples_leaf=20,
                                            early_stopping=False, random_state=42).fit(X.iloc[fit][keep], y[fit])
        p9, pl = [], []
        for m, cols in ((lr, feats), (hg, keep)):
            a, b = _two_forms(m.predict_proba(X.iloc[cb][cols])[:, 1], y[cb], m.predict_proba(X.iloc[te][cols])[:, 1])
            p9.append(a); pl.append(b)
        days = pd.to_datetime(d["date"].iloc[te]).dt.strftime("%Y-%m-%d").to_numpy()
        r = _compare(f"player:{mk}", y[te].astype(float), np.mean(p9, axis=0), np.mean(pl, axis=0), days)
        out.append(r)
        print(r["model"], r["delta_logit_minus_v9"], r["ci95"], "slope v9", r["slope_v9_form"], "-> logit", r["slope_logit_form"])
    return out


def team() -> list[dict]:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from src.prediction_lab import features as PF
    from src.prediction_lab import run as PR
    df = PR.load().sort_values("date", kind="mergesort").reset_index(drop=True)
    fc = PF.feature_columns(df, PF.FOOTBALL_FAMILIES)
    out = []
    for t in TEAM_TARGETS:
        d = df[df[t].notna()].reset_index(drop=True)
        y = d[t].astype(int).to_numpy()
        X = d[fc].apply(pd.to_numeric, errors="coerce")
        X = X.fillna(X.median().fillna(0.0))
        n = len(d); split = int(n * 0.80); cal = int(split * 0.85)
        fit, cb, te = slice(0, cal), slice(cal, split), slice(split, n)
        p9, pl = [], []
        for clf in (LogisticRegression(max_iter=2000, C=0.5),
                    GradientBoostingClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8,
                                               min_samples_leaf=20, random_state=42)):
            m = Pipeline([("s", StandardScaler()), ("c", clf)]).fit(X.iloc[fit], y[fit])
            a, b = _two_forms(m.predict_proba(X.iloc[cb])[:, 1], y[cb], m.predict_proba(X.iloc[te])[:, 1])
            p9.append(a); pl.append(b)
        days = pd.to_datetime(d["date"].iloc[te]).dt.strftime("%Y-%m-%d").to_numpy()
        r = _compare(f"team:{t}", y[te].astype(float), np.mean(p9, axis=0), np.mean(pl, axis=0), days)
        out.append(r)
        print(r["model"], r["delta_logit_minus_v9"], r["ci95"], "slope v9", r["slope_v9_form"], "-> logit", r["slope_logit_form"])
    return out


def to_md(rows: list[dict]) -> str:
    L = ["# Calibration form: v9's Platt-on-probability vs Platt-on-log-odds", "",
         "Same models, same split, ONLY the calibration form differs. Negative delta = log-odds form better. "
         "Slope > 1 = predictions compressed toward the middle; 1 = right; < 1 = over-spread.", "",
         "| Model | Test n | Log loss v9 / log-odds | Delta (95% CI) | ECE v9 / log-odds | Slope v9 / log-odds | Top 5%: v9 said/real | Top 5%: log-odds said/real |",
         "|---|---:|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['model']} | {r['n_test']:,} | {r['logloss_v9_form']} / {r['logloss_logit_form']} | "
                 f"{r['delta_logit_minus_v9']:+.5f} {r['ci95']} | {r['ece_v9_form']} / {r['ece_logit_form']} | "
                 f"{r['slope_v9_form']} / {r['slope_logit_form']} | {r['top5_v9_said']} / {r['top5_v9_real']} | "
                 f"{r['top5_logit_said']} / {r['top5_logit_real']} |")
    L += ["", "Research only. Changing v9's calibrators would alter every probability, edge and tier, so it needs "
              "its own owner-approved PR and a shadow period."]
    return "\n".join(L) + "\n"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = player() + team()
    (OUT / "calibration_form.json").write_text(json.dumps({"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                                                           "rows": rows}, indent=1), encoding="utf-8")
    (OUT / "CALIBRATION_FORM.md").write_text(to_md(rows), encoding="utf-8")
    print(to_md(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

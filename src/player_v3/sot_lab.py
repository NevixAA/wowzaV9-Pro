"""SOT Matchup Lab — H1 (minutes), H2 (count model), H3 (usage), H4/H5 (personnel/matchup), role,
ablation and calibration, all on ONE frozen chronological split.

    python -m src.player_v3.sot_lab        # -> output/player_v3/*.csv + sot_lab_results.json

Protocol (fixed before results): learner = HGB (v9's own settings), fit on TRAIN (< 2025-02-01),
Platt-calibrated on VALIDATION (Feb-Jun 2025), scored ONCE on HOLDOUT (>= 2025-07-01).
Every variant is the champion's view (v9's 138 features, BASE_V9) plus exactly one family, so each
answer is "what does THIS family add". Paired comparison: per-row log-loss difference vs BASE_V9,
95% CI by matchday-block bootstrap. Population = appearances (as v9 trains), so H1 is tested as
"does an expected-minutes estimate add information", not by re-weighting the population.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.player_v3 import CALC_VERSION, HOLDOUT_FROM, TRAIN_END, VALID_END
from src.player_v3 import data as D
from src.player_v3 import features as F

OUT = cfg.OUTPUT_DIR / "player_v3"
CACHE = cfg.BASE_DIR / "experiments" / "player_v3"
HGB = dict(max_iter=300, max_depth=3, learning_rate=0.05, min_samples_leaf=20, early_stopping=False,
           random_state=42)
LINES = {"sot": 1, "sot2": 2, "sot3": 3, "sot4": 4}


def _ll(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _ece(p, y, bins=10):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    return float(sum((idx == b).mean() * abs(p[idx == b].mean() - y[idx == b].mean()) for b in range(bins) if (idx == b).any()))


def _ci(a, b, days, n=2000, seed=0):
    d = pd.DataFrame({"x": a - b, "g": days}).groupby("g")["x"].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(d), size=(n, len(d)))
    m = d["sum"].to_numpy()[i].sum(1) / d["count"].to_numpy()[i].sum(1)
    return [round(float(np.quantile(m, 0.025)), 6), round(float(np.quantile(m, 0.975)), 6)]


def _usable(X):
    v = X.to_numpy(float)
    return [c for j, c in enumerate(X.columns) if np.isfinite(v[:, j]).sum() > 1
            and np.nanmax(v[:, j]) > np.nanmin(v[:, j])]


def fit_binary(X: pd.DataFrame, y: np.ndarray, tr, va, model: str = "hgb", calib: str = "logit"):
    """Fit on train, Platt on validation; returns calibrated probabilities for every row.

    calib="logit": Platt on the log-odds of the raw score (the standard form) - the default.
    calib="v9": Platt on the raw PROBABILITY, exactly as v9's player_model.model.train does. Found
    2026-10-14: on SOT 1+ that form costs ~0.0066 log loss vs the logit form - it was silently
    inflating every V3 comparison against v9's calibration, so all evidence now uses "logit" and
    v9's method appears only as an explicit reference row."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    cols = _usable(X[tr])
    if model == "hgb":
        m = HistGradientBoostingClassifier(**HGB).fit(X.loc[tr, cols], y[tr])
    else:
        m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                          LogisticRegression(max_iter=1000, C=0.5)).fit(X.loc[tr, cols], y[tr])
    raw = m.predict_proba(X[cols])[:, 1]
    z = raw if calib == "v9" else np.log(np.clip(raw, 1e-6, 1 - 1e-6) / (1 - np.clip(raw, 1e-6, 1 - 1e-6)))
    pl = LogisticRegression(C=1.0, max_iter=1000).fit(z[va].reshape(-1, 1), y[va])
    return np.clip(pl.predict_proba(z.reshape(-1, 1))[:, 1], 0.001, 0.999), raw


def score(p, y, days, ref=None) -> dict:
    ll = _ll(p, y)
    from sklearn.metrics import roc_auc_score
    r = {"n": int(len(y)), "log_loss": round(float(ll.mean()), 6), "brier": round(float(((p - y) ** 2).mean()), 6),
         "auc": round(float(roc_auc_score(y, p)), 4), "ece": round(_ece(p, y), 5)}
    if ref is not None:
        r["ll_diff_vs_base"] = round(float((ll - ref).mean()), 6)
        r["ci95"] = _ci(ll, ref, days)
        r["verdict"] = ("BETTER" if r["ci95"][1] < 0 else "WORSE" if r["ci95"][0] > 0 else "NO_DIFFERENCE")
    return r


def load_features() -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / "features.parquet"
    if f.exists():
        X = pd.read_parquet(f)
        F.build.__globals__["FAMILIES"].update(json.loads((CACHE / "families.json").read_text()))
        return X
    X = F.build()
    X.to_parquet(f)
    (CACHE / "families.json").write_text(json.dumps(F.FAMILIES))
    return X


def expected_minutes(X: pd.DataFrame) -> pd.DataFrame:
    """Phase B's HGB expected-minutes outputs joined onto appearances (as-of, fit on TRAIN)."""
    f = CACHE / "minutes_preds.parquet"
    if f.exists():
        return _one_per_key(pd.read_parquet(f))
    from src.player_v3 import minutes as M
    p = M.add_features(M.build_panel())
    pr = M.predictions(p)["HGB"]
    out = pd.DataFrame({"player_id": p["player_id"], "fixture_id": p["fixture_id"],
                        "xm_start": pr["start"], "xm_minutes": pr["minutes"], "xm_m60": pr["m60"],
                        "xm_m75": pr["m75"], "xm_m90": pr["m90"]})
    out.to_parquet(f)
    return _one_per_key(out)


def _one_per_key(xm: pd.DataFrame) -> pd.DataFrame:
    """One row per (player, fixture). player_id 0 is v9's placeholder for an unidentified player and
    can sit on both teams of one fixture; merging it duplicated 232 of 857,450 appearance rows
    (found 2026-10-14, too few to move a result, removed anyway)."""
    return xm[xm["player_id"] != 0].drop_duplicates(["player_id", "fixture_id"], keep="first")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    X = load_features()
    fam = F.FAMILIES
    xm = expected_minutes(X)
    X = X.merge(xm, on=["player_id", "fixture_id"], how="left")
    fam["MINUTES_V3"] = ["xm_start", "xm_minutes", "xm_m60", "xm_m75", "xm_m90"]
    tr, va, ho = (m.to_numpy() for m in D.chrono_split(X["date"], TRAIN_END, VALID_END, HOLDOUT_FROM))
    days = X.loc[ho, "date"].dt.strftime("%Y-%m-%d").to_numpy()
    res = {"calculation_version": CALC_VERSION, "split": [TRAIN_END, VALID_END, HOLDOUT_FROM],
           "n": {"train": int(tr.sum()), "validation": int(va.sum()), "holdout": int(ho.sum())}}
    base = fam["BASE_V9"]
    v3 = [c for k in ("FORM_MH", "FORM_SHRUNK", "USAGE_SHARE", "TEAM_ENV", "OPP_PERSONNEL", "MATCHUP_RAW",
                      "ROLE", "MINUTES_V3") for c in fam[k]]
    variants = {
        "E0_BASE_V9": base, "E1_+FORM_MH": base + fam["FORM_MH"], "E2_+FORM_SHRUNK": base + fam["FORM_SHRUNK"],
        "E3_+USAGE_SHARE": base + fam["USAGE_SHARE"] + fam["TEAM_ENV"],
        "E4_+OPP_PERSONNEL": base + fam["OPP_PERSONNEL"],
        "E5_+PERSONNEL+MATCHUP": base + fam["OPP_PERSONNEL"] + fam["MATCHUP_RAW"],
        "E6_+ROLE": base + fam["ROLE"], "E9_+EXPECTED_MINUTES": base + fam["MINUTES_V3"],
        "E7_ALL_V3": base + v3,
    }
    study = []
    probs = {}
    for target in ("sot", "sot2"):
        y = X[f"target_{target}"].fillna(0).astype(int).to_numpy()
        ref = None
        for name, cols in variants.items():
            p, _ = fit_binary(X[cols], y, tr, va)
            probs[(target, name)] = p
            r = score(p[ho], y[ho], days, None if ref is None else ref)
            if name == "E0_BASE_V9":
                ref = _ll(p[ho], y[ho])
            study.append({"target": target, "variant": name, "n_features": len(cols), **r})
            print(target, name, r)
        p, _ = fit_binary(X[base], y, tr, va, model="logit")
        study.append({"target": target, "variant": "E8_LOGISTIC_BASE", "n_features": len(base),
                      **score(p[ho], y[ho], days, ref)})
        p, _ = fit_binary(X[base], y, tr, va, calib="v9")
        study.append({"target": target, "variant": "R0_BASE_V9_WITH_V9_PLATT", "n_features": len(base),
                      **score(p[ho], y[ho], days, ref)})
    st = pd.DataFrame(study)
    st.insert(0, "calculation_version", CALC_VERSION)
    st.to_csv(OUT / "feature_variants.csv", index=False)
    st[st["variant"].str.contains("USAGE|BASE_V9|FORM")].to_csv(OUT / "usage_share_study.csv", index=False)
    st[st["variant"].str.contains("PERSONNEL|BASE_V9")].to_csv(OUT / "matchup_study.csv", index=False)
    st[st["variant"].str.contains("ROLE|BASE_V9")].to_csv(OUT / "role_study.csv", index=False)
    res["variants"] = study

    # ── H2: count distribution vs four independent binary models (same features, same rows) ──
    res["count_model"] = count_models(X, base + v3, tr, va, ho, days)
    # ── ablation: drop one family at a time from ALL_V3 (SOT 1+) ──
    res["ablation"] = ablation(X, fam, base, v3, tr, va, ho, days)
    # ── calibration challengers on the ALL_V3 SOT 1+ scores ──
    res["calibration"] = calibration(X, base + v3, tr, va, ho)
    (OUT / "sot_lab_results.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return 0


def count_models(X, cols, tr, va, ho, days) -> list[dict]:
    from scipy.stats import nbinom, poisson
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import PoissonRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    cnt = X["shots_on_target"].fillna(0).clip(0, 12).to_numpy(float)
    use = _usable(X.loc[tr, cols])
    hg = HistGradientBoostingRegressor(loss="poisson", **{k: v for k, v in HGB.items() if k != "random_state"},
                                       random_state=42).fit(X.loc[tr, use], cnt[tr])
    mu_h = np.clip(hg.predict(X[use]), 1e-4, 15)
    glm = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), PoissonRegressor(alpha=1e-4, max_iter=300))
    mu_g = np.clip(glm.fit(X.loc[tr, use], cnt[tr]).predict(X[use]), 1e-4, 15)
    # NB dispersion: MLE of alpha on VALIDATION given the HGB mean (grid; never the holdout)
    grid = np.array([0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0])
    def nb_ll(a, mu, y):
        n = 1 / a
        return nbinom.logpmf(y, n, n / (n + mu)).sum()
    alpha = float(grid[np.argmax([nb_ll(a, mu_h[va], cnt[va]) for a in grid])])
    out = [{"model": "HGB_POISSON_MEAN+NB", "nb_alpha_from_validation": alpha}]
    bin_probs = {}
    for t, k in LINES.items():
        y = X[f"target_{t}"].fillna(0).astype(int).to_numpy()
        pb, _ = fit_binary(X[cols], y, tr, va)
        pv9, _ = fit_binary(X[cols], y, tr, va, calib="v9")
        bin_probs[t] = pb
        n = 1 / alpha
        cand = {"BINARY_HGB": pb, "BINARY_HGB_V9_PLATT": pv9,
                "POISSON_GLM": 1 - poisson.cdf(k - 1, mu_g),
                "HGB_POISSON": 1 - poisson.cdf(k - 1, mu_h),
                "HGB_MEAN_NB": 1 - nbinom.cdf(k - 1, n, n / (n + mu_h))}
        ref = _ll(pb[ho], y[ho])
        for name, p in cand.items():
            p = np.clip(p, 1e-4, 1 - 1e-4)
            r = score(p[ho], y[ho], days, None if name == "BINARY_HGB" else ref)
            out.append({"line": f"{k}+", "model": name, **r})
            print("count", t, name, r)
    viol = ((bin_probs["sot2"] > bin_probs["sot"] + 1e-9) | (bin_probs["sot3"] > bin_probs["sot2"] + 1e-9)
            | (bin_probs["sot4"] > bin_probs["sot3"] + 1e-9))[ho]
    out.append({"model": "BINARY_HGB", "monotonic_violation_share": round(float(viol.mean()), 5)})
    out.append({"model": "COUNT_MODELS", "monotonic_violation_share": 0.0})
    df = pd.DataFrame(out)
    df.insert(0, "calculation_version", CALC_VERSION)
    df.to_csv(OUT / "sot_distribution_comparison.csv", index=False)
    return out


def ablation(X, fam, base, v3, tr, va, ho, days) -> list[dict]:
    y = X["target_sot"].fillna(0).astype(int).to_numpy()
    full = base + v3
    pf, _ = fit_binary(X[full], y, tr, va)
    ref = _ll(pf[ho], y[ho])
    rows = [{"dropped": "NONE (ALL_V3)", **score(pf[ho], y[ho], days)}]
    groups = {k: fam[k] for k in ("BASE_V9", "FORM_MH", "FORM_SHRUNK", "USAGE_SHARE", "TEAM_ENV",
                                   "OPP_PERSONNEL", "MATCHUP_RAW", "ROLE", "MINUTES_V3")}
    composites = [c for c in base if c.endswith(("_score", "_index", "_composite", "_edge", "_interaction"))]
    groups["V9_HANDCRAFTED_COMPOSITES"] = composites
    for g, cols in groups.items():
        keep = [c for c in full if c not in set(cols)]
        p, _ = fit_binary(X[keep], y, tr, va)
        r = score(p[ho], y[ho], days, ref)
        r["family_contribution"] = ("NEEDED" if r["verdict"] == "WORSE" else
                                    "REDUNDANT_IN_V3_CHALLENGER" if r["verdict"] != "WORSE" else "")
        rows.append({"dropped": g, "n_dropped": len(cols), **r})
        print("ablation", g, r)
    df = pd.DataFrame(rows)
    df.insert(0, "calculation_version", CALC_VERSION)
    df.to_csv(OUT / "feature_family_ablation.csv", index=False)
    return rows


def calibration(X, cols, tr, va, ho) -> list[dict]:
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    y = X["target_sot"].fillna(0).astype(int).to_numpy()
    _, raw = fit_binary(X[cols], y, tr, va)
    lg = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))  # noqa: E731
    out = {}
    v9p = LogisticRegression(max_iter=1000).fit(raw[va].reshape(-1, 1), y[va])
    out["V9_PLATT_ON_PROBABILITY"] = v9p.predict_proba(raw.reshape(-1, 1))[:, 1]
    pl = LogisticRegression(max_iter=1000).fit(lg(raw[va]).reshape(-1, 1), y[va])
    out["GLOBAL_PLATT"] = pl.predict_proba(lg(raw).reshape(-1, 1))[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-3, y_max=1 - 1e-3).fit(raw[va], y[va])
    out["GLOBAL_ISOTONIC"] = iso.predict(raw)
    for grp in ("position", "league"):
        p = out["GLOBAL_PLATT"].copy()
        for g, idx in X.groupby(grp).groups.items():
            m = np.zeros(len(X), bool); m[np.asarray([X.index.get_loc(i) for i in idx])] = True
            if (m & va).sum() >= 3000:           # partial pooling: small groups keep the global map
                c = LogisticRegression(max_iter=1000).fit(lg(raw[m & va]).reshape(-1, 1), y[m & va])
                p[m] = c.predict_proba(lg(raw[m]).reshape(-1, 1))[:, 1]
        out[f"{grp.upper()}_PLATT_POOLED"] = p
    rows = []
    hy = y[ho]
    for name, p in out.items():
        q = np.clip(p[ho], 1e-4, 1 - 1e-4)
        top = q >= np.quantile(q, 0.95)
        rows.append({"method": name, "log_loss": round(float(_ll(q, hy).mean()), 6),
                     "brier": round(float(((q - hy) ** 2).mean()), 6), "ece": round(_ece(q, hy), 5),
                     "top5pct_pred": round(float(q[top].mean()), 4), "top5pct_actual": round(float(hy[top].mean()), 4)})
    df = pd.DataFrame(rows)
    df.insert(0, "calculation_version", CALC_VERSION)
    df.to_csv(OUT / "player_calibration.csv", index=False)
    return rows


if __name__ == "__main__":
    raise SystemExit(main())

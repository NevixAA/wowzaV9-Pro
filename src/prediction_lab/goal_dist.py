"""Model the SCORELINE and derive the markets from it, instead of fitting four separate models.

    python -m src.prediction_lab.goal_dist

THE IDEA. Over 1.5, Over 2.5, Over 3.5 and BTTS are not four independent facts about a football
match -- they are four readings of one thing, the joint distribution of (home goals, away goals).
So instead of four classifiers that each rediscover "goals" from scratch, predict expected goals
for each side, build the score matrix, and read every market off it.

TWO THINGS THAT SHOULD FOLLOW, AND ONE THAT MIGHT NOT.

Should follow (1): INTERNAL CONSISTENCY, FOR FREE. Four independent classifiers can and do emit
P(Over 3.5) > P(Over 2.5), which is impossible -- four goals implies three. A score matrix cannot
produce that because the probabilities are sums over nested sets of the same matrix. This is
measured here, not assumed: the violation rate of the binary models is counted.

Should follow (2): better use of thin data. Every fixture teaches the scoreline model about every
market at once.

Might not follow: better SCORES. A Poisson model imposes a shape on the data, and if real
football does not have that shape the constraint costs more than it buys. Which is why this is a
measured comparison on identical test fixtures, not an argument.

THE DIXON-COLES CORRECTION exists because independent Poisson is known to be wrong in one
specific, well-documented place: it under-predicts 0-0 and 1-1 and over-predicts 1-0 and 0-1.
Real matches are not two independent scoring processes -- a 1-1 is "stickier" than independence
implies. The correction re-weights exactly those four cells by a single parameter rho, fitted on
TRAIN ONLY. If rho comes back near zero, independence was fine and that is a finding too.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy.stats import poisson

from src.prediction_lab import data as D
from src.prediction_lab import experiments as E
from src.prediction_lab import features as F
from src.prediction_lab import folds as FO
from src.prediction_lab import metrics as M
from src.prediction_lab import run as R

CALC_VERSION = "1.0.0"
MAXG = 12                       # score matrix is 13x13; P(7+ goals a side) is ~1e-5
RHO_GRID = np.arange(-0.25, 0.2501, 0.01)


def _score_matrix(lam_h: np.ndarray, lam_a: np.ndarray, rho: float = 0.0) -> np.ndarray:
    """(n, MAXG+1, MAXG+1) joint score probabilities, optionally Dixon-Coles corrected."""
    ks = np.arange(MAXG + 1)
    ph = poisson.pmf(ks[None, :], lam_h[:, None])       # (n, G)
    pa = poisson.pmf(ks[None, :], lam_a[:, None])
    m = ph[:, :, None] * pa[:, None, :]
    if rho:
        lh, la = lam_h[:, None], lam_a[:, None]
        tau = np.ones_like(m)
        tau[:, 0, 0] = (1 - (lam_h * lam_a * rho)).clip(1e-6)
        tau[:, 0, 1] = (1 + lam_h * rho).clip(1e-6)
        tau[:, 1, 0] = (1 + lam_a * rho).clip(1e-6)
        tau[:, 1, 1] = max(1 - rho, 1e-6)
        m = m * tau
    return m / m.sum(axis=(1, 2), keepdims=True)


def _markets_from_matrix(m: np.ndarray) -> dict[str, np.ndarray]:
    """Read every market off the score matrix. Nested by construction, so never inconsistent."""
    ks = np.arange(MAXG + 1)
    tot = ks[:, None] + ks[None, :]
    out = {}
    for name, thr in (("over15", 2), ("over25", 3), ("over35", 4)):
        out[name] = m[:, tot >= thr].sum(axis=1)
    out["btts"] = m[:, 1:, 1:].sum(axis=(1, 2))
    out["home_scores"] = m[:, 1:, :].sum(axis=(1, 2))
    out["away_scores"] = m[:, :, 1:].sum(axis=(1, 2))
    out["exp_goals"] = (m * tot[None, :, :]).sum(axis=(1, 2))
    return out


def _fit_rho(hg: np.ndarray, ag: np.ndarray, lam_h: np.ndarray, lam_a: np.ndarray) -> float:
    """Grid-search rho by training log-likelihood. TRAIN ONLY -- it is a fitted parameter."""
    h = np.clip(hg.astype(int), 0, MAXG)
    a = np.clip(ag.astype(int), 0, MAXG)
    best, best_ll = 0.0, -np.inf
    for rho in RHO_GRID:
        m = _score_matrix(lam_h, lam_a, float(rho))
        ll = np.log(np.clip(m[np.arange(len(h)), h, a], 1e-12, None)).mean()
        if ll > best_ll:
            best, best_ll = float(rho), float(ll)
    return best


def _lambda_models(X_tr, hg_tr, ag_tr):
    """Expected goals per side. Poisson deviance objective, not squared error -- goal counts are
    counts, and a squared-error fit on them is both biased and able to predict negatives."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    kw = dict(loss="poisson", max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
              min_samples_leaf=40, l2_regularization=1.0, early_stopping=True,
              validation_fraction=0.12, random_state=0)
    mh = HistGradientBoostingRegressor(**kw).fit(X_tr, hg_tr)
    ma = HistGradientBoostingRegressor(**kw).fit(X_tr, ag_tr)
    return mh, ma


def walk_forward_scoreline(df: pd.DataFrame, feat_cols: list[str],
                           fl: list[FO.Fold]) -> pd.DataFrame:
    """OOS market probabilities derived from a fitted scoreline model, per fold."""
    X = df[feat_cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    hg = df["home_goals"].to_numpy(dtype=float)
    ag = df["away_goals"].to_numpy(dtype=float)
    dates = pd.to_datetime(df["date"]).to_numpy()
    rows = []
    for f in fl:
        mh, ma = _lambda_models(X[f.train], hg[f.train], ag[f.train])
        lam_tr_h = np.clip(mh.predict(X[f.train]), 0.05, 6.0)
        lam_tr_a = np.clip(ma.predict(X[f.train]), 0.05, 6.0)
        rho = _fit_rho(hg[f.train], ag[f.train], lam_tr_h, lam_tr_a)
        lh = np.clip(mh.predict(X[f.test]), 0.05, 6.0)
        la = np.clip(ma.predict(X[f.test]), 0.05, 6.0)
        for tag, r in (("bipoisson", 0.0), ("bipoisson_dc", rho)):
            mk = _markets_from_matrix(_score_matrix(lh, la, r))
            base = pd.DataFrame({
                "fixture_key": df["fixture_key"].to_numpy()[f.test], "date": dates[f.test],
                "league": df["league"].to_numpy()[f.test],
                "model_type": df["model_type"].to_numpy()[f.test],
                "fold": f.name, "model": tag, "rho": r,
                "lam_home": lh, "lam_away": la})
            for t in ("btts", "over15", "over25", "over35", "home_scores", "away_scores"):
                x = base.copy()
                x["target"] = t
                x["p"] = mk[t]
                x["y"] = df[t].to_numpy()[f.test]
                x["threshold"] = 0.5
                x["threshold_bal"] = 0.5
                rows.append(x)
    return pd.concat(rows, ignore_index=True)


def consistency_violations(wide: pd.DataFrame) -> dict:
    """How often does a set of probabilities claim something impossible? (rule 31)"""
    v15_25 = float((wide["p_over25"] > wide["p_over15"] + 1e-9).mean())
    v25_35 = float((wide["p_over35"] > wide["p_over25"] + 1e-9).mean())
    v_btts = float((wide["p_btts"] > wide["p_over15"] + 1e-9).mean())
    return {"p_over25_gt_p_over15": round(v15_25, 5),
            "p_over35_gt_p_over25": round(v25_35, 5),
            "p_btts_gt_p_over15": round(v_btts, 5),
            "any_violation": round(float(((wide["p_over25"] > wide["p_over15"] + 1e-9)
                                          | (wide["p_over35"] > wide["p_over25"] + 1e-9)
                                          | (wide["p_btts"] > wide["p_over15"] + 1e-9)).mean()), 5)}


def _wide(oof: pd.DataFrame) -> pd.DataFrame:
    w = oof.pivot_table(index="fixture_key", columns="target", values="p", aggfunc="last")
    return w.rename(columns={c: f"p_{c}" for c in w.columns})


def main() -> int:
    ap = argparse.ArgumentParser()
    a = ap.parse_args()
    out = D.out_dir()
    df = R.load()
    fl = FO.rolling_folds(df)
    fc = F.feature_columns(df, F.FOOTBALL_FAMILIES)
    print(f"[goal_dist] {len(df):,} fixtures, {len(fl)} folds, {len(fc)} football features")

    sl = walk_forward_scoreline(df, fc, fl)
    sl.to_parquet(out / "scoreline_oof.parquet", index=False)
    print(f"[goal_dist] Dixon-Coles rho per fold: "
          f"{sorted(set(sl[sl.model == 'bipoisson_dc'].rho.round(3)))}")

    binary = pd.read_parquet(out / "oof_probabilities.parquet")
    rows = []
    for t in ("btts", "over15", "over25", "over35", "home_scores", "away_scores"):
        b = binary[binary.target == t]
        if not b.empty:
            r = E.score(b, label=f"{t}/binary_classifiers")
            r.update({"target": t, "approach": "binary_classifiers"})
            rows.append(r)
        for tag in ("bipoisson", "bipoisson_dc"):
            g = sl[(sl.target == t) & (sl.model == tag)]
            if g.empty:
                continue
            r = E.score(g, label=f"{t}/{tag}")
            r.update({"target": t, "approach": tag})
            rows.append(r)
    tab = pd.DataFrame(rows)
    tab.to_csv(out / "goal_distribution_comparison.csv", index=False)

    print("\nSCORELINE MODEL vs FOUR SEPARATE CLASSIFIERS -- identical test fixtures")
    print(f"  {'target':<13}{'approach':<22}{'n':>8}{'logloss':>10}{'brier':>9}{'auc':>8}{'lift':>9}")
    for t in ("btts", "over15", "over25", "over35"):
        for _, r in tab[tab.target == t].iterrows():
            print(f"  {t:<13}{r.approach:<22}{int(r.n):>8}{r.log_loss:>10.5f}{r.brier:>9.5f}"
                  f"{r.auc:>8.4f}{r.lift_pp:>+8.2f}pp")

    # Consistency: can these probabilities contradict themselves?
    wb = _wide(binary[binary.target.isin(("btts", "over15", "over25", "over35"))])
    wd = _wide(sl[(sl.model == "bipoisson_dc")
                  & sl.target.isin(("btts", "over15", "over25", "over35"))])
    cons = pd.DataFrame([{"approach": "binary_classifiers", **consistency_violations(wb)},
                         {"approach": "bipoisson_dc", **consistency_violations(wd)}])
    cons.to_csv(out / "consistency_violations.csv", index=False)
    print("\nIMPOSSIBLE PROBABILITY ORDERINGS (share of fixtures):")
    print(cons.to_string(index=False))
    print("  A scoreline model cannot produce these; they are sums over nested sets of one matrix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

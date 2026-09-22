"""Prove the feature matrix cannot see the future. Phase 1 does not end until this passes.

    python -m src.prediction_lab.leakage

THE TEST THAT MATTERS IS A PERTURBATION TEST, NOT AN INSPECTION. Reading the feature code and
concluding "this looks pre-match" is how leaks survive review -- the three mtime bugs in this
estate all looked fine. So this module does something a reading cannot do:

    1. Build the features normally.
    2. Pick a cutoff date T. RANDOMISE THE SCORELINE of every fixture from T onward.
    3. Rebuild the features from scratch.
    4. Every feature value on every fixture strictly BEFORE T must be bit-identical.

If a single value moves, some feature on an earlier match consumed a result that had not
happened yet. That is leakage, located precisely, with no judgement call involved. The test runs
at several cutoffs so almost every row gets checked as "the past" at least once.

A SECOND TEST CATCHES THE OTHER DIRECTION. A feature could be pre-match in construction and
still be the answer in disguise -- a "rolling goals" column that accidentally included the
current match would show a near-perfect single-feature AUC. So every feature is scored alone
against every target, and anything above 0.80 is reported for inspection. Real football features
sit between 0.50 and 0.60; this is not a pass/fail line, it is a tripwire.

WHAT THIS DOES NOT TEST. It cannot tell you whether the underlying SOURCE was recorded before
kickoff -- if v9 wrote a fixture's shot count into a row dated before the match, this test sees a
consistent past and passes. That is a collection-side question, answered in the inventory by
whether a column exists at all, not here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.prediction_lab import data as D
from src.prediction_lab import features as F

CALC_VERSION = "1.0.0"
CUTOFF_QUANTILES = (0.05, 0.25, 0.55, 0.85)
SINGLE_FEATURE_AUC_TRIPWIRE = 0.80


def _auc(y: np.ndarray, x: np.ndarray) -> float:
    """Rank AUC, NaN-safe. No sklearn import for a two-line computation."""
    m = ~(np.isnan(x) | np.isnan(y))
    y, x = y[m], x[m]
    if len(y) < 50 or y.min() == y.max():
        return float("nan")
    r = pd.Series(x).rank().to_numpy()
    n1 = float(y.sum())
    n0 = float(len(y) - n1)
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def perturbation_test(fx: pd.DataFrame, *, seed: int = 11, verbose: bool = True) -> pd.DataFrame:
    """Randomise the future, rebuild, and demand the past did not move."""
    rng = np.random.default_rng(seed)
    base = F.build(fx).set_index("fixture_key").sort_index()
    fam = F.family_columns(base)
    feat_cols = [c for fs in fam.values() for c in fs]
    rows = []
    for q in CUTOFF_QUANTILES:
        T = fx["date"].quantile(q)
        pert = fx.copy()
        fut = pert["date"] >= T
        n_fut = int(fut.sum())
        # Randomise the RESULT of every future fixture, then recompute the targets from it, so
        # the perturbed world is internally consistent rather than half-rewritten.
        pert.loc[fut, "home_goals"] = rng.integers(0, 5, n_fut)
        pert.loc[fut, "away_goals"] = rng.integers(0, 5, n_fut)
        for c in ("home_shots", "away_shots", "home_sot", "away_sot", "home_corners",
                  "away_corners", "home_fouls", "away_fouls", "ht_home_goals", "ht_away_goals",
                  "home_yellow", "away_yellow"):
            if c in pert.columns:
                pert.loc[fut, c] = rng.integers(0, 15, n_fut).astype(float)
        pert = D._attach_targets(pert)

        re = F.build(pert).set_index("fixture_key").sort_index()
        past = base.index[base["date"] < T]
        a = base.loc[past, feat_cols]
        b = re.loc[past, feat_cols]
        # NaN == NaN must count as equal; a straight != would flag every unpopulated cell.
        diff = ~((a.to_numpy() == b.to_numpy()) | (a.isna().to_numpy() & b.isna().to_numpy()))
        bad_cols = [c for c, n in zip(feat_cols, diff.sum(axis=0)) if n > 0]
        rows.append({"cutoff_q": q, "cutoff_date": str(pd.Timestamp(T).date()),
                     "past_rows": len(past), "future_rows": n_fut,
                     "cells_changed": int(diff.sum()), "columns_leaking": len(bad_cols),
                     "leaking": ";".join(bad_cols[:12])})
        if verbose:
            v = "CLEAN" if diff.sum() == 0 else f"LEAK in {len(bad_cols)} cols"
            print(f"  cutoff {q:.0%} ({str(pd.Timestamp(T).date())}): "
                  f"{len(past):,} past rows checked -> {v}")
            if bad_cols:
                print(f"     {bad_cols[:12]}")
    return pd.DataFrame(rows)


def tripwire_test(df: pd.DataFrame, *, verbose: bool = True) -> pd.DataFrame:
    """Single-feature AUC against each target. A real football feature cannot be near-perfect."""
    fam = F.family_columns(df)
    rows = []
    for t in ("btts", "over15", "over25", "over35"):
        y = df[t].to_numpy().astype(float)
        for f, cols in fam.items():
            for c in cols:
                x = pd.to_numeric(df[c], errors="coerce").to_numpy()
                a = _auc(y, x)
                if np.isnan(a):
                    continue
                rows.append({"target": t, "family": f, "feature": c,
                             "auc": round(max(a, 1 - a), 4),
                             "coverage": round(float(np.isfinite(x).mean()), 4)})
    r = pd.DataFrame(rows).sort_values("auc", ascending=False)
    hot = r[r.auc >= SINGLE_FEATURE_AUC_TRIPWIRE]
    if verbose:
        print(f"\n  single-feature AUC tripwire (>= {SINGLE_FEATURE_AUC_TRIPWIRE}): "
              f"{len(hot)} of {len(r)} feature-target pairs")
        print("  strongest single features (this is the honest ceiling of any one column):")
        for _, x in r.head(8).iterrows():
            print(f"     {x.target:<8}{x.family:<11}{x.feature:<34}auc={x.auc:.4f}  "
                  f"cov={x.coverage:.2f}")
    return r


def audit(fx: pd.DataFrame | None = None, df: pd.DataFrame | None = None,
          *, verbose: bool = True) -> dict:
    fx = D.load_fixtures() if fx is None else fx
    df = F.build(fx) if df is None else df
    if verbose:
        print("LEAKAGE AUDIT -- randomise the future, rebuild, demand the past is unchanged")
    p = perturbation_test(fx, verbose=verbose)
    t = tripwire_test(df, verbose=verbose)
    # A target must never appear among the features.
    fam = F.family_columns(df)
    feat_cols = {c for fs in fam.values() for c in fs}
    overlap = sorted(feat_cols & set(D.TARGETS) | (feat_cols & {"total_goals", "goals_bucket",
                                                               "home_goals", "away_goals"}))
    clean = bool(p["cells_changed"].sum() == 0) and not overlap
    verdict = "YES" if clean else "NO"
    if verbose:
        print(f"\n  target columns leaking into features: {overlap or 'none'}")
        print(f"\n  DATASET_LEAKAGE_SAFE={verdict}")
    return {"perturbation": p, "tripwire": t, "target_overlap": overlap, "safe": clean,
            "calc_version": CALC_VERSION}


def main() -> int:
    fx = D.load_fixtures()
    df = F.build(fx)
    r = audit(fx, df, verbose=True)
    out = D.out_dir()
    r["perturbation"].to_csv(out / "leakage_perturbation.csv", index=False)
    r["tripwire"].to_csv(out / "leakage_single_feature_auc.csv", index=False)
    print(f"\n[leakage] wrote leakage_perturbation.csv, leakage_single_feature_auc.csv")
    return 0 if r["safe"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

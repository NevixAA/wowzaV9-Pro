"""
Feature contracts and drift monitoring.
=======================================
Prompt 1 sections 5 and 6. A model is only valid on data that resembles what it was fitted on.
v9 has no way to notice when that stops being true — `feature_health.json` records whether
columns are *present*, not whether their distributions still match training. So a feature can
silently change meaning (a provider changes units, an enrichment starts failing and gets
median-imputed, a league's data goes missing) and the model keeps scoring with confidence.

Two measures, because they fail differently:

  PSI  Population Stability Index. Bins the TRAINING distribution and compares serving
       population shares. Sensitive to a shift in the middle of the distribution — the kind
       caused by an upstream unit change or a broken enrichment. Industry rule of thumb:
       < 0.10 stable, 0.10-0.25 moderate, > 0.25 significant.
  KS   Kolmogorov-Smirnov. Maximum gap between the two cumulative distributions. Sensitive to
       a change in SHAPE that PSI's binning can hide.

Both are reported; neither is trusted alone.

Out-of-range percentage is tracked separately because it means something different again: a
serving value outside the training [min, max] is an extrapolation, and a tree ensemble
extrapolating produces confident nonsense rather than an obvious error.

Nothing here decides anything. It produces flags, and src/betting/gates.py decides what a flag
means for permission to bet.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from src.features.imputers import ImputerManifest

# Conventional PSI thresholds. Named so a future change is visible in a diff rather than
# buried in a comparison.
PSI_STABLE = 0.10
PSI_SIGNIFICANT = 0.25
KS_SIGNIFICANT = 0.15
OUT_OF_RANGE_SIGNIFICANT = 0.05      # 5% of serving rows outside the training range


def psi(train_ref: np.ndarray, serve: np.ndarray, *, bins: int = 10) -> float:
    """Population Stability Index against a TRAINING reference.

    Bin edges come from the training quantiles, not from the serving data — using serving
    quantiles would move the ruler along with the thing being measured. Empty bins get a small
    floor so the log is finite.
    """
    t = np.asarray(train_ref, dtype=float)
    s = np.asarray(serve, dtype=float)
    t, s = t[~np.isnan(t)], s[~np.isnan(s)]
    if len(t) < 2 or len(s) < 1:
        return float("nan")

    edges = np.unique(np.quantile(t, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0                       # effectively constant in training; nothing to measure
    edges[0], edges[-1] = -np.inf, np.inf

    t_share = np.histogram(t, bins=edges)[0] / len(t)
    s_share = np.histogram(s, bins=edges)[0] / len(s)
    floor = 1e-6
    t_share = np.clip(t_share, floor, None)
    s_share = np.clip(s_share, floor, None)
    return float(np.sum((s_share - t_share) * np.log(s_share / t_share)))


def ks_statistic(train_ref: np.ndarray, serve: np.ndarray) -> float:
    """Two-sample KS: the largest vertical gap between the two empirical CDFs."""
    t = np.sort(np.asarray(train_ref, dtype=float))
    s = np.sort(np.asarray(serve, dtype=float))
    t, s = t[~np.isnan(t)], s[~np.isnan(s)]
    if len(t) == 0 or len(s) == 0:
        return float("nan")
    grid = np.concatenate([t, s])
    ct = np.searchsorted(t, grid, side="right") / len(t)
    cs = np.searchsorted(s, grid, side="right") / len(s)
    return float(np.max(np.abs(ct - cs)))


@dataclass
class FeatureDrift:
    feature: str
    n_serve: int
    train_mean: float | None = None
    serve_mean: float | None = None
    train_std: float | None = None
    serve_std: float | None = None
    train_missing_rate: float | None = None
    serve_missing_rate: float | None = None
    psi: float | None = None
    ks: float | None = None
    out_of_range_pct: float | None = None
    degenerate_at_serve: bool = False
    flags: list[str] = field(default_factory=list)
    severity: str = "OK"          # OK | MODERATE | SIGNIFICANT | CRITICAL

    def as_row(self) -> dict:
        d = asdict(self)
        d["flags"] = "|".join(self.flags)
        return d


def _severity(flags: list[str], required: bool) -> str:
    if not flags:
        return "OK"
    hard = {"PSI_SIGNIFICANT", "KS_SIGNIFICANT", "OUT_OF_RANGE", "DEGENERATE_AT_SERVE",
            "MISSING_AT_SERVE"}
    if required and (hard & set(flags)):
        return "CRITICAL"        # a required feature has genuinely changed -> block, not warn
    if hard & set(flags):
        return "SIGNIFICANT"
    return "MODERATE"


def feature_drift(
    serve_df: pd.DataFrame,
    manifest: ImputerManifest,
    *,
    train_reference: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compare serving data against the training manifest, feature by feature.

    PSI and KS need the training SAMPLE, not just its summary statistics, so pass
    `train_reference` when it is available. Without it the mean/std/missing/out-of-range checks
    still run from the manifest alone — degraded but not useless, which matters because the
    manifest is what gets shipped with a model.
    """
    rows: list[FeatureDrift] = []
    for name, st in manifest.features.items():
        d = FeatureDrift(feature=name, n_serve=len(serve_df),
                         train_mean=st.mean, train_std=st.std,
                         train_missing_rate=st.missing_rate)

        if name not in serve_df.columns:
            d.flags.append("MISSING_AT_SERVE")
            d.serve_missing_rate = 1.0
            d.severity = _severity(d.flags, st.required)
            rows.append(d)
            continue

        s = pd.to_numeric(serve_df[name], errors="coerce")
        d.n_serve = int(len(s))
        d.serve_missing_rate = round(float(s.isna().mean()), 6)
        valid = s.dropna()
        if valid.empty:
            d.flags.append("MISSING_AT_SERVE")
            d.severity = _severity(d.flags, st.required)
            rows.append(d)
            continue

        d.serve_mean = round(float(valid.mean()), 6)
        d.serve_std = round(float(valid.std(ddof=0)), 6)
        d.degenerate_at_serve = bool(d.serve_std == 0.0)
        if d.degenerate_at_serve and not st.degenerate:
            # Constant at serving but variable in training: the feature has stopped arriving
            # even though the column is present. This is the failure `feature_health.json`
            # cannot see.
            d.flags.append("DEGENERATE_AT_SERVE")

        if st.min is not None and st.max is not None:
            oor = float(((valid < st.min) | (valid > st.max)).mean())
            d.out_of_range_pct = round(oor, 6)
            if oor > OUT_OF_RANGE_SIGNIFICANT:
                d.flags.append("OUT_OF_RANGE")

        if (st.missing_rate is not None
                and d.serve_missing_rate > max(0.20, st.missing_rate + 0.20)):
            d.flags.append("MISSING_RATE_JUMP")

        if train_reference is not None and name in train_reference.columns:
            t = pd.to_numeric(train_reference[name], errors="coerce").dropna().to_numpy()
            d.psi = round(psi(t, valid.to_numpy()), 6)
            d.ks = round(ks_statistic(t, valid.to_numpy()), 6)
            if not np.isnan(d.psi):
                if d.psi > PSI_SIGNIFICANT:
                    d.flags.append("PSI_SIGNIFICANT")
                elif d.psi > PSI_STABLE:
                    d.flags.append("PSI_MODERATE")
            if not np.isnan(d.ks) and d.ks > KS_SIGNIFICANT:
                d.flags.append("KS_SIGNIFICANT")

        d.severity = _severity(d.flags, st.required)
        rows.append(d)

    out = pd.DataFrame([r.as_row() for r in rows])
    order = {"CRITICAL": 0, "SIGNIFICANT": 1, "MODERATE": 2, "OK": 3}
    return (out.assign(_o=out["severity"].map(order))
               .sort_values(["_o", "feature"]).drop(columns="_o").reset_index(drop=True))


def prediction_drift(
    train_probs, serve_probs, *, bins: int = 10
) -> dict:
    """Has the OUTPUT distribution moved, independently of the inputs?

    Worth checking separately: inputs can drift within tolerance while predictions pile up at
    one end, and inputs can look fine while a code change alters the output. This is the check
    that would have caught v9's HT model sitting inert in a 0.68-0.72 band against thresholds of
    >= 0.75 and <= 0.30 — every feature healthy, and the model incapable of firing.
    """
    t = np.asarray(train_probs, dtype=float)
    s = np.asarray(serve_probs, dtype=float)
    t, s = t[~np.isnan(t)], s[~np.isnan(s)]
    out = {"n_train": int(len(t)), "n_serve": int(len(s))}
    if len(t) == 0 or len(s) == 0:
        out["flags"] = "NO_DATA"
        return out
    out.update({
        "train_mean": round(float(t.mean()), 6), "serve_mean": round(float(s.mean()), 6),
        "train_std": round(float(t.std()), 6), "serve_std": round(float(s.std()), 6),
        "psi": round(psi(t, s, bins=bins), 6), "ks": round(ks_statistic(t, s), 6),
        "serve_min": round(float(s.min()), 6), "serve_max": round(float(s.max()), 6),
    })
    flags = []
    if out["psi"] > PSI_SIGNIFICANT:
        flags.append("PREDICTION_PSI_SIGNIFICANT")
    if out["ks"] > KS_SIGNIFICANT:
        flags.append("PREDICTION_KS_SIGNIFICANT")
    if out["serve_std"] == 0.0:
        flags.append("PREDICTIONS_CONSTANT")
    # A range so narrow it cannot cross any plausible threshold: the model is inert.
    if (out["serve_max"] - out["serve_min"]) < 0.10:
        flags.append("PREDICTION_RANGE_COLLAPSED")
    out["flags"] = "|".join(flags)
    return out


def health_summary(drift_df: pd.DataFrame) -> dict:
    """One-line verdict for output/system_registry.json."""
    if drift_df.empty:
        return {"status": "NO_DATA", "critical": 0, "significant": 0, "moderate": 0}
    counts = drift_df["severity"].value_counts().to_dict()
    crit = int(counts.get("CRITICAL", 0))
    sig = int(counts.get("SIGNIFICANT", 0))
    return {
        "status": "CRITICAL" if crit else "SIGNIFICANT" if sig else
                  "MODERATE" if counts.get("MODERATE") else "OK",
        "critical": crit, "significant": sig,
        "moderate": int(counts.get("MODERATE", 0)), "ok": int(counts.get("OK", 0)),
        "worst_features": drift_df.loc[drift_df["severity"].isin(["CRITICAL", "SIGNIFICANT"]),
                                       "feature"].head(10).tolist(),
    }

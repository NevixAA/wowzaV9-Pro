"""
Training-time imputers, persisted with the model.
=================================================
Prompt 1 section 4: "Never derive production imputation values from the current prediction
batch. Store training median/mean/std/missing rate/min/max/quantiles with the model and use
those values at inference."

Why this is not academic. v9's own invariants record what batch-time imputation cost:

  * invariant 8 — a fixture with no rolling-form history was median-imputed, so it produced a
    CONFIDENT-LOOKING WRONG edge rather than a cautious one. York City, with no history at all,
    showed the second-strongest EFL edge on the board at 4.4%, built on nothing.
  * invariant 9 — 29 columns were seeded with hardcoded stand-ins (api_implied_btts=0.5,
    h2h_avg_goals=2.6, coach_tenure=180) that survived into predictions.csv whenever
    enrichment failed, which was always.

Two distinct failures, and they need different answers:

  IMPUTE a value that is missing for a benign reason (a genuinely new feature, an occasional
  gap) — using the TRAINING distribution, so the model sees the same distribution it learned
  on, and the imputed value cannot drift with today's batch.

  REFUSE to score a row whose CRITICAL features are missing. Imputation makes such a row
  look ordinary; it is not ordinary, it is unknown. `required` features are declared, and a row
  missing one is flagged FEATURE_DEGRADED and can never become LIVE.

Batch-derived imputation is worse than a fixed constant, because it is unstable: the same
fixture scores differently depending on which other fixtures happen to be in the batch.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class FeatureStats:
    """The training distribution of one feature. Everything Prompt 1 section 4 asks for."""
    name: str
    dtype: str
    count: int
    missing_rate: float
    mean: float | None = None
    std: float | None = None
    median: float | None = None
    min: float | None = None
    max: float | None = None
    q01: float | None = None
    q05: float | None = None
    q25: float | None = None
    q75: float | None = None
    q95: float | None = None
    q99: float | None = None
    required: bool = False          # a row missing this cannot be scored LIVE
    degenerate: bool = False        # zero variance in training -> carries no information


@dataclass
class ImputerManifest:
    """Fitted on the TRAIN block only, saved beside the model, applied unchanged at inference."""
    fitted_on_rows: int = 0
    fitted_on_dates: tuple[str, str] = ("", "")
    features: dict[str, FeatureStats] = field(default_factory=dict)

    # ── persistence ──────────────────────────────────────────────────────────
    def to_json(self, path: Path) -> None:
        payload = {
            "fitted_on_rows": self.fitted_on_rows,
            "fitted_on_dates": list(self.fitted_on_dates),
            "features": {k: asdict(v) for k, v in self.features.items()},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def from_json(cls, path: Path) -> "ImputerManifest":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        m = cls(fitted_on_rows=d.get("fitted_on_rows", 0),
                fitted_on_dates=tuple(d.get("fitted_on_dates", ["", ""])))
        for k, v in (d.get("features") or {}).items():
            m.features[k] = FeatureStats(**v)
        return m


def fit_imputer(
    train_df: pd.DataFrame,
    feature_cols: list[str],
    *,
    required: list[str] | None = None,
    date_col: str = "match_date",
) -> ImputerManifest:
    """Fit on the TRAIN block and nothing else.

    Passing calibration, meta-train or holdout rows here is leakage: the imputed values would
    carry information from data the model is supposed to be evaluated on.
    """
    req = set(required or [])
    m = ImputerManifest(fitted_on_rows=len(train_df))
    if date_col in train_df.columns and len(train_df):
        d = pd.to_datetime(train_df[date_col], errors="coerce")
        m.fitted_on_dates = (str(d.min())[:10], str(d.max())[:10])

    for c in feature_cols:
        if c not in train_df.columns:
            # Declared but absent in training: record it so serving can tell "never existed"
            # apart from "missing today".
            m.features[c] = FeatureStats(name=c, dtype="absent", count=0, missing_rate=1.0,
                                         required=c in req)
            continue
        s = pd.to_numeric(train_df[c], errors="coerce")
        n_valid = int(s.notna().sum())
        st = FeatureStats(
            name=c, dtype=str(train_df[c].dtype), count=n_valid,
            missing_rate=round(1.0 - n_valid / max(1, len(s)), 6),
            required=c in req,
        )
        if n_valid:
            st.mean, st.std = float(s.mean()), float(s.std(ddof=0))
            st.median, st.min, st.max = float(s.median()), float(s.min()), float(s.max())
            for q, attr in ((0.01, "q01"), (0.05, "q05"), (0.25, "q25"),
                            (0.75, "q75"), (0.95, "q95"), (0.99, "q99")):
                setattr(st, attr, float(s.quantile(q)))
            st.degenerate = bool(st.std is not None and st.std == 0.0)
        m.features[c] = st
    return m


@dataclass
class ImputeReport:
    """What was filled, and which rows are not safe to score."""
    rows: int
    imputed_counts: dict[str, int] = field(default_factory=dict)
    degraded_rows: int = 0
    missing_required: dict[str, int] = field(default_factory=dict)
    unknown_features: list[str] = field(default_factory=list)


def apply_imputer(
    df: pd.DataFrame,
    manifest: ImputerManifest,
    *,
    clip_to_training_range: bool = True,
) -> tuple[pd.DataFrame, pd.Series, ImputeReport]:
    """Fill from the TRAINING distribution and flag rows that should not be scored.

    Returns (filled_frame, degraded_mask, report). `degraded_mask` is True for any row missing
    a REQUIRED feature — those rows are still returned, because Prompt 2 forbids dropping
    observations, but they carry the flag and must never become LIVE.

    Values are clipped to the training [min, max] by default. A serving value far outside the
    range the model was fitted on is an extrapolation, and extrapolating a tree ensemble
    produces confident nonsense.
    """
    out = df.copy()
    rep = ImputeReport(rows=len(out))
    degraded = pd.Series(False, index=out.index)

    for name, st in manifest.features.items():
        if name not in out.columns:
            rep.unknown_features.append(name)
            # Declared feature entirely absent at serving time. Fill so the matrix is complete,
            # but a REQUIRED one degrades every row.
            out[name] = st.median if st.median is not None else np.nan
            rep.imputed_counts[name] = len(out)
            if st.required:
                degraded |= True
                rep.missing_required[name] = len(out)
            continue

        s = pd.to_numeric(out[name], errors="coerce")
        miss = s.isna()
        n_miss = int(miss.sum())
        if st.required and n_miss:
            degraded |= miss
            rep.missing_required[name] = n_miss
        if n_miss and st.median is not None:
            s = s.fillna(st.median)          # TRAINING median, never the batch median
            rep.imputed_counts[name] = n_miss
        if clip_to_training_range and st.min is not None and st.max is not None:
            s = s.clip(lower=st.min, upper=st.max)
        out[name] = s

    rep.degraded_rows = int(degraded.sum())
    return out, degraded, rep


def batch_median_would_differ(
    serve_df: pd.DataFrame, manifest: ImputerManifest, *, tol: float = 1e-9
) -> pd.DataFrame:
    """Diagnostic: how far the SERVING batch median sits from the TRAINING median.

    Makes the cost of batch-time imputation visible instead of theoretical. A large gap means
    rows imputed from the batch were being handed values the model never saw in training — and
    that the same fixture would score differently in a different batch.
    """
    rows = []
    for name, st in manifest.features.items():
        if name not in serve_df.columns or st.median is None:
            continue
        s = pd.to_numeric(serve_df[name], errors="coerce")
        if s.notna().sum() == 0:
            continue
        bm = float(s.median())
        if abs(bm - st.median) > tol:
            span = (st.max - st.min) if (st.max is not None and st.min is not None) else None
            rows.append({"feature": name, "training_median": st.median, "batch_median": bm,
                         "abs_diff": abs(bm - st.median),
                         "diff_vs_training_range": (abs(bm - st.median) / span)
                         if span else None})
    return (pd.DataFrame(rows).sort_values("abs_diff", ascending=False).reset_index(drop=True)
            if rows else pd.DataFrame())

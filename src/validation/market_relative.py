"""
Market-relative validation: does the model add anything the market does not already have?
=========================================================================================
Prompt 1 section 2 and Prompt 3 section 14. This is the central question of the whole project,
and standalone AUC does not answer it — a model can score 0.60 AUC purely by rediscovering
what the odds already say.

Three competing forecasts on the same rows:

    A  MODEL ONLY      p_model
    B  MARKET ONLY     p_market            (de-vigged consensus — the baseline to beat)
    C  MARKET + MODEL  blend(p_market, p_model, w)

The only result that matters is whether C beats B. If it does not, the model contains no
information beyond the price, whatever its AUC.

Metrics are LogLoss and Brier — proper scoring rules, so they reward calibration and cannot be
gamed by ranking alone. AUC is reported as secondary because it is rank-only and blind to
calibration: a model can have identical AUC to the market and still be useless (or harmful) to
bet with.

Reported per segment with N attached, and labelled INSUFFICIENT_SAMPLE / EARLY_SIGNAL /
RESEARCH_ONLY / VALIDATED per Prompt 3 section 22. A tiny league sample is an observation, not
a discovery.

v11's own early evidence, which this module is built to extend rather than contradict:
market Brier/LogLoss about .2292/.6503 against market+Wowza about .2295/.6514 at n=83 — i.e.
the model was very slightly WORSE. That result is not to be hidden (section 31).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

EPS = 1e-12

# Sample-size labels. Deliberately conservative: nothing is "validated" on a few hundred rows.
SAMPLE_BANDS = ((0, 50, "INSUFFICIENT_SAMPLE"),
                (50, 250, "EARLY_SIGNAL"),
                (250, 1000, "RESEARCH_ONLY"),
                (1000, 10 ** 12, "VALIDATED"))


def sample_label(n: int) -> str:
    for lo, hi, name in SAMPLE_BANDS:
        if lo <= n < hi:
            return name
    return "INSUFFICIENT_SAMPLE"


def log_loss(y, p) -> float:
    y = np.asarray(y, dtype=float)
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y, p) -> float:
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    return float(np.mean((p - y) ** 2))


def auc(y, p) -> float | None:
    """Rank AUC via the Mann-Whitney identity. None when one class is absent."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order), dtype=float)
    ranks[order] = np.arange(1, len(order) + 1)
    # average ranks over ties so a flat model scores 0.5 rather than something arbitrary
    vals = np.concatenate([pos, neg])
    df = pd.DataFrame({"v": vals, "r": ranks})
    ranks = df.groupby("v")["r"].transform("mean").to_numpy()
    r_pos = ranks[:len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def ece(y, p, bins: int = 10) -> float:
    """Expected calibration error — mean |predicted - observed| weighted by bin population."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    if len(y) == 0:
        return float("nan")
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    total = 0.0
    for b in range(bins):
        m = idx == b
        if m.sum():
            total += (m.sum() / len(y)) * abs(p[m].mean() - y[m].mean())
    return float(total)


@dataclass
class Comparison:
    segment: str
    n: int
    n_pos: int
    sample_label: str
    # B — market only
    market_logloss: float | None = None
    market_brier: float | None = None
    market_auc: float | None = None
    market_ece: float | None = None
    # A — model only
    model_logloss: float | None = None
    model_brier: float | None = None
    model_auc: float | None = None
    model_ece: float | None = None
    # C — market + model
    blend_logloss: float | None = None
    blend_brier: float | None = None
    blend_auc: float | None = None
    blend_ece: float | None = None
    blend_weight: float | None = None
    # C vs B — the answer. Positive = the model ADDS information.
    logloss_improvement: float | None = None
    brier_improvement: float | None = None
    verdict: str = "NO_EVIDENCE"

    def as_row(self) -> dict:
        return asdict(self)


def compare(
    y,
    p_market,
    p_model,
    *,
    segment: str = "overall",
    weight: float = 0.20,
) -> Comparison:
    """Score A, B and C on one set of rows.

    `weight` is the weight on the MODEL in the blend. It must come from somewhere defensible —
    a chronologically-earlier block, never fitted on these rows, or Prompt 3 section 13's
    candidate sweep evaluated out of sample. Optimising it here and reporting the result would
    be the same in-sample error this whole module exists to remove.
    """
    y = np.asarray(y, dtype=float)
    m = np.asarray(p_market, dtype=float)
    o = np.asarray(p_model, dtype=float)
    keep = ~(np.isnan(y) | np.isnan(m) | np.isnan(o))
    y, m, o = y[keep], m[keep], o[keep]

    n = len(y)
    c = Comparison(segment=segment, n=n, n_pos=int(y.sum()), sample_label=sample_label(n),
                   blend_weight=weight)
    if n == 0:
        return c

    b = weight * o + (1.0 - weight) * m

    c.market_logloss, c.market_brier = log_loss(y, m), brier(y, m)
    c.market_auc, c.market_ece = auc(y, m), ece(y, m)
    c.model_logloss, c.model_brier = log_loss(y, o), brier(y, o)
    c.model_auc, c.model_ece = auc(y, o), ece(y, o)
    c.blend_logloss, c.blend_brier = log_loss(y, b), brier(y, b)
    c.blend_auc, c.blend_ece = auc(y, b), ece(y, b)

    # Positive = blend is BETTER (lower loss than market alone).
    c.logloss_improvement = round(c.market_logloss - c.blend_logloss, 8)
    c.brier_improvement = round(c.market_brier - c.blend_brier, 8)

    both_better = c.logloss_improvement > 0 and c.brier_improvement > 0
    both_worse = c.logloss_improvement < 0 and c.brier_improvement < 0
    if c.sample_label == "INSUFFICIENT_SAMPLE":
        c.verdict = "INSUFFICIENT_SAMPLE"
    elif both_better:
        c.verdict = "MODEL_ADDS_INFORMATION" if c.sample_label == "VALIDATED" \
            else "MODEL_ADDS_INFORMATION_UNCONFIRMED"
    elif both_worse:
        c.verdict = "MARKET_DOMINATES"
    else:
        c.verdict = "MIXED"
    return c


def compare_by(
    df: pd.DataFrame,
    *,
    y_col: str,
    market_col: str,
    model_col: str,
    by: str | list[str] | None = None,
    weight: float = 0.20,
) -> pd.DataFrame:
    """Overall plus per-segment comparisons in one frame.

    Segmentation is where multiple testing creeps in: league x market x side x odds band x tier
    is hundreds of hypotheses, and some will look good by chance. Feed the resulting p-values
    through src/validation/multiple_testing.py before believing any of them.
    """
    rows = [compare(df[y_col], df[market_col], df[model_col],
                    segment="overall", weight=weight).as_row()]
    if by:
        keys = [by] if isinstance(by, str) else list(by)
        for vals, g in df.groupby(keys, dropna=False):
            label = "|".join(str(v) for v in (vals if isinstance(vals, tuple) else (vals,)))
            rows.append(compare(g[y_col], g[market_col], g[model_col],
                                segment=label, weight=weight).as_row())
    out = pd.DataFrame(rows)
    return out.sort_values("n", ascending=False).reset_index(drop=True)

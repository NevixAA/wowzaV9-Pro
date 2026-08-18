"""
Multiple-testing control.
=========================
Prompt 1 section 17. Threshold and segment search runs over leagues x markets x sides x odds
bands x tiers — easily hundreds of hypotheses. At the usual 5% level, testing 200 segments
yields about 10 "significant" findings from pure noise, and those are exactly the segments a
backtest will happily report as an edge.

Benjamini-Hochberg controls the FALSE DISCOVERY RATE: of everything declared significant, the
expected share of false positives is at most q. That is the right target here — the goal is not
to never be wrong once (Bonferroni, which would reject almost everything at this scale) but to
keep the proportion of junk among the accepted findings low.

Every result keeps its raw p, its adjusted q, the number of hypotheses it was tested among, and
whether it survived. Persisting the hypothesis count is what makes the correction auditable
later: the same p-value means very different things among 5 tests and among 500.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def benjamini_hochberg(p_values, q: float = 0.05) -> pd.DataFrame:
    """BH step-up procedure.

    Returns one row per input in the ORIGINAL order, with:
        p_raw, p_adjusted (q-value), rank, n_hypotheses, significant, threshold
    NaN p-values are carried through as not-significant rather than dropped, so the output
    always aligns with the input.
    """
    p = np.asarray(p_values, dtype=float)
    n_all = len(p)
    valid = ~np.isnan(p)
    m = int(valid.sum())

    out = pd.DataFrame({
        "p_raw": p,
        "p_adjusted": np.full(n_all, np.nan),
        "rank": np.full(n_all, np.nan),
        "n_hypotheses": m,
        "significant": np.zeros(n_all, dtype=bool),
        "bh_threshold": np.nan,
        "q_target": q,
    })
    if m == 0:
        return out

    idx = np.flatnonzero(valid)
    order = idx[np.argsort(p[idx], kind="mergesort")]
    ranks = np.arange(1, m + 1)

    # Step-up adjusted p: enforce monotonicity from the largest p downwards, so a small p can
    # never end up with a larger q than a bigger p.
    adj_sorted = np.minimum.accumulate((p[order] * m / ranks)[::-1])[::-1]
    adj_sorted = np.clip(adj_sorted, 0.0, 1.0)

    out.loc[order, "p_adjusted"] = adj_sorted
    out.loc[order, "rank"] = ranks

    # Largest k with p_(k) <= k/m * q; everything up to that rank is significant.
    below = np.flatnonzero(p[order] <= ranks / m * q)
    if len(below):
        k = below[-1] + 1
        out.loc[order[:k], "significant"] = True
        out["bh_threshold"] = float(k / m * q)
    else:
        out["bh_threshold"] = float(1 / m * q)
    return out


def bonferroni(p_values, alpha: float = 0.05) -> pd.DataFrame:
    """Family-wise control, for comparison. Much stricter than BH; at hundreds of segments it
    rejects nearly everything, which is why BH is the primary method here."""
    p = np.asarray(p_values, dtype=float)
    m = int((~np.isnan(p)).sum()) or 1
    return pd.DataFrame({
        "p_raw": p,
        "p_adjusted": np.clip(p * m, 0.0, 1.0),
        "n_hypotheses": m,
        "significant": np.nan_to_num(p, nan=1.0) <= alpha / m,
        "alpha_target": alpha,
    })


def paired_bootstrap_p(
    loss_a,
    loss_b,
    *,
    n_boot: int = 10_000,
    block: int = 1,
    seed: int = 7,
) -> tuple[float, float, tuple[float, float]]:
    """Two-sided p for "mean(loss_a) != mean(loss_b)" on PAIRED per-row losses.

    Paired because both forecasts score the same fixtures; comparing unpaired means throws
    away the pairing and inflates the variance.

    `block` > 1 draws contiguous blocks instead of single rows, which preserves short-range
    dependence — fixtures on the same matchday share weather, referee assignment and news, so
    row-independent resampling understates the true standard error.

    Returns (p_value, observed mean difference b - a, 90% CI of the difference).
    Positive difference = loss_b is HIGHER = a is better.
    """
    a = np.asarray(loss_a, dtype=float)
    b = np.asarray(loss_b, dtype=float)
    keep = ~(np.isnan(a) | np.isnan(b))
    a, b = a[keep], b[keep]
    n = len(a)
    if n < 2:
        return float("nan"), float("nan"), (float("nan"), float("nan"))

    d = b - a
    observed = float(d.mean())
    rng = np.random.default_rng(seed)
    block = max(1, int(block))
    n_blocks = int(np.ceil(n / block))

    means = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        starts = rng.integers(0, n, size=n_blocks)
        take = np.concatenate([np.arange(s, s + block) % n for s in starts])[:n]
        means[i] = d[take].mean()

    # Centre on zero to get the null distribution of the mean difference.
    centred = means - means.mean()
    p = float((np.abs(centred) >= abs(observed)).mean())
    lo, hi = np.percentile(means, [5.0, 95.0])
    return p, observed, (float(lo), float(hi))

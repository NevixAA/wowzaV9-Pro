"""Evaluation harness: walk-forward splits, nested shrinkage bars, multiple testing, CLV / line-move tests.

PLUMBING AND STATISTICS ONLY. Nothing here reads a file. Owner rule: these functions are run on
synthetic data (tests/test_props_matchup.py) until the readiness gate passes and the owner approves
the first real run. src.props_matchup.__main__ exposes no fit / backtest command.

  walk_forward_blocks     out-of-sample folds by MATCHDAY block: train = blocks strictly before the
                          test block (minus an embargo), never after
  nested_shrinkage        empirical-Bayes normal-normal down a hierarchy (market -> league -> role ->
                          player): a cell with few matches stays near its parent
  cell_bars               the bar per cell from the shrunk posterior and an OWNER confidence level
  bh_qvalues / by_qvalues / holm_adjust   multiple-testing control across thousands of cells
  clv_log, line_move_test, residual_test  "does the bookmaker already price the absence?"
  min_n_for_mean          minimum sample for a mean-shift test, with a design effect for clustering
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

HIERARCHY = ("market", "league", "role", "player_id")


# ── walk-forward by matchday blocks ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Fold:
    test_block: object
    train_idx: np.ndarray
    test_idx: np.ndarray


def walk_forward_blocks(block: pd.Series, *, min_train_blocks: int, embargo_blocks: int = 0) -> list[Fold]:
    """Folds over ordered blocks (a matchday date, or an ISO week). Test = one block; train = every
    block at least `embargo_blocks` + 1 positions earlier. The first `min_train_blocks` blocks are
    never tested. Blocks are sorted by value, so pass sortable labels (dates / 'YYYY-Www')."""
    if min_train_blocks < 1:
        raise ValueError("min_train_blocks must be >= 1")
    b = pd.Series(block).reset_index(drop=True)
    if b.isna().any():
        raise ValueError("a row without a block cannot be placed in time")
    order = sorted(b.unique())
    pos = {v: i for i, v in enumerate(order)}
    bi = b.map(pos).to_numpy()
    folds = []
    for k in range(min_train_blocks, len(order)):
        train = np.flatnonzero(bi <= k - 1 - embargo_blocks)
        if len(train) == 0:
            continue
        folds.append(Fold(order[k], train, np.flatnonzero(bi == k)))
    return folds


# ── nested shrinkage ─────────────────────────────────────────────────────────────────────────────
def _dl_tau2(est: np.ndarray, se2: np.ndarray) -> float:
    """DerSimonian-Laird between-cell variance around the inverse-variance mean (0 if < 2 cells)."""
    ok = np.isfinite(est) & np.isfinite(se2) & (se2 > 0)
    est, se2 = est[ok], se2[ok]
    if len(est) < 2:
        return 0.0
    w = 1 / se2
    mu = (w * est).sum() / w.sum()
    q = (w * (est - mu) ** 2).sum()
    denom = w.sum() - (w ** 2).sum() / w.sum()
    return float(max(0.0, (q - (len(est) - 1)) / denom)) if denom > 0 else 0.0


def nested_shrinkage(df: pd.DataFrame, value: str, levels=HIERARCHY, *, min_n: int,
                     sd_floor: float | None = None) -> pd.DataFrame:
    """Per-node posterior of the mean of `value` at every level of `levels`.

    Root = the pooled mean of everything. At each level a child's raw mean (se^2 = s^2 / n, with s
    the pooled within-level sd floored at `sd_floor` when given) is shrunk toward its PARENT'S
    posterior with B = se^2 / (se^2 + tau^2), tau^2 by DerSimonian-Laird across all nodes of that
    level with n >= min_n. Nodes below min_n take B = 1 (their parent's posterior): a 3-match player
    gets his role's number. Returns one row per node: level, key columns, n, raw_mean, se, B,
    posterior_mean, posterior_sd."""
    d = df[list(levels) + [value]].copy()
    d[value] = pd.to_numeric(d[value], errors="coerce")
    d = d.dropna(subset=[value])
    if d.empty:
        return pd.DataFrame()
    x = d[value].to_numpy(float)
    root_mean, root_sd = float(x.mean()), float(x.std(ddof=1)) if len(x) > 1 else float("nan")
    out = [{"level": "root", "n": len(x), "raw_mean": root_mean, "se": root_sd / math.sqrt(len(x)),
            "B": 0.0, "posterior_mean": root_mean, "posterior_sd": root_sd / math.sqrt(len(x))}]
    parent_map = {(): (root_mean, root_sd / math.sqrt(len(x)))}
    for depth in range(1, len(levels) + 1):
        keys = list(levels[:depth])
        g = d.groupby(keys, dropna=False)[value].agg(["count", "mean", "var"]).reset_index()
        # pooled within-node variance at this level (nodes with >= 2 rows)
        vv = g[g["count"] >= 2]
        pooled = float(((vv["count"] - 1) * vv["var"]).sum() / max(1, (vv["count"] - 1).sum())) \
            if len(vv) else root_sd ** 2
        sd = math.sqrt(pooled) if pooled > 0 else root_sd
        if sd_floor is not None:
            sd = max(sd, sd_floor)
        g["se2"] = sd ** 2 / g["count"]
        test = g["count"] >= min_n
        tau2 = _dl_tau2(g.loc[test, "mean"].to_numpy(float), g.loc[test, "se2"].to_numpy(float))
        level_map = {}
        for r in g.itertuples(index=False):
            k = tuple(getattr(r, c) for c in keys)
            pm, psd = parent_map[k[:-1]]
            if r.count < min_n or tau2 == 0.0:
                B = 1.0
            else:
                B = r.se2 / (r.se2 + tau2)
            post = B * pm + (1 - B) * r.mean
            post_sd = math.sqrt((1 - B) * r.se2 + B ** 2 * psd ** 2) if B < 1 else psd
            level_map[k] = (post, post_sd)
            out.append({"level": levels[depth - 1], **dict(zip(keys, k)), "n": int(r.count),
                        "raw_mean": float(r.mean), "se": math.sqrt(r.se2), "tau": math.sqrt(tau2),
                        "B": float(B), "posterior_mean": float(post), "posterior_sd": float(post_sd)})
        parent_map = level_map
    return pd.DataFrame(out)


def _norm_ppf(p: float) -> float:
    from scipy.stats import norm
    return float(norm.ppf(p))


def _norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


def cell_bars(post: pd.DataFrame, *, confidence: float | None) -> pd.DataFrame:
    """The bar per cell: the smallest predicted edge whose realised edge, after this cell's shrunk
    out-of-sample bias (posterior of realised - predicted edge), is still > 0 with probability
    `confidence`:  bar = max(0, -posterior_mean + z_conf * posterior_sd).

    `confidence` is an OWNER decision. None -> no bar for any cell (bar NaN, permission BLOCKED):
    fail closed, never a typed default."""
    p = post.copy()
    if confidence is None:
        p["bar"] = np.nan
        p["permission"] = "BLOCKED"
        p["p_bias_gt_0"] = np.nan
        return p
    if not 0.5 < confidence < 1:
        raise ValueError("confidence must be in (0.5, 1)")
    z = _norm_ppf(confidence)
    p["bar"] = np.maximum(0.0, -p["posterior_mean"] + z * p["posterior_sd"])
    p["p_bias_gt_0"] = [_norm_sf(-m / s) if s > 0 else np.nan
                        for m, s in zip(p["posterior_mean"], p["posterior_sd"])]
    p["permission"] = "PAPER"
    return p


# ── multiple testing ─────────────────────────────────────────────────────────────────────────────
def _clean_p(p) -> np.ndarray:
    a = np.asarray(p, float)
    if np.any((a[np.isfinite(a)] < 0) | (a[np.isfinite(a)] > 1)):
        raise ValueError("p-values must be in [0, 1]")
    return a


def bh_qvalues(p) -> np.ndarray:
    """Benjamini-Hochberg q-values (NaN p stays NaN and does not count as a test)."""
    a = _clean_p(p)
    q = np.full(len(a), np.nan)
    ok = np.flatnonzero(np.isfinite(a))
    m = len(ok)
    if m == 0:
        return q
    order = ok[np.argsort(a[ok], kind="mergesort")]
    ranked = a[order] * m / np.arange(1, m + 1)
    q[order] = np.minimum(1.0, np.minimum.accumulate(ranked[::-1])[::-1])
    return q


def by_qvalues(p) -> np.ndarray:
    """Benjamini-Yekutieli: BH x sum(1/i), valid under ANY dependence between cells (one player's
    cells share matches, so cells are not independent)."""
    a = _clean_p(p)
    m = int(np.isfinite(a).sum())
    if m == 0:
        return np.full(len(a), np.nan)
    c = float(np.sum(1.0 / np.arange(1, m + 1)))
    return np.minimum(1.0, bh_qvalues(a) * c)


def holm_adjust(p) -> np.ndarray:
    """Holm step-down family-wise adjusted p-values."""
    a = _clean_p(p)
    adj = np.full(len(a), np.nan)
    ok = np.flatnonzero(np.isfinite(a))
    m = len(ok)
    if m == 0:
        return adj
    order = ok[np.argsort(a[ok], kind="mergesort")]
    stepped = np.maximum.accumulate((m - np.arange(m)) * a[order])
    adj[order] = np.minimum(1.0, stepped)
    return adj


# ── CLV and line-move tests ──────────────────────────────────────────────────────────────────────
def clv_log(odds_taken, odds_close) -> np.ndarray:
    """ln(odds_taken / odds_close): > 0 means we beat the close. Missing or <= 1 odds -> NaN."""
    t = pd.to_numeric(pd.Series(odds_taken), errors="coerce").to_numpy(float)
    c = pd.to_numeric(pd.Series(odds_close), errors="coerce").to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(t / c)
    out[~((t > 1) & (c > 1))] = np.nan
    return out


def _ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def _cluster_bootstrap(y, X, cluster, n_boot: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    labels = pd.Series(cluster).astype("category").cat.codes.to_numpy()
    groups = [np.flatnonzero(labels == g) for g in range(labels.max() + 1)]
    draws = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        idx = np.concatenate([groups[i] for i in pick])
        draws.append(_ols(y[idx], X[idx]))
    return np.asarray(draws)


def _design(cols: dict, n: int) -> tuple[np.ndarray, list[str]]:
    names = ["const"] + list(cols)
    X = np.column_stack([np.ones(n)] + [np.asarray(v, float) for v in cols.values()])
    return X, names


def line_move_test(our_shift, market_move, cluster, *, n_boot: int = 2000, seed: int = 0) -> dict:
    """Does the market move WITH our absence-driven probability shift between the pre-news and the
    post-news snapshot?  market_move = p_post - p_pre (de-vigged), our_shift = our p(with absence) -
    p(without). Slope ~1: the market absorbs the news fully; ~0: it ignores it. Cluster bootstrap by
    matchday. Descriptive: a slope < 1 is NOT an edge on its own (the residual test decides)."""
    s = np.asarray(our_shift, float)
    m = np.asarray(market_move, float)
    ok = np.isfinite(s) & np.isfinite(m)
    s, m, cl = s[ok], m[ok], np.asarray(cluster)[ok]
    if len(s) < 3 or len(np.unique(cl)) < 3:
        return {"n": int(len(s)), "status": "TOO_FEW"}
    X, _ = _design({"our_shift": s}, len(s))
    b = _ols(m, X)
    boot = _cluster_bootstrap(m, X, cl, n_boot, seed)[:, 1]
    return {"n": int(len(s)), "clusters": int(len(np.unique(cl))), "slope": float(b[1]),
            "slope_ci90": [float(np.quantile(boot, 0.05)), float(np.quantile(boot, 0.95))]}


def residual_test(y, p_close, our_shift, prior_move, cluster, *, n_boot: int = 2000, seed: int = 0) -> dict:
    """THE test. Outcome residual against the CLOSING de-vigged probability, regressed on our shift
    with the market's own move UP TO THE DECISION as a control:

        y - p_close = a + b * our_shift + c * prior_move + e,   prior_move = p_decision - p_open

    H0: b <= 0 (the closing price already contains everything our absence signal knows).
    One-sided p from the cluster bootstrap (share of draws with b <= 0, matchday clusters).

    Why not control for the move AFTER the decision (p_close - p_decision): it shares p_close with the
    left-hand side, so the market's own closing error enters both sides and biases b upward even when
    the market prices the absence perfectly (shown on synthetic data in the tests). The post-decision
    move is measured by line_move_test and takeable_clv instead."""
    y = np.asarray(y, float)
    pc = np.asarray(p_close, float)
    s = np.asarray(our_shift, float)
    m = np.asarray(prior_move, float)
    ok = np.isfinite(y) & np.isfinite(pc) & np.isfinite(s) & np.isfinite(m)
    y, pc, s, m, cl = y[ok], pc[ok], s[ok], m[ok], np.asarray(cluster)[ok]
    if len(y) < 3 or len(np.unique(cl)) < 3:
        return {"n": int(len(y)), "status": "TOO_FEW"}
    X, names = _design({"our_shift": s, "prior_move": m}, len(y))
    r = y - pc
    b = _ols(r, X)
    boot = _cluster_bootstrap(r, X, cl, n_boot, seed)
    return {"n": int(len(y)), "clusters": int(len(np.unique(cl))),
            "coef": dict(zip(names, map(float, b))),
            "p_one_sided_b_le_0": float(np.mean(boot[:, 1] <= 0)),
            "b_ci90": [float(np.quantile(boot[:, 1], 0.05)), float(np.quantile(boot[:, 1], 0.95))]}


def takeable_clv(odds_taken, odds_close, cluster, *, n_boot: int = 2000, seed: int = 0) -> dict:
    """Mean log-CLV at the price actually takeable (the snapshot price at decision time, same book),
    with a matchday-cluster bootstrap CI. H0: mean CLV <= 0."""
    c = clv_log(odds_taken, odds_close)
    ok = np.isfinite(c)
    c, cl = c[ok], np.asarray(cluster)[ok]
    if len(c) < 3 or len(np.unique(cl)) < 3:
        return {"n": int(len(c)), "status": "TOO_FEW"}
    rng = np.random.default_rng(seed)
    s = pd.DataFrame({"c": c, "g": cl}).groupby("g")["c"].agg(["sum", "count"])
    idx = rng.integers(0, len(s), size=(n_boot, len(s)))
    means = s["sum"].to_numpy()[idx].sum(1) / s["count"].to_numpy()[idx].sum(1)
    return {"n": int(len(c)), "clusters": int(len(s)), "mean_clv_log": float(c.mean()),
            "ci90": [float(np.quantile(means, 0.05)), float(np.quantile(means, 0.95))],
            "p_one_sided_le_0": float(np.mean(means <= 0))}


def min_n_for_mean(sd: float, delta: float, *, alpha: float, power: float,
                   design_effect: float = 1.0) -> int:
    """n to detect a mean shift `delta` (one-sided, level alpha, given power) with per-bet sd `sd`,
    inflated by a clustering design effect (1 + (m - 1) * icc). Inputs are measured, not assumed:
    the spec says where each comes from."""
    if sd <= 0 or delta <= 0:
        raise ValueError("sd and delta must be > 0")
    z = _norm_ppf(1 - alpha) + _norm_ppf(power)
    return int(math.ceil((z * sd / delta) ** 2 * design_effect))

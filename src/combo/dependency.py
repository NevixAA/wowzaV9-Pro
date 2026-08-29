"""
Empirical joint-frequency / dependency matrix (bet-builder brief, Phase 3, section 18).
=======================================================================================

THE ONE NUMBER THIS EXISTS TO PRODUCE

    dependency_ratio = P(A and B) / (P(A) * P(B))

A ratio of 1.0 means independence and multiplication is safe. Anything else means multiplying
marginals is WRONG, and the ratio says by how much and in which direction.

On the full sample the answer is emphatic. P(O2.5) = 0.5034 and P(BTTS) = 0.5316, so independence
predicts 0.2676 -- but the observed joint is 0.4098, a ratio of **1.53**. Pricing that pair by
multiplication understates the true probability by more than half, which is the difference
between a builder that looks like value and one that is.

MEASURED, NOT MODELLED

Every cell is a plain count over settled scorelines from `team_match_stats` (23,604 fixtures,
100% goal coverage, 2023-01-26 to 2026-08-25, 23 leagues). No model, no assumption, no fitted
parameter. That makes this the ground truth any joint model must reproduce before it is trusted,
and it is why the brief asks for it in Phase 3, before any pricing.

WHAT IS DELIBERATELY EXCLUDED

Redundant pairs never appear. A "combination" of O2.5 and O1.5 is just O2.5, and one of BTTS and
BTTS_NO cannot happen at all -- offering either as a two-leg builder would be a category error
rather than a bad price. `events.is_redundant` names the reason for each excluded pair and the
exclusions are reported, not silently dropped.

SEGMENTATION IS BOUNDED BY SAMPLE, NOT BY CURIOSITY

The brief warns against exploding the cell count. Segments are only emitted when they hold at
least `MIN_SEGMENT_N` fixtures, and every row carries `n` and a `sample_status` so a ratio
measured on 40 fixtures cannot be read with the same confidence as one measured on 23,604.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from src.combo import events as ev

CALC_VERSION = "1.0.0"

MIN_SEGMENT_N = 300          # below this a segment is not emitted at all
MIN_CELL_N = 30              # below this a pair within a segment is not emitted


def sample_status(n: int) -> str:
    if n < 100:
        return "INSUFFICIENT"
    if n < 500:
        return "EARLY"
    if n < 2000:
        return "RESEARCH"
    return "VALIDATION_CANDIDATE"


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * np.sqrt(max(p * (1 - p) / n + z * z / (4 * n * n), 0.0))
    return ((c - m) / d, (c + m) / d)


def _phi(a: np.ndarray, b: np.ndarray) -> float:
    """Phi coefficient — Pearson correlation for two binary variables."""
    n11 = float(np.sum(a & b)); n10 = float(np.sum(a & ~b))
    n01 = float(np.sum(~a & b)); n00 = float(np.sum(~a & ~b))
    den = np.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    return float((n11 * n00 - n10 * n01) / den) if den > 0 else float("nan")


def pair_rows(d: pd.DataFrame, *, segment: str, league: str = "ALL",
              model_type: str = "ALL") -> list[dict]:
    """Every legitimate market pair for one segment of settled fixtures."""
    names = [k for k in ev.EVENTS if f"ev_{k}" in d.columns]
    n = len(d)
    rows: list[dict] = []
    for a, b in itertools.combinations(names, 2):
        why = ev.is_redundant(a, b)
        if why:
            continue                                   # not a combination at all
        va = d[f"ev_{a}"].to_numpy(dtype=bool)
        vb = d[f"ev_{b}"].to_numpy(dtype=bool)
        k_joint = int(np.sum(va & vb))
        if n < MIN_CELL_N:
            continue
        p_a, p_b = float(va.mean()), float(vb.mean())
        p_joint = k_joint / n
        indep = p_a * p_b
        lo_f, hi_f = ev.frechet_bounds(p_a, p_b)
        lo, hi = _wilson(k_joint, n)
        rows.append({
            "segment": segment, "league": league, "model_type": model_type,
            "market_a": a, "market_b": b,
            "label_a": ev.EVENTS[a][1], "label_b": ev.EVENTS[b][1],
            "n": n, "k_joint": k_joint,
            "p_a": round(p_a, 6), "p_b": round(p_b, 6),
            "p_joint": round(p_joint, 6),
            "independent_joint": round(indep, 6),
            # The headline. >1 means positively dependent: multiplication UNDERSTATES the joint.
            "dependency_ratio": round(p_joint / indep, 4) if indep > 0 else None,
            "excess_pp": round(100 * (p_joint - indep), 3),
            "phi": round(_phi(va, vb), 4),
            "joint_ci_lo": round(lo, 6), "joint_ci_hi": round(hi, 6),
            # An observed frequency cannot violate Frechet; if it does, `settle` is broken.
            "frechet_lo": round(lo_f, 6), "frechet_hi": round(hi_f, 6),
            "frechet_ok": bool(lo_f - 1e-9 <= p_joint <= hi_f + 1e-9),
            # Is independence a defensible approximation here? Only if the CI covers it.
            "independence_within_ci": bool(lo <= indep <= hi),
            "sample_status": sample_status(n),
            "calc_version": CALC_VERSION,
        })
    return rows


def build(stats: pd.DataFrame, *, by_league: bool = True,
          by_season: bool = True) -> tuple[pd.DataFrame, dict]:
    """The full matrix: overall, then per league and per season where the sample allows."""
    d = ev.settle(stats)
    meta = {
        "fixtures_settled": len(d),
        "dropped_no_scoreline": d.attrs.get("dropped_no_scoreline", 0),
        "coherence_violations": ev.check_coherence(d),
        "date_min": str(pd.to_datetime(d["match_date"], errors="coerce").min())[:10],
        "date_max": str(pd.to_datetime(d["match_date"], errors="coerce").max())[:10],
        "leagues": int(d["league"].nunique()) if "league" in d.columns else 0,
        "calc_version": CALC_VERSION,
        "schema_version": ev.SCHEMA_VERSION,
        "ht_unavailable": ev.HT_EVENTS,
    }
    rows = pair_rows(d, segment="ALL")
    excluded = [(a, b, ev.is_redundant(a, b))
                for a, b in itertools.combinations(list(ev.EVENTS), 2)
                if ev.is_redundant(a, b)]
    meta["pairs_excluded_as_redundant"] = len(excluded)
    meta["excluded_examples"] = [f"{a}+{b}: {w}" for a, b, w in excluded[:8]]

    if by_league and "league" in d.columns:
        for lg, g in d.groupby("league"):
            if len(g) >= MIN_SEGMENT_N:
                rows += pair_rows(g, segment=f"league={lg}", league=str(lg))
    if by_season and "season" in d.columns:
        for sn, g in d.groupby("season"):
            if len(g) >= MIN_SEGMENT_N:
                rows += pair_rows(g, segment=f"season={sn}")
    return pd.DataFrame(rows), meta


def stability(df: pd.DataFrame, *, min_segments: int = 3) -> pd.DataFrame:
    """Which dependencies hold up ACROSS segments (research question Q1).

    A ratio measured once is a number; a ratio that reproduces across leagues and seasons is a
    property of football. Spread across segments is what separates the two, and it is the only
    honest basis for using a dependency in pricing.
    """
    seg = df[df["segment"] != "ALL"]
    if seg.empty:
        return pd.DataFrame()
    g = seg.groupby(["market_a", "market_b"])["dependency_ratio"]
    out = g.agg(n_segments="size", ratio_mean="mean", ratio_min="min",
                ratio_max="max", ratio_std="std").reset_index()
    overall = (df[df["segment"] == "ALL"]
               .set_index(["market_a", "market_b"])["dependency_ratio"])
    out["ratio_overall"] = [overall.get((a, b)) for a, b in
                            zip(out["market_a"], out["market_b"])]
    out = out[out["n_segments"] >= min_segments].copy()
    # Same sign and never near-independent anywhere => usable. Anything that flips sign across
    # leagues is noise being read as structure.
    out["all_same_direction"] = ((out["ratio_min"] > 1.0) | (out["ratio_max"] < 1.0))
    out["spread"] = (out["ratio_max"] - out["ratio_min"]).round(4)
    return out.sort_values("spread").round(4)

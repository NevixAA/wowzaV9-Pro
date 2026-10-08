"""Evidence control for league x market x track cells: shrinkage, multiple testing, sequential CLV.

    python -m src.studies.evidence

Answers "has this cell EARNED money?" in a way that does not reward a lucky small sample.

  SHRINKAGE     empirical-Bayes normal-normal per cell: ROI_hat ~ N(theta, se^2),
                theta ~ N(mu_market, tau^2), tau^2 by DerSimonian-Laird. A 12-bet +30% cell
                shrinks almost to its market's mean; a 400-bet cell barely moves.
                Outputs posterior mean/sd, P(edge>0), P(edge>2%), shrinkage factor.
  DEPENDENCE    SE three ways: independent bets, matchday blocks, ISO-week blocks; the LARGEST is
                used, so a conclusion has to survive the most pessimistic of the three.
  MULTIPLE TESTS  n cells searched, raw one-sided p, Benjamini-Hochberg q, and a White
                reality-check p for the best cell (max-t under a centred block bootstrap).
  SEQUENTIAL CLV  anytime-valid normal-mixture confidence sequence on mean CLV (alpha 0.10),
                which can be looked at after every bet without inflating error; plus a one-sided
                CUSUM that alarms on deterioration.

Nothing here moves money. The output is a RECOMMENDATION per cell; changing the execution policy
is a human-approved commit (wowza-exec registry/execution_policy.json).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies import common as C

CUTOFF = "2026-08-10"
STAKED = ("SNIPER", "MARKSMAN")
ALPHA = 0.10
GATES = {"min_n": 150, "p_edge_pos": 0.80}
#: Cells below this are reported but never tested or used to estimate priors: three bets that all
#: won have a sample sd of zero and would otherwise look infinitely significant.
MIN_TEST_N, MIN_TEST_DAYS = 10, 5


def _bets() -> pd.DataFrame:
    m = pd.read_csv(cfg.V9_LOCAL / "output" / "bets_ledger.csv")
    m["market"] = "ou25"
    s = pd.read_csv(cfg.V9_LOCAL / "output" / "side_bets_ledger.csv")
    cols = ["generated_at", "match_date", "league", "home_team", "away_team", "market", "odds",
            "signal_tier", "model_type", "result", "clv_pct"]
    d = pd.concat([m[cols], s[cols]], ignore_index=True)
    d = d[d["result"].isin(["WIN", "LOSS"]) & d["signal_tier"].isin(STAKED)
          & (pd.to_datetime(d["match_date"], errors="coerce") >= CUTOFF)].copy()
    d["u"] = np.where(d["result"] == "WIN", d["odds"] - 1, -1.0)
    d["week"] = pd.to_datetime(d["match_date"]).dt.strftime("%G-%V")
    d["paper_league"] = d["league"].astype(str).str.strip().isin(cfg.PAPER_LEAGUES)
    return d.sort_values("generated_at")


def _block_se(u, g) -> float:
    s = pd.DataFrame({"u": u, "g": g}).groupby("g")["u"].agg(["sum", "count"])
    if len(s) < 3:
        return float("nan")
    idx = C.RNG.integers(0, len(s), size=(2000, len(s)))
    return float(np.std(s["sum"].to_numpy()[idx].sum(1) / s["count"].to_numpy()[idx].sum(1), ddof=1))


def _norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def confidence_sequence(x, alpha=ALPHA, rho=50.0) -> dict:
    """Robbins normal-mixture confidence sequence for the running mean, with a plug-in sd.
    Approximate (sd estimated, not known), stated as such."""
    x = np.asarray(pd.to_numeric(pd.Series(x), errors="coerce").dropna(), float)
    if len(x) < 10:
        return {"n": int(len(x)), "status": "TOO_FEW"}
    t = np.arange(1, len(x) + 1)
    mean = np.cumsum(x) / t
    sd = np.maximum(pd.Series(x).expanding(5).std().bfill().to_numpy(), 1e-6)
    rad = sd * np.sqrt(2 * (t + rho) / t ** 2 * np.log(np.sqrt((t + rho) / rho) / alpha))
    lo, hi = mean - rad, mean + rad
    first_pos = int(np.argmax(lo > 0)) + 1 if (lo > 0).any() else None
    first_neg = int(np.argmax(hi < 0)) + 1 if (hi < 0).any() else None
    return {"n": int(len(x)), "mean": round(float(mean[-1]), 3), "lcb": round(float(lo[-1]), 3),
            "ucb": round(float(hi[-1]), 3), "first_bet_lcb_above_0": first_pos,
            "first_bet_ucb_below_0": first_neg}


def cusum_down(x, k=0.5, h=4.0) -> dict:
    """One-sided CUSUM on standardised CLV: alarms when the mean drifts DOWN by ~k sd."""
    x = np.asarray(pd.to_numeric(pd.Series(x), errors="coerce").dropna(), float)
    if len(x) < 20:
        return {"status": "TOO_FEW"}
    z = (x - x[:20].mean()) / max(x[:20].std(ddof=1), 1e-6)
    s, alarm = 0.0, None
    for i, v in enumerate(z):
        s = max(0.0, s - v - k)
        if s > h and alarm is None:
            alarm = i + 1
    return {"alarm": alarm is not None, "alarm_at_bet": alarm, "baseline": "first 20 bets"}


def run() -> dict:
    d = _bets()
    # SE FLOOR: a cell cannot be more certain than independent bets with the estate's per-bet sd.
    sd_bet = float(d["u"].std(ddof=1))
    cells = []
    for (lg, mk, tr), g in d.groupby(["league", "market", "model_type"]):
        n = len(g)
        roi = float(g["u"].mean())
        se_iid = float(g["u"].std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
        se_day, se_week = _block_se(g["u"], g["match_date"]), _block_se(g["u"], g["week"])
        se = np.nanmax([se_iid, se_day, se_week, sd_bet / math.sqrt(n)]) if n > 1 else float("nan")
        cells.append({"league": lg, "market": mk, "track": tr, "paper_league": bool(g["paper_league"].iloc[0]),
                      "n": n, "matchdays": int(g["match_date"].nunique()), "units": round(float(g["u"].sum()), 2),
                      "roi": round(roi, 4), "se_iid": round(se_iid, 4), "se_matchday": round(se_day, 4),
                      "se_week": round(se_week, 4), "se_used": round(float(se), 4),
                      "clv_cs": confidence_sequence(g["clv_pct"]), "clv_cusum": cusum_down(g["clv_pct"]),
                      "_u": g["u"].to_numpy(), "_days": g["match_date"].to_numpy()})
    E = pd.DataFrame(cells)
    E = E[E["se_used"].notna() & (E["se_used"] > 0)].copy()
    E["testable"] = (E["n"] >= MIN_TEST_N) & (E["matchdays"] >= MIN_TEST_DAYS) & ~E["paper_league"]

    # ── empirical-Bayes shrinkage toward each market's pooled mean ──────────────────────────
    # ONE POOL across every testable cell, not one per market. Per-market pooling was tried first
    # and failed on this data: BTTS had two testable cells and Argentina carried 73 of their 88
    # bets, so "the BTTS mean" WAS Argentina, and a Japan BTTS cell that lost 18% was pulled up to
    # +39%. Shrinkage must be at least as sceptical as the cell is small, so every cell shrinks
    # toward the mean of ALL testable cells. Market means are still reported, as context only.
    g = E[E["testable"]]
    w = 1 / g["se_used"] ** 2
    mu = float((w * g["roi"]).sum() / w.sum())
    Q = float((w * (g["roi"] - mu) ** 2).sum())
    k = len(g)
    tau2 = max(0.0, (Q - (k - 1)) / (w.sum() - (w ** 2).sum() / w.sum())) if k > 1 else 0.0
    se_mu = math.sqrt(1 / (1 / (g["se_used"] ** 2 + tau2)).sum())
    se2 = E["se_used"] ** 2
    B = se2 / (se2 + tau2) if tau2 > 0 else pd.Series(1.0, index=E.index)
    post_mean = B * mu + (1 - B) * E["roi"]
    post_sd = np.maximum(np.sqrt((1 - B) * se2 + (B ** 2) * se_mu ** 2), 1e-9)
    E["prior_mean"], E["prior_mean_se"], E["tau"] = round(mu, 4), round(se_mu, 4), round(math.sqrt(tau2), 4)
    E["shrinkage"] = B.round(3)
    E["posterior_mean"] = post_mean.round(4)
    E["posterior_sd"] = np.round(post_sd, 4)
    # P(theta > c) = 1 - Phi((c - m) / s) = sf((c - m) / s)
    E["p_edge_gt_0"] = [round(_norm_sf((0 - m) / s), 3) for m, s in zip(post_mean, post_sd)]
    E["p_edge_gt_2pct"] = [round(_norm_sf((0.02 - m) / s), 3) for m, s in zip(post_mean, post_sd)]
    market_means = {mk: {"n_bets": int(x["n"].sum()), "cells": int(len(x)),
                         "pooled_roi": round(float((x["roi"] * x["n"]).sum() / x["n"].sum()), 4)}
                    for mk, x in E[E["testable"]].groupby("market")}

    # ── multiple testing ─────────────────────────────────────────────────────────────────────
    E["z"] = E["roi"] / E["se_used"]
    E["p_raw"] = [round(_norm_sf(z), 4) for z in E["z"]]
    T = E[E["testable"]]
    m = len(T)
    order = T["p_raw"].sort_values().index
    q = pd.Series(index=E.index, dtype=float)
    prev = 1.0
    for rank, i in reversed(list(enumerate(order, start=1))):
        prev = min(prev, E.at[i, "p_raw"] * m / rank)
        q[i] = prev
    E["q_bh"] = q.round(4)          # NaN for untestable cells
    # White reality check for the best cell: max-t under a centred matchday bootstrap
    t_obs = float(T["z"].max())
    maxes = []
    for _ in range(1000):
        tb = []
        for _, r in T.iterrows():
            u, days = r["_u"], r["_days"]
            ud = pd.Series(u - u.mean()).groupby(days).agg(["sum", "count"])
            idx = C.RNG.integers(0, len(ud), len(ud))
            mb = ud["sum"].to_numpy()[idx].sum() / ud["count"].to_numpy()[idx].sum()
            tb.append(mb / r["se_used"])
        maxes.append(max(tb))
    rc_p = float(np.mean(np.array(maxes) >= t_obs))

    # ── recommendation ───────────────────────────────────────────────────────────────────────
    def rec(r):
        if r["paper_league"]:
            return "BLOCKED (paper league)"
        if r["clv_cusum"].get("alarm"):
            return "PAPER (CLV deterioration alarm)"
        if not r["testable"]:
            return f"PAPER (too small to test: n {r['n']}, {r['matchdays']} matchdays)"
        if r["n"] < GATES["min_n"]:
            return f"PAPER (n {r['n']} < {GATES['min_n']})"
        if r["p_edge_gt_0"] < GATES["p_edge_pos"]:
            return f"PAPER (P(edge>0) {r['p_edge_gt_0']:.2f} < {GATES['p_edge_pos']})"
        if r["q_bh"] > ALPHA:
            return f"PAPER (fails FDR: q {r['q_bh']:.2f})"
        return "CANDIDATE for TINY_REAL review (human decision)"
    E["recommendation"] = E.apply(rec, axis=1)
    E = E.drop(columns=["_u", "_days"]).sort_values("posterior_mean", ascending=False)
    return {"window_from": CUTOFF, "tiers": list(STAKED), "n_cells_searched": int(m),
            "per_bet_sd_floor": round(sd_bet, 4),
            "pool": {"prior_mean": round(mu, 4), "tau": round(math.sqrt(tau2), 4), "testable_cells": int(k)},
            "market_means_context_only": market_means,
            "n_cells_total": int(len(E)), "best_cell": T.sort_values("z").iloc[-1][["league", "market", "track", "n", "roi", "z"]].to_dict(),
            "reality_check_p_best_cell": round(rc_p, 3),
            "reading": ("reality_check_p is the chance that the BEST of all cells looks this good by luck "
                        "alone; q_bh controls the share of false discoveries across cells"),
            "gates": GATES, "cells": E.to_dict("records")}


if __name__ == "__main__":
    import json
    r = run()
    C.write("evidence", r)
    print(json.dumps({k: v for k, v in r.items() if k != "cells"}, indent=1, default=str))
    for c in r["cells"][:12]:
        print(c["league"][:22].ljust(22), c["market"].ljust(6), c["track"][:10].ljust(10), c["n"],
              c["roi"], "post", c["posterior_mean"], "P>0", c["p_edge_gt_0"], "q", c["q_bh"], "|", c["recommendation"])

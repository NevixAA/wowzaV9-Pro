"""Chronological benchmark: train -> validation (chooses) -> holdout (evaluated once).

SPLITS (fixed before any result was seen; recorded in results.json):
  train       2023-08-04 .. 2024-12-31   (initial fit window; also v9's OOS warm-up)
  validation  2025-01-01 .. 2025-12-31   quarterly blocks, expanding refit before each block
  holdout     2026-01-01 .. 2026-10-14   quarterly blocks, expanding refit, FROZEN choices
Every block is scored by a model fitted only on rows dated strictly before the block starts
(no same-block fit/score). Hyperparameter grids and the market baseline variant are chosen on the
validation period only; holdout labels never feed any choice (no test-label meta-fitting).

DECISION RULE (frozen here, before the holdout was run) — an arm "beats the market on holdout" when
  (1) it is its family's validation-selected configuration,
  (2) holdout mean paired log-loss difference vs the primary MARKET baseline < 0,
  (3) the 95% matchday-week block-bootstrap CI upper bound < 0, and
  (4) the Benjamini-Hochberg q-value across ALL arms x markets <= 0.05.
Betting metrics are reported afterwards and never select anything.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.standard_repair import candidates as C
from src.studies.standard_repair.data import EXP, MARKETS, load, logit

OUT = cfg.OUTPUT_DIR / "standard_repair"
SPLITS = {"train_start": "2023-08-04", "validation": ("2025-01-01", "2025-12-31"),
          "holdout": ("2026-01-01", "2026-12-31")}
N_BOOT = 2000
RULE = {"alpha_ci": 0.95, "bh_q": 0.05,
        "family": "all model arms x markets (market-only variants are the baseline family and excluded)"}
EPS = 1e-6


def ll(p, y):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def _blocks(lo, hi):
    s = pd.date_range(lo, hi, freq="QS")
    return [(a, a + pd.offsets.QuarterBegin(startingMonth=1)) for a in s]


def block_boot(x, groups, n=N_BOOT, seed=20261026):
    """Bootstrap distribution of mean(x), resampling whole matchday-weeks."""
    d = pd.DataFrame({"x": np.asarray(x, float), "g": np.asarray(groups)}).dropna()
    s = d.groupby("g")["x"].agg(["sum", "count"])
    if len(s) < 3:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(s), size=(n, len(s)))
    return s["sum"].to_numpy()[idx].sum(1) / s["count"].to_numpy()[idx].sum(1)


def paired(dx, groups) -> dict:
    bs = block_boot(dx, groups)
    m = float(np.nanmean(dx))
    if bs is None:
        return {"delta": round(m, 6), "ci90": None, "ci95": None, "p_one_sided": None}
    return {"delta": round(m, 6),
            "ci90": [round(float(q), 6) for q in np.quantile(bs, [0.05, 0.95])],
            "ci95": [round(float(q), 6) for q in np.quantile(bs, [0.025, 0.975])],
            # H1: the arm is better (delta < 0). Share of bootstrap means >= 0, +1 smoothing.
            "p_one_sided": round(float((np.sum(bs >= 0) + 1) / (len(bs) + 1)), 5)}


def calib(p, y) -> dict:
    p, y = np.asarray(p, float), np.asarray(y, float)
    b = C.pen_logit(logit(p)[:, None], y, n_free=1)
    q = pd.qcut(pd.Series(p).rank(method="first"), 10, labels=False)
    g = pd.DataFrame({"p": p, "y": y, "q": q}).groupby("q")
    ece = float((g.size() / len(p) * (g["p"].mean() - g["y"].mean()).abs()).sum())
    return {"cal_intercept": round(float(b[0]), 4), "cal_slope": round(float(b[1]), 4), "ece": round(ece, 4)}


def bh(pvals: dict) -> dict:
    keys = [k for k, v in pvals.items() if v is not None]
    if not keys:
        return {}
    p = np.array([pvals[k] for k in keys])
    o = np.argsort(p)
    m = len(p)
    q = np.empty(m)
    run = 1.0
    for rank, i in reversed(list(enumerate(o, start=1))):
        run = min(run, p[i] * m / rank)
        q[i] = run
    return {k: round(float(q[j]), 5) for j, k in enumerate(keys)}


def walk(d: pd.DataFrame, market: str, arm: str, hp: dict, period: str) -> pd.Series:
    fn, _, need_v9, _ = C.ARMS[arm]
    y = f"y_{market}"
    out = pd.Series(np.nan, index=d.index)
    lo, hi = SPLITS[period]
    for b0, b1 in _blocks(lo, hi):
        te = d[(d["date"] >= b0) & (d["date"] < b1)]
        if te.empty:
            continue
        tr = d[(d["date"] < b0) & d[y].notna()]
        out.loc[te.index] = fn(tr, te, market, hp)
    return out


def eval_rows(d: pd.DataFrame, market: str) -> pd.DataFrame:
    """Rows scored in validation + holdout: priced, with v9's walk-forward probability (so every arm is
    compared on the SAME rows)."""
    e = d[(d["date"] >= SPLITS["validation"][0]) & d[f"y_{market}"].notna() & d[f"p_v9_{market}"].notna()]
    return e


def run(markets=MARKETS) -> dict:
    t0 = time.time()
    d = load()
    d["date"] = pd.to_datetime(d["date"])
    res = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"), "splits": SPLITS,
           "decision_rule": RULE, "n_boot": N_BOOT, "bootstrap_block": "ISO matchday-week", "markets": {},
           "log": []}
    rows_out = []
    allp = {}
    for market in markets:
        y = f"y_{market}"
        E = eval_rows(d, market)
        val = E["date"] <= SPLITS["validation"][1]
        hold = E["date"] >= SPLITS["holdout"][0]
        D = d[d["date"] <= E["date"].max()]
        preds_val, sel = {}, {}
        # 1. validation: every arm x every grid point
        for arm in C.arms_for(market):
            grid = C.ARMS[arm][1]
            best = None
            for hp in grid:
                p = walk(D, market, arm, hp, "validation").loc[E.index[val]]
                s = float(ll(p, E.loc[val, y]).mean())
                res["log"].append({"market": market, "arm": arm, "hp": hp, "period": "validation",
                                   "n": int(val.sum()), "log_loss": round(s, 6)})
                if best is None or s < best[0]:
                    best = (s, hp, p)
            sel[arm] = best[1]
            preds_val[arm] = best[2]
        # 2. primary market baseline = best market-only variant on validation
        mv = {a: float(ll(preds_val[a], E.loc[val, y]).mean()) for a in C.MARKET_VARIANTS[market]}
        base = min(mv, key=mv.get)
        # 3. holdout: validation-selected config only, run once
        preds_hold = {arm: walk(D, market, arm, sel[arm], "holdout").loc[E.index[hold]] for arm in sel}
        M = {"n_validation": int(val.sum()), "n_holdout": int(hold.sum()),
             "weeks_validation": int(E.loc[val, "week"].nunique()), "weeks_holdout": int(E.loc[hold, "week"].nunique()),
             "market_baseline": base, "market_variant_validation_ll": {k: round(v, 6) for k, v in mv.items()},
             "selected_hp": sel, "arms": {}}
        for period, mask, P in (("validation", val, preds_val), ("holdout", hold, preds_hold)):
            yy, wk = E.loc[mask, y].to_numpy(), E.loc[mask, "week"].to_numpy()
            lb = ll(P[base], yy)
            bb = (np.asarray(P[base]) - yy) ** 2
            for arm, p in P.items():
                p = np.asarray(p, float)
                la, ba = ll(p, yy), (p - yy) ** 2
                r = {"log_loss": round(float(la.mean()), 6), "brier": round(float(ba.mean()), 6), **calib(p, yy),
                     "sd_prob": round(float(p.std()), 4)}
                if arm != base:
                    r["dLL_vs_market"] = paired(la - lb, wk)
                    r["dBrier_vs_market"] = paired(ba - bb, wk)
                M["arms"].setdefault(arm, {})[period] = r
                if period == "holdout" and arm != base and not arm.startswith("MARKET"):
                    allp[(market, arm)] = r["dLL_vs_market"]["p_one_sided"]
        res["markets"][market] = M
        R = E.loc[:, ["date", "week", "league", "home_team", "away_team", y, "o_AVG", "u_AVG", "close_o_AVG",
                      "close_u_AVG", "pclose_OU25_AVG_power", "book_dispersion", "n_books_ou"]].copy()
        R["market"], R["period"] = market, np.where(val, "validation", "holdout")
        R = R.rename(columns={y: "y"})
        for arm in sel:
            R[f"p_{arm}"] = pd.concat([preds_val[arm], preds_hold[arm]]).reindex(R.index).to_numpy()
        R["p_MARKET"] = R[f"p_{base}"]
        rows_out.append(R)
        print(f"{market} done {time.time() - t0:.0f}s base={base}", flush=True)
    q = bh(allp)
    verdict = {}
    for (market, arm), qq in q.items():
        h = res["markets"][market]["arms"][arm]["holdout"]
        h["dLL_vs_market"]["bh_q"] = qq
        d95 = h["dLL_vs_market"]["ci95"]
        h["beats_market"] = bool(h["dLL_vs_market"]["delta"] < 0 and d95 and d95[1] < 0 and qq <= RULE["bh_q"])
    for market, M in res["markets"].items():
        winners = [a for a, r in M["arms"].items() if r.get("holdout", {}).get("beats_market")]
        verdict[market] = {"beats_market": winners,
                           "best_holdout_arm": min((a for a in M["arms"] if a != M["market_baseline"]),
                                                   key=lambda a: M["arms"][a]["holdout"]["dLL_vs_market"]["delta"])}
    res["verdict"] = verdict
    rows = pd.concat(rows_out, ignore_index=True)
    rows.to_parquet(EXP / "benchmark_rows.parquet", index=False)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    flat = []
    for market, M in res["markets"].items():
        for arm, r in M["arms"].items():
            for period in ("validation", "holdout"):
                x = r.get(period, {})
                dl = x.get("dLL_vs_market", {}) or {}
                db = x.get("dBrier_vs_market", {}) or {}
                flat.append({"market": market, "arm": arm, "period": period, "baseline": M["market_baseline"],
                             "hp": json.dumps(M["selected_hp"].get(arm, {})), "log_loss": x.get("log_loss"),
                             "brier": x.get("brier"), "cal_slope": x.get("cal_slope"), "ece": x.get("ece"),
                             "dLL": dl.get("delta"), "dLL_ci95_lo": (dl.get("ci95") or [None, None])[0],
                             "dLL_ci95_hi": (dl.get("ci95") or [None, None])[1], "p_one_sided": dl.get("p_one_sided"),
                             "bh_q": dl.get("bh_q"), "dBrier": db.get("delta"),
                             "beats_market": x.get("beats_market")})
    pd.DataFrame(flat).to_csv(OUT / "results.csv", index=False)
    return res

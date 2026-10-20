"""VALUABLE deep dive - where, why and under which market conditions does a moderate Wowza-market
disagreement have value? (owner brief 2026-10-20)

    python -m src.studies.valuable.deep_dive --v9 <wowza-betting clone> --v11 <wowza_v11 clone>
        -> output/valuable_deep_dive/*.csv|json|md  +  WOWZA_VALUABLE_Deep_Dive_<date>.xlsx

MEASURE -> EXPLAIN -> VALIDATE. Nothing here changes production: no threshold, tier, stake, BET_ENABLED
or prediction logic is touched, and every artifact says so.

EVIDENCE CLASSES (never mixed):
  LIVE ledger      v9 output/bets_ledger.csv (source=live) + side_bets_ledger.csv, FIRST SIGHT:
                   OU25 earliest tip per fixture, side markets earliest per fixture x market.
                   Only edges that passed the production gate exist here -> lower bands are CENSORED.
  SNAPSHOT history every committed v9 predictions.csv (src.studies.valuable.snapshots): what v9 saw at
                   the time for EVERY fixture, including below-floor candidates, with both sides' prices.
                   Settled from Pro team_match_stats via v9's league-scoped name resolver. Never bet,
                   never notified -> "HISTORICAL_SNAPSHOT", not live-tested.
EDGE DEFINITIONS:
  raw_edge   production's own: OU25 p - 1/odds (vig INCLUDED); side markets p - (1/odds)/1.08 (fixed vig)
  fair_edge  p - two-sided de-vigged market probability (proportional), from the snapshot of the SAME
             run that produced the tip. OU25 and BTTS only; O1.5/O3.5 have no opposite price ->
             FAIR_EDGE_AVAILABLE = NO.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from config import pro_config as cfg

OUT = cfg.BASE_DIR / "output" / "valuable_deep_dive"
EXP = cfg.BASE_DIR / "experiments" / "valuable_2026_10"
REGIME_CHANGE = pd.Timestamp("2026-08-21")          # predict.yml b82cec9f widened the tier gates
FINE = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 10), (10, 12), (12, 15), (15, 999)]
AGG = [(1, 3), (3, 4), (4, 6), (6, 8), (4, 8), (8, 10), (10, 999)]
ODDS = [(1.50, 1.80), (1.80, 2.00), (2.00, 2.25), (2.25, 2.50), (2.50, 2.75), (2.75, 99)]
FLAGS = {"PRODUCTION_SELECTION_CHANGED": "NO", "TIER_THRESHOLDS_CHANGED": "NO", "STAKING_CHANGED": "NO",
         "BET_ENABLED_CHANGED": "NO"}
rng = np.random.default_rng(20261020)


# ───────────────────────────── loading ─────────────────────────────

def _first_sight(d: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    d = d.copy()
    d["gen"] = pd.to_datetime(d["generated_at"], errors="coerce")
    return d.sort_values("gen").drop_duplicates(keys, keep="first")


def effective_floors(market: str, model_type: str, league: str, md: pd.Timestamp, gates_now: dict, gates_old: dict) -> dict:
    """The tier floors in force for this tip, and where they came from."""
    if market == "over25":
        g = (gates_now if md >= REGIME_CHANGE else gates_old).get(league)
        if g:
            return {"effective_valuable_floor": g["valuable"], "effective_marksman_floor": g["marksman"],
                    "effective_sniper_floor": g["sniper"], "tier_rule_source": g["sniper_source"].split(" (")[0],
                    "tier_regime_id": ("post_2026-08-21 " if md >= REGIME_CHANGE else "pre_2026-08-21 ") + g["regime_id"]}
        return {"effective_valuable_floor": np.nan, "effective_marksman_floor": np.nan, "effective_sniper_floor": np.nan,
                "tier_rule_source": "unresolved", "tier_regime_id": "unresolved"}
    return {"effective_valuable_floor": 0.04, "effective_marksman_floor": 0.08, "effective_sniper_floor": 0.10,
            "tier_rule_source": "pipeline.py side-market default (0.04/0.08/0.10, approved league rule may differ)",
            "tier_regime_id": "side_markets_fixed_1.08_overround"}


def _gates(v9: str, env: dict) -> dict:
    """Resolve v9's per-league OU25 gates under a given environment, in a subprocess (v9's own code)."""
    import os
    import subprocess
    code = ("import json,sys; sys.path.insert(0,'.'); from src.gate_resolver import all_gates;"
            "print(json.dumps({g.league: g.as_dict() for g in all_gates(('over25',))}))")
    e = {k: v for k, v in os.environ.items() if k not in ("LEAGUE_SNIPER_CAP", "MARKSMAN_THRESHOLD", "VALUABLE_THRESHOLD")}
    e.update(env)
    r = subprocess.run([sys.executable, "-c", code], cwd=v9, capture_output=True, text=True, env=e)
    return json.loads(r.stdout.strip().splitlines()[-1])


def load_live(v9: str) -> pd.DataFrame:
    o = pd.read_csv(Path(v9) / "output" / "bets_ledger.csv", low_memory=False)
    o = _first_sight(o[o["source"] == "live"], ["match_date", "home_team", "away_team"])
    o["market"] = "over25"
    s = pd.read_csv(Path(v9) / "output" / "side_bets_ledger.csv", low_memory=False)
    s = _first_sight(s[s["source"] == "live"], ["match_date", "home_team", "away_team", "market"])
    cols = ["generated_at", "gen", "match_date", "league", "home_team", "away_team", "market", "side", "odds",
            "edge_pct", "signal_tier", "result", "pnl", "closing_odds", "clv_pct", "model_type", "model_version",
            "retrain_batch_id", "drift_signal", "model_prob"]
    d = pd.concat([o.reindex(columns=cols), s.reindex(columns=cols)], ignore_index=True)
    d["md"] = pd.to_datetime(d["match_date"], errors="coerce")
    d["side"] = d["side"].astype(str).str.upper().replace({"NAN": "YES"})
    d.loc[d["market"] != "over25", "side"] = d.loc[d["market"] != "over25", "side"].replace({"OVER": "YES"})
    d["settled"] = d["result"].isin(["WIN", "LOSS"])
    d["won"] = (d["result"] == "WIN").astype(float)
    d["edge"] = pd.to_numeric(d["edge_pct"], errors="coerce")
    gnow = _gates(v9, {"LEAGUE_SNIPER_CAP": "0.12", "MARKSMAN_THRESHOLD": "0.08", "VALUABLE_THRESHOLD": "0.03"})
    gold = _gates(v9, {})
    fl = [effective_floors(r.market, r.model_type, r.league, r.md, gnow, gold) for r in d.itertuples()]
    d = pd.concat([d.reset_index(drop=True), pd.DataFrame(fl)], axis=1)
    return d


def attach_fair(d: pd.DataFrame) -> pd.DataFrame:
    """Two-sided fair edge from the snapshot of the SAME run (latest snapshot at or before the tip, <=90 min)."""
    s = pd.read_parquet(EXP / "prematch_snapshots.parquet")
    s["gen"] = pd.to_datetime(s["generated_at"], utc=True).dt.tz_localize(None)
    s["match_date"] = s["date"].astype(str).str[:10]
    k = ["match_date", "home_team", "away_team"]
    d = d.copy()
    d["gen"] = pd.to_datetime(d["generated_at"], errors="coerce")
    d["_i"] = np.arange(len(d))
    # the ledger stamps generated_at to the MINUTE (11:00) while the run's snapshot says 11:00:48 -> look up to
    # 59 s past the stamp, backward, so the tip joins the snapshot of the run that CREATED it
    d["gen_q"] = d["gen"] + pd.Timedelta(seconds=59)
    snap = s.sort_values("gen")[k + ["gen", "p_over25", "odds_over25", "odds_under25", "p_btts", "odds_btts",
                                     "odds_btts_no", "no_form_data", "drift_signal", "model_version", "snapshot_sha",
                                     "signal_tier", "best_side", "edge_over", "edge_under"]].rename(columns={
        "gen": "gen_q", "drift_signal": "snap_drift", "model_version": "snap_model_version",
        "signal_tier": "snap_tier", "best_side": "snap_side"})
    m = pd.merge_asof(d.dropna(subset=["gen_q"]).sort_values("gen_q"), snap, on="gen_q", by=k,
                      direction="backward", tolerance=pd.Timedelta("90min"))
    # merge_asof resets the index (CLAUDE.md trap 3) - re-key on the carried row id, never by position
    m = m.set_index("_i")
    d = d.set_index("_i").join(m[[c for c in m.columns if c not in d.columns]], how="left").reset_index()
    ou = d["market"] == "over25"
    qo, qu = 1 / d["odds_over25"], 1 / d["odds_under25"]
    d["fair_over"] = qo / (qo + qu)
    d["ou_overround"] = qo + qu
    p_side = np.where(d["side"] == "UNDER", 1 - d["p_over25"], d["p_over25"])
    fair_side = np.where(d["side"] == "UNDER", 1 - d["fair_over"], d["fair_over"])
    d["model_p"] = np.where(ou, p_side, pd.to_numeric(d["model_prob"], errors="coerce"))
    d["fair_p"] = np.where(ou, fair_side, np.nan)
    by, bn = 1 / d["odds_btts"], 1 / d["odds_btts_no"]
    bt = d["market"] == "btts"
    d.loc[bt, "fair_p"] = (by / (by + bn))[bt]
    d.loc[bt, "btts_actual_overround"] = (by + bn)[bt]
    d["fair_edge"] = (d["model_p"] - d["fair_p"]) * 100
    d["FAIR_EDGE_AVAILABLE"] = np.where(d["market"].isin(["over15", "over35"]), "NO",
                                        np.where(d["fair_edge"].notna(), "YES", "NO_SNAPSHOT_MATCH"))
    # integrity: does the snapshot price equal the ledger price? (proves it is the same run)
    snap_odds = np.where(ou, np.where(d["side"] == "UNDER", d["odds_under25"], d["odds_over25"]),
                         np.where(bt, d["odds_btts"], np.nan))
    d["snapshot_odds_match"] = np.isclose(snap_odds, pd.to_numeric(d["odds"], errors="coerce"), atol=0.011)
    d["recomputed_raw_edge"] = np.where(ou, (d["model_p"] - 1 / pd.to_numeric(d["odds"], errors="coerce")) * 100, np.nan)
    # TRUE FIRST-SIGHT label (src/ledger.py upgrades tier+edge in place when a later run is stronger)
    snap_edge = np.where(d["side"] == "UNDER", d["edge_under"], d["edge_over"]) * 100
    d["first_edge"] = np.where(ou, snap_edge, np.nan)
    d["first_tier"] = np.where(ou & d["snap_tier"].notna(), d["snap_tier"].astype(str).str.upper()
                               .replace({"VALUE": "VALUABLE"}), None)
    if "btts" in set(d["market"]):                                       # side markets: production rule on first odds
        e = (d["model_p"] - (1 / d["odds_btts"]) / 1.08) * 100
        d.loc[bt, "first_edge"] = e[bt]
    rank = {"VALUABLE": 1, "MARKSMAN": 2, "SNIPER": 3}
    d["upgraded_after_first_sight"] = [(rank.get(str(a), 0) > rank.get(str(b), 0)) if b is not None else None
                                       for a, b in zip(d["signal_tier"], d["first_tier"])]
    return d.drop(columns=["_i"], errors="ignore")


# ───────────────────────────── statistics ─────────────────────────────

def _boot_ci(pnl: np.ndarray, days: np.ndarray, n: int = 2000) -> tuple:
    if len(pnl) < 5:
        return (np.nan, np.nan)
    u = np.unique(days)
    idx = {k: np.where(days == k)[0] for k in u}
    b = [pnl[np.concatenate([idx[k] for k in rng.choice(u, len(u))])].mean() for _ in range(n)]
    return tuple(np.round(np.percentile(b, [5, 95]) * 100, 1))


def summ(x: pd.DataFrame, ci: bool = False) -> dict:
    x = x[x["settled"]]
    n = len(x)
    if not n:
        return {"N": 0}
    pnl = x["pnl"].astype(float).values
    r = {"N": n, "W": int(x["won"].sum()), "L": int(n - x["won"].sum()), "PnL": round(float(pnl.sum()), 2),
         "ROI_pct": round(float(pnl.mean() * 100), 1), "hit_pct": round(float(x["won"].mean() * 100), 1),
         "avg_odds": round(float(x["odds"].astype(float).mean()), 2),
         "CLV_pct": round(float(pd.to_numeric(x["clv_pct"], errors="coerce").mean()), 2)
         if pd.to_numeric(x["clv_pct"], errors="coerce").notna().any() else None,
         "CLV_n": int(pd.to_numeric(x["clv_pct"], errors="coerce").notna().sum())}
    # one-sided t-test that mean pnl > 0 (flat 1u stakes)
    r["p_value"] = float(stats.ttest_1samp(pnl, 0, alternative="greater").pvalue) if n >= 5 and pnl.std() > 0 else np.nan
    if ci:
        lo, hi = _boot_ci(pnl, x["md"].dt.date.values)
        r["ROI_ci90_lo"], r["ROI_ci90_hi"] = lo, hi
    return r


def bh(p: pd.Series) -> pd.Series:
    p = p.astype(float)
    ok = p.notna()
    q = pd.Series(np.nan, index=p.index)
    if ok.sum():
        v = p[ok].values
        o = np.argsort(v)
        m = len(v)
        qq = v[o] * m / (np.arange(m) + 1)
        qq = np.minimum.accumulate(qq[::-1])[::-1]
        out = np.empty(m)
        out[o] = np.minimum(qq, 1)
        q[ok] = out
    return q


def shrink(cells: pd.DataFrame, group_col: str, prior: dict) -> pd.Series:
    """Empirical-Bayes shrinkage of cell ROI toward its parent (model x market) mean.
    tau^2 (true between-cell variance) by method of moments; per-bet variance ~1.0 at even-ish odds."""
    out = pd.Series(np.nan, index=cells.index)
    for g, c in cells.groupby(group_col):
        roi = c["ROI_pct"] / 100
        n = c["N"].astype(float)
        mu = prior.get(g, float(np.average(roi, weights=n)) if n.sum() else 0.0)
        s2 = 1.0 / n
        tau2 = max(float(np.average((roi - mu) ** 2, weights=n) - np.average(s2, weights=n)), 0.0)
        w = tau2 / (tau2 + s2) if tau2 > 0 else 0 * n
        out[c.index] = ((w * roi + (1 - w) * mu) * 100).round(1)
    return out


def band_of(v: float, bands) -> str | None:
    for lo, hi in bands:
        if lo <= v < hi:
            return f"{lo}-{hi if hi < 999 else '+'}"
    return None


# ───────────────────────────── analyses ─────────────────────────────

def windows(d: pd.DataFrame, end: pd.Timestamp) -> dict:
    return {"full_history": d, "since_aug26": d[d.md >= "2026-08-26"], "pre_oct6": d[d.md < "2026-10-06"],
            "oct6_onward": d[d.md >= "2026-10-06"], "last30": d[d.md > end - pd.Timedelta(days=30)],
            "last14": d[d.md > end - pd.Timedelta(days=14)], "last7": d[d.md > end - pd.Timedelta(days=7)]}


def edge_band_table(d: pd.DataFrame, col: str, label: str) -> pd.DataFrame:
    rows = []
    for bands, kind in ((FINE, "fine"), (AGG, "aggregate")):
        for lo, hi in bands:
            for (mkt, mt), g in d.groupby(["market", "model_type"]):
                x = g[(g[col] >= lo) & (g[col] < hi)]
                floor = g["effective_valuable_floor"].min() * 100 if g["effective_valuable_floor"].notna().any() else 3
                status = ("LEDGER_CENSORED" if hi <= floor else
                          "PARTLY_CENSORED" if lo < floor else "LIVE_OBSERVED")
                if col == "fair_edge":
                    status = "LIVE_OBSERVED (fair edge of gated tips)" if len(x) else "NO_OBSERVATIONS"
                rows.append({"edge_type": label, "kind": kind, "band": f"{lo}-{hi if hi < 999 else '+'}",
                             "market": mkt, "model_type": mt, "status": status, **summ(x, ci=True)})
    return pd.DataFrame(rows)


def cell_table(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (tier, lg, mkt, mt), g in d.groupby(["signal_tier", "league", "market", "model_type"]):
        rows.append({"tier": tier, "league": lg, "market": mkt, "model_type": mt, **summ(g, ci=True),
                     "avg_raw_edge": round(float(g.loc[g.settled, "edge"].mean()), 2) if g.settled.any() else None,
                     "avg_fair_edge": round(float(g.loc[g.settled, "fair_edge"].mean()), 2)
                     if g.loc[g.settled, "fair_edge"].notna().any() else None})
    c = pd.DataFrame(rows)
    c = c[c["N"] > 0].reset_index(drop=True)
    c["parent"] = c["tier"] + "|" + c["market"] + "|" + c["model_type"]
    c["ROI_shrunk_pct"] = shrink(c, "parent", {})
    c["q_value_BH"] = bh(c["p_value"]).round(3)
    return c.drop(columns=["parent"])


def tier_comparison(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (lg, mkt, mt), g in d.groupby(["league", "market", "model_type"]):
        r = {"league": lg, "market": mkt, "model_type": mt}
        for t in ("VALUABLE", "MARKSMAN", "SNIPER"):
            s = summ(g[g.signal_tier == t])
            r.update({f"{t}_N": s.get("N", 0), f"{t}_ROI": s.get("ROI_pct"), f"{t}_CLV": s.get("CLV_pct")})
        if r["VALUABLE_N"] and (r["MARKSMAN_N"] or r["SNIPER_N"]):
            hi = [x for x in (r["MARKSMAN_ROI"], r["SNIPER_ROI"]) if x is not None]
            r["valuable_beats_higher_tiers_in_cell"] = bool(hi) and r["VALUABLE_ROI"] > max(hi)
        rows.append(r)
    return pd.DataFrame(rows)


def drift_explanation(d: pd.DataFrame) -> pd.DataFrame:
    """Do drift upgrades/downgrades explain the tier inversion? OU25 only (drift_signal is OU25)."""
    x = d[(d.market == "over25") & d.settled].copy()
    x["drift"] = x["drift_signal"].fillna("None").astype(str)
    rows = []
    for (t, dr), g in x.groupby(["signal_tier", "drift"]):
        rows.append({"tier": t, "drift_signal": dr, **summ(g, ci=True),
                     "avg_raw_edge": round(float(g.edge.mean()), 2)})
    return pd.DataFrame(rows)


def monotonicity(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    x = d[d.settled].copy()
    x["clv"] = pd.to_numeric(x["clv_pct"], errors="coerce")
    x["excess_hit"] = x["won"] - 1 / x["odds"].astype(float)          # outcome beyond the raw implied price
    for scope, keys in (("model x market", ["model_type", "market"]), ("league x model x market", ["league", "model_type", "market"])):
        for k, g in x.groupby(keys):
            if len(g) < 30:
                continue
            r = {"scope": scope, "cell": " | ".join(k if isinstance(k, tuple) else (k,)), "N": len(g)}
            for target in ("pnl", "clv", "excess_hit"):
                gg = g.dropna(subset=["edge", target])
                if len(gg) >= 30:
                    rho, p = stats.spearmanr(gg["edge"], gg[target])
                    r[f"spearman_edge_vs_{target}"], r[f"p_{target}"] = round(float(rho), 3), round(float(p), 4)
            if g["fair_edge"].notna().sum() >= 30:
                gg = g.dropna(subset=["fair_edge"])
                rho, p = stats.spearmanr(gg["fair_edge"], gg["pnl"])
                r["spearman_fair_edge_vs_pnl"], r["p_fair_pnl"] = round(float(rho), 3), round(float(p), 4)
            rows.append(r)
    m = pd.DataFrame(rows)
    for c in [c for c in m.columns if c.startswith("p_")]:
        m["q_" + c[2:]] = bh(m[c]).round(3)
    return m


def calibration(d: pd.DataFrame) -> pd.DataFrame:
    x = d[d.settled & d["model_p"].notna()].copy()
    x["band"] = x["edge"].map(lambda v: band_of(v, AGG[1:4] + [(8, 12), (12, 999)]))
    rows = []
    for (mkt, b), g in x.groupby(["market", "band"]):
        rows.append({"market": mkt, "raw_edge_band": b, "N": len(g),
                     "claimed_hit": round(float(g.model_p.mean()), 3), "fair_market_hit": round(float(g.fair_p.mean()), 3)
                     if g.fair_p.notna().any() else None, "real_hit": round(float(g.won.mean()), 3),
                     "model_error_pp": round(float((g.model_p.mean() - g.won.mean()) * 100), 1),
                     "market_error_pp": round(float((g.fair_p.mean() - g.won.mean()) * 100), 1) if g.fair_p.notna().any() else None})
    return pd.DataFrame(rows)


def data_quality(d: pd.DataFrame) -> pd.DataFrame:
    x = d[d.market == "over25"].copy()
    x["band"] = x["edge"].map(lambda v: band_of(v, [(3, 4), (4, 6), (6, 8), (8, 12), (12, 999)]))
    x["odds_f"] = x["odds"].astype(float)
    x["version_transition"] = x["model_version"].astype(str) != x["snap_model_version"].astype(str)
    rows = []
    for b, g in x.groupby("band"):
        rows.append({"raw_edge_band": b, "N_tips": len(g),
                     "no_form_data_share": round(float(pd.to_numeric(g["no_form_data"], errors="coerce").fillna(0).astype(bool).mean()), 3),
                     "overround_mean": round(float(g["ou_overround"].mean()), 4),
                     "overround_below_1_share": round(float((g["ou_overround"] < 1).mean()), 3),
                     "odds_ge_3_share": round(float((g["odds_f"] >= 3).mean()), 3),
                     "drift_confirmed_share": round(float((g["drift_signal"] == "Confirmed").mean()), 3),
                     "new_format_share": round(float((g["model_type"] == "new_format").mean()), 3),
                     "snapshot_matched_share": round(float(g["snapshot_odds_match"].mean()), 3),
                     "model_version_differs_from_snapshot_share": round(float(g["version_transition"].mean()), 3)})
    return pd.DataFrame(rows)


def odds_interaction(d: pd.DataFrame) -> pd.DataFrame:
    x = d.copy()
    x["edge_band"] = x["edge"].map(lambda v: band_of(v, [(3, 4), (4, 6), (6, 8), (8, 12), (12, 999)]))
    x["odds_band"] = x["odds"].astype(float).map(lambda v: band_of(v, ODDS))
    rows = [{"tier": t, "market": m, "edge_band": e, "odds_band": o, **summ(g)}
            for (t, m, e, o), g in x.groupby(["signal_tier", "market", "edge_band", "odds_band"])]
    return pd.DataFrame(rows)


def side_table(d: pd.DataFrame) -> pd.DataFrame:
    x = d[d.market == "over25"].copy()
    x["edge_band"] = x["edge"].map(lambda v: band_of(v, [(3, 4), (4, 6), (6, 8), (8, 12), (12, 999)]))
    rows = [{"league": lg, "tier": t, "side": s, "edge_band": e, **summ(g)}
            for (lg, t, s, e), g in x.groupby(["league", "signal_tier", "side", "edge_band"])]
    rows += [{"league": "ALL", "tier": t, "side": s, "edge_band": "ALL", **summ(g, ci=True)}
             for (t, s), g in x.groupby(["signal_tier", "side"])]
    return pd.DataFrame(rows)


def regime_table(d: pd.DataFrame, end) -> pd.DataFrame:
    rows = []
    for w, x in windows(d, end).items():
        for (t, m), g in x.groupby(["signal_tier", "market"]):
            rows.append({"split": "window", "value": w, "tier": t, "market": m, **summ(g, ci=True)})
    for reg, x in (("pre_2026-08-21", d[d.md < REGIME_CHANGE]), ("post_2026-08-21", d[d.md >= REGIME_CHANGE])):
        for (t, m), g in x.groupby(["signal_tier", "market"]):
            rows.append({"split": "tier_regime", "value": reg, "tier": t, "market": m, **summ(g)})
    for col in ("retrain_batch_id", "model_version"):
        for (v, t), g in d[d.signal_tier == "VALUABLE"].groupby([col, "market"]):
            rows.append({"split": col, "value": str(v), "tier": "VALUABLE", "market": t, **summ(g)})
    return pd.DataFrame(rows)


def concentration(v: pd.DataFrame) -> dict:
    v = v[v.settled].copy()
    v["cell"] = v["league"] + " | " + v["market"]
    base = summ(v, ci=True)
    by_cell = v.groupby("cell")["pnl"].sum().sort_values(ascending=False)
    by_lg = v.groupby("league")["pnl"].sum().sort_values(ascending=False)
    tot = float(v["pnl"].sum())
    out = {"all": base, "top5_cells_share_of_profit": round(float(by_cell.head(5).sum() / tot), 3) if tot > 0 else None,
           "top5_cells": by_cell.head(5).round(2).to_dict()}
    out["ex_top_league (" + by_lg.index[0] + ")"] = summ(v[v.league != by_lg.index[0]], ci=True)
    out["ex_top3_cells"] = summ(v[~v.cell.isin(by_cell.index[:3])], ci=True)
    out["ex_top5_cells"] = summ(v[~v.cell.isin(by_cell.index[:5])], ci=True)
    out["ex_argentina"] = summ(v[v.league != "Argentina Primera Division"], ci=True)
    top5 = v.sort_values("pnl", ascending=False).index[:5]
    out["ex_best_5_winners"] = summ(v.drop(index=top5), ci=True)
    return out


def walk_forward(d: pd.DataFrame) -> pd.DataFrame:
    """Choose the edge band on DISCOVERY only, then score VALIDATION and HOLDOUT untouched.
    Discovery 2026-08-10..09-20, validation 09-21..10-05, holdout 10-06..10-19."""
    per = {"discovery": (pd.Timestamp("2026-08-10"), pd.Timestamp("2026-09-20")),
           "validation": (pd.Timestamp("2026-09-21"), pd.Timestamp("2026-10-05")),
           "holdout": (pd.Timestamp("2026-10-06"), pd.Timestamp("2026-10-19"))}
    cands = [(3, 4), (4, 6), (6, 8), (4, 8), (3, 6), (8, 12), (12, 999)]
    rows = []
    x = d[d.settled]
    for edge_col in ("edge", "fair_edge"):
        for (mkt, mt), g in x.groupby(["market", "model_type"]):
            disc = g[(g.md >= per["discovery"][0]) & (g.md <= per["discovery"][1])]
            best, best_roi = None, -9e9
            for lo, hi in cands:
                s = disc[(disc[edge_col] >= lo) & (disc[edge_col] < hi)]
                if len(s) >= 20 and s.pnl.mean() > best_roi:
                    best, best_roi = (lo, hi), s.pnl.mean()
            for lo, hi in ([best] if best else []) + [(4, 8)]:
                tag = "selected_on_discovery" if (lo, hi) == best else "pre_specified_H-VAL-01 (4-8)"
                for pname, (a, b) in per.items():
                    s = g[(g.md >= a) & (g.md <= b) & (g[edge_col] >= lo) & (g[edge_col] < hi)]
                    rows.append({"edge_type": edge_col, "market": mkt, "model_type": mt, "band": f"{lo}-{hi}",
                                 "how_chosen": tag, "period": pname, **summ(s, ci=True)})
    return pd.DataFrame(rows)


def v11_convergence(d: pd.DataFrame, v11: str) -> pd.DataFrame:
    o = Path(v11) / "output"
    mv = pd.read_csv(o / "v11_movement_by_league.csv")
    pl = pd.read_csv(o / "v11_placebo_by_league.csv")
    rs = pd.read_csv(o / "v11_residual.csv")
    v = d[(d.market == "over25") & (d.signal_tier == "VALUABLE") & (d.md >= "2026-08-26")]
    rows = []
    for lg, g in v.groupby("league"):
        s = summ(g)
        m = mv[mv.segment == lg].head(1)
        p = pl[pl.league == lg].head(1)
        r = rs[rs.scope == lg].head(1)
        row = {"league": lg, "market": "over25", "VALUABLE_N": s.get("N", 0), "VALUABLE_ROI": s.get("ROI_pct"),
               "VALUABLE_CLV": s.get("CLV_pct"),
               "V11_toward": float(m.toward_rate.iloc[0]) if len(m) else None,
               "V11_toward_ci": f"[{m.toward_ci_lo.iloc[0]}, {m.toward_ci_hi.iloc[0]}]" if len(m) else None,
               "V11_movement_n_fixtures": int(m.n_fixtures.iloc[0]) if len(m) else 0,
               "V11_minus_placebo": float(p.wowza_minus_fixed.iloc[0]) if len(p) else None,
               "V11_placebo_ci": p.CI.iloc[0] if len(p) else None,
               "V11_CLV": float(m.mean_clv_pct.iloc[0]) if len(m) else None,
               "V11_residual_wowza_helps": bool(r.wowza_helps.iloc[0]) if len(r) else None,
               "V11_residual_n": int(r.n.iloc[0]) if len(r) else 0,
               "V11_sample_status": m.sample_status.iloc[0] if len(m) and "sample_status" in m else None}
        roi_ok = (row["VALUABLE_ROI"] or -1) > 0 and row["VALUABLE_N"] >= 10
        price_ok = sum([(row["VALUABLE_CLV"] or 0) > 0, (row["V11_CLV"] or 0) > 0,
                        (row["V11_minus_placebo"] or 0) > 0, bool(row["V11_residual_wowza_helps"])]) >= 3
        row["classification"] = ("INSUFFICIENT" if row["VALUABLE_N"] < 10 else
                                 "OUTCOME_AND_PRICE" if roi_ok and price_ok else
                                 "OUTCOME_ONLY" if roi_ok else
                                 "PRICE_ONLY" if price_ok else "NEGATIVE")
        rows.append(row)
    return pd.DataFrame(rows)


# ───────────────────── 1-3% from snapshot history (never bet) ─────────────────────

def snapshot_low_edge(v9: str) -> tuple[pd.DataFrame, dict]:
    import importlib.util                                                # v9's league-scoped resolver, by FILE:
    spec = importlib.util.spec_from_file_location("v9_team_names", Path(v9) / "src" / "team_names.py")
    tn = importlib.util.module_from_spec(spec)                          # Pro's own `src` would shadow v9's
    spec.loader.exec_module(tn)
    resolve = tn.resolve
    s = pd.read_parquet(EXP / "prematch_snapshots.parquet")
    s["gen"] = pd.to_datetime(s["generated_at"], utc=True)
    s = s.dropna(subset=["p_over25", "odds_over25", "odds_under25"]).sort_values("gen")
    s = s.drop_duplicates(["league", "date", "home_team", "away_team"], keep="first")          # first VALID price
    import glob
    fs = sorted(glob.glob(str(cfg.BASE_DIR / "data" / "season_2026_27" / "team_match_stats" / "**" / "*.parquet"), recursive=True))
    r = pd.concat([pd.read_parquet(f, columns=["league", "match_date", "home_team", "away_team", "home_goals", "away_goals"])
                   for f in fs], ignore_index=True).dropna(subset=["home_goals", "away_goals"])
    r = r.drop_duplicates(["league", "match_date", "home_team", "away_team"], keep="last")
    r["md"] = pd.to_datetime(r["match_date"]).dt.normalize()
    out = []
    for lg, g in s.groupby("league"):
        rl = r[r.league == lg]
        names = sorted(set(rl.home_team) | set(rl.away_team))
        if not names:
            continue
        for row in g.itertuples():
            h, a = resolve(row.home_team, names), resolve(row.away_team, names)
            if not h or not a:
                continue
            md = pd.Timestamp(str(row.date)[:10])
            m = rl[(rl.home_team == h) & (rl.away_team == a) & ((rl.md - md).abs() <= pd.Timedelta(days=1))]
            if len(m) == 1:
                out.append({"idx": row.Index, "goals": float(m.home_goals.iloc[0] + m.away_goals.iloc[0])})
    n_priced = int(len(s))
    gl = pd.DataFrame(out).set_index("idx")
    s = s.join(gl, how="inner")
    s["over"] = (s["goals"] > 2.5).astype(float)
    qo, qu = 1 / s.odds_over25, 1 / s.odds_under25
    s["fair_over"] = qo / (qo + qu)
    rows = []
    for side in ("OVER", "UNDER"):
        p = s.p_over25 if side == "OVER" else 1 - s.p_over25
        odds = s.odds_over25 if side == "OVER" else s.odds_under25
        fair = s.fair_over if side == "OVER" else 1 - s.fair_over
        won = s.over if side == "OVER" else 1 - s.over
        rows.append(pd.DataFrame({"league": s.league, "home_team": s.home_team, "away_team": s.away_team,
                                  "model_type": s.model_type, "md": pd.to_datetime(s.date.astype(str).str[:10]),
                                  "side": side, "odds": odds, "raw_edge": (p - 1 / odds) * 100, "fair_edge": (p - fair) * 100,
                                  "won": won, "pnl": np.where(won == 1, odds - 1, -1.0), "snapshot_sha": s.snapshot_sha}))
    c = pd.concat(rows, ignore_index=True)
    # one candidate per fixture: the side v9 itself would pick (larger raw edge), as production does
    c = c.sort_values("raw_edge", ascending=False).drop_duplicates(["league", "md", "home_team", "away_team"], keep="first")
    meta = {"fixtures_with_snapshot_price": n_priced, "settled_via_team_match_stats": int(len(gl)),
            "settled_share": round(len(gl) / n_priced, 3) if n_priced else None}
    # integrity: settled outcome must agree with the live ledger's own WIN/LOSS where both exist
    return c, meta


def low_edge_table(c: pd.DataFrame) -> pd.DataFrame:
    rows = []
    c = c.assign(settled=True)
    c["md"] = pd.to_datetime(c["md"])
    for col in ("raw_edge", "fair_edge"):
        for lo, hi in [(0, 1), (1, 2), (2, 3), (1, 3), (3, 4), (4, 6), (6, 8), (8, 12), (12, 999)]:
            for mt, g in c.groupby("model_type"):
                x = g[(g[col] >= lo) & (g[col] < hi)]
                if not len(x):
                    continue
                pnl = x.pnl.values
                lo_ci, hi_ci = _boot_ci(pnl, x.md.dt.date.values)
                rows.append({"edge_type": col, "band": f"{lo}-{hi if hi < 999 else '+'}", "model_type": mt,
                             "status": "HISTORICAL_SNAPSHOT (recorded at the time, never bet)",
                             "N": len(x), "hit_pct": round(float(x.won.mean() * 100), 1),
                             "ROI_pct": round(float(pnl.mean() * 100), 1), "ROI_ci90_lo": lo_ci, "ROI_ci90_hi": hi_ci,
                             "avg_odds": round(float(x.odds.mean()), 2)})
    return pd.DataFrame(rows)


def upgrade_table(d: pd.DataFrame) -> pd.DataFrame:
    """Ledger tier (max tier reached before kickoff) vs TRUE first-sight tier, OU25 (snapshot-matched rows)."""
    x = d[(d.market == "over25") & d.first_tier.notna()].copy()
    x["first_tier"] = x["first_tier"].fillna("NONE")
    rows = []
    for (ft, lt), g in x.groupby(["first_tier", "signal_tier"]):
        rows.append({"first_sight_tier": ft, "ledger_tier": lt, "upgraded": ft != lt, **summ(g, ci=True),
                     "first_edge_mean": round(float(g.first_edge.mean()), 2), "ledger_edge_mean": round(float(g.edge.mean()), 2)})
    for up, g in x.groupby(x["upgraded_after_first_sight"].astype(str)):
        rows.append({"first_sight_tier": "ALL", "ledger_tier": "ALL", "upgraded": up, **summ(g, ci=True)})
    return pd.DataFrame(rows)


def first_tier_comparison(d: pd.DataFrame) -> pd.DataFrame:
    x = d[(d.market == "over25") & d.first_tier.notna()].copy()
    rows = [{"first_sight_tier": t, "window": w, **summ(g, ci=True)}
            for w, xx in (("since_aug26", x[x.md >= "2026-08-26"]), ("oct6_onward", x[x.md >= "2026-10-06"]), ("all", x))
            for t, g in xx.groupby("first_tier")]
    return pd.DataFrame(rows)


# ───────────────────────────── run ─────────────────────────────

def run(v9: str, v11: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    d = attach_fair(load_live(v9))
    settled = d[d.settled]
    end = settled.md.max()
    v = d[d.signal_tier == "VALUABLE"]
    integ = {"live_first_sight_rows": int(len(d)), "settled": int(d.settled.sum()), "last_settled_match_date": str(end.date()),
             "snapshot_matched_ou25": round(float(d.loc[d.market == "over25", "snapshot_odds_match"].mean()), 3),
             "raw_edge_recomputed_matches_ledger_share": round(float((np.abs(d.loc[d.market == "over25", "recomputed_raw_edge"]
                                                                              - d.loc[d.market == "over25", "edge"]) < 0.15).mean()), 3),
             "tier_not_monotone_in_edge_examples": int(((d.signal_tier == "MARKSMAN") & (d.edge < d.effective_marksman_floor * 100)).sum()),
             "ou25_first_tier_recovered": round(float(d.loc[d.market == "over25", "first_tier"].notna().mean()), 3),
             "ou25_upgraded_after_first_sight_share": round(float(pd.Series(d.loc[(d.market == "over25") & d.first_tier.notna(),
                                                                       "upgraded_after_first_sight"]).astype(bool).mean()), 3)}

    summary = []
    for w, x in windows(d, end).items():
        for (t, m), g in x.groupby(["signal_tier", "market"]):
            summary.append({"window": w, "tier": t, "market": m, **summ(g, ci=True)})
        for t, g in x.groupby("signal_tier"):
            summary.append({"window": w, "tier": t, "market": "ALL (pooled, as owner audit)", **summ(g, ci=True)})
    summary = pd.DataFrame(summary)

    eb = pd.concat([edge_band_table(v, "edge", "raw_edge"), edge_band_table(d, "edge", "raw_edge_all_tiers").assign(scope="all tiers")])
    fb = edge_band_table(v[v.FAIR_EDGE_AVAILABLE == "YES"], "fair_edge", "fair_edge")
    cells = cell_table(d)
    tc = tier_comparison(d)
    drift = drift_explanation(d)
    mono = monotonicity(d)
    cal = calibration(d)
    dq = data_quality(d)
    oi = odds_interaction(d)
    sides = side_table(d)
    reg = regime_table(d, end)
    conc = {"last14": concentration(v[v.md > end - pd.Timedelta(days=14)]), "since_aug26": concentration(v[v.md >= "2026-08-26"])}
    wf = walk_forward(v)
    conv = v11_convergence(d, v11)
    upg = upgrade_table(d)
    ftc = first_tier_comparison(d)
    low, low_meta = snapshot_low_edge(v9)
    low_t = low_edge_table(low)
    # settlement integrity: snapshot-settled OVER/UNDER outcome vs live ledger WIN/LOSS on the same fixtures
    lo = d[(d.market == "over25") & d.settled].assign(md=lambda x: x.md.dt.normalize())
    chk = lo.merge(low[["league", "md", "home_team", "away_team", "side", "won"]].rename(columns={"won": "won_snap"}),
                   on=["league", "md", "home_team", "away_team", "side"], how="inner")
    low_meta["ledger_crosscheck_n"] = int(len(chk))
    low_meta["ledger_crosscheck_agree"] = round(float((chk.won == chk.won_snap).mean()), 3) if len(chk) else None

    # BTTS: production fixed-1.08 edge vs actual two-sided fair edge
    bt = d[(d.market == "btts") & d.fair_edge.notna()]
    btts_cmp = {"n": int(len(bt)), "actual_overround_mean": round(float(bt.btts_actual_overround.mean()), 4) if len(bt) else None,
                "production_edge_mean": round(float(bt.edge.mean()), 2) if len(bt) else None,
                "fair_edge_mean": round(float(bt.fair_edge.mean()), 2) if len(bt) else None}
    ou = d[(d.market == "over25") & d.fair_edge.notna()]
    ou_cmp = {"n": int(len(ou)), "overround_mean": round(float(ou.ou_overround.mean()), 4),
              "raw_edge_mean": round(float(ou.edge.mean()), 2), "fair_edge_mean": round(float(ou.fair_edge.mean()), 2),
              "fair_minus_raw_mean_pp": round(float((ou.fair_edge - ou.edge).mean()), 2)}

    # write
    files = {"valuable_summary.csv": summary, "valuable_edge_bands.csv": eb, "valuable_fair_edge_bands.csv": fb,
             "valuable_league_market.csv": cells[cells.tier == "VALUABLE"], "valuable_tier_comparison.csv": tc,
             "valuable_side.csv": sides, "valuable_odds_interaction.csv": oi, "valuable_v11_convergence.csv": conv,
             "valuable_regime_analysis.csv": reg, "valuable_all_cells.csv": cells, "valuable_drift_explanation.csv": drift,
             "valuable_monotonicity.csv": mono, "valuable_calibration.csv": cal, "valuable_data_quality.csv": dq,
             "valuable_walk_forward.csv": wf, "valuable_low_edge_snapshot.csv": low_t,
             "valuable_upgrade_effect.csv": upg, "valuable_first_sight_tiers.csv": ftc}
    for f, t in files.items():
        t.to_csv(OUT / f, index=False)
    res = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"), **FLAGS, "integrity": integ,
           "ou25_raw_vs_fair": ou_cmp, "btts_production_vs_fair": btts_cmp, "concentration": conc,
           "low_edge_snapshot_meta": low_meta}
    (OUT / "valuable_results.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return {"d": d, "files": files, "res": res}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--v9", required=True)
    ap.add_argument("--v11", required=True)
    a = ap.parse_args()
    out = run(a.v9, a.v11)
    print(json.dumps(out["res"], indent=1, default=str)[:6000])

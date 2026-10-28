"""Phase-2 orchestration: walk-forward arms -> identical-row evaluation -> outputs (see benchmark.py)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.standard_repair import forensic as F
from src.studies.standard_repair import identity as ID
from src.studies.standard_repair.benchmark import (BASE_MARKET, CONFIRM_START, EVAL_START, GROUPS, MARKETS, WF, _features, _metrics,
                                                   candidates, evaluate, frame_variant, market_table, rank_test, run_wf)
from src.studies.standard_repair.candidates import _pred, pen_logit
from src.studies.standard_repair.data import logit
from src.studies.standard_repair.evaluate import bh, ll, paired

WF_PLAN = {
    # name: (frame, recipe, side_scope, window, drop, targets)
    "LEGACY_V9_REPRO": ("legacy", "legacy_v9", "pooled", "all", "", "over25,btts,over15"),
    "LEGACY_ON_CANON": ("canonical", "legacy_v9", "pooled", "all", "", "over25,btts,over15"),
    "LEGACY_CANON_STD_SIDE": ("canonical", "legacy_v9", "standard", "all", "", "btts,over15"),
    "LEGACY_CANON_MKT_ASOF": ("asof", "legacy_v9", "pooled", "all", "", "over25"),
    "LEGACY_CANON_MKT_NONE": ("canonical", "legacy_v9", "pooled", "all", "bookmaker_overround", "over25"),
    "LEGACY_CANON_W_MODERN": ("canonical", "legacy_v9", "standard", "modern", "", "over25,btts"),
    "LEGACY_CANON_W_RECENT3": ("canonical", "legacy_v9", "standard", "recent3", "", "over25,btts"),
    "LEGACY_CANON_W_RECENT2": ("canonical", "legacy_v9", "standard", "recent2", "", "over25,btts"),
    "LEGACY_CANON_W_WEIGHTED": ("canonical", "legacy_v9", "standard", "weighted", "", "over25,btts"),
}
REPAIRED_RECIPE = os.getenv("V9_REPAIRED_RECIPE", "v9_repaired")
PAIRS = [("LEGACY_V9_REPRO", "LEGACY_ON_CANON", "identity repair"),
         ("LEGACY_ON_CANON", "V9_REPAIRED", "recipe repair"),
         ("LEGACY_V9_REPRO", "V9_REPAIRED", "full repair"),
         ("LEGACY_ON_CANON", "LEGACY_CANON_MKT_ASOF", "closing -> as-of market feature"),
         ("LEGACY_ON_CANON", "LEGACY_CANON_MKT_NONE", "drop market feature"),
         ("LEGACY_ON_CANON", "LEGACY_CANON_STD_SIDE", "pooled -> standard-only side model"),
         ("V9_REPAIRED_POOLED_SIDE", "V9_REPAIRED", "repaired: pooled -> standard-only side model"),
         ("V9_REPAIRED_MKT_CLOSING", "V9_REPAIRED", "repaired: closing-contaminated -> no market feature"),
         ("V9_REPAIRED_MKT_ASOF", "V9_REPAIRED", "repaired: true as-of market feature -> no market feature")]
PRO_ARMS = ["MKT_RESID_LR", "MKT_RESID_HGB", "BASE_RATE", "POISSON_FORM"]


def repaired_plan() -> dict:
    """V9_REPAIRED arms: R1's recipe (identity + canonical league-scoped features + persisted
    train-only imputer + four-block stacking + date-derived weights), frames built by frame_build.py
    inside R1's worktree. 7th element = R1 market-feature mode."""
    r = REPAIRED_RECIPE
    return {"V9_REPAIRED": ("repaired_none", r, "standard", "all", "", "over25,btts,over15", "none"),
            "V9_REPAIRED_POOLED_SIDE": ("repaired_none", r, "pooled", "all", "", "btts,over15", "none"),
            "V9_REPAIRED_MKT_ASOF": ("repaired_asof", r, "standard", "all", "", "over25", "asof"),
            "V9_REPAIRED_MKT_CLOSING": ("repaired_closing", r, "standard", "all", "", "over25", "closing"),
            "V9_REPAIRED_W_MODERN": ("repaired_none", r, "standard", "modern", "", "over25,btts", "none"),
            "V9_REPAIRED_W_RECENT2": ("repaired_none", r, "standard", "recent2", "", "over25,btts", "none")}


def _load_wf(name: str, amap: dict) -> pd.DataFrame | None:
    p = WF / f"{name}.parquet"
    if not p.exists():
        return None
    w = pd.read_parquet(p)
    w["date"] = pd.to_datetime(w["date"]).dt.normalize()
    w = ID.apply_aliases(w, amap)
    k = ["league", "date", "home_team", "away_team"]
    copies = int(w.duplicated(k).sum())
    w = w.drop_duplicates(k, keep="first").drop(columns=["block"], errors="ignore")
    w = w.rename(columns={"p_over25": f"{name}|OU25", "p_btts": f"{name}|BTTS", "p_over15": f"{name}|OU15"})
    w.attrs["alias_copies"] = copies
    return w


def _has_recipe() -> bool:
    try:
        v9 = Path(os.getenv("V9_REPAIRED_LOCAL") or os.getenv("V9_LOCAL") or cfg.V9_LOCAL)
        src = (v9 / "src" / "model.py").read_text(encoding="utf-8")
        return "recipe" in src and "def train(" in src
    except Exception:                                                            # noqa: BLE001
        return False


def build_dataset(skip_wf: bool = False, only: list[str] | None = None):
    dq = F.require_data_quality()
    fr, man = F.load_benchmark_frame()
    amap = json.loads(F.ALIASES.read_text(encoding="utf-8"))["map"]
    std = fr[fr["track"].astype(str) == "standard"].copy()
    std["date"] = pd.to_datetime(std["date"]).dt.normalize()
    mt = market_table(std, amap)
    k = ["league", "date", "home_team", "away_team"]
    d = _features(std.merge(mt, on=k, how="left"))
    for m, t in MARKETS.items():
        d[f"y_{m}"] = d[t].astype(float)
    d["week"] = d["date"].dt.strftime("%G-W%V")
    d["period"] = np.where(d["date"] >= pd.Timestamp(CONFIRM_START), "CONFIRMATION", "DISCOVERY")
    frames = {"legacy": F.LEGACY / "frame.parquet", "canonical": F.CANON / "frame.parquet"}
    plan = dict(WF_PLAN)
    if _has_recipe():
        plan.update(repaired_plan())
    if only:
        plan = {n: v for n, v in plan.items() if n in only}
    if not skip_wf:
        for name, spec in plan.items():
            fname, recipe, scope, window, drop, targets = spec[:6]
            pmode = spec[6] if len(spec) > 6 else "none"
            if fname.startswith("repaired_"):
                frame = F.REBUILD / fname / "frame.parquet"
                if not frame.exists():
                    raise F.IntegrityError(f"repaired frame {fname} missing - build it in the R1 worktree")
            else:
                frame = frames.get(fname) or frame_variant(frames["canonical"], fname, mt, mode=fname)
            run_wf(name, frame, recipe, scope, window, drop, targets, price_mode=pmode)
    copies = {}
    for name in list(WF_PLAN) + list(repaired_plan()):
        w = _load_wf(name, amap)
        if w is not None:
            copies[name] = w.attrs.get("alias_copies", 0)
            d = d.merge(w, on=k, how="left")
    return d, dq, man, mt, copies


def analyse(d: pd.DataFrame) -> dict:
    comp_all, lg_all, side_all, rank_all, extra, results = [], [], [], [], [], {}
    for m in MARKETS:
        pm = f"pm_{m}"
        cand = candidates(d, m)
        dm = d.join(cand)
        bm = BASE_MARKET.get(m, m)                     # BTTS_REAL scores the BTTS model predictions
        wf_cols = [c for c in dm.columns if c.endswith(f"|{bm}")]
        core = [c for c in (f"LEGACY_V9_REPRO|{bm}", f"LEGACY_ON_CANON|{bm}", f"V9_REPAIRED|{bm}") if c in dm.columns]
        E = dm[(dm["date"] >= pd.Timestamp(EVAL_START)) & dm[pm].notna() & dm[f"y_{m}"].notna()]
        E = E.dropna(subset=core + PRO_ARMS).copy()
        E = E.rename(columns={pm: "pm", f"y_{m}": "y", **{c: c.split("|")[0] for c in wf_cols}})
        arms = [c.split("|")[0] for c in wf_cols] + PRO_ARMS
        full = [a for a in arms if E[a].notna().all()]
        c, l, s = evaluate(E, full, m)
        comp_all += c
        lg_all += l
        side_all += s
        for a in full:
            if not a.startswith(("BASE", "POISSON")):
                rank_all += rank_test(E, a, m)
        for a in [x for x in arms if x not in full]:
            h = E[E[a].notna()]
            for period, P in (("ALL", h), ("CONFIRMATION", h[h["period"] == "CONFIRMATION"])):
                if len(P) >= 50:
                    comp_all.append({"market": m, "arm": a, "period": period, "scope": "OWN_ROWS",
                                     **_metrics(P[a], P["y"], P["pm"], P["week"])})
                    for lg, g in P.groupby("league"):
                        if len(g) >= 50:
                            lg_all.append({"market": m, "arm": a, "period": period, "league": lg, "scope": "OWN_ROWS",
                                           **_metrics(g[a], g["y"], g["pm"], g["week"])})
        pdl = {}
        for a, b, why in PAIRS:
            if a in E and b in E:
                h = E[[a, b, "league"]].dropna()
                if len(h):
                    dd = (h[b] - h[a]).abs()
                    pdl[f"{a}->{b}"] = {"what": why, "n": int(len(h)), "mean_abs_dp_pp": round(float(dd.mean()) * 100, 3),
                                        "p90_abs_dp_pp": round(float(dd.quantile(0.9)) * 100, 3),
                                        "share_gt_2pp": round(float((dd > 0.02).mean()), 4),
                                        "mean_signed_dp_pp": round(float((h[b] - h[a]).mean()) * 100, 3),
                                        "by_league_mean_abs_dp_pp": {lg: round(float(v) * 100, 3)
                                                                     for lg, v in dd.groupby(h["league"]).mean().items()}}
        results[m] = {"rows_identical": int(len(E)), "gameweeks": int(E["week"].nunique()), "arms_identical_rows": full,
                      "market_class": {"OU25": "GENUINE_PREMATCH_TWO_SIDED (FD_PREMATCH_APPROX)",
                                       "BTTS_REAL": "GENUINE_TWO_SIDED (" + "+".join(sorted(E["btts_price_class"].dropna().astype(str).unique())) + ")"}
                      .get(m, "SYNTHETIC_MARKET_PROXY"),
                      "rows_by_league": E["league"].value_counts().to_dict(),
                      "period_rows": E["period"].value_counts().to_dict(), "probability_deltas": pdl,
                      "date_range": [str(E["date"].min().date()), str(E["date"].max().date())]}
        if m in ("OU25", "BTTS", "BTTS_REAL"):
            for g in GROUPS:
                alt = candidates(d, m, groups=[x for x in GROUPS if x != g], arms=("MKT_RESID_LR",))["MKT_RESID_LR"]
                h = E.assign(alt=alt.reindex(E.index).to_numpy()).dropna(subset=["alt"])
                dll = ll(h["MKT_RESID_LR"], h["y"]) - ll(h["alt"], h["y"])
                pr = paired(dll, h["week"])
                extra.append({"study": "feature_group_ablation", "market": m, "variant": f"drop:{g}", "league": "ALL",
                              "n": int(len(h)), "dLL": pr["delta"], "ci95": pr["ci95"],
                              "note": "dLL = loss(full) - loss(without group); > 0 means the group HURTS",
                              "by_year": {int(k2): round(float(v), 5) for k2, v in pd.Series(dll).groupby(h["date"].dt.year.to_numpy()).mean().items()},
                              "leagues_where_group_helps": int((pd.Series(dll).groupby(h["league"].to_numpy()).mean() < 0).sum())})
            for win in ("modern", "recent3", "recent2", "weighted"):
                alt = candidates(d, m, window=win, arms=("MKT_RESID_LR",))["MKT_RESID_LR"]
                h = E.assign(alt=alt.reindex(E.index).to_numpy()).dropna(subset=["alt"])
                for lg, g in list(h.groupby("league")) + [("ALL", h)]:
                    pr = paired(ll(g["alt"], g["y"]) - ll(g["pm"], g["y"]), g["week"])
                    pf = paired(ll(g["MKT_RESID_LR"], g["y"]) - ll(g["pm"], g["y"]), g["week"])
                    extra.append({"study": "history_window", "market": m, "variant": f"MKT_RESID_LR:{win}", "league": lg,
                                  "n": int(len(g)), "dLL": pr["delta"], "ci95": pr["ci95"],
                                  "note": f"vs market; full-history residual {pf['delta']}"})
        # v9-recipe history windows (paired on own rows vs the same recipe's full history)
        for a in [x for x in E.columns if "_W_" in str(x)]:
            base = "V9_REPAIRED" if a.startswith("V9_REPAIRED") else "LEGACY_ON_CANON"
            base_alt = "LEGACY_CANON_STD_SIDE" if (base == "LEGACY_ON_CANON" and m != "OU25" and "LEGACY_CANON_STD_SIDE" in E) else base
            if base_alt not in E:
                continue
            h = E[[a, base_alt, "y", "week", "league", "pm"]].dropna()
            for lg, g in list(h.groupby("league")) + [("ALL", h)]:
                if len(g) < 50:
                    continue
                pr = paired(ll(g[a], g["y"]) - ll(g[base_alt], g["y"]), g["week"])
                extra.append({"study": "history_window", "market": m, "variant": a, "league": lg, "n": int(len(g)),
                              "dLL": pr["delta"], "ci95": pr["ci95"], "note": f"vs {base_alt} (full history)"})
        tgt = "V9_REPAIRED" if "V9_REPAIRED" in E else "LEGACY_ON_CANON"
        Dd, Cc = E[E["period"] == "DISCOVERY"], E[E["period"] == "CONFIRMATION"]
        if tgt in E and len(Dd) > 500 and len(Cc) > 100:
            bg = pen_logit(logit(Dd[tgt])[:, None], Dd["y"], n_free=1)
            lv = sorted(Dd["league"].unique())
            L = lambda z: np.column_stack([(z["league"] == x).to_numpy(float) for x in lv])
            bl = pen_logit(np.column_stack([logit(Dd[tgt]), L(Dd)]), Dd["y"], n_free=1, lam=0.05)
            for nm, p in (("raw", Cc[tgt].to_numpy()), ("global_platt", _pred(bg, logit(Cc[tgt])[:, None])),
                          ("league_shrunk_platt", _pred(bl, np.column_stack([logit(Cc[tgt]), L(Cc)])))):
                mm = _metrics(p, Cc["y"], Cc["pm"], Cc["week"])
                extra.append({"study": "calibration", "market": m, "variant": f"{tgt}:{nm}", "league": "ALL", "n": int(len(Cc)),
                              "dLL": mm["dLL_vs_market"], "ci95": mm["dLL_ci95"],
                              "note": f"fit on DISCOVERY, scored on CONFIRMATION; ece {mm.get('ece')} slope {mm.get('cal_slope')} LL {mm['log_loss']}"})
        E.to_parquet(F.REBUILD / f"eval_{m}.parquet", index=False)

    side = pd.DataFrame(side_all)
    fam = side[(side["period"] == "DISCOVERY") & (side["league"] != "ALL")
               & side["arm"].isin(["V9_REPAIRED", "MKT_RESID_LR", "MKT_RESID_HGB", "LEGACY_ON_CANON"])]
    q = bh({i: v for i, v in fam["dLL_p_one_sided"].items()})
    side["bh_q_discovery"] = [q.get(i) for i in side.index]
    conf = side[side["period"] == "CONFIRMATION"].set_index(["market", "arm", "league", "side"])
    calls = []
    for i, r in fam.iterrows():
        key = (r["market"], r["arm"], r["league"], r["side"])
        c = conf.loc[key] if key in conf.index else None
        disc_ok = q.get(i) is not None and q[i] <= 0.10 and r["dLL_vs_market"] < 0
        conf_ok = c is not None and c["dLL_vs_market"] < 0 and (c["dLL_p_one_sided"] if c["dLL_p_one_sided"] is not None else 1) < 0.05
        calls.append({"market": r["market"], "arm": r["arm"], "league": r["league"], "side": r["side"],
                      "disc_n": int(r["n"]), "disc_gameweeks": int(r["gameweeks"]), "disc_dLL": r["dLL_vs_market"],
                      "disc_p": r["dLL_p_one_sided"], "disc_bh_q": q.get(i),
                      "conf_n": None if c is None else int(c["n"]), "conf_gameweeks": None if c is None else int(c["gameweeks"]),
                      "conf_dLL": None if c is None else c["dLL_vs_market"], "conf_ci95": None if c is None else c["dLL_ci95"],
                      "conf_p": None if c is None else c["dLL_p_one_sided"],
                      "status": ("CONFIRMED" if disc_ok and conf_ok else "DISCOVERY_ONLY" if disc_ok
                                 else "CONFIRMATION_ONLY" if conf_ok else "NO_SIGNAL")})
    return {"comp": pd.DataFrame(comp_all), "lg": pd.DataFrame(lg_all), "side": side, "rank": pd.DataFrame(rank_all),
            "extra": pd.DataFrame(extra), "calls": pd.DataFrame(calls), "results": results}

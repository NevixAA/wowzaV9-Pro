"""Wowza edge reassessment (owner brief 2026-10-20): where does evidence exist, and where can the system simply
not observe the counterfactual?

    python -m src.studies.edge_reassessment --v9 <wowza-betting clone>
        -> output/edge_reassessment/*.csv|json  +  registry/candidate_forward_tests.json (first run only)

The live ledger is selection-censored: it holds only fixtures that cleared the production gate, so it can say
what happens if a gate is RAISED but not what happens if it is LOWERED. This study evaluates gates on the
ALL-FIXTURE record instead:

  ALL_FIXTURE  every fixture v9 priced, from its committed predictions.csv snapshots (2026-08-15 ->), first sight
               per fixture x market with a valid price, settled from Pro team_match_stats via v9's league-scoped
               resolver (validated 100% against the ledger's own results). Close = the LAST committed snapshot
               strictly before kickoff, accepted only within CLOSE_MAX_GAP_H of kickoff, else NaN (never an early
               price relabelled as the close).
  V91_SHADOW   v9 output/v91_shadow.csv (OU25, from 2026-10-04) once settled - an independent capture, used as a
               cross-check, never pooled with ALL_FIXTURE.
  LIVE         v9 ledgers (first sight) for live ROI/CLV of tips that were actually sent.

No production behaviour changes: no threshold, stake, routing, champion or selection rule is touched.
Status vocabulary for forward tests: DISCOVERY, REGISTERED, ACCRUING, INSUFFICIENT, REJECTED, FORWARD_SUPPORTED.
CONFIRMED can only be assigned by a separate preregistered prospective evaluator - never here.
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from config import pro_config as cfg

OUT = cfg.BASE_DIR / "output" / "edge_reassessment"
EXP = cfg.BASE_DIR / "experiments" / "valuable_2026_10"
REG = cfg.BASE_DIR / "registry" / "candidate_forward_tests.json"
FORWARD_START = pd.Timestamp("2026-10-21T00:00:00Z")
SIDE_OVERROUND = 1.08
CLOSE_MAX_GAP_H = 6.0
ODDS_BANDS = [(0, 1.80, "<1.80"), (1.80, 2.00, "1.80-2.00"), (2.00, 2.50, "2.00-2.50"), (2.50, 3.00, "2.50-3.00"),
              (3.00, 99, ">3.00")]
rng = np.random.default_rng(20261020)
EPS = 1e-6


# ───────────────────────────── data ─────────────────────────────

def _resolver(v9: str):
    spec = importlib.util.spec_from_file_location("v9_team_names", Path(v9) / "src" / "team_names.py")
    tn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tn)
    return tn.resolve


def _results() -> pd.DataFrame:
    fs = sorted(glob.glob(str(cfg.BASE_DIR / "data" / "season_2026_27" / "team_match_stats" / "**" / "*.parquet"), recursive=True))
    r = pd.concat([pd.read_parquet(f, columns=["league", "match_date", "home_team", "away_team", "home_goals", "away_goals"])
                   for f in fs], ignore_index=True).dropna(subset=["home_goals", "away_goals"])
    r = r.drop_duplicates(["league", "match_date", "home_team", "away_team"], keep="last")
    r["md"] = pd.to_datetime(r["match_date"]).dt.normalize()
    return r


def all_fixture(v9: str) -> pd.DataFrame:
    """One row per fixture x market x (chosen) side at first sight, settled, with a strict pre-kickoff close."""
    s = pd.read_parquet(EXP / "prematch_snapshots.parquet")
    s["gen"] = pd.to_datetime(s["generated_at"], utc=True)
    s["kick"] = pd.to_datetime(s["kickoff_utc"], utc=True, errors="coerce")
    s = s[s["kick"].notna() & (s["gen"] < s["kick"])].sort_values("gen")
    s["fx"] = s["league"] + "|" + s["date"].astype(str).str[:10] + "|" + s["home_team"] + "|" + s["away_team"]
    resolve, res = _resolver(v9), _results()
    goals = {}
    for lg, g in s.drop_duplicates("fx").groupby("league"):
        rl = res[res.league == lg]
        names = sorted(set(rl.home_team) | set(rl.away_team))
        for row in g.itertuples():
            h, a = resolve(row.home_team, names), resolve(row.away_team, names)
            if not h or not a:
                continue
            md = pd.Timestamp(str(row.date)[:10])
            m = rl[(rl.home_team == h) & (rl.away_team == a) & ((rl.md - md).abs() <= pd.Timedelta(days=1))]
            if len(m) == 1:
                goals[row.fx] = (float(m.home_goals.iloc[0]), float(m.away_goals.iloc[0]))
    rows = []
    specs = [("ou25", "OVER", "p_over25", "odds_over25", "odds_under25", False),
             ("ou25", "UNDER", "p_over25", "odds_under25", "odds_over25", True),
             ("btts", "YES", "p_btts", "odds_btts", "odds_btts_no", False),
             ("over15", "OVER", "p_over15", "odds_over15", None, False),
             ("over35", "OVER", "p_over35", "odds_over35", None, False)]
    for mkt, side, pc, oc, opc, flip in specs:
        x = s.dropna(subset=[pc, oc])
        x = x[x[oc] > 1]
        p = (1 - x[pc]) if flip else x[pc]
        imp = 1 / x[oc]
        raw = (p - imp) if mkt == "ou25" else (p - imp / SIDE_OVERROUND)
        opp = x[opc].where(x[opc] > 1) if opc else pd.Series(np.nan, index=x.index)
        fair = imp / (imp + 1 / opp)
        tier = (x["tier_under"] if flip else x["tier_over"]) if mkt == "ou25" else pd.Series(
            np.select([raw >= 0.10, raw >= 0.08, raw >= 0.04], ["SNIPER", "MARKSMAN", "VALUABLE"], "AVOID"), index=x.index)
        rows.append(pd.DataFrame({"fx": x.fx, "league": x.league, "model_type": x.model_type, "market": mkt, "side": side,
                                  "gen": x.gen, "kick": x.kick, "p_model": p, "odds": x[oc], "opp_odds": opp,
                                  "p_market_fair": np.where(flip, fair, fair) if opc else np.nan,
                                  "raw_edge": raw, "fair_edge": p - fair, "prod_tier": tier.astype(str).str.upper()
                                  .replace({"VALUE": "VALUABLE", "NAN": "AVOID"}),
                                  "drift_signal": x.get("drift_signal"), "snapshot_sha": x.snapshot_sha}))
    c = pd.concat(rows, ignore_index=True)
    # close = last committed snapshot price strictly pre-kickoff, within CLOSE_MAX_GAP_H, same fixture/market/side
    last = c.sort_values("gen").drop_duplicates(["fx", "market", "side"], keep="last")
    last = last.assign(gap_h=(last.kick - last.gen).dt.total_seconds() / 3600)[["fx", "market", "side", "odds", "gap_h", "gen"]]
    last = last.rename(columns={"odds": "close_odds", "gen": "close_at"})
    first = c.sort_values("gen").drop_duplicates(["fx", "market", "side"], keep="first")
    f = first.merge(last, on=["fx", "market", "side"], how="left")
    f["close_status"] = np.where(f.close_at <= f.gen, "ONLY_ONE_OBSERVATION",
                                 np.where(f.gap_h <= CLOSE_MAX_GAP_H, "VALID_PRE_KICKOFF_CLOSE", "NO_CLOSE_NEAR_KICKOFF"))
    ok = f.close_status == "VALID_PRE_KICKOFF_CLOSE"
    f["close_odds"] = f["close_odds"].where(ok)
    f["clv"] = (f["odds"] / f["close_odds"] - 1) * 100
    # OU25: keep only the side v9 itself would pick (larger raw edge), as production does
    ou = f[f.market == "ou25"].sort_values("raw_edge", ascending=False).drop_duplicates("fx", keep="first")
    f = pd.concat([ou, f[f.market != "ou25"]], ignore_index=True)
    g = f["fx"].map(goals)
    f = f[g.notna()].copy()
    hg, ag = zip(*f["fx"].map(goals))
    hg, ag = np.array(hg), np.array(ag)
    hit = np.select([f.market == "ou25", f.market == "over15", f.market == "over35", f.market == "btts"],
                    [hg + ag > 2.5, hg + ag > 1.5, hg + ag > 3.5, (hg > 0) & (ag > 0)])
    f["outcome_yes"] = hit.astype(float)                                 # the market's "Over/Yes" happened
    f["won"] = np.where(f.side.isin(["OVER", "YES"]), hit, ~hit.astype(bool)).astype(float)
    f["pnl"] = np.where(f.won == 1, f.odds - 1, -1.0)
    f["md"] = f["kick"].dt.tz_convert(None).dt.normalize()
    f["hours_before"] = (f.kick - f.gen).dt.total_seconds() / 3600
    f["source"] = "ALL_FIXTURE"
    return f


# ───────────────────────────── metrics ─────────────────────────────

def _boot(v: np.ndarray, days: np.ndarray, n=2000, q=(2.5, 97.5)):
    if len(v) < 5:
        return (np.nan, np.nan)
    u = np.unique(days)
    idx = {k: np.where(days == k)[0] for k in u}
    b = [v[np.concatenate([idx[k] for k in rng.choice(u, len(u))])].mean() for _ in range(n)]
    return tuple(np.round(np.percentile(b, q) * 100, 1))


def metrics(x: pd.DataFrame) -> dict:
    n = len(x)
    if not n:
        return {"n": 0}
    x = x.sort_values("kick")
    x = x[pd.to_numeric(x.odds, errors="coerce") > 1]
    n = len(x)
    if not n:
        return {"n": 0}
    pnl, won, odds = x.pnl.values.astype(float), x.won.values.astype(float), x.odds.values.astype(float)
    cum = np.cumsum(pnl)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum]))
    run = best = 0
    for w in won:
        run = run + 1 if w == 0 else 0
        best = max(best, run)
    lo, hi = _boot(pnl, x.md.values)
    clv = pd.to_numeric(x.get("clv"), errors="coerce") if "clv" in x else pd.Series(dtype=float)
    month = x.groupby(x.md.dt.to_period("M")).pnl.sum()
    tot = pnl.sum()
    ob = x.odds.astype(float).map(lambda o: next(l for a, b, l in ODDS_BANDS if a <= o < b))
    top5 = np.sort(pnl)[::-1][5:] if n > 5 else np.array([])
    return {"n": n, "matchdays": int(x.md.nunique()), "wins": int(won.sum()), "hit_pct": round(won.mean() * 100, 1),
            "mean_odds": round(odds.mean(), 3), "breakeven_hit_pct": round((1 / odds).mean() * 100, 1),
            "excess_hit_pp": round((won.mean() - (1 / odds).mean()) * 100, 1), "pnl": round(tot, 2),
            "roi_pct": round(pnl.mean() * 100, 1), "roi_ci95_lo": lo, "roi_ci95_hi": hi,
            "p_one_sided": float(stats.ttest_1samp(pnl, 0, alternative="greater").pvalue) if n >= 5 and pnl.std() > 0 else np.nan,
            "max_drawdown_u": round(dd, 2), "longest_losing_run": int(best),
            "close_coverage_pct": round(float(clv.notna().mean() * 100), 1) if len(clv) else 0.0,
            "clv_mean": round(float(clv.mean()), 2) if clv.notna().any() else np.nan,
            "clv_median": round(float(clv.median()), 2) if clv.notna().any() else np.nan,
            "clv_pos_pct": round(float((clv > 0).mean() * 100), 1) if clv.notna().any() else np.nan,
            "roi_ex_top5_winners_pct": round(top5.mean() * 100, 1) if len(top5) else np.nan,
            "largest_month_share": round(float(month.max() / tot), 2) if tot > 0 else np.nan,
            "side_concentration": _top_share(x.side), "odds_band_concentration": _top_share(ob)}


def _top_share(s: pd.Series) -> float:
    v = s.dropna().value_counts(normalize=True)
    return round(float(v.iloc[0]), 2) if len(v) else np.nan


def bh(p: pd.Series) -> pd.Series:
    p = pd.to_numeric(p, errors="coerce")
    ok = p.notna()
    q = pd.Series(np.nan, index=p.index)
    if ok.sum():
        v = p[ok].values
        o = np.argsort(v)
        qq = v[o] * len(v) / (np.arange(len(v)) + 1)
        qq = np.minimum.accumulate(qq[::-1])[::-1]
        out = np.empty(len(v))
        out[o] = np.minimum(qq, 1)
        q[ok] = out
    return q


# ───────────────────────────── forward-test registry ─────────────────────────────

def build_registry(v9: str) -> dict:
    """Freeze candidate forward tests from v9's gate registry (CANDIDATE cells). Written ONCE; never re-tuned."""
    if REG.exists():
        return json.loads(REG.read_text(encoding="utf-8"))
    g = json.loads((Path(v9) / "output" / "league_market_gate_registry.json").read_text(encoding="utf-8"))
    hyps = []
    for c in g["cells"]:
        if c.get("evidence_grade") != "CANDIDATE":
            continue
        mkt = {"ou25": "ou25", "btts": "btts", "over15": "over15", "over35": "over35"}.get(c["market"], c["market"])
        hyps.append({
            "id": f"H-GATE-{len(hyps) + 1:02d}", "league": c["league"], "market": mkt, "model_type": c["model_type"],
            "production_gates": {k: c.get(f"production_{k}") for k in ("valuable", "marksman", "sniper")},
            "candidate_gate": c.get("candidate_sniper") if c.get("candidate_sniper") is not None else c.get("candidate_marksman"), "edge_definition": "production raw edge (OU25 p-1/odds; side p-(1/odds)/1.08) on the side v9 picks",
            "discovery_date": g["generated_at_utc"][:10], "discovery_hypotheses_examined": g.get("hypotheses_examined"),
            "historical": {"fit_roi": c.get("fit_roi"), "fit_n": c.get("fit_n"), "validation_roi": c.get("roi_validation"),
                           "validation_n": c.get("validation_n"), "holdout_roi": c.get("roi_holdout"), "holdout_n": c.get("holdout_n"),
                           "windows": c.get("windows")},
            "forward_start": str(FORWARD_START), "min_forward_n": 100 if mkt == "ou25" else 80, "required_matchdays": 10,
            "statistical_test": "flat 1u ROI, 95% matchday block bootstrap; one-sided t for BH",
            "multiple_comparison_family": "H-GATE-* (all candidates in this registry), Benjamini-Hochberg q<=0.10",
            "pass_criterion": "n>=min_forward_n AND matchdays>=10 AND ROI 95% CI lower > 0 AND BH q<=0.10 AND (CLV mean>=0 where close coverage>=50%) -> FORWARD_SUPPORTED",
            "fail_criterion": "n>=min_forward_n AND ROI 95% CI upper < 0 -> REJECTED; or n>=2*min_forward_n AND ROI<=0 -> REJECTED",
            "status": "REGISTERED" if (c.get("candidate_sniper") is not None or c.get("candidate_marksman") is not None)
                      else "DISCOVERY (source registry gives no candidate gate - nothing to test)",
            "production_behaviour": "UNCHANGED - this is a forward test on the all-fixture shadow, never a live gate"})
    reg = {"registry": "candidate_forward_tests", "version": 1, "registered_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": "v9 output/league_market_gate_registry.json CANDIDATE cells (generated " + g["generated_at_utc"][:10] + ")",
           "caveats": ["candidate gates are the best point of each cell's own fit curve after examining "
                       f"{g.get('hypotheses_examined')} hypotheses - heavy selection",
                       "new_format OU25 historical prices are best-of-books (11% of rows with two-way margin < 0) - historical ROI inflated",
                       "rows between discovery and forward_start are reported as POST_DISCOVERY and never count toward a pass"],
           "confirmed_assignable_here": False, "hypotheses": hyps}
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(reg, indent=1, default=str), encoding="utf-8")
    return reg


def evaluate_registry(reg: dict, af: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for h in reg["hypotheses"]:
        if h["candidate_gate"] is None:
            rows.append({"id": h["id"], "league": h["league"], "market": h["market"], "model_type": h["model_type"],
                         "window": "FORWARD", "n": 0, "note": "no candidate gate"})
            continue
        x = af[(af.league == h["league"]) & (af.market == h["market"]) & (af.model_type == h["model_type"])
               & (af.raw_edge >= float(h["candidate_gate"]))]
        disc = pd.Timestamp(h["discovery_date"], tz="UTC")
        for win, w in (("POST_DISCOVERY (not counted)", x[(x.gen >= disc) & (x.gen < FORWARD_START)]),
                       ("FORWARD", x[x.gen >= FORWARD_START])):
            m = metrics(w)
            rows.append({"id": h["id"], "league": h["league"], "market": h["market"], "model_type": h["model_type"],
                         "candidate_gate": h["candidate_gate"], "production_sniper": h["production_gates"]["sniper"],
                         "hist_fit_roi": h["historical"]["fit_roi"], "hist_val_roi": h["historical"]["validation_roi"],
                         "hist_holdout_roi": h["historical"]["holdout_roi"], "window": win, **m})
    t = pd.DataFrame(rows)
    fw = t.window == "FORWARD"
    t.loc[fw, "q_BH"] = bh(t.loc[fw, "p_one_sided"]).values
    def status(r):
        if r.window != "FORWARD":
            return "POST_DISCOVERY_ONLY"
        h = next(h for h in reg["hypotheses"] if h["id"] == r.id)
        if h["candidate_gate"] is None:
            return "DISCOVERY"
        if r.n == 0:
            return "REGISTERED"
        if r.n >= 2 * h["min_forward_n"] and r.roi_pct <= 0:
            return "REJECTED"
        if r.n >= h["min_forward_n"] and r.roi_ci95_hi < 0:
            return "REJECTED"
        if (r.n >= h["min_forward_n"] and r.matchdays >= h["required_matchdays"] and r.roi_ci95_lo > 0
                and (r.q_BH or 1) <= 0.10):
            return "FORWARD_SUPPORTED"
        return "ACCRUING"
    t["status"] = t.apply(status, axis=1)
    return t


# ───────────────────────────── analyses ─────────────────────────────

def ou25_breakdowns(af: pd.DataFrame, champion_since: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    ou = af[af.market == "ou25"].copy()
    ou["odds_band"] = ou.odds.map(lambda o: next(l for a, b, l in ODDS_BANDS if a <= o < b))
    ou["entry"] = pd.cut(ou.hours_before, [0, 6, 24, 48, 96, 1e9], labels=["<6h", "6-24h", "24-48h", "48-96h", "96h+"])
    end = ou.kick.max()
    rows, mono = [], []
    for mt, g in ou.groupby("model_type"):
        g = g.copy()
        g["edge_decile"] = pd.qcut(g.raw_edge.rank(method="first"), 10, labels=[f"D{i}" for i in range(1, 11)])
        bet = g[g.raw_edge >= 0]                                          # every positive-edge candidate
        wins = {"last7": bet[bet.kick > end - pd.Timedelta(days=7)], "last14": bet[bet.kick > end - pd.Timedelta(days=14)],
                "last30": bet[bet.kick > end - pd.Timedelta(days=30)], "since_champion_2026-10-18": bet[bet.gen >= champion_since],
                "since_regime_2026-08-21": bet[bet.gen >= pd.Timestamp("2026-08-21", tz="UTC")],
                "post_registration_2026-10-21": bet[bet.gen >= FORWARD_START], "all_snapshot_history": bet}
        for w, x in wins.items():
            rows.append({"model_type": mt, "dimension": "window", "value": w, **metrics(x)})
        for dim in ("league", "side", "odds_band", "prod_tier", "entry", "drift_signal"):
            for v, x in bet.groupby(dim, observed=True):
                rows.append({"model_type": mt, "dimension": dim, "value": str(v), **metrics(x)})
        for v, x in g.groupby("edge_decile", observed=True):
            rows.append({"model_type": mt, "dimension": "edge_decile (all candidates incl. negative edge)",
                         "value": f"{v} [{x.raw_edge.min()*100:.1f},{x.raw_edge.max()*100:.1f}]%", **metrics(x)})
        rho, p = stats.spearmanr(g.raw_edge, g.pnl)
        rho2, p2 = stats.spearmanr(g.raw_edge, g.won - 1 / g.odds)
        dec = g.groupby("edge_decile", observed=True).pnl.mean().values
        rho3, _ = stats.spearmanr(np.arange(len(dec)), dec)
        mono.append({"model_type": mt, "market": "ou25", "n": len(g), "spearman_edge_pnl": round(float(rho), 3), "p": round(float(p), 4),
                     "spearman_edge_excess_hit": round(float(rho2), 3), "p_excess": round(float(p2), 4),
                     "decile_roi_rank_corr": round(float(rho3), 3),
                     "label": "EDGE_NOT_RANKING_OUTCOMES" if (p > 0.05 or rho <= 0) else "EDGE_RANKS_OUTCOMES"})
    return pd.DataFrame(rows), pd.DataFrame(mono)


def odds_band_table(af: pd.DataFrame) -> pd.DataFrame:
    x = af[af.raw_edge >= 0].copy()
    x["odds_band"] = x.odds.map(lambda o: next(l for a, b, l in ODDS_BANDS if a <= o < b))
    rows = [{"model_type": mt, "market": m, "odds_band": b, **metrics(g)}
            for (mt, m, b), g in x.groupby(["model_type", "market", "odds_band"])]
    t = pd.DataFrame(rows)
    t["q_BH_across_cells"] = bh(t.p_one_sided)
    return t


def tier_table(af: pd.DataFrame, live: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for src, d in (("ALL_FIXTURE first-sight production tier", af), ("LIVE ledger tier (max reached, upgraded in place)", live)):
        for (mt, m, t), g in d[d.prod_tier.isin(["VALUABLE", "MARKSMAN", "SNIPER"])].groupby(["model_type", "market", "prod_tier"]):
            r = metrics(g)
            r["calibration_err_pp"] = round(float((g.p_model.mean() - g.won.mean()) * 100), 1) if "p_model" in g and g.p_model.notna().any() else np.nan
            rows.append({"source": src, "model_type": mt, "market": m, "tier": t, **r})
    t = pd.DataFrame(rows)
    order = {"VALUABLE": 1, "MARKSMAN": 2, "SNIPER": 3}
    verdict = []
    for (s, mt, m), g in t.groupby(["source", "model_type", "market"]):
        g = g.set_index("tier")
        if {"MARKSMAN", "SNIPER"} <= set(g.index):
            verdict.append({"source": s, "model_type": mt, "market": m,
                            "sniper_beats_marksman_roi": bool(g.at["SNIPER", "roi_pct"] > g.at["MARKSMAN", "roi_pct"]),
                            "ordering_by_roi": " > ".join(g.sort_values("roi_pct", ascending=False).index)})
    return t, pd.DataFrame(verdict)


class _Fit:
    def __init__(self, params, llf):
        self.params, self.llf = params, llf


def _logit(X: np.ndarray, y: np.ndarray) -> _Fit:
    """Maximum-likelihood logistic regression with an intercept (scipy; no statsmodels dependency)."""
    from scipy.optimize import minimize
    Xc = np.c_[np.ones(len(X)), X]
    nll = lambda b: -np.sum(y * (Xc @ b) - np.logaddexp(0, Xc @ b))
    r = minimize(nll, np.zeros(Xc.shape[1]), method="BFGS")
    return _Fit(r.x, -r.fun)


def model_vs_market(af: pd.DataFrame) -> pd.DataFrame:
    """Does Wowza know something the (de-vigged) price does not? Scored on the market's YES/OVER outcome."""
    from sklearn.metrics import roc_auc_score
    rows = []
    for (mt, m), g in af[af.p_market_fair.notna()].groupby(["model_type", "market"]):
        # on OU25 rows the chosen side may be UNDER: express everything as P(over / yes)
        pm = np.where(g.side.isin(["UNDER", "NO"]), 1 - g.p_model, g.p_model).clip(EPS, 1 - EPS)
        pk = np.where(g.side.isin(["UNDER", "NO"]), 1 - g.p_market_fair, g.p_market_fair).clip(EPS, 1 - EPS)
        y = g.outcome_yes.values
        if len(g) < 50 or y.min() == y.max():
            continue
        ll = lambda p: -(y * np.log(p) + (1 - y) * np.log(1 - p))
        br_m, br_k = (pm - y) ** 2, (pk - y) ** 2
        d = br_m - br_k
        lo, hi = _boot(d, g.md.values)
        lm, lk = np.log(pm / (1 - pm)), np.log(pk / (1 - pk))
        base, full, cal = _logit(np.c_[lk], y), _logit(np.c_[lk, lm], y), _logit(np.c_[lm], y)
        lr = 2 * (full.llf - base.llf)
        rows.append({"model_type": mt, "market": m, "n": len(g),
                     "logloss_model": round(float(ll(pm).mean()), 5), "logloss_market": round(float(ll(pk).mean()), 5),
                     "brier_model": round(float(br_m.mean()), 5), "brier_market": round(float(br_k.mean()), 5),
                     "paired_brier_diff_model_minus_market": round(float(d.mean()), 5),
                     "paired_brier_ci95": f"[{lo/100:.5f}, {hi/100:.5f}]",
                     "auc_model": round(float(roc_auc_score(y, pm)), 3), "auc_market": round(float(roc_auc_score(y, pk)), 3),
                     "model_calibration_slope": round(float(cal.params[1]), 3), "model_calibration_intercept": round(float(cal.params[0]), 3),
                     "residual_coef_model_given_market": round(float(full.params[2]), 3),
                     "residual_LR_p": round(float(stats.chi2.sf(lr, 1)), 4),
                     "verdict": ("MODEL_ADDS_INFORMATION" if stats.chi2.sf(lr, 1) < 0.05 and full.params[2] > 0
                                 else "MARKET_SUFFICIENT")})
    return pd.DataFrame(rows)


def btts_prereg(v9: str, af: pd.DataFrame) -> list[dict]:
    """Progress only for the frozen H-BTTS-01..04 family - definitions untouched."""
    reg = json.loads((Path(v9) / "registry" / "preregistered_hypotheses.json").read_text(encoding="utf-8"))
    hs = {h["id"]: h for h in reg["hypotheses"]}
    s = pd.read_csv(Path(v9) / "output" / "side_bets_ledger.csv", low_memory=False)
    s = s[(s.source == "live") & (s.market == "btts")].copy()
    s["gen"] = pd.to_datetime(s.generated_at, errors="coerce")
    s = s.sort_values("gen").drop_duplicates(["match_date", "home_team", "away_team"])
    s = s[s.signal_tier.isin(["SNIPER", "MARKSMAN"]) & s.result.isin(["WIN", "LOSS"])
          & (pd.to_datetime(s.match_date) >= "2026-10-02")].copy()
    s["md"] = pd.to_datetime(s.match_date)
    s["kick"] = s["md"]
    s["won"] = (s.result == "WIN").astype(float)
    s["pnl"] = s.pnl.astype(float)
    s["odds"] = s.odds.astype(float)
    s["side"] = "YES"
    out = []

    def boot10(pnl):                                                    # the registered test: 10,000 resamples, block 10
        if len(pnl) < 10:
            return (np.nan, np.nan)
        nb = int(np.ceil(len(pnl) / 10))
        starts = np.arange(0, len(pnl) - 9)
        b = [np.concatenate([pnl[k:k + 10] for k in rng.choice(starts, nb)])[:len(pnl)].mean() for _ in range(10000)]
        return tuple(np.round(np.percentile(b, [2.5, 97.5]) * 100, 1))

    arg = s[s.league == "Argentina Primera Division"].sort_values("md")
    ex = s[s.league != "Argentina Primera Division"].sort_values("md")
    for hid, x in (("H-BTTS-01", arg), ("H-BTTS-02", ex)):
        lo, hi = boot10(x.pnl.values)
        out.append({"id": hid, "title": hs[hid]["title"], "n_post_registration": len(x), "n_min": hs[hid]["n_min"],
                    "roi_pct": round(float(x.pnl.mean() * 100), 1) if len(x) else None, "ci95_block10": [lo, hi],
                    "progress_pct": round(100 * len(x) / hs[hid]["n_min"], 1), "status": "ACCRUING (definition unchanged)"})
    # H-BTTS-03 consensus CLV needs >=3 two-sided books per close: report the available proxy honestly
    clv = pd.to_numeric(arg.clv_pct, errors="coerce")
    out.append({"id": "H-BTTS-03", "title": hs["H-BTTS-03"]["title"], "n_post_registration": len(arg),
                "single_book_clv_mean_pct": round(float(clv.mean()), 2) if clv.notna().any() else None,
                "status": "NOT_EVALUABLE_HERE - the registered metric is consensus_clv (>=3 two-sided books); the ledger CLV is single-book and is shown only as context"})
    # H-BTTS-04: model vs de-vigged market at entry, on the staked Argentina bets, via the same-run snapshot price
    a = af[(af.market == "btts") & (af.league == "Argentina Primera Division") & (af.prod_tier.isin(["SNIPER", "MARKSMAN"]))
           & (af.gen >= pd.Timestamp("2026-10-02", tz="UTC")) & af.p_market_fair.notna()]
    if len(a):
        out.append({"id": "H-BTTS-04", "title": hs["H-BTTS-04"]["title"], "n": len(a),
                    "brier_model": round(float(((a.p_model - a.won) ** 2).mean()), 4),
                    "brier_market_devig": round(float(((a.p_market_fair - a.won) ** 2).mean()), 4),
                    "status": "ACCRUING (definition unchanged; all-fixture snapshot rows = staked-tier proxy)"})
    return out


def over15_certification(v9: str, af: pd.DataFrame) -> dict:
    """Old O1.5 backtests used filled/default prices -> INVALID. Re-certify from genuinely observed prices only."""
    bt = pd.read_csv(Path(v9) / "output" / "backtest_results_over15.csv", low_memory=False, usecols=lambda c: c in ("odds_over15", "date"))
    v = bt.odds_over15.dropna()
    top = v.round(3).value_counts(normalize=True).head(3)
    live = af[(af.market == "over15") & (af.raw_edge >= 0)]
    s = pd.read_csv(Path(v9) / "output" / "side_bets_ledger.csv", low_memory=False)
    s = s[(s.source == "live") & (s.market == "over15") & s.result.isin(["WIN", "LOSS"])]
    return {"historical_backtest": "INVALID - contains filled/default prices (src/data_loader.py:542/587 fill paths); not quoted",
            "backtest_top_price_shares": {str(k): round(float(x), 3) for k, x in top.items()},
            "genuine_snapshot_prices": {mt: metrics(g) for mt, g in live.groupby("model_type")},
            "live_ledger": {"n": int(len(s)), "roi_pct": round(float(s.pnl.astype(float).mean() * 100), 1) if len(s) else None,
                            "note": "live prices are captured quotes; small n"},
            "fair_edge_available": "NO (no Under 1.5 price captured)"}


def v91_crosscheck(v9: str) -> dict:
    p = Path(v9) / "output" / "v91_shadow.csv"
    s = pd.read_csv(p, low_memory=False)
    settled = s.result.isin(["WIN", "LOSS"])
    out = {"rows": int(len(s)), "settled": int(settled.sum())}
    if settled.sum() >= 30:
        x = s[settled].copy()
        x["won"] = (x.result == "WIN").astype(float)
        x["pnl"] = np.where(x.won == 1, x.entry_odds.astype(float) - 1, -1.0)
        x["md"] = pd.to_datetime(x.match_date)
        x["kick"] = pd.to_datetime(x.kickoff_utc)
        x["odds"] = x.entry_odds.astype(float)
        x["side"] = x.v9_side
        for mt, g in x.groupby("model_type"):
            pos = g[g.v9_edge.astype(float) >= 0]
            out[mt] = {"all_positive_edge": metrics(pos)}
            if len(pos) >= 30:
                rho, pv = stats.spearmanr(pos.v9_edge.astype(float), pos.pnl)
                out[mt]["spearman_edge_pnl"] = [round(float(rho), 3), round(float(pv), 4)]
    return out


def run(v9: str) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    af = all_fixture(v9)
    af.to_parquet(EXP / "all_fixture_settled.parquet", index=False)
    reg = build_registry(v9)
    cand = evaluate_registry(reg, af)
    champ = pd.Timestamp("2026-10-18T08:04:23Z")
    ou_b, mono = ou25_breakdowns(af, champ)
    # BTTS / O1.5 monotonicity on the all-fixture record too
    for (mt, m), g in af[af.market != "ou25"].groupby(["model_type", "market"]):
        if len(g) >= 50:
            rho, p = stats.spearmanr(g.raw_edge, g.pnl)
            mono = pd.concat([mono, pd.DataFrame([{"model_type": mt, "market": m, "n": len(g), "spearman_edge_pnl": round(float(rho), 3),
                                                   "p": round(float(p), 4),
                                                   "label": "EDGE_NOT_RANKING_OUTCOMES" if (p > 0.05 or rho <= 0) else "EDGE_RANKS_OUTCOMES"}])])
    ob = odds_band_table(af)
    sys_live = __import__("src.studies.valuable.deep_dive", fromlist=["x"])
    live = sys_live.attach_fair(sys_live.load_live(v9))
    live = live.rename(columns={"signal_tier": "prod_tier", "model_p": "p_model"})
    live["market"] = live["market"].replace({"over25": "ou25"})
    live = live[live.settled].assign(kick=lambda x: x.md, clv=lambda x: pd.to_numeric(x.clv_pct, errors="coerce"))
    tiers, tier_v = tier_table(af, live)
    mvm = model_vs_market(af)
    btts = btts_prereg(v9, af)
    o15 = over15_certification(v9, af)
    v91 = v91_crosscheck(v9)
    files = {"candidates_forward.csv": cand, "ou25_breakdowns.csv": ou_b, "edge_monotonicity.csv": mono,
             "odds_bands.csv": ob, "tiers.csv": tiers, "tier_ordering.csv": tier_v, "model_vs_market.csv": mvm}
    for f, t in files.items():
        t.to_csv(OUT / f, index=False)
    res = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
           "production_changed": "NO", "all_fixture_rows": int(len(af)),
           "all_fixture_by_market": {f"{k[0]}|{k[1]}": int(v) for k, v in af.groupby(["model_type", "market"]).size().items()},
           "close_status": af.close_status.value_counts().to_dict(),
           "btts_preregistered_progress": btts, "over15_certification": o15, "v91_shadow_crosscheck": v91,
           "registry": str(REG.relative_to(cfg.BASE_DIR)), "n_forward_tests": len(reg["hypotheses"])}
    (OUT / "edge_reassessment.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--v9", required=True)
    print(json.dumps(run(ap.parse_args().v9), indent=1, default=str)[:5000])

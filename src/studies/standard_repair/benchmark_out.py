"""Phase-2 outputs: tables, reconciliation, Top-5 panel, forward registrations, health.

    python -m src.studies.standard_repair benchmark [--skip-wf] [--only A,B]
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.standard_repair import fingerprint as FP
from src.studies.standard_repair import forensic as F
from src.studies.standard_repair import identity as ID
from src.studies.standard_repair import prices as PR
from src.studies.standard_repair import v9r_registry as VR
from src.studies.standard_repair.benchmark import CONFIRM_START, EVAL_START, LEGACY_THRESH, SIDES
from src.studies.standard_repair.benchmark_run import (REPAIRED_RECIPE, WF_PLAN, _has_recipe, analyse, build_dataset,
                                                       repaired_plan)
from src.studies.standard_repair.data import FD_CODES, power_devig
from src.studies.standard_repair.evaluate import block_boot

OUT = F.OUT
BET = set(F.BET_LEAGUES)


def _ci(x, g):
    bs = block_boot(np.asarray(x, float), np.asarray(g))
    return None if bs is None else [round(float(q), 4) for q in np.quantile(bs, [0.025, 0.975])]


# ── reconciliation ──────────────────────────────────────────────────────────────────────────────
def btts_reconciliation(analysis: dict, amap: dict) -> list:
    """BTTS: (a) v9's legacy BTTS backtest priced its bets at the 1.85 fallback - re-price the same
    placed YES tips at the REAL two-sided quote where one exists; (b) the July real-odds study's
    Serie B / La Liga 2 BTTS pockets, re-tested on the repaired data on identical rows."""
    from src.studies.standard_repair import btts_real as BR
    rows = []
    p = F._v9_file("output/backtest_results_btts.csv")
    if p.exists():
        keep = {"date", "league", "home_team", "away_team", "btts", "odds_btts", "price_synthetic", "p_btts",
                "edge", "signal_tier", "bet", "pnl"}
        b = pd.read_csv(p, low_memory=False, usecols=lambda c: c in keep)
        b = b[b["league"].isin(BET)].copy()
        b["date"] = pd.to_datetime(b["date"]).dt.normalize()
        b["week"] = b["date"].dt.strftime("%G-W%V")
        b = ID.apply_aliases(b, amap)
        placed = b[b["signal_tier"].isin(["SNIPER", "MARKSMAN", "VALUABLE"])].copy()
        real, rep_ = BR.attach(placed.drop_duplicates(["league", "date", "home_team", "away_team"]), amap)
        j = placed.merge(real, on=["league", "date", "home_team", "away_team"], how="left")
        j["pnl_real"] = np.where(j["btts_yes_odds"].notna(), np.where(j["btts"] == 1, j["btts_yes_odds"] - 1, -1.0), np.nan)
        j["pnl_185_same_rows"] = np.where(j["btts_yes_odds"].notna(), j["pnl"], np.nan)
        for lg, g in list(j.groupby("league")) + [("ALL", j)]:
            n_fb = int(PR.is_fallback("BTTS", g["odds_btts"]).sum())
            for col, fac, note in (("pnl", "B0_published_legacy_BTTS_backtest", f"{n_fb} of {len(g)} placed rows priced at the 1.85 fallback"),
                                   ("pnl_185_same_rows", "B1_legacy_pnl_same_rows_with_real_price", "rows that also have a real two-sided quote"),
                                   ("pnl_real", "B2_same_tips_at_REAL_BTTS_YES_price", "real quote: PREMATCH_SNAPSHOT_00Z / FORWARD_EARLIEST_PREKO")):
                s2 = g.dropna(subset=[col])
                rows.append({"factor": fac, "scope": lg, "bets": int(len(s2)), "gameweeks": int(s2["week"].nunique()),
                             "roi": round(float(s2[col].mean()), 4) if len(s2) else None,
                             "roi_ci95": _ci(s2[col], s2["week"]) if len(s2) >= 20 else None, "note": note})
        rows.append({"factor": "B_match_report", "scope": "ALL",
                     "note": f"real-quote match rate on legacy BTTS tips {rep_['match_rate']}"})
    side = analysis["side"]
    for lg in ("Serie B", "La Liga 2"):
        for sd in ("YES", "NO"):
            for arm in ("LEGACY_V9_REPRO", "V9_REPAIRED", "MKT_RESID_LR", "MKT_RESID_HGB"):
                for per in ("ALL", "DISCOVERY", "CONFIRMATION"):
                    r = side[(side["market"] == "BTTS_REAL") & (side["league"] == lg) & (side["side"] == sd)
                             & (side["arm"] == arm) & (side["period"] == per)]
                    if r.empty:
                        continue
                    r = r.iloc[0]
                    rows.append({"factor": "B3_july_claim_retest_real_BTTS", "scope": f"{lg} BTTS {sd} {arm} {per}",
                                 "bets": r.get("roi_n"), "gameweeks": r["gameweeks"], "roi": r.get("roi"),
                                 "roi_ci95": r.get("roi_ci95"), "dLL_vs_market": r["dLL_vs_market"],
                                 "dLL_ci95": r["dLL_ci95"], "n": r["n"],
                                 "note": "identical rows vs the REAL two-sided BTTS price; every lean, no threshold"})
    return rows


def reconciliation(analysis: dict, amap: dict) -> pd.DataFrame:
    """Why does v9's legacy backtest show profitable Standard leagues when the benchmark finds no pooled
    edge? Each row changes ONE thing on v9's own legacy backtest rows (or compares two benchmark arms)."""
    rows = []
    p = F._v9_file("output/backtest_results_standard.csv")
    if p.exists():
        lb = pd.read_csv(p, low_memory=False, usecols=lambda c: c in {
            "date", "league", "season", "home_team", "away_team", "over25", "odds_over25", "odds_under25",
            "p_over25", "best_side", "best_edge", "signal_tier", "pnl"})
        lb["date"] = pd.to_datetime(lb["date"]).dt.normalize()
        lb["week"] = lb["date"].dt.strftime("%G-W%V")
        lb = lb[lb["league"].isin(BET)]
        placed = lb[lb["signal_tier"].isin(["SNIPER", "MARKSMAN"])].copy()

        def add(factor, scope, sub, pnl_col="pnl", note=""):
            s = sub.dropna(subset=[pnl_col])
            rows.append({"factor": factor, "scope": scope, "bets": int(len(s)),
                         "gameweeks": int(s["week"].nunique()) if len(s) else 0,
                         "roi": round(float(s[pnl_col].mean()), 4) if len(s) else None,
                         "roi_ci95": _ci(s[pnl_col], s["week"]) if len(s) >= 20 else None, "note": note})
        for lg, g in list(placed.groupby("league")) + [("ALL", placed)]:
            add("0_published_legacy_backtest", lg, g, note="v9 backtest_results_standard.csv, SNIPER+MARKSMAN, closing odds")
        # 1 identity duplicates inside the legacy backtest
        m = ID.apply_aliases(placed, amap)
        dupe = m.duplicated(["league", "date", "home_team", "away_team"], keep=False)
        add("1_alias_duplicate_tips_removed", "ALL", placed[~dupe.to_numpy()],
            note=f"{int(dupe.sum())} placed tips sit on a match stored twice under two club spellings")
        # 2 COVID seasons
        cov = placed["season"].astype(str).isin(["2019/20", "2020/21"])
        add("2_covid_seasons_removed", "ALL", placed[~cov.to_numpy()], note=f"{int(cov.sum())} tips in 2019/20-2020/21 (v9 trains without them)")
        # 3 closing -> FD pre-match entry, same selection
        fd = PR.fd_ou25_rows(F._fd_dir(), FD_CODES)
        for c in ("home_team", "away_team"):
            fd[c] = [amap.get(l, {}).get(t, t) for l, t in zip(fd["league"], fd[c])]
        fd = fd.drop_duplicates(["league", "date", "home_team", "away_team"])
        j = m.merge(fd[["league", "date", "home_team", "away_team", "o_AVG", "u_AVG", "o_B365", "u_B365", "o_AVGC", "u_AVGC"]],
                    on=["league", "date", "home_team", "away_team"], how="left")
        eo, eu = j["o_AVG"].fillna(j["o_B365"]), j["u_AVG"].where(j["o_AVG"].notna(), j["u_B365"])
        over = j["best_side"].astype(str).str.upper().eq("OVER")
        won = np.where(over, j["over25"] == 1, j["over25"] == 0)
        odds_e = np.where(over, eo, eu)
        j["pnl_entry"] = np.where(np.isfinite(odds_e), np.where(won, odds_e - 1, -1.0), np.nan)
        j["pnl_close_same_rows"] = np.where(np.isfinite(odds_e), j["pnl"], np.nan)
        for lg, g in list(j.groupby("league")) + [("ALL", j)]:
            add("3a_closing_price_same_rows", lg, g, "pnl_close_same_rows", note="legacy pnl on the rows that also have an FD pre-match entry")
            add("3b_entry_price_FD_PREMATCH_APPROX", lg, g, "pnl_entry", note="same tips priced at the pre-match entry, not the close")
        # 4 raw implied vs de-vigged edge at the legacy tier floors (reproduction of the rule, not tuning)
        allr = ID.apply_aliases(lb, amap)
        pdv = power_devig(allr["odds_over25"], allr["odds_under25"])
        e_over, e_under = allr["p_over25"] - pdv, (1 - allr["p_over25"]) - (1 - pdv)
        best = np.where(e_over >= e_under, e_over, e_under)
        side_over = e_over >= e_under
        won2 = np.where(side_over, allr["over25"] == 1, allr["over25"] == 0)
        odds2 = np.where(side_over, allr["odds_over25"], allr["odds_under25"])
        allr["pnl_devig_sel"] = np.where(best >= LEGACY_THRESH["MARKSMAN"], np.where(won2, odds2 - 1, -1.0), np.nan)
        add("4_devigged_edge_selection", "ALL", allr, "pnl_devig_sel",
            note="edge = p_model - de-vigged closing prob (power), tier floor 0.08; closing odds as in legacy")
        # 5 no threshold: every row, the side the model leans to
        lean_over = allr["p_over25"] >= (1 / allr["odds_over25"]) / (1 / allr["odds_over25"] + 1 / allr["odds_under25"])
        won3 = np.where(lean_over, allr["over25"] == 1, allr["over25"] == 0)
        odds3 = np.where(lean_over, allr["odds_over25"], allr["odds_under25"])
        allr["pnl_all_lean"] = np.where(np.isfinite(odds3), np.where(won3, odds3 - 1, -1.0), np.nan)
        add("5_no_threshold_every_lean", "ALL", allr, "pnl_all_lean", note="selection effect: legacy model, every fixture, side it leans to")
        # 6 period: the benchmark window only
        add("6_legacy_tips_in_benchmark_window", "ALL", placed[placed["date"] >= pd.Timestamp(EVAL_START)],
            note=f"legacy placed tips dated >= {EVAL_START}")
    # 7+ model-quality factors from the identical-row benchmark
    comp = analysis["comp"]
    lgd = analysis["lg"]

    def dll(arm, market="OU25", period="ALL"):
        r = comp[(comp["arm"] == arm) & (comp["market"] == market) & (comp["period"] == period) & (comp["scope"].isin(["ALL", "OWN_ROWS"]))]
        return None if r.empty else (float(r.iloc[0]["dLL_vs_market"]), r.iloc[0]["dLL_ci95"], int(r.iloc[0]["n"]))
    for factor, arm, mk in (("7_batch_median_and_legacy_recipe (served model reproduction)", "LEGACY_V9_REPRO", "OU25"),
                            ("8_identity_repair (legacy recipe, canonical frame)", "LEGACY_ON_CANON", "OU25"),
                            ("9_train_serve_and_recipe_repair", "V9_REPAIRED", "OU25"),
                            ("9b_repaired_CLOSING_CONTAMINATED_REPRODUCTION", "V9_REPAIRED_MKT_CLOSING", "OU25"),
                            ("9c_repaired_TRUE_ASOF_MARKET_FEATURES", "V9_REPAIRED_MKT_ASOF", "OU25"),
                            ("9d_repaired_NO_MARKET_FEATURES (= V9_REPAIRED)", "V9_REPAIRED", "OU25"),
                            ("10_closing_market_feature -> as-of", "LEGACY_CANON_MKT_ASOF", "OU25"),
                            ("10b_market_feature_removed", "LEGACY_CANON_MKT_NONE", "OU25"),
                            ("11_history_window_modern_only", "LEGACY_CANON_W_MODERN", "OU25"),
                            ("11b_history_window_recent2", "LEGACY_CANON_W_RECENT2", "OU25"),
                            ("12_side_composition_pooled_BTTS (served)", "LEGACY_ON_CANON", "BTTS"),
                            ("12b_side_track_specific_BTTS", "LEGACY_CANON_STD_SIDE", "BTTS"),
                            ("12c_repaired_side_pooled_BTTS", "V9_REPAIRED_POOLED_SIDE", "BTTS"),
                            ("12d_repaired_side_track_BTTS", "V9_REPAIRED", "BTTS"),
                            ("13_best_market_anchored_residual", "MKT_RESID_LR", "OU25")):
        v = dll(arm, mk)
        if v:
            rows.append({"factor": factor, "scope": f"{mk} all bet+training leagues", "bets": None, "gameweeks": None,
                         "roi": None, "roi_ci95": None, "dLL_vs_market": round(v[0], 5), "dLL_ci95": v[1], "n": v[2],
                         "note": "probability quality vs the genuine pre-match market on identical rows (negative = beats market)"})
    # league composition: spread of league dLL for the legacy repro
    rows += btts_reconciliation(analysis, amap)
    lr = lgd[(lgd["arm"] == "LEGACY_V9_REPRO") & (lgd["market"] == "OU25") & (lgd["period"] == "ALL")]
    if len(lr):
        rows.append({"factor": "14_league_composition", "scope": "OU25 per league", "note":
                     "legacy dLL vs market per league: " + ", ".join(f"{r.league} {r.dLL_vs_market:+.4f} (n{r.n})" for r in lr.itertuples())})
    return pd.DataFrame(rows)


# ── Top-5 panel (retrospective, settled) ────────────────────────────────────────────────────────
def top5_panel() -> pd.DataFrame:
    p = F.REBUILD / "eval_OU25.parquet"
    if not p.exists():
        return pd.DataFrame()
    E = pd.read_parquet(p)
    rep = "V9_REPAIRED" if "V9_REPAIRED" in E else "LEGACY_ON_CANON"
    out = []
    for arm in ("LEGACY_V9_REPRO", rep):
        if arm not in E:
            continue
        g = E.assign(gap=(E[arm] - E["pm"]).abs())
        g["rank"] = g.groupby(["league", "week"])["gap"].rank(ascending=False, method="first")
        g = g[g["rank"] <= 5]
        for r in g.itertuples():
            over = getattr(r, arm) > r.pm
            out.append({"week": r.week, "league": r.league, "date": str(r.date.date()), "home_team": r.home_team,
                        "away_team": r.away_team, "panel": "LEGACY" if arm == "LEGACY_V9_REPRO" else "REPAIRED",
                        "legacy_prob": getattr(r, "LEGACY_V9_REPRO", np.nan), "repaired_prob": getattr(r, rep, np.nan),
                        "repaired_arm": rep, "market_prob": r.pm, "rank": int(r.rank),
                        "decision": "OVER" if over else "UNDER", "entry_odds": r.entry_over if over else r.entry_under,
                        "result_over25": int(r.y), "won": int((r.y == 1) == over), "settled": True})
    d = pd.DataFrame(out)
    if len(d):
        lr = d.pivot_table(index=["week", "league", "home_team", "away_team"], columns="panel", values="rank").reset_index()
        d = d.merge(lr.rename(columns={"LEGACY": "legacy_rank", "REPAIRED": "repaired_rank"}),
                    on=["week", "league", "home_team", "away_team"], how="left")
        dec = d.pivot_table(index=["week", "league", "home_team", "away_team"], columns="panel", values="decision",
                            aggfunc="first").reset_index()
        d = d.merge(dec.rename(columns={"LEGACY": "legacy_decision", "REPAIRED": "repaired_decision"}),
                    on=["week", "league", "home_team", "away_team"], how="left")
    return d


# ── league x market x side table ────────────────────────────────────────────────────────────────
def lms_table(side: pd.DataFrame, lg: pd.DataFrame) -> pd.DataFrame:
    rows = []
    s = side[side["period"] == "ALL"]
    rep = "V9_REPAIRED" if (s["arm"] == "V9_REPAIRED").any() else "LEGACY_ON_CANON"
    chal = ["MKT_RESID_LR", "MKT_RESID_HGB"]
    for (mk, lgn), g in s.groupby(["market", "league"]):
        for sd in SIDES[mk]:
            def pick(arm):
                r = g[(g["arm"] == arm) & (g["side"] == sd)]
                return None if r.empty else r.iloc[0]
            best = None
            for a in chal:
                r = pick(a)
                if r is not None and (best is None or r["dLL_vs_market"] < best["dLL_vs_market"]):
                    best = r
            for label, r in (("LEGACY_V9", pick("LEGACY_V9_REPRO")), ("REPAIRED_V9", pick(rep)), ("BEST_CHALLENGER", best)):
                if r is None:
                    continue
                cert = mk in ("OU25", "BTTS_REAL")
                rows.append({"league": lgn, "market": mk, "side": sd, "model": label, "arm": r["arm"],
                             "n": r["n"], "gameweeks": r["gameweeks"], "log_loss": r["log_loss"], "brier": r["brier"],
                             "cal_slope": r.get("cal_slope"), "ece": r.get("ece"),
                             "dLL_vs_market": r["dLL_vs_market"], "dLL_ci95": r["dLL_ci95"],
                             "dBrier_vs_market": r["dBrier_vs_market"], "dBrier_ci95": r["dBrier_ci95"],
                             "clv_prob_pp": r.get("clv_prob_pp") if cert else None,
                             "roi": r.get("roi") if cert else None, "roi_ci95": r.get("roi_ci95") if cert else None,
                             "roi_clv_status": ({"OU25": "FD_PREMATCH_APPROX entry / FD_CLOSING close",
                                                 "BTTS_REAL": "real two-sided entry (PREMATCH_SNAPSHOT_00Z / FORWARD_EARLIEST_PREKO); no close -> CLV blank"}
                                                .get(mk, "NOT CERTIFIABLE (synthetic market proxy, no real price)")),
                             "market_class": "GENUINE_TWO_SIDED" if cert else "SYNTHETIC_MARKET_PROXY"})
    return pd.DataFrame(rows)


def register_forward(calls: pd.DataFrame, fp: dict) -> list:
    """STD-V9R forward experiments only for CONFIRMED cells (discovery BH q<=0.10 AND confirmation
    p<0.05, same sign). Frozen; the forward test decides, never this retrospective evidence."""
    out = []
    if calls is None or calls.empty:
        return out
    for r in calls[calls["status"] == "CONFIRMED"].itertuples():
        eid = f"STD-V9R-{r.league.upper().replace(' ', '')}-{r.market}-{r.side}-2026Q4"
        spec = {"experiment_id": eid, "league": r.league, "market": r.market, "side": r.side,
                "model_version": f"{r.arm}@{fp.get('model_recipe_version')}", "feature_manifest": fp.get("feature_schema_version"),
                "imputer": fp.get("imputer_version"), "calibrator": "as trained (no post-hoc league calibrator)",
                "selection_rule": f"every first-sight fixture where {r.arm} leans {r.side} vs the de-vigged market (no threshold)",
                "market_source": "Pro book_odds_snapshots two-sided consensus at first sight" if r.market == "OU25"
                else "Pro book_odds_snapshots REAL two-sided BTTS/O1.5 only (synthetic proxy never)",
                "min_n": 150, "min_matchdays": 12, "primary_metric": "paired dLL vs market, matchday block bootstrap CI95 < 0",
                "evidence": {"disc_dLL": r.disc_dLL, "disc_bh_q": r.disc_bh_q, "conf_dLL": r.conf_dLL, "conf_p": r.conf_p,
                             "conf_n": r.conf_n}, "frame_hash": fp.get("frame_hash_at_cutoff")}
        out.append(VR.register(spec))
    return out


def parity_gate() -> dict:
    """feature_parity.csv comes from R1's scripts/standard_feature_audit.py (replayed historical as-of
    features vs the upcoming builder at the same cutoff). Any REQUIRED feature FAIL for the repaired
    recipe fails the pipeline; legacy FAILs are the documented defect, not a gate."""
    p = OUT / "feature_parity.csv"
    if not p.exists():
        return {"status": "MISSING"}
    f = pd.read_csv(p)
    rep = f[(f["recipe"] == "v9_repaired") & (f["kind"] == "replay_asof_vs_upcoming")]
    bad = rep[rep["required"].astype(str).str.lower().eq("true") & rep["status"].eq("FAIL")]
    if len(bad):
        raise F.IntegrityError(f"feature parity FAIL on REQUIRED repaired features: {bad['feature'].tolist()}")
    return {"status": "PASS" if len(rep) else "NO_REPAIRED_ROWS",
            "summary": f.groupby(["kind", "recipe", "status"]).size().rename("n").reset_index().to_dict("records"),
            "repaired_warn": rep[rep["status"] == "WARN"][["feature", "p95_abs_diff"]].to_dict("records")}


def write(skip_wf: bool = False, only=None) -> dict:
    parity = parity_gate()
    d, dq, man, mt, copies = build_dataset(skip_wf=skip_wf, only=only)
    A = analyse(d)
    amap = json.loads(F.ALIASES.read_text(encoding="utf-8"))["map"]
    has_rep = any(a == "V9_REPAIRED" for a in A["comp"]["arm"].unique())
    expected = set(WF_PLAN) | (set(repaired_plan()) if _has_recipe() else set())
    missing = sorted(expected - set(copies))
    # R1's pooled vs standard-only vs NF-only side study (its own four-block holdout), if it ran
    sides = sorted((F.REBUILD / "sides").glob("side_track_comparison_*.csv"))
    side_tab = pd.concat([pd.read_csv(x) for x in sides], ignore_index=True) if sides else pd.DataFrame()
    fp = FP.current(*F.load_benchmark_frame(), data_cutoff=dq["data_cutoff"],
                    imputer_version=("persisted_train_only (R1)" if has_rep else None),
                    model_recipe_version=(REPAIRED_RECIPE if has_rep else None))
    rec = reconciliation(A, amap)
    lms = lms_table(A["side"], A["lg"])
    panel = top5_panel()
    regs = register_forward(A["calls"], fp)
    OUT.mkdir(parents=True, exist_ok=True)
    FP.stamp_csv(A["comp"], fp).to_csv(OUT / "model_comparison.csv", index=False)
    if (OUT / "feature_parity.csv").exists():
        fpar = pd.read_csv(OUT / "feature_parity.csv")
        FP.stamp_csv(fpar[[c for c in fpar.columns if c not in ("generated_at", "data_cutoff", "v9_commit", "pro_commit",
                                                                   "frame_hash", "feature_version", "model_recipe_version",
                                                                   "price_source_version")]], fp)             .to_csv(OUT / "feature_parity.csv", index=False)
    FP.stamp_csv(A["lg"], fp).to_csv(OUT / "repaired_by_league.csv", index=False)
    FP.stamp_csv(A["side"], fp).to_csv(OUT / "repaired_by_side.csv", index=False)
    FP.stamp_csv(lms, fp).to_csv(OUT / "league_market_side.csv", index=False)
    FP.stamp_csv(rec, fp).to_csv(OUT / "reconciliation.csv", index=False)
    if len(side_tab):
        FP.stamp_csv(side_tab, fp).to_csv(OUT / "side_track_comparison.csv", index=False)
    if len(panel):
        FP.stamp_csv(panel, fp).to_csv(OUT / "top5_panel_repair.csv", index=False)
    comp = A["comp"]
    head = comp[(comp["period"].isin(["ALL", "DISCOVERY", "CONFIRMATION"])) & (comp["scope"] == "ALL")]
    bench = {
        "title": "Standard v9 forensic repair - repaired benchmark (Phase 2)",
        "status": ("PARTIAL_NO_V9_REPAIRED_RECIPE" if not has_rep else "PARTIAL_MISSING_ARMS" if missing
                   else "COMPLETE"),
        "arms_expected": sorted(expected), "arms_missing": missing,
        "side_track_study_r1": side_tab.to_dict("records"),
        "btts_real_market": mt.attrs.get("btts_real_report"),
        "eval_start": EVAL_START, "confirm_start": CONFIRM_START,
        "markets": A["results"], "alias_copies_in_legacy_scoring": copies,
        "headline": head.to_dict("records"),
        "discovery_confirmation": A["calls"][A["calls"]["status"] != "NO_SIGNAL"].to_dict("records") if len(A["calls"]) else [],
        "n_cells_tested": int(len(A["calls"])),
        "rank_test": A["rank"].to_dict("records"),
        "feature_parity": parity,
        "studies": A["extra"].to_dict("records"),
        "forward_registrations": regs,
        "notes": ["BTTS/OU15 compared to a SYNTHETIC_MARKET_PROXY: 'did / did not improve the synthetic proxy'",
                  "ROI/CLV only for OU25 against FD_PREMATCH_APPROX entries; BTTS/OU15 ROI is NOT CERTIFIABLE",
                  "no threshold was optimised; legacy tier floors appear only in the reconciliation reproduction"],
    }
    bench = FP.stamp_obj(bench, fp)
    (OUT / "repaired_benchmark.json").write_text(json.dumps(bench, indent=1, default=str), encoding="utf-8")
    F.write_health()
    return bench


def main(argv: list[str]) -> int:
    skip = "--skip-wf" in argv
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1].split(",")
    if "--wf-only" in argv:
        # CI matrix shard: run only these walk-forward arms (gate still enforced), no analysis
        build_dataset(skip_wf=False, only=only)
        print("walk-forward arms done:", only)
        return 0
    b = write(skip_wf=skip, only=only)
    print(json.dumps({"status": b["status"], "n_cells": b["n_cells_tested"],
                      "confirmed": [c for c in b["discovery_confirmation"] if c["status"] == "CONFIRMED"]}, indent=1, default=str))
    return 0

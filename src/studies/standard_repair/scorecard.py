"""REPAIR SCORECARD per Standard league x market x side, its diagnostics, and the automated diagnosis.

One track = (league, market, side): Championship .. Serie B x {OU25 OVER, OU25 UNDER, BTTS YES, BTTS NO,
OU15 OVER}. A model "takes" a side on a fixture when its probability for that side exceeds the
market's (it leans that way). Everything below is computed on the rows a model leans on, except the
market-efficiency profile, which uses every row of the league.

Evidence sources, each labelled in the output:
  HISTORICAL  benchmark_rows (evaluate.py): v9 walk-forward + every arm, holdout 2026-01..2026-10 and
              validation 2025. OU25 has genuine pre-match prices (ROI, CLV vs football-data close);
              BTTS/OU15 have NO historical prices, so their ROI/CLV are "n/a" historically.
  FORWARD     first-sight rows (forward.py): the SERVED model vs real quotes, 2026-08-17 onwards.
  RANK PANEL  v9 output/league_weekly_research.csv (weekly Top-5 per league x market), settled rows.

Diagnoses are evidence statements with a date, re-derived every run — never permanent labels.
Nothing here changes production; scorecard.json is a reader for a later v9 League Repair Lab.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.standard_repair.data import EXP, logit
from src.studies.standard_repair.evaluate import ll, paired

OUT = cfg.OUTPUT_DIR / "standard_repair"
REG = cfg.REGISTRY_DIR / "standard_repair"
LEAGUES = {"Championship": "CHAMP", "League One": "LEAGUE1", "League Two": "LEAGUE2", "Bundesliga 2": "BUNDES2",
           "La Liga 2": "LALIGA2", "Ligue 2": "LIGUE2", "Serie B": "SERIEB"}
SIDES = {"OU25": ("OVER", "UNDER"), "BTTS": ("YES", "NO"), "OU15": ("OVER",)}
FIRST = {"OU25": "OVER", "BTTS": "YES", "OU15": "OVER"}
FLOOR = 0.03                                    # VALUABLE floor; diagnosis only, never tuned here
ODDS_BANDS = [(1.0, 1.70, "<1.70"), (1.50, 1.70, "1.50-1.70"), (1.70, 1.90, "1.70-1.90"), (1.90, 2.10, "1.90-2.10"),
              (2.10, 2.40, "2.10-2.40"), (2.40, 99, "2.40+")]
DIS_BANDS = [0, 2, 4, 6, 8, 10, 999]
MIN_N, MIN_WEEKS = 150, 10
DIAG_ORDER = ["INSUFFICIENT_SAMPLE", "PRICE_QUALITY_PROBLEM", "MODEL_BELOW_MARKET", "CALIBRATION_FAILURE",
              "REGIME_DRIFT", "MODEL_ABOVE_MARKET_SELECTION_BAD", "SIDE_SPECIFIC_EDGE", "ODDS_BAND_DEPENDENCE",
              "RANKING_PROMISING", "NO_EDGE_YET"]


def _r(x, k=4):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), k)


def _side_p(p, side, market):
    return p if side == FIRST[market] else 1 - p


def _won(y, side, market):
    return (y == 1) if side == FIRST[market] else (y == 0)


def _cal_slope(p, y):
    from src.studies.standard_repair.candidates import pen_logit
    if len(p) < 50 or len(np.unique(y)) < 2:
        return None
    return _r(pen_logit(logit(p)[:, None], y, n_free=1)[1])


def _monotone(vals: list) -> dict:
    v = [x for x in vals if x is not None]
    if len(v) < 3:
        return {"spearman": None, "non_monotone": None}
    rho = pd.Series(range(len(v))).corr(pd.Series(v), method="spearman")
    s = np.sign(np.diff(v))
    flips = int((s[1:] != s[:-1]).sum()) if len(s) > 1 else 0
    return {"spearman": _r(rho, 3), "non_monotone": bool(flips >= 2)}


# ── historical per-track block ────────────────────────────────────────────────────────────────
def _hist_block(R: pd.DataFrame, market: str, side: str, col: str) -> dict:
    """R: one league's benchmark rows for one market and period. col: model probability column."""
    p, pm, y = R[col].to_numpy(float), R["p_MARKET"].to_numpy(float), R["y"].to_numpy(float)
    ps, pms = _side_p(p, side, market), _side_p(pm, side, market)
    lean = ps > pms
    L = R[lean]
    if not len(L):
        return {"n": 0}
    won = _won(L["y"].to_numpy(float), side, market)
    dl = ll(p[lean], y[lean]) - ll(pm[lean], y[lean])
    db = (p[lean] - y[lean]) ** 2 - (pm[lean] - y[lean]) ** 2
    out = {"n": int(lean.sum()), "gameweeks": int(L["week"].nunique()),
           "claimed_side_prob": _r(ps[lean].mean()), "market_side_prob": _r(pms[lean].mean()), "hit_rate": _r(won.mean()),
           "log_loss": _r(ll(p[lean], y[lean]).mean(), 5), "brier": _r(((p[lean] - y[lean]) ** 2).mean(), 5),
           "dLL_vs_market": paired(dl, L["week"].to_numpy()), "dBrier_vs_market": paired(db, L["week"].to_numpy())}
    if market == "OU25":
        o = (L["o_AVG"] if side == "OVER" else L["u_AVG"]).to_numpy(float)
        edge = ps[lean] - 1 / o
        pnl = np.where(won, o - 1, -1.0)
        sel = np.isfinite(o) & (edge >= FLOOR)
        # CLV = entry price / closing price of the same side (both the football-data book average) - 1
        oc = (L["close_o_AVG"] if side == "OVER" else L["close_u_AVG"]).to_numpy(float)
        clv = o / oc - 1
        cov = np.isfinite(clv)
        out.update({"price_coverage": _r(np.isfinite(o).mean(), 3),
                    "roi_at_floor": {"n": int(sel.sum()), "roi": _r(pnl[sel].mean()) if sel.any() else None,
                                     "ci90": (paired(pnl[sel], L["week"].to_numpy()[sel])["ci90"] if sel.sum() >= 20 else None)},
                    "clv": {"coverage": _r(cov.mean(), 3), "mean_all_lean": _r(np.nanmean(clv)) if cov.any() else None,
                            "mean_at_floor": _r(np.nanmean(clv[sel & cov])) if (sel & cov).any() else None},
                    "odds_bands": []})
        for lo, hi, name in ODDS_BANDS[1:]:
            m = (o >= lo) & (o < hi)
            out["odds_bands"].append({"band": name, "n": int(m.sum()), "hit": _r(won[m].mean()) if m.any() else None,
                                      "roi": _r(pnl[m].mean()) if m.any() else None,
                                      "clv": _r(np.nanmean(clv[m & cov])) if (m & cov).any() else None,
                                      "dLL": _r(dl[m].mean(), 5) if m.any() else None})
    else:
        out.update({"price_coverage": 0.0, "roi_at_floor": None, "clv": None,
                    "note": "no historical two-sided price for this market in standard leagues; ROI/CLV forward only"})
    # disagreement bands (pp of side probability over market)
    gap = (ps[lean] - pms[lean]) * 100
    bands = []
    for lo, hi in zip(DIS_BANDS[:-1], DIS_BANDS[1:]):
        m = (gap >= lo) & (gap < hi)
        b = {"band_pp": f"{lo}-{hi}" if hi < 999 else f"{lo}+", "n": int(m.sum()),
             "win_rate": _r(won[m].mean()) if m.any() else None, "dLL": _r(dl[m].mean(), 5) if m.any() else None,
             "dBrier": _r(db[m].mean(), 5) if m.any() else None}
        if market == "OU25":
            b["roi"] = _r(pnl[m].mean()) if m.any() else None
            b["clv"] = _r(np.nanmean(clv[m & cov])) if (m & cov).any() else None
        bands.append(b)
    out["disagreement_bands"] = bands
    key = [b.get("roi") if market == "OU25" else (None if b["dLL"] is None else -b["dLL"]) for b in bands if b["n"] >= 10]
    out["disagreement_monotonicity"] = _monotone(key)
    return out


def _efficiency(R: pd.DataFrame, market: str) -> dict:
    y, pm = R["y"].to_numpy(float), R["p_MARKET"].to_numpy(float)
    e = {"n": int(len(R)), "market_log_loss": _r(ll(pm, y).mean(), 5), "market_brier": _r(((pm - y) ** 2).mean(), 5),
         "market_cal_slope": _cal_slope(pm, y),
         "wowza_minus_market_dLL": _r((ll(R["p_V9"], y) - ll(pm, y)).mean(), 5),
         "book_dispersion_median": _r(R["book_dispersion"].median(), 4) if market == "OU25" else None}
    if market == "OU25":
        pc = R["pclose_OU25_AVG_power"].to_numpy(float)
        ok = np.isfinite(pc)
        pre = R["p_MARKET_AVG_power"].to_numpy(float)      # like-for-like: same book average, same de-vig, raw
        e["closing_accuracy_dLL_close_minus_prematch"] = _r((ll(pc[ok], y[ok]) - ll(pre[ok], y[ok])).mean(), 5) if ok.any() else None
        e["clv_availability"] = _r(ok.mean(), 3)
    else:
        e["closing_accuracy_dLL_close_minus_prematch"], e["clv_availability"] = None, 0.0
    return e


# ── forward and rank-panel blocks ─────────────────────────────────────────────────────────────
def _forward_block(F: pd.DataFrame, market: str, side: str) -> dict:
    if F is None or F.empty:
        return {"n_first_sight": 0}
    g = F[F["market"] == market]
    out = {"n_first_sight": int(len(g)), "price_coverage_first_sight": _r(g["p_market"].notna().mean(), 3) if len(g) else None}
    g = g.dropna(subset=["p_market"])
    ps, pms = _side_p(g["p_model"].to_numpy(float), side, market), _side_p(g["p_market"].to_numpy(float), side, market)
    L = g[ps > pms]
    S = L.dropna(subset=["y"])
    out.update({"n_lean": int(len(L)), "n_settled": int(len(S)), "gameweeks": int(S["week"].nunique()) if len(S) else 0})
    if len(S):
        dl = ll(S["p_model"], S["y"]) - ll(S["p_market"], S["y"])
        out["dLL_vs_market"] = paired(dl, S["week"].to_numpy())
        out["hit_rate"] = _r(_won(S["y"].to_numpy(float), side, market).mean())
    odds = L["odds_first"] if side == FIRST[market] else L["odds_other"]
    close = L["close_first"] if side == FIRST[market] else L["close_other"]
    clv = (odds / close - 1).to_numpy(float)      # median-book entry price vs median-book closing price
    ok = np.isfinite(clv)
    out["clv"] = {"coverage": _r(ok.mean(), 3) if len(L) else None, "mean": _r(np.nanmean(clv)) if ok.any() else None}
    return out


def rank_panel() -> pd.DataFrame:
    p = Path(cfg.V9_LOCAL) / "output" / "league_weekly_research.csv"
    try:
        d = pd.read_csv(p) if p.exists() else __import__("src.data.v9_source", fromlist=["fetch_csv"]).fetch_csv(
            "output/league_weekly_research.csv", required=False)
    except Exception:                                                        # noqa: BLE001
        return pd.DataFrame()
    if d is None or d.empty:
        return pd.DataFrame()
    return d[d.get("model_type", pd.Series(dtype=str)).astype(str) == "standard"]


def _rank_block(P: pd.DataFrame, league: str, market: str, side: str) -> dict:
    if P.empty:
        return {"n_settled": 0}
    mk = {"OU25": ["OU25"], "BTTS": ["BTTS"], "OU15": ["OU15", "OVER15"]}[market]
    g = P[(P["league"] == league) & P["market"].isin(mk) & (P["side"].astype(str).str.upper() == side)]
    s = g[g["settle_status"].astype(str) == "SETTLED"] if "settle_status" in g else g.iloc[0:0]
    out = {"n_panel": int(len(g)), "n_settled": int(len(s))}
    if len(s):
        won = pd.to_numeric(s["won"], errors="coerce")
        out.update({"hit_rate": _r(won.mean()), "flat_roi": _r(pd.to_numeric(s["flat_pnl"], errors="coerce").mean()),
                    "clv_coverage": _r(pd.to_numeric(s["clv_pct"], errors="coerce").notna().mean(), 3),
                    "clv_mean_pct": _r(pd.to_numeric(s["clv_pct"], errors="coerce").mean()),
                    "hit_by_rank": {str(int(k)): _r(v) for k, v in won.groupby(pd.to_numeric(s["league_market_rank"], errors="coerce")).mean().items()
                                    if pd.notna(k)},
                    "rank_vs_won_spearman": _r(pd.to_numeric(s["league_market_rank"], errors="coerce").corr(won, method="spearman"), 3)
                    if len(s) >= 10 else None})
    return out


# ── diagnosis ─────────────────────────────────────────────────────────────────────────────────
def diagnose(t: dict) -> list[dict]:
    """Evidence-based flags, each with the numbers that triggered it."""
    out = []
    h, hv, ch = t["historical"]["v9_holdout"], t["historical"]["v9_validation"], t["historical"]["challenger_holdout"]
    fw, rk = t["forward"], t["rank_panel"]
    n = h.get("n", 0)
    if n < MIN_N or h.get("gameweeks", 0) < MIN_WEEKS:
        out.append({"code": "INSUFFICIENT_SAMPLE", "evidence": f"holdout lean n={n}, weeks={h.get('gameweeks', 0)} (< {MIN_N}/{MIN_WEEKS})"})
    pcov = h.get("price_coverage")
    if t["market"] == "OU25" and pcov is not None and pcov < 0.8:
        out.append({"code": "PRICE_QUALITY_PROBLEM", "evidence": f"historical price coverage {pcov}"})
    if t["market"] != "OU25" and (fw.get("price_coverage_first_sight") or 0) < 0.5:
        out.append({"code": "PRICE_QUALITY_PROBLEM",
                    "evidence": f"no historical two-sided price; forward first-sight coverage {fw.get('price_coverage_first_sight')}"})
    d = (h.get("dLL_vs_market") or {})
    if d.get("ci95") and d["ci95"][0] > 0:
        out.append({"code": "MODEL_BELOW_MARKET", "evidence": f"v9 holdout dLL {d['delta']} CI95 {d['ci95']} (positive = worse than market)"})
    cs, ms = h.get("claimed_side_prob"), h.get("hit_rate")
    if cs is not None and ms is not None and n >= 50 and abs(cs - ms) > 0.05:
        out.append({"code": "CALIBRATION_FAILURE", "evidence": f"v9 claims {cs} on this side, realised {ms} (n={n})"})
    dv, dh = (hv.get("dLL_vs_market") or {}), (ch.get("dLL_vs_market") or {})
    cv = (t["historical"]["challenger_validation"].get("dLL_vs_market") or {})
    if cv.get("delta") is not None and dh.get("delta") is not None and np.sign(cv["delta"]) != np.sign(dh["delta"]) \
            and abs(cv["delta"] - dh["delta"]) > 0.002:
        out.append({"code": "REGIME_DRIFT", "evidence": f"challenger dLL validation {cv['delta']} vs holdout {dh['delta']}"})
    roi = (h.get("roi_at_floor") or {})
    if dh.get("delta") is not None and dh["delta"] < 0 and roi.get("roi") is not None and roi["roi"] < 0 and roi.get("n", 0) >= 30:
        out.append({"code": "MODEL_ABOVE_MARKET_SELECTION_BAD",
                    "evidence": f"challenger dLL {dh['delta']} < 0 but v9 floor ROI {roi['roi']} (n={roi['n']})"})
    if dh.get("ci90") and dh["ci90"][1] < 0:
        out.append({"code": "SIDE_SPECIFIC_EDGE", "evidence": f"challenger dLL {dh['delta']} CI90 {dh['ci90']} on this side only "
                                                             "(diagnostic; not significant after multiplicity unless the pooled rule passes)"})
    bands = [b for b in (h.get("odds_bands") or []) if b["n"] >= 40 and b["roi"] is not None]
    if len(bands) >= 2 and max(b["roi"] for b in bands) - min(b["roi"] for b in bands) > 0.30:
        out.append({"code": "ODDS_BAND_DEPENDENCE",
                    "evidence": "; ".join(f"{b['band']} roi {b['roi']} n={b['n']}" for b in bands)})
    sp = rk.get("rank_vs_won_spearman")
    if sp is not None and sp < -0.2 and rk.get("n_settled", 0) >= 20:
        out.append({"code": "RANKING_PROMISING", "evidence": f"rank 1 wins more than rank 5 (spearman {sp}, n={rk['n_settled']})"})
    if not any(o["code"] in ("SIDE_SPECIFIC_EDGE", "RANKING_PROMISING") for o in out):
        out.append({"code": "NO_EDGE_YET", "evidence": f"challenger holdout dLL {dh.get('delta')} CI95 {dh.get('ci95')}"})
    out.sort(key=lambda o: DIAG_ORDER.index(o["code"]))
    return out


def next_experiment(t: dict) -> str:
    codes = {d["code"] for d in t["diagnosis"]}
    if "PRICE_QUALITY_PROBLEM" in codes and t["market"] != "OU25":
        return "Accumulate two-sided first-sight quotes (forward capture) before any model work; re-test residual on real quotes at n>=150."
    if "SIDE_SPECIFIC_EDGE" in codes:
        return "Pre-register this side as a forward shadow only if the pooled rule passes; otherwise re-test on next quarter's untouched block."
    if "REGIME_DRIFT" in codes:
        return "Test a shorter recency window / league-environment reset at season start on the next untouched block."
    if "CALIBRATION_FAILURE" in codes or "MODEL_BELOW_MARKET" in codes:
        return "Replace absolute-probability scoring with the market-anchored residual (v9 adds no info after the price); test market-anchored HGB residual per league with shrinkage."
    return "Hold: keep collecting; re-evaluate pooled challengers with the next quarter as fresh holdout."


# ── assemble ──────────────────────────────────────────────────────────────────────────────────
def challenger_for(res: dict, market: str) -> str:
    """The challenger is chosen on VALIDATION (never holdout): best validation dLL among model arms."""
    M = res["markets"][market]
    arms = [a for a in M["arms"] if not a.startswith("MARKET") and a not in ("V9", "V9_CAL")]
    return min(arms, key=lambda a: M["arms"][a]["validation"]["dLL_vs_market"]["delta"])


def build(res: dict | None = None, rows: pd.DataFrame | None = None, fwd: pd.DataFrame | None = None) -> dict:
    res = res or json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    if rows is None and (EXP / "benchmark_rows.parquet").exists():
        rows = pd.read_parquet(EXP / "benchmark_rows.parquet")
    prev = {}
    if (OUT / "scorecard.json").exists():
        prev = {t["track_id"]: t for t in json.loads((OUT / "scorecard.json").read_text(encoding="utf-8")).get("tracks", [])}
    P = rank_panel()
    tracks = []
    for league, code in LEAGUES.items():
        for market, sides in SIDES.items():
            ch = challenger_for(res, market)
            for side in sides:
                tid = f"STD-REPAIR-{code}-{market}-{side}"
                if rows is not None:
                    R = rows[(rows["market"] == market) & (rows["league"] == league)]
                    Rh, Rv = R[R["period"] == "holdout"], R[R["period"] == "validation"]
                    hist = {"v9_holdout": _hist_block(Rh, market, side, "p_V9"),
                            "v9_validation": _hist_block(Rv, market, side, "p_V9"),
                            "challenger_holdout": _hist_block(Rh, market, side, f"p_{ch}"),
                            "challenger_validation": _hist_block(Rv, market, side, f"p_{ch}"),
                            "market_efficiency_holdout": _efficiency(Rh, market),
                            "v9_cal_slope_holdout": _cal_slope(Rh["p_V9"].to_numpy(float), Rh["y"].to_numpy(float))}
                else:                                   # CI has no benchmark rows: carry the last historical block
                    hist = prev.get(tid, {}).get("historical", {})
                t = {"track_id": tid, "league": league, "market": market, "side": side,
                     "current_model": "v9 served Standard model (historical: v9 recipe walk-forward)",
                     "market_baseline": res["markets"][market]["market_baseline"],
                     "current_challenger": ch, "historical": hist,
                     "forward": _forward_block(fwd, market, side) if fwd is not None else prev.get(tid, {}).get("forward", {}),
                     "rank_panel": _rank_block(P, league, market, side)}
                if fwd is not None and not fwd.empty:
                    t["forward"] = _forward_block(fwd[fwd["league"] == league], market, side)
                if not hist:
                    t["diagnosis"] = prev.get(tid, {}).get("diagnosis", [])
                else:
                    t["diagnosis"] = diagnose(t)
                t["research_status"] = "RESEARCH_REPAIR"
                t["next_experiment"] = next_experiment(t)
                t["experiment_id"] = f"{tid}-V1"
                tracks.append(t)
    sc = {"generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
          "scope": "Standard leagues only; New Format untouched", "ladder":
              ["RESEARCH_REPAIR", "CHALLENGER_READY", "FORWARD_SHADOW", "ELIGIBLE_FOR_REVIEW", "OWNER_REVIEW", "PAPER",
               "ACTIVE_LOW", "ACTIVE"],
          "pooled_verdict": res["verdict"], "tracks": tracks}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scorecard.json").write_text(json.dumps(sc, indent=1, default=str), encoding="utf-8")
    flat = []
    for t in tracks:
        h = t["historical"].get("v9_holdout", {}) if t["historical"] else {}
        c = t["historical"].get("challenger_holdout", {}) if t["historical"] else {}
        flat.append({"track_id": t["track_id"], "league": t["league"], "market": t["market"], "side": t["side"],
                     "n_holdout_lean_v9": h.get("n"), "gameweeks": h.get("gameweeks"),
                     "v9_dLL": (h.get("dLL_vs_market") or {}).get("delta"),
                     "v9_dLL_ci95": json.dumps((h.get("dLL_vs_market") or {}).get("ci95")),
                     "v9_roi_floor": (h.get("roi_at_floor") or {}).get("roi"), "v9_clv": (h.get("clv") or {}).get("mean_all_lean"),
                     "challenger": t["current_challenger"], "challenger_dLL": (c.get("dLL_vs_market") or {}).get("delta"),
                     "challenger_dLL_ci95": json.dumps((c.get("dLL_vs_market") or {}).get("ci95")),
                     "forward_n_settled": t["forward"].get("n_settled"),
                     "forward_dLL": (t["forward"].get("dLL_vs_market") or {}).get("delta"),
                     "rank_panel_settled": t["rank_panel"].get("n_settled"),
                     "diagnosis": "|".join(d["code"] for d in t["diagnosis"]), "status": t["research_status"],
                     "next_experiment": t["next_experiment"]})
    pd.DataFrame(flat).to_csv(OUT / "scorecard.csv", index=False)
    return sc

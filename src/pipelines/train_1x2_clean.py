"""
Monthly 1X2 retrain on v9's repaired data (owner 2026-11-09; reports/P5_1X2_REVIEW.md). PAPER only.

    python -m src.pipelines.train_1x2_clean [--v9 <root>] [--extract <dir>] [--asof YYYY-MM-DD]

1. v9's committed history through the loader, network blocked (src/pipelines/onex2_v9_bridge.py
   history mode; skipped when --extract points at an existing extract).
2. src.models.onex2_clean.train: the multinomial logistic on the 3 years before --asof (default:
   today, UTC) and the blend with the pre-kickoff price, fitted on the last 9 months' out-of-sample
   predictions.
3. The research cells of config/onex2_research_cells.json (LEAGUE_WIDE Eredivisie draws), scored on
   the bettable history since 2024-07-01 and on the LIVE paper bets of output/paper_1x2.csv, with the
   owner's strict PROVEN rule on the live bets.

Writes output/model_1x2_clean.pkl, output/model_1x2_clean.json, output/onex2_research_cells.json.
Run by .github/workflows/pro_train_1x2_clean.yml, which stays off until the repository variable
PRO_1X2_CLEAN_ENABLED is 'true' (go-live).
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.models import onex2_clean as C

ROOT = Path(__file__).resolve().parents[2]
FD_RAW = ROOT / "experiments" / "ou_info_inputs_2026_10" / "fd_raw"
PAPER_FILE = ROOT / "output" / "paper_1x2.csv"
OUTCOME_INDEX = {"home": 0, "draw": 1, "away": 2}


def _roi_stats(pnl: np.ndarray, dates: np.ndarray) -> dict:
    from src.studies.onex2_review import ROI_bootstrap
    if len(pnl) == 0:
        return {"n": 0}
    p, ci = ROI_bootstrap(pnl, dates, 2000, 20261109)
    return {"n": int(len(pnl)), "roi": float(np.mean(pnl)), "ci95": ci, "p_one_sided": p}


def evaluate_cells(extract_dir: Path, asof: pd.Timestamp, paper: pd.DataFrame | None) -> dict:
    from src.studies.onex2_review import holm
    cfg = json.loads(C.CELLS_CONFIG.read_text(encoding="utf-8"))
    rule = cfg["proven_rule"]
    M = pd.read_parquet(extract_dir / "matches.parquet")
    M["date"] = pd.to_datetime(M["date"])
    M["y"] = np.where(M["home_goals"] > M["away_goals"], 0,
                      np.where(M["home_goals"] == M["away_goals"], 1, 2))
    P = pd.read_parquet(extract_dir / "prices.parquet")
    bet = P[P["class"].isin(["FD_BET365_ENTRY", "SHARP_OPEN"])].copy()
    bet["_r"] = (bet["class"] != "FD_BET365_ENTRY").astype(int)
    bet = bet.sort_values("_r").drop_duplicates("row_id")
    close = P[P["class"].isin(["FD_CLOSE", "SHARP_CLOSE"])].copy()
    close["_r"] = (close["class"] != "FD_CLOSE").astype(int)
    close = close.sort_values("_r").drop_duplicates("row_id")
    out = []
    for c in cfg["cells"]:
        i = OUTCOME_INDEX[c["outcome"]]
        col = ("o_home", "o_draw", "o_away")[i]
        h = M[(M["league"] == c["league"]) & (M["date"] >= pd.Timestamp(cfg["history_start"]))
              & (M["date"] < asof)].merge(bet[["row_id", col]], on="row_id")
        h = h.merge(close[["row_id", col]].rename(columns={col: "close"}), on="row_id", how="left")
        pnl = np.where(h["y"].to_numpy() == i, h[col].to_numpy() - 1.0, -1.0)
        hist = _roi_stats(pnl, h["date"].to_numpy())
        clv = (h[col] / h["close"] - 1.0).dropna()
        hist["clv_mean"] = float(clv.mean()) if len(clv) else None
        live = {"n": 0}
        if paper is not None and len(paper) and "research_cell" in paper.columns:
            L = paper[(paper["research_cell"] == c["id"])
                      & pd.to_numeric(paper.get("result"), errors="coerce").notna()
                      & pd.to_numeric(paper.get("research_odds"), errors="coerce").notna()]
            if len(L):
                res = pd.to_numeric(L["result"]).to_numpy().astype(int)
                o = pd.to_numeric(L["research_odds"]).to_numpy()
                live = _roi_stats(np.where(res == i, o - 1.0, -1.0),
                                  pd.to_datetime(L["match_date"]).to_numpy())
        out.append({**c, "history": hist, "live": live})
    pl = np.array([x["live"].get("p_one_sided", np.nan) for x in out], dtype=float)
    ph = holm(pl)
    for x, p in zip(out, ph):
        x["live"]["p_holm"] = None if not np.isfinite(p) else float(p)
        n, roi = x["live"]["n"], x["live"].get("roi")
        if n >= rule["min_live_bets"] and np.isfinite(p) and p < rule["family_alpha"]:
            x["verdict"] = "PROVEN"
        elif roi is not None and roi > 0 and x["history"].get("clv_mean") is not None                 and x["history"]["clv_mean"] > 0:
            x["verdict"] = "PROMISING"
        else:
            x["verdict"] = "UNPROVEN" if n else "ACCRUING (no settled live bet yet)"
    return {"asof": str(asof.date()), "proven_rule": rule, "cells": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--v9", default=os.getenv("V9_LOCAL", ""))
    ap.add_argument("--extract", default="")
    ap.add_argument("--asof", default="")
    ap.add_argument("--fd-raw", default=str(FD_RAW))
    a = ap.parse_args(argv)
    asof = (pd.Timestamp(a.asof) if a.asof
            else pd.Timestamp.now(tz="UTC").tz_convert(None).normalize())
    ex = Path(a.extract) if a.extract else Path(tempfile.mkdtemp(prefix="onex2_"))
    if not (ex / "meta.json").exists():
        if not a.v9:
            print("[1x2-clean] no v9 checkout (--v9 / V9_LOCAL) - nothing trained")
            return 1
        meta = C.run_bridge("history", a.v9, str(ex), a.fd_raw)
        print(f"[1x2-clean] extract: {meta['matches']:,} matches, v9 {meta['v9_commit'][:8]}, "
              f"fingerprint {meta['feature_fingerprint']}")
    artifact, report = C.train(ex, asof)
    paper = pd.read_csv(PAPER_FILE, low_memory=False) if PAPER_FILE.exists() else None
    cells = evaluate_cells(ex, asof, paper)
    report["research_cells"] = [{"id": x["id"], "verdict": x["verdict"], "live_n": x["live"]["n"],
                                 "history_n": x["history"]["n"]} for x in cells["cells"]]
    C.save(artifact, report)
    C.CELLS_FILE.write_text(json.dumps(cells, indent=1, default=str), encoding="utf-8")
    print(f"[1x2-clean] trained {report['name']} {report['calc_version']} as of {report['asof']}: "
          f"{report['n_train']:,} rows, {len(report['leagues'])} leagues; blend "
          f"{'n=' + str(report['blend']['n_fit']) if report['blend'] else 'not fitted'}; "
          f"OOS {report['oos_last_months']}")
    for x in cells["cells"]:
        print(f"[1x2-clean] research cell {x['id']}: {x['verdict']} (history {x['history']}, live {x['live']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""ROW PROVENANCE and SOURCE REGIME test (owner brief 2026-10-28, "row provenance" / "mixed history").

Each Standard row in the rebuilt frame carries `row_source` (frame_build.py):
FOOTBALL_DATA_CURRENT / FOOTBALL_DATA_ARCHIVE / BACKTEST_ARCHIVE / API_FOOTBALL / OTHER.

coverage(): non-null share of every serving feature and every raw input column by
source x season x league -> output/standard_repair/source_coverage.csv.

source_predictability(): can a simple classifier tell BACKTEST_ARCHIVE rows from football-data rows
using ONLY which values are missing? If yes (AUC well above 0.5) the two sources are different
REGIMES — the model would partly learn "which file did this come from" — and every history-window
ablation must treat the source explicitly (MODERN_ONLY vs MODERN+ARCHIVE). The test is a 5-fold
cross-validated logistic regression on missingness indicators; a second run restricted to the
seasons where BOTH sources have rows separates "source" from "era".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RAW_COLS = ["home_shots", "home_sot", "home_corners", "home_fouls", "ht_home_goals", "home_xg",
            "home_insidebox", "odds_over25", "odds_under25", "odds_btts", "odds_over15", "odds_over35", "referee"]


def coverage(std: pd.DataFrame, serving: list[str]) -> pd.DataFrame:
    cols = [c for c in list(dict.fromkeys(serving + RAW_COLS)) if c in std.columns]
    g = std.groupby(["row_source", "season", "league"], dropna=False)
    out = g.size().rename("rows").to_frame()
    nn = std[cols].notna().groupby([std["row_source"], std["season"], std["league"]], dropna=False).mean().round(4)
    nn.columns = [f"cov_{c}" for c in nn.columns]
    out = out.join(nn).reset_index()
    out["serving_mean_coverage"] = out[[f"cov_{c}" for c in serving if c in std.columns]].mean(axis=1).round(4)
    return out.sort_values(["league", "season", "row_source"])


def _auc(y, s) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, s))


def source_predictability(std: pd.DataFrame, serving: list[str]) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    d = std[std["row_source"].isin(["BACKTEST_ARCHIVE", "FOOTBALL_DATA_ARCHIVE", "FOOTBALL_DATA_CURRENT"])].copy()
    y = (d["row_source"] == "BACKTEST_ARCHIVE").astype(int).to_numpy()
    res = {"rows": int(len(d)), "archive_share": round(float(y.mean()), 4) if len(y) else None}
    if len(np.unique(y)) < 2:
        res["verdict"] = "ONE_SOURCE_ONLY"
        return res

    def run(X, yy):
        if len(np.unique(yy)) < 2 or len(yy) < 100:
            return None
        cv = StratifiedKFold(5, shuffle=True, random_state=0)
        p = cross_val_predict(LogisticRegression(max_iter=2000), X, yy, cv=cv, method="predict_proba")[:, 1]
        return round(_auc(yy, p), 4)

    feats_serv = [c for c in serving if c in d.columns]
    feats_all = [c for c in dict.fromkeys(feats_serv + RAW_COLS) if c in d.columns]
    Xs = d[feats_serv].isna().astype(int).to_numpy()
    Xa = d[feats_all].isna().astype(int).to_numpy()
    res["auc_missingness_serving_features"] = run(Xs, y)
    res["auc_missingness_all_inputs"] = run(Xa, y)
    # overlap seasons only (both sources present) -> source, not era
    ss = d.groupby("season")["row_source"].agg(lambda x: x.eq("BACKTEST_ARCHIVE").any() and (~x.eq("BACKTEST_ARCHIVE")).any())
    ov = ss[ss].index
    o = d[d["season"].isin(ov)]
    yo = (o["row_source"] == "BACKTEST_ARCHIVE").astype(int).to_numpy()
    res["overlap_seasons"] = [str(s) for s in ov]
    res["overlap_rows"] = int(len(o))
    res["auc_missingness_all_inputs_overlap_seasons"] = run(o[feats_all].isna().astype(int).to_numpy(), yo)
    # which columns differ most in missingness between sources
    miss = d[feats_all].isna().groupby(d["row_source"]).mean().T
    if {"BACKTEST_ARCHIVE"} <= set(miss.columns):
        other = [c for c in miss.columns if c != "BACKTEST_ARCHIVE"]
        miss["gap"] = (miss["BACKTEST_ARCHIVE"] - miss[other].mean(axis=1)).abs()
        res["largest_missingness_gaps"] = miss.sort_values("gap", ascending=False).head(10).round(4).reset_index() \
            .rename(columns={"index": "column"}).to_dict("records")
    a = res["auc_missingness_all_inputs"] or 0.5
    res["verdict"] = ("SOURCE_REGIME_DETECTABLE" if a >= 0.75 else "SOURCE_WEAKLY_DETECTABLE" if a >= 0.6
                      else "SOURCE_NOT_DETECTABLE")
    res["handling"] = ("history-window ablations must compare MODERN_ONLY (football-data, 2023/24+) against "
                       "MODERN+ARCHIVE explicitly; never pool the archive in silently" if a >= 0.6 else
                       "no source-specific handling needed beyond the standard ablations")
    return res

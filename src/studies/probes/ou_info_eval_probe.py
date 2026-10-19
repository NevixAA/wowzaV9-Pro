"""Walk-forward: v9's O/U model WITHOUT vs WITH injury inputs, trained by v9's own code.

Run with cwd = a wowza-betting checkout and v9's interpreter (Pro's `src` would shadow v9's):

    python ou_info_eval_probe.py --frame F.parquet --inj I.parquet --out rows.parquet

Both arms are identical except the injury columns: same rows, same folds, same v9 `train()`
(LogReg + GB + meta-stack), same season decay weights, the champion's exact feature list.
Injury inputs are NaN outside covered league-seasons and flagged by `inj_covered`, which is how a
production model would see them. READ-ONLY against v9.
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

INJ = ["home_inj_n_missing", "away_inj_n_missing", "home_inj_minutes_share", "away_inj_minutes_share",
       "home_inj_goal_share", "away_inj_goal_share", "total_inj_minutes_share", "total_inj_goal_share",
       "inj_covered"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True)
    ap.add_argument("--inj", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2024-01-01")
    a = ap.parse_args()

    import numpy as np
    import pandas as pd
    import config
    from src.model import train, predict_proba

    fr = pd.read_parquet(a.frame)
    fr["date"] = pd.to_datetime(fr["date"]).dt.normalize()
    inj = pd.read_parquet(a.inj)
    inj["date"] = pd.to_datetime(inj["date"]).dt.normalize()
    cols = [c for c in INJ if c != "inj_covered"]
    d = fr.merge(inj[["league", "date", "home_team", "away_team"] + cols],
                 on=["league", "date", "home_team", "away_team"], how="left")
    d["inj_covered"] = d[cols[0]].notna().astype(float)

    feats = {"standard": pickle.load(open("models/model_v9_standard.pkl", "rb"))["feature_cols"],
             "new_format": pickle.load(open("models/model_v9_newformat.pkl", "rb"))["feature_cols"]}
    blocks = pd.date_range(a.start, d["date"].max() + pd.Timedelta(days=1), freq="QS")
    blocks = list(blocks) + [d["date"].max() + pd.Timedelta(days=1)]
    out = []
    for track, base in feats.items():
        t = d[d["track"] == track].sort_values("date").reset_index(drop=True)
        w_all = t["season"].map(lambda s: config.TRAINING_DECAY_WEIGHTS.get(s, config.DEFAULT_DECAY_WEIGHT)).fillna(
            config.DEFAULT_DECAY_WEIGHT).to_numpy()
        for b0, b1 in zip(blocks[:-1], blocks[1:]):
            tr = t[t["date"] < b0]
            te = t[(t["date"] >= b0) & (t["date"] < b1)]
            if len(te) == 0 or len(tr) < 2000:
                continue
            w = w_all[tr.index]
            t0 = time.time()
            r_base = train(tr.reset_index(drop=True), feature_cols=list(base), sample_weight=w)
            r_inj = train(tr.reset_index(drop=True), feature_cols=list(base) + INJ, sample_weight=w)

            def payload(r):
                return {"target": "over25", "models": {k: v["model"] for k, v in r.items()},
                        "feature_cols": r[next(iter(r))]["feature_cols"]}
            pb = predict_proba(te, payload=payload(r_base)).to_numpy()
            pi = predict_proba(te, payload=payload(r_inj)).to_numpy()
            keep = ["date", "league", "home_team", "away_team", "over25", "inj_covered"] + \
                   [c for c in ("odds_over25", "odds_under25") if c in te.columns] + cols
            o = te[keep].copy()
            o["track"], o["block"], o["p_base"], o["p_inj"] = track, str(b0.date()), pb, pi
            out.append(o)
            print(f"{track} {b0.date()} train={len(tr)} test={len(te)} covered={int(te['inj_covered'].sum())} "
                  f"{time.time() - t0:.0f}s", flush=True)
    pd.concat(out, ignore_index=True).to_parquet(a.out, index=False)
    print("done", sum(len(x) for x in out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

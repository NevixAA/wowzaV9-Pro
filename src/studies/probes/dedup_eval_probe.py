"""Does removing duplicate-spelling match copies improve v9's O/U model? (owner 2026-10-19)

Run with cwd = a wowza-betting checkout and v9's interpreter:

    python dedup_eval_probe.py --raw RAW.parquet --dedup DEDUP.parquet --out rows.parquet

Arm A trains on v9's frame AS IT IS (duplicates included); arm B on the de-duplicated frame. Both are
scored on the SAME de-duplicated test rows (a duplicated test row would count one match twice), with
v9's own train(), the champion's feature list and season decay weights. READ-ONLY against v9.
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--dedup", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2024-01-01")
    a = ap.parse_args()
    import pandas as pd
    import config
    from src.model import train, predict_proba

    raw = pd.read_parquet(a.raw)
    ded = pd.read_parquet(a.dedup)
    for d in (raw, ded):
        d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    feats = {"standard": pickle.load(open("models/model_v9_standard.pkl", "rb"))["feature_cols"],
             "new_format": pickle.load(open("models/model_v9_newformat.pkl", "rb"))["feature_cols"]}
    blocks = list(pd.date_range(a.start, ded["date"].max() + pd.Timedelta(days=1), freq="QS")) + \
        [ded["date"].max() + pd.Timedelta(days=1)]

    def w(df):
        return df["season"].map(lambda s: config.TRAINING_DECAY_WEIGHTS.get(s, config.DEFAULT_DECAY_WEIGHT)) \
            .fillna(config.DEFAULT_DECAY_WEIGHT).to_numpy()

    def payload(r):
        return {"target": "over25", "models": {k: v["model"] for k, v in r.items()},
                "feature_cols": r[next(iter(r))]["feature_cols"]}
    out = []
    for track, base in feats.items():
        R = raw[raw["track"] == track].sort_values("date").reset_index(drop=True)
        D = ded[ded["track"] == track].sort_values("date").reset_index(drop=True)
        for b0, b1 in zip(blocks[:-1], blocks[1:]):
            trR, trD = R[R["date"] < b0].reset_index(drop=True), D[D["date"] < b0].reset_index(drop=True)
            te = D[(D["date"] >= b0) & (D["date"] < b1)]
            if len(te) == 0 or len(trD) < 2000:
                continue
            t0 = time.time()
            pa = predict_proba(te, payload=payload(train(trR, feature_cols=list(base), sample_weight=w(trR)))).to_numpy()
            pb = predict_proba(te, payload=payload(train(trD, feature_cols=list(base), sample_weight=w(trD)))).to_numpy()
            o = te[["date", "league", "home_team", "away_team", "over25"]].copy()
            o["track"], o["block"], o["p_raw"], o["p_dedup"] = track, str(b0.date()), pa, pb
            out.append(o)
            print(f"{track} {b0.date()} trainRaw={len(trR)} trainDedup={len(trD)} test={len(te)} "
                  f"{time.time() - t0:.0f}s", flush=True)
    pd.concat(out, ignore_index=True).to_parquet(a.out, index=False)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

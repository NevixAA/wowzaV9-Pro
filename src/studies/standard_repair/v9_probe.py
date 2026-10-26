"""Walk-forward reproduction of v9's STANDARD model for O/U 2.5, BTTS and Over 1.5 — v9's own trainer.

Run with cwd = a v9 (wowza-betting) checkout and v9's interpreter, because Pro's `src` would shadow v9's:

    python <pro>/src/studies/standard_repair/v9_probe.py --frame F.parquet --out OUT.parquet

READ-ONLY against v9: it imports `config`, `src.model.train/predict_proba` and reads the champion's
feature list from models/model_v9_standard.pkl; it writes only --out.

What it reproduces: the standard track only (never pooled with new format), quarterly blocks, each
block scored by a model trained strictly on rows dated before the block starts (v9's own 80/20
chronological train/calibration split inside `train`), v9's season decay weights, the champion's 42
feature columns. Side markets use the SAME feature list (that is what v9 ships: model_v9_btts.pkl and
model_v9_over15.pkl carry the identical 42 columns) — but trained standard-only here, whereas the
shipped side models may differ in data scope. So this is "v9's recipe, standard-only", the closest
honest historical stand-in for the served model; the served model itself is measured forward from
Pro's model_snapshots (src/studies/standard_repair/forward.py).
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

TARGETS = ("over25", "btts", "over15")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2024-01-01")
    a = ap.parse_args()

    import pandas as pd
    import config
    from src.model import train, predict_proba

    fr = pd.read_parquet(a.frame)
    fr["date"] = pd.to_datetime(fr["date"]).dt.normalize()
    t = fr[fr["track"] == "standard"].sort_values("date").reset_index(drop=True)
    feats = list(pickle.load(open("models/model_v9_standard.pkl", "rb"))["feature_cols"])
    end = t["date"].max() + pd.Timedelta(days=1)
    blocks = list(pd.date_range(a.start, end, freq="QS")) + [end]
    w_all = t["season"].map(lambda s: config.TRAINING_DECAY_WEIGHTS.get(s, config.DEFAULT_DECAY_WEIGHT)) \
        .fillna(config.DEFAULT_DECAY_WEIGHT).to_numpy()
    out = []
    for b0, b1 in zip(blocks[:-1], blocks[1:]):
        tr = t[t["date"] < b0]
        te = t[(t["date"] >= b0) & (t["date"] < b1)]
        if len(te) == 0 or len(tr) < 2000:
            continue
        o = te[["date", "league", "home_team", "away_team"]].copy()
        o["block"] = str(b0.date())
        t0 = time.time()
        for tgt in TARGETS:
            trt = tr.dropna(subset=[tgt])
            r = train(trt.reset_index(drop=True), target=tgt, feature_cols=feats,
                      sample_weight=w_all[trt.index])
            payload = {"target": tgt, "models": {k: v["model"] for k, v in r.items()},
                       "feature_cols": r[next(iter(r))]["feature_cols"]}
            o[f"p_v9_{tgt}"] = predict_proba(te, payload=payload).to_numpy()
        out.append(o)
        print(f"{b0.date()} train={len(tr)} test={len(te)} {time.time() - t0:.0f}s", flush=True)
    pd.concat(out, ignore_index=True).to_parquet(a.out, index=False)
    print("done", sum(len(x) for x in out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

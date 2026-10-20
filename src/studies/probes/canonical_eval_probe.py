"""v9 AS IT IS vs v9 with club aliases merged — same real matches, v9's own trainer.

Run with cwd = a wowza-betting checkout and v9's interpreter:

    python canonical_eval_probe.py --current CUR.parquet --canonical CAN.parquet --aliases A.json --out rows.parquet

Arm CURRENT trains on the frame production builds today (duplicates, split club histories). Arm
CANONICAL trains on the alias-merged frame. Each arm predicts its OWN feature rows (the features are
what changed), and the two are compared on the SAME matches: CURRENT's rows are keyed through the
alias map and de-duplicated, then inner-joined to CANONICAL's. READ-ONLY against v9.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current", required=True)
    ap.add_argument("--canonical", required=True)
    ap.add_argument("--aliases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2024-01-01")
    a = ap.parse_args()
    import pandas as pd
    import config
    from src.model import train, predict_proba

    al = json.loads(Path(a.aliases).read_text(encoding="utf-8"))["aliases"]
    cur = pd.read_parquet(a.current)
    can = pd.read_parquet(a.canonical)
    for d in (cur, can):
        d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    for c in ("home_team", "away_team"):
        cur[f"k_{c}"] = [al.get(lg, {}).get(t, t) for lg, t in zip(cur["league"], cur[c])]
        can[f"k_{c}"] = can[c]
    K = ["league", "date", "k_home_team", "k_away_team"]
    feats = {"standard": pickle.load(open("models/model_v9_standard.pkl", "rb"))["feature_cols"],
             "new_format": pickle.load(open("models/model_v9_newformat.pkl", "rb"))["feature_cols"]}
    end = can["date"].max() + pd.Timedelta(days=1)
    blocks = list(pd.date_range(a.start, end, freq="QS")) + [end]

    def w(df):
        return df["season"].map(lambda s: config.TRAINING_DECAY_WEIGHTS.get(s, config.DEFAULT_DECAY_WEIGHT)) \
            .fillna(config.DEFAULT_DECAY_WEIGHT).to_numpy()

    def payload(r):
        return {"target": "over25", "models": {k: v["model"] for k, v in r.items()},
                "feature_cols": r[next(iter(r))]["feature_cols"]}
    out = []
    for track, base in feats.items():
        C = cur[cur["track"] == track].sort_values("date").reset_index(drop=True)
        N = can[can["track"] == track].sort_values("date").reset_index(drop=True)
        for b0, b1 in zip(blocks[:-1], blocks[1:]):
            trC, trN = C[C["date"] < b0].reset_index(drop=True), N[N["date"] < b0].reset_index(drop=True)
            teC = C[(C["date"] >= b0) & (C["date"] < b1)].copy()
            teN = N[(N["date"] >= b0) & (N["date"] < b1)].copy()
            if len(teN) == 0 or len(trN) < 2000:
                continue
            t0 = time.time()
            teC["p_current"] = predict_proba(teC, payload=payload(
                train(trC, feature_cols=list(base), sample_weight=w(trC)))).to_numpy()
            teN["p_canonical"] = predict_proba(teN, payload=payload(
                train(trN, feature_cols=list(base), sample_weight=w(trN)))).to_numpy()
            teC = teC.drop_duplicates(K, keep="first")
            m = teN[K + ["over25", "p_canonical"]].merge(teC[K + ["p_current"]], on=K, how="inner")
            m["track"], m["block"] = track, str(b0.date())
            out.append(m)
            print(f"{track} {b0.date()} trainCur={len(trC)} trainCan={len(trN)} matched={len(m)}/{len(teN)} "
                  f"{time.time() - t0:.0f}s", flush=True)
    pd.concat(out, ignore_index=True).to_parquet(a.out, index=False)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

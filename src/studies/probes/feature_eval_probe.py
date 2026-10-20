"""Generic walk-forward: v9's O/U model with extra input columns, trained by v9's own code.

Run with cwd = a wowza-betting checkout and v9's interpreter (Pro's `src` would shadow v9's):

    python feature_eval_probe.py --frame F.parquet --extra X.parquet \
        --arms '{"open": ["p_open"], "open+move": ["p_open", "move"]}' --track standard --out rows.parquet

Every arm is v9's champion feature list PLUS its columns; the "base" arm (no extras) is always run.
Same rows, same quarterly blocks, same v9 train() (LogReg + GB + meta-stack), same season decay
weights. Extra columns are merged on (league, date, home_team, away_team); `<name>_covered` flags rows
where the extra table had the fixture. READ-ONLY against v9.
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
    ap.add_argument("--frame", required=True)
    ap.add_argument("--extra", required=True)
    ap.add_argument("--arms", required=True)
    ap.add_argument("--track", default="standard")
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2024-01-01")
    a = ap.parse_args()
    import pandas as pd
    import config
    from src.model import train, predict_proba

    arms = json.loads(a.arms)
    fr = pd.read_parquet(a.frame)
    fr["date"] = pd.to_datetime(fr["date"]).dt.normalize()
    ex = pd.read_parquet(a.extra)
    ex["date"] = pd.to_datetime(ex["date"]).dt.normalize()
    cols = sorted({c for v in arms.values() for c in v})
    d = fr.merge(ex[["league", "date", "home_team", "away_team"] + cols].drop_duplicates(
        ["league", "date", "home_team", "away_team"]), on=["league", "date", "home_team", "away_team"], how="left")
    d["extra_covered"] = d[cols].notna().any(axis=1).astype(float)
    model_file = {"standard": "models/model_v9_standard.pkl", "new_format": "models/model_v9_newformat.pkl"}[a.track]
    base = list(pickle.load(open(model_file, "rb"))["feature_cols"])
    t = d[d["track"] == a.track].sort_values("date").reset_index(drop=True)
    w_all = t["season"].map(lambda s: config.TRAINING_DECAY_WEIGHTS.get(s, config.DEFAULT_DECAY_WEIGHT)) \
        .fillna(config.DEFAULT_DECAY_WEIGHT).to_numpy()
    blocks = list(pd.date_range(a.start, t["date"].max() + pd.Timedelta(days=1), freq="QS")) + \
        [t["date"].max() + pd.Timedelta(days=1)]

    def payload(r):
        return {"target": "over25", "models": {k: v["model"] for k, v in r.items()},
                "feature_cols": r[next(iter(r))]["feature_cols"]}
    out = []
    for b0, b1 in zip(blocks[:-1], blocks[1:]):
        tr = t[t["date"] < b0]
        te = t[(t["date"] >= b0) & (t["date"] < b1)]
        if len(te) == 0 or len(tr) < 2000:
            continue
        w = w_all[tr.index]
        trr = tr.reset_index(drop=True)
        t0 = time.time()
        o = te[["date", "league", "home_team", "away_team", "over25", "extra_covered"]
               + [c for c in ("odds_over25", "odds_under25") if c in te.columns] + cols].copy()
        o["track"], o["block"] = a.track, str(b0.date())
        o["p_base"] = predict_proba(te, payload=payload(train(trr, feature_cols=base, sample_weight=w))).to_numpy()
        for name, extra in arms.items():
            r = train(trr, feature_cols=base + list(extra), sample_weight=w)
            o[f"p_{name}"] = predict_proba(te, payload=payload(r)).to_numpy()
        out.append(o)
        print(f"{a.track} {b0.date()} train={len(tr)} test={len(te)} covered={int(te['extra_covered'].sum())} "
              f"{time.time() - t0:.0f}s", flush=True)
    pd.concat(out, ignore_index=True).to_parquet(a.out, index=False)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

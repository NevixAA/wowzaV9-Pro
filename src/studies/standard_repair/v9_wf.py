"""Walk-forward with v9's OWN trainer on a rebuilt frame — runs inside a v9 checkout (v9's `src`).

    cd <v9 checkout> && python <pro>/src/studies/standard_repair/v9_wf.py --frame F --out O.parquet \
        [--recipe legacy_v9|<R1 recipe>] [--side-scope pooled|standard|newformat] [--start 2024-07-01]

LEGACY_V9_REPRO reproduces what v9's `pipeline.mode_train` does, defects included:
  * OU25: standard rows only, `train(valid_std, target, sample_weight=season decay weights)` with
    the champion's feature list (v9 calls train with feature_cols=None -> FEATURE_COLS; the champion
    payload carries the same 42 columns).
  * BTTS / Over 1.5: v9 trains them on concat([std_valid, nf_valid]) — POOLED Standard + New Format
    (pipeline.py:735). `--side-scope pooled` reproduces that; `standard` / `newformat` are the
    track-specific challengers (brief P0 #9).
  * scoring: v9's `predict_proba` imputes with the median of the BATCH it is scoring (P0 #1). Live,
    the batch is the board; here each ISO week of fixtures (all leagues) is one batch, the closest
    historical stand-in for a board.
  * blocks: quarterly; each block is scored by a model trained only on rows dated before it.
With `--recipe` other than legacy_v9 the recipe switch from R1's repaired v9 code is passed through
(train(..., recipe=...)) when v9's `train` accepts it; otherwise the run refuses rather than silently
falling back to the legacy recipe.
"""
from __future__ import annotations

import argparse
import inspect
import json
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
    ap.add_argument("--start", default="2024-07-01")
    ap.add_argument("--recipe", default="legacy_v9")
    ap.add_argument("--side-scope", default="pooled", choices=["pooled", "standard", "newformat"])
    ap.add_argument("--targets", default=",".join(TARGETS))
    ap.add_argument("--score-track", default="standard")
    ap.add_argument("--train-window", default="all",
                    choices=["all", "modern", "recent3", "recent2", "weighted"],
                    help="history policy: all=MODERN+ARCHIVE (v9), modern=football-data rows only, "
                         "recentN=last N years before the block, weighted=v9 weights x 0.5**age_years")
    ap.add_argument("--price-mode", default="none", help="v9_repaired feature list mode (R1 feature_cols)")
    ap.add_argument("--drop-features", default="", help="comma list removed from the champion feature list")
    a = ap.parse_args()

    import numpy as np
    import pandas as pd
    import config
    from src import model as M

    fr = pd.read_parquet(a.frame)
    fr["date"] = pd.to_datetime(fr["date"]).dt.normalize()
    fr = fr.sort_values("date").reset_index(drop=True)
    elig = fr["v9_train_eligible"].astype(bool) if "v9_train_eligible" in fr else fr["over25"].notna()
    feats = list(pickle.load(open("models/model_v9_standard.pkl", "rb"))["feature_cols"])
    drop = {x for x in a.drop_features.split(",") if x}
    feats = [f for f in feats if f not in drop]
    kw_recipe = {}
    SR = None
    if a.recipe != "legacy_v9":
        if "recipe" not in inspect.signature(M.train).parameters:
            raise SystemExit(f"v9 train() has no recipe switch; refusing to run recipe {a.recipe!r} as legacy")
        kw_recipe = {"recipe": a.recipe}
        from src import standard_repair as SR                      # R1's research API
        feats = [f for f in SR.feature_cols(a.recipe, a.price_mode) if f not in drop]

    def weights(df):
        return df["season"].astype(str).map(lambda s: config.TRAINING_DECAY_WEIGHTS.get(s, config.DEFAULT_DECAY_WEIGHT)) \
            .fillna(config.DEFAULT_DECAY_WEIGHT).to_numpy()

    end = fr["date"].max() + pd.Timedelta(days=1)
    blocks = list(pd.date_range(a.start, end, freq="QS")) + [end]
    out = []
    meta = {"recipe": a.recipe, "price_mode": a.price_mode, "side_scope": a.side_scope, "train_window": a.train_window, "blocks": [], "feature_cols": feats}
    for b0, b1 in zip(blocks[:-1], blocks[1:]):
        tr_all = fr[(fr["date"] < b0) & elig]
        te = fr[(fr["date"] >= b0) & (fr["date"] < b1) & (fr["track"].astype(str) == a.score_track)]
        if te.empty:
            continue
        o = te[["date", "league", "home_team", "away_team"]].copy()
        o["block"] = str(b0.date())
        t0 = time.time()
        for tgt in a.targets.split(","):
            if tgt == "over25":
                tr = tr_all[tr_all["track"].astype(str) == "standard"]
            else:
                scope = {"pooled": ("standard", "new_format"), "standard": ("standard",), "newformat": ("new_format",)}[a.side_scope]
                tr = tr_all[tr_all["track"].astype(str).isin(scope)]
            if a.train_window == "modern" and "row_source" in tr:
                tr = tr[tr["row_source"].astype(str).str.startswith("FOOTBALL_DATA") | (tr["track"].astype(str) != "standard")]
            elif a.train_window in ("recent3", "recent2"):
                tr = tr[tr["date"] >= b0 - pd.Timedelta(days=365 * int(a.train_window[-1]))]
            tr = tr.dropna(subset=[tgt]).reset_index(drop=True)
            if len(tr) < 2000:
                o[f"p_{tgt}"] = np.nan
                continue
            w = weights(tr) if SR is None else SR.derived_weights(tr, as_of=b0 - pd.Timedelta(days=1)).to_numpy()
            if a.train_window == "weighted":
                w = w * 0.5 ** ((b0 - tr["date"]).dt.days.to_numpy() / 365.0)
            r = M.train(tr, target=tgt, feature_cols=feats,
                        sample_weight=(w if SR is None else pd.Series(w, index=tr.index)), **kw_recipe)
            if hasattr(M, "build_payload"):
                payload = M.build_payload(r, tgt)               # carries the persisted imputer (repaired)
            else:
                payload = {"target": tgt, "models": {k: v["model"] for k, v in r.items()},
                           "feature_cols": r[next(iter(r))]["feature_cols"]}
            if a.recipe != "legacy_v9" and payload.get("imputer") is None:
                raise SystemExit("repaired payload carries no persisted imputer - refusing (batch imputation)")
            p = pd.Series(np.nan, index=te.index)
            wk = te["date"].dt.strftime("%G-W%V")
            for _, g in te.groupby(wk):                     # one board-sized batch per ISO week
                p.loc[g.index] = M.predict_proba(g, payload=payload).to_numpy()
            o[f"p_{tgt}"] = p.to_numpy()
            meta["blocks"].append({"block": str(b0.date()), "target": tgt, "train_rows": int(len(tr)),
                                   "train_tracks": sorted(tr["track"].astype(str).unique())})
        out.append(o)
        print(f"{b0.date()} test={len(te)} {time.time() - t0:.0f}s", flush=True)
    pd.concat(out, ignore_index=True).to_parquet(a.out, index=False)
    Path(a.out).with_suffix(".json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    print("done", sum(len(x) for x in out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

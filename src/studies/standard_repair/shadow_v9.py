"""v9-side half of the Standard repair FORWARD SHADOW (STD-V9R-SHADOW-2026Q4). Runs INSIDE a v9
checkout with v9's own code (`cd <v9> && python <pro>/src/studies/standard_repair/shadow_v9.py ...`),
like v9_wf.py. Read-only w.r.t. v9: it never writes inside the checkout (save_research_payload refuses
every serving path) and nothing it produces is read by v9 serving, tips, stakes or Telegram.

    train     --out DIR --alias-map JSON --cutoff YYYY-MM-DD
              v9 loader -> identity canonicalisation (frozen alias map) -> rows dated STRICTLY before
              the cutoff -> v9_repaired as-of features (price_mode none) -> V9_REPAIRED Standard-track
              payloads for over25 / btts / over15 + the Standard feature frame for the Pro-side
              MKT_RESID fit + meta.json (versions, v9 commit, source digests, row counts).
    features  --board CSV --payloads DIR --alias-map JSON --out DIR
              the SAME loader / canonicalisation / builder for the upcoming board fixtures
              (build_upcoming_features_repaired: unplayed rows appended, batch-invariant) scored with
              the frozen V9_REPAIRED payloads, + the played Standard rows Pro needs for env_rate.
    results   --since YYYY-MM-DD --alias-map JSON --out CSV
              played Standard rows since a date (settlement), canonical names.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

TARGETS = ("over25", "btts", "over15")
SOURCE_FILES = ("config.py", "src/data_loader.py", "src/feature_engineering.py", "src/features_repaired.py",
                "src/identity_repair.py", "src/imputer.py", "src/model.py", "src/poisson.py",
                "src/standard_repair.py", "src/team_names.py")
FORM = ("home_scored_last5", "away_scored_last5", "home_conceded_last5", "away_conceded_last5")


def _versions() -> dict:
    from src.features_repaired import FEATURE_RECIPE_VERSION
    from src.identity_repair import IDENTITY_VERSION
    from src.imputer import IMPUTER_VERSION
    from src.model import MODEL_RECIPE_VERSION
    return {"feature_recipe_version": FEATURE_RECIPE_VERSION, "model_recipe_version": MODEL_RECIPE_VERSION,
            "imputer_version": IMPUTER_VERSION, "identity_version": IDENTITY_VERSION}


def _source_digest() -> dict:
    out = {}
    for f in SOURCE_FILES:
        p = Path.cwd() / f
        out[f] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return out


def _commit() -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def _history(alias_map: str):
    from src.standard_repair import load_history, prepare_history
    raw, rep = prepare_history(load_history(), "v9_repaired", alias_map, True)
    return raw, {k: v for k, v in rep.items() if k not in ("aliases", "quarantine_rows")}


def cmd_train(a) -> None:
    import pandas as pd
    import config
    from src.standard_repair import feature_frame, save_research_payload, train_track
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cutoff = pd.Timestamp(a.cutoff)
    raw, idrep = _history(a.alias_map)
    raw = raw[pd.to_datetime(raw["date"]).dt.normalize() < cutoff]
    feat = feature_frame(raw, "v9_repaired", "none", None, "league")
    if pd.to_datetime(feat["date"]).max() >= cutoff:
        raise SystemExit("a training row is on/after the cutoff")
    meta = {"v9_commit": _commit(), "versions": _versions(), "source_sha256": _source_digest(),
            "training_cutoff": str(cutoff.date()), "identity_report": idrep, "payloads": {}}
    for t in TARGETS:
        p = train_track(feat, "v9_repaired", "none", "standard", t)
        p["research"]["arm"] = "V9_REPAIRED"
        p["research"]["training_cutoff"] = str(cutoff.date())
        path = save_research_payload(p, out / f"V9_REPAIRED_standard_{t}.pkl")
        meta["payloads"][t] = {"file": path.name, "feature_cols": list(p.get("feature_cols") or []),
                               "rows": int(p["research"]["rows"]),
                               "served_holdout_metrics": p.get("served_holdout_metrics")}
    std = feat[feat["league"].isin(config.STANDARD_FORMAT_LEAGUES)]
    std = std[std["home_goals"].notna() & std["away_goals"].notna()].copy()
    tot = std["home_goals"] + std["away_goals"]
    std["y_OU25"] = (tot > 2.5).astype(float)
    std["y_BTTS"] = ((std["home_goals"] > 0) & (std["away_goals"] > 0)).astype(float)
    std["y_OU15"] = (tot > 1.5).astype(float)
    keep = [c for c in std.columns if not c.startswith("_") and std[c].dtype != object
            or c in ("league", "home_team", "away_team", "row_source")]
    std[keep].to_parquet(out / "frame_std.parquet", index=False)
    meta["frame_std_rows"] = int(len(std))
    (out / "meta.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in meta.items() if k != "identity_report"}, indent=1, default=str))


def cmd_features(a) -> None:
    import numpy as np
    import pandas as pd
    import config
    from src.features_repaired import build_upcoming_features_repaired
    from src.model import predict_proba
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    board = pd.read_csv(a.board)
    hist, _ = _history(a.alias_map)
    meta = {"v9_commit": _commit(), "versions": _versions(), "source_sha256": _source_digest()}
    if board.empty:
        feats = board.copy()
    else:
        ident = board[["row_key", "date", "league", "home_team", "away_team"]].copy()
        feats = build_upcoming_features_repaired(ident, hist, price_mode="none", team_scope="league")
        if len(feats) != len(board) or list(feats["row_key"]) != list(board["row_key"]):
            raise SystemExit("upcoming feature rows do not line up with the board")
        for t in TARGETS:
            with open(Path(a.payloads) / f"V9_REPAIRED_standard_{t}.pkl", "rb") as f:
                pay = pickle.load(f)
            recipe = pay.get("recipe") or (pay.get("research") or {}).get("recipe")
            if recipe != "v9_repaired" or not pay.get("imputer"):
                raise SystemExit(f"{t}: payload is not a v9_repaired payload with a persisted imputer")
            feats[f"p_V9_REPAIRED_{t}"] = predict_proba(feats, payload=pay).to_numpy(float)
        feats["no_form_data"] = feats[list(FORM)].isna().any(axis=1)
    feats.to_parquet(out / "upcoming.parquet", index=False)
    h = hist[hist["league"].isin(config.STANDARD_FORMAT_LEAGUES) & hist["home_goals"].notna()
             & hist["away_goals"].notna()].copy()
    h["date"] = pd.to_datetime(h["date"]).dt.normalize()
    h = h[h["date"] >= h["date"].max() - pd.Timedelta(days=730)]
    h["y_OU25"] = ((h["home_goals"] + h["away_goals"]) > 2.5).astype(float)
    h[["league", "date", "home_team", "away_team", "y_OU25"]].to_parquet(out / "played.parquet", index=False)
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"upcoming rows {len(feats)}; played rows {len(h)}; v9 {meta['v9_commit'][:12]}")


def cmd_results(a) -> None:
    import pandas as pd
    import config
    hist, _ = _history(a.alias_map)
    hist["date"] = pd.to_datetime(hist["date"]).dt.normalize()
    r = hist[hist["league"].isin(config.STANDARD_FORMAT_LEAGUES) & (hist["date"] >= pd.Timestamp(a.since))
             & hist["home_goals"].notna() & hist["away_goals"].notna()]
    r[["league", "date", "home_team", "away_team", "home_goals", "away_goals"]].to_csv(a.out, index=False)
    print(f"played standard rows since {a.since}: {len(r)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--out", required=True)
    t.add_argument("--alias-map", required=True)
    t.add_argument("--cutoff", required=True)
    f = sub.add_parser("features")
    f.add_argument("--board", required=True)
    f.add_argument("--payloads", required=True)
    f.add_argument("--alias-map", required=True)
    f.add_argument("--out", required=True)
    r = sub.add_parser("results")
    r.add_argument("--since", required=True)
    r.add_argument("--alias-map", required=True)
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    import logging
    logging.basicConfig(level=logging.WARNING)
    {"train": cmd_train, "features": cmd_features, "results": cmd_results}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())

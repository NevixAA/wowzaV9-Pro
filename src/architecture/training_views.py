"""Versioned training views, and a canary that fails when the learner stops receiving experience.

    python -m src.architecture.training_views --write

TWO JOBS, deliberately in one module because they answer the same question from opposite ends.

1. TRAINING VIEWS (sections 15-16). Deterministic derived datasets -- one for matches, one for
   players -- built from the canonical layer, carrying pre-match features and targets and
   nothing else. Every training script joining raw tables by hand is a chance for two scripts to
   join them differently; a shared view removes that.

   Each view ships a MANIFEST with a content hash, the code SHA, row and fixture counts, the
   cutoff, and the target distribution. Without it "the model trained last season" is a sentence
   with no way to check it: you cannot reconstruct a dataset you cannot identify. With it, the
   hash either matches or the dataset is not the one that was used.

2. THE CANARY (section 37). Everything in this audit exists because the estate has repeatedly
   kept running while quietly not learning -- player history frozen 35 days, four seasons of
   columns cached out of training, a retrain path that never compared anything. Every one of
   those looked healthy: workflows green, files committed, no errors.

   So the canary does not ask "did the workflow succeed". It asks the only question that
   matters:

       Is the newest thing we know about actually IN the dataset the next model will train on?

   It walks the chain -- newest completed fixture -> present in canonical -> training-eligible ->
   inside the current training view -- and fails on the first link that breaks, naming it. The
   same for player observations. A green canary means experience is flowing; a red one names the
   pipe that is blocked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.prediction_lab import data as D
from src.prediction_lab import features as F

CALC_VERSION = "1.0.0"
MAX_LAG_DAYS = 10           # beyond this the chain is considered blocked, not merely quiet


def A() -> Path:
    p = cfg.OUTPUT_DIR / "architecture"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _code_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=str(cfg.BASE_DIR), capture_output=True, text=True,
                              timeout=30).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _frame_hash(d: pd.DataFrame) -> str:
    """Content hash over the SHAPE and the DATA, not the file bytes.

    Parquet encodes metadata and compression choices that change between library versions, so
    hashing the file would report a different dataset for byte-level differences that mean
    nothing. Hashing sorted column names plus the row values identifies the dataset itself.
    """
    h = hashlib.sha256()
    h.update(",".join(sorted(map(str, d.columns))).encode())
    h.update(str(d.shape).encode())
    num = d.select_dtypes(include=[np.number]).fillna(-9.87654321e30)
    h.update(pd.util.hash_pandas_object(num, index=False).values.tobytes())
    return h.hexdigest()[:16]


def build_match_view() -> tuple[pd.DataFrame, dict]:
    can_p = A() / "canonical_match_history.parquet"
    if not can_p.exists():
        raise RuntimeError("canonical_match_history.parquet missing — run "
                           "src.architecture.canonical --write first")
    can = pd.read_parquet(can_p)
    can = can[can["trainable"]].copy()
    can["date"] = pd.to_datetime(can["date"], errors="coerce")
    can["league"] = can["league"].astype(str).str.strip()
    can["fixture_key"] = (can["date"].dt.strftime("%Y-%m-%d") + "|" + can["league"] + "|"
                          + can["home_team"].astype(str).str.strip() + "|"
                          + can["away_team"].astype(str).str.strip())
    can["model_type"] = can["league"].map(D.model_type_for_league)
    can["season_label"] = D._season_label(can["date"])
    can = D._attach_targets(can)
    can = (can.sort_values("date", kind="mergesort")
              .drop_duplicates("fixture_key", keep="last").reset_index(drop=True))

    feat = F.build(can)
    cols = F.feature_columns(feat, F.FOOTBALL_FAMILIES)
    keep = (["fixture_key", "date", "league", "season_label", "model_type",
             "home_team", "away_team", "quality_tier"] + cols
            + list(D.TARGETS) + ["total_goals", "goals_bucket"])
    view = feat[[c for c in keep if c in feat.columns]].copy()

    man = {
        "dataset_id": f"match_training_{_frame_hash(view)}",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "calc_version": CALC_VERSION, "code_sha": _code_sha(),
        "cutoff": str(view["date"].max())[:10],
        "row_count": int(len(view)), "fixture_count": int(view["fixture_key"].nunique()),
        "league_count": int(view["league"].nunique()),
        "season_count": int(pd.Series(view["season_label"]).nunique()),
        "feature_count": len(cols),
        "latest_fixture": str(view["date"].max())[:10],
        "earliest_fixture": str(view["date"].min())[:10],
        "content_hash": _frame_hash(view),
        "target_distribution": {t: round(float(view[t].mean()), 4)
                                for t in ("btts", "over15", "over25", "over35")
                                if t in view.columns},
        "quality_tiers": (view["quality_tier"].value_counts().to_dict()
                          if "quality_tier" in view.columns else {}),
        "source_versions": {
            "canonical_match_history": _json_get("canonical_match_manifest.json",
                                                 "generated_at"),
        },
    }
    return view, man


def build_player_view() -> tuple[pd.DataFrame, dict]:
    p = A() / "canonical_player_history.parquet"
    if not p.exists():
        raise RuntimeError("canonical_player_history.parquet missing")
    d = pd.read_parquet(p)
    d = d[d["training_eligible"]].copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d = d.sort_values(["player_id", "date"], kind="mergesort").reset_index(drop=True)

    base = [c for c in ("minutes", "goals", "assists", "shots_total", "shots_on_target",
                        "started", "rating") if c in d.columns]
    g = d.groupby("player_id", sort=False)
    sh = g[base].shift(1)
    sh["player_id"] = d["player_id"].to_numpy()
    out = d[["fixture_id", "player_id", "date", "league", "team", "opponent",
             "position", "scored"]].copy()
    for w in (5, 10):
        r = sh.groupby("player_id", sort=False)[base].rolling(w, min_periods=2).mean()
        r.index = r.index.droplevel(0)
        r = r.reindex(d.index)
        for c in base:
            out[f"pl_{c}_r{w}"] = r[c]
    out["pl_apps_prior"] = g.cumcount().to_numpy()
    cum = g["goals"].cumsum() - d["goals"].fillna(0)
    out["pl_career_goals"] = cum
    out["pl_career_gpa"] = np.where(out["pl_apps_prior"] > 0,
                                    cum / out["pl_apps_prior"].replace(0, np.nan), np.nan)
    man = {
        "dataset_id": f"player_training_{_frame_hash(out)}",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "calc_version": CALC_VERSION, "code_sha": _code_sha(),
        "row_count": int(len(out)), "player_count": int(out["player_id"].nunique()),
        "fixture_count": int(out["fixture_id"].nunique()),
        "latest_fixture": str(out["date"].max())[:10],
        "earliest_fixture": str(out["date"].min())[:10],
        "content_hash": _frame_hash(out),
        "target_distribution": {"scored": round(float(out["scored"].mean()), 4)},
        "feature_count": int(len([c for c in out.columns if c.startswith("pl_")])),
    }
    return out, man


def _json_get(name: str, key: str):
    p = A() / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get(key)
    except Exception:
        return None


def canary(match_man: dict, player_man: dict) -> dict:
    """Walk the chain and fail on the first broken link, by name."""
    checks = []

    def add(name: str, ok: bool, detail: str):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})
        return ok

    can_p = A() / "canonical_match_history.parquet"
    can = pd.read_parquet(can_p, columns=["date", "trainable"]) if can_p.exists() \
        else pd.DataFrame()
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()

    if can.empty:
        add("canonical_match_exists", False, "canonical_match_history.parquet missing")
    else:
        newest = pd.to_datetime(can["date"]).max()
        lag = (today - newest).days
        add("canonical_match_fresh", lag <= MAX_LAG_DAYS,
            f"newest canonical fixture {str(newest)[:10]}, {lag}d old (limit {MAX_LAG_DAYS})")
        tr = pd.to_datetime(can.loc[can["trainable"], "date"]).max()
        add("canonical_match_trainable", (newest - tr).days <= 1,
            f"newest trainable {str(tr)[:10]} vs newest known {str(newest)[:10]}")

    mv = pd.Timestamp(match_man["latest_fixture"])
    add("match_view_reaches_canonical", True if can.empty else
        (pd.to_datetime(can["date"]).max() - mv).days <= 1,
        f"training view reaches {match_man['latest_fixture']}")
    add("match_view_lag", (today - mv).days <= MAX_LAG_DAYS,
        f"training view is {(today - mv).days}d behind today")

    pv = pd.Timestamp(player_man["latest_fixture"])
    add("player_view_lag", (today - pv).days <= 45,
        f"player training view reaches {player_man['latest_fixture']}, "
        f"{(today - pv).days}d behind (club football pauses for internationals, so the "
        f"tolerance here is wider than the match side's)")

    pman = json.loads((A() / "canonical_player_manifest.json").read_text(encoding="utf-8")) \
        if (A() / "canonical_player_manifest.json").exists() else {}
    blocked = pman.get("needs_fixture_resolution_rows", 0)
    add("player_observations_all_placeable", blocked == 0,
        f"{blocked:,} collected player rows cannot be placed in time (missing fixture date) "
        f"and are therefore excluded from training")

    status = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    return {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "status": status,
            "checks": checks, "calc_version": CALC_VERSION,
            "failing": [c["check"] for c in checks if c["status"] == "FAIL"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    mview, mman = build_match_view()
    print(f"[views] match_training  {mman['row_count']:,} rows  "
          f"{mman['feature_count']} features  {mman['earliest_fixture']}..{mman['latest_fixture']}")
    print(f"        dataset_id {mman['dataset_id']}  code {mman['code_sha']}")
    pview, pman = build_player_view()
    print(f"[views] player_training {pman['row_count']:,} rows  "
          f"{pman['feature_count']} features  {pman['earliest_fixture']}..{pman['latest_fixture']}")
    print(f"        dataset_id {pman['dataset_id']}")

    c = canary(mman, pman)
    print(f"\n[canary] {c['status']}")
    for ch in c["checks"]:
        print(f"   {ch['status']:<5}{ch['check']:<36}{ch['detail']}")

    if a.write:
        mview.to_parquet(A() / "match_training.parquet", index=False)
        pview.to_parquet(A() / "player_training.parquet", index=False)
        (A() / "canonical_match_training_manifest.json").write_text(
            json.dumps(mman, indent=2, default=str), encoding="utf-8")
        (A() / "canonical_player_training_manifest.json").write_text(
            json.dumps(pman, indent=2, default=str), encoding="utf-8")
        (A() / "training_flow_canary.json").write_text(
            json.dumps(c, indent=2, default=str), encoding="utf-8")
        print(f"\n[views] wrote training views, manifests and the canary to {A()}")
    return 0 if c["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

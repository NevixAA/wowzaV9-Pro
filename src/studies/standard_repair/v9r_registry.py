"""Immutable registry for POST-REPAIR forward experiments (STD-V9R-*) and their first-sight rows.

registry/standard_repair/v9r_experiments.json
    One entry per ID, written once. Freezes model version, feature manifest, imputer, calibrator,
    selection rule, market source, min N, min matchdays and the primary metric, plus a content hash.
    Re-registering an ID with identical content is a no-op; with ANY different content it is refused —
    a changed hypothesis is a new ID (…-V2). Nothing here is ever edited after the fact.
output/standard_repair/v9r_first_sight.csv
    Append-only. A (experiment_id, fixture_key, market, side) row, once written, can never change:
    a later observation of the same fixture is not a first sight. Rows observed before the
    experiment's frozen_at are refused (that would be retrospective evidence).

Kept separate from the PRE_REPAIR registry (registry/standard_repair/experiments.json): forward
evidence before and after the repair is never pooled (trusted.forward_phase).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

REG = cfg.REGISTRY_DIR / "standard_repair" / "v9r_experiments.json"
FS = cfg.OUTPUT_DIR / "standard_repair" / "v9r_first_sight.csv"
REQUIRED = ("experiment_id", "league", "market", "side", "model_version", "feature_manifest", "imputer",
            "calibrator", "selection_rule", "market_source", "min_n", "min_matchdays", "primary_metric")
FS_KEY = ["experiment_id", "fixture_key", "market", "side"]


class Immutable(RuntimeError):
    pass


def _hash(spec: dict) -> str:
    body = {k: v for k, v in spec.items() if k not in ("frozen_at", "content_sha256")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def load(path: Path = REG) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"experiments": {}}


def register(spec: dict, path: Path = REG) -> dict:
    miss = [k for k in REQUIRED if k not in spec]
    if miss:
        raise ValueError(f"registration missing {miss}")
    if not str(spec["experiment_id"]).startswith("STD-V9R-"):
        raise ValueError("post-repair experiment ids start with STD-V9R-")
    reg = load(path)
    eid = spec["experiment_id"]
    h = _hash(spec)
    if eid in reg["experiments"]:
        if reg["experiments"][eid]["content_sha256"] != h:
            raise Immutable(f"{eid} is frozen; a changed experiment needs a new id")
        return reg["experiments"][eid]
    entry = dict(spec, frozen_at=spec.get("frozen_at") or pd.Timestamp.now(tz="UTC").isoformat(), content_sha256=h,
                 phase="POST_REPAIR_FORWARD")
    reg["experiments"][eid] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(reg, indent=1, default=str), encoding="utf-8")
    return entry


def append_first_sight(rows: pd.DataFrame, path: Path = FS, reg_path: Path = REG) -> int:
    """Append new first-sight rows; existing keys are never rewritten. Returns rows added."""
    reg = load(reg_path)["experiments"]
    r = rows.copy()
    unknown = set(r["experiment_id"]) - set(reg)
    if unknown:
        raise ValueError(f"unregistered experiments {sorted(unknown)}")
    frozen = r["experiment_id"].map(lambda e: pd.Timestamp(reg[e]["frozen_at"]))
    seen = pd.to_datetime(r["first_seen_at"], utc=True)
    if (seen < frozen).any():
        raise Immutable("first-sight rows observed before the experiment was frozen are retrospective")
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=list(r.columns))
    if len(old):
        k_old = set(map(tuple, old[FS_KEY].astype(str).to_numpy()))
        r = r[[tuple(x) not in k_old for x in r[FS_KEY].astype(str).to_numpy()]]
    r = r.drop_duplicates(FS_KEY, keep="first")
    if r.empty:
        return 0
    out = pd.concat([old, r], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return int(len(r))


def select_track(df: pd.DataFrame, track: str) -> pd.DataFrame:
    """Rows of exactly one model track. Track-specific side-market work must go through this: pooled
    Std+NF rows can never silently enter a track-specific test (owner brief P0 #9)."""
    if "track" not in df:
        raise ValueError("frame has no `track` column; cannot prove track isolation")
    out = df[df["track"].astype(str) == track]
    assert_single_track(out, track)
    return out


def assert_single_track(df: pd.DataFrame, track: str) -> None:
    got = set(df["track"].astype(str).unique()) if "track" in df else {"<none>"}
    if got - {track}:
        raise ValueError(f"track-specific rows for {track!r} contain {sorted(got - {track})}")

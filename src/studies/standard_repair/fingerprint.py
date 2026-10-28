"""Benchmark FINGERPRINTS and the STALE rule (owner brief 2026-10-28, P0 #10 / "artifact freshness").

Every Standard research output carries `stamp()`: generated_at, data_cutoff, v9_commit, pro_commit and
the content fingerprints below. `compare(stamped, current)` decides whether an output still describes
the data and code that exist now:

    CURRENT   every CRITICAL fingerprint matches
    BEHIND    nothing that the result was computed on changed, but newer fixtures exist after its
              data_cutoff (the frame hash is taken over rows <= data_cutoff only, so new matches alone
              never invalidate a result — they make it behind, and the weekly rebuild catches up)
    STALE     a CRITICAL fingerprint differs: historical rows, an input file, the feature schema, the
              team canonicaliser, the imputer, the price source or the model recipe changed. A STALE
              result must never be shown as current.

Commits are recorded for provenance but are NOT critical: v9 auto-commits every few minutes and Pro
every half hour, so a SHA comparison would mark everything STALE forever and teach people to ignore it.
Content hashes are what can actually move a number.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

REBUILD = cfg.BASE_DIR / "experiments" / "standard_repair_2026_10" / "rebuild"
SCHEMA = "standard_repair_fingerprint/1"
CRITICAL = ("frame_hash_at_cutoff", "raw_fd_finished_hash", "archive_hash", "feature_schema_version",
            "team_canon_version", "imputer_version", "price_source_version", "model_recipe_version",
            "research_code_hash")
INFO = ("v9_commit", "pro_commit", "raw_fd_current_hash", "frame_rows_after_cutoff")
#: bumped by hand when the price-labelling rules in prices.py change meaning
PRICE_SOURCE_VERSION = "price_audit/1.0"
#: until R1's v9_repaired recipe exists the only recipe/imputer are v9's own (batch median, P0 #1)
DEFAULT_IMPUTER = "v9_batch_median"
DEFAULT_RECIPE = "legacy_v9"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str | None:
    p = Path(p)
    return sha256_bytes(p.read_bytes()) if p.exists() else None


def combine(parts: dict) -> str:
    return sha256_bytes(json.dumps(parts, sort_keys=True, default=str).encode())[:16]


def frame_hash(df: pd.DataFrame, cutoff: str | None = None, cols: list[str] | None = None) -> tuple[str, int]:
    """Content hash of the STANDARD frame rows dated <= cutoff (all rows when None). Order-independent.
    Returns (hash, rows after cutoff)."""
    d = df[df["track"].astype(str) == "standard"] if "track" in df else df
    dt = pd.to_datetime(d["date"])
    after = 0
    if cutoff:
        after = int((dt > pd.Timestamp(cutoff)).sum())
        d = d[dt <= pd.Timestamp(cutoff)]
    use = cols or [c for c in d.columns if not str(c).startswith("_")]
    use = sorted(c for c in use if c in d.columns)
    d = d[use].copy()
    d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
    d = d.astype(str).sort_values(["date", "league", "home_team", "away_team"]) if {"league", "home_team", "away_team"} <= set(d) else d.astype(str)
    h = pd.util.hash_pandas_object(d, index=False).to_numpy().tobytes()
    return sha256_bytes(h)[:16], after


def _git(path: Path, *args) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:                                                          # noqa: BLE001
        return ""


def research_code_hash() -> str:
    here = Path(__file__).resolve().parent
    # newline-normalised: a CRLF workstation checkout and an LF CI checkout of one commit agree
    return combine({p.name: sha256_bytes(p.read_bytes().replace(bytes([13, 10]), bytes([10])))
                    for p in sorted(here.glob("*.py"))})


def current(frame: pd.DataFrame | None = None, manifest: dict | None = None, data_cutoff: str | None = None,
            imputer_version: str | None = None, model_recipe_version: str | None = None,
            fd_dir: Path | None = None) -> dict:
    """The fingerprint of what exists NOW (rebuild dir + v9 checkout + this code)."""
    manifest = manifest if manifest is not None else load_manifest()
    if frame is None and (REBUILD / "frame.parquet").exists():
        frame = pd.read_parquet(REBUILD / "frame.parquet")
    if data_cutoff is None and frame is not None:
        data_cutoff = str(pd.to_datetime(frame.loc[frame["track"].astype(str) == "standard", "date"]).max().date())
    fh, after = (frame_hash(frame, data_cutoff) if frame is not None else (None, None))
    inp = (manifest or {}).get("inputs_sha256", {})
    fd = (manifest or {}).get("fd_dir_sha256") or {}
    if not fd and fd_dir is not None:
        fd = {f.name: sha256_file(f) for f in sorted(Path(fd_dir).glob("*.csv"))}
    live = str((manifest or {}).get("live_season_start", ""))
    cur_tag = (live[2:] + str(int(live) + 1)[2:]) if live.isdigit() else "????"
    finished = {k: v for k, v in fd.items() if not k.endswith(f"_{cur_tag}.csv")}
    current_fd = {k: v for k, v in fd.items() if k.endswith(f"_{cur_tag}.csv")}
    return {
        "schema": SCHEMA,
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "data_cutoff": data_cutoff,
        "v9_commit": (manifest or {}).get("v9_commit") or _git(cfg.V9_LOCAL, "rev-parse", "HEAD"),
        "pro_commit": _git(cfg.BASE_DIR, "rev-parse", "HEAD"),
        "frame_hash_at_cutoff": fh,
        "frame_rows_after_cutoff": after,
        "raw_fd_finished_hash": combine(finished) if finished else None,
        "raw_fd_current_hash": combine(current_fd) if current_fd else None,
        "archive_hash": (inp.get("output/backtest_all_leagues.csv") or "")[:16] or None,
        "feature_schema_version": combine({"serving": (manifest or {}).get("serving_feature_cols"),
                                           "fe": inp.get("src/feature_engineering.py")}),
        "team_canon_version": combine({"team_names": inp.get("src/team_names.py"),
                                       "data_loader": inp.get("src/data_loader.py")}),
        "imputer_version": imputer_version or DEFAULT_IMPUTER,
        "price_source_version": combine({"rules": PRICE_SOURCE_VERSION, "fd": finished,
                                         "captures": inp.get("output/standard_sidemarket_odds_history.csv")
                                         and "v9_captures"}),
        "model_recipe_version": model_recipe_version or DEFAULT_RECIPE,
        "research_code_hash": research_code_hash(),
        "frame_build_version": (manifest or {}).get("frame_build_version"),
        "frame_build_mode": (manifest or {}).get("mode"),
    }


def load_manifest() -> dict:
    p = REBUILD / "frame_manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def compare(stamped: dict | None, now: dict) -> dict:
    """CURRENT / BEHIND / STALE (see module doc). A missing stamp is STALE, never CURRENT."""
    if not stamped:
        return {"status": "STALE", "reason": "output carries no fingerprint", "mismatched": list(CRITICAL)}
    bad = [k for k in CRITICAL if stamped.get(k) != now.get(k)]
    if bad:
        return {"status": "STALE", "reason": "critical input changed since this output was computed",
                "mismatched": bad}
    if (now.get("frame_rows_after_cutoff") or 0) > 0:
        return {"status": "BEHIND", "reason": f"{now['frame_rows_after_cutoff']} newer fixtures after data_cutoff",
                "mismatched": []}
    return {"status": "CURRENT", "reason": "all critical fingerprints match", "mismatched": []}


def stamp_obj(obj: dict, fp: dict) -> dict:
    out = dict(obj)
    out["fingerprint"] = fp
    for k in ("generated_at", "data_cutoff", "v9_commit", "pro_commit"):
        out.setdefault(k, fp.get(k))
    out.setdefault("frame_hash", fp.get("frame_hash_at_cutoff"))
    out.setdefault("feature_version", fp.get("feature_schema_version"))
    out.setdefault("model_recipe_version", fp.get("model_recipe_version"))
    out.setdefault("price_source_version", fp.get("price_source_version"))
    return out


def stamp_csv(df: pd.DataFrame, fp: dict) -> pd.DataFrame:
    """CSV outputs carry the same stamp as columns, so a lone CSV is still self-describing."""
    d = df.copy()
    for k in ("generated_at", "data_cutoff", "v9_commit", "pro_commit"):
        d[k] = fp.get(k)
    d["frame_hash"] = fp.get("frame_hash_at_cutoff")
    d["feature_version"] = fp.get("feature_schema_version")
    d["model_recipe_version"] = fp.get("model_recipe_version")
    d["price_source_version"] = fp.get("price_source_version")
    return d

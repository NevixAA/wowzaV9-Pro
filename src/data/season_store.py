"""
Append-only, run-partitioned season store.
==========================================
Layout:

    data/season_2026_27/<table>/dt=YYYY-MM-DD/run=<run_id>.parquet

WHY run-partitioned, and not one file per table:

v9 commits shared CSVs from multiple workflows and reconciles with
`git pull --rebase --autostash -X ours`. During a rebase `ours` is upstream, so the run that
pushes second silently discards its own rows — `output/bets_ledger.csv` has three concurrent
writers, two of them with no concurrency group at all (WORKFLOW_MAP.md section 2). Prompt 2
section 7 ("never overwrite repeated model predictions") is therefore not achievable on that
storage model.

Partitioning by run_id removes the conflict surface entirely rather than reducing it: two
executions cannot target the same path, so there is nothing to merge and nothing to discard.
Append is the only operation this module supports — there is deliberately no update or delete.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg


class SchemaError(ValueError):
    """Raised when an importer hands the store a frame it cannot honestly store."""


# ── required columns per table ────────────────────────────────────────────────
# Deliberately minimal: the key that makes a row joinable and the timestamp that makes it
# interpretable. Importers may add any extra columns; they are preserved as-is.
REQUIRED: dict[str, tuple[str, ...]] = {
    "fixtures":          ("fixture_key", "league", "match_date", "home_team", "away_team"),
    "model_snapshots":   ("fixture_key", "market", "model_prob"),
    "market_snapshots":  ("fixture_key", "market", "odds", "odds_source"),
    "feature_snapshots": ("fixture_key",),
    "signals":           ("fixture_key", "market", "signal_tier", "deployment_mode"),
    "settlements":       ("fixture_key", "market", "result"),
    # Outcome, not bet result: `y` is "did OVER 2.5 happen". No `result` column, because most
    # of these fixtures were never bet and inventing one would be a fabricated value.
    "settlements_backfill": ("fixture_key", "market", "y"),
    "clv":               ("fixture_key", "market"),
    "player_props":      ("fixture_key", "market", "player_name"),
    "live_signals":      ("fixture_key",),
    "data_quality":      ("check", "status"),
}


def _pro_git_sha() -> str:
    """Pro's own code version, so any row can be traced to the logic that made it."""
    env = os.getenv("GITHUB_SHA")
    if env:
        return env[:12]
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                             cwd=cfg.BASE_DIR, capture_output=True, text=True, timeout=15)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


_PRO_SHA = None


def pro_git_sha() -> str:
    global _PRO_SHA
    if _PRO_SHA is None:
        _PRO_SHA = _pro_git_sha()
    return _PRO_SHA


def partition_path(table: str, dt: str, rid: str, season: str | None = None) -> Path:
    if table not in cfg.TABLES:
        raise SchemaError(f"unknown table {table!r}; expected one of {cfg.TABLES}")
    root = cfg.DATA_DIR / (season or cfg.season_label())
    return root / table / f"dt={dt}" / f"run={rid}.parquet"


def append(
    table: str,
    df: pd.DataFrame,
    *,
    source: str,
    observed_at: str | None = None,
    source_sha: str | None = None,
    rid: str | None = None,
    partition_on: str | None = None,
) -> list[Path]:
    """Append `df` to `table`, one parquet per (date partition, run).

    `observed_at` is when the fact was true in the world — the v9 commit timestamp when
    backfilling from git history, or now for a live capture. It is NOT the ingest time; both
    are stored, because conflating them is what makes leakage undetectable later.

    Partitioning defaults to the OBSERVATION date, not `match_date`. Partitioning on
    match_date looked natural but produced 1,690 files per run, because v9's odds histories
    span months of fixtures — a season of that is millions of tiny parquet files. Observation
    date gives exactly one file per (table, run); `match_date` remains a column, and at this
    row count a full scan is trivial. Pass `partition_on` explicitly only when a table really
    should be laid out by one of its own date columns.

    Returns the paths written. Refuses to overwrite an existing partition file.
    """
    if df is None or df.empty:
        return []

    missing = [c for c in REQUIRED.get(table, ()) if c not in df.columns]
    if missing:
        raise SchemaError(f"{table}: missing required column(s) {missing}")

    out = df.copy()
    rid = rid or cfg.run_id()
    now = cfg.utc_now_iso()
    out["ingested_at"] = now
    # A PER-ROW observed_at already set by the importer wins: since 2026-08-17 v9 stamps
    # `generated_at` into predictions.csv, so a snapshot can carry the moment the board was
    # actually produced rather than the moment Pro happened to read it. Falls back to the
    # caller's value (git-history backfill) and finally to now.
    if "observed_at" in out.columns and out["observed_at"].notna().any():
        out["observed_at"] = out["observed_at"].fillna(observed_at or now)
    else:
        out["observed_at"] = observed_at or now
    out["run_id"] = rid
    out["source"] = source
    out["source_sha"] = source_sha or ""
    out["pro_git_sha"] = pro_git_sha()

    if partition_on and partition_on in out.columns:
        keys = (pd.to_datetime(out[partition_on], errors="coerce")
                .dt.strftime("%Y-%m-%d").fillna("unknown"))
    else:
        # Observation date: one file per (table, run). A git-history backfill lands under the
        # day the fact was true, because observed_at carries the commit timestamp.
        keys = pd.Series([str(out["observed_at"].iloc[0])[:10]] * len(out), index=out.index)

    written: list[Path] = []
    for dt, chunk in out.groupby(keys, sort=True):
        p = partition_path(table, str(dt), rid)
        if p.exists():
            raise SchemaError(
                f"refusing to overwrite {p}. The store is append-only; a repeated "
                f"(table, dt, run_id) means the same run wrote twice — give the second "
                f"write its own run_id."
            )
        p.parent.mkdir(parents=True, exist_ok=True)
        chunk.to_parquet(p, index=False)
        written.append(p)
    return written


def read(table: str, season: str | None = None) -> pd.DataFrame:
    """Read every partition of a table. Returns an empty frame when nothing is stored."""
    root = cfg.DATA_DIR / (season or cfg.season_label()) / table
    files = sorted(root.glob("dt=*/run=*.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def stats(season: str | None = None) -> dict[str, dict]:
    """Per-table row counts, partition counts and date span — the collector's health output."""
    root = cfg.DATA_DIR / (season or cfg.season_label())
    out: dict[str, dict] = {}
    for t in cfg.TABLES:
        files = sorted((root / t).glob("dt=*/run=*.parquet"))
        if not files:
            out[t] = {"rows": 0, "partitions": 0, "runs": 0, "first_dt": None, "last_dt": None}
            continue
        dts = sorted({f.parent.name.split("=", 1)[1] for f in files})
        rows = 0
        for f in files:
            # Read row count from parquet FOOTER METADATA — exact and O(1) per file.
            # This used to be len(pd.read_parquet(f, columns=[])), which returns a frame with
            # no columns AND no rows: every table reported 0 rows while the store actually
            # held 68,625. A health check that under-reports to zero is worse than none,
            # because it makes a working collector look broken.
            try:
                import pyarrow.parquet as _pq
                rows += _pq.ParquetFile(f).metadata.num_rows
            except Exception:
                try:
                    rows += len(pd.read_parquet(f))
                except Exception:
                    pass
        out[t] = {
            "rows": rows,
            "partitions": len(files),
            "runs": len({f.name.split("=", 1)[1].removesuffix(".parquet") for f in files}),
            "first_dt": dts[0],
            "last_dt": dts[-1],
        }
    return out

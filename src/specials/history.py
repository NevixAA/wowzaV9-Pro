"""
v9's REPAIRED match history, read the way v9's own clean retrain reads it.

The specials tracker fits its score model and its league base rates on the same served frame v9's
Phase 2 retrain used: `src.data_loader.load_all_matches(force=True)` with the football-data download
switched off and the network blocked, so every row is a committed row with every loader correction
applied (identity, one-match dedupe, provider dates, history corrections). Nothing is re-derived here.

v9 has its own top-level `src` package, so it cannot be imported into Pro's process without
shadowing Pro's `src`. It runs in a SUBPROCESS with v9 as the working directory and returns a
parquet of six columns. Missing goals stay missing: such a row is dropped and COUNTED, never filled.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

COLUMNS = ["date", "league", "home_team", "away_team", "home_goals", "away_goals", "row_source"]

_EXPORT = r"""
import socket, sys
def _no_net(*a, **k):
    raise OSError("network blocked (specials history export reads committed data only)")
socket.socket.connect = _no_net
socket.create_connection = _no_net
from src import data_loader as DL
DL._ci_download_all = lambda have=None: []
DL._report_training_coverage = lambda out: None
raw = DL.load_all_matches(force=True)
cols = %r
raw[[c for c in cols if c in raw.columns]].to_parquet(sys.argv[1])
"""


def v9_sha(v9_root: Path | None = None) -> str | None:
    root = Path(v9_root or cfg.V9_LOCAL)
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True,
                           text=True, timeout=30)
        return r.stdout.strip() or None
    except Exception:                                           # noqa: BLE001
        return None


def export_v9_history(v9_root: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """(history frame, info). Raises when v9 is not checked out or its loader fails: a tracker that
    cannot read the repaired history has nothing honest to say, so it stops instead of guessing."""
    root = Path(v9_root or cfg.V9_LOCAL)
    if not (root / "src" / "data_loader.py").exists():
        raise FileNotFoundError(f"v9 data_loader not found under {root}; set V9_LOCAL")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "history.parquet"
        env = dict(os.environ, PYTHONPATH=str(root), PYTHONIOENCODING="utf-8",
                   PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, "-c", _EXPORT % (COLUMNS,), str(out)], cwd=str(root),
                           env=env, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not out.exists():
            tail = (r.stderr or r.stdout or "")[-2000:]
            raise RuntimeError(f"v9 history export failed (exit {r.returncode}): {tail}")
        h = pd.read_parquet(out)
    return clean_history(h, v9_sha=v9_sha(root))


def clean_history(h: pd.DataFrame, v9_sha: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Normalise types; drop (and count) rows without a 90-minute score, a league or a date."""
    missing = [c for c in COLUMNS[:6] if c not in h.columns]
    if missing:
        raise ValueError(f"history is missing columns {missing}")
    d = h.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce").dt.normalize()
    d["home_goals"] = pd.to_numeric(d["home_goals"], errors="coerce")
    d["away_goals"] = pd.to_numeric(d["away_goals"], errors="coerce")
    bad = d["date"].isna() | d["league"].isna() | d["home_goals"].isna() | d["away_goals"].isna()
    d = d[~bad].copy()
    d["home_goals"] = d["home_goals"].astype(int)
    d["away_goals"] = d["away_goals"].astype(int)
    d = d.sort_values(["league", "date"], kind="stable").reset_index(drop=True)
    info = {"rows": int(len(d)), "rows_dropped_incomplete": int(bad.sum()),
            "leagues": int(d["league"].nunique()), "v9_sha": v9_sha,
            "date_min": str(d["date"].min().date()) if len(d) else None,
            "date_max": str(d["date"].max().date()) if len(d) else None}
    return d, info

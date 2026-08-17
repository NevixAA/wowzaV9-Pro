"""
Read-only access to the v9 baseline.
====================================
Pro NEVER writes to v9. It reads v9's committed output, preferring a local clone when one is
present and falling back to public raw HTTP — the same unauthenticated pattern wowza-v11
already uses, so no credential is required.
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg


class SourceUnavailable(RuntimeError):
    """A v9 artifact could not be read. Never swallowed: a collector that silently reads
    nothing is the exact failure mode that hid two multi-day outages in v9."""


def v9_head_sha() -> str:
    """v9's commit sha, recorded on every imported row so a row can be traced to the exact
    baseline state that produced it."""
    if cfg.V9_LOCAL.exists():
        try:
            out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                                 cwd=cfg.V9_LOCAL, capture_output=True, text=True, timeout=20)
            if out.returncode == 0:
                return out.stdout.strip()
        except Exception:
            pass
    return "unknown"


def fetch_csv(rel_path: str, *, required: bool = True) -> pd.DataFrame:
    """Read a v9 CSV by repo-relative path, e.g. 'output/predictions.csv'.

    Local clone first, then raw HTTP. Everything is read as str: v9's CSVs mix blanks,
    'nan' strings and numbers in the same column, and letting pandas guess per-file has
    already produced silent dtype drift. Importers coerce explicitly.
    """
    local = cfg.V9_LOCAL / rel_path
    if local.exists():
        try:
            return pd.read_csv(local, dtype=str, keep_default_na=False, na_values=[""])
        except Exception as e:
            if required:
                raise SourceUnavailable(f"local read failed for {rel_path}: {e}") from e
            return pd.DataFrame()

    url = f"{cfg.V9_RAW_BASE}/{rel_path}"
    try:
        import requests
        r = requests.get(url, timeout=60)
        if r.status_code != 200:
            raise SourceUnavailable(f"HTTP {r.status_code} for {url}")
        return pd.read_csv(io.StringIO(r.text), dtype=str,
                           keep_default_na=False, na_values=[""])
    except SourceUnavailable:
        if required:
            raise
        return pd.DataFrame()
    except Exception as e:
        if required:
            raise SourceUnavailable(f"fetch failed for {url}: {e}") from e
        return pd.DataFrame()


def num(s: pd.Series) -> pd.Series:
    """Coerce to float, turning v9's blanks and 'nan' strings into real NaN.

    Invariant 9 in v9's CLAUDE.md: write NaN, never an invented number. Pro keeps that —
    a missing value stays missing rather than becoming a plausible-looking default.
    """
    return pd.to_numeric(s, errors="coerce")

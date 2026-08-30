"""
Read-only access to the v9 baseline.
====================================
Pro NEVER writes to v9. It reads v9's committed output, preferring a local clone when one is
present and falling back to public raw HTTP — the same unauthenticated pattern wowza-v11
already uses, so no credential is required.
"""
from __future__ import annotations

import hashlib
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


def v9_model_version() -> dict:
    """A STABLE identity for the frozen v9 models — Prompt 02 section 1.

    WHY THIS EXISTS

    v9 stamps its own `model_sha` into predictions.csv, and it is unusable as a version.
    `v9/src/provenance.py::_model_sha` hashes each file's **size and mtime**, not its contents,
    and a CI `git checkout` sets mtime to checkout time — so the stamp changes on every run even
    when the model bytes are identical. Measured 2026-08-30 over the same two-week window:

        commits that actually changed models/*.pkl      4
        distinct model_sha values in model_snapshots   95

    A version that changes 24x more often than the thing it versions cannot answer "was this
    prediction made by the frozen model", which is the question the whole prospective-validation
    phase rests on. It also makes "increment the version when a fix materially changes
    probabilities" meaningless, because the version increments constantly on its own.

    The stated reason for hashing size+mtime was that reading the .pkl files would add I/O to the
    5-minute predict path. Measured: 16 files, 12.2 MB, **46 ms**, once per process because the
    result is cached — 0.03% of a ~3 minute run. The cost was never the real constraint.

    WHY IT IS FIXED HERE AND NOT IN v9

    v9 is frozen (root CLAUDE.md invariant 3). Prompt 02 section 1 does permit provenance fixes,
    but it does not require them to be made in v9, and Pro already checks v9 out — so the same
    answer is available without opening the frozen repository at all. v9's own stamp is preserved
    untouched alongside this one, so the two remain comparable and nothing is rewritten.

    WHAT IT RETURNS

    A content digest over the committed model files. Content, not mtime: the bytes are identical
    in every clone, so the digest is the same on a runner, on a laptop, and in a year's time.
    Returns `{}` when the checkout is unavailable, and the caller flags the rows rather than
    inventing a version.
    """
    root = cfg.V9_LOCAL
    if not root.exists():
        return {}
    try:
        files = sorted((root / "models").glob("*.pkl"))
        if not files:
            return {}
        h = hashlib.sha1()
        total = 0
        for f in files:
            # The NAME is hashed too, so adding or renaming a model changes the version even if
            # the bytes of every other file are unchanged.
            h.update(f.name.encode("utf-8"))
            with open(f, "rb") as fh:
                for chunk in iter(lambda fh=fh: fh.read(1024 * 1024), b""):
                    h.update(chunk)
            total += f.stat().st_size
        return {"model_content_sha": h.hexdigest()[:12],
                "n_model_files": len(files),
                "model_bytes": total}
    except Exception:
        # Never fatal: a missing version is a flagged row, not a failed collection.
        return {}


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

    # Last-resort fallback. raw.githubusercontent.com rate-limits unauthenticated requests and
    # Pro's first live CI run died on HTTP 429, so a 429 is retried with backoff rather than
    # treated as fatal. CI should supply V9_LOCAL and never reach this path at all.
    import time
    url = f"{cfg.V9_RAW_BASE}/{rel_path}"
    last: Exception | None = None
    for attempt in range(4):
        try:
            import requests
            r = requests.get(url, timeout=60)
            if r.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"[v9_source] 429 for {rel_path}; retry {attempt + 1}/3 in {wait}s")
                last = SourceUnavailable(f"HTTP 429 for {url}")
                time.sleep(wait)
                continue
            if r.status_code != 200:
                raise SourceUnavailable(f"HTTP {r.status_code} for {url}")
            return pd.read_csv(io.StringIO(r.text), dtype=str,
                               keep_default_na=False, na_values=[""])
        except SourceUnavailable as e:
            last = e
            break
        except Exception as e:
            last = e
            time.sleep(3 * (attempt + 1))
    if required:
        raise SourceUnavailable(
            f"could not read v9 {rel_path} ({last}). Set V9_LOCAL to a wowza-betting "
            f"checkout to avoid raw-HTTP rate limits."
        ) from last
    return pd.DataFrame()


def num(s: pd.Series) -> pd.Series:
    """Coerce to float, turning v9's blanks and 'nan' strings into real NaN.

    Invariant 9 in v9's CLAUDE.md: write NaN, never an invented number. Pro keeps that —
    a missing value stays missing rather than becoming a plausible-looking default.
    """
    return pd.to_numeric(s, errors="coerce")

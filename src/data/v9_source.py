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
import re
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


# ── v9 ROLLING files (v9 src/rolling_store.py, 2026-10-22) ───────────────────────────────────────
# v9 stopped rewriting three append-only odds logs whole on every run (git re-stored ~100 MB per
# commit and the repo grew by GBs a week). The live file keeps its PATH but now holds only rows
# whose match_date >= today - 2; played matches move once into <stem>_archive/<YYYY-MM-DD>.csv
# beside it. A reader that needs the FULL history must read archive + live -- these helpers.
# Incremental readers (watermark on snapshot_ts) and "latest price" readers need only the live file.
ROLLING_FILES = ("output/book_odds_snapshots.csv", "output/player_prop_odds_history.csv")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def archive_rel_dir(rel_path: str) -> str:
    p = Path(rel_path)
    return (p.parent / f"{p.stem}_archive").as_posix()


def v9_archive_parts(rel_path: str, root: Path | None = None) -> list[Path]:
    adir = Path(root or cfg.V9_LOCAL) / archive_rel_dir(rel_path)
    if not adir.exists():
        return []
    return sorted(p for p in adir.glob("*.csv") if _DAY.match(p.stem))


def read_v9_all(rel_path: str, root: Path | None = None, **read_kw) -> pd.DataFrame:
    """LOCAL full history of a v9 rolling file: archive parts + live, exact duplicates dropped.

    For a file with no archive dir this is exactly `pd.read_csv(root / rel_path, **read_kw)`
    (no dedupe), so pointing an existing reader at it changes nothing until v9 rolls the file.
    Missing everything -> empty frame (callers already treat a missing file that way)."""
    root = Path(root or cfg.V9_LOCAL)
    parts = v9_archive_parts(rel_path, root)
    live = root / rel_path
    frames = [pd.read_csv(p, **read_kw) for p in parts]
    if live.exists():
        frames.append(pd.read_csv(live, **read_kw))
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates().reset_index(drop=True) if parts else out


def fetch_csv_all(rel_path: str, *, required: bool = True) -> pd.DataFrame:
    """`fetch_csv` for a v9 ROLLING file, archive included (all columns as str, like fetch_csv).

    Local clone first. Over HTTP the archive is listed through the GitHub contents API (one
    unauthenticated call) and each part fetched raw; if the listing fails the LIVE file alone is
    returned with a loud warning -- recent matches only, never a crash."""
    kw = dict(dtype=str, keep_default_na=False, na_values=[""])
    if (cfg.V9_LOCAL / rel_path).exists() or v9_archive_parts(rel_path):
        try:
            return read_v9_all(rel_path, **kw)
        except Exception as e:
            if required:
                raise SourceUnavailable(f"local read failed for {rel_path}: {e}") from e
            return pd.DataFrame()
    live = fetch_csv(rel_path, required=required)
    try:
        import requests
        r = requests.get(f"https://api.github.com/repos/{cfg.V9_REPO}/contents/"
                         f"{archive_rel_dir(rel_path)}", timeout=30)
        if r.status_code == 404:
            return live
        r.raise_for_status()
        names = sorted(x["name"] for x in r.json()
                       if x.get("name", "").endswith(".csv") and _DAY.match(x["name"][:-4]))
    except Exception as e:                                          # noqa: BLE001
        print(f"[v9_source] WARNING: archive listing for {rel_path} failed ({e}); "
              f"using the live file only (recent matches)")
        return live
    frames = [fetch_csv(f"{archive_rel_dir(rel_path)}/{n}", required=False) for n in names]
    frames = [f for f in frames + [live] if not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates().reset_index(drop=True)


def num(s: pd.Series) -> pd.Series:
    """Coerce to float, turning v9's blanks and 'nan' strings into real NaN.

    Invariant 9 in v9's CLAUDE.md: write NaN, never an invented number. Pro keeps that —
    a missing value stays missing rather than becoming a plausible-looking default.
    """
    return pd.to_numeric(s, errors="coerce")

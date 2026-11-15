"""Every committed v9 predictions.csv snapshot -> one row per fixture x market at FIRST SIGHT.

    python -m src.studies.valuable.snapshots --v9 <path to a wowza-betting clone>

v9 commits output/predictions.csv on every predict run. Its git history is therefore a real record of
what v9 saw at the time - every fixture, including candidates BELOW the VALUABLE floor that never became
tips, with BOTH sides' prices. Nothing here is reconstructed: each row carries the commit it came from.
A fixture enters at the first snapshot whose generated_at is before kickoff (pre-match only).
"""
from __future__ import annotations

import argparse
import io
import subprocess
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

OUT = cfg.BASE_DIR / "experiments" / "valuable_2026_10"
KEEP = ["league", "date", "kickoff_utc", "home_team", "away_team", "model_type", "model_version", "generated_at",
        "p_over25", "odds_over25", "odds_under25", "edge_over", "edge_under", "tier_over", "tier_under",
        "best_side", "signal_tier", "drift_signal", "p_btts", "odds_btts", "odds_btts_no", "btts_overround",
        "btts_fair_yes", "p_over15", "odds_over15", "p_over35", "odds_over35", "no_form_data",
        "home_scored_last5", "away_scored_last5", "n_books", "bookmaker_count", "odds_n_books"]


MANIFEST = OUT / "prematch_snapshots_manifest.json"


def _git(v9: str, *args) -> bytes:
    return subprocess.run(["git", "-C", v9, *args], capture_output=True, check=True).stdout


def write_manifest(parquet: "Path", s: pd.DataFrame, shas: list[str], v9: str) -> dict:
    """REPRODUCIBILITY (Data Truth round 3). prematch_snapshots.parquet is not committed (*.parquet is
    ignored), so the VALUABLE verdicts built on it could not be reproduced. The manifest IS committed
    (.gitignore allowlist): the parquet's SHA-256, its row count and time span, and every v9 commit it
    was read from - `snapshots.extract` at those commits rebuilds the identical file."""
    import hashlib
    import json
    h = hashlib.sha256(Path(parquet).read_bytes()).hexdigest()
    try:
        head = _git(v9, "rev-parse", "HEAD").decode().strip()
    except Exception:                                                  # noqa: BLE001
        head = None
    m = {"file": "experiments/valuable_2026_10/prematch_snapshots.parquet", "sha256": h,
         "rows": int(len(s)), "first_generated_at": str(s["generated_at"].min()),
         "last_generated_at": str(s["generated_at"].max()), "v9_head": head,
         "v9_commits_read": shas, "rebuild": "python -m src.studies.valuable.snapshots --v9 <clone> "
                                              "(reads output/predictions.csv at each listed commit)"}
    MANIFEST.write_text(json.dumps(m, indent=1), encoding="utf-8")
    return m


def extract(v9: str, since: str = "2026-08-10") -> pd.DataFrame:
    shas = _git(v9, "log", f"--since={since}", "--format=%H %cI", "--", "output/predictions.csv").decode().split("\n")
    frames = []
    for line in filter(None, shas):
        sha, ts = line.split(" ", 1)
        try:
            raw = _git(v9, "show", f"{sha}:output/predictions.csv")
            d = pd.read_csv(io.BytesIO(raw), low_memory=False, usecols=lambda c: c in KEEP)
        except Exception:                                              # noqa: BLE001 - a malformed snapshot is skipped, not guessed
            continue
        d["snapshot_sha"], d["committed_at"] = sha[:10], ts
        frames.append(d)
    s = pd.concat(frames, ignore_index=True)
    s["committed_at"] = pd.to_datetime(s["committed_at"], utc=True)
    s["generated_at"] = pd.to_datetime(s.get("generated_at"), utc=True, errors="coerce").fillna(s["committed_at"])
    s["kickoff"] = pd.to_datetime(s["kickoff_utc"], utc=True, errors="coerce")
    # PRE-MATCH ONLY, PROVEN (Data Truth round 3): a snapshot with no kickoff cannot be shown to be
    # pre-match, so it is dropped (it used to be kept as if it were), and a snapshot must precede
    # the EARLIEST kickoff any snapshot gave its fixture, not only its own (kickoffs get re-stamped).
    s = s[s["kickoff"].notna()]
    kmin = s.groupby(["league", "date", "home_team", "away_team"])["kickoff"].transform("min")
    s = s[s["generated_at"] < kmin]
    s = s.sort_values("generated_at")
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "prematch_snapshots.parquet"
    s.to_parquet(p, index=False)      # first VALID price per market is chosen later
    write_manifest(p, s, [line.split(" ", 1)[0] for line in filter(None, shas)], v9)
    first = s.drop_duplicates(["league", "date", "home_team", "away_team"], keep="first")
    meta = {"snapshots_read": len(frames), "rows": int(len(s)), "fixtures_first_sight": int(len(first)),
            "first": str(s["generated_at"].min()), "last": str(s["generated_at"].max())}
    print(meta)
    return first


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--v9", required=True)
    ap.add_argument("--since", default="2026-08-10")
    a = ap.parse_args()
    extract(a.v9, a.since)

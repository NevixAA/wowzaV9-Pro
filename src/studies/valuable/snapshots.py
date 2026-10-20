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

import pandas as pd

from config import pro_config as cfg

OUT = cfg.BASE_DIR / "experiments" / "valuable_2026_10"
KEEP = ["league", "date", "kickoff_utc", "home_team", "away_team", "model_type", "model_version", "generated_at",
        "p_over25", "odds_over25", "odds_under25", "edge_over", "edge_under", "tier_over", "tier_under",
        "best_side", "signal_tier", "drift_signal", "p_btts", "odds_btts", "odds_btts_no", "btts_overround",
        "btts_fair_yes", "p_over15", "odds_over15", "p_over35", "odds_over35", "no_form_data",
        "home_scored_last5", "away_scored_last5", "n_books", "bookmaker_count", "odds_n_books"]


def _git(v9: str, *args) -> bytes:
    return subprocess.run(["git", "-C", v9, *args], capture_output=True, check=True).stdout


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
    s = s[s["kickoff"].isna() | (s["generated_at"] < s["kickoff"])]          # pre-match only
    s = s.sort_values("generated_at")
    OUT.mkdir(parents=True, exist_ok=True)
    s.to_parquet(OUT / "prematch_snapshots.parquet", index=False)      # first VALID price per market is chosen later
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

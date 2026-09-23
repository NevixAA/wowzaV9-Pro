"""Canonical player-match history — the training log plus the observations that never reached it.

    python -m src.architecture.canonical_player --write

WHY THIS EXISTS (sections 11 and 32). The player model trains from `player_history.parquet`, a
file that one workflow refreshes and that has already gone stale for 35 days without anything
failing. Meanwhile `fixture_player_cache/` holds the raw API responses those rows were built
from -- and it holds MORE of them: 709 fixtures sit in the cache with full player statistics and
have no rows in the training history at all.

That is the player-side version of the same defect the match side has: the data was collected,
paid for, and stored, and the learner never saw it.

WHAT THIS BUILDS. One row per player per fixture, from both sources, with the source recorded.
It does NOT replace `player_history.parquet` and nothing reads it yet -- it is the parallel
artifact section 39 asks for.

AN HONEST LIMIT, recorded rather than papered over. The cache files are keyed by fixture id and
contain team names and player statistics but NO DATE and NO LEAGUE. For fixtures that also
appear in `player_history` those come from the join. For the 709 that do not, they cannot be
recovered locally at all -- they need a fixture lookup against API-Football. Those rows are
therefore emitted with a null date, flagged `needs_fixture_resolution`, and EXCLUDED from any
training-eligible count. A row whose date is unknown cannot be placed in time, and a row that
cannot be placed in time cannot be used for chronological training without risking leakage. The
recovery is cheap (709 calls, against 75,000/day of headroom) but it is a collection task, not
something this module may invent.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"

KEEP = ["fixture_id", "player_id", "player_name", "date", "league", "team", "opponent",
        "is_home", "position", "started", "minutes", "goals", "assists", "shots_total",
        "shots_on_target", "yellow_cards", "red_cards", "rating"]


def _v9() -> Path:
    return Path(cfg.V9_LOCAL)


def _from_history() -> pd.DataFrame:
    d = pd.read_parquet(_v9() / "player_history.parquet")
    out = pd.DataFrame(index=d.index)
    for c in KEEP:
        out[c] = d[c] if c in d.columns else np.nan
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["source"] = "player_history"
    return out


def _from_cache() -> pd.DataFrame:
    """Parse the raw API fixture-player responses into the same shape."""
    rows = []
    for f in glob.glob(str(_v9() / "fixture_player_cache" / "fix_*.json")):
        m = re.search(r"fix_(\d+)\.json$", f)
        if not m:
            continue
        fid = int(m.group(1))
        try:
            payload = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, list):
            continue
        teams = [t.get("team", {}).get("name") for t in payload if isinstance(t, dict)]
        for t in payload:
            if not isinstance(t, dict):
                continue
            tname = (t.get("team") or {}).get("name")
            opp = next((x for x in teams if x and x != tname), None)
            for pl in t.get("players") or []:
                info = pl.get("player") or {}
                st = (pl.get("statistics") or [{}])[0]
                games = st.get("games") or {}
                goals = st.get("goals") or {}
                shots = st.get("shots") or {}
                cards = st.get("cards") or {}
                rows.append({
                    "fixture_id": fid, "player_id": info.get("id"),
                    "player_name": info.get("name"), "date": pd.NaT, "league": np.nan,
                    "team": tname, "opponent": opp, "is_home": np.nan,
                    "position": games.get("position"),
                    "started": 1 if games.get("substitute") is False else
                               (0 if games.get("substitute") is True else np.nan),
                    "minutes": games.get("minutes"), "goals": goals.get("total"),
                    "assists": goals.get("assists"), "shots_total": shots.get("total"),
                    "shots_on_target": shots.get("on"), "yellow_cards": cards.get("yellow"),
                    "red_cards": cards.get("red"), "rating": games.get("rating"),
                })
    d = pd.DataFrame(rows)
    if not d.empty:
        d["source"] = "fixture_player_cache"
    return d


def build() -> tuple[pd.DataFrame, dict]:
    hist = _from_history()
    cache = _from_cache()
    hist_fix = set(pd.to_numeric(hist["fixture_id"], errors="coerce").dropna().astype(int))

    if cache.empty:
        recovered = cache
    else:
        cf = pd.to_numeric(cache["fixture_id"], errors="coerce")
        recovered = cache[~cf.isin(hist_fix)].copy()

    can = pd.concat([hist, recovered], ignore_index=True)
    for c in ("minutes", "goals", "assists", "shots_total", "shots_on_target",
              "yellow_cards", "red_cards", "started", "rating"):
        can[c] = pd.to_numeric(can[c], errors="coerce")
    can["scored"] = (can["goals"].fillna(0) > 0).astype(int)
    can["needs_fixture_resolution"] = can["date"].isna()
    # Only rows that can be PLACED IN TIME are training-eligible. See the docstring.
    can["training_eligible"] = (~can["needs_fixture_resolution"]) & can["player_id"].notna()
    can = can.drop_duplicates(["fixture_id", "player_id"], keep="first").reset_index(drop=True)

    man = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "calc_version": CALC_VERSION,
        "rows": int(len(can)),
        "rows_from_training_history": int((can["source"] == "player_history").sum()),
        "rows_recovered_from_cache": int((can["source"] == "fixture_player_cache").sum()),
        "fixtures": int(can["fixture_id"].nunique()),
        "fixtures_recovered": int(recovered["fixture_id"].nunique()) if len(recovered) else 0,
        "players": int(can["player_id"].nunique()),
        "training_eligible_rows": int(can["training_eligible"].sum()),
        "needs_fixture_resolution_rows": int(can["needs_fixture_resolution"].sum()),
        "first": str(can["date"].min())[:10], "last": str(can["date"].max())[:10],
        "scoring_rate": round(float(can["scored"].mean()), 4),
        "coverage": {c: round(float(can[c].notna().mean()), 4)
                     for c in ("minutes", "started", "goals", "shots_total",
                               "shots_on_target", "position", "rating")},
    }
    return can, man


def out_dir() -> Path:
    p = cfg.OUTPUT_DIR / "architecture"
    p.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    can, man = build()
    print(f"[player] {man['rows']:,} player-match rows on {man['fixtures']:,} fixtures  "
          f"{man['first']}..{man['last']}")
    print(f"[player] from training history : {man['rows_from_training_history']:,}")
    print(f"[player] RECOVERED from cache  : {man['rows_recovered_from_cache']:,} "
          f"across {man['fixtures_recovered']:,} fixtures")
    print(f"[player] training-eligible     : {man['training_eligible_rows']:,}")
    print(f"[player] blocked on a missing fixture date: "
          f"{man['needs_fixture_resolution_rows']:,} "
          f"(recoverable with ~{man['fixtures_recovered']:,} API calls)")
    print("\nCOLUMN COVERAGE")
    for c, v in man["coverage"].items():
        print(f"   {c:<18}{v:>7.2%}")
    if a.write:
        can.to_parquet(out_dir() / "canonical_player_history.parquet", index=False)
        (out_dir() / "canonical_player_manifest.json").write_text(
            json.dumps(man, indent=2, default=str), encoding="utf-8")
        print(f"\n[player] wrote canonical_player_history.parquet + manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

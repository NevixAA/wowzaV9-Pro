"""Give the recovered player rows a date, so they can be placed in time and trained on.

    python -m src.architecture.resolve_fixtures --write

THE BLOCK THIS CLEARS. `fixture_player_cache/` holds full player statistics for 709 fixtures
that never reached `player_history.parquet` -- roughly 30,919 player-match observations we
collected, stored, and never learned from. They cannot simply be appended: the cached API
responses carry team names and statistics but NO DATE and NO LEAGUE, and a row that cannot be
placed in time cannot be used for chronological training without risking leakage. So the canary
correctly refuses them.

The missing field is recoverable from the provider that produced them, and cheaply.

BATCHED, BECAUSE 709 CALLS IS THE LAZY VERSION. API-Football's /fixtures endpoint accepts up to
20 ids at a time, so the whole job is ~36 calls rather than 709 -- against 75,000/day of
headroom. Every response is cached to disk and never re-requested: a finished fixture's date is
immutable, and re-fetching immutable data on every run is exactly the pattern that had this
estate re-downloading four seasons of football-data on every CI run.

WHAT IT DOES NOT DO. It does not write into v9, does not touch player_history.parquet, and does
not invent anything. A fixture the provider cannot resolve stays unresolved and stays excluded --
the output is a mapping table, and rows with no mapping keep their null date and their flag.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"
API = "https://v3.football.api-sports.io/fixtures"
BATCH = 20                      # provider maximum per request
SLEEP = 6.5                     # seconds between calls; the plan allows 300/min, this is safe


def A() -> Path:
    p = cfg.OUTPUT_DIR / "architecture"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_dir() -> Path:
    p = A() / "fixture_lookup_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _key() -> str:
    """Read the provider key from the environment or v9's local .env. Never printed."""
    k = os.getenv("APIFOOTBALL_KEY", "").strip()
    if k:
        return k
    env = Path(cfg.V9_LOCAL) / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("APIFOOTBALL_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("APIFOOTBALL_KEY not configured")


def unresolved_ids() -> list[int]:
    p = A() / "canonical_player_history.parquet"
    if not p.exists():
        raise RuntimeError("canonical_player_history.parquet missing — build it first")
    d = pd.read_parquet(p, columns=["fixture_id", "needs_fixture_resolution"])
    ids = (pd.to_numeric(d.loc[d["needs_fixture_resolution"], "fixture_id"], errors="coerce")
             .dropna().astype(int).unique())
    return sorted(int(x) for x in ids)


def fetch(ids: list[int], *, live: bool = True) -> pd.DataFrame:
    rows, calls, cached_hits = [], 0, 0
    todo = []
    for i in ids:
        c = _cache_dir() / f"fx_{i}.json"
        if c.exists():
            try:
                rows.append(json.loads(c.read_text(encoding="utf-8")))
                cached_hits += 1
                continue
            except Exception:
                pass
        todo.append(i)

    if todo and live:
        import requests
        headers = {"x-apisports-key": _key()}
        for k in range(0, len(todo), BATCH):
            chunk = todo[k:k + BATCH]
            try:
                r = requests.get(API, params={"ids": "-".join(map(str, chunk))},
                                 headers=headers, timeout=45)
                calls += 1
                if r.status_code != 200:
                    print(f"  batch {k // BATCH + 1}: HTTP {r.status_code}")
                    time.sleep(SLEEP)
                    continue
                payload = r.json()
                got = {int(f["fixture"]["id"]) for f in payload.get("response", [])
                       if f.get("fixture")}
                for f in payload.get("response", []):
                    fx, lg, tm = f.get("fixture", {}), f.get("league", {}), f.get("teams", {})
                    rec = {"fixture_id": int(fx.get("id")),
                           "date": str(fx.get("date", ""))[:10],
                           "kickoff_utc": fx.get("date"),
                           "league_api": lg.get("name"), "country": lg.get("country"),
                           "season": lg.get("season"),
                           "home_team": (tm.get("home") or {}).get("name"),
                           "away_team": (tm.get("away") or {}).get("name"),
                           "status": (fx.get("status") or {}).get("short")}
                    (_cache_dir() / f"fx_{rec['fixture_id']}.json").write_text(
                        json.dumps(rec), encoding="utf-8")
                    rows.append(rec)
                # Record misses too, so a fixture the provider does not know is never re-asked.
                for miss in set(chunk) - got:
                    rec = {"fixture_id": miss, "date": "", "kickoff_utc": None,
                           "league_api": None, "country": None, "season": None,
                           "home_team": None, "away_team": None, "status": "NOT_FOUND"}
                    (_cache_dir() / f"fx_{miss}.json").write_text(json.dumps(rec),
                                                                  encoding="utf-8")
                    rows.append(rec)
                print(f"  batch {k // BATCH + 1}/{(len(todo) + BATCH - 1) // BATCH}: "
                      f"{len(got)}/{len(chunk)} resolved")
            except Exception as e:                                   # noqa: BLE001
                print(f"  batch {k // BATCH + 1} failed: {type(e).__name__}")
            time.sleep(SLEEP)

    d = pd.DataFrame(rows)
    print(f"[resolve] {len(d)} records  ({cached_hits} from cache, {calls} API calls)")
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--offline", action="store_true", help="cache only, make no API calls")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    ids = unresolved_ids()
    if a.limit:
        ids = ids[:a.limit]
    print(f"[resolve] {len(ids):,} fixtures need a date "
          f"(~{(len(ids) + BATCH - 1) // BATCH} batched calls)")
    d = fetch(ids, live=not a.offline)
    if d.empty:
        print("[resolve] nothing resolved")
        return 1
    ok = d[d["date"].astype(str).str.len() == 10]
    print(f"[resolve] resolved {len(ok):,} of {len(ids):,}  "
          f"({len(d) - len(ok)} not found by the provider)")
    if len(ok):
        print(f"[resolve] span {ok['date'].min()}..{ok['date'].max()}")
        print("[resolve] leagues:",
              ok["league_api"].value_counts().head(8).to_dict())
    if a.write:
        d.to_parquet(A() / "fixture_id_map.parquet", index=False)
        (A() / "fixture_resolution_manifest.json").write_text(json.dumps({
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "calc_version": CALC_VERSION, "requested": len(ids),
            "resolved": int(len(ok)), "not_found": int(len(d) - len(ok)),
            "first": str(ok["date"].min()) if len(ok) else "",
            "last": str(ok["date"].max()) if len(ok) else "",
        }, indent=2), encoding="utf-8")
        print(f"[resolve] wrote fixture_id_map.parquet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

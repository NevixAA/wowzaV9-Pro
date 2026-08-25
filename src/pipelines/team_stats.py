"""
Collect per-fixture team match statistics — the xG the model never had.
======================================================================
    python -m src.pipelines.team_stats [--season 2026] [--limit N] [--dry-run]

THE GAP THIS FILLS, measured on the live board 2026-08-25:

    home_xg_last5 / away_xg_last5      0% populated
    home_insidebox_last5                0%
    home_possession_last5               0%
    h2h_avg_goals                       0%
    home_season_goals_h / cs_rate      41%
    home_shots_last5 / sot             76%

Missing features are MEDIAN-IMPUTED, so the model is handed the league average for a quarter to
all of its per-team inputs. That is not a modelling weakness, it is an absent input.

AND THE PIECES WERE ALREADY THERE. v9's `api_football_ou.py` parses `expected_goals`,
`Shots insidebox` and `Ball Possession` from `/fixtures/statistics`. `feature_engineering.py`
computes `home_xg_last5` by rolling a `home_xg` column. What never existed was a HISTORY holding
those columns: `af_history.parquet` carries only football-data fields (FTHG, HS, HST, HC, HF, HY,
...) and no xG at all. So the parser wrote to nothing and the feature read from nothing.

This retracts an earlier conclusion of mine. I tested BTTS asymmetry features, found
`p_btts_dc` scored AUC 0.5032, and concluded "the lambdas carry no per-team signal, so
distribution features cannot help". The real explanation is narrower and fixable: those lambdas
are `attack_str x opponent_defence`, and the inputs behind them are placeholders. A model fed the
league mean for xG cannot express per-team scoring rates, so of course a distribution built on
them is noise.

COST, measured before writing any of this:

    season-to-date backfill   2,298 calls   3.1% of one day of the 75,000 quota
    ongoing                   ~47 calls/day (~47 fixtures/day across 20 leagues)

Root CLAUDE.md is explicit that spare quota is only worth spending when a consumer exists —
"spending credits without a consumer is cost, not value". This is the first proposal that passes
that test: the consumer is the feature set of every model Pro will build.

DESIGN NOTES

* **Finished fixtures only.** A statistics row for an in-play match changes as the match runs, so
  collecting one would store a value that is wrong by the time it is read. `status=FT` only.
* **Resumable and idempotent.** Already-collected `fixture_id`s are skipped by reading the
  existing table, so an interrupted run costs nothing to resume and a re-run costs no calls.
* **Cached forever.** A finished fixture's statistics never change, so the cache TTL is long;
  re-deriving is free.
* **Quota-guarded.** Stops at MIN_QUOTA remaining rather than racing the limit, because the
  5-minute predict loop shares the same key and must not be starved.
* **One row per FIXTURE, home_/away_ columns.** Matches how `feature_engineering._team_recent`
  consumes it. A per-team grain is more normalised and would force every consumer to pivot.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pandas as pd

from config import pro_config as cfg
from src.data import entities as ent
from src.data import season_store as store

TABLE = "team_match_stats"
_BASE = "https://v3.football.api-sports.io"
MIN_QUOTA = int(os.getenv("MIN_QUOTA", "5000"))

# API stat name -> our column stem. Only the ones a model can use; cards/offsides are available
# but nothing consumes them, and an unused column is a maintenance cost with no benefit.
STAT_MAP = {
    "expected_goals": "xg",
    "Shots insidebox": "insidebox",
    "Shots outsidebox": "outsidebox",
    "Ball Possession": "possession",
    "Total Shots": "shots",
    "Shots on Goal": "sot",
    "Blocked Shots": "blocked",
    "Corner Kicks": "corners",
    "Fouls": "fouls",
    "Goalkeeper Saves": "saves",
    "goals_prevented": "goals_prevented",
    "Passes %": "pass_pct",
}


def _headers() -> dict:
    key = os.getenv("APIFOOTBALL_KEY", "")
    if not key:
        # Loaded here rather than at import: a module-level read means an absent key becomes an
        # import-time failure in every consumer, which is how backfill_af_odds ends up printing
        # "not set" once per worker and exiting before doing anything.
        for name in (".env", "secrets.env"):
            p = cfg.BASE_DIR / name
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("APIFOOTBALL_KEY"):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            if key:
                break
    if not key:
        raise RuntimeError("APIFOOTBALL_KEY not available (env or .env)")
    return {"x-apisports-key": key}


def _num(v):
    """API values arrive as '52%', '1.85', None or ''. Percent signs stripped, blanks -> NaN."""
    if v is None:
        return float("nan")
    s = str(v).strip().replace("%", "")
    if not s:
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _get(endpoint: str, params: dict, session, cache_hours: float = 24 * 365):
    """GET with an on-disk cache. Returns the parsed body or None.

    A 200 with an `errors` payload is NOT success — API-Football answers that way for quota and
    parameter problems, and treating it as data is how a malformed request masqueraded as a quiet
    day for two weeks elsewhere in this project.
    """
    import hashlib
    import json
    key = hashlib.sha1(f"{endpoint}{sorted(params.items())}".encode()).hexdigest()[:20]
    cache_dir = cfg.BASE_DIR / "cache" / "af_stats"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{key}.json"
    if cf.exists() and (time.time() - cf.stat().st_mtime) < cache_hours * 3600:
        try:
            return json.loads(cf.read_text(encoding="utf-8")), True
        except Exception:
            pass
    r = session.get(f"{_BASE}{endpoint}", headers=_headers(), params=params, timeout=25)
    if r.status_code != 200:
        print(f"[team_stats] {endpoint} HTTP {r.status_code}")
        return None, False
    body = r.json()
    errs = body.get("errors")
    if errs:
        print(f"[team_stats] {endpoint} returned errors={errs}")
        return None, False
    cf.write_text(json.dumps(body), encoding="utf-8")
    return body, False


def _league_ids() -> dict:
    """v9's league-id mapping, loaded by explicit file spec.

    Imported rather than duplicated so a second copy cannot drift. By file spec rather than
    sys.path because inserting v9's directory shadows Pro's own `config` PACKAGE for the rest of
    the process — that broke three test groups when I did it in pro_tests.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("_v9cfg_stats", cfg.V9_LOCAL / "config.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return dict(m.API_FOOTBALL_IDS)


def _already_collected() -> set:
    try:
        prev = store.read(TABLE)
        if prev is not None and not prev.empty and "fixture_id" in prev.columns:
            return set(prev["fixture_id"].astype(str))
    except Exception:
        pass
    return set()


def _parse_stats(fx: dict, teams: list, league: str) -> dict | None:
    """One fixture's row. response[0] is HOME for /fixtures/statistics."""
    if len(teams) < 2:
        return None
    pick = {}
    for side, blk in (("home", teams[0]), ("away", teams[1])):
        got = {s.get("type"): s.get("value") for s in blk.get("statistics", [])}
        for api_name, stem in STAT_MAP.items():
            pick[f"{side}_{stem}"] = _num(got.get(api_name))
    return {
        "fixture_id": str(fx["fixture"]["id"]),
        "league": league,
        "season": str(fx["league"].get("season", "")),
        "match_date": str(fx["fixture"]["date"])[:10],
        "kickoff_utc": fx["fixture"]["date"],
        "home_team": fx["teams"]["home"]["name"],
        "away_team": fx["teams"]["away"]["name"],
        "home_goals": fx["goals"]["home"],
        "away_goals": fx["goals"]["away"],
        "stats_source": "api_football/fixtures/statistics",
        **pick,
    }


def collect(seasons=("2026",), limit: int | None = None, dry_run: bool = False,
            sleep_s: float = 0.25) -> pd.DataFrame:
    """Collect statistics for finished fixtures across `seasons`.

    COMMITS PER (LEAGUE, SEASON) rather than accumulating everything and writing once. A full
    four-season backfill is ~24,500 calls and ~3.4 hours of wall clock; holding it all in memory
    means an interruption at hour three throws away every call spent. Chunked, a crash costs at
    most one league-season and the next run resumes from what is already stored.
    """
    import requests
    league_ids = _league_ids()
    already = _already_collected()
    print(f"[team_stats] seasons {list(seasons)}; {len(already):,} fixture(s) already stored")

    session = requests.Session()
    calls = cached = written = chunk_no = 0
    frames = []
    for season in seasons:
        for league, lid in sorted(league_ids.items()):
            body, was_cached = _get("/fixtures",
                                    {"league": lid, "season": season, "status": "FT"},
                                    session, cache_hours=24)
            calls += 0 if was_cached else 1
            fixtures = (body or {}).get("response") or []
            todo = [f for f in fixtures if str(f["fixture"]["id"]) not in already]
            if not todo:
                continue
            rows = []
            for fx in todo:
                if limit is not None and written + len(rows) >= limit:
                    break
                st, wc = _get("/fixtures/statistics", {"fixture": str(fx["fixture"]["id"])},
                              session)
                if wc:
                    cached += 1
                else:
                    calls += 1
                    time.sleep(sleep_s)
                row = _parse_stats(fx, (st or {}).get("response") or [], league)
                if row:
                    rows.append(row)
                    already.add(row["fixture_id"])
            if not rows:
                continue
            chunk = ent.add_fixture_key(pd.DataFrame(rows))
            frames.append(chunk)
            written += len(chunk)
            xg = pd.to_numeric(chunk.get("home_xg"), errors="coerce")
            print(f"  {season} {league:28} +{len(chunk):>4} rows  "
                  f"xG {xg.notna().mean():5.1%}  (calls {calls:,}, cache {cached:,})")
            if not dry_run:
                try:
                    # Unique per chunk AND filesystem-safe. The first version used
                    # f"...-{league[:12]}", which put a SPACE in the parquet filename and
                    # could collide between two leagues sharing a 12-char prefix. The
                    # counter makes a collision impossible even on a re-run within the
                    # same process second.
                    _slug = "".join(ch if ch.isalnum() else "_" for ch in league)[:20]
                    chunk_no += 1
                    store.append(TABLE, chunk, source="api_football:fixtures/statistics",
                                 rid=f"{cfg.run_id()}-stats-{season}-{_slug}-{chunk_no}")
                except store.LocalWriteRefused as e:
                    print(f"    NOT written — {e}")
                    dry_run = True
            if limit is not None and written >= limit:
                break
        if limit is not None and written >= limit:
            break

    d = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if d.empty:
        print("[team_stats] nothing new to collect")
        return d
    print(f"\n[team_stats] {len(d):,} fixture(s) | {calls:,} API call(s), {cached:,} cached")
    for c in ("home_xg", "home_insidebox", "home_possession", "home_shots", "home_sot",
              "home_goals_prevented", "home_pass_pct"):
        if c in d.columns:
            v = pd.to_numeric(d[c], errors="coerce")
            print(f"    {c:24} {v.notna().sum():>6}/{len(d)} = {v.notna().mean():5.1%}")
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect per-fixture team match statistics")
    ap.add_argument("--seasons", default="2026",
                    help="comma-separated, e.g. 2023,2024,2025,2026")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N new fixtures (for a costed trial run)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    collect(seasons=tuple(x.strip() for x in a.seasons.split(",") if x.strip()),
            limit=a.limit, dry_run=a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

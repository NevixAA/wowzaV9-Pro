"""
Backfill the CONTROL GROUP from v9's git history.
=================================================
    python -m src.pipelines.backfill_history --extract          # step 1, offline
    python -m src.pipelines.backfill_history --results          # step 2, free public CSVs
    python -m src.pipelines.backfill_history --all

Why this exists. Phase 5's first real result was significant and worthless, for a knowable
reason: the sample contained only fixtures v9 CHOSE TO BET, selected for maximum model-market
disagreement. On such a subset the market scores worse than predicting the base rate, which no
real market does, so "the blend beats the market" was close to circular.

The missing half is the fixtures v9 DECLINED. Those exist: `predict` commits the full board to
output/predictions.csv roughly 192 times a day, and a typical snapshot is 166 rows of which 142
are AVOID. 678 such commits span 2026-05 to 2026-08. Every one of those fixtures has long since
been played.

SAFETY. This is strictly read-only against v9:
  * `git show <sha>:output/predictions.csv` reads a blob directly. It never checks anything out,
    never touches the working tree, and cannot disturb a running workflow.
  * nothing is written into v9. Output goes to Pro's season store.
  * results come from football-data.co.uk, the same free public CSVs update_results.py already
    uses. No API key, no quota, no paid call.
"""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config import pro_config as cfg
from src.data import entities as ent
from src.data import season_store as store

V9 = cfg.V9_LOCAL
PRED = "output/predictions.csv"
# The joined result. Its EXISTENCE is what tells the scheduled workflow the backfill is
# already done, so the marker is the artifact itself and cannot drift from it.
JOINED = cfg.DATA_DIR / "_backfill_joined.parquet"

# league -> (football-data format, code). Only the leagues that actually appear in the
# snapshots need an entry; anything unmapped is reported rather than silently skipped.
FD_CODES: dict[str, tuple[str, str]] = {
    "Premier League": ("std", "E0"), "Championship": ("std", "E1"),
    "League One": ("std", "E2"), "League Two": ("std", "E3"),
    "Bundesliga": ("std", "D1"), "Bundesliga 2": ("std", "D2"),
    "La Liga": ("std", "SP1"), "La Liga 2": ("std", "SP2"),
    "Serie A": ("std", "I1"), "Serie B": ("std", "I2"),
    "Ligue 1": ("std", "F1"), "Ligue 2": ("std", "F2"),
    "Scottish Premiership": ("std", "SC0"), "Greek Super League": ("std", "G1"),
    "Portugal Primeira Liga": ("std", "P1"), "Turkey Super Lig": ("std", "T1"),
    "Belgium Pro League": ("std", "B1"), "Netherlands Eredivisie": ("std", "N1"),
    "Argentina Primera Division": ("new", "ARG"), "Austrian Bundesliga": ("new", "AUT"),
    "Brazil Serie A": ("new", "BRA"), "China Super League": ("new", "CHN"),
    "Denmark Superliga": ("new", "DNK"), "Finland Veikkausliiga": ("new", "FIN"),
    "Ireland Premier Division": ("new", "IRL"), "Japan J-League": ("new", "JPN"),
    "Mexico Liga MX": ("new", "MEX"), "Sweden Allsvenskan": ("new", "SWE"),
    "USA MLS": ("new", "USA"), "Norway Eliteserien": ("new", "NOR"),
    "Switzerland Super League": ("std", "SWZ"), "Poland Ekstraklasa": ("new", "POL"),
}

STD_URL = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
NEW_URL = "https://www.football-data.co.uk/new/{code}.csv"

# Identity and decision columns that must always be present.
_REQUIRED = ["league", "date", "home_team", "away_team", "p_over25"]

# Everything else in predictions.csv is kept too. The first version of this listed 14 columns
# and dropped the other ~128 — including every engineered feature — which made the extract
# useless for TRAINING a model, only for comparing one. Since predictions.csv is pre-match by
# construction, no column in it can carry post-kickoff information, so keeping all of them
# cannot leak. Storage is trivial: 935 fixtures x ~142 columns is about 1MB of parquet.
_DROP = {"Unnamed: 0"}


def _git(args: list[str], binary: bool = False):
    r = subprocess.run(["git", *args], cwd=V9, capture_output=True,
                       text=not binary, timeout=300)
    return r.stdout if r.returncode == 0 else None


def snapshot_commits() -> list[tuple[str, str]]:
    """(sha, committed_at) for every commit that touched predictions.csv, oldest first."""
    out = _git(["log", "--format=%H|%cI", "--reverse", "--", PRED])
    if not out:
        return []
    return [tuple(line.split("|", 1)) for line in out.strip().splitlines() if "|" in line]


def extract() -> pd.DataFrame:
    """Every fixture v9 ever evaluated, with the model's view at that moment.

    Keeps the LAST snapshot per fixture, which is the closest pre-kickoff view v9 had — the
    fairest single number to judge it on. `predictions.csv` is pre-match only, so no snapshot
    can contain post-kickoff information.
    """
    commits = snapshot_commits()
    print(f"[backfill] {len(commits)} predictions.csv commits to read (read-only)")
    frames = []
    for i, (sha, when) in enumerate(commits, 1):
        raw = _git(["show", f"{sha}:{PRED}"], binary=True)
        if not raw:
            continue
        try:
            d = pd.read_csv(io.BytesIO(raw))
        except Exception:
            continue
        if not set(_REQUIRED) <= set(d.columns):
            continue
        d = d[[c for c in d.columns if c not in _DROP]].copy()
        d["observed_at"] = when
        d["source_sha"] = sha[:12]
        frames.append(d)
        if i % 100 == 0:
            print(f"[backfill]   {i}/{len(commits)} ...")
    if not frames:
        return pd.DataFrame()

    all_df = pd.concat(frames, ignore_index=True)
    all_df["match_date"] = all_df["date"].astype(str).str[:10]
    all_df = ent.add_fixture_key(all_df)
    # Closest-to-kickoff view per fixture.
    out = (all_df.sort_values("observed_at")
                 .drop_duplicates("fixture_key", keep="last")
                 .reset_index(drop=True))
    print(f"[backfill] {len(all_df):,} snapshot rows -> {len(out):,} unique fixtures")
    print(f"[backfill] tier spread: {out['signal_tier'].value_counts().to_dict()}")
    non_bet = int((~out["bet"].isin(["OVER", "UNDER"])).sum()) if "bet" in out else 0
    print(f"[backfill] fixtures v9 DECLINED (the control group): {non_bet:,} "
          f"({100 * non_bet / max(1, len(out)):.1f}%)")
    return out


def _season_codes(dates: pd.Series) -> set[str]:
    """football-data season folders, e.g. 2526, covering the fixture dates present."""
    d = pd.to_datetime(dates, errors="coerce").dropna()
    out = set()
    for y, m in zip(d.dt.year, d.dt.month):
        start = y if m >= 7 else y - 1
        out.add(f"{str(start)[-2:]}{str(start + 1)[-2:]}")
    return out


def fetch_results(fixtures: pd.DataFrame) -> pd.DataFrame:
    """Actual goals from football-data.co.uk — free, public, no key."""
    import requests

    leagues = sorted(fixtures["league"].astype(str).unique())
    seasons = sorted(_season_codes(fixtures["match_date"]))
    print(f"[backfill] results for {len(leagues)} league(s), season folder(s) {seasons}")

    unmapped = [lg for lg in leagues if lg not in FD_CODES]
    if unmapped:
        print(f"[backfill] NO football-data code for {len(unmapped)} league(s) — these keep no "
              f"result and are reported, not silently dropped: {unmapped[:8]}")

    rows = []
    for lg in leagues:
        if lg not in FD_CODES:
            continue
        fmt, code = FD_CODES[lg]
        urls = ([NEW_URL.format(code=code)] if fmt == "new"
                else [STD_URL.format(season=s, code=code) for s in seasons])
        for u in urls:
            try:
                r = requests.get(u, timeout=60)
                if r.status_code != 200:
                    continue
                d = pd.read_csv(io.StringIO(r.text), encoding_errors="replace")
            except Exception as e:
                print(f"[backfill]   {lg}: {e}")
                continue
            h = "HomeTeam" if "HomeTeam" in d.columns else "Home"
            a = "AwayTeam" if "AwayTeam" in d.columns else "Away"
            hg = "FTHG" if "FTHG" in d.columns else "HG"
            ag = "FTAG" if "FTAG" in d.columns else "AG"
            if not {h, a, hg, ag, "Date"} <= set(d.columns):
                continue
            blk = pd.DataFrame({
                "league": lg,
                "home_team": d[h].astype(str),
                "away_team": d[a].astype(str),
                "home_goals": pd.to_numeric(d[hg], errors="coerce"),
                "away_goals": pd.to_numeric(d[ag], errors="coerce"),
                "match_date": pd.to_datetime(d["Date"], dayfirst=True,
                                             errors="coerce").dt.strftime("%Y-%m-%d"),
            })
            rows.append(blk.dropna(subset=["home_goals", "away_goals", "match_date"]))
    if not rows:
        return pd.DataFrame()
    res = pd.concat(rows, ignore_index=True)
    res = ent.add_fixture_key(res)
    res["total_goals"] = res["home_goals"] + res["away_goals"]
    res["y_over25"] = (res["total_goals"] > 2.5).astype(int)
    res = res.drop_duplicates("fixture_key", keep="last")
    print(f"[backfill] {len(res):,} results fetched")
    return res


def run(*, do_extract: bool, do_results: bool, write: bool = True) -> pd.DataFrame:
    cache = cfg.DATA_DIR / "_backfill_fixtures.parquet"
    if do_extract or not cache.exists():
        fx = extract()
        if fx.empty:
            print("[backfill] nothing extracted")
            return fx
        cache.parent.mkdir(parents=True, exist_ok=True)
        fx.to_parquet(cache, index=False)
    else:
        fx = pd.read_parquet(cache)
        print(f"[backfill] reusing cached extract: {len(fx):,} fixtures")

    if not do_results:
        return fx

    res = fetch_results(fx)
    if res.empty:
        print("[backfill] no results fetched")
        return fx

    j = fx.merge(res[["fixture_key", "home_goals", "away_goals", "total_goals", "y_over25"]],
                 on="fixture_key", how="inner")
    print(f"[backfill] joined on results: {len(j):,} of {len(fx):,} fixtures "
          f"({100 * len(j) / max(1, len(fx)):.1f}%)")
    if len(j):
        nb = (~j["bet"].isin(["OVER", "UNDER"])) if "bet" in j else pd.Series(True, index=j.index)
        print(f"[backfill]   of which v9 DECLINED: {int(nb.sum()):,}  "
              f"(the control group, previously absent)")
        print(f"[backfill]   base rate over 2.5: {j['y_over25'].mean():.3f}")

    if write and len(j):
        j2 = j.rename(columns={"y_over25": "y"})
        j2["market"] = "OU25"
        store.append("settlements_backfill" if "settlements_backfill" in cfg.TABLES
                     else "settlements", j2, source="v9:git_backfill",
                     rid=f"backfill-{pd.Timestamp.utcnow():%Y%m%dT%H%M%S}")
        # Joined artifact, which doubles as the DONE marker for the scheduled workflow. A
        # marker derived from the real output cannot drift out of step with it, unlike a
        # separate flag file.
        j.to_parquet(JOINED, index=False)
        print(f"[backfill] written to the season store and to {JOINED.name}")
    return j


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill the control group from v9 git history")
    ap.add_argument("--extract", action="store_true")
    ap.add_argument("--results", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    df = run(do_extract=a.extract or a.all,
             do_results=a.results or a.all,
             write=not a.no_write)
    return 0 if len(df) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""
API-Football club ids for team_match_stats rows (Data Truth round 2, 2026-11-02).
================================================================================
team_match_stats rows written before 2026-11-02 carry the club NAME only. Pro's own warehouse
already holds API-Football's club ids for many of the same fixtures, keyed by the SAME
API-Football `fixture_id`:

  scout_results          fixture_id, home_id, away_id            (scout collector)
  live_odds_snapshots    fixture_id, home_team_id, away_team_id   (live collector)

`attach_team_ids` fills `home_team_id` / `away_team_id` from those tables by exact fixture_id. A
value already on the row is never overwritten; a fixture_id that two sources give DIFFERENT ids
for is refused (left None and counted), never resolved by preference. No name matching is done
here: the join is on the provider's own fixture id.
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

# (table, fixture id column, home id column, away id column)
SOURCES = (
    ("scout_results", "fixture_id", "home_id", "away_id"),
    ("live_odds_snapshots", "fixture_id", "home_team_id", "away_team_id"),
)


def _s(v) -> str | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():          # an int stored through a float column
        s = s[:-2]
    return s or None


def id_lookup(frames: dict[str, pd.DataFrame]) -> tuple[dict, int]:
    """fixture_id -> (home_id, away_id) from the source frames, plus the count of fixture ids the
    sources disagree on (dropped)."""
    seen: dict = {}
    for table, fcol, hcol, acol in SOURCES:
        d = frames.get(table)
        if d is None or d.empty or not {fcol, hcol, acol} <= set(d.columns):
            continue
        for f, h, a in d[[fcol, hcol, acol]].drop_duplicates().itertuples(index=False):
            f, h, a = _s(f), _s(h), _s(a)
            if f is None or h is None or a is None:
                continue
            seen.setdefault(f, set()).add((h, a))
    out = {f: next(iter(v)) for f, v in seen.items() if len(v) == 1}
    return out, sum(1 for v in seen.values() if len(v) > 1)


def attach_team_ids(stats: pd.DataFrame, frames: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """A copy of `stats` with `home_team_id` / `away_team_id` filled by exact fixture_id where a
    source has them. `frames` defaults to reading SOURCES from the season store."""
    if stats is None or stats.empty or "fixture_id" not in stats.columns:
        return stats
    if frames is None:
        from src.data import season_store as store
        frames = {}
        for table, fcol, hcol, acol in SOURCES:
            try:
                d = store.read(table)
            except Exception as e:                      # a missing source is logged, not invented
                log.warning("[team_ids] %s unreadable: %s", table, e)
                continue
            if not d.empty and {fcol, hcol, acol} <= set(d.columns):
                frames[table] = d[[fcol, hcol, acol]].drop_duplicates()
    lk, conflicts = id_lookup(frames)
    out = stats.copy()
    for c in ("home_team_id", "away_team_id"):
        if c not in out.columns:
            out[c] = pd.Series([None] * len(out), index=out.index, dtype=object)
        out[c] = out[c].map(_s).astype(object)
    fid = out["fixture_id"].map(_s)
    hit = fid.map(lambda f: lk.get(f) if f is not None else None)
    for i, c in enumerate(("home_team_id", "away_team_id")):
        fill = out[c].isna() & hit.notna()
        out.loc[fill, c] = hit[fill].map(lambda t: t[i])
    if conflicts:
        log.warning("[team_ids] %d fixture id(s) with conflicting club ids across sources - left "
                    "without ids", conflicts)
    return out

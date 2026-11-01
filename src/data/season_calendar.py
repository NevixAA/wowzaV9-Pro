"""League-aware season calendar (R2 finding 26, 2026-11-01).

The Prediction Lab labelled every fixture with an Aug-Jul bucket. For winter leagues that is the
season; for calendar-year leagues (Scandinavia, Ireland, MLS, Brazil, China, K-League, Argentina
since 2021) it splits ONE campaign across two labels, so "first match of the season", "previous
season's average", "changed league" and season-stage features were wrong exactly where a season
starts. Japan's J1 changed calendar in 2026 (spring special, then autumn-spring with an END-year
API-Football season id), which no single date rule survives.

This service resolves (league, date) -> season from ``registry/league_season_calendar.json``:

    season_for("USA MLS", "2026-03-01")        -> label "2026",    api_football "2026"
    season_for("Championship", "2026-03-01")   -> label "2025/26", api_football "2025"
    season_for("Japan J-League", "2026-11-01") -> label "2026/27", api_football "2027"
    season_for("Mystery League", ...)          -> status SEASON_UNKNOWN, label None

FAIL-CLOSED. An unknown league (or a date before any rule) is SEASON_UNKNOWN with label None --
never a guessed Aug-Jul label. Callers decide what an unknown season means for them; the lab keeps
such rows out of season-scoped features (they stay NaN) and counts them.

TODO(R2 registry): read v9 ``config/leagues.json`` once branch r2/registry-season-failclosed lands.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

CALENDAR_PATH = cfg.REGISTRY_DIR / "league_season_calendar.json"
RESOLVED = "RESOLVED"
SEASON_UNKNOWN = "SEASON_UNKNOWN"


@dataclass(frozen=True)
class SeasonResolution:
    league: str
    date: str
    status: str
    season_type: str | None = None
    label: str | None = None
    start_year: int | None = None
    api_football_season: str | None = None
    calendar_version: str | None = None


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    leagues = {}
    alias = {}
    for name, e in d["leagues"].items():
        base = sorted([r for r in e["rules"] if "to" not in r], key=lambda r: r["from"])
        special = [r for r in e["rules"] if "to" in r]
        leagues[name] = {"base": base, "special": special, "model_type": e.get("model_type")}
        for a in e.get("aliases", []):
            alias[a] = name
    return {"version": d["version"], "leagues": leagues, "alias": alias}


def calendar(path: Path | str | None = None) -> dict:
    return _load(str(path or CALENDAR_PATH))


def calendar_version(path: Path | str | None = None) -> str:
    return calendar(path)["version"]


def canonical_league(league: str, path=None) -> str | None:
    c = calendar(path)
    lg = str(league).strip()
    if lg in c["leagues"]:
        return lg
    return c["alias"].get(lg)


def season_for(league: str, when, path=None) -> SeasonResolution:
    c = calendar(path)
    d = pd.Timestamp(when).date() if not isinstance(when, date) else when
    iso = d.isoformat()
    lg = canonical_league(league, path)
    if lg is None:
        return SeasonResolution(str(league), iso, SEASON_UNKNOWN, calendar_version=c["version"])
    e = c["leagues"][lg]
    for r in e["special"]:
        if r["from"] <= iso <= r["to"]:
            lab = r["label"]
            sy = int(lab[:4])
            return SeasonResolution(lg, iso, RESOLVED, "special", lab, sy,
                                    str(r.get("api_season", sy)), c["version"])
    rule = None
    for r in e["base"]:
        if r["from"] <= iso:
            rule = r
    if rule is None:
        return SeasonResolution(lg, iso, SEASON_UNKNOWN, calendar_version=c["version"])
    if rule["type"] == "calendar":
        sy = d.year
        lab = str(sy)
        api = str(sy)
    elif rule["type"] == "winter":
        sy = d.year if d.month >= 7 else d.year - 1
        lab = f"{sy}/{str(sy + 1)[-2:]}"
        api = str(sy + 1) if rule.get("api") == "end_year" else str(sy)
    else:                                                     # pragma: no cover - schema guard
        return SeasonResolution(lg, iso, SEASON_UNKNOWN, calendar_version=c["version"])
    return SeasonResolution(lg, iso, RESOLVED, rule["type"], lab, sy, api, c["version"])


def api_football_season(league: str, when, path=None) -> str | None:
    """API-Football `season` parameter for this league on this date, or None (SEASON_UNKNOWN)."""
    return season_for(league, when, path).api_football_season


def league_season_frame(leagues: pd.Series, dates: pd.Series, path=None) -> pd.DataFrame:
    """Vectorised over unique (league, date) pairs. Columns: league_season, season_type,
    season_status (aligned to the input index)."""
    dd = pd.to_datetime(dates).dt.normalize()
    key = pd.DataFrame({"lg": leagues.astype(str).to_numpy(), "d": dd.to_numpy()})
    uniq = key.drop_duplicates()
    res = [season_for(lg, d, path) for lg, d in zip(uniq["lg"], uniq["d"])]
    uniq = uniq.assign(league_season=[r.label for r in res],
                       season_type=[r.season_type for r in res],
                       season_status=[r.status for r in res])
    out = key.merge(uniq, on=["lg", "d"], how="left", validate="many_to_one")
    if len(out) != len(key):                                  # pragma: no cover - guard
        raise AssertionError("season resolution changed the row count")
    out.index = leagues.index
    return out[["league_season", "season_type", "season_status"]]


def health(leagues: pd.Series, dates: pd.Series, path=None) -> dict:
    f = league_season_frame(leagues, dates, path)
    unk = f["season_status"].eq(SEASON_UNKNOWN)
    return {"calendar_version": calendar_version(path), "rows": int(len(f)),
            "season_unknown_rows": int(unk.sum()),
            "season_unknown_leagues": sorted(set(leagues[unk.to_numpy()].astype(str))),
            "by_type": {str(k): int(v) for k, v in f["season_type"].value_counts(dropna=False).items()}}


__all__ = ["SeasonResolution", "season_for", "api_football_season", "league_season_frame",
           "calendar_version", "canonical_league", "health", "RESOLVED", "SEASON_UNKNOWN"]

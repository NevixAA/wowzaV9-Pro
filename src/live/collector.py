"""
Live match + live odds collector (brief sections 126-160).
==========================================================

THE GAP THIS CLOSES

v9's live scanner has run for weeks and collects match STATE only -- `inplay_snapshots.csv` holds
snapshot_ts, fixture_id, league, match, elapsed, goals and shots-on-target. Its own docstring
explains why there are no prices:

    "No live odds API needed - we calculate the FAIR live price and alert the user to check
     their bookmaker's live screen."

That was a reasonable decision when it was made and it is now wrong: `/odds/live` works on the
current API-Football plan and returns 266 live bet types, including `Over/Under Line` -- the
DYNAMIC total the brief asks for in section 133 -- plus both-teams-to-score, handicaps and team
goals, each value carrying a `suspended` flag, and each fixture an `update` timestamp.

Without live prices, none of sections 132, 137, 138, 140 or 151 can be attempted at all: there
is no live market probability to compare a live model against, no movement to measure, and no
way to know whether a price was stale. With them, all of it becomes possible.

AND IT CANNOT BE BACKFILLED. A live price exists for seconds. Every minute of a match that goes
uncollected is gone permanently, which is why this collects first and models later.

WHAT IT DOES NOT DO

No betting, no notifications, no live model. It fetches, it stamps, it appends. Section 156
requires the live path stay light: no retraining, no history rebuild, no report generation
inside a live cycle.

ODDS AGE IS RECORDED ON EVERY ROW

Section 140 is emphatic that a live decision cannot rest on a price several minutes old. The
API's own `update` field is the market timestamp, so `odds_age_seconds` is the difference
between that and our fetch. It is stored rather than enforced -- this module's job is evidence,
and a consumer decides what age is tolerable -- but rows past `STALE_ODDS_SECONDS` are flagged
so no later analysis can silently treat them as fresh.
"""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd

CALC_VERSION = "1.0.0"

# Beyond this a live price is not something anyone could have acted on (section 140).
STALE_ODDS_SECONDS = 120

# API-Football live market names -> our vocabulary. Only markets we actually model or can
# settle; the other ~260 are ignored rather than stored as noise.
LIVE_MARKETS = {
    "Over/Under Line": "TOTALS_LINE",          # the DYNAMIC line (section 133)
    "Over/Under": "TOTALS_LINE",
    "Both Teams to Score": "BTTS",
    "Asian Handicap": "AH",
    "3-Way Handicap": "AH_3WAY",
    "Home Team Goals": "HOME_GOALS",
    "How many goals will Home Team score?": "HOME_GOALS",
    "How many goals will Away Team score?": "AWAY_GOALS",
}

_LINE_RE = re.compile(r"(-?\d+(?:\.\d+)?)")


def _parse_line(value: str, handicap=None) -> tuple[str | None, float | None]:
    """('OVER'|'UNDER', line) for a live totals selection.

    THE LINE IS IN `handicap`, NOT IN THE VALUE STRING. Live payloads look like

        {"value": "Over", "odd": "2.2", "handicap": "1.5", "main": true}

    not "Over 2.5" as the pre-match feed does. The first version searched the value string for a
    number, found none, and produced 44 totals rows with a null line -- silently useless for the
    dynamic-line research in section 133, since the line IS the market. Handicap is preferred and
    the value string is only a fallback for feeds that inline it."""
    s = str(value or "").strip()
    side = ("OVER" if s.lower().startswith("over")
            else "UNDER" if s.lower().startswith("under") else None)
    if handicap is not None and str(handicap).strip() != "":
        m = _LINE_RE.search(str(handicap))
        if m:
            return side, float(m.group(1))
    m = _LINE_RE.search(s)
    return side, (float(m.group(1)) if m else None)


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def fetch(get_fn, *, now: dt.datetime | None = None) -> pd.DataFrame:
    """One live sweep. `get_fn` is api_football._get, injected so this is testable offline.

    Returns one row per (fixture, market, selection). Empty frame when nothing is live, which is
    the normal state most of the day and is NOT an error.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    payload = get_fn("/odds/live", {}, cache_hours=0) or {}
    resp = payload.get("response") or []
    rows: list[dict] = []

    for f in resp:
        fx = f.get("fixture") or {}
        st = fx.get("status") or {}
        teams = f.get("teams") or {}
        # SCORE LIVES UNDER teams.home.goals / teams.away.goals. There is no top-level `goals`
        # block, so the first version stored None for every score -- and a live model without the
        # scoreline is not a live model at all. Team NAMES are absent from this payload entirely;
        # only ids are given, so names are left to a join rather than invented here.
        home_t = teams.get("home") or {}
        away_t = teams.get("away") or {}
        # The market's own timestamp. Without it a price cannot be aged, so a missing `update`
        # is recorded as unknown rather than assumed to be now.
        upd = f.get("update")
        try:
            upd_ts = dt.datetime.fromisoformat(str(upd).replace("Z", "+00:00")) if upd else None
        except ValueError:
            upd_ts = None
        age = (now - upd_ts).total_seconds() if upd_ts else None

        base = {
            "snapshot_ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fixture_id": fx.get("id"),
            "match_status": st.get("long"),
            "match_minute": st.get("elapsed"),
            "home_team_id": home_t.get("id"),
            "away_team_id": away_t.get("id"),
            "home_score": home_t.get("goals"),
            "away_score": away_t.get("goals"),
            "match_seconds": (st.get("seconds") or None),
            "odds_updated_at": upd,
            "odds_age_seconds": round(age, 1) if age is not None else None,
            "odds_stale": bool(age is not None and age > STALE_ODDS_SECONDS),
            "calc_version": CALC_VERSION,
        }

        for bet in (f.get("odds") or []):
            fam = LIVE_MARKETS.get(str(bet.get("name")))
            if not fam:
                continue
            for v in (bet.get("values") or []):
                odd = _num(v.get("odd"))
                if odd is None or odd <= 1.0:
                    continue
                side, line = _parse_line(v.get("value"), v.get("handicap"))
                rows.append({
                    **base,
                    "market_family": fam,
                    "market_name": bet.get("name"),
                    "selection": str(v.get("value")),
                    "line": line,
                    "side": side,
                    "odds": odd,
                    # A suspended price is visible but not takeable. Kept, because a suspension
                    # is itself a signal that the market is reacting to something.
                    "suspended": bool(v.get("suspended", False)),
                    "handicap": v.get("handicap"),
                    # The book's own primary line. Several lines are quoted at once, and only
                    # this one is the headline market a price would normally be taken at.
                    "is_main_line": bool(v.get("main", False)),
                })
    return pd.DataFrame(rows)


def quality_flags(d: pd.DataFrame) -> pd.DataFrame:
    """Per-row quality, so no downstream analysis silently trusts a bad price."""
    if d.empty:
        return d
    out = d.copy()
    flags = []
    for r in out.itertuples():
        f = []
        if r.odds_age_seconds is None:
            f.append("NO_ODDS_TIMESTAMP")
        elif r.odds_stale:
            f.append("STALE_LIVE_ODDS")
        if r.suspended:
            f.append("SUSPENDED")
        if r.match_minute is None:
            f.append("NO_MATCH_MINUTE")
        if r.market_family == "TOTALS_LINE" and r.line is None:
            f.append("NO_LINE_PARSED")
        flags.append("|".join(f) if f else "OK")
    out["quality_flags"] = flags
    return out


def summarise(d: pd.DataFrame) -> dict:
    """What one sweep saw — for scheduler health (section 154)."""
    if d.empty:
        return {"live_fixtures": 0, "rows": 0, "markets": 0, "stale_pct": None,
                "suspended_pct": None, "median_odds_age_s": None}
    age = pd.to_numeric(d.get("odds_age_seconds"), errors="coerce")
    return {
        "live_fixtures": int(d["fixture_id"].nunique()),
        "rows": int(len(d)),
        "markets": int(d["market_family"].nunique()),
        "stale_pct": round(100.0 * float(d["odds_stale"].mean()), 2),
        "suspended_pct": round(100.0 * float(d["suspended"].mean()), 2),
        "median_odds_age_s": round(float(age.median()), 1) if age.notna().any() else None,
        "with_minute": int(d["match_minute"].notna().sum()),
    }

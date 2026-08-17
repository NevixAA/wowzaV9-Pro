"""
Canonical entity keys (Prompt 1 section 18).
============================================
v9's artifacts have NO fixture_id. `predictions.csv` identifies a fixture only by
(league, date, home_team, away_team), and club spellings differ between OddsAPI,
football-data.co.uk and API-Football — the failure that left 46% of standard fixtures with no
rolling-form features, and the one that made 35 of 56 prop fixtures unmatchable against
OddsAPI events.

So Pro derives a deterministic `fixture_key` and, separately, tracks how confident it is in
the club names behind it. Resolution failures are CLASSIFIED, not hidden: a fixture whose
entities are unresolved is flagged ENTITY_UNRESOLVED and can never become LIVE.

`resolve()` from v9/src/team_names.py is the intended canonical matcher and is ported in
phase 2. Until then `fixture_key` is derived from normalised names and is stable but
provisional — two spellings of one club still produce two keys, which is precisely what the
resolution-rate metric below is for.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

import pandas as pd

# Club-form words carrying no identity. Kept in sync with v9/src/team_names._GENERIC.
_GENERIC = {
    "fc", "cf", "sc", "afc", "cd", "sd", "ad", "ac", "ss", "as", "us", "sv", "vfl", "vfb",
    "fsv", "tsg", "spvgg", "msv", "bsc", "if", "ifk", "fk", "sk", "bk", "ca", "cp", "club",
    "calcio",
}


def norm_name(s) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    ascii_str = ascii_str.lower().replace("&", " and ")
    ascii_str = re.sub(r"[^a-z0-9 ]", " ", ascii_str)
    return re.sub(r"\s+", " ", ascii_str).strip()


def club_slug(s) -> str:
    """Identity tokens only, sorted — so 'VfL Wolfsburg' and 'Wolfsburg' agree, while
    'Manchester City' and 'Manchester United' stay distinct."""
    toks = [t for t in norm_name(s).split() if t not in _GENERIC and not t.isdigit()]
    return "-".join(sorted(toks)) or norm_name(s).replace(" ", "-")


def fixture_key(league, match_date, home, away) -> str:
    """Stable 16-hex key. Deterministic across runs and machines, which is what lets a
    backfilled row and a live row for the same fixture join."""
    d = str(match_date or "")[:10]
    raw = f"{norm_name(league)}|{d}|{club_slug(home)}|{club_slug(away)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def add_fixture_key(df: pd.DataFrame, *, league="league", date="match_date",
                    home="home_team", away="away_team") -> pd.DataFrame:
    out = df.copy()
    out["fixture_key"] = [
        fixture_key(l, d, h, a)
        for l, d, h, a in zip(out.get(league, ""), out.get(date, ""),
                              out.get(home, ""), out.get(away, ""))
    ]
    return out


def split_match(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """v9's odds histories store the fixture as one 'Home vs Away' string."""
    parts = series.astype(str).str.split(r"\s+vs\.?\s+", n=1, regex=True)
    home = parts.str[0].str.strip()
    away = parts.str[1].fillna("").str.strip() if parts.str.len().max() and True else ""
    return home, away


def resolution_rate(df: pd.DataFrame, *, by="league") -> pd.DataFrame:
    """Share of rows whose club names produced a non-degenerate slug, per league.
    Prompt 1 section 18 wants this tracked, not assumed."""
    if df.empty:
        return pd.DataFrame()
    ok = (df["home_team"].map(lambda s: bool(club_slug(s))) &
          df["away_team"].map(lambda s: bool(club_slug(s))))
    g = df.assign(_ok=ok).groupby(by)["_ok"]
    return pd.DataFrame({"rows": g.size(), "resolved": g.sum(),
                         "resolution_rate": g.mean().round(4)}).reset_index()

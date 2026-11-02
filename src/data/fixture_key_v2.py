"""
fixture_key v2: canonical league + canonical club identity (Data Truth round 2, 2026-11-02).
==========================================================================================
WHY A NEW VERSION. v1 (`entities.fixture_key_v1`) hashes `norm_name(league)` and a sorted
token slug of each club string. It never asked v9's league registry or v9's club resolver, so

  * a league alias ('Brazil Serie A' under another spelling) hashed to a different fixture;
  * the same club under the OddsAPI and the API-Football spelling ('Celta Fortuna' /
    'Celta de Vigo II', 'Sporting CP' / 'Sp Lisbon') produced two keys, and team_match_stats rows
    (API-Football names) did not join the board rows (OddsAPI names) for the same match;
  * a slug collision could merge two clubs whose identity tokens happen to sort the same.

v2 builds the key from

  league  -> v9 `league_registry.canonical_name` (via src/data/v9_config). Unknown -> NO key.
  date    -> the calendar date as written, parsed with an EXPLICIT format list. Unparseable -> NO key.
  clubs   -> v9 `team_names.resolve(name, vocabulary[league])`, where the vocabulary is a FROZEN,
             hash-pinned list of canonical club names per league (registry/identity/
             fixture_key_v2_clubs_1.0.json), built once from v9's own history bank through v9's
             own identity pipeline (scripts/build_fixture_key_v2_vocab.py).

A club the resolver cannot place (no candidate, or an ambiguous one - resolve() refuses rather
than guesses) is NOT mapped onto anything. Its token is its own normalised source spelling with a
distinct `u:` prefix, the row's `fixture_key_status` says CLUB_UNRESOLVED, and the migration lists
it. That keeps the row joinable to other rows carrying the SAME spelling (what v1 did) without
claiming an identity nobody proved. Two different source names resolving to the SAME canonical club
inside one fixture is refused too (CLUB_COLLISION): both fall back to their source spellings.

WHY A FROZEN VOCABULARY. A key is only useful if it is stable. Resolving against the live history
bank would change keys whenever a promoted club appeared and made an old spelling ambiguous. The
vocabulary is versioned and its sha256 is pinned below; a new vocabulary is a new VOCAB_VERSION and
a re-run of scripts/migrate_fixture_key_v2.py, never a silent edit.

`old_fixture_key` carries the v1 key on every row written by `add_keys`, so a v1 key that some
older artifact still holds can always be traced to its v2 key.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd

from config import pro_config as cfg
from src.data import entities as ent

log = logging.getLogger(__name__)

KEY_VERSION = "fk2"
VOCAB_VERSION = "fk2-clubs/1.0"
VOCAB_PATH = cfg.REGISTRY_DIR / "identity" / "fixture_key_v2_clubs_1.0.json"
# sha256 of json.dumps(vocab["leagues"], sort_keys=True, ensure_ascii=False). Pinned: an edited
# vocabulary changes keys, so it must arrive as a new version, never in place.
VOCAB_SHA256 = "34d0b3c6bcdd42c235b72fdca7923d6136c10112c67cad9eff9ce3c8d9782ac9"

RESOLVED = "RESOLVED"
CLUB_UNRESOLVED = "CLUB_UNRESOLVED"
CLUB_COLLISION = "CLUB_COLLISION"
LEAGUE_UNKNOWN = "LEAGUE_UNKNOWN"
DATE_UNPARSEABLE = "DATE_UNPARSEABLE"
CLUB_MISSING = "CLUB_MISSING"

# Every format the warehouse and v9's files actually carry (measured 2026-11-02 over all 23
# tables). Tried in order; nothing is inferred.
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M",
)


class VocabularyError(ValueError):
    """The frozen club vocabulary is missing or was edited. Keys cannot be built honestly."""


def parse_when(v) -> datetime | None:
    """A datetime from one of DATE_FORMATS, else None. Never inferred, never defaulted."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (pd.Timestamp, datetime)):
        return pd.Timestamp(v).to_pydatetime()
    s = str(v).strip()
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def match_day(v) -> str | None:
    """The calendar date AS WRITTEN (no timezone conversion: '2026-08-20T23:30:00-03:00' is the
    20th, as v1 read it), or None when the value matches no explicit format."""
    d = parse_when(v)
    return d.strftime("%Y-%m-%d") if d is not None else None


def to_utc_iso(v) -> str | None:
    """A kickoff value as 'YYYY-MM-DDTHH:MM:SSZ'. A naive value is taken as UTC, which is what
    every `kickoff_utc` column in the warehouse is by name and by its writer. None when
    unparseable."""
    d = parse_when(v)
    if d is None:
        return None
    ts = pd.Timestamp(d)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── vocabulary ────────────────────────────────────────────────────────────────────────────────

def vocab_sha256(leagues: dict) -> str:
    return hashlib.sha256(json.dumps(leagues, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


@lru_cache(maxsize=4)
def _load_vocab(path: str, verify: bool) -> dict:
    p = Path(path)
    if not p.exists():
        raise VocabularyError(f"fixture_key v2 club vocabulary missing: {p}")
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("version") != VOCAB_VERSION:
        raise VocabularyError(f"vocabulary version {d.get('version')!r} != {VOCAB_VERSION}")
    leagues = {str(k): [str(x) for x in v] for k, v in (d.get("leagues") or {}).items()}
    if verify and vocab_sha256(leagues) != VOCAB_SHA256:
        raise VocabularyError("vocabulary sha256 differs from the pinned one: a new vocabulary is "
                              "a new VOCAB_VERSION plus a re-key migration, not an edit")
    return leagues


def vocabulary(path: Path | None = None, *, verify: bool = True) -> dict:
    return _load_vocab(str(path or VOCAB_PATH), verify)


# ── resolution ────────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=512)
def canonical_league(name) -> str | None:
    from src.data import v9_config
    if name is None:
        return None
    return v9_config.canonical_league(name)


@lru_cache(maxsize=100_000)
def canonical_club(league: str, name: str) -> str | None:
    """v9 team_names.resolve against the frozen vocabulary of the CANONICAL league. None when the
    league has no vocabulary or the resolver finds nothing / refuses an ambiguous match."""
    from src.data import v9_config
    cands = vocabulary().get(league)
    if not cands or not name:
        return None
    return v9_config.team_names().resolve(name, cands)


def _norm(s) -> str:
    from src.data import v9_config
    return v9_config.team_names().norm(str(s))


def _blank(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return not str(v).strip()


def key_and_status(league, match_date, home, away) -> tuple[str | None, str]:
    """(v2 key or None, status). None only when the league is unknown to the registry, the date
    matches no explicit format, or a club name is blank."""
    lg = canonical_league(None if _blank(league) else str(league).strip())
    if lg is None:
        return None, LEAGUE_UNKNOWN
    day = match_day(match_date)
    if day is None:
        return None, DATE_UNPARSEABLE
    if _blank(home) or _blank(away):
        return None, CLUB_MISSING
    h, a = str(home).strip(), str(away).strip()
    ch, ca = canonical_club(lg, h), canonical_club(lg, a)
    status = RESOLVED
    if ch is not None and ch == ca:
        ch = ca = None
        status = CLUB_COLLISION
    elif ch is None or ca is None:
        status = CLUB_UNRESOLVED
    th = f"c:{_norm(ch)}" if ch is not None else f"u:{_norm(h)}"
    ta = f"c:{_norm(ca)}" if ca is not None else f"u:{_norm(a)}"
    raw = f"{KEY_VERSION}|{lg}|{day}|{th}|{ta}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16], status


def fixture_key(league, match_date, home, away) -> str | None:
    return key_and_status(league, match_date, home, away)[0]


def add_keys(df: pd.DataFrame, *, league="league", date="match_date",
             home="home_team", away="away_team", log_unresolved: bool = True) -> pd.DataFrame:
    """Write `fixture_key` (v2), `old_fixture_key` (v1), `fixture_key_version` and
    `fixture_key_status` on a copy of `df`. Computed once per distinct (league, date, home, away).
    Rows that cannot be keyed get fixture_key None and are logged, never given a made-up key."""
    out = df.copy()
    n = len(out)

    def col(c):
        return out[c] if c in out.columns else pd.Series([None] * n, index=out.index, dtype=object)

    quads = list(zip(col(league), col(date), col(home), col(away)))
    memo: dict = {}
    keys, stats, olds = [], [], []
    for qd in quads:
        hk = tuple("" if _blank(x) else str(x) for x in qd)
        if hk not in memo:
            memo[hk] = (key_and_status(*qd), ent.fixture_key_v1(*hk))
        (k, s), o = memo[hk]
        keys.append(k)
        stats.append(s)
        olds.append(o)
    out["fixture_key"] = pd.Series(keys, index=out.index, dtype=object)
    out["old_fixture_key"] = pd.Series(olds, index=out.index, dtype=object)
    out["fixture_key_version"] = KEY_VERSION
    out["fixture_key_status"] = pd.Series(stats, index=out.index, dtype=object)
    if log_unresolved and n:
        bad = out["fixture_key_status"] != RESOLVED
        if bad.any():
            vc = out.loc[bad, "fixture_key_status"].value_counts().to_dict()
            log.warning("[fixture_key v2] %d of %d row(s) not fully resolved: %s", int(bad.sum()), n, vc)
    return out


def unresolved_names(df: pd.DataFrame, *, league="league", home="home_team",
                     away="away_team") -> pd.DataFrame:
    """(league, name, rows) for every source club spelling the resolver could not place."""
    rows = []
    for side in (home, away):
        if side not in df.columns or league not in df.columns:
            continue
        g = df.groupby([league, side], dropna=False).size()
        for (lg, nm), cnt in g.items():
            c = canonical_league(None if _blank(lg) else str(lg).strip())
            if c is None or _blank(nm):
                continue
            if canonical_club(c, str(nm).strip()) is None:
                rows.append({"league": c, "name": str(nm), "rows": int(cnt)})
    if not rows:
        return pd.DataFrame(columns=["league", "name", "rows"])
    return (pd.DataFrame(rows).groupby(["league", "name"], as_index=False)["rows"].sum()
            .sort_values(["league", "name"]).reset_index(drop=True))


def clear_caches() -> None:
    _load_vocab.cache_clear()
    canonical_league.cache_clear()
    canonical_club.cache_clear()

"""Special-market quotes from the league scout's /odds pages (owner 2026-11-10: "we have all the league
scouters"). The scout already calls /odds?league&season, /odds?league&season&date and /odds?fixture for
every watched league; this keeps, from the SAME answers and at ZERO extra calls:

    Exact Score                    every score quoted ("h:a")
    Goals Over/Under               Over/Under 0.5, 4.5, 5.5, 6.5
    Total - Home / Total - Away    Over/Under 3.5                    (a side scoring 4+)

SAME RULES AS v9 (wowza-betting src/specials_quotes.py, 2026-11-10), not a fork:
  * a bet is kept only when its name EQUALS one of the four full-time names (first/second-half bets
    can never overwrite them);
  * a row exists only when the provider returned that bookmaker, bet, selection and a numeric decimal
    price above 1.0, captured BEFORE the kickoff the answer states (unknown kickoff -> not stored);
  * per (fixture, bookmaker, bet, selection, capture) a row is appended when the quote opens ("open"),
    when its price moves ("change"), and once per near rung T-1h / T-30m / T-10m when it did not move
    ("heartbeat"); the ladder is v9 src/book_quotes.LADDER.
tests/test_scout_specials.py runs v9's own parser on the same payload (when V9_LOCAL is checked out) and
requires identical kept quotes, so the two cannot drift silently. v9's module is not imported here: it
imports v9's `config` and `src`, which collide with Pro's packages of the same names.

APPEND-ONLY SIDECAR. data/season_<YYYY_YY>/scout_specials_quotes/<YYYY-MM>/<day>_<producer>[_pN].csv.
One file per producer (sweep = pro_scout.yml, near = pro_scout_near.yml): the two workflows push to main
independently, so one writer per file. A part rolls over to _p2, _p3 ... at MAX_PART_MB, keeping every
file far under GitHub's 100 MB per-file limit. Written rows are never rewritten.

The /odds answer carries no club names. They are taken from the scout's own /fixtures?date rows (sweep)
or from this sidecar's earlier rows of the same fixture (near loop); when neither has them they stay
missing, never guessed.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd

BET_EXACT, BET_OU, BET_HOME, BET_AWAY = "Exact Score", "Goals Over/Under", "Total - Home", "Total - Away"
BETS = (BET_EXACT, BET_OU, BET_HOME, BET_AWAY)
OU_LINES = frozenset({"0.5", "4.5", "5.5", "6.5"})
TEAM_LINES = frozenset({"3.5"})
#: v9 src/book_quotes.LADDER / HEARTBEAT_BANDS
LADDER = [("T-10m", 10), ("T-30m", 30), ("T-1h", 60), ("T-3h", 180), ("T-6h", 360)]
HEARTBEAT_BANDS = frozenset({"T-1h", "T-30m", "T-10m"})
CAPTURES = frozenset({"scout_sweep", "scout_near"})
PRODUCER = {"scout_sweep": "sweep", "scout_near": "near"}
TABLE = "scout_specials_quotes"
MAX_PART_MB = 80

COLUMNS = ["captured_at", "provider_update", "af_fixture_id", "fixture_key", "league_id", "league",
           "country", "match_date", "kickoff_utc", "home_team", "away_team", "bookmaker_id", "bookmaker",
           "bet_id", "bet", "selection", "odds", "capture", "minutes_to_kickoff", "ladder_band",
           "obs_reason"]

_SCORE = re.compile(r"^\d{1,2}:\d{1,2}$")


def keep_selection(bet: str, value: str) -> bool:
    """True when (bet, selection) is a kept special quote. `bet` must match EXACTLY (v9 rule)."""
    if bet == BET_EXACT:
        return bool(_SCORE.match(value))
    parts = value.split(" ")
    if len(parts) != 2 or parts[0] not in ("Over", "Under"):
        return False
    if bet == BET_OU:
        return parts[1] in OU_LINES
    if bet in (BET_HOME, BET_AWAY):
        return parts[1] in TEAM_LINES
    return False


def ladder_band(minutes: float | None) -> str:
    if minutes is None or (isinstance(minutes, float) and math.isnan(minutes)):
        return "UNKNOWN"
    if minutes < 0:
        return "POST"
    for name, edge in LADDER:
        if minutes <= edge:
            return name
    return "FAR"


def _utc(ts) -> pd.Timestamp | None:
    try:
        t = pd.Timestamp(ts)
    except Exception:                                                 # noqa: BLE001
        return None
    if pd.isna(t):
        return None
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _iso(t: pd.Timestamp | None) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t is not None else ""


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse(resp: list, *, capture: str, captured_at, names: dict | None = None,
          leagues: dict | None = None) -> list[dict]:
    """Kept special quotes of one /odds answer (`response` list, any number of fixtures).

    names:   {fixture_id: (home, away)} from the scout's own fixture rows; missing -> names stay missing.
    leagues: {league_id: (name, country)} from the scout registry; else the answer's own league block.
    """
    if capture not in CAPTURES:
        raise ValueError(f"unknown capture {capture!r}; expected one of {sorted(CAPTURES)}")
    cap = _utc(captured_at)
    if cap is None:
        return []
    names, leagues = names or {}, leagues or {}
    rows: list[dict] = []
    for entry in resp or []:
        fx = entry.get("fixture") or {}
        ko = None
        if fx.get("timestamp") is not None:
            try:
                ko = pd.Timestamp(int(fx["timestamp"]), unit="s", tz="UTC")
            except (TypeError, ValueError):
                ko = None
        if ko is None and fx.get("date"):
            ko = _utc(fx.get("date"))
        fid = _int(fx.get("id"))
        if ko is None or fid is None or cap >= ko:
            continue                                  # unknown kickoff / fixture, or not pre-match
        lg = entry.get("league") or {}
        lid = _int(lg.get("id"))
        lname, country = leagues.get(lid, (lg.get("name"), lg.get("country")))
        home, away = names.get(fid, (None, None))
        upd = _utc(entry.get("update")) if entry.get("update") else None
        ko_iso, cap_iso = _iso(ko), _iso(cap)
        mins = (ko - cap).total_seconds() / 60.0
        band = ladder_band(mins)
        fkey = f"{lname}|{ko_iso[:10]}|{home}|{away}" if (lname and home and away) else None
        for bk in entry.get("bookmakers") or []:
            bid = _int(bk.get("id"))
            if bid is None:
                continue
            bname = (bk.get("name") or "").strip()
            for bet in bk.get("bets") or []:
                name = bet.get("name")
                if name not in BETS:
                    continue
                for v in bet.get("values") or []:
                    sel = str(v.get("value") if v.get("value") is not None else "").strip()
                    if not keep_selection(name, sel):
                        continue
                    try:
                        odds = float(v.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if not math.isfinite(odds) or odds <= 1.0:
                        continue
                    rows.append({"captured_at": cap_iso, "provider_update": _iso(upd) or None,
                                 "af_fixture_id": fid, "fixture_key": fkey, "league_id": lid,
                                 "league": lname, "country": country, "match_date": ko_iso[:10],
                                 "kickoff_utc": ko_iso, "home_team": home, "away_team": away,
                                 "bookmaker_id": bid, "bookmaker": bname, "bet_id": _int(bet.get("id")),
                                 "bet": name, "selection": sel, "odds": odds, "capture": capture,
                                 "minutes_to_kickoff": round(mins, 1), "ladder_band": band})
    return rows


# ── append-only store ────────────────────────────────────────────────────────────────────────

def base_dir() -> Path:
    from config import pro_config as cfg
    return cfg.season_dir() / TABLE


def _files(base: Path, producer: str) -> list[Path]:
    if not base.exists():
        return []
    def order(p: Path):
        m = re.search(r"_p(\d+)$", p.stem)
        return (p.name[:10], int(m.group(1)) if m else 1)
    return sorted(base.glob(f"*/*_{producer}*.csv"), key=order)


def _target(base: Path, day: str, producer: str) -> Path:
    month = base / day[:7]
    parts = [p for p in _files(base, producer) if p.name[:10] == day]
    p = parts[-1] if parts else month / f"{day}_{producer}.csv"
    if p.exists() and p.stat().st_size / 1e6 >= MAX_PART_MB:
        n = len(parts) + 1
        p = month / f"{day}_{producer}_p{n}.csv"
    return p


def _k(df: pd.DataFrame) -> pd.Series:
    return (df["af_fixture_id"].astype("int64").astype(str) + "|"
            + df["bookmaker_id"].astype("int64").astype(str) + "|" + df["bet"].astype(str) + "|"
            + df["selection"].astype(str) + "|" + df["capture"].astype(str))


#: per-process memory of what each producer has stored: {(base, producer): (days, last_odds, seen_bands)}.
#: One process is the only writer of its producer's files, so after the first load the in-memory state
#: is exact; it saves the near loop re-reading the day files on every pass.
_STATE: dict = {}


def _state(base: Path, producer: str, day: str):
    key = (str(base), producer)
    st = _STATE.get(key)
    if st is not None and st[0] == day:
        return st
    days = sorted({p.name[:10] for p in _files(base, producer) if p.name[:10] <= day})[-2:]
    frames = [pd.read_csv(p, low_memory=False) for p in _files(base, producer) if p.name[:10] in days]
    frames = [f for f in frames if len(f)]
    last, seen = {}, set()
    if frames:
        old = pd.concat(frames, ignore_index=True).sort_values("captured_at", kind="stable")
        ok = _k(old)
        last = dict(zip(ok, old["odds"].astype(float)))
        seen = set(zip(ok, old["ladder_band"].astype(str)))
    st = (day, last, seen)
    _STATE[key] = st
    return st


def append(rows: list[dict], base: Path | None = None, dry: bool = False) -> int:
    """Append open / change / near-rung heartbeat rows to each producer's day part. Returns rows kept."""
    if not rows:
        return 0
    base = Path(base) if base is not None else base_dir()
    df = pd.DataFrame(rows).reindex(columns=COLUMNS)
    bad = set(df["capture"]) - CAPTURES
    if bad:
        raise ValueError(f"unknown capture(s) {sorted(bad)}")
    df["_day"] = df["captured_at"].astype(str).str[:10]
    df["_prod"] = df["capture"].map(PRODUCER)
    total = 0
    for (day, prod), chunk in df.groupby(["_day", "_prod"], sort=True):
        total += _append_one(chunk.drop(columns=["_day", "_prod"]), base, day, prod, dry)
    return total


def _append_one(df: pd.DataFrame, base: Path, day: str, producer: str, dry: bool) -> int:
    df = df.sort_values("captured_at", kind="stable").copy()
    df["_k"] = _k(df)
    df = df.drop_duplicates(["_k", "captured_at"], keep="last")
    _, last, seen = _state(base, producer, day)
    if dry:                                   # never mutate the state on a dry run
        last, seen = dict(last), set(seen)
    keep, reason = [], []
    for k, o, b in zip(df["_k"], df["odds"].astype(float), df["ladder_band"].astype(str)):
        prev = last.get(k)
        if prev is None:
            r = "open"
        elif not math.isclose(prev, o, rel_tol=0, abs_tol=1e-9):
            r = "change"
        elif b in HEARTBEAT_BANDS and (k, b) not in seen:
            r = "heartbeat"
        else:
            r = ""
        keep.append(bool(r))
        reason.append(r)
        if r:
            last[k] = o
            seen.add((k, b))
    df["obs_reason"] = reason
    out = df[pd.Series(keep, index=df.index)].drop(columns="_k")[COLUMNS]
    if out.empty:
        return 0
    if dry:
        print(f"  [dry-run] would append {len(out):,} special quote(s) to {TABLE}")
        return int(len(out))
    p = _target(base, day, producer)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    out.to_csv(p, mode="w" if new else "a", header=new, index=False)
    return int(len(out))


def known_names(fixture_ids, base: Path | None = None) -> dict:
    """{fixture_id: (home, away)} from this sidecar's earlier rows (any producer, last 2 day files each),
    for the near loop, whose /odds answers carry no club names."""
    base = Path(base) if base is not None else base_dir()
    ids = {int(x) for x in fixture_ids}
    out: dict = {}
    if not ids:
        return out
    for prod in PRODUCER.values():
        files = _files(base, prod)
        days = sorted({p.name[:10] for p in files})[-2:]
        for p in (f for f in files if f.name[:10] in days):
            d = pd.read_csv(p, usecols=["af_fixture_id", "home_team", "away_team"], low_memory=False)
            d = d[d["af_fixture_id"].isin(ids) & d["home_team"].notna() & d["away_team"].notna()]
            for r in d.drop_duplicates("af_fixture_id").itertuples(index=False):
                out[int(r.af_fixture_id)] = (r.home_team, r.away_team)
    return out


def registry_leagues(watch: list[dict]) -> dict:
    """{league_id: (name, country)} from the scout registry entries."""
    return {int(x["id"]): (x.get("name"), x.get("country")) for x in watch if x.get("id") is not None}

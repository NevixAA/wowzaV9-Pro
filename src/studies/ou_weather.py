"""HISTORICAL WEATHER feature table for the O/U information-inputs study (research only).

    python -m src.studies.ou_weather            # build (resumable; every response cached)

Builds experiments/ou_info_inputs_2026_10/weather_features.parquet: one row per v9 fixture since
2023-07-01, keyed by (league, date, home_team, away_team) in v9's spellings, with the weather in
the match window at the HOME team's ground. It trains nothing and writes nowhere else except
weather_audit.json and the response cache (weather_cache/).

PIPELINE
  1. v9 row -> API-Football fixture via common.match_frames (refuses ambiguous joins). Kickoff is
     the fixture's UTC timestamp.
  2. home_id -> /teams?id (API-Football) -> venue name + city + team.country.
  3. city -> Open-Meteo geocoding, keeping only results in the team's country (ISO code). No match
     in the team's country = NO location (never a guess in another country).
  4. one Open-Meteo archive call per distinct coordinate per contiguous run of match dates
     (runs are split at gaps > 14 days; the free tier bills max(1, days/14) calls per request and
     allows ~10k weighted calls/day, so a full build takes more than one day — it is resumable).
  5. hours h, h+1, h+2 UTC where h = floor(kickoff hour): temp_c mean, precip_mm sum, wind_kmh mean,
     gust_kmh max, humidity mean. Any missing hour -> NaN for that variable (never 0).

KNOWN LIMITS (all reported in the audit, none "fixed" silently)
  * The location is the CITY centroid of the home team's CURRENT venue (/teams is not dated), so a
    ground-share, temporary relocation or neutral venue gets the wrong place. `at_home_venue`
    compares each fixture's own venue id (from the cached /fixtures responses) with the team venue.
  * Roofed / retractable-roof stadia get outdoor weather like everyone else (only listed).
  * Open-Meteo hourly precipitation is the sum over the PRECEDING hour, so the h..h+2 sum covers
    h-1..h+2 — one hour before kickoff to roughly the 75th minute.
  * This is REALISED weather. A pre-match model only ever sees a forecast; using these columns as
    pre-match inputs is optimistic (look-ahead) and has to be treated as an upper bound.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import re
import sys
import time
import unicodedata
from datetime import date, timedelta

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies import common

EXP = cfg.BASE_DIR / "experiments" / "ou_info_inputs_2026_10"
WCACHE = EXP / "weather_cache"
AF_CACHE = EXP / "cache"
START = "2023-07-01"
AF = "https://v3.football.api-sports.io"
GEO = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
HOURLY = ["temperature_2m", "precipitation", "wind_speed_10m", "wind_gusts_10m", "relative_humidity_2m"]
AF_BUDGET = 1500
SLEEP = 0.2
FAR_KM = 300.0

CALLS = {"api_football": 0, "om_geocoding": 0, "om_archive": 0, "om_archive_weight": 0.0}

#: API-Football team.country -> ISO 3166-1 alpha-2 (Open-Meteo `country_code`).
COUNTRY_ISO = {
    "England": "GB", "Scotland": "GB", "Wales": "GB", "Northern-Ireland": "GB", "Ireland": "IE",
    "Argentina": "AR", "Austria": "AT", "Brazil": "BR", "China": "CN", "Denmark": "DK",
    "Finland": "FI", "Japan": "JP", "South-Korea": "KR", "Mexico": "MX", "Norway": "NO",
    "Romania": "RO", "Saudi-Arabia": "SA", "Sweden": "SE", "USA": "US", "Canada": "CA",
    "Belgium": "BE", "Germany": "DE", "Netherlands": "NL", "Greece": "GR", "Spain": "ES",
    "France": "FR", "Italy": "IT", "Portugal": "PT", "Turkey": "TR", "Andorra": "AD", "Monaco": "MC",
    "San-Marino": "SM", "Liechtenstein": "LI", "Switzerland": "CH",
}

#: Known fully roofed / retractable-roof grounds (substring of the lower-cased venue name). Report
#: only: these rows still carry outdoor weather. "toyota stadium" also matches Frisco (open) — it is
#: a CANDIDATE list, not a verdict.
ROOFED_HINTS = ["johan cruijff", "gelredome", "friends arena", "strawberry arena", "nationalarena",
                "tele2 arena", "parken", "mercedes-benz stadium", "bc place", "sapporo dome",
                "oita bank dome", "showa denko dome", "resonac dome", "toyota stadium", "noevir",
                "arena nationala", "arena națională", "unity arena", "kingdom arena", "telia parken",
                "olympic stadium montreal", "stade olympique", "allianz stadium", "nissan stadium",
                "düsseldorf arena", "merkur spiel-arena", "esprit arena", "veltins"]


class DailyLimit(RuntimeError):
    pass


def _bump_ledger(kind: str) -> None:
    """Cumulative call count across runs (weather_cache/call_ledger.json) — crashes included."""
    f = WCACHE / "call_ledger.json"
    led = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    led[kind] = led.get(kind, 0) + 1
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(led), encoding="utf-8")


# ── HTTP with permanent cache ─────────────────────────────────────────────────────────────────
def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:80] or "x"


def _load(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if path.suffix == ".gz":
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(obj, f)
    else:
        tmp.write_text(json.dumps(obj), encoding="utf-8")
    tmp.replace(path)


def _om_get(url: str, params: dict, cache_path, kind: str, weight: float = 1.0):
    """Open-Meteo GET with cache, 0.2 s pacing and 429 handling (minutely/hourly -> wait, daily -> stop)."""
    import requests
    if cache_path.exists():
        return _load(cache_path)
    waited = 0
    for attempt in range(12):
        time.sleep(SLEEP)
        try:
            r = requests.get(url, params=params, timeout=120)
        except requests.RequestException:
            time.sleep(5 * (attempt + 1))
            continue
        CALLS[kind] += 1
        _bump_ledger(kind)
        if kind == "om_archive":
            CALLS["om_archive_weight"] += weight
        if r.status_code == 429 or (r.status_code >= 500):
            reason = ""
            try:
                reason = r.json().get("reason", "")
            except ValueError:
                pass
            if "daily" in reason.lower():
                raise DailyLimit(reason)
            pause = 3600 if "hourly" in reason.lower() else 65
            if waited + pause > 2 * 3600:
                raise DailyLimit(f"gave up after waiting {waited}s: {reason}")
            print(f"  429/{r.status_code} {reason[:80]!r} -> sleeping {pause}s", flush=True)
            time.sleep(pause)
            waited += pause
            continue
        body = r.json()
        if r.status_code != 200 or body.get("error"):
            # a 400 (bad request) is deterministic: cache it so reruns do not re-spend it
            body = {"_http_status": r.status_code, **(body if isinstance(body, dict) else {})}
        _save(cache_path, body)
        return body
    raise RuntimeError(f"Open-Meteo {kind} failed repeatedly: {params}")


def _af_team(team_id: int) -> dict:
    import requests
    f = WCACHE / "teams" / f"team_{int(team_id)}.json"
    if f.exists():
        return _load(f)
    if CALLS["api_football"] >= AF_BUDGET or _TEAMS["off"]:
        return None
    body = {}
    # The key is shared with other jobs (measured 2026-10-19: ~370 of the 450/min window in use by
    # someone else, so roughly every other /teams call bounced). Pace on the per-minute header, give
    # each team 3 tries, and after 8 teams in a row fail, stop asking: the caller falls back to the
    # venue on the team's own cached home fixtures (zero calls) and records the source per row.
    for attempt in range(3):
        time.sleep(0.3)
        r = requests.get(f"{AF}/teams", headers={"x-apisports-key": common._af_key()},
                         params={"id": int(team_id)}, timeout=60)
        CALLS["api_football"] += 1
        _bump_ledger("api_football")
        body = r.json()
        try:
            left = int(r.headers.get("x-ratelimit-remaining", "999"))
        except ValueError:
            left = 999
        if not body.get("errors"):
            if left < 25:
                time.sleep(20)
            break
        if CALLS["api_football"] >= AF_BUDGET:
            break
        rate = "ratelimit" in json.dumps(body.get("errors")).lower()
        print(f"  API-Football error ({'rate limit' if rate else 'other'}) -> retry", flush=True)
        time.sleep(20 if rate else 2 + 3 * attempt)
    if body.get("errors"):
        _TEAMS["fail_streak"] += 1
        if _TEAMS["fail_streak"] >= 8:
            _TEAMS["off"] = True
            print("  /teams switched off for this run (8 consecutive failed teams)", flush=True)
        return None
    _TEAMS["fail_streak"] = 0
    _save(f, body)
    return body


#: WX_NO_TEAMS=1 -> use only cached /teams responses (no new API-Football calls); uncached teams fall
#: back to their modal cached home-fixture venue. Rerunning without it later fills the gaps.
_TEAMS = {"fail_streak": 0, "off": os.getenv("WX_NO_TEAMS", "") == "1"}


# ── step 1: v9 rows -> AF fixtures ────────────────────────────────────────────────────────────
def _matched() -> pd.DataFrame:
    v9 = pd.read_parquet(EXP / "v9_frame_dedup.parquet",
                         columns=["league", "date", "season", "home_team", "away_team", "track"])
    v9 = v9[pd.to_datetime(v9["date"]) >= START].reset_index(drop=True)
    dup = v9.duplicated(["league", "date", "home_team", "away_team"]).sum()
    if dup:
        raise RuntimeError(f"{dup} duplicate keys in v9_frame_dedup since {START}")
    af = pd.read_parquet(EXP / "af_fixtures.parquet")
    af = af[pd.to_datetime(af["fixture_ts"], utc=True) >= pd.Timestamp(START, tz="UTC") - pd.Timedelta(days=3)]
    af = af.drop_duplicates("af_fixture_id").reset_index(drop=True)
    af["match_date"] = af["fixture_ts"].str[:10]
    cache = WCACHE / "match_index.parquet"
    if cache.exists():
        mi = pd.read_parquet(cache)
        if len(mi) == len(v9) and (mi["key"].values == (v9["league"] + "|" + v9["date"].astype(str) + "|"
                                                          + v9["home_team"] + "|" + v9["away_team"]).values).all():
            idx = mi["idx"]
        else:
            mi = None
    else:
        mi = None
    if mi is None:
        print(f"matching {len(v9):,} v9 rows to {len(af):,} AF fixtures ...", flush=True)
        idx = common.match_frames(v9.assign(match_date=v9["date"].astype(str).str[:10]), af)
        WCACHE.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"key": (v9["league"] + "|" + v9["date"].astype(str) + "|" + v9["home_team"]
                              + "|" + v9["away_team"]).values, "idx": idx.values}).to_parquet(cache, index=False)
    idx = pd.Series(np.asarray(idx, dtype=float), index=v9.index)
    ok = idx.notna()
    take = af.loc[idx[ok].astype(int).values, ["af_fixture_id", "fixture_ts", "home_id", "away_id"]]
    take.index = v9.index[ok]
    out = v9.join(take)
    # A fixture claimed by two v9 rows: measured 2026-10-19, these are v9 near-duplicates of ONE
    # match (same clubs, dates one day apart: local vs UTC date; 1,148 rows, mostly MLS / Brazil /
    # Argentina / Liga MX). Each row matched its fixture uniquely, so both keep the weather of the
    # one real match; they are flagged, not dropped, and counted in the audit.
    d = out["af_fixture_id"].notna() & out["af_fixture_id"].duplicated(keep=False)
    out["v9_dup_same_fixture"] = d.astype(float)
    out.attrs["double_claimed"] = int(d.sum())
    return out


def _fixture_venues() -> pd.DataFrame:
    """Every cached /fixtures row: af_fixture_id, home_id, home name, venue (id, name, city), league
    country, kickoff. Zero API calls — these were pulled by ou_info_inputs.fetch()."""
    rows = []
    for f in AF_CACHE.glob("fixtures_*.json"):
        for x in _load(f).get("response", []):
            v = (x.get("fixture") or {}).get("venue") or {}
            rows.append({"af_fixture_id": x["fixture"]["id"], "home_id": x["teams"]["home"]["id"],
                         "home_name": x["teams"]["home"]["name"], "fv_id": v.get("id"),
                         "fv_name": v.get("name"), "fv_city": v.get("city"),
                         "league_country": (x.get("league") or {}).get("country"),
                         "ts": x["fixture"].get("date")})
    return pd.DataFrame(rows).drop_duplicates("af_fixture_id")


def _modal_home_venue(fx: pd.DataFrame, tid: int) -> dict:
    """Fallback location: the venue a team used most often for its home fixtures since START."""
    g = fx[(fx["home_id"] == tid) & (fx["ts"] >= START) & fx["fv_city"].notna()]
    if g.empty:
        return {}
    top = g.groupby(["fv_id", "fv_name", "fv_city"], dropna=False).size().sort_values().index[-1]
    return {"name": g["home_name"].iloc[-1], "country": g["league_country"].mode().iat[0],
            "venue": {"id": top[0], "name": top[1], "city": top[2]}}


# ── step 2-3: venues + geocoding ──────────────────────────────────────────────────────────────
def _city_variants(city: str) -> list[str]:
    c = str(city or "").strip()
    if not c:
        return []
    out = [c]
    first = c.split(",")[0].strip()
    out.append(first)
    for pre in ("Ciudad de ", "Ciudad Autónoma de ", "City of "):
        if first.startswith(pre):
            out.append(first[len(pre):])
    stripped = re.sub(r"\s*\(.*?\)\s*", " ", first).strip()
    out.append(stripped)
    for sep in (" - ", "-", "/"):
        if sep in stripped:
            out.append(stripped.split(sep)[0].strip())
    seen, res = set(), []
    for v in out:
        if v and v.lower() not in seen:
            seen.add(v.lower())
            res.append(v)
    return res


#: API-Football city strings the geocoder cannot resolve (endonyms, exonyms, abbreviations) or
#: resolves to the wrong same-name town. Found on the 2026-10-19 build; value = (query, admin1 hint).
CITY_ALIAS = {
    "Caerdydd": ("Cardiff", ""), "Casnewydd": ("Newport", "Wales"), "Wrecsam": ("Wrexham", ""),
    "La Haye": ("The Hague", ""), "Lisboa": ("Lisbon", ""), "Wien": ("Vienna", ""),
    "Genova": ("Genoa", ""), "La Coruña": ("A Coruña", ""), "Åland": ("Mariehamn", ""),
    "Åbo": ("Turku", ""), "Esbo": ("Espoo", ""), "St.-Trond": ("Sint-Truiden", ""),
    "Bruxelles": ("Brussels", ""), "Ji'nan": ("Jinan", ""), "Levadia": ("Livadeia", ""),
    "D.F.": ("Mexico City", ""), "León de los Aldamas": ("León", "Guanajuato"),
    "Al Majmaah": ("Al Majma'ah", ""), "Al-Hofuf": ("Hofuf", ""), "Hail": ("Ha'il", ""),
    "Vila das Aves": ("Aves", ""), "Harrison": ("Harrison", "New Jersey"), "Bronx": ("New York", "New York"),
    "Derry": ("Derry", "Northern Ireland"), "Hamilton": ("Hamilton", "Scotland"),
    "Livingston": ("Livingston", "Scotland"), "Boston": ("Boston", "England"),
    "San Fernando, Provincia de Buenos Aires": ("Tigre", "Buenos Aires"),
    "Chester": ("Chester", "Pennsylvania"), "Carson": ("Carson", "California"),
    "Villarreal": ("Vila-real", "Valencia"), "Tucuman": ("San Miguel de Tucumán", "Tucumán"),
    "Lyngby": ("Kongens Lyngby", ""), "Ried": ("Ried im Innkreis", ""), "Mantova": ("Mantua", "Lombardy"),
    "Anyang": ("Anyang-si", "Gyeonggi"), "San Sebastian": ("Donostia", "Basque"),
}
#: Clubs that play across a border from their league: Derry City (Ireland league, Northern Ireland),
#: FC Andorra (Spanish league, Andorra), Welsh clubs in English leagues (GB either way).
EXTRA_ISO = {"IE": {"GB"}, "ES": {"AD"}, "FI": {"AX"}}


def _geocode(city: str, isos: set):
    isos = set(isos)
    for i in list(isos):
        isos |= EXTRA_ISO.get(i, set())
    iso = bool(isos)
    alias = CITY_ALIAS.get(str(city).strip())
    hint = (alias[1].lower() if alias else
            (str(city).split(",")[1].strip().lower() if "," in str(city) else ""))
    for q in ([alias[0]] if alias else _city_variants(city)):
        body = _om_get(GEO, {"name": q, "count": 20, "language": "en", "format": "json"},
                       WCACHE / "geo" / f"geo20_{_slug(q)}.json", "om_geocoding")
        res = body.get("results") or []
        cand = [r for r in res if r.get("country_code") in isos]
        if not cand:
            continue
        if hint:
            hs = _slug(hint)
            h = [r for r in cand if hs in _slug(r.get("admin1", "")) or hs in _slug(r.get("admin2", ""))]
            if alias and not h:
                continue          # a pinned alias with a region must land in that region
            cand = h or cand
        # Open-Meteo's own ranking (first result). Tried and rejected 2026-10-19: "most populous"
        # (Vancouver Island, a Venezia hamlet) and "exact name" (Washington, Utah; Puebla in Baja
        # California). The same-name misses of first-result (Bronx -> Idaho, Carson -> Nevada,
        # Chester -> Illinois, Villarreal -> Extremadura) are pinned in CITY_ALIAS instead.
        r = cand[0]
        return {"lat": r["latitude"], "lon": r["longitude"], "geo_name": r.get("name"),
                "geo_admin1": r.get("admin1"), "geo_country": r.get("country_code"),
                "geo_query": q, "geocode_status": "ok_alias" if alias else "ok"}
    return {"lat": np.nan, "lon": np.nan, "geo_name": None, "geo_admin1": None, "geo_country": None,
            "geo_query": None, "geocode_status": "no_iso" if not iso else "no_match_in_country"}


def _venues(home_ids, fx: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for n, tid in enumerate(sorted({int(x) for x in home_ids})):
        body = _af_team(tid)
        resp = (body or {}).get("response") or []
        if resp:
            t = resp[0].get("team") or {}
            v = resp[0].get("venue") or {}
            source = "af_teams"
            country = t.get("country")
            isos = {COUNTRY_ISO[country]} if country in COUNTRY_ISO else set()
        else:
            fb = _modal_home_venue(fx, tid)
            t, v = {"name": fb.get("name"), "country": fb.get("country")}, fb.get("venue") or {}
            source = "fixture_modal_venue" if fb else "none"
            country = fb.get("country")       # LEAGUE country: MLS hosts Canadian clubs
            isos = ({COUNTRY_ISO[country]} if country in COUNTRY_ISO else set())
            if country == "USA":
                isos |= {"CA"}
        row = {"home_id": tid, "af_team": t.get("name"), "team_country": country, "venue_source": source,
               "venue_id": v.get("id"), "venue_name": v.get("name"), "venue_city": v.get("city"),
               "venue_capacity": v.get("capacity"), "venue_surface": v.get("surface")}
        if not v.get("city"):
            row.update({"lat": np.nan, "lon": np.nan, "geocode_status": "no_city"})
        else:
            row.update(_geocode(v["city"], isos))
        rows.append(row)
        if (n + 1) % 50 == 0:
            print(f"  teams {n + 1}: AF calls this run={CALLS['api_football']} /teams off={_TEAMS['off']}",
                  flush=True)
    return pd.DataFrame(rows)


# ── step 4: archive ───────────────────────────────────────────────────────────────────────────
def _segments(dates: list[date], gap: int = 14) -> list[tuple[date, date]]:
    """Contiguous runs of match dates. Open-Meteo bills max(1, days/14) per request, so extending a
    run across a gap of g days costs ~g/14 while a new request costs 1: split when g > 14. Measured
    2026-10-19: gap=14 -> ~10.4k requests / ~16.8k weighted; gap=27 -> 3.8k requests but ~22.7k
    weighted. The weighted figure is what the daily limit counts."""
    ds = sorted(set(dates))
    segs, s, e = [], ds[0], ds[0]
    for d in ds[1:]:
        if (d - e).days > gap:
            segs.append((s, e))
            s = d
        e = d
    segs.append((s, e))
    return segs


def _archive(lat, lon, d0: date, d1: date):
    cap = date.today() - timedelta(days=1)
    d1 = min(d1, cap)
    if d0 > d1:
        return None
    days = (d1 - d0).days + 1
    weight = max(1.0, days / 14.0)
    # reuse any cached response for this coordinate whose range already covers [d0, d1]
    for g in (WCACHE / "archive").glob(f"arch_{lat:.4f}_{lon:.4f}_*.json.gz"):
        parts = g.name[: -len(".json.gz")].split("_")
        try:
            c0, c1 = date.fromisoformat(parts[-2]), date.fromisoformat(parts[-1])
        except ValueError:
            continue
        if c0 <= d0 and c1 >= d1:
            return _load(g)
    f = WCACHE / "archive" / f"arch_{lat:.4f}_{lon:.4f}_{d0}_{d1}.json.gz"
    return _om_get(ARCHIVE, {"latitude": lat, "longitude": lon, "start_date": str(d0), "end_date": str(d1),
                             "hourly": ",".join(HOURLY), "timezone": "UTC"}, f, "om_archive", weight)


def _haversine(a_lat, a_lon, b_lat, b_lon):
    p = math.pi / 180
    x = (math.sin((b_lat - a_lat) * p / 2) ** 2 + math.cos(a_lat * p) * math.cos(b_lat * p)
         * math.sin((b_lon - a_lon) * p / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(x))


# ── build ─────────────────────────────────────────────────────────────────────────────────────
def build() -> dict:
    WCACHE.mkdir(parents=True, exist_ok=True)
    m = _matched()
    print(f"v9 rows since {START}: {len(m):,}; matched to AF: {m['af_fixture_id'].notna().sum():,}"
          f" (v9 near-duplicate rows sharing a fixture: {m.attrs['double_claimed']})", flush=True)

    double_claimed = m.attrs["double_claimed"]
    fx = _fixture_venues()
    ven = _venues(m.loc[m["home_id"].notna(), "home_id"], fx)
    print(f"home teams: {len(ven)}; API-Football calls this run: {CALLS['api_football']}; "
          f"geocoded: {ven['geocode_status'].str.startswith('ok').sum()}; sources: "
          f"{ven['venue_source'].value_counts().to_dict()}", flush=True)
    m = m.merge(ven, on="home_id", how="left")

    fvi = fx.set_index("af_fixture_id")
    ids = m["af_fixture_id"]
    m["fixture_venue_id"] = pd.to_numeric(ids.map(fvi["fv_id"]), errors="coerce")
    m["fixture_venue_name"] = ids.map(fvi["fv_name"])
    both = m["fixture_venue_id"].notna() & m["venue_id"].notna()
    m["at_home_venue"] = np.where(both, (m["fixture_venue_id"] == m["venue_id"]).astype(float), np.nan)

    m["kickoff_utc"] = pd.to_datetime(m["fixture_ts"], utc=True, errors="coerce")
    m["kick_hour"] = m["kickoff_utc"].dt.floor("h")

    # archive calls per coordinate x contiguous date run
    have = m["lat"].notna() & m["kick_hour"].notna()
    m["coord"] = np.where(have, m["lat"].round(4).astype(str) + "," + m["lon"].round(4).astype(str), None)
    plan = []
    for coord, g in m[have].groupby("coord"):
        lat, lon = map(float, coord.split(","))
        dts = [d.date() for d in g["kick_hour"].dt.tz_convert(None)]
        for s, e in _segments(dts):
            plan.append((lat, lon, s, e + timedelta(days=1)))
    est = sum(max(1.0, ((min(e, date.today() - timedelta(days=1)) - s).days + 1) / 14) for _, _, s, e in plan)
    print(f"coordinates: {m['coord'].nunique()}; archive requests: {len(plan)} "
          f"(~{est:,.0f} weighted Open-Meteo calls if nothing is cached)", flush=True)

    hourly: dict[str, pd.DataFrame] = {}
    pending = 0
    stopped = None
    for i, (lat, lon, s, e) in enumerate(plan):
        if stopped:
            pending += 1
            continue
        try:
            body = _archive(lat, lon, s, e)
        except DailyLimit as ex:
            stopped = str(ex)
            pending += 1
            print(f"  STOP: {ex}", flush=True)
            continue
        if (i + 1) % 50 == 0:
            print(f"  archive {i + 1}/{len(plan)}  calls={CALLS['om_archive']} "
                  f"weight={CALLS['om_archive_weight']:.0f}", flush=True)
        if not body or "hourly" not in body:
            continue
        h = body["hourly"]
        df = pd.DataFrame({k: pd.to_numeric(pd.Series(h.get(k)), errors="coerce") for k in HOURLY})
        df.index = pd.to_datetime(pd.Series(h["time"]), utc=True)
        key = f"{round(lat, 4)},{round(lon, 4)}"
        hourly[key] = pd.concat([hourly[key], df]) if key in hourly else df

    # step 5: match-window features
    win = {c: np.full(len(m), np.nan) for c in ("temp_c", "precip_mm", "wind_kmh", "gust_kmh", "humidity")}
    for key, df in hourly.items():
        df = df[~df.index.duplicated(keep="first")].sort_index()
        rows = np.flatnonzero((m["coord"] == key).values)
        for r in rows:
            h0 = m["kick_hour"].iat[r]
            w = df.reindex([h0, h0 + pd.Timedelta(hours=1), h0 + pd.Timedelta(hours=2)])
            win["temp_c"][r] = w["temperature_2m"].mean() if w["temperature_2m"].notna().all() else np.nan
            win["precip_mm"][r] = w["precipitation"].sum() if w["precipitation"].notna().all() else np.nan
            win["wind_kmh"][r] = w["wind_speed_10m"].mean() if w["wind_speed_10m"].notna().all() else np.nan
            win["gust_kmh"][r] = w["wind_gusts_10m"].max() if w["wind_gusts_10m"].notna().all() else np.nan
            win["humidity"][r] = (w["relative_humidity_2m"].mean()
                                  if w["relative_humidity_2m"].notna().all() else np.nan)
    for c, v in win.items():
        m[c] = v

    def flag(x, cond):
        return np.where(np.isnan(x), np.nan, cond.astype(float))
    m["heavy_rain"] = flag(m["precip_mm"].values, m["precip_mm"].values >= 3)
    m["strong_wind"] = flag(m["wind_kmh"].values, m["wind_kmh"].values >= 30)
    m["hot"] = flag(m["temp_c"].values, m["temp_c"].values >= 28)
    m["cold"] = flag(m["temp_c"].values, m["temp_c"].values <= 2)

    cols = ["league", "date", "home_team", "away_team", "season", "track", "af_fixture_id", "kickoff_utc",
            "home_id", "af_team", "team_country", "venue_source", "venue_id", "venue_name", "venue_city", "lat", "lon",
            "geocode_status", "fixture_venue_id", "fixture_venue_name", "at_home_venue", "v9_dup_same_fixture",
            "temp_c", "precip_mm", "wind_kmh", "gust_kmh", "humidity",
            "heavy_rain", "strong_wind", "hot", "cold"]
    out = m[cols].copy()
    out.to_parquet(EXP / "weather_features.parquet", index=False)

    audit = _audit(out, ven, pending, stopped, double_claimed)
    (EXP / "weather_audit.json").write_text(json.dumps(audit, indent=2, default=str), encoding="utf-8")
    return audit


def _audit(out: pd.DataFrame, ven: pd.DataFrame, pending: int, stopped, double_claimed: int) -> dict:
    wx = ["temp_c", "precip_mm", "wind_kmh", "gust_kmh", "humidity"]
    has_wx = out[wx].notna().all(axis=1)
    per_league = (out.assign(matched=out["af_fixture_id"].notna(), has_loc=out["lat"].notna(), has_wx=has_wx)
                  .groupby("league").agg(rows=("league", "size"), matched=("matched", "mean"),
                                         located=("has_loc", "mean"), with_weather=("has_wx", "mean"),
                                         at_home_venue=("at_home_venue", "mean"))
                  .round(4))

    # far venues: nearest OTHER located venue in the same league (by where the team played at home)
    team_league = (out.dropna(subset=["home_id"]).groupby("home_id")["league"]
                   .agg(lambda s: s.value_counts().index[0]))
    v = ven.assign(league=ven["home_id"].map(team_league)).dropna(subset=["lat"])
    far = []
    for lg, g in v.groupby("league"):
        pts = g[["home_id", "af_team", "venue_name", "venue_city", "geo_name", "geo_admin1", "lat", "lon"]].values
        for i, a in enumerate(pts):
            ds = [_haversine(a[6], a[7], b[6], b[7]) for j, b in enumerate(pts) if j != i]
            if ds and min(ds) > FAR_KM:
                far.append({"league": lg, "team": a[1], "venue": a[2], "af_city": a[3],
                            "geocoded_to": f"{a[4]}, {a[5]}", "lat": a[6], "lon": a[7],
                            "nearest_other_venue_km": round(min(ds), 0)})

    roofed = []
    for _, r in ven.iterrows():
        n = str(r.get("venue_name") or "").lower()
        hit = [h for h in ROOFED_HINTS if h in n]
        if hit:
            roofed.append({"team": r["af_team"], "venue": r["venue_name"], "city": r["venue_city"],
                           "matches": int((out["home_id"] == r["home_id"]).sum())})

    ranges = {c: {"min": float(out[c].min()), "p01": float(out[c].quantile(.01)),
                  "median": float(out[c].median()), "p99": float(out[c].quantile(.99)),
                  "max": float(out[c].max()), "nan_share": round(float(out[c].isna().mean()), 4)}
              for c in wx}
    flags = {c: {"rate": round(float(out[c].mean()), 4), "n_true": int((out[c] == 1).sum())}
             for c in ("heavy_rain", "strong_wind", "hot", "cold")}
    impossible = {
        "temp_outside_-35_50": int(((out["temp_c"] < -35) | (out["temp_c"] > 50)).sum()),
        "precip_negative": int((out["precip_mm"] < 0).sum()),
        "gust_below_wind": int((out["gust_kmh"] < out["wind_kmh"]).sum()),
        "humidity_outside_0_100": int(((out["humidity"] < 0) | (out["humidity"] > 100)).sum()),
    }
    no_geo = ven[~ven["geocode_status"].str.startswith("ok")][["home_id", "af_team", "team_country", "venue_source", "venue_name",
                                                  "venue_city", "geocode_status"]].to_dict("records")
    away_from_home = out[out["at_home_venue"] == 0]
    return {
        "built": str(pd.Timestamp.now("UTC")),
        "window": f"{START} .. {out['date'].max()}",
        "rows": len(out),
        "matched_to_af": int(out["af_fixture_id"].notna().sum()),
        "match_rate": round(float(out["af_fixture_id"].notna().mean()), 4),
        "v9_near_duplicate_rows_same_fixture": double_claimed,
        "home_teams": len(ven),
        "venues_distinct": int(ven["venue_id"].nunique()),
        "coordinates_distinct": int(ven.dropna(subset=["lat"])[["lat", "lon"]].drop_duplicates().shape[0]),
        "geocode_success_rate": round(float(ven["geocode_status"].str.startswith("ok").mean()), 4),
        "geocode_alias_used": int((ven["geocode_status"] == "ok_alias").sum()),
        "venue_source_counts": ven["venue_source"].value_counts().to_dict(),
        "rows_by_venue_source": out["venue_source"].value_counts().to_dict(),
        "cumulative_call_ledger_all_runs": (json.loads((WCACHE / "call_ledger.json").read_text(encoding="utf-8"))
                                            if (WCACHE / "call_ledger.json").exists() else {}),
        "geocode_failures": no_geo,
        "share_rows_with_weather": round(float(has_wx.mean()), 4),
        "share_matched_rows_with_weather": round(float(has_wx[out["af_fixture_id"].notna()].mean()), 4),
        "at_home_venue_share_where_known": round(float(out["at_home_venue"].mean()), 4),
        "rows_not_at_home_venue": int(len(away_from_home)),
        "not_at_home_venue_by_league": away_from_home["league"].value_counts().to_dict(),
        "per_league": per_league.reset_index().to_dict("records"),
        "far_venues_gt_300km_from_nearest_league_venue": far,
        "value_ranges": ranges,
        "flag_rates": flags,
        "impossible_values": impossible,
        "roofed_candidates_treated_as_outdoor": roofed,
        "roof_note": "No special handling: roofed/retractable grounds carry outdoor weather. List is a "
                     "name-based candidate list, not a verdict.",
        "archive_requests_pending": pending,
        "archive_stopped_reason": stopped,
        "calls_this_run": dict(CALLS),
        "caveats": ["location = city centroid of the home team's CURRENT venue (/teams is undated)",
                    "precipitation is preceding-hour sum, so window covers kickoff-1h .. kickoff+2h",
                    "realised weather, not a forecast: look-ahead if used as a pre-match input",
                    "Open-Meteo archive reanalysis grid (~9-25 km), not a stadium station"],
    }


def main(argv):
    audit = build()
    short = {k: audit[k] for k in ("rows", "matched_to_af", "match_rate", "home_teams", "venues_distinct",
                                   "coordinates_distinct", "geocode_success_rate", "share_rows_with_weather",
                                   "at_home_venue_share_where_known", "archive_requests_pending",
                                   "archive_stopped_reason", "calls_this_run")}
    print(json.dumps(short, indent=2, default=str))
    print(f"far venues: {len(audit['far_venues_gt_300km_from_nearest_league_venue'])}; "
          f"roofed candidates: {len(audit['roofed_candidates_treated_as_outdoor'])}; "
          f"geocode failures: {len(audit['geocode_failures'])}")
    print(f"impossible values: {audit['impossible_values']}")


if __name__ == "__main__":
    main(sys.argv[1:])

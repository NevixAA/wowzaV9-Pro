"""Genuine forward two-sided market for the Standard forward shadow, from v9's COMMITTED odds files.

Sources (read-only, a v9 checkout):
  ODDSAPI      output/book_odds_snapshots.csv (+ book_odds_snapshots_archive/<date>.csv once played)
               markets OU25 / BTTS / OU15, sides OVER/UNDER/YES/NO, OddsAPI club names (= the board's).
  APIFOOTBALL  output/book_quotes/<YYYY-MM-DD>.csv: market ou (line 1.5 / 2.5) and btts, sides
               over/under/yes/no, API-Football club names, with periodic `heartbeat` re-observations.
Both files are CHANGE-LOGS, not panels (CLAUDE.md trap 2): a consensus at time t takes, per
(source, bookmaker, side), the LAST quote with snapshot_ts <= t (last observation carried forward),
power-de-vigs each book that has BOTH sides, and takes the median across books.

Price classes:
  GENUINE_FORWARD_TWO_SIDED   >= MIN_BOOKS books quoting both sides at the cut-off.
  NO_GENUINE_PRICE            otherwise. (SYNTHETIC_MARKET_PROXY is reserved for a Poisson proxy;
                              v9 commits no live 1X2, so v1 never builds one and a row without a
                              genuine price is simply not first-sighted.)
Close: the consensus from quotes strictly before kickoff. CERTIFIED_T30 only when >= MIN_BOOKS
two-sided books AND the capture observed this fixture+market within 30 minutes of kickoff (proof
the change-log was alive, so carrying the last price forward is legitimate). Anything else is
UNCERTIFIED and never enters CLV.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.data.entities import split_match
from src.studies.common import match_frames
from src.studies.standard_repair.data import power_devig

MIN_BOOKS = 3
CLOSE_WINDOW_MIN = 30
FIRST_SIDE = {"OU25": ("OVER", "UNDER"), "BTTS": ("YES", "NO"), "OU15": ("OVER", "UNDER")}
COLS = ["source", "book", "ts", "league", "kickoff", "home", "away", "market", "side", "odds"]


def _utc(s) -> pd.Series:
    return pd.to_datetime(s, utc=True, errors="coerce")


def _norm_oddsapi(d: pd.DataFrame) -> pd.DataFrame:
    if d.empty:
        return pd.DataFrame(columns=COLS)
    d = d[d["market"].isin(list(FIRST_SIDE))]
    h, a = split_match(d["match"])
    return pd.DataFrame({"source": "ODDSAPI", "book": "oddsapi:" + d["bookmaker"].astype(str), "ts": _utc(d["snapshot_ts"]),
                         "league": d["league"].astype(str), "kickoff": _utc(d["kickoff_utc"]), "home": h, "away": a,
                         "market": d["market"].astype(str), "side": d["side"].astype(str).str.upper(),
                         "odds": pd.to_numeric(d["odds"], errors="coerce")})


def _norm_af(d: pd.DataFrame) -> pd.DataFrame:
    if d.empty:
        return pd.DataFrame(columns=COLS)
    line = pd.to_numeric(d.get("line"), errors="coerce")
    mk = np.select([(d["market"] == "ou") & (line == 2.5), (d["market"] == "ou") & (line == 1.5), d["market"] == "btts"],
                   ["OU25", "OU15", "BTTS"], default="")
    d = d.assign(_m=mk)
    d = d[d["_m"] != ""]
    return pd.DataFrame({"source": "APIFOOTBALL", "book": "af:" + d["bookmaker"].astype(str), "ts": _utc(d["snapshot_ts"]),
                         "league": d["league"].astype(str), "kickoff": _utc(d["kickoff_utc"]),
                         "home": d["home_team"].astype(str), "away": d["away_team"].astype(str), "market": d["_m"],
                         "side": d["side"].astype(str).str.upper(), "odds": pd.to_numeric(d["odds"], errors="coerce")})


def _read(p: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[""])
    except Exception as e:                                                 # noqa: BLE001
        raise RuntimeError(f"cannot read v9 odds file {p}: {e}") from e


def load_quotes(v9_root, leagues, day_from, day_to, archive: bool = False) -> pd.DataFrame:
    """All quotes of the given leagues whose snapshot day (API-Football files) / match day (OddsAPI
    archive parts) lies in [day_from, day_to]; the OddsAPI live file is always read."""
    root = Path(v9_root) / "output"
    days = {d.strftime("%Y-%m-%d") for d in pd.date_range(pd.Timestamp(day_from).normalize(), pd.Timestamp(day_to).normalize())}
    frames = []
    live = root / "book_odds_snapshots.csv"
    if not live.exists():
        raise RuntimeError("v9 output/book_odds_snapshots.csv missing - the market source is unavailable")
    frames.append(_norm_oddsapi(_read(live)))
    if archive:
        adir = root / "book_odds_snapshots_archive"
        for p in sorted(adir.glob("*.csv")) if adir.exists() else []:
            if p.stem in days:
                frames.append(_norm_oddsapi(_read(p)))
    bq = root / "book_quotes"
    for p in sorted(bq.glob("*.csv")) if bq.exists() else []:
        if p.stem in days:
            frames.append(_norm_af(_read(p)))
    q = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else pd.DataFrame(columns=COLS)
    q = q[q["league"].isin(set(leagues)) & q["odds"].gt(1.0) & q["ts"].notna()]
    return q.drop_duplicates(["book", "ts", "home", "away", "market", "side"]).reset_index(drop=True)


def attach_fixtures(q: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    """Give every quote the `row_key` of its board fixture (league + date +-1 day + token club
    match on both teams, ambiguous -> unmatched). `fixtures`: row_key, league, kickoff_utc, home_team,
    away_team (board / OddsAPI spelling)."""
    if q.empty or fixtures.empty:
        return q.assign(row_key=pd.Series(dtype=object))
    sf = q.drop_duplicates(["source", "league", "home", "away", "kickoff"])[["source", "league", "home", "away", "kickoff"]]
    sf = sf.assign(match_date=sf["kickoff"].dt.strftime("%Y-%m-%d")).reset_index(drop=True)
    fx = fixtures.assign(match_date=_utc(fixtures["kickoff_utc"]).dt.strftime("%Y-%m-%d")).reset_index(drop=True)
    hit = match_frames(sf, fx, l_cols=("league", "match_date", "home", "away"),
                       r_cols=("league", "match_date", "home_team", "away_team"))
    sf["row_key"] = [fx.at[int(i), "row_key"] if pd.notna(i) else None for i in hit]
    return q.merge(sf[["source", "league", "home", "away", "kickoff", "row_key"]],
                   on=["source", "league", "home", "away", "kickoff"], how="left")


def consensus(q: pd.DataFrame, market: str, cutoff) -> dict:
    """Consensus of one fixture+market from quotes with ts <= cutoff (LOCF per book and side)."""
    first, other = FIRST_SIDE[market]
    empty = {"p_market": np.nan, "n_books": 0, "odds_first_median": np.nan, "odds_other_median": np.nan,
             "odds_first_best": np.nan, "odds_other_best": np.nan, "price_ts": None, "books": "", "sources": "",
             "market_class": "NO_GENUINE_PRICE", "price_is_real": False}
    c = q[q["ts"] <= pd.Timestamp(cutoff)]
    if c.empty:
        return empty
    last = c.sort_values("ts", kind="mergesort").drop_duplicates(["book", "side"], keep="last")
    w = last.set_index(["book", "side"])["odds"].astype(float).unstack()
    ts = last.set_index(["book", "side"])["ts"].unstack()
    if first not in w or other not in w:
        return empty
    w = w.dropna(subset=[first, other])
    if w.empty:
        return empty
    p = pd.Series(power_devig(w[first].to_numpy(), w[other].to_numpy()), index=w.index).dropna()
    if p.empty:
        return empty
    w = w.loc[p.index]
    real = len(p) >= MIN_BOOKS
    used_ts = pd.concat([ts.loc[p.index, first], ts.loc[p.index, other]])
    return {"p_market": float(np.median(p)), "n_books": int(len(p)),
            "odds_first_median": float(w[first].median()), "odds_other_median": float(w[other].median()),
            "odds_first_best": float(w[first].max()), "odds_other_best": float(w[other].max()),
            "price_ts": pd.Timestamp(used_ts.max()).isoformat(), "books": ";".join(sorted(p.index)),
            "sources": ";".join(sorted({b.split(":", 1)[0] for b in p.index})),
            "market_class": "GENUINE_FORWARD_TWO_SIDED" if real else "NO_GENUINE_PRICE", "price_is_real": bool(real)}


def closing(q: pd.DataFrame, market: str, kickoff) -> dict:
    ko = pd.Timestamp(kickoff)
    pre = q[q["ts"] < ko]
    c = consensus(pre, market, ko - pd.Timedelta(microseconds=1))
    last_obs = pre["ts"].max() if not pre.empty else pd.NaT
    mins = (ko - last_obs).total_seconds() / 60 if pd.notna(last_obs) else np.nan
    if c["n_books"] == 0:
        status = "NO_CLOSE"
    elif c["price_is_real"] and np.isfinite(mins) and mins <= CLOSE_WINDOW_MIN:
        status = "CERTIFIED_T30"
    else:
        status = "UNCERTIFIED_STALE" if c["price_is_real"] else "UNCERTIFIED_THIN"
    return {"p_close": c["p_market"], "n_books_close": c["n_books"], "close_odds_first": c["odds_first_median"],
            "close_odds_other": c["odds_other_median"], "close_last_obs_min_before_ko": None if not np.isfinite(mins) else round(mins, 1),
            "close_status": status}

"""Prospective FIRST-SIGHT design: the served Standard model vs the market at the moment Pro first saw it.

For every Standard fixture and market (OU25 / BTTS / OU15):
  * first-sight row  = the EARLIEST model_snapshots row observed before kickoff (what v9 served first;
                       never revised with later information),
  * market at first sight = per-book quotes with snapshot_ts <= that observation, last-observation-
                       carried-forward PER BOOK AND SIDE (the snapshot tables are change-logs, not
                       panels - CLAUDE.md trap 2), each book power-de-vigged two-sided, median across
                       books,
  * close            = the same consensus from the last pre-kickoff quote per book (EVALUATION ONLY:
                       CLV and closing accuracy; never an entry),
  * outcome          = football-data results (fd_raw current season), joined by league, date +-1 day
                       and the token club matcher, refusing ambiguous matches.
This is the design any registration in registry/standard_repair/ is evaluated on. Reads Pro's store
only; writes output/standard_repair/forward_first_sight.csv.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.data import season_store as store
from src.studies import common
from src.studies.standard_repair.data import FD_CODES, FD_RAW, power_devig

OUT = cfg.OUTPUT_DIR / "standard_repair"
FIRST_SIDE = {"OU25": ("OVER", "UNDER"), "BTTS": ("YES", "NO"), "OU15": ("OVER", "UNDER")}


def _ts(s):
    return pd.to_datetime(s, utc=True, errors="coerce")


def _consensus(q: pd.DataFrame, first: str, other: str):
    """q: one fixture's quotes already cut at the cutoff. LOCF per (book, side) -> per-book power de-vig."""
    if q.empty:
        return np.nan, 0, np.nan, np.nan
    last = q.sort_values("ts").drop_duplicates(["bookmaker", "side"], keep="last")
    w = last.pivot_table(index="bookmaker", columns="side", values="odds", aggfunc="last")
    if first not in w or other not in w:
        return np.nan, 0, np.nan, np.nan
    w = w.dropna(subset=[first, other])
    if w.empty:
        return np.nan, 0, np.nan, np.nan
    p = power_devig(w[first].to_numpy(), w[other].to_numpy())
    p = p[np.isfinite(p)]
    if not len(p):
        return np.nan, 0, np.nan, np.nan
    return float(np.median(p)), int(len(p)), float(w[first].median()), float(w[other].median())


def _results() -> pd.DataFrame:
    rows = []
    for league, code in FD_CODES.items():
        for f in sorted(FD_RAW.glob(f"{code}_2627.csv")):
            d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False).dropna(subset=["HomeTeam", "AwayTeam", "FTHG"])
            rows.append(pd.DataFrame({"league": league, "match_date": pd.to_datetime(d["Date"], dayfirst=True).dt.strftime("%Y-%m-%d"),
                                      "home_team": d["HomeTeam"], "away_team": d["AwayTeam"],
                                      "hg": d["FTHG"].astype(float), "ag": d["FTAG"].astype(float)}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def build() -> pd.DataFrame:
    ms = store.read("model_snapshots")
    ms = ms[(ms["model_type"] == "standard") & ms["market"].isin(list(FIRST_SIDE))].copy()
    fx = store.read("fixtures").sort_values("observed_at").drop_duplicates("fixture_key", keep="last")
    fx = fx[["fixture_key", "kickoff_utc", "home_team", "away_team"]]
    ms = ms.merge(fx, on="fixture_key", how="inner")
    ms["ts"], ms["ko"] = _ts(ms["observed_at"]), _ts(ms["kickoff_utc"])
    ms = ms[ms["ts"] < ms["ko"]].sort_values("ts")
    first = ms.drop_duplicates(["fixture_key", "market"], keep="first")
    bo = store.read("book_odds_snapshots")
    bo = bo[bo["market"].isin(list(FIRST_SIDE)) & ~bo["is_post_kickoff"].astype(bool)].copy()
    bo["ts"] = _ts(bo["snapshot_ts"])
    bo = bo[bo["fixture_key"].isin(first["fixture_key"])]
    groups = {k: g for k, g in bo.groupby(["fixture_key", "market"])}
    out = []
    for r in first.itertuples(index=False):
        f, o = FIRST_SIDE[r.market]
        q = groups.get((r.fixture_key, r.market), pd.DataFrame(columns=["ts", "bookmaker", "side", "odds"]))
        pm, nb, of, oo = _consensus(q[q["ts"] <= r.ts], f, o)
        pc, nbc, cf, co = _consensus(q[q["ts"] < r.ko], f, o)
        out.append({"fixture_key": r.fixture_key, "league": r.league, "match_date": str(r.match_date)[:10],
                    "home_team": r.home_team, "away_team": r.away_team, "market": r.market,
                    "first_seen_at": r.ts.isoformat(), "kickoff_utc": r.ko.isoformat(),
                    "p_model": float(r.model_prob), "model_content_sha": getattr(r, "model_content_sha", None),
                    "p_market": pm, "n_books": nb, "odds_first": of, "odds_other": oo,
                    "p_close": pc, "n_books_close": nbc, "close_first": cf, "close_other": co})
    d = pd.DataFrame(out)
    if d.empty:
        return d
    res = _results()
    if not res.empty:
        fxr = d.drop_duplicates("fixture_key")[["fixture_key", "league", "match_date", "home_team", "away_team"]].reset_index(drop=True)
        hit = common.match_frames(fxr, res)
        fxr["hg"] = [res.at[int(i), "hg"] if pd.notna(i) else np.nan for i in hit]
        fxr["ag"] = [res.at[int(i), "ag"] if pd.notna(i) else np.nan for i in hit]
        d = d.merge(fxr[["fixture_key", "hg", "ag"]], on="fixture_key", how="left")
        t = d["hg"] + d["ag"]
        d["y"] = np.where(d["market"] == "OU25", t > 2.5, np.where(d["market"] == "OU15", t > 1.5, (d["hg"] > 0) & (d["ag"] > 0))).astype(float)
        d.loc[t.isna(), "y"] = np.nan
    else:
        d["y"] = np.nan
    d["week"] = pd.to_datetime(d["match_date"]).dt.strftime("%G-W%V")
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "forward_first_sight.csv", index=False)
    return d


def load() -> pd.DataFrame:
    p = OUT / "forward_first_sight.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

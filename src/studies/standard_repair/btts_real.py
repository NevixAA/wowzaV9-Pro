"""GENUINE two-sided BTTS prices for the Standard benchmark (owner follow-up 2026-10-28).

Source: v9 `output/standard_sidemarket_odds_history.csv` (snapshot_date, snapshot_ts, match_date,
kickoff_utc, league, match, market, odds).
  * HISTORICAL BACKFILL (OddsAPI historical, run 2026-07-01): btts_yes AND btts_no for ~4.6k matches in
    the 7 bet leagues, 2024-08 .. 2026-05, every snapshot stamped 00:00Z on match day.
    Timing class PREMATCH_SNAPSHOT_00Z - a genuine pre-match quote taken the morning of the match,
    NOT a closing price and NOT a fill.
  * FORWARD CAPTURE (Aug 2026 ->): timestamped snapshots. The first-half BTTS mislabel (YES > 3.20) is
    removed on read and only rows from TRUSTED_FROM (v9 8d9962c6, 2026-08-23) are used. For each side
    the EARLIEST pre-kickoff quote is the entry: timing class FORWARD_EARLIEST_PREKO.
  * Over 1.5 / Over 3.5 were NOT backfilled historically (1 and 18 rows), so those markets stay
    SYNTHETIC_MARKET_PROXY historically.

Matching: OddsAPI names -> the benchmark's canonical names with v9's own `src/team_names.resolve`
(league-scoped, refuses ambiguity), loaded from the v9 checkout without importing v9's package, after
applying Pro's identity alias map. Exact match date first, then +-1 day when unique. Every capture match
is reported as matched or unmatched (sample kept).
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.standard_repair import prices as PR
from src.studies.standard_repair.data import power_devig

TRUSTED_FROM_FORWARD = "2026-08-23T08:26:13Z"
HIST_CLASS = "PREMATCH_SNAPSHOT_00Z"
FWD_CLASS = "FORWARD_EARLIEST_PREKO"
REAL_CLASS = "GENUINE_TWO_SIDED"
SYN_CLASS = "SYNTHETIC_MARKET_PROXY"


def _v9_root() -> Path:
    return Path(os.getenv("V9_LOCAL") or cfg.V9_LOCAL)


def team_resolver():
    """v9's src/team_names.resolve, loaded by file path (stdlib-only module)."""
    p = _v9_root() / "src" / "team_names.py"
    spec = importlib.util.spec_from_file_location("_v9_team_names", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.resolve


def load_quotes(path: Path | None = None) -> tuple[pd.DataFrame, dict]:
    """One row per capture match (league, match_date, home, away) with the two-sided entry quote."""
    p = Path(path) if path else _v9_root() / "output" / "standard_sidemarket_odds_history.csv"
    o = pd.read_csv(p, low_memory=False)
    o = o[o["market"].isin(["btts_yes", "btts_no"])].copy()
    kept, removed = PR.contamination_filter_btts(o, "market", None, "odds")
    o = kept
    o["odds"] = pd.to_numeric(o["odds"], errors="coerce")
    o["ts"] = pd.to_datetime(o["snapshot_ts"], utc=True, errors="coerce")
    o["is_hist"] = o["snapshot_ts"].astype(str).str[11:19].eq("00:00:00")
    ko = pd.to_datetime(o.get("kickoff_utc"), utc=True, errors="coerce")
    fwd = ~o["is_hist"]
    o = o[o["is_hist"] | (fwd & (o["ts"] >= pd.Timestamp(TRUSTED_FROM_FORWARD)) & (ko.isna() | (o["ts"] < ko)))]
    o = o.sort_values("ts").drop_duplicates(["league", "match_date", "match", "market"], keep="first")
    w = o.pivot_table(index=["league", "match_date", "match"], columns="market", values="odds", aggfunc="first").reset_index()
    cls = o.groupby(["league", "match_date", "match"])["is_hist"].all().rename("is_hist").reset_index()
    tsx = o.groupby(["league", "match_date", "match"])["ts"].max().rename("quote_ts").reset_index()
    w = w.merge(cls, on=["league", "match_date", "match"]).merge(tsx, on=["league", "match_date", "match"])
    w = w.dropna(subset=["btts_yes", "btts_no"])
    parts = w["match"].astype(str).str.split(" vs ", n=1, expand=True)
    w["home_raw"], w["away_raw"] = parts[0].str.strip(), parts[1].str.strip()
    w["date"] = pd.to_datetime(w["match_date"].astype(str).str[:10], errors="coerce").dt.normalize()
    w["price_class"] = np.where(w["is_hist"], HIST_CLASS, FWD_CLASS)
    meta = {"btts_1h_rows_removed": int(len(removed)), "two_sided_matches": int(len(w)),
            "by_class": w["price_class"].value_counts().to_dict()}
    return w, meta


def attach(std: pd.DataFrame, amap: dict, quotes: pd.DataFrame | None = None, resolve=None) -> tuple[pd.DataFrame, dict]:
    """Return std's key columns + real BTTS columns, and a match report."""
    if quotes is None:
        quotes, meta = load_quotes()
    else:
        meta = {}
    resolve = resolve or team_resolver()
    k = ["league", "date", "home_team", "away_team"]
    s = std[k].copy()
    s["date"] = pd.to_datetime(s["date"]).dt.normalize()
    names = {lg: sorted(set(g["home_team"].astype(str)) | set(g["away_team"].astype(str))) for lg, g in s.groupby("league")}
    idx = {key: i for i, key in enumerate(zip(s["league"], s["date"], s["home_team"].astype(str), s["away_team"].astype(str)))}
    memo: dict = {}

    def res(lg, nm):
        nm2 = amap.get(lg, {}).get(nm, nm)
        key = (lg, nm2)
        if key not in memo:
            cands = names.get(lg, [])
            memo[key] = nm2 if nm2 in cands else resolve(nm2, cands)
        return memo[key]
    out = {c: np.full(len(s), np.nan) for c in ("btts_yes_odds", "btts_no_odds")}
    pcls = np.full(len(s), None, dtype=object)
    qts = np.full(len(s), None, dtype=object)
    matched, unmatched = [], []
    q = quotes[quotes["league"].isin(names)]
    for r in q.itertuples(index=False):
        h, a = res(r.league, r.home_raw), res(r.league, r.away_raw)
        hit = None
        if h and a:
            for dd in (0, -1, 1):
                i = idx.get((r.league, r.date + pd.Timedelta(days=dd), h, a))
                if i is not None:
                    hit = i
                    break
        if hit is None:
            unmatched.append({"league": r.league, "match_date": str(r.match_date)[:10], "match": r.match,
                              "resolved_home": h, "resolved_away": a})
            continue
        if not np.isnan(out["btts_yes_odds"][hit]):
            continue                                                        # first quote per fixture wins
        out["btts_yes_odds"][hit], out["btts_no_odds"][hit] = r.btts_yes, r.btts_no
        pcls[hit], qts[hit] = r.price_class, str(r.quote_ts)
        matched.append(r.league)
    s["btts_yes_odds"], s["btts_no_odds"] = out["btts_yes_odds"], out["btts_no_odds"]
    s["btts_price_class"], s["btts_quote_ts"] = pcls, qts
    s["pm_BTTS_REAL"] = power_devig(s["btts_yes_odds"], s["btts_no_odds"])
    s["market_class_BTTS_REAL"] = np.where(s["pm_BTTS_REAL"].notna(), REAL_CLASS, None)
    tot = q.groupby("league").size()
    mt = pd.Series(matched).value_counts() if matched else pd.Series(dtype=int)
    report = {**meta, "capture_matches_in_benchmark_leagues": int(len(q)), "matched": int(len(matched)),
              "match_rate": round(len(matched) / max(len(q), 1), 4),
              "by_league": {lg: {"capture": int(n), "matched": int(mt.get(lg, 0)),
                                 "rate": round(float(mt.get(lg, 0)) / n, 4)} for lg, n in tot.items()},
              "by_class_matched": pd.Series(pcls[pd.notna(pcls)]).value_counts().to_dict(),
              "unmatched_sample": unmatched[:40], "unmatched_total": len(unmatched),
              "devig": "power, two-sided, same snapshot; overround outside [1.00, 1.25] rejected"}
    return s, report

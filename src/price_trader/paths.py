"""Canonical trades + price paths, built only from prices that existed at each timestamp.

SOURCE: v9 output/book_odds_snapshots.csv (per-book quotes, both sides, OU15/OU25/OU35/BTTS, since
2026-08-19). It is a CHANGE-LOG - a snapshot lists only the books whose price moved - so every
(book, side) price is CARRIED FORWARD before any best/median is taken (CLAUDE.md trap 2).
BOOKS vs EXCHANGES: matchbook and betfair_ex_* are exchanges (back prices only in this feed; no lay
ladder, no volume). Bookmaker best price = max over non-exchange books.

TRADES: every Wowza tip (v9 ledgers, live source, paper leagues out) from 2026-08-19, one per
fixture x market x side at its FIRST signal time (generated_at, UTC). ENTRY = the latest snapshot at
or before the signal (as-of; never a later price). No snapshot before the signal -> NO_ENTRY_PRICE.
The eventual result is stored but never used by the price-trading P/L.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import pro_config as cfg

EXCHANGES = ("matchbook", "betfair_ex_uk", "betfair_ex_eu", "betfair_ex_au", "smarkets")
OPP = {"OVER": "UNDER", "UNDER": "OVER", "YES": "NO", "NO": "YES"}
SIDE_MKT = {"btts": ("BTTS", "YES"), "over15": ("OU15", "OVER"), "over35": ("OU35", "OVER")}
PAPER = {"USA MLS"}


def load_snapshots() -> pd.DataFrame:
    # v9's file is ROLLING since 2026-10-22: played matches live in book_odds_snapshots_archive/.
    from src.data.v9_source import read_v9_all
    d = read_v9_all("output/book_odds_snapshots.csv", low_memory=False)
    d["ts"] = pd.to_datetime(d["snapshot_ts"], utc=True, errors="coerce")
    d["ko"] = pd.to_datetime(d["kickoff_utc"], utc=True, errors="coerce")
    d["side"] = d["side"].astype(str).str.upper()
    d["odds"] = pd.to_numeric(d["odds"], errors="coerce")
    d = d[(d["odds"] > 1.0) & d["ts"].notna()]
    d["exchange"] = d["bookmaker"].astype(str).str.lower().isin(EXCHANGES)
    return d.sort_values("ts", kind="mergesort")


def load_trades() -> pd.DataFrame:
    out = cfg.V9_LOCAL / "output"
    m = pd.read_csv(out / "bets_ledger.csv", low_memory=False)
    m = m.assign(market="OU25", side=m["side"].astype(str).str.upper())
    s = pd.read_csv(out / "side_bets_ledger.csv", low_memory=False)
    s = s.assign(market=s["market"].map(lambda k: SIDE_MKT.get(k, (None, None))[0]),
                 side=s["market"].map(lambda k: SIDE_MKT.get(k, (None, None))[1]))
    cols = ["source", "generated_at", "match_date", "league", "home_team", "away_team", "model_type",
            "signal_tier", "odds", "edge_pct", "result", "market", "side"]
    t = pd.concat([m.reindex(columns=cols), s.reindex(columns=cols)], ignore_index=True)
    t = t[t["source"].fillna("live").astype(str).eq("live") & ~t["league"].isin(PAPER) & t["market"].notna()]
    t["signal_ts"] = pd.to_datetime(t["generated_at"], utc=True, errors="coerce")
    t["match"] = t["home_team"].astype(str) + " vs " + t["away_team"].astype(str)
    t["match_date"] = t["match_date"].astype(str).str[:10]
    t = t[t["match_date"] >= "2026-08-19"].dropna(subset=["signal_ts"])
    t = t.sort_values("signal_ts").drop_duplicates(["match_date", "match", "market", "side"], keep="first")
    t["trade_id"] = t["match_date"] + "|" + t["match"] + "|" + t["market"] + "|" + t["side"]
    return t.reset_index(drop=True)


def path_for(snaps: pd.DataFrame) -> pd.DataFrame:
    """Carry-forward per (book, side) -> one row per snapshot time with best/median prices."""
    last: dict = {}
    rows = []
    for ts, g in snaps.groupby("ts", sort=True):
        for r in g.itertuples(index=False):
            last[(r.bookmaker, r.side, r.exchange)] = r.odds
        rows.append((ts, dict(last)))
    return rows


def summarise(state: dict, side: str) -> dict:
    opp = OPP[side]
    bk_s = [o for (b, s, ex), o in state.items() if s == side and not ex]
    bk_o = [o for (b, s, ex), o in state.items() if s == opp and not ex]
    ex_s = [o for (b, s, ex), o in state.items() if s == side and ex]
    ex_o = [o for (b, s, ex), o in state.items() if s == opp and ex]
    both = [(state[(b, side, ex)], state[(b, opp, ex)]) for (b, s, ex) in state
            if s == side and not ex and (b, opp, ex) in state]
    fair = [(1 / a) / (1 / a + 1 / b) for a, b in both]
    return {"best_back": max(bk_s) if bk_s else np.nan, "best_opposite": max(bk_o) if bk_o else np.nan,
            "median_back": float(np.median(bk_s)) if bk_s else np.nan,
            "exch_back": max(ex_s) if ex_s else np.nan, "exch_opposite": max(ex_o) if ex_o else np.nan,
            "book_count": len(bk_s), "consensus_probability": float(np.median(fair)) if fair else np.nan}


def build(trades: pd.DataFrame | None = None, snaps: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades = load_trades() if trades is None else trades
    snaps = load_snapshots() if snaps is None else snaps
    key = snaps["match_date"].astype(str) + "|" + snaps["match"].astype(str) + "|" + snaps["market"].astype(str)
    groups = {k: g for k, g in snaps.groupby(key, sort=False)}
    paths, trows = [], []
    for t in trades.itertuples(index=False):
        g = groups.get(f"{t.match_date}|{t.match}|{t.market}")
        rec = t._asdict()
        if g is None or g.empty:
            trows.append({**rec, "status": "NO_PRICE_DATA"})
            continue
        ko = g["ko"].dropna().iloc[0] if g["ko"].notna().any() else pd.NaT
        rows = path_for(g)
        entry_i = max((i for i, (ts, _) in enumerate(rows) if ts <= t.signal_ts), default=None)
        if entry_i is None:
            trows.append({**rec, "kickoff": ko, "status": "NO_ENTRY_PRICE"})
            continue
        e = summarise(rows[entry_i][1], t.side)
        if not (e["best_back"] > 1):
            trows.append({**rec, "kickoff": ko, "status": "NO_ENTRY_PRICE"})
            continue
        trows.append({**rec, "kickoff": ko, "status": "OK", "entry_ts": rows[entry_i][0],
                      "entry_time_to_kickoff_h": (ko - t.signal_ts).total_seconds() / 3600 if pd.notna(ko) else np.nan,
                      "entry_back_odds": e["best_back"], "entry_exchange_back": e["exch_back"],
                      "entry_opposite_odds": e["best_opposite"], "entry_book_count": e["book_count"],
                      "market_consensus_probability": e["consensus_probability"],
                      "eventual_result": t.result})
        for ts, st in rows[entry_i:]:
            if pd.notna(ko) and ts >= ko:
                break
            s = summarise(st, t.side)
            paths.append({"trade_id": t.trade_id, "timestamp": ts,
                          "minutes_to_kickoff": (ko - ts).total_seconds() / 60 if pd.notna(ko) else np.nan,
                          **s, "spread_pct": (1 / s["best_back"] + 1 / s["best_opposite"] - 1) if s["best_opposite"] > 1 and s["best_back"] > 1 else np.nan})
    T, P = pd.DataFrame(trows), pd.DataFrame(paths)
    if len(P):
        p0 = P.groupby("trade_id")["consensus_probability"].transform("first")
        P["signed_move_pp"] = 100 * (P["consensus_probability"] - p0)
        P["movement_toward_wowza"] = P["signed_move_pp"] > 0
    return T, P

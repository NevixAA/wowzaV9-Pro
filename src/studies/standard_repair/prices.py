"""PRICE AUDIT for the Standard benchmark (owner brief 2026-10-28, P0 #5 and "price certification").

Every price that can reach a Standard result is labelled with three fields:

    price_is_real              a quote a bookmaker actually offered (False for any fill / constant)
    price_source               where it came from (FD_AVG, FD_B365, FD_AVG_CLOSE, V9_CAPTURE, PRO_BOOK_SNAPSHOT,
                               BACKTEST_ARCHIVE, FALLBACK_CONSTANT, ...)
    price_timestamp_or_class   FD_PREMATCH_APPROX   football-data non-closing column (recorded Fri/Tue before KO)
                               FD_CLOSING           any football-data column with the "C" infix
                               ARCHIVE_UNKNOWN      v9's backtest archive: price copied from an older frame,
                                                    timing not recorded (and v9's frame prefers closing)
                               CAPTURE_LAST         v9 forward capture, last snapshot (near close)
                               BACKFILL_DATE_ONLY   v9 side-market backfill, stamped at midnight of match day
                               <ISO timestamp>      a forward snapshot with its own capture time

ENTRY vs CLOSE are separate fields and never substitute for each other: the entry (selection, EV,
ROI) is FD_PREMATCH_APPROX historically and the first-sight snapshot forward; the close is used only
for CLV, closing calibration and movement. No *C* column ever becomes an entry.

FALLBACK CONSTANTS. v9's backtest fills a missing side-market price with BTTS 1.85 / O1.5 1.40 /
O3.5 2.60 (src/backtest.py _DEFAULT_ODDS) and v9's market_edge flags them `price_synthetic`. A
constant-filled price is never real: it is excluded from every certified ROI/EV/CLV here, and counted.

1H-BTTS CONTAMINATION. Until v9 commit 8d9962c6 (2026-08-23) the capture parser stored the
FIRST-HALF BTTS price as full-match BTTS. The two populations do not overlap (full-match YES 1.34-2.97,
first-half 3.40-7.00), so YES > 3.20 is removed on READ — before any model comparison, baseline, ROI,
CLV or threshold work — and counted. Raw captures are never rewritten.

CERTIFIED T30 CLOSE (forward). A fixture x market has a certified close when a capture run observed it
between 0 and 30 minutes before kickoff and, carrying every book's last quote forward to that run
(the snapshot tables are change-logs, CLAUDE.md trap 2), at least MIN_BOOKS books are two-sided.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import pro_config as cfg

FALLBACK_CONSTANTS = {"BTTS": 1.85, "OU15": 1.40, "OU35": 2.60}
BTTS_YES_1H_MAX = 3.20
MIN_BOOKS = 3
T30 = 30.0
FRAME_SIDE_COLS = {"BTTS": "odds_btts", "OU15": "odds_over15", "OU35": "odds_over35"}
CAPTURE_MARKETS = {"btts_yes": ("BTTS", "YES"), "btts_no": ("BTTS", "NO"), "over15": ("OU15", "OVER"),
                   "under15": ("OU15", "UNDER"), "over25": ("OU25", "OVER"), "under25": ("OU25", "UNDER"),
                   "over35": ("OU35", "OVER"), "under35": ("OU35", "UNDER")}


def contamination_filter_btts(df: pd.DataFrame, market_col: str, side_col: str | None,
                              odds_col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split rows into (kept, removed): a BTTS-YES quote above 3.20 is a first-half price.
    side_col=None: v9 capture layout (market 'btts_yes'); else Pro layout (market 'BTTS', side 'YES')."""
    m = df[market_col].astype(str)
    is_yes = m.eq("btts_yes") if side_col is None else (m.eq("BTTS") & df[side_col].astype(str).eq("YES"))
    bad = is_yes & (pd.to_numeric(df[odds_col], errors="coerce") > BTTS_YES_1H_MAX)
    return df[~bad], df[bad]


def is_fallback(market: str, odds) -> np.ndarray:
    c = FALLBACK_CONSTANTS.get(market)
    o = pd.to_numeric(pd.Series(odds), errors="coerce").to_numpy()
    return np.zeros(len(o), bool) if c is None else np.isclose(o, c, atol=1e-9)


# ── historical OU25: football-data pre-match vs closing ─────────────────────────────────────────
def fd_ou25_rows(fd_raw_dir, fd_codes: dict) -> pd.DataFrame:
    """Every football-data OU2.5 quote pair in the raw files, entry and close as separate fields."""
    rows = []
    for league, code in fd_codes.items():
        for f in sorted(fd_raw_dir.glob(f"{code}_*.csv")):
            try:
                d = pd.read_csv(f, encoding="utf-8-sig", low_memory=False)
            except UnicodeDecodeError:
                d = pd.read_csv(f, encoding="latin-1", low_memory=False)
            if not {"Date", "HomeTeam", "AwayTeam"} <= set(d.columns):
                continue
            d = d.dropna(subset=["HomeTeam", "AwayTeam"])
            r = pd.DataFrame({"league": league, "file": f.name,
                              "date": pd.to_datetime(d["Date"], dayfirst=True, errors="coerce").dt.normalize(),
                              "home_team": d["HomeTeam"].astype(str).str.strip(),
                              "away_team": d["AwayTeam"].astype(str).str.strip()})
            for nm, (o, u) in {"AVG": ("Avg>2.5", "Avg<2.5"), "B365": ("B365>2.5", "B365<2.5"),
                               "PIN": ("P>2.5", "P<2.5"), "BFE": ("BFE>2.5", "BFE<2.5"),
                               "AVGC": ("AvgC>2.5", "AvgC<2.5"), "B365C": ("B365C>2.5", "B365C<2.5"),
                               "PINC": ("PC>2.5", "PC<2.5"), "MAXC": ("MaxC>2.5", "MaxC<2.5")}.items():
                r[f"o_{nm}"] = pd.to_numeric(d.get(o), errors="coerce")
                r[f"u_{nm}"] = pd.to_numeric(d.get(u), errors="coerce")
            rows.append(r)
    return pd.concat(rows, ignore_index=True).dropna(subset=["date"]) if rows else pd.DataFrame()


def label_frame_ou25(std: pd.DataFrame, fd: pd.DataFrame, amap: dict | None = None) -> pd.DataFrame:
    """Per standard frame row: the price v9 trained on (odds_over25) classified, plus the separate
    entry (FD pre-match) and close (FD closing) fields."""
    s = std[["league", "date", "home_team", "away_team", "row_source", "odds_over25", "odds_under25",
             "_ou25_src"]].copy()
    s["date"] = pd.to_datetime(s["date"]).dt.normalize()
    f = fd.copy()
    if amap:
        for c in ("home_team", "away_team"):
            f[c] = [amap.get(lg, {}).get(t, t) for lg, t in zip(f["league"], f[c])]
    f = f.drop_duplicates(["league", "date", "home_team", "away_team"])
    s = s.merge(f.drop(columns=["file"]), on=["league", "date", "home_team", "away_team"], how="left")
    s["fd_matched"] = s["o_AVGC"].notna() | s["o_AVG"].notna() | s["o_B365"].notna()
    # entry: average pre-match, else Bet365 pre-match. Never a closing column.
    s["entry_over25"] = s["o_AVG"].fillna(s["o_B365"])
    s["entry_under25"] = s["u_AVG"].where(s["o_AVG"].notna(), s["u_B365"])
    s["entry_source"] = np.where(s["o_AVG"].notna(), "FD_AVG", np.where(s["o_B365"].notna(), "FD_B365", None))
    s["entry_class"] = np.where(s["entry_over25"].notna(), "FD_PREMATCH_APPROX", None)
    s["close_over25"] = s["o_AVGC"]
    s["close_under25"] = s["u_AVGC"]
    s["close_class"] = np.where(s["close_over25"].notna(), "FD_CLOSING", None)
    # what v9's frame actually carries
    tol = 1e-9
    eq_close = (np.isclose(s["odds_over25"], s["o_AVGC"], atol=tol) | np.isclose(s["odds_over25"], s["o_MAXC"], atol=tol)
                | np.isclose(s["odds_over25"], s["o_B365C"], atol=tol) | np.isclose(s["odds_over25"], s["o_PINC"], atol=tol))
    eq_pre = np.isclose(s["odds_over25"], s["o_AVG"], atol=tol) | np.isclose(s["odds_over25"], s["o_B365"], atol=tol)
    src = s["_ou25_src"].astype("string").fillna("NONE")
    s["frame_price_class"] = np.select(
        [s["odds_over25"].isna(), src.eq("V9_OU25_CAPTURE_LAST"), eq_close & ~eq_pre, eq_pre & ~eq_close,
         eq_close & eq_pre, src.eq("BACKTEST_ARCHIVE")],
        ["NO_PRICE", "CAPTURE_LAST", "FD_CLOSING", "FD_PREMATCH_APPROX", "FD_CLOSING_EQ_PREMATCH",
         "ARCHIVE_UNKNOWN"], "UNVERIFIED")
    s["frame_price_is_real"] = s["odds_over25"].notna()
    s["frame_price_usable_as_entry"] = s["frame_price_class"].isin(["FD_PREMATCH_APPROX"])
    return s


# ── forward snapshots (Pro store) ───────────────────────────────────────────────────────────────
def forward_coverage(bo: pd.DataFrame, leagues: set, min_books: int = MIN_BOOKS) -> tuple[pd.DataFrame, dict]:
    """Per league x market: fixtures, two-sided, >= min_books, certified T30 close; 1H-BTTS removed."""
    b = bo[bo["league"].isin(leagues)].copy()
    kept, removed = contamination_filter_btts(b, "market", "side", "odds")
    removed_by_league = removed.groupby("league").size().to_dict()
    b = kept[~kept["is_post_kickoff"].astype(bool)].copy()
    b["ts"] = pd.to_datetime(b["snapshot_ts"], utc=True, errors="coerce")
    b["mtk"] = pd.to_numeric(b["minutes_to_kickoff"], errors="coerce")
    b["odds"] = pd.to_numeric(b["odds"], errors="coerce")
    first_side = {"OU25": ("OVER", "UNDER"), "BTTS": ("YES", "NO"), "OU15": ("OVER", "UNDER"), "OU35": ("OVER", "UNDER")}
    out = []
    for (lg, mk, fk), g in b.groupby(["league", "market", "fixture_key"], sort=False):
        f1, f2 = first_side.get(mk, ("OVER", "UNDER"))
        last = g.sort_values("ts").drop_duplicates(["bookmaker", "side"], keep="last")
        w = last.pivot_table(index="bookmaker", columns="side", values="odds", aggfunc="last")
        two = int(w.dropna(subset=[c for c in (f1, f2) if c in w]).shape[0]) if (f1 in w and f2 in w) else 0
        cert = False
        near = g[(g["mtk"] >= 0) & (g["mtk"] <= T30)]
        if len(near):
            tstar = near["ts"].max()
            gg = g[g["ts"] <= tstar].sort_values("ts").drop_duplicates(["bookmaker", "side"], keep="last")
            ww = gg.pivot_table(index="bookmaker", columns="side", values="odds", aggfunc="last")
            if f1 in ww and f2 in ww:
                cert = int(ww.dropna(subset=[f1, f2]).shape[0]) >= min_books
        out.append({"league": lg, "market": mk, "fixture_key": fk, "two_sided_books": two,
                    "has_t30_capture": bool(len(near)), "certified_t30_close": cert,
                    "fallback_like": bool(is_fallback(mk, g["odds"]).any())})
    d = pd.DataFrame(out)
    if d.empty:
        return pd.DataFrame(), {"btts_1h_rows_removed": removed_by_league}
    agg = d.groupby(["league", "market"]).agg(
        fixtures=("fixture_key", "nunique"),
        two_sided_any=("two_sided_books", lambda x: int((x >= 1).sum())),
        two_sided_min_books=("two_sided_books", lambda x: int((x >= min_books).sum())),
        t30_captured=("has_t30_capture", "sum"),
        certified_t30_close=("certified_t30_close", "sum")).reset_index()
    agg["certified_t30_close_share"] = (agg["certified_t30_close"] / agg["fixtures"]).round(4)
    return agg, {"btts_1h_rows_removed": {k: int(v) for k, v in removed_by_league.items()},
                 "btts_1h_rows_removed_total": int(len(removed)), "window": [str(b["ts"].min()), str(b["ts"].max())]}


# ── v9 captures (history + forward) ─────────────────────────────────────────────────────────────
def v9_capture_coverage(path, leagues: set) -> tuple[pd.DataFrame, dict]:
    o = pd.read_csv(path, low_memory=False)
    o = o[o["league"].isin(leagues)].copy()
    kept, removed = contamination_filter_btts(o, "market", None, "odds")
    o = kept[kept["market"].isin(CAPTURE_MARKETS)].copy()
    o["mkt"] = o["market"].map(lambda m: CAPTURE_MARKETS[m][0])
    o["side"] = o["market"].map(lambda m: CAPTURE_MARKETS[m][1])
    o["timing_class"] = np.where(o["snapshot_ts"].astype(str).str[11:19].eq("00:00:00"), "BACKFILL_DATE_ONLY", "TIMESTAMPED")
    o["fallback_like"] = [bool(is_fallback(m, [x])[0]) for m, x in zip(o["mkt"], o["odds"])]
    fx = o.groupby(["league", "mkt", "match_date", "match"]).agg(
        sides=("side", "nunique"), timing=("timing_class", "first"), fb=("fallback_like", "any")).reset_index()
    agg = fx.groupby(["league", "mkt", "timing"]).agg(fixtures=("match", "size"),
                                                      two_sided=("sides", lambda x: int((x >= 2).sum())),
                                                      fallback_like=("fb", "sum")).reset_index()
    return agg, {"btts_1h_rows_removed": {k: int(v) for k, v in removed.groupby("league").size().items()},
                 "btts_1h_rows_removed_total": int(len(removed)),
                 "btts_1h_date_range": [str(removed["match_date"].min()), str(removed["match_date"].max())] if len(removed) else None}


def legacy_backtest_fallbacks(v9_out, leagues: set) -> dict:
    """Constant-filled side-market prices in v9's legacy backtest results (never certifiable)."""
    res = {}
    for mk, fn, col in (("BTTS", "backtest_results_btts.csv", "odds_btts"),
                        ("OU15", "backtest_results_over15.csv", "odds_over15"),
                        ("OU35", "backtest_results_over35.csv", "odds_over35")):
        p = v9_out / fn
        if not p.exists():
            continue
        d = pd.read_csv(p, low_memory=False, usecols=lambda c: c in {"league", "date", col, "price_synthetic"})
        d = d[d["league"].isin(leagues)]
        fb = is_fallback(mk, d[col])
        syn = d["price_synthetic"].astype(str).str.lower().eq("true") if "price_synthetic" in d else pd.Series(False, index=d.index)
        res[mk] = {"rows": int(len(d)), "price_present": int(d[col].notna().sum()),
                   "equals_fallback_constant": int(fb.sum()), "flagged_price_synthetic": int(syn.sum()),
                   "real_price_rows": int((d[col].notna() & ~fb & ~syn.to_numpy()).sum()),
                   "by_league_fallback": {k: int(v) for k, v in d[fb].groupby("league").size().items()}}
    return res


# ── certification ───────────────────────────────────────────────────────────────────────────────
#: price classes that may enter a CERTIFIED ROI / EV / CLV. Everything else (closing as entry,
#: archive with unknown timing, date-only backfill, synthetic proxies, constants) is NOT certifiable.
CERTIFIABLE_ENTRY = {"FD_PREMATCH_APPROX", "FIRST_SIGHT_SNAPSHOT"}
NOT_CERTIFIABLE_SOURCES = {"FALLBACK_CONSTANT", "SYNTHETIC_MARKET_PROXY", "BACKTEST_ARCHIVE"}


def certifiable(market: str, odds, price_is_real, price_source, price_class) -> np.ndarray:
    """Row mask of prices allowed in a certified ROI/EV/CLV."""
    o = pd.to_numeric(pd.Series(odds), errors="coerce").to_numpy()
    real = pd.Series(price_is_real).fillna(False).astype(bool).to_numpy()
    src = pd.Series(price_source).astype(str).to_numpy()
    cls = pd.Series(price_class).astype(str).to_numpy()
    fb = is_fallback(market, o) & (cls != "FIRST_SIGHT_SNAPSHOT")      # a timed real 1.85 quote survives
    return (real & np.isfinite(o) & (o > 1.0) & ~fb & ~np.isin(src, list(NOT_CERTIFIABLE_SOURCES))
            & np.isin(cls, list(CERTIFIABLE_ENTRY)))


def certified_roi(df: pd.DataFrame, market: str) -> dict:
    """Flat-stake ROI over certifiable rows only. df: odds, won (0/1), price_is_real, price_source,
    price_class. Rows that are not certifiable are counted and excluded, never priced."""
    m = certifiable(market, df["odds"], df["price_is_real"], df["price_source"], df["price_class"])
    d = df[m]
    pnl = np.where(d["won"].astype(float) == 1, d["odds"].astype(float) - 1, -1.0)
    return {"n_certified": int(m.sum()), "n_excluded": int((~m).sum()),
            "roi": float(pnl.mean()) if len(d) else None, "status": "CERTIFIED" if len(d) else "NOT_CERTIFIABLE"}

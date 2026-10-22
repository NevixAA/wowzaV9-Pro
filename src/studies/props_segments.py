"""Pre-registered props segments — do attacking defenders / attacking midfielders carry an edge?

    python -m src.studies.props_segments

THE HYPOTHESIS (owner, 2026-10-13). With weekly retraining, more data and odds-movement tracking,
the props model will find real edges where bookmakers price by reputation rather than role:
attacking full-backs / wing-backs, and attacking (advanced) midfielders.

WHY PRE-REGISTERED. Eight earlier tests found no repeatable props edge. Searching many past
segments always turns up some that look profitable by chance, so this one is decided on FUTURE
tips only, under rules frozen here BEFORE any of those tips exist. Nothing in this file may be
tuned after results are seen — a change means a new registration with a new date.

FROZEN RULES (REGISTERED_ON = 2026-10-13)
  Segment definitions, from each player's latest player_history row BEFORE the match (no peeking):
    ATT_DEF  position D, minutes_pg >= 45, and shots_pg >= 0.6 or key_passes_pg >= 0.6
    ATT_MID  position M, minutes_pg >= 45, and shots_pg >= 1.0 or key_passes_pg >= 1.2
    (thresholds = top quarter of each position by those rates, players with 45+ min, history
     to 2026-10-13: D shots 0.6 / key passes 0.6, M shots 1.0 / key passes 1.2)
  Markets: goals (anytime scorer), sot (1+ shot on target), assists — 6 segment x market cells.
  CONTROL: every other priced prop meeting the same tip rule, per market.
  Tip rule: priced by a bookmaker AND model_prob > 1 / market_odds (the model says value).
  Window: signal_date >= 2026-10-14 (tips made after registration), settled WIN/LOSS only.
  Price: market_odds as recorded when the tip was made (v9 records the best available price).
  Verdict per cell, 6 cells -> Bonferroni: one-sided 99.17% bounds (0.05 / 6):
    EDGE      n >= 150, ROI lower bound > 0, AND median CLV > 0 (beat the closing price)
    NO EDGE   n >= 150 and ROI upper bound < 0
    COLLECTING otherwise (n of 150)
  CLV: price taken / last captured price before kickoff - 1, from v9's prop odds history,
  matched on match date + market + initial-and-surname, ambiguous names refused.

Research only. Reads v9 through V9_LOCAL; never writes into v9; never stakes.
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.studies.common import write

REGISTERED_ON = "2026-10-13"
WINDOW_FROM = "2026-10-14"
SEGMENTS = {
    "ATT_DEF": {"position": "D", "min_minutes_pg": 45, "shots_pg": 0.6, "key_passes_pg": 0.6},
    "ATT_MID": {"position": "M", "min_minutes_pg": 45, "shots_pg": 1.0, "key_passes_pg": 1.2},
}
MARKETS = ("goals", "sot", "assists")
N_MIN = 150
ALPHA_ONE_SIDED = 0.05 / (len(SEGMENTS) * len(MARKETS))       # Bonferroni over 6 cells
N_BOOT = 4000
RNG = np.random.default_rng(20261013)

_TR = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "æ": "ae", "Æ": "Ae", "ß": "ss",
                     "đ": "d", "Đ": "D", "ı": "i"})


def _ini_sur(name) -> tuple | None:
    s = unicodedata.normalize("NFKD", str(name or "").translate(_TR))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    toks = [t for t in re.split(r"[\s.]+", re.sub(r"[^a-z\s.'-]", "", s)) if t]
    return (toks[0][0], toks[-1]) if len(toks) >= 2 else None


def load_ledger() -> pd.DataFrame:
    p = cfg.V9_LOCAL / "output" / "player_ledger.csv"
    d = pd.read_csv(p, low_memory=False)
    d = d[d["result"].isin(["WIN", "LOSS"])].copy()
    d["signal_date"] = d["signal_date"].astype(str).str[:10]
    d["match_date"] = d["match_date"].astype(str).str[:10]
    for c in ("model_prob", "market_odds", "pnl"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[(d["signal_date"] >= WINDOW_FROM) & d["market"].isin(MARKETS)]
    d = d[d["market_odds"].notna() & (d["market_odds"] > 1.0)]
    return d[d["model_prob"] > 1 / d["market_odds"]].reset_index(drop=True)


def attach_role(d: pd.DataFrame) -> pd.DataFrame:
    """Each tip's player rates from his latest history row strictly BEFORE the match date."""
    if d.empty:
        return d.assign(segment=pd.Series(dtype=str))
    h = pd.read_parquet(cfg.V9_LOCAL / "player_history.parquet",
                        columns=["player_id", "date", "minutes_pg", "shots_pg", "key_passes_pg"])
    h["date"] = pd.to_datetime(h["date"], errors="coerce")
    h = h[h["player_id"].isin(d["player_id"].dropna().unique())].sort_values("date")
    d = d.copy()
    d["_md"] = pd.to_datetime(d["match_date"], errors="coerce") - pd.Timedelta(days=1)
    d = d.sort_values("_md")
    # Identical key dtypes, or merge_asof refuses (ledger ids parse as float, history as int).
    d["player_id"] = pd.to_numeric(d["player_id"], errors="coerce").astype("float64")
    h["player_id"] = pd.to_numeric(h["player_id"], errors="coerce").astype("float64")
    d["_md"] = d["_md"].astype("datetime64[ns]")
    h["date"] = h["date"].astype("datetime64[ns]")
    # merge_asof RESETS THE INDEX (CLAUDE.md trap 3): read the columns off the merged frame and
    # never assign back by index.
    m = pd.merge_asof(d.dropna(subset=["player_id", "_md"]), h.dropna(subset=["date"]),
                      left_on="_md", right_on="date", by="player_id", direction="backward")
    seg = pd.Series("CONTROL", index=m.index)
    for name, r in SEGMENTS.items():
        hit = ((m["position"].astype(str) == r["position"]) & (m["minutes_pg"] >= r["min_minutes_pg"])
               & ((m["shots_pg"] >= r["shots_pg"]) | (m["key_passes_pg"] >= r["key_passes_pg"])))
        seg[hit] = name
    return m.assign(segment=seg).drop(columns=["_md", "date"], errors="ignore")


def attach_clv(d: pd.DataFrame) -> pd.DataFrame:
    if d.empty:
        return d.assign(clv=pd.Series(dtype=float))
    # v9's file is ROLLING since 2026-10-22: played matches live in player_prop_odds_history_archive/.
    from src.data.v9_source import read_v9_all
    h = read_v9_all("output/player_prop_odds_history.csv",
                    usecols=["snapshot_ts", "match_date", "player", "market", "odds"],
                    low_memory=False)
    if h.empty:
        return d.assign(clv=np.nan)
    h = h[h["match_date"].astype(str) >= WINDOW_FROM]
    h["k"] = h["player"].map(_ini_sur)
    h = h.dropna(subset=["k"])
    h["odds"] = pd.to_numeric(h["odds"], errors="coerce")
    # closing = best price at the LAST snapshot each player was quoted in, per match date + market
    last_ts = h.groupby(["match_date", "market", "player"])["snapshot_ts"].transform("max")
    close = (h[h["snapshot_ts"] == last_ts].groupby(["match_date", "market", "player", "k"])["odds"]
             .max().reset_index())
    names = close.groupby(["match_date", "market", "k"])["player"].nunique()
    close = close.set_index(["match_date", "market", "k"])
    out = []
    for r in d.itertuples(index=False):
        k = _ini_sur(r.player_name)
        key = (r.match_date, r.market, k)
        if k is None or key not in names.index or names[key] != 1:
            out.append(np.nan)
            continue
        c = close.loc[key, "odds"]
        c = float(c.iloc[0]) if hasattr(c, "iloc") else float(c)
        out.append(r.market_odds / c - 1 if c > 1 else np.nan)
    return d.assign(clv=out)


def _bounds(x: pd.Series, groups: pd.Series) -> tuple:
    s = pd.DataFrame({"x": x.to_numpy(float), "g": groups.to_numpy()}).groupby("g")["x"].agg(["sum", "count"])
    if len(s) < 3:
        return None, None
    idx = RNG.integers(0, len(s), size=(N_BOOT, len(s)))
    m = s["sum"].to_numpy()[idx].sum(1) / s["count"].to_numpy()[idx].sum(1)
    return (round(float(np.quantile(m, ALPHA_ONE_SIDED)), 4),
            round(float(np.quantile(m, 1 - ALPHA_ONE_SIDED)), 4))


def cell(g: pd.DataFrame) -> dict:
    n = len(g)
    if n == 0:
        return {"n": 0, "verdict": f"COLLECTING (0/{N_MIN})"}
    roi = float(g["pnl"].mean())
    lo, hi = _bounds(g["pnl"], g["match_date"])
    clv = g["clv"].dropna()
    med_clv = float(clv.median()) if len(clv) else None
    if n >= N_MIN and lo is not None and lo > 0 and med_clv is not None and med_clv > 0:
        verdict = "EDGE"
    elif n >= N_MIN and hi is not None and hi < 0:
        verdict = "NO EDGE"
    else:
        verdict = f"COLLECTING ({n}/{N_MIN})"
    return {"n": n, "won": int((g["result"] == "WIN").sum()), "hit": round(float((g["result"] == "WIN").mean()), 4),
            "needed": round(float((1 / g["market_odds"]).mean()), 4),
            "model_said": round(float(g["model_prob"].mean()), 4),
            "units": round(float(g["pnl"].sum()), 2), "roi": round(roi, 4), "roi_bounds": [lo, hi],
            "clv_n": int(len(clv)), "clv_median": None if med_clv is None else round(med_clv, 4),
            "clv_beat_share": round(float((clv > 0).mean()), 3) if len(clv) else None,
            "verdict": verdict}


def build() -> dict:
    d = attach_clv(attach_role(load_ledger()))
    cells = {}
    for seg in (*SEGMENTS, "CONTROL"):
        for mk in MARKETS:
            g = d[(d["segment"] == seg) & (d["market"] == mk)] if len(d) else d
            cells[f"{seg}|{mk}"] = cell(g)
    return {"registered_on": REGISTERED_ON, "window_from": WINDOW_FROM, "segments": SEGMENTS,
            "markets": list(MARKETS), "n_min": N_MIN, "alpha_one_sided": round(ALPHA_ONE_SIDED, 5),
            "tips_in_window": int(len(d)), "cells": cells,
            "generated_at": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")}


def to_md(r: dict) -> str:
    lab = {"goals": "Anytime scorer", "sot": "1+ shot on target", "assists": "Assist"}
    lines = ["# Props segments — pre-registered forward test", "",
             f"Registered {r['registered_on']}; counts tips made from {r['window_from']}. Rules frozen "
             f"in src/studies/props_segments.py. EDGE needs n >= {r['n_min']}, a positive ROI lower bound "
             f"(one-sided, Bonferroni over 6 cells) AND a positive median CLV.", "",
             f"Qualifying tips so far: **{r['tips_in_window']}**", "",
             "| Segment | Market | n | Won | Hit | Needed | P/L | ROI (bounds) | Median CLV | Verdict |",
             "|---|---|---:|---:|---:|---:|---:|---|---:|---|"]
    for k, c in r["cells"].items():
        seg, mk = k.split("|")
        if not c["n"]:
            lines.append(f"| {seg} | {lab[mk]} | 0 | | | | | | | {c['verdict']} |")
            continue
        b = c["roi_bounds"]
        bt = "" if b[0] is None else f" [{b[0]:+.0%}, {b[1]:+.0%}]"
        cl = "" if c["clv_median"] is None else f"{c['clv_median']:+.1%} ({c['clv_n']})"
        lines.append(f"| {seg} | {lab[mk]} | {c['n']} | {c['won']} | {c['hit']:.0%} | {c['needed']:.0%} | "
                     f"{c['units']:+.2f}u | {c['roi']:+.0%}{bt} | {cl} | {c['verdict']} |")
    lines += ["", "CONTROL = every other priced prop where the model beats the price. A segment only "
                  "matters if it beats its control AND the market's closing price. Paper only."]
    return "\n".join(lines) + "\n"


def main() -> int:
    r = build()
    write("props_segments", r)
    (cfg.OUTPUT_DIR / "studies" / "PROPS_SEGMENTS.md").write_text(to_md(r), encoding="utf-8")
    print(to_md(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

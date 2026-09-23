"""Canonical market history — five odds stores normalised into one shape, raw left untouched.

    python -m src.architecture.canonical_market --write

THE PROBLEM THIS SOLVES (section 12). Five files hold prices and none of them agree on how to
say so. `standard_odds_history` writes the market as `over25`; `standard_sidemarket` writes
`btts_yes` and `ht_over05`; `book_odds_snapshots` splits it into `OU25` plus a side of `OVER`
and adds a bookmaker column the others do not have. Training code should not have to learn five
dialects, and every place it does is a place a market gets silently missed.

WHAT NORMALISING DOES AND DOES NOT MEAN. It rewrites the SHAPE, never the numbers. Every raw
file stays exactly where it is and keeps its meaning -- this reads them and writes a sixth,
derived table. Nothing is deduplicated across sources either, because two quotes for the same
fixture and market at two timestamps are two observations, not a duplicate (section 26): the
only rows collapsed are exact repeats of (fixture, bookmaker, market, selection, timestamp).

MINUTES TO KICKOFF IS THE COLUMN THAT MAKES THIS USABLE. A price is only meaningful relative to
when it was taken, and two of the five sources record a kickoff time while three do not. Where
kickoff is absent the field is NaN rather than guessed, because inventing a kickoff would make
a late price look early and quietly corrupt any timing analysis built on it.

A CONSENSUS ROW IS NOT A BOOKMAKER. Four of the five sources record no bookmaker at all -- they
are the consensus or best price v9 captured. Those rows are labelled `CONSENSUS`, never assigned
to a real book, so a per-bookmaker analysis cannot accidentally attribute them to someone.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"

SOURCES = {
    "standard_odds_history.csv": "std_main",
    "standard_sidemarket_odds_history.csv": "std_side",
    "newformat_odds_history.csv": "nf_main",
    "newformat_odds_dense.csv": "nf_dense",
    "book_odds_snapshots.csv": "book_snapshots",
}

# One market vocabulary. Anything unmapped is kept verbatim and flagged, never dropped silently.
MARKET_MAP = {
    "over15": ("OU", 1.5, "OVER"), "under15": ("OU", 1.5, "UNDER"),
    "over25": ("OU", 2.5, "OVER"), "under25": ("OU", 2.5, "UNDER"),
    "over35": ("OU", 3.5, "OVER"), "under35": ("OU", 3.5, "UNDER"),
    "btts_yes": ("BTTS", None, "YES"), "btts_no": ("BTTS", None, "NO"),
    "ht_over05": ("HT_OU", 0.5, "OVER"), "ht_under05": ("HT_OU", 0.5, "UNDER"),
    "ht_over15": ("HT_OU", 1.5, "OVER"), "ht_under15": ("HT_OU", 1.5, "UNDER"),
    "h2h_home": ("H2H", None, "HOME"), "h2h_draw": ("H2H", None, "DRAW"),
    "h2h_away": ("H2H", None, "AWAY"),
}
SPLIT_MARKET = {"OU15": ("OU", 1.5), "OU25": ("OU", 2.5), "OU35": ("OU", 3.5),
                "BTTS": ("BTTS", None)}


def _v9() -> Path:
    return Path(cfg.V9_LOCAL)


def _split_match(s: pd.Series) -> pd.DataFrame:
    parts = s.astype(str).str.split(" vs ", n=1, expand=True)
    if parts.shape[1] < 2:
        parts[1] = np.nan
    return pd.DataFrame({"home_team": parts[0].str.strip(),
                         "away_team": parts[1].astype(str).str.strip()})


def build() -> tuple[pd.DataFrame, dict]:
    frames, stats = [], {}
    for fname, tag in SOURCES.items():
        p = _v9() / "output" / fname
        if not p.exists():
            stats[tag] = {"rows": 0, "note": "missing"}
            continue
        d = pd.read_csv(p, low_memory=False)
        n0 = len(d)
        out = pd.DataFrame(index=d.index)
        out["source"] = tag
        out["league"] = d.get("league", pd.Series(index=d.index, dtype=object)).astype(str).str.strip()
        out["match_date"] = pd.to_datetime(d.get("match_date"), errors="coerce")
        out["kickoff_utc"] = pd.to_datetime(d.get("kickoff_utc"), errors="coerce", utc=True) \
            if "kickoff_utc" in d.columns else pd.NaT
        out["snapshot_ts"] = pd.to_datetime(d.get("snapshot_ts"), errors="coerce", utc=True)
        tm = _split_match(d["match"]) if "match" in d.columns else pd.DataFrame(
            {"home_team": np.nan, "away_team": np.nan}, index=d.index)
        out["home_team"], out["away_team"] = tm["home_team"], tm["away_team"]
        out["bookmaker"] = (d["bookmaker"].astype(str).str.strip()
                            if "bookmaker" in d.columns else "CONSENSUS")
        out["odds"] = pd.to_numeric(d.get("odds"), errors="coerce")

        raw_mkt = d.get("market", pd.Series(index=d.index, dtype=object)).astype(str).str.strip()
        if "side" in d.columns:
            side = d["side"].astype(str).str.upper().str.strip()
            fam = raw_mkt.map(lambda m: SPLIT_MARKET.get(str(m), (str(m), None))[0])
            line = raw_mkt.map(lambda m: SPLIT_MARKET.get(str(m), (str(m), None))[1])
            out["market"], out["line"], out["selection"] = fam, line, side
        else:
            low = raw_mkt.str.lower()
            out["market"] = low.map(lambda m: MARKET_MAP.get(m, (m.upper(), None, None))[0])
            out["line"] = low.map(lambda m: MARKET_MAP.get(m, (m, None, None))[1])
            out["selection"] = low.map(lambda m: MARKET_MAP.get(m, (m, None, "UNKNOWN"))[2])
        out["market_raw"] = raw_mkt
        frames.append(out)
        stats[tag] = {"rows": int(n0),
                      "unmapped_markets": sorted(set(
                          raw_mkt[out["selection"].isin(["UNKNOWN", None])].astype(str)))[:8]}

    if not frames:
        raise RuntimeError("no odds sources readable")
    m = pd.concat(frames, ignore_index=True)
    m = m.dropna(subset=["odds", "home_team", "away_team"])
    m = m[m["odds"] > 1.0]

    # Re-coerce the datetime columns AFTER the concat. Three of the five sources have no
    # kickoff column at all, so those frames carry a scalar NaT and the concatenated column
    # comes back as object dtype -- which subtracts with a TypeError rather than producing NaN.
    for c in ("kickoff_utc", "snapshot_ts"):
        m[c] = pd.to_datetime(m[c], errors="coerce", utc=True)
    m["match_date"] = pd.to_datetime(m["match_date"], errors="coerce")

    m["fixture_key"] = (m["match_date"].dt.strftime("%Y-%m-%d") + "|" + m["league"] + "|"
                        + m["home_team"] + "|" + m["away_team"])
    m["minutes_to_kickoff"] = ((m["kickoff_utc"] - m["snapshot_ts"]).dt.total_seconds() / 60.0)

    before = len(m)
    # Collapse only EXACT repeats. Two quotes at two timestamps are two observations.
    m = m.drop_duplicates(["fixture_key", "bookmaker", "market", "line", "selection",
                           "snapshot_ts"], keep="last")
    man = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "calc_version": CALC_VERSION,
        "rows": int(len(m)), "exact_duplicate_rows_collapsed": int(before - len(m)),
        "fixtures": int(m["fixture_key"].nunique()),
        "first": str(m["match_date"].min())[:10], "last": str(m["match_date"].max())[:10],
        "bookmakers": int(m["bookmaker"].nunique()),
        "consensus_share": round(float((m["bookmaker"] == "CONSENSUS").mean()), 4),
        "rows_with_kickoff_time": round(float(m["minutes_to_kickoff"].notna().mean()), 4),
        "by_source": {k: int(v) for k, v in m["source"].value_counts().items()},
        "by_market": {k: int(v) for k, v in m["market"].value_counts().items()},
        "source_stats": stats,
    }
    return m, man


def out_dir() -> Path:
    p = cfg.OUTPUT_DIR / "architecture"
    p.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    m, man = build()
    print(f"[market] {man['rows']:,} quotes on {man['fixtures']:,} fixtures  "
          f"{man['first']}..{man['last']}")
    print(f"[market] {man['bookmakers']} bookmaker labels, "
          f"{man['consensus_share']:.1%} of rows are CONSENSUS (no book recorded)")
    print(f"[market] exact duplicates collapsed: {man['exact_duplicate_rows_collapsed']:,}")
    print(f"[market] rows with a usable minutes-to-kickoff: {man['rows_with_kickoff_time']:.1%}")
    print("\nBY SOURCE");  [print(f"   {k:<18}{v:>9,}") for k, v in man["by_source"].items()]
    print("\nBY MARKET");  [print(f"   {k:<18}{v:>9,}") for k, v in man["by_market"].items()]
    if a.write:
        m.to_parquet(out_dir() / "canonical_market_history.parquet", index=False)
        (out_dir() / "canonical_market_manifest.json").write_text(
            json.dumps(man, indent=2, default=str), encoding="utf-8")
        print(f"\n[market] wrote canonical_market_history.parquet + manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

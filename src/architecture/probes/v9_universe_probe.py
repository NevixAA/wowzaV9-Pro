"""Dump the EXACT set of fixtures that reach v9 training, with the metadata to compare it.

Run from inside a wowza-betting checkout with v9's own interpreter:

    python v9_universe_probe.py --out universe.parquet

The counting probe answered "how many". This answers "which", because every question in the
shadow-learning brief -- what are the incremental fixtures, are they older, thinner, from
different leagues, from a different football regime -- needs the row set, not a total.

Same discipline as the counting probe: v9's own loader, v9's own feature builder, v9's own
config, invoked as a subprocess rather than imported, so the universe measured is the one
production actually builds and not a re-implementation that might drift.

READ-ONLY. Loads, tags, writes one parquet outside the repo, exits.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    import numpy as np
    import pandas as pd
    import config
    from src.data_loader import load_all_matches
    from src.feature_engineering import build_features

    raw = load_all_matches()
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")

    def key(d):
        return (d["date"].dt.strftime("%Y-%m-%d") + "|" + d["league"].astype(str).str.strip()
                + "|" + d["home_team"].astype(str).str.strip()
                + "|" + d["away_team"].astype(str).str.strip())

    raw["fixture_key"] = key(raw)
    raw["in_loader"] = True
    raw["is_duplicate_row"] = raw.duplicated("fixture_key", keep=False)

    after_covid = raw
    if getattr(config, "EXCLUDE_COVID_SEASONS", False):
        after_covid = raw[~raw["season"].isin(config.COVID_SEASONS)]
    covid_dropped = set(raw["fixture_key"]) - set(after_covid["fixture_key"])

    feat = build_features(after_covid)
    feat["date"] = pd.to_datetime(feat["date"], errors="coerce")
    feat["fixture_key"] = key(feat)
    valid = feat.dropna(subset=["over25", "home_scored_last5"])
    reached = set(valid["fixture_key"])

    std = set(config.STANDARD_FORMAT_LEAGUES)
    nfm = set(config.NEW_FORMAT_LEAGUES)
    in_std = set(valid.loc[valid["league"].isin(std), "fixture_key"])
    in_nf = set(valid.loc[valid["league"].isin(nfm), "fixture_key"])
    ht_cols = [c for c in ("ht_over05", "home_ht_over05_rate") if c in valid.columns]
    in_ht = set(valid.dropna(subset=ht_cols)["fixture_key"]) if ht_cols else set()

    out = (raw.sort_values("date", kind="mergesort")
              .drop_duplicates("fixture_key", keep="last").copy())
    out["reaches_features"] = out["fixture_key"].isin(reached)
    out["dropped_by_covid_filter"] = out["fixture_key"].isin(covid_dropped)
    out["in_standard_model"] = out["fixture_key"].isin(in_std)
    out["in_newformat_model"] = out["fixture_key"].isin(in_nf)
    out["in_ht_model"] = out["fixture_key"].isin(in_ht)
    out["in_v9_training"] = out["in_standard_model"] | out["in_newformat_model"]

    cols = ["fixture_key", "date", "league", "season", "home_team", "away_team",
            "home_goals", "away_goals", "home_shots", "away_shots", "home_sot", "away_sot",
            "home_corners", "away_corners", "home_fouls", "away_fouls",
            "ht_home_goals", "ht_away_goals",
            "odds_over25", "odds_under25", "odds_btts", "odds_over15", "odds_over35",
            "is_duplicate_row", "reaches_features", "dropped_by_covid_filter",
            "in_standard_model", "in_newformat_model", "in_ht_model", "in_v9_training"]
    out = out[[c for c in cols if c in out.columns]]
    for c in out.columns:
        if out[c].dtype == object and c not in ("fixture_key", "league", "season",
                                                "home_team", "away_team"):
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out.to_parquet(a.out, index=False)

    print(f"[universe] wrote {a.out}")
    print(f"  loader rows (pre-dedupe) : {len(raw):,}")
    print(f"  unique fixtures          : {len(out):,}")
    print(f"  duplicate rows in loader : {int(raw['is_duplicate_row'].sum()):,}")
    print(f"  dropped by COVID filter  : {len(covid_dropped):,}")
    print(f"  reach feature build      : {int(out['reaches_features'].sum()):,}")
    print(f"  IN V9 TRAINING           : {int(out['in_v9_training'].sum()):,}")
    print(f"     standard track        : {int(out['in_standard_model'].sum()):,}")
    print(f"     new-format track      : {int(out['in_newformat_model'].sum()):,}")
    print(f"     HT track              : {int(out['in_ht_model'].sum()):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

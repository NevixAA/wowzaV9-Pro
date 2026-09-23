"""Probe: reproduce v9's training frame EXACTLY and report where every fixture is lost.

Run from inside a wowza-betting checkout, with v9's own interpreter:

    python v9_training_probe.py --out probe.json

WHY A SUBPROCESS AND NOT AN IMPORT. Pro reads v9's committed data; it does not import v9's code.
Keeping that boundary means this audit cannot accidentally couple the two repos, and it means
the frame measured here is the one v9's own interpreter and its own config produce -- not a
re-implementation of them that might drift. If the numbers here are wrong, they are wrong in the
same way production is wrong, which is the only useful kind of wrong for an audit.

WHAT IT MEASURES. `mode_train` is a funnel, and every stage silently discards rows:

    load_all_matches()                       every completed fixture the loader can see
      -> drop COVID seasons                  config.EXCLUDE_COVID_SEASONS
      -> build_features()                    adds rolling form
      -> dropna(over25, home_scored_last5)   a team's first matches have no form yet
      -> league membership                   STANDARD_FORMAT / NEW_FORMAT sets
      -> per-target dropna                   ht_over05 needs half-time scores, etc.

Nothing logs the size of the loss at each stage, so a fixture that never reaches a model is
indistinguishable from one that was never collected. This prints both, per stage and per league.

READ-ONLY. It loads, counts and exits. It does not train, save a model, write into output/, or
touch the network beyond what load_all_matches already does.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    import pandas as pd
    import config
    from src.data_loader import load_all_matches
    from src.feature_engineering import build_features

    rep: dict = {"stages": [], "errors": []}

    raw = load_all_matches()
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce")

    def fkey(d):
        return (d["date"].dt.strftime("%Y-%m-%d") + "|" + d["league"].astype(str) + "|"
                + d["home_team"].astype(str).str.strip() + "|"
                + d["away_team"].astype(str).str.strip())

    def stage(name, d, note=""):
        k = fkey(d)
        rep["stages"].append({
            "stage": name, "rows": int(len(d)), "unique_fixtures": int(k.nunique()),
            "duplicate_rows": int(len(d) - k.nunique()),
            "leagues": int(d["league"].nunique()),
            "first": str(d["date"].min())[:10], "last": str(d["date"].max())[:10],
            "note": note})
        return k

    k_raw = stage("1_load_all_matches", raw, "everything the loader can see")
    rep["loader_leagues"] = sorted(raw["league"].dropna().astype(str).unique().tolist())

    after_covid = raw
    if getattr(config, "EXCLUDE_COVID_SEASONS", False):
        after_covid = raw[~raw["season"].isin(config.COVID_SEASONS)]
    stage("2_after_covid_exclusion", after_covid,
          f"EXCLUDE_COVID_SEASONS={getattr(config, 'EXCLUDE_COVID_SEASONS', None)} "
          f"{list(getattr(config, 'COVID_SEASONS', []))}")

    feat = build_features(after_covid)
    feat["date"] = pd.to_datetime(feat["date"], errors="coerce")
    stage("3_build_features", feat, "rolling form attached")

    valid = feat.dropna(subset=["over25", "home_scored_last5"])
    k_valid = stage("4_dropna_form", valid,
                    "rows with no rolling-form history are dropped (invariant 8)")

    std = set(config.STANDARD_FORMAT_LEAGUES)
    nfm = set(config.NEW_FORMAT_LEAGUES)
    std_valid = valid[valid["league"].isin(std)]
    nf_valid = valid[valid["league"].isin(nfm)]
    stage("5a_standard_model_input", std_valid, "STANDARD_FORMAT_LEAGUES only")
    stage("5b_newformat_model_input", nf_valid, "NEW_FORMAT_LEAGUES only")

    unclassified = valid[~valid["league"].isin(std | nfm)]
    rep["unclassified_leagues"] = (
        unclassified.groupby("league").size().sort_values(ascending=False).to_dict())
    rep["unclassified_rows"] = int(len(unclassified))

    for tgt, need in (("ht_over05", ["ht_over05", "home_ht_over05_rate"]),
                      ("ht_over15", ["ht_over15", "home_ht_over15_rate"])):
        have = [c for c in need if c in valid.columns]
        sub = valid.dropna(subset=have) if have else valid.iloc[0:0]
        stage(f"6_{tgt}_model_input", sub, f"needs {need}")
        rep.setdefault("ht_leagues", {})[tgt] = sorted(
            sub["league"].dropna().astype(str).unique().tolist())

    sm_all = pd.concat([std_valid, nf_valid], ignore_index=True)
    for tgt in getattr(config, "SIDE_MARKETS", {}):
        sub = sm_all.dropna(subset=[tgt]) if tgt in sm_all.columns else sm_all.iloc[0:0]
        stage(f"7_sidemarket_{tgt}", sub, f"dropna on target {tgt}")

    # The union of every model's input -- a fixture reaching NO model is stranded inside v9.
    reached = set()
    for d in (std_valid, nf_valid):
        reached |= set(fkey(d))
    rep["fixtures_reaching_any_main_model"] = len(reached)
    rep["fixtures_loaded"] = int(k_raw.nunique())
    rep["loaded_but_no_model"] = int(k_raw.nunique() - len(set(k_raw) & reached))

    lost = raw[~fkey(raw).isin(reached)]
    rep["lost_by_league"] = (lost.groupby("league").size()
                             .sort_values(ascending=False).head(40).to_dict())
    rep["lost_by_season"] = (lost.groupby(lost["date"].dt.year).size().to_dict())

    cov = {}
    for c in ("home_corners", "ht_home_goals", "odds_over25", "odds_btts", "odds_over15",
              "odds_over35", "home_shots", "home_sot", "home_xg"):
        if c in raw.columns:
            cov[c] = round(float(raw[c].notna().mean()), 4)
    rep["loader_column_coverage"] = cov
    rep["config"] = {
        "STANDARD_FORMAT_LEAGUES": sorted(std),
        "NEW_FORMAT_LEAGUES": sorted(nfm),
        "ENABLED_LEAGUES": sorted(set(getattr(config, "ENABLED_LEAGUES", set()))),
        "SIDE_MARKETS": list(getattr(config, "SIDE_MARKETS", {})),
        "BACKTEST_MIN_TRAIN": getattr(config, "BACKTEST_MIN_TRAIN", None),
    }
    Path(a.out).write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    print(f"[probe] wrote {a.out}")
    for s in rep["stages"]:
        print(f"  {s['stage']:<30}{s['rows']:>8,} rows  {s['unique_fixtures']:>8,} fixtures  "
              f"{s['first']}..{s['last']}  {s['note']}")
    print(f"\n  loaded fixtures: {rep['fixtures_loaded']:,}")
    print(f"  reaching a main model: {rep['fixtures_reaching_any_main_model']:,}")
    print(f"  LOADED BUT REACHING NO MAIN MODEL: {rep['loaded_but_no_model']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

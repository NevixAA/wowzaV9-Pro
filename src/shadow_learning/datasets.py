"""Define the champion dataset, the canonical dataset, and explain the difference between them.

    python -m src.shadow_learning.datasets --write

Sections 3, 4 and 5 of the brief. Three jobs:

    DATASET_V9_CURRENT      the exact fixtures v9 trains on today, taken from v9's own loader
                            and feature builder run in v9's own interpreter -- not approximated.
    DATASET_CANONICAL_FULL  the canonical match history, same measurements recorded.
    INCREMENTAL             canonical minus v9, described well enough to say WHY each fixture is
                            missing and whether it looks like useful evidence or filler.

WHY THE INCREMENTAL DESCRIPTION MATTERS MORE THAN THE COUNT. The first controlled comparison
found that 23,000 extra fixtures changed nothing. There are several very different explanations
for that and they lead to opposite actions: if the extra fixtures are recent, complete and from
leagues we bet, then the null result is a fact about the model's ceiling. If they are old, thin
and from leagues we never touch, the null result is a fact about the data and a better-chosen
subset might still help. Counting cannot separate those. Describing can.

THE COMPARISON IS DELIBERATELY ASYMMETRIC IN ONE PLACE. v9's universe is taken AFTER its feature
build and league filters, because that is what reaches a model -- a fixture the loader sees and
then drops is not training data. The canonical side is taken before any model-specific filter,
because the whole point is to ask what a different training policy could have used.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"
PROBE = (Path(__file__).resolve().parents[1] / "architecture" / "probes"
         / "v9_universe_probe.py")

# Feature families used to grade completeness. Kept to what actually exists at scale: xG is
# present on under 2% of rows estate-wide, so grading on it would grade almost everything F.
COMPLETENESS = {
    "shots": ("home_shots", "away_shots"),
    "sot": ("home_sot", "away_sot"),
    "corners": ("home_corners", "away_corners"),
    "fouls": ("home_fouls", "away_fouls"),
    "ht": ("ht_home_goals", "ht_away_goals"),
    "market": ("odds_over25", "odds_under25"),
}


def O() -> Path:
    p = cfg.OUTPUT_DIR / "shadow_learning"
    p.mkdir(parents=True, exist_ok=True)
    return p


def A() -> Path:
    return cfg.OUTPUT_DIR / "architecture"


def v9_universe(*, refresh: bool = False) -> pd.DataFrame:
    """The champion dataset, from v9's own code. Cached; the probe is slow."""
    cache = O() / "v9_universe.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)
    v9 = Path(cfg.V9_LOCAL)
    tmp = v9 / "_shadow_universe_tmp.py"
    tmp.write_text(PROBE.read_text(encoding="utf-8"), encoding="utf-8")
    py = v9 / ".venv" / "Scripts" / "python.exe"
    try:
        subprocess.run([str(py) if py.exists() else sys.executable,
                        "_shadow_universe_tmp.py", "--out", str(cache)],
                       cwd=str(v9), check=True, timeout=5400)
    finally:
        tmp.unlink(missing_ok=True)
    return pd.read_parquet(cache)


def canonical() -> pd.DataFrame:
    p = A() / "canonical_match_history.parquet"
    if not p.exists():
        raise RuntimeError("canonical_match_history.parquet missing — run "
                           "src.architecture.canonical --write")
    d = pd.read_parquet(p)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["league"] = d["league"].astype(str).str.strip()
    d["fixture_key"] = (d["date"].dt.strftime("%Y-%m-%d") + "|" + d["league"] + "|"
                        + d["home_team"].astype(str).str.strip() + "|"
                        + d["away_team"].astype(str).str.strip())
    return d


def _grade(d: pd.DataFrame) -> pd.DataFrame:
    """Per-fixture completeness flags and a single tier."""
    out = d.copy()
    for name, cols in COMPLETENESS.items():
        have = [c for c in cols if c in out.columns]
        out[f"has_{name}"] = (out[have].notna().all(axis=1) if have
                              else pd.Series(False, index=out.index))
    out["n_families"] = out[[f"has_{k}" for k in COMPLETENESS]].sum(axis=1)
    # Tiers are cumulative and named for what they let a model do, not for how many columns
    # they happen to contain.
    out["tier"] = np.select(
        [out["has_shots"] & out["has_sot"] & out["has_corners"] & out["has_market"],
         out["has_shots"] & out["has_sot"] & out["has_corners"],
         out["has_shots"] & out["has_sot"],
         out["has_shots"]],
        ["MARKET", "STANDARD_PLUS", "STANDARD", "PARTIAL"], default="CORE")
    return out


def _describe(d: pd.DataFrame, label: str) -> dict:
    r = {"dataset": label, "rows": int(len(d)),
         "unique_fixtures": int(d["fixture_key"].nunique()),
         "duplicate_rows": int(len(d) - d["fixture_key"].nunique()),
         "first": str(d["date"].min())[:10], "last": str(d["date"].max())[:10],
         "leagues": int(d["league"].nunique()),
         "median_age_days": int((pd.Timestamp.now().normalize() - d["date"]).dt.days.median()),
         "avg_goals": round(float((d["home_goals"] + d["away_goals"]).mean()), 4)}
    for t, expr in (("btts", lambda x: ((x.home_goals > 0) & (x.away_goals > 0))),
                    ("over15", lambda x: (x.home_goals + x.away_goals) >= 2),
                    ("over25", lambda x: (x.home_goals + x.away_goals) >= 3),
                    ("over35", lambda x: (x.home_goals + x.away_goals) >= 4)):
        r[f"rate_{t}"] = round(float(expr(d).mean()), 4)
    for k in COMPLETENESS:
        r[f"cov_{k}"] = round(float(d[f"has_{k}"].mean()), 4) if f"has_{k}" in d.columns else 0.0
    return r


def build() -> dict:
    v9 = v9_universe()
    v9["date"] = pd.to_datetime(v9["date"], errors="coerce")
    v9_train = _grade(v9[v9["in_v9_training"]].copy())
    can = _grade(canonical()[lambda x: x["trainable"]].copy())

    v9_keys = set(v9_train["fixture_key"])
    inc = can[~can["fixture_key"].isin(v9_keys)].copy()

    # WHY is each incremental fixture absent from v9 training? Ordered from most specific to
    # least, so a fixture gets the most informative reason that applies.
    seen_by_loader = set(v9["fixture_key"])
    reached_features = set(v9.loc[v9["reaches_features"], "fixture_key"])
    std = set(v9.loc[v9["in_standard_model"], "fixture_key"])
    nfm = set(v9.loc[v9["in_newformat_model"], "fixture_key"])
    v9_leagues = set(v9["league"].unique())

    def reason(row):
        k = row["fixture_key"]
        if k in reached_features and k not in std and k not in nfm:
            return "league_in_neither_model_track"
        if k in seen_by_loader:
            return "dropped_no_rolling_form_history"
        if row["league"] not in v9_leagues:
            return "league_absent_from_v9_loader"
        return "fixture_absent_from_v9_loader_sources"

    inc["reason_not_in_v9_current"] = inc.apply(reason, axis=1)
    inc["age_days"] = (pd.Timestamp.now().normalize() - inc["date"]).dt.days
    inc["season_year"] = inc["date"].dt.year
    inc["month"] = inc["date"].dt.to_period("M").astype(str)

    inv = pd.DataFrame([_describe(v9_train, "DATASET_V9_CURRENT"),
                        _describe(can, "DATASET_CANONICAL_FULL"),
                        _describe(inc, "INCREMENTAL")])

    by_league = (inc.groupby("league")
                 .agg(n=("fixture_key", "size"), first=("date", "min"), last=("date", "max"),
                      avg_goals=("total_goals", "mean"),
                      cov_shots=("has_shots", "mean"), cov_corners=("has_corners", "mean"),
                      cov_market=("has_market", "mean"))
                 .reset_index().sort_values("n", ascending=False))
    by_league["in_v9_leagues"] = by_league["league"].isin(v9_leagues)

    shift = []
    for label, d in (("V9_CURRENT", v9_train), ("INCREMENTAL", inc)):
        for yr, g in d.groupby(d["date"].dt.year):
            if len(g) < 200:
                continue
            shift.append({"dataset": label, "year": int(yr), "n": int(len(g)),
                          "avg_goals": round(float((g.home_goals + g.away_goals).mean()), 4),
                          "rate_btts": round(float(((g.home_goals > 0)
                                                    & (g.away_goals > 0)).mean()), 4),
                          "rate_over25": round(float(((g.home_goals + g.away_goals)
                                                      >= 3).mean()), 4),
                          "home_goals": round(float(g.home_goals.mean()), 4),
                          "away_goals": round(float(g.away_goals.mean()), 4),
                          "cov_shots": round(float(g["has_shots"].mean()), 4),
                          "cov_corners": round(float(g["has_corners"].mean()), 4)})

    tiers = pd.concat([
        v9_train["tier"].value_counts().rename("V9_CURRENT"),
        can["tier"].value_counts().rename("CANONICAL_FULL"),
        inc["tier"].value_counts().rename("INCREMENTAL")], axis=1).fillna(0).astype(int)
    tiers.index.name = "tier"

    return {"v9_train": v9_train, "canonical": can, "incremental": inc,
            "inventory": inv, "by_league": by_league,
            "shift": pd.DataFrame(shift), "tiers": tiers.reset_index(),
            "duplicate_rows_in_v9_loader": int(v9["is_duplicate_row"].sum() // 2),
            "covid_dropped": int(v9["dropped_by_covid_filter"].sum())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    r = build()

    print("DATASET INVENTORY")
    print(r["inventory"][["dataset", "rows", "unique_fixtures", "first", "last", "leagues",
                          "median_age_days", "avg_goals", "rate_over25"]].to_string(index=False))
    print("\nCOMPLETENESS")
    print(r["inventory"][["dataset"] + [f"cov_{k}" for k in COMPLETENESS]].to_string(index=False))
    print("\nQUALITY TIERS")
    print(r["tiers"].to_string(index=False))
    print(f"\nWHY THE INCREMENTAL FIXTURES ARE NOT IN V9 TRAINING")
    print(r["incremental"]["reason_not_in_v9_current"].value_counts().to_string())
    print(f"\nINCREMENTAL BY LEAGUE (top 16)")
    print(r["by_league"].head(16).to_string(index=False))
    print(f"\nduplicate fixture pairs inside v9's loader : "
          f"{r['duplicate_rows_in_v9_loader']:,}")
    print(f"fixtures the COVID filter removes           : {r['covid_dropped']:,}")

    if a.write:
        cols = ["fixture_key", "date", "league", "season", "month", "age_days",
                "home_team", "away_team", "sources", "quality_tier", "tier",
                "has_shots", "has_sot", "has_corners", "has_fouls", "has_ht", "has_market",
                "n_families", "btts", "over15", "over25", "over35",
                "reason_not_in_v9_current"]
        r["incremental"][[c for c in cols if c in r["incremental"].columns]].to_csv(
            O() / "incremental_fixture_inventory.csv", index=False)
        r["inventory"].to_csv(O() / "dataset_inventory.csv", index=False)
        r["tiers"].to_csv(O() / "dataset_quality_tiers.csv", index=False)
        r["by_league"].to_csv(O() / "incremental_by_league.csv", index=False)
        r["shift"].to_csv(O() / "distribution_shift.csv", index=False)
        print(f"\n[datasets] wrote 5 artifacts to {O()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

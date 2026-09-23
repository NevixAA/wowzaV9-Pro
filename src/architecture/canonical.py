"""PHASE B — build the canonical completed-fixture history, in parallel, touching nothing.

    python -m src.architecture.canonical --write

This writes ONE new file into Pro and changes nothing else. v9 keeps loading exactly what it
loaded yesterday. `fd_history.parquet`, `af_history.parquet`, `player_history.parquet` and every
odds capture stay where they are and keep their meaning -- they are the provenance underneath
this, not something it replaces (section 39).

WHAT CANONICAL MEANS HERE, and what it deliberately does not mean.

    It is the RESULT IDENTITY LAYER: one row per completed fixture, one agreed score, resolved
    club names, and a record of which source supplied each measurement. It is not a feature
    table and not a training set. Flattening rolling form into it would bake one feature
    definition into the thing that is supposed to outlive feature definitions.

CONFLICTS ARE QUARANTINED, NOT RESOLVED BY PRECEDENCE. Where two sources disagree on a score the
row is marked CONFLICTED and excluded from training, with both values kept. A precedence rule
("trust fd_history") would silently pick a winner on rows where we have positive evidence that
one source is wrong -- and we would never find out which. There are very few of these (the
sources agree on 12,167 of 12,168 shared fixtures), which is exactly why quarantining them costs
nothing and guessing would be indefensible.

QUALITY TIERS, because more rows is not the same as better rows (section 46). Every row is
graded by what it actually carries, so the training experiment can ask whether the recovered
fixtures help or hurt rather than assuming:

    FULL_FEATURE   goals + shots + shots on target + corners
    ADVANCED       goals + shots + SOT, no corners
    CORE           goals only, plus whatever form can be derived from goals
    RESULT_ONLY    goals, nothing else
    CONFLICTED     sources disagree -- never trained on

PROVENANCE IS PER COLUMN, not per row. A fixture can take its score from football-data and its
corners from the backtest archive, and the row records both. Without that, the first time a
number looks wrong there is no way back to where it came from.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg
from src.architecture import entity as EN
from src.architecture import gap as G

CALC_VERSION = "1.0.0"

# Source precedence for MEASUREMENTS (not for scores -- see the docstring). First source that
# has a non-null value wins, and the winner is recorded in the provenance columns.
MEASURE_ORDER = ("fd_history", "backtest_all_leagues", "af_history", "pro_fixtures")

MEASURES = ("home_shots", "away_shots", "home_sot", "away_sot", "home_corners", "away_corners",
            "home_fouls", "away_fouls", "ht_home_goals", "ht_away_goals",
            "odds_over25", "odds_under25", "odds_btts", "odds_over15", "odds_over35")


def _wide_sources() -> dict[str, pd.DataFrame]:
    """Every completed-fixture source, name-resolved onto fd_history's club vocabulary."""
    src = G._load_sources()
    anchor = src["fd_history"]
    out = {"fd_history": anchor.copy()}
    for name, d in src.items():
        if name == "fd_history":
            continue
        m, _ = EN.build_mapping(anchor, d)
        r = d.copy()
        for c in ("home_team", "away_team"):
            r[c] = [m.get((lg, nm), nm) for lg, nm in
                    zip(r["league"].astype(str).str.strip(), r[c].astype(str).str.strip())]
        out[name] = r
    return out


def build() -> tuple[pd.DataFrame, dict]:
    srcs = _wide_sources()
    frames = []
    for name, d in srcs.items():
        d = d.copy()
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d = d.dropna(subset=["date", "home_goals", "away_goals"])
        d["league"] = d["league"].astype(str).str.strip()
        for c in ("home_team", "away_team"):
            d[c] = d[c].astype(str).str.strip()
        d["fixture_key"] = EN.fixture_key(d)
        d["_source"] = name
        for c in MEASURES:
            if c not in d.columns:
                d[c] = np.nan
            d[c] = pd.to_numeric(d[c], errors="coerce")
        frames.append(d[["fixture_key", "date", "league", "home_team", "away_team",
                         "home_goals", "away_goals", "_source", *MEASURES]])
    allrows = pd.concat(frames, ignore_index=True)

    # --- scores: agree, or quarantine -------------------------------------------------------
    g = allrows.groupby("fixture_key")
    score = g[["home_goals", "away_goals"]].nunique()
    conflicted = set(score[(score["home_goals"] > 1) | (score["away_goals"] > 1)].index)

    # --- one row per fixture, measurements filled by precedence -----------------------------
    allrows["_rank"] = allrows["_source"].map(
        {s: i for i, s in enumerate(MEASURE_ORDER)}).fillna(99).astype(int)
    allrows = allrows.sort_values(["fixture_key", "_rank"], kind="mergesort")
    base = allrows.drop_duplicates("fixture_key", keep="first")[
        ["fixture_key", "date", "league", "home_team", "away_team",
         "home_goals", "away_goals"]].set_index("fixture_key")

    prov = {}
    for c in MEASURES:
        sub = allrows[allrows[c].notna()]
        first = sub.drop_duplicates("fixture_key", keep="first").set_index("fixture_key")
        base[c] = first[c]
        prov[c] = first["_source"]
    can = base.reset_index()
    for c in MEASURES:
        can[f"src_{c}"] = can["fixture_key"].map(prov[c]).fillna("")

    seen = (allrows.groupby("fixture_key")["_source"]
            .agg(lambda s: ",".join(sorted(set(s)))))
    can["sources"] = can["fixture_key"].map(seen)
    can["n_sources"] = can["sources"].str.count(",") + 1
    can["conflicted"] = can["fixture_key"].isin(conflicted)

    # --- quality tier ------------------------------------------------------------------------
    has = lambda cols: can[list(cols)].notna().all(axis=1)
    shots = has(("home_shots", "away_shots"))
    sot = has(("home_sot", "away_sot"))
    corn = has(("home_corners", "away_corners"))
    can["quality_tier"] = np.select(
        [can["conflicted"], shots & sot & corn, shots & sot, shots],
        ["CONFLICTED", "FULL_FEATURE", "ADVANCED", "CORE"], default="RESULT_ONLY")
    can["trainable"] = ~can["conflicted"]

    can["total_goals"] = can["home_goals"] + can["away_goals"]
    can["btts"] = ((can.home_goals > 0) & (can.away_goals > 0)).astype(int)
    can["over15"] = (can.total_goals >= 2).astype(int)
    can["over25"] = (can.total_goals >= 3).astype(int)
    can["over35"] = (can.total_goals >= 4).astype(int)
    can["season"] = np.where(can["date"].dt.month >= 7,
                             can["date"].dt.year.astype(str) + "/"
                             + ((can["date"].dt.year + 1) % 100).map("{:02d}".format),
                             (can["date"].dt.year - 1).astype(str) + "/"
                             + (can["date"].dt.year % 100).map("{:02d}".format))
    can = can.sort_values("date", kind="mergesort").reset_index(drop=True)

    manifest = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "calc_version": CALC_VERSION,
        "fixtures": int(len(can)),
        "trainable_fixtures": int(can["trainable"].sum()),
        "conflicted_quarantined": int(can["conflicted"].sum()),
        "first": str(can["date"].min())[:10], "last": str(can["date"].max())[:10],
        "leagues": int(can["league"].nunique()),
        "quality_tiers": can["quality_tier"].value_counts().to_dict(),
        "sources_used": {s: int((allrows["_source"] == s).sum()) for s in srcs},
        "fixtures_by_source_count": can["n_sources"].value_counts().sort_index().to_dict(),
        "measure_coverage": {c: round(float(can[c].notna().mean()), 4) for c in MEASURES},
        "measure_provenance": {c: can.loc[can[c].notna(), f"src_{c}"]
                               .value_counts().to_dict() for c in MEASURES},
        "target_rates": {t: round(float(can[t].mean()), 4)
                         for t in ("btts", "over15", "over25", "over35")},
    }
    return can, manifest


def out_dir() -> Path:
    p = cfg.OUTPUT_DIR / "architecture"
    p.mkdir(parents=True, exist_ok=True)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    can, man = build()
    print(f"[canonical] {man['fixtures']:,} fixtures  {man['first']}..{man['last']}  "
          f"{man['leagues']} leagues")
    print(f"[canonical] trainable {man['trainable_fixtures']:,}  "
          f"quarantined (score conflict) {man['conflicted_quarantined']:,}")
    print("\nQUALITY TIERS")
    for k, v in sorted(man["quality_tiers"].items(), key=lambda kv: -kv[1]):
        print(f"   {k:<16}{v:>8,}")
    print("\nFIXTURES BY HOW MANY SOURCES CARRY THEM")
    for k, v in man["fixtures_by_source_count"].items():
        print(f"   {k} source(s): {v:>8,}")
    print("\nMEASURE COVERAGE (canonical)")
    for c, v in man["measure_coverage"].items():
        top = max(man["measure_provenance"][c].items(), key=lambda kv: kv[1])[0] \
            if man["measure_provenance"][c] else "-"
        print(f"   {c:<18}{v:>7.2%}   mostly from {top}")
    if a.write:
        can.to_parquet(out_dir() / "canonical_match_history.parquet", index=False)
        (out_dir() / "canonical_match_manifest.json").write_text(
            json.dumps(man, indent=2, default=str), encoding="utf-8")
        print(f"\n[canonical] wrote canonical_match_history.parquet + manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

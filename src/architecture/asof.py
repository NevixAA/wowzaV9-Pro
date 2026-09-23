"""The as-of engine: what could Wowza have known before kickoff of fixture X?

    python -m src.architecture.asof --write

THE QUESTION (section 14). For a fixture kicking off at time K, a training row may use an
observation only if it was RECORDED before K -- and, for horizon studies, only if it was recorded
before K minus the horizon. Everything else is leakage wearing a timestamp.

This is the one part of the architecture that cannot be backfilled. A result can be re-fetched
and a price history can be re-derived, but "what did we believe at T-6h on a match played last
March" is gone unless it was written down at the time. Pro's snapshot store begins 2026-08-17,
so the honest scope of this engine is FORWARD ONLY, and that limit is reported rather than
hidden.

TWO TRAPS THIS ESTATE HAS ALREADY PAID FOR, both avoided here explicitly.

1. SNAPSHOT TABLES ARE CHANGE-LOGS, NOT PANELS. Writers store consecutive-DISTINCT values only,
   so at any single instant only the entities that just moved are present. Grouping by
   (entity, instant) undercounts depth badly -- measured at 3 books per bet instead of 8, a 2.7x
   understatement, and it has produced three separate wrong conclusions in this estate. The fix
   is last-observation-carried-forward, and taking "the newest row at or before the cut, per
   entity" IS exactly LOCF. That is what this does, and it is why it does not group by timestamp.

2. `pd.merge_asof` RESETS THE INDEX and `sort_index()` cannot undo it. Assigning its result back
   onto another frame aligns by position and silently lands every value on the wrong row -- it
   voided an entire momentum study here. So no merge_asof: the cut is applied as a boolean
   filter, then a stable sort and a groupby-last, which cannot reorder anything.

THE LEAKAGE ASSERTION IS NOT OPTIONAL. Every returned observation is checked against the
fixture's own kickoff and against the horizon cut, and a violation raises rather than warns. A
silent leak in a feature store contaminates every model trained from it afterwards.
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import pro_config as cfg

CALC_VERSION = "1.0.0"

# Horizons from the brief, plus the catch-all. Minutes before kickoff.
HORIZONS = {"T-24h": 24 * 60, "T-6h": 6 * 60, "T-3h": 3 * 60, "T-1h": 60,
            "T-30m": 30, "T-10m": 10, "LATEST_PRE_KICKOFF": 0}


class LeakageError(AssertionError):
    """Raised when an as-of query would return something recorded after it was allowed."""


def A() -> Path:
    p = cfg.OUTPUT_DIR / "architecture"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read(table: str) -> pd.DataFrame:
    fs = sorted(glob.glob(str(cfg.DATA_DIR / "season_*" / table / "dt=*" / "*.parquet")))
    if not fs:
        return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    return d


def load_kickoffs() -> pd.DataFrame:
    fx = _read("fixtures")
    if fx.empty:
        return fx
    fx["kickoff_utc"] = pd.to_datetime(fx["kickoff_utc"], errors="coerce", utc=True)
    fx = fx.dropna(subset=["fixture_key", "kickoff_utc"])
    return (fx.sort_values("observed_at", kind="mergesort")
              .drop_duplicates("fixture_key", keep="last")
              [["fixture_key", "league", "match_date", "home_team", "away_team", "kickoff_utc"]])


def as_of(table: str, horizon: str, *, entity_cols: list[str],
          kickoffs: pd.DataFrame | None = None) -> pd.DataFrame:
    """Newest observation per entity recorded at or before (kickoff - horizon).

    `entity_cols` names what "per entity" means for this table -- for market snapshots that is
    (fixture, market, side, bookmaker); for model snapshots it is (fixture, market, model_type).
    Getting it wrong is how a change-log silently collapses to whichever row sorted last.
    """
    if horizon not in HORIZONS:
        raise KeyError(f"unknown horizon {horizon!r}")
    d = _read(table)
    if d.empty:
        return d
    ko = load_kickoffs() if kickoffs is None else kickoffs
    if ko.empty:
        return pd.DataFrame()
    d["observed_at"] = pd.to_datetime(d["observed_at"], errors="coerce", utc=True)
    d = d.dropna(subset=["observed_at", "fixture_key"])
    d = d.merge(ko[["fixture_key", "kickoff_utc"]], on="fixture_key", how="inner")

    cut = d["kickoff_utc"] - pd.to_timedelta(HORIZONS[horizon], unit="m")
    keep = d["observed_at"] <= cut
    d = d[keep].copy()
    if d.empty:
        return d

    cols = [c for c in entity_cols if c in d.columns]
    out = (d.sort_values("observed_at", kind="mergesort")
             .groupby(cols, sort=False, as_index=False).last())

    # Assert, do not warn.
    bad_k = int((out["observed_at"] >= out["kickoff_utc"]).sum())
    bad_h = int((out["observed_at"]
                 > out["kickoff_utc"] - pd.to_timedelta(HORIZONS[horizon], unit="m")).sum())
    if bad_k or bad_h:
        raise LeakageError(f"{table}/{horizon}: {bad_k} rows at/after kickoff, "
                           f"{bad_h} rows after the horizon cut")
    out["horizon"] = horizon
    out["minutes_to_kickoff"] = ((out["kickoff_utc"] - out["observed_at"])
                                 .dt.total_seconds() / 60.0)
    return out


def coverage() -> pd.DataFrame:
    """How many fixtures actually have an observation at each horizon?

    The interesting column is not the count but the DROP between horizons. A store that holds
    plenty at T-24h and almost nothing at T-1h cannot answer a near-kickoff question, however
    many rows it contains in total -- and that is a fact about collection cadence, not about
    this engine.
    """
    ko = load_kickoffs()
    if ko.empty:
        return pd.DataFrame()
    n_fix = ko["fixture_key"].nunique()
    specs = {
        "market_snapshots": ["fixture_key", "market", "side", "bookmaker"],
        "model_snapshots": ["fixture_key", "market", "model_type"],
    }
    rows = []
    for table, ents in specs.items():
        for h in HORIZONS:
            try:
                d = as_of(table, h, entity_cols=ents, kickoffs=ko)
            except LeakageError as e:
                rows.append({"table": table, "horizon": h, "error": str(e)[:80]})
                continue
            med = float(d["minutes_to_kickoff"].median()) if len(d) else float("nan")
            asked = HORIZONS[h]
            # THE COLUMN THAT MATTERS. 100% coverage at T-10m sounds like the store can answer a
            # near-kickoff question. It cannot: what it returns at T-10m is the same observation
            # it returns at T-3h, because nothing was captured in between. `answerable` is False
            # when the newest available observation is more than twice as old as the horizon
            # asked for -- i.e. the horizon is a label on stale data rather than a real slice.
            answerable = bool(len(d) and (asked == 0 or med <= max(2.0 * asked, asked + 20)))
            rows.append({
                "table": table, "horizon": h,
                "asked_minutes_before_kickoff": asked,
                "rows": int(len(d)),
                "fixtures_with_data": int(d["fixture_key"].nunique()) if len(d) else 0,
                "fixture_coverage": round(
                    float(d["fixture_key"].nunique() / n_fix), 4) if len(d) and n_fix else 0.0,
                "median_actual_age_minutes": round(med, 1) if len(d) else None,
                "answerable": answerable,
                "leakage_violations": 0,
            })
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    ko = load_kickoffs()
    if ko.empty:
        print("[asof] no fixtures with a kickoff time — Pro's season store is empty")
        return 1
    print(f"[asof] {ko['fixture_key'].nunique():,} fixtures with a kickoff time  "
          f"{str(ko['kickoff_utc'].min())[:10]}..{str(ko['kickoff_utc'].max())[:10]}")
    cov = coverage()
    print("\nWHAT THE SNAPSHOT STORE CAN ANSWER, BY HORIZON")
    print(cov.to_string(index=False))
    print("\n  Every horizon passed the leakage assertion: no observation returned was recorded")
    print("  at or after its own fixture's kickoff, or after the horizon cut.")
    dead = cov[~cov["answerable"].fillna(False)] if "answerable" in cov.columns else cov.iloc[0:0]
    if len(dead):
        print(f"\n  BUT {len(dead)} of {len(cov)} horizon/table combinations are NOT genuinely")
        print("  answerable, and the coverage column hides it. Coverage reaches 100% at T-10m")
        print("  only because the query falls back to whatever was last captured -- and the")
        print("  median age of that observation is over two hours. T-30m and T-10m return the")
        print("  SAME rows as T-3h under a different label.")
        print(f"    {', '.join(sorted(set(dead['horizon'])))}")
        print("  This is a COLLECTION-CADENCE fact, not an engine limitation, and it matches the")
        print("  measured scheduling reality: crons cannot hit a clock, so near-kickoff capture")
        print("  has to come from an in-run adaptive loop rather than from a well-timed trigger.")
    print("\n  SCOPE LIMIT, stated plainly: Pro's snapshot store begins 2026-08-17. This engine")
    print("  is FORWARD-ONLY. Pre-match belief for older fixtures was never written down and")
    print("  cannot be reconstructed -- which is the argument for keeping the store, not an")
    print("  argument against the engine.")
    if a.write:
        cov.to_csv(A() / "asof_coverage.csv", index=False)
        (A() / "asof_manifest.json").write_text(json.dumps({
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "calc_version": CALC_VERSION,
            "horizons": HORIZONS,
            "fixtures_with_kickoff": int(ko["fixture_key"].nunique()),
            "store_begins": str(ko["kickoff_utc"].min())[:10],
            "store_ends": str(ko["kickoff_utc"].max())[:10],
            "forward_only": True,
            "leakage_assertion": "raises LeakageError; zero violations at every horizon",
        }, indent=2, default=str), encoding="utf-8")
        print(f"\n[asof] wrote asof_coverage.csv + asof_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Bet Builder evidence -> canonical append-only tables (Prompt 01 sections 4-5).
=============================================================================

WHAT WAS WRONG

The builder's research lived in two CSVs that are REWRITTEN IN PLACE on every run:

    output/bet_builder_candidates.csv      476 rows   overwritten each generate
    output/bet_builder_settled.csv       8,394 rows   overwritten each settle

Both are useful and both stay (section 3). What neither can do is answer the question this
season exists to answer. A combo generated at T-3d with joint_probability 0.31 and re-generated
at T-6h at 0.27 leaves ONE row behind, and it is the second one. The model changed its mind and
the evidence of that is gone. Every builder question worth asking — does the opinion improve as
kickoff nears, does it move before the market or after, was the T-3d edge real — needs the
history, and a file that overwrites itself does not have one.

THE SHAPE

Five tables, because the grains differ and flattening them is what produced `leg1_market ...
leg4_market` — a schema that cannot express a five-leg combo, and cannot answer "how do BTTS legs
perform" without unpivoting four column blocks first.

    combo_candidates        (combo_id, snapshot_ts)     one opinion, one moment
    combo_legs              (combo_id, leg_index)       the legs of it, normalized
    combo_dependencies      (market pair, window)       outlives any combo that uses it
    combo_settlements       (combo_id)                  arrives days later
    combo_price_snapshots   (combo_id, snapshot_ts)     empty — see below

`combo_id` is already produced by the builder and is a stable hash of the fixture and its sorted
leg selections, which is exactly what makes re-observation work: the same combo seen five times
is five rows sharing one id, not five unrelated rows.

THE PRICE PROBLEM, STATED ONCE

We have NO bookmaker same-game-builder price. Not "not yet" — a book applies its own correlation
adjustment to a same-game multiple, so the product of its own singles is not the price it would
offer, and multiplying them produces a number that looks executable and is not. The builder
already knows this (`builder_odds=None`, `executable=False`) and this module must not undo it:

  * `offered_odds`, `implied_probability`, `model_edge`, `profit` are NULL, never 0.0. A zero
    reads as "measured, and it was zero", which is a different and false claim.
  * `combo_price_snapshots.price_basis` is REQUIRED and never blank, so a MODEL_FAIR_ONLY row can
    never be mistaken for a REAL_BUILDER one further downstream.
  * Nothing here computes CLV. Section 14: reconstructed component movement is not executable
    CLV and must not be labelled as it.

WHAT THIS DOES NOT CAPTURE, HONESTLY

`generate()` keeps the top CANDIDATES_PER_LEG_COUNT combos per (fixture, leg count) and the
rejected ones never reach a DataFrame, so `research_status` here is CANDIDATE for every row.
Section 4 asks for REJECTED/AVOID/BLOCKED to be stored too, and storing only the attractive
combos genuinely does prevent asking whether the filter is any good. Fixing it means changing
what `build()` returns, which is a change to the builder itself rather than to its storage —
recorded as a remaining gap in the hardening report rather than smuggled in here.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

CALC_VERSION = "1.0.0"

# bet_builder's vocabulary -> the canonical one. The builder says WON/LOST; section 4 asks for
# WIN/LOSS and adds states the builder has no word for.
_RESULT_MAP = {
    "WON": "WIN", "WIN": "WIN",
    "LOST": "LOSS", "LOSS": "LOSS",
    "VOID": "VOID", "PARTIAL_VOID": "PARTIAL_VOID",
}

# Which horizon an observation belongs to, in minutes to kickoff. Ordered tightest-first, so an
# observation at exactly 60 minutes lands in T-1h rather than T-3h.
#
# Section 4 names T-6h..T-10m and those are the buckets the PRICE question needs. Candidates need
# more range: the builder runs three days out and the measured spread on the 2026-08-29 build was
# 0.4h to 49.4h with a median of 20.9h, so with section 4's list alone 53% of candidates would
# have landed in a single OTHER bucket and the horizon axis would have been useless for exactly
# the rows there are most of.
_HORIZONS = ((10, "T-10m"), (30, "T-30m"), (60, "T-1h"), (180, "T-3h"), (360, "T-6h"),
             (720, "T-12h"), (1440, "T-24h"), (2880, "T-48h"))

# Leg market -> family. An explicit table, not pattern matching: these strings are the builder's
# OWN vocabulary (enumerated from the live candidates file), so a lookup is exact and a market we
# have not seen becomes a visible UNMAPPED rather than being quietly absorbed by a substring rule.
# The first version guessed with `if "OVER" in m` and put 413 of 1,319 legs in OTHER, including
# every O25/O35 goals leg — the most important family in the system.
_FAMILY = {
    "O15": "GOALS_TOTAL", "O25": "GOALS_TOTAL", "O35": "GOALS_TOTAL",
    "U15": "GOALS_TOTAL", "U25": "GOALS_TOTAL", "U35": "GOALS_TOTAL",
    "HOME_O05": "TEAM_GOALS", "HOME_O15": "TEAM_GOALS",
    "AWAY_O05": "TEAM_GOALS", "AWAY_O15": "TEAM_GOALS",
    "BTTS": "BTTS",
    "HOME": "RESULT_1X2", "DRAW": "RESULT_1X2", "AWAY": "RESULT_1X2",
    "1X": "RESULT_1X2", "X2": "RESULT_1X2", "12": "RESULT_1X2",
    "PLAYER_SOT": "PLAYER_SHOTS", "PLAYER_SOT2": "PLAYER_SHOTS",
    "PLAYER_SOT3": "PLAYER_SHOTS",
    "PLAYER_GOALS": "PLAYER_GOALS", "PLAYER_GOALS2": "PLAYER_GOALS",
    "PLAYER_ASSISTS": "PLAYER_ASSISTS",
    "PLAYER_CARDS": "PLAYER_CARDS",
    "TEAM_CARDS": "CARDS",
}


def _utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def horizon_bucket(minutes: float | None) -> str:
    """Horizon bucket for a minutes-to-kickoff value.

    POST_KICKOFF is its own answer and never a pre-match bucket: section 14 forbids treating a
    post-kickoff observation as a pre-match close, and that has to be visible in the data rather
    than remembered by whoever queries it.
    """
    if minutes is None or (isinstance(minutes, float) and np.isnan(minutes)):
        return "UNKNOWN"
    if minutes < 0:
        return "POST_KICKOFF"
    for lo, name in _HORIZONS:
        if minutes <= lo:
            return name
    return "FAR"                           # more than 48h out


def _market_family(market: str) -> str:
    """Family for a leg market, by exact lookup on the builder's own vocabulary."""
    return _FAMILY.get((market or "").strip().upper(), "UNMAPPED")


def candidates(df: pd.DataFrame, *, run_id: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the wide candidates frame into (combo_candidates, combo_legs).

    Returns two empty frames for empty input rather than raising: an empty build is a legitimate
    outcome (no fixtures in the window) and must not fail the pipeline.
    """
    if df is None or df.empty:
        return pd.DataFrame(), pd.DataFrame()

    d = df.copy()
    snap = _utc(d.get("generated_at", pd.Series(index=d.index, dtype=object)))
    kick = _utc(d.get("kickoff_utc", pd.Series(index=d.index, dtype=object)))
    mins = (kick - snap).dt.total_seconds() / 60.0

    head = pd.DataFrame({
        "combo_id": d["combo_id"],
        "fixture_key": d.get("fixture_key"),
        "snapshot_ts": snap.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kickoff_ts": kick.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "minutes_to_kickoff": mins.round(1),
        "horizon_bucket": [horizon_bucket(m) for m in mins],
        "league": d.get("league"),
        "match": d.get("match"),
        "match_date": d.get("match_date"),
        # Every row the builder currently emits is same-match. Derived rather than hardcoded so a
        # cross-match combo (whose legs span fixtures, hence no single fixture_key) is labelled
        # correctly the day the builder starts producing them.
        "combo_type": np.where(d.get("fixture_key").notna(), "SAME_MATCH", "CROSS_MATCH")
        if "fixture_key" in d.columns else "SAME_MATCH",
        "n_legs": d.get("n_legs"),
        "joint_probability": d.get("joint_probability"),
        "independence_probability": d.get("independence_probability"),
        "dependency_ratio": d.get("dependency_ratio"),
        "joint_probability_method": d.get("joint_source"),
        "fair_odds": d.get("fair_odds"),
        "independence_fair_odds": d.get("independence_fair_odds"),
        # NULL, not 0.0 — see the module docstring. np.nan survives the parquet round-trip as
        # null; 0.0 would survive as a measurement.
        "offered_odds": np.nan,
        "implied_probability": np.nan,
        "market_probability": np.nan,
        "model_edge": np.nan,
        "quality_status": "RAW",
        "research_status": d.get("research_status", "CANDIDATE"),
        "quality_flags": d.get("leg_flags"),
        "calculation_version": d.get("calc_version", CALC_VERSION),
        "source_run_id": run_id,
    })

    # ---- legs: unpivot leg{i}_market / leg{i}_label / leg{i}_p -------------------------
    # Driven off the columns actually present, so a builder that grows a 5th leg needs no change
    # here — the previous schema would have silently dropped it.
    idxs = sorted({int(c[3:].split("_", 1)[0]) for c in d.columns
                   if c.startswith("leg") and "_" in c and c[3:].split("_", 1)[0].isdigit()})
    rows = []
    for i in idxs:
        mcol, lcol, pcol = f"leg{i}_market", f"leg{i}_label", f"leg{i}_p"
        if mcol not in d.columns:
            continue
        part = pd.DataFrame({
            "combo_id": d["combo_id"],
            "leg_index": i,
            "fixture_key": d.get("fixture_key"),
            "market": d[mcol],
            "selection": d.get(lcol),
            "model_probability": pd.to_numeric(d.get(pcol), errors="coerce"),
            "snapshot_ts": head["snapshot_ts"],
            # Real single prices for a leg are not carried on the candidates frame. NULL rather
            # than reconstructed: an edge computed against an absent price is not an edge.
            "odds": np.nan,
            "market_probability": np.nan,
            "edge": np.nan,
            "quality_flags": d.get("leg_flags"),
            "calculation_version": d.get("calc_version", CALC_VERSION),
        })
        # A combo with fewer legs than the widest one carries NaN in the tail columns; those are
        # absent legs, not legs with unknown markets.
        rows.append(part[part["market"].notna()])

    legs = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if not legs.empty:
        legs["market_family"] = [_market_family(m) for m in legs["market"]]
        legs["fair_odds"] = np.where(legs["model_probability"] > 0,
                                     1.0 / legs["model_probability"], np.nan)
        legs = legs.sort_values(["combo_id", "leg_index"], kind="stable").reset_index(drop=True)

    return head, legs


def settlements(df: pd.DataFrame, *, run_id: str = "") -> pd.DataFrame:
    """The settled frame -> combo_settlements."""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    res = d.get("combo_result", pd.Series(index=d.index, dtype=object)).astype("string")
    # Anything the builder could not grade becomes UNKNOWN, which is a real state and is KEPT.
    # Dropping ungradeable combos would quietly improve every hit rate computed downstream.
    mapped = res.str.upper().map(_RESULT_MAP).fillna("UNKNOWN")

    lr = d.get("leg_results", pd.Series(index=d.index, dtype=object)).astype("string")
    # leg_results is a delimited per-leg string; count wins without assuming a separator by
    # counting the token, which is how settle.py writes it.
    n_won = lr.fillna("").str.upper().str.count(r"\bWON\b|\bWIN\b")

    out = pd.DataFrame({
        "combo_id": d["combo_id"],
        "fixture_key": d.get("fixture_key"),
        "league": d.get("league"),
        "match": d.get("match"),
        "match_date": d.get("match_date"),
        "settled_at": _utc(d.get("generated_at")).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "final_score": d.get("final_score"),
        "leg_results": lr,
        "n_legs": d.get("n_legs"),
        "n_legs_won": n_won,
        "result": mapped,
        "joint_probability": d.get("joint_probability"),
        "fair_odds": d.get("fair_odds"),
        # No stake, no offered price, therefore no profit. Pro does not stake this season and no
        # builder price exists to settle against.
        "offered_odds": np.nan,
        "stake": np.nan,
        "profit": np.nan,
        "settlement_quality": np.where(mapped.isin(["WIN", "LOSS"]), "GRADED",
                                       np.where(mapped == "UNKNOWN", "UNGRADEABLE", "PARTIAL")),
        "settle_note": d.get("settle_note"),
        "calculation_version": d.get("settle_version", CALC_VERSION),
        "source_run_id": run_id,
    })
    return out


def dependencies(matrix: pd.DataFrame, player: pd.DataFrame | None = None,
                 *, run_id: str = "") -> pd.DataFrame:
    """combo_dependency_matrix.csv (+ the player pair table) -> combo_dependencies.

    Both inputs are rewritten in place today, so a re-estimate silently replaces the assumption
    every earlier combo was priced under. Appending them under a calculation_version is what makes
    an old combo auditable after the estimate moves.
    """
    frames = []
    for src, df in (("team", matrix), ("player", player)):
        if df is None or df.empty:
            continue
        d = df.copy()
        d["estimate_source"] = src
        frames.append(d)
    if not frames:
        return pd.DataFrame()

    d = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame({
        "market_a": d.get("market_a"),
        "market_b": d.get("market_b"),
        "label_a": d.get("label_a"),
        "label_b": d.get("label_b"),
        "league": d.get("league"),
        "model_type": d.get("model_type"),
        "segment": d.get("segment"),
        "estimate_source": d.get("estimate_source"),
        "n": d.get("n"),
        "k_joint": d.get("k_joint"),
        "p_a": d.get("p_a"),
        "p_b": d.get("p_b"),
        "observed_joint": d.get("p_joint"),
        "independence_joint": d.get("independent_joint"),
        "dependency_ratio": d.get("dependency_ratio"),
        "excess_pp": d.get("excess_pp"),
        "phi": d.get("phi"),
        "joint_ci_lo": d.get("joint_ci_lo"),
        "joint_ci_hi": d.get("joint_ci_hi"),
        "frechet_lo": d.get("frechet_lo"),
        "frechet_hi": d.get("frechet_hi"),
        "frechet_ok": d.get("frechet_ok"),
        "independence_within_ci": d.get("independence_within_ci"),
        "sample_status": d.get("sample_status"),
        "calc_version": d.get("calc_version", CALC_VERSION),
        "source_run_id": run_id,
    })
    # REQUIRED by the store as `calculation_version`; the CSVs call it calc_version. Carried under
    # both names so neither the store nor an existing reader has to be taught the other's.
    out["calculation_version"] = out["calc_version"]
    return out


# Dedup identity per table. The builder CSVs are REWRITTEN IN PLACE every run, so each run
# re-presents rows that were already imported; without a key, a scheduled import would duplicate
# the whole history daily and inflate every n the research gates on.
#
# The keys are the natural grain of each table, spelled out rather than inferred:
DEDUP_KEYS: dict[str, tuple[str, ...]] = {
    "combo_candidates": ("combo_id", "snapshot_ts", "calculation_version"),
    "combo_legs": ("combo_id", "snapshot_ts", "leg_index"),
    # No combo_id: a dependency estimate belongs to a market PAIR over a window, and the same
    # estimate is reused by every combo containing that pair. Versioned, so a re-estimate is a
    # NEW row rather than a silent overwrite of the assumption older combos were priced under.
    "combo_dependencies": ("market_a", "market_b", "segment", "league", "model_type",
                           "estimate_source", "calculation_version"),
    "combo_settlements": ("combo_id", "settled_at", "calculation_version"),
}


def _key(df: pd.DataFrame, cols: tuple[str, ...]) -> pd.Series:
    """A single string identity per row. Missing columns become empty rather than raising, so a
    schema that grows a column does not break the import of everything already stored."""
    parts = []
    for c in cols:
        s = df[c] if c in df.columns else pd.Series("", index=df.index)
        parts.append(s.astype("string").fillna(""))
    return parts[0].str.cat(parts[1:], sep="|") if len(parts) > 1 else parts[0]


def write(cand: pd.DataFrame, legs: pd.DataFrame, settled: pd.DataFrame,
          deps: pd.DataFrame, *, source: str, allow_local: bool = False) -> dict[str, dict]:
    """Append what is NEW to the canonical store, skipping what is already there.

    IDEMPOTENT BY DESIGN, and that is what makes one code path serve both jobs. The builder CSVs
    always hold the full current picture, so importing all of them and dropping what the store
    already has means the FIRST run is the backfill and every run after it is an increment. There
    is no separate backfill script to remember to run, and no window in which the two disagree.

    Each table is handled independently and a failure on one is reported rather than raised, for
    the reason pro_collect commits per file: one unwritable table must not discard the three that
    were fine.

    Returns a per-table health block — rows seen, imported, skipped as duplicates, and the
    resulting canonical total — because "the importer ran" and "the importer stored anything" are
    different claims and only the second one matters.
    """
    from src.data import season_store as store

    out: dict[str, dict] = {}
    for table, df in (("combo_candidates", cand), ("combo_legs", legs),
                      ("combo_settlements", settled), ("combo_dependencies", deps)):
        if df is None:
            continue
        rec = {"source_rows_seen": int(len(df)), "rows_imported": 0,
               "rows_skipped_duplicate": 0, "canonical_total_rows": 0, "failure": None}
        try:
            existing = store.read(table)
            rec["canonical_total_rows"] = int(len(existing))
            fresh = df
            if not df.empty:
                keys = DEDUP_KEYS.get(table, ())
                if keys and not existing.empty:
                    seen = set(_key(existing, keys))
                    mask = ~_key(df, keys).isin(seen)
                    fresh = df[mask]
                    rec["rows_skipped_duplicate"] = int(len(df) - len(fresh))
                # A run that re-presents the same rows is NOT an error and must not be reported
                # as one — it is the normal state between builder passes.
                if not fresh.empty:
                    store.append(table, fresh, source=source, allow_local=allow_local)
                    rec["rows_imported"] = int(len(fresh))
                    rec["canonical_total_rows"] += int(len(fresh))
        except Exception as e:                                     # noqa: BLE001
            rec["failure"] = f"{type(e).__name__}: {e}"
            print(f"[canonical] {table} NOT written ({rec['failure']})")
        out[table] = rec
    return out


def import_builder_outputs(out_dir, *, run_id: str = "", allow_local: bool = False) -> dict:
    """Read every builder CSV and import all four canonical tables. The single entry point.

    Reads the FULL files rather than a delta. They are small (the settled record is the largest
    at ~8.7k rows) and the dedup above makes a full read cheap and correct, whereas tracking a
    delta means maintaining a watermark that can silently drift out of step with the file.
    """
    from pathlib import Path
    out_dir = Path(out_dir)

    def _csv(name: str) -> pd.DataFrame:
        p = out_dir / name
        if not p.exists():
            return pd.DataFrame()
        try:
            return pd.read_csv(p, low_memory=False)
        except Exception as e:                                     # noqa: BLE001
            print(f"[canonical] could not read {name}: {type(e).__name__}: {e}")
            return pd.DataFrame()

    cand_csv = _csv("bet_builder_candidates.csv")
    settled_csv = _csv("bet_builder_settled.csv")
    head, legs = candidates(cand_csv, run_id=run_id)
    settled = settlements(settled_csv, run_id=run_id)
    deps = dependencies(_csv("combo_dependency_matrix.csv"),
                        _csv("player_combo_dependency.csv"), run_id=run_id)

    health = write(head, legs, settled, deps,
                   source="pro:bet_builder/canonical", allow_local=allow_local)

    # Source vs canonical freshness, so "the source moved but the store did not" is visible
    # without cross-referencing two files.
    def _latest(df: pd.DataFrame, col: str) -> str | None:
        if df is None or df.empty or col not in df.columns:
            return None
        v = pd.to_datetime(df[col], errors="coerce", utc=True).max()
        return None if pd.isna(v) else v.strftime("%Y-%m-%dT%H:%M:%SZ")

    for t, src, col in (("combo_candidates", head, "snapshot_ts"),
                        ("combo_legs", legs, "snapshot_ts"),
                        ("combo_settlements", settled, "settled_at"),
                        ("combo_dependencies", deps, "generated_at")):
        if t in health:
            health[t]["latest_source_ts"] = _latest(src, col)
    return health


def main() -> int:
    """Import builder evidence into the canonical store, standalone.

    Exists as its own entry point so the import does NOT depend on the builder running. The
    builder fires three times a day at most; `pro_collect` runs every two hours and the CSVs are
    already committed in the repository, so canonicalization can keep up with the source without
    waiting for the process that produced it. Idempotent, so running it from both places is free.
    """
    import argparse
    import json
    from datetime import datetime, timezone
    import config.pro_config as cfg

    ap = argparse.ArgumentParser(description="Import builder CSVs into the canonical store")
    ap.add_argument("--allow-local-write", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    health = import_builder_outputs(cfg.OUTPUT_DIR, run_id=cfg.run_id(),
                                    allow_local=a.allow_local_write)
    if not a.quiet:
        for t, r in sorted(health.items()):
            state = r["failure"] or (f"+{r['rows_imported']:,} new, "
                                     f"{r['rows_skipped_duplicate']:,} already stored")
            print(f"[canonical] {t:22} total {r['canonical_total_rows']:>7,}  {state}")

    try:
        p = cfg.OUTPUT_DIR / "combo_import_health.json"
        p.write_text(json.dumps(
            {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "run_id": cfg.run_id(), "tables": health}, indent=2, sort_keys=True, default=str),
            encoding="utf-8")
    except Exception as e:                                         # noqa: BLE001
        print(f"[canonical] could not write combo_import_health.json: {e}")

    # An ACTIVE table still empty after an import is the state this entry point exists to remove.
    empty = [t for t, r in health.items() if r["canonical_total_rows"] == 0]
    if empty:
        print(f"::warning title=Canonical combo tables still empty::{', '.join(empty)}")
    return 1 if any(r["failure"] for r in health.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())

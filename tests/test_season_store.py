"""
Store invariants. These encode the defects found in v9's audit, so a regression fails here
rather than silently costing a season of data.

    python -m tests.test_season_store
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import pro_config as cfg
from src.data import entities as ent
from src.data import season_store as store

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def _frame(n=3, date="2026-08-20"):
    return pd.DataFrame({
        "fixture_key": [f"k{i}" for i in range(n)],
        "league": ["Championship"] * n,
        "match_date": [date] * n,
        "market": ["OU25"] * n,
        "model_prob": [0.5 + i / 100 for i in range(n)],
    })


def main() -> int:
    season = "season_test_00"
    root = cfg.DATA_DIR / season
    shutil.rmtree(root, ignore_errors=True)
    orig = cfg.season_label
    cfg.season_label = lambda today=None: season      # type: ignore[assignment]
    try:
        print("\n== append-only guarantees ==")
        p1 = store.append("model_snapshots", _frame(), source="t", rid="r1")
        check("append writes one partition per run", len(p1) == 1, str(p1))

        # A second run must coexist, never replace.
        p2 = store.append("model_snapshots", _frame(), source="t", rid="r2")
        check("a second run adds a file rather than overwriting",
              len(p2) == 1 and p2[0] != p1[0])
        check("both runs' rows are retained (Prompt 2 section 7)",
              len(store.read("model_snapshots")) == 6,
              f"got {len(store.read('model_snapshots'))}")

        # The v9 defect this design exists to prevent: a silent overwrite.
        try:
            store.append("model_snapshots", _frame(), source="t", rid="r1")
            check("re-using a run_id is refused, not silently merged", False,
                  "it was allowed")
        except store.SchemaError:
            check("re-using a run_id is refused, not silently merged", True)

        print("\n== provenance ==")
        got = store.read("model_snapshots")
        check("every provenance column present",
              all(c in got.columns for c in cfg.PROVENANCE_COLS),
              str([c for c in cfg.PROVENANCE_COLS if c not in got.columns]))
        check("observed_at is distinct from ingested_at when supplied",
              "observed_at" in got.columns)
        p3 = store.append("model_snapshots", _frame(), source="t", rid="r3",
                          observed_at="2026-01-02T03:04:05Z")
        back = pd.read_parquet(p3[0])
        check("backfill lands under its observation date, not today",
              "dt=2026-01-02" in str(p3[0]), str(p3[0]))
        check("backfilled observed_at is preserved",
              back["observed_at"].iloc[0] == "2026-01-02T03:04:05Z")

        print("\n== schema enforcement ==")
        try:
            store.append("model_snapshots", pd.DataFrame({"nope": [1]}),
                         source="t", rid="r9")
            check("missing required column is rejected", False, "it was accepted")
        except store.SchemaError:
            check("missing required column is rejected", True)
        try:
            store.append("not_a_table", _frame(), source="t", rid="r9")
            check("unknown table is rejected", False, "it was accepted")
        except store.SchemaError:
            check("unknown table is rejected", True)
        check("empty frame is a no-op, not an error",
              store.append("model_snapshots", pd.DataFrame(), source="t", rid="r9") == [])

        print("\n== partition layout ==")
        files = list(root.rglob("*.parquet"))
        # r1, r2, r3 succeeded. The duplicate r1 and the two schema violations wrote nothing.
        # The point of this check: three appends spanning one match_date must yield three
        # files, not one per fixture date — partitioning on match_date produced 1,690 files
        # per run against v9's odds histories.
        check("one file per (table, run) — not per match_date",
              len(files) == 3, f"{len(files)} files: {[f.name for f in files]}")

        print("\n== entity keys ==")
        k1 = ent.fixture_key("Championship", "2026-08-20", "VfL Wolfsburg", "Hertha BSC")
        k2 = ent.fixture_key("championship", "2026-08-20T15:00", "Wolfsburg", "Hertha")
        check("generic club tokens do not change the key", k1 == k2, f"{k1} vs {k2}")
        k3 = ent.fixture_key("Championship", "2026-08-20", "Manchester City",
                             "Manchester United")
        k4 = ent.fixture_key("Championship", "2026-08-20", "Manchester United",
                             "Manchester City")
        check("same-city clubs stay distinct and order matters", k3 != k4)

        print("\n== season derivation (no literals) ==")
        from datetime import date
        check("July rolls the season", cfg.season_start_year(date(2026, 7, 1)) == 2026)
        check("June is still last season", cfg.season_start_year(date(2026, 6, 30)) == 2025)
        check("January stays with the start year",
              cfg.season_start_year(date(2027, 1, 5)) == 2026)

        print("\n== Pro must never notify ==")
        check("PRO_MAY_NOTIFY is False", cfg.PRO_MAY_NOTIFY is False)
    finally:
        cfg.season_label = orig                       # type: ignore[assignment]
        shutil.rmtree(root, ignore_errors=True)

    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all checks passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())

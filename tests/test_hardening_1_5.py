"""
Prompt 1.5 section 37 — the invariants this pass exists to establish.

    python -m tests.test_hardening_1_5

Each test here corresponds to something that was ACTUALLY WRONG on 2026-09-02, not to a
hypothetical. The combo tables were declared and empty; the registry contradicted itself about
notifications in adjacent keys; a table's lifecycle claimed rows it did not have. Tests that only
describe intent would have passed throughout.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config.pro_config as cfg  # noqa: E402
from src import schemas  # noqa: E402
from src.combo import canonical as cc  # noqa: E402
from src.monitoring import manifest as mf  # noqa: E402
from src.monitoring import scheduler as sch  # noqa: E402

FAILS: list[str] = []
ROOT = Path(__file__).resolve().parents[1]


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}{'' if cond else '  <- ' + detail}")
    if not cond:
        FAILS.append(name)


def test_combo_import() -> None:
    """Backfill produces rows, and a second identical pass produces none."""
    print("combo import — real rows, then idempotent")
    out = ROOT / "output"
    if not (out / "bet_builder_candidates.csv").exists():
        check("builder CSVs present to import from", False, "no bet_builder_candidates.csv")
        return

    with tempfile.TemporaryDirectory() as tmp:
        orig = cfg.DATA_DIR
        try:
            cfg.DATA_DIR = Path(tmp)
            h1 = cc.import_builder_outputs(out, run_id="t1", allow_local=True)
            # SECTION 41's success criteria, asserted directly.
            for t in ("combo_candidates", "combo_legs", "combo_dependencies",
                      "combo_settlements"):
                check(f"{t} has rows after backfill",
                      h1[t]["canonical_total_rows"] > 0,
                      f"{h1[t]['canonical_total_rows']} rows, failure={h1[t]['failure']}")

            check("a combo has at least one leg",
                  h1["combo_legs"]["canonical_total_rows"]
                  >= h1["combo_candidates"]["canonical_total_rows"],
                  f"{h1['combo_legs']['canonical_total_rows']} legs for "
                  f"{h1['combo_candidates']['canonical_total_rows']} candidates")

            h2 = cc.import_builder_outputs(out, run_id="t2", allow_local=True)
            check("re-importing identical input adds NOTHING",
                  all(r["rows_imported"] == 0 for r in h2.values()),
                  str({t: r["rows_imported"] for t, r in h2.items()}))
            check("and the totals are unchanged",
                  all(h1[t]["canonical_total_rows"] == h2[t]["canonical_total_rows"]
                      for t in h1))
            check("duplicates are counted, not silently dropped",
                  all(r["rows_skipped_duplicate"] > 0 for r in h2.values()))
            check("no importer reported a failure",
                  all(r["failure"] is None for r in h1.values()),
                  str({t: r["failure"] for t, r in h1.items() if r["failure"]}))
        finally:
            cfg.DATA_DIR = orig


def test_dedup_keys() -> None:
    print("dedup identities")
    for t, keys in cc.DEDUP_KEYS.items():
        check(f"{t} has a dedup key", bool(keys))
    # A dependency estimate must be versioned, or a re-estimate silently replaces the assumption
    # older combos were priced under.
    check("dependency identity is versioned",
          "calculation_version" in cc.DEDUP_KEYS["combo_dependencies"])
    check("candidates are keyed per SNAPSHOT, not per combo",
          "snapshot_ts" in cc.DEDUP_KEYS["combo_candidates"],
          "keying on combo_id alone would make re-observation look like duplication")
    check("legs are keyed per leg_index", "leg_index" in cc.DEDUP_KEYS["combo_legs"])


def test_lifecycle_truth() -> None:
    """ACTIVE + 0 rows is the state this pass exists to remove; SOURCE_REQUIRED + 0 is fine."""
    print("lifecycle honesty")
    check("combo_price_snapshots stays SOURCE_REQUIRED",
          schemas.status("combo_price_snapshots") == schemas.SOURCE_REQUIRED,
          "no bookmaker same-game-builder price exists to collect")
    check("an empty SOURCE_REQUIRED table is NOT an outage",
          schemas.is_expected_empty("combo_price_snapshots"))
    for t in ("live_odds_snapshots", "team_news", "team_match_stats",
              "combo_candidates", "combo_legs", "combo_dependencies", "combo_settlements"):
        check(f"{t} is ACTIVE, so an empty one alarms",
              schemas.status(t) == schemas.ACTIVE and not schemas.is_expected_empty(t),
              schemas.status(t))
    # The claim in the schema note must not contradict the status.
    for t in ("live_odds_snapshots", "team_news"):
        spec = schemas.TABLES[t]
        check(f"{t}'s note does not still claim it is empty",
              "Not empty" in spec["_why_empty"],
              spec["_why_empty"][:70])


def test_registry_consistency() -> None:
    """Section 12: the accounting must add up, and must not contradict itself."""
    print("registry accounting")
    p = cfg.OUTPUT_DIR / "system_registry.json"
    if not p.exists():
        check("system_registry.json exists", False)
        return
    r = json.loads(p.read_text(encoding="utf-8"))
    store = r.get("season_store", {})
    check("every declared table appears in the registry",
          set(cfg.TABLES) <= set(store) | set(r.get("tables_never_written", [])),
          str(sorted(set(cfg.TABLES) - set(store))))
    check("n_tables_declared matches config",
          r.get("n_tables_declared") == len(cfg.TABLES),
          f"{r.get('n_tables_declared')} vs {len(cfg.TABLES)}")
    check("populated + expected-empty + unexpected-empty accounts for every table",
          r.get("n_tables_populated", 0) + len(r.get("tables_expected_empty", []))
          + len(r.get("tables_unexpected_empty", [])) == len(store),
          f"{r.get('n_tables_populated')} + {len(r.get('tables_expected_empty', []))} + "
          f"{len(r.get('tables_unexpected_empty', []))} != {len(store)}")
    check("accounted = populated + expected empty",
          r.get("n_tables_accounted", 0)
          == r.get("n_tables_populated", 0) + len(r.get("tables_expected_empty", [])))
    # No table may be listed with rows > 0 AND as empty.
    empty_named = set(r.get("tables_expected_empty", [])) | set(
        r.get("tables_unexpected_empty", []))
    contradictory = [t for t in empty_named if store.get(t, {}).get("rows", 0) > 0]
    check("no table is called empty while holding rows", not contradictory, str(contradictory))


def test_deployment_policy() -> None:
    """Section 30: one truthful state, not two contradictory keys.

    Asserted against a FRESHLY GENERATED payload, not the committed artifact. The policy is a
    property of the code; the committed JSON is whatever CI last wrote, so testing it would fail
    for hours after a correct fix and pass again for reasons unrelated to the code. Row counts are
    the opposite — those must come from the store — which is why the registry test above reads
    the file and this one does not.
    """
    print("deployment policy consistency")
    from src.pipelines import registry as _reg
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "system_registry.json"
        try:
            r = _reg.refresh(path=p, quiet=True)
        except Exception as e:                                     # noqa: BLE001
            check("registry refresh runs", False, f"{type(e).__name__}: {e}")
            return
    note = (r.get("deployment_note") or "").lower()
    may = r.get("pro_may_notify")
    if may is None:
        check("registry states pro_may_notify", False)
        return
    # The exact contradiction found on 2026-09-02: pro_may_notify true beside a note saying
    # Pro does not notify.
    #
    # Only BLANKET denials count. The corrected note legitimately says "collect, live and research
    # pipelines never notify", which is a scoped statement and true — a naive search for
    # "never notif" flags it and would push the note back toward vagueness to satisfy the test.
    blanket = ("pro does not notify", "pro never notifies", "does not stake and does not notify")
    says_never = any(b in note for b in blanket)
    check("the note does not contradict pro_may_notify",
          not (may and says_never),
          f"pro_may_notify={may} but the note makes a blanket denial")
    if may:
        check("the note states the permission, not only the prohibitions",
              "may notify" in note,
              "a reader must be able to learn Pro notifies without opening config")
    check("pro_may_stake is false — Pro never stakes", r.get("pro_may_stake") is False)
    check("config agrees with the registry", may == cfg.PRO_MAY_NOTIFY)
    if may:
        check("the notify scope is stated, not implied", bool(r.get("notify_scope")),
              "a permission with no stated scope is an unbounded one")


def test_manifest() -> None:
    print("output manifest")
    m = mf.build()
    check("manifest has entries", m["n_entries"] > 0)
    for t in ("RAW", "CANONICAL", "DERIVED_RESEARCH", "HEALTH", "REPORT"):
        check(f"covers {t} artifacts", m["by_artifact_type"].get(t, 0) > 0)
    check("every canonical table is represented",
          all(any(t in e["path"] for e in m["entries"] if e["artifact_type"] == "CANONICAL")
              for t in cfg.TABLES),
          str([t for t in cfg.TABLES
               if not any(t in e["path"] for e in m["entries"]
                          if e["artifact_type"] == "CANONICAL")]))
    # A RAW artifact must name its canonical table, or state why it has none. Silence is what
    # makes "no destination recorded" indistinguishable from "never imported".
    silent = [e["path"] for e in m["entries"]
              if e["artifact_type"] == "RAW"
              and not e["canonical_destination"]
              and not e.get("no_canonical_destination_reason")]
    check("every RAW entry names a destination or says why it has none",
          not silent, str(silent))


def test_scheduler_active_window() -> None:
    """Section 22: a quiet night must not count as a missed capture."""
    print("active-window cadence")
    base = pd.Timestamp("2026-09-02T12:00:00Z")
    # Six observations 10 min apart, then an 8-hour overnight gap, then six more.
    ts = pd.Series([base + pd.Timedelta(minutes=10 * i) for i in range(6)]
                   + [base + pd.Timedelta(hours=8) + pd.Timedelta(minutes=10 * i)
                      for i in range(6)])
    active = pd.Series([True] * 6 + [True] * 6)
    all_time = sch.spacing(ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ"), 10)
    windowed = sch.spacing(ts.dt.strftime("%Y-%m-%dT%H:%M:%SZ"), 10, active=active)
    check("the all-time count includes the overnight gap",
          all_time["missed_windows"] > 40, str(all_time["missed_windows"]))
    check("the active-window count excludes it",
          windowed["active_missed_windows"] == 0,
          str(windowed["active_missed_windows"]))
    check("both figures are reported, not one replaced by the other",
          windowed["missed_windows"] == all_time["missed_windows"])


def test_odds_budget_math() -> None:
    print("odds api budget arithmetic")
    now = pd.Timestamp.now(tz="UTC")
    d = pd.DataFrame({
        "fixture_key": ["a", "a", "b"],
        "market": ["OU25", "OU25", "OU25"],
        # Two rows of ONE market response must bill once, not twice.
        "observed_at": [now.strftime("%Y-%m-%dT%H:%M:%SZ")] * 2
                       + [now.strftime("%Y-%m-%dT%H:%M:%SZ")],
        "league": ["L", "L", "L"],
    })
    b = sch._odds_api_budget(d)
    check("both sides of one market bill once", b["credits_used_today"] == 2,
          f"{b.get('credits_used_today')} (expected 2: one per fixture)")
    check("it is labelled an estimate", b.get("is_estimate") is True,
          "no credit meter exists; presenting this as measured would be false")
    check("the monthly allowance is stated", b.get("monthly_allowance") == 100_000)


def main() -> int:
    for fn in (test_combo_import, test_dedup_keys, test_lifecycle_truth,
               test_registry_consistency, test_deployment_policy, test_manifest,
               test_scheduler_active_window, test_odds_budget_math):
        fn()
    print()
    if FAILS:
        print(f"FAILED ({len(FAILS)}): {', '.join(FAILS)}")
        return 1
    print("all prompt 1.5 hardening tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

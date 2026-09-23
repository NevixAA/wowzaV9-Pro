"""How many completed observations does Wowza possess that its models never learn from?

    python -m src.architecture.gap --write

This is the question the whole audit exists to answer (section 45), and it is answered by
counting, not by reasoning about architecture. Architecture proposals are cheap; a stranded
fixture count is falsifiable.

THE TWO NUMBERS THAT CAN BOTH BE WRONG IN OPPOSITE DIRECTIONS.

    AVAILABLE is easy to overstate. Take four history tables, key each on date+home+away, union
    them, and the total is inflated by every club whose name differs between providers -- "FC
    Koln" and "1. FC Koln" become two clubs and their shared fixtures get counted twice. A naive
    union here reports 83,792 fixtures, and a good part of that is double counting.

    ACTUAL is easy to understate. v9's training funnel discards rows at six separate stages and
    logs the size of none of them, so it is tempting to attribute every missing fixture to the
    funnel when most were never loaded at all.

So both are measured properly: AVAILABLE is counted AFTER resolving club identity on fixture
evidence (see entity.py), and ACTUAL comes from a probe that runs v9's own loader and feature
builder inside v9's own interpreter, rather than from a re-implementation of them here.

STRANDED IS THEN SPLIT BY CAUSE, because "26,000 fixtures are missing" is not actionable and
"24,000 sit in a file no code reads, 2,000 are dropped by a filter, 457 lack rolling form" is.
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
from src.architecture import entity as EN

CALC_VERSION = "1.0.0"
PROBE = Path(__file__).resolve().parent / "probes" / "v9_training_probe.py"


def out_dir() -> Path:
    p = cfg.OUTPUT_DIR / "architecture"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _v9() -> Path:
    return Path(cfg.V9_LOCAL)


def run_probe(*, refresh: bool = False) -> dict:
    """Run v9's own loader in v9's own interpreter. Cached -- it is slow and hits the network."""
    cache = out_dir() / "v9_training_probe.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    v9 = _v9()
    tmp = v9 / "_arch_probe_tmp.py"
    tmp.write_text(PROBE.read_text(encoding="utf-8"), encoding="utf-8")
    py = v9 / ".venv" / "Scripts" / "python.exe"
    py = str(py) if py.exists() else sys.executable
    try:
        subprocess.run([py, "_arch_probe_tmp.py", "--out", str(cache)],
                       cwd=str(v9), check=True, timeout=3600)
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(cache.read_text(encoding="utf-8"))


def _load_sources() -> dict[str, pd.DataFrame]:
    """Every store that contains a COMPLETED fixture with a final score."""
    v9 = _v9()
    src: dict[str, pd.DataFrame] = {}

    def keep(d, name):
        need = {"date", "league", "home_team", "away_team", "home_goals", "away_goals"}
        if need.issubset(d.columns):
            d = d.dropna(subset=["home_goals", "away_goals"])
            if len(d):
                src[name] = d
    try:
        keep(pd.read_parquet(v9 / "output" / "fd_history.parquet"), "fd_history")
    except Exception:
        pass
    try:
        keep(pd.read_csv(v9 / "output" / "backtest_all_leagues.csv", low_memory=False),
             "backtest_all_leagues")
    except Exception:
        pass
    try:
        af = pd.read_parquet(v9 / "output" / "af_history.parquet")
        af = af.rename(columns={"FTHG": "home_goals", "FTAG": "away_goals"})
        keep(af, "af_history")
    except Exception:
        pass
    # Pro's own season store -- the live evidence layer.
    try:
        import glob
        fs = sorted(glob.glob(str(cfg.DATA_DIR / "season_*" / "fixtures" / "dt=*" / "*.parquet")))
        if fs:
            d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
            ren = {"home": "home_team", "away": "away_team", "match_date": "date",
                   "home_score": "home_goals", "away_score": "away_goals"}
            d = d.rename(columns={k: v for k, v in ren.items() if k in d.columns})
            keep(d, "pro_fixtures")
    except Exception:
        pass
    return src


def analyse(*, refresh_probe: bool = False) -> dict:
    probe = run_probe(refresh=refresh_probe)
    src = _load_sources()
    if "fd_history" not in src:
        raise RuntimeError("fd_history is the anchor and could not be read")

    anchor = src["fd_history"]
    mappings, audits = {}, []
    resolved = {"fd_history": EN.apply_mapping(anchor, {})}
    for name, d in src.items():
        if name == "fd_history":
            continue
        m, aud = EN.build_mapping(anchor, d)
        aud.insert(0, "source", name)
        mappings[name] = m
        audits.append(aud)
        resolved[name] = EN.apply_mapping(d, m)

    audit = pd.concat(audits, ignore_index=True) if audits else pd.DataFrame()

    naive_union, res_union = set(), set()
    per_source = {}
    for name, d in src.items():
        naive_union |= set(EN.fixture_key(EN._fx(d)))
    for name, d in resolved.items():
        k = set(EN.fixture_key(d))
        res_union |= k
        per_source[name] = {"rows": int(len(d)), "fixtures": int(len(k)),
                            "first": str(pd.to_datetime(d["date"]).min())[:10],
                            "last": str(pd.to_datetime(d["date"]).max())[:10]}

    anchor_keys = set(EN.fixture_key(resolved["fd_history"]))
    extra = {n: len(set(EN.fixture_key(d)) - anchor_keys)
             for n, d in resolved.items() if n != "fd_history"}

    actual = int(probe.get("fixtures_reaching_any_main_model", 0))
    loaded = int(probe.get("fixtures_loaded", 0))
    available = len(res_union)
    stranded = max(available - actual, 0)

    res = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "calc_version": CALC_VERSION,
        "AVAILABLE_COMPLETED_FIXTURES": available,
        "AVAILABLE_NAIVE_UNION_BEFORE_NAME_RESOLUTION": len(naive_union),
        "NAME_RESOLUTION_REMOVED_DOUBLE_COUNTED": len(naive_union) - available,
        "FIXTURES_REACHING_V9_LOADER": loaded,
        "ACTUAL_V9_TRAINING_FIXTURES": actual,
        "STRANDED_FIXTURES": stranded,
        "STRANDED_FIXTURE_PCT": round(100 * stranded / available, 2) if available else None,
        "stranded_by_cause": {
            "never_loaded_not_in_loader_sources": max(available - loaded, 0),
            "loaded_but_reached_no_main_model": int(probe.get("loaded_but_no_model", 0)),
        },
        "unique_fixtures_each_source_adds_over_fd_history": extra,
        "per_source": per_source,
        "duplicate_rows_inside_v9_training_frame": next(
            (s["duplicate_rows"] for s in probe["stages"]
             if s["stage"] == "1_load_all_matches"), None),
        "LATEST_AVAILABLE_FIXTURE": max(
            (v["last"] for v in per_source.values() if v["last"]), default=""),
        "LATEST_TRAINING_FIXTURE": next(
            (s["last"] for s in probe["stages"] if s["stage"] == "4_dropna_form"), ""),
        "entity_resolution": {
            "pairs_examined": int(len(audit)),
            "accepted": int((audit.status == "ACCEPTED").sum()) if len(audit) else 0,
            "ambiguous_quarantined": int((audit.status == "AMBIGUOUS").sum()) if len(audit) else 0,
            "weak_evidence": int((audit.status == "WEAK_EVIDENCE").sum()) if len(audit) else 0,
            "accepted_but_different_string": int(
                ((audit.status == "ACCEPTED") & (~audit.identical_string)).sum())
            if len(audit) else 0,
        },
        "v9_funnel": probe["stages"],
        "covid_filter_removed_rows": (
            probe["stages"][0]["rows"] - probe["stages"][1]["rows"]
            if len(probe["stages"]) > 1 else None),
    }
    lag = None
    try:
        lag = (pd.Timestamp(res["LATEST_AVAILABLE_FIXTURE"])
               - pd.Timestamp(res["LATEST_TRAINING_FIXTURE"])).days
    except Exception:
        pass
    res["TRAINING_DATA_LAG_DAYS"] = lag
    return res, audit, resolved, anchor_keys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--refresh-probe", action="store_true")
    a = ap.parse_args()
    res, audit, resolved, anchor_keys = analyse(refresh_probe=a.refresh_probe)

    print("=" * 92)
    print("STRANDED TRAINING DATA")
    print("=" * 92)
    for k in ("AVAILABLE_NAIVE_UNION_BEFORE_NAME_RESOLUTION",
              "NAME_RESOLUTION_REMOVED_DOUBLE_COUNTED",
              "AVAILABLE_COMPLETED_FIXTURES", "FIXTURES_REACHING_V9_LOADER",
              "ACTUAL_V9_TRAINING_FIXTURES", "STRANDED_FIXTURES", "STRANDED_FIXTURE_PCT",
              "LATEST_AVAILABLE_FIXTURE", "LATEST_TRAINING_FIXTURE", "TRAINING_DATA_LAG_DAYS",
              "duplicate_rows_inside_v9_training_frame", "covid_filter_removed_rows"):
        print(f"  {k:<52}{res[k]}")

    print("\n  stranded by cause:")
    for k, v in res["stranded_by_cause"].items():
        print(f"     {k:<48}{v:,}")

    print("\n  unique fixtures each source adds beyond fd_history (after name resolution):")
    for k, v in res["unique_fixtures_each_source_adds_over_fd_history"].items():
        print(f"     {k:<34}{v:,}")

    print("\n  entity resolution:")
    for k, v in res["entity_resolution"].items():
        print(f"     {k:<40}{v:,}")

    if len(audit):
        amb = audit[audit.status == "AMBIGUOUS"]
        print(f"\n  QUARANTINED (ambiguous, never guessed): {len(amb)}")
        if len(amb):
            print(amb.head(8)[["source", "league", "name_b", "name_a", "evidence",
                               "runner_up_evidence"]].to_string(index=False))
        ren = audit[(audit.status == "ACCEPTED") & (~audit.identical_string)]
        print(f"\n  ACCEPTED RENAMES (different string, same club by fixture evidence): {len(ren)}")
        if len(ren):
            print(ren.head(12)[["source", "league", "name_b", "name_a",
                                "evidence"]].to_string(index=False))

    if a.write:
        (out_dir() / "training_data_health.json").write_text(
            json.dumps(res, indent=2, default=str), encoding="utf-8")
        if len(audit):
            audit.to_csv(out_dir() / "entity_resolution_audit.csv", index=False)
        print(f"\n[gap] wrote training_data_health.json + entity_resolution_audit.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

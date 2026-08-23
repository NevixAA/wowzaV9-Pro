"""
Snapshot density and near-kickoff coverage — is the closing line actually being captured?
=========================================================================================
CLV is the gate that turns a PAPER signal into a BET, and CLV needs a price close to kickoff.
`/odds` is pre-match only (see root CLAUDE.md), so a closing price not captured before kickoff
is gone permanently — there is no backfill at any price. That makes coverage of the last hour
the single most important thing to monitor about collection, and nothing was watching it.

THE METHODOLOGICAL POINT, which is easy to get wrong and was got wrong once.

Coverage must be measured ONLY over fixtures whose kickoff has already PASSED. For a match
kicking off tomorrow, the T-10m bucket has not *arrived* yet, so counting it as "not covered"
measures the calendar rather than our collection. Including upcoming fixtures produced a
confident "99% of fixtures are never sampled inside T-1h" that was pure artefact — the real
figure for the main market is 71%. Every function here filters on `kickoff < now` first.

A SECOND CONFOUND worth stating: these files are consecutive-distinct deduped, so a series with
one row means EITHER the price never moved across every capture OR the fixture was only seen
once. Those need opposite fixes (nothing to do vs. widen the capture window) and this module
cannot tell them apart — it reports the count and says so, rather than inferring a cause.

WHAT THIS DOES NOT DO: it does not change capture cadence. Density is deliberately high and the
brief's non-goals forbid reducing it. This measures; it never throttles.

Baseline measured 2026-08-23 over kicked-off fixtures:

    series (fixture x market)     main O/U          standard side-markets
    snapshots: median / p10        41 / 5            1 / 1
    within T-6h                    87.1%             41.3%
    within T-3h                    81.0%             25.5%
    within T-1h                    71.4%             14.7%
    within T-30m                   63.7%             10.3%
    within T-10m                   35.4%              0.8%

The side-market row is the finding: a median of one snapshot per series and 0.8% reaching the
final ten minutes means we effectively never hold a true closing price for BTTS/over15/over35,
which is the most likely reason CLV coverage sits at 9% of settled tips. Thresholds below are
therefore set from the MEASURED main-market baseline to catch regression, while the side-market
figures are reported as INFO — a threshold set at an aspiration fires every single run and
teaches people to ignore the check.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import pro_config as cfg

# (label, hours before kickoff). T-10m is the one CLV really wants.
BUCKETS = (("T-6h", 6.0), ("T-3h", 3.0), ("T-1h", 1.0), ("T-30m", 0.5), ("T-10m", 1.0 / 6.0))

# path -> (label, key columns). Files without kickoff_utc cannot be bucketed at all; that is
# itself reported rather than silently skipped.
SOURCES = (
    ("output/book_odds_snapshots.csv", "main O/U (per book)", ("match", "market", "side")),
    ("output/standard_sidemarket_odds_history.csv", "standard side-markets", ("match", "market")),
    ("output/newformat_odds_dense.csv", "new-format dense", ("match", "market")),
)

# Regression floors from the measured main-market baseline, set with headroom so normal
# fixture-mix variation cannot trip them. Only the main market is gated; see module docstring.
MAIN_FLOORS = {"T-1h": 0.55, "T-30m": 0.45}
MIN_MEDIAN_SNAPSHOTS = 10          # main market measured 41


def _load(path: str) -> pd.DataFrame:
    p = cfg.V9_LOCAL / path
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def measure(path: str, keys: tuple[str, ...], now=None) -> dict:
    """Density + near-kickoff coverage for one snapshot file. Never raises."""
    now = now or pd.Timestamp.now(tz="UTC")
    out = {"path": path, "rows": 0, "has_kickoff": False, "series": 0,
           "fixtures": 0, "median_snapshots": None, "p10_snapshots": None,
           "coverage": {}, "note": ""}
    d = _load(path)
    if d.empty:
        out["note"] = "missing or empty"
        return out
    out["rows"] = int(len(d))
    if "kickoff_utc" not in d.columns:
        # Not a failure of collection — a schema gap. newformat_odds_dense.csv carries
        # match_date only, so T-minus buckets are not computable for it at all. Saying that is
        # better than reporting 0% and implying the capture is broken.
        out["note"] = "no kickoff_utc column; T-minus buckets not computable for this source"
        return out
    out["has_kickoff"] = True
    ts = pd.to_datetime(d["snapshot_ts"], errors="coerce", utc=True)
    ko = pd.to_datetime(d["kickoff_utc"], errors="coerce", utc=True)
    out["kickoff_parseable"] = round(float(ko.notna().mean()), 4)
    d = d.assign(_ts=ts, _ko=ko).dropna(subset=["_ts", "_ko"])
    # Kicked-off only (see docstring), and pre-match rows only.
    d = d[d["_ko"] < now]
    d = d.assign(_tminus=(d["_ko"] - d["_ts"]).dt.total_seconds() / 3600.0)
    d = d[d["_tminus"] >= 0]
    if d.empty:
        out["note"] = "no pre-match rows on already-kicked-off fixtures yet"
        return out

    keys = tuple(k for k in keys if k in d.columns)
    g = d.groupby(list(keys))
    sizes = g.size()
    out["series"] = int(g.ngroups)
    out["fixtures"] = int(d["match"].nunique()) if "match" in d.columns else 0
    out["median_snapshots"] = float(sizes.median())
    out["p10_snapshots"] = float(sizes.quantile(0.10))
    out["max_snapshots"] = int(sizes.max())
    for label, hi in BUCKETS:
        n = d[d["_tminus"] <= hi].groupby(list(keys)).ngroups
        out["coverage"][label] = {"series": int(n), "of": out["series"],
                                  "pct": round(n / out["series"], 4)}
    return out


def report(now=None, write: bool = True) -> dict:
    """Measure every source; optionally write output/snapshot_coverage.json."""
    now = now or pd.Timestamp.now(tz="UTC")
    res = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "sources": {}}
    for path, label, keys in SOURCES:
        m = measure(path, keys, now)
        m["label"] = label
        res["sources"][path] = m
    if write:
        p = cfg.OUTPUT_DIR / "snapshot_coverage.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        res["written_to"] = str(p)
    return res


def main() -> int:
    r = report()
    for path, m in r["sources"].items():
        print(f"\n== {m['label']}  ({path}) ==")
        if not m["has_kickoff"] or not m["series"]:
            print(f"   {m['note']}  (rows {m['rows']:,})")
            continue
        print(f"   {m['rows']:,} rows; {m['series']} series over {m['fixtures']} kicked-off "
              f"fixtures; kickoff_utc parseable {m.get('kickoff_parseable', 0):.1%}")
        print(f"   snapshots per series: median {m['median_snapshots']:.0f}  "
              f"p10 {m['p10_snapshots']:.0f}  max {m['max_snapshots']}")
        for label, _ in BUCKETS:
            c = m["coverage"][label]
            print(f"     within {label:6} {c['series']:>5}/{c['of']:<5} {c['pct']:6.1%}")
    print(f"\n[snapshot_coverage] -> {r.get('written_to')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Populate the canonical `data_quality` table — observation-level quality records.
===============================================================================
    python -m src.pipelines.data_quality [--dry-run]

WHY IT WAS EMPTY, AND WHY THAT MATTERED. `data_quality` has been in `cfg.TABLES` since the store
was created and has held **0 rows the entire time**. It had no writer at all. The weekly audit
has been reporting "10/11 tables populated; empty: ['data_quality']" every run — correctly, and
with nobody able to tell from a row count whether that meant "nothing writes to it" or "nothing
was wrong yet". Those need opposite responses, which is why the audit now names the distinction.

WHAT A RECORD IS. One row per (table, flag) finding per run, not one per flagged row. The
alternative — an observation-level row for every flagged observation — would make `data_quality`
larger than the tables it describes: 33,447 flagged movement observations alone. The grain here
is the finding, carrying the affected count and enough identity to go and look:

    check            the store's required key: the quality flag being reported (registry in
                     src/quality.py), or NO_FLAGS / NOT_CLASSIFIED / TABLE_UNREADABLE
    status           the store's required key: FAIL a definitely-wrong flag is present,
                     WARN an unverified flag is present or the table cannot be classified,
                     PASS no flag on any row
    observed_at      when the scan ran
    table            which canonical table
    flag             same value as `check`, kept because every other module in Pro and v11 calls
                     this concept a flag; `check` exists because season_store.REQUIRED demands it
    is_wrong         True = the value is definitely incorrect (excluded from CLEAN)
                     False = unverified, may be fine (excluded from STRICT_CLEAN only)
    n_rows           rows in the table at scan time
    n_flagged        rows carrying this flag
    pct_flagged      n_flagged / n_rows
    n_clean          rows qualifying for CLEAN
    n_strict_clean   rows qualifying for STRICT_CLEAN
    first_dt/last_dt date span of the flagged rows, so contamination can be bounded in time
    sample_keys      up to 5 fixture keys, so a finding is investigable rather than just a number
    why              the registry's explanation, denormalised so the row is self-describing

THE POINT IS THE TREND. A single scan says what is wrong now; the series says whether it is
getting worse. That is why this writes to the append-only store rather than overwriting a JSON —
a quality metric whose history is discarded cannot show a slow decline, which is the failure mode
every incident in this project has had.

Rows are never deleted and nothing is filtered out of the source tables. This module only
describes.
"""
from __future__ import annotations

import argparse

import pandas as pd

from config import pro_config as cfg
from src import quality as q
from src.data import season_store as store

# Tables worth scanning: those that carry a quality_flags column or a CLV value. Adding a table
# here is all that is needed for it to appear in the record.
SCAN_TABLES = ("market_snapshots", "model_snapshots", "signals", "settlements", "clv",
               "player_props", "live_signals", "movement_observations", "fixtures",
               "feature_snapshots")

_KEY_COLS = ("fixture_key", "fixture_id", "match", "snapshot_id")


def _sample_keys(d: pd.DataFrame, mask, limit: int = 5) -> str:
    for c in _KEY_COLS:
        if c in d.columns:
            vals = d.loc[mask, c].dropna().astype(str).unique()[:limit]
            if len(vals):
                return "|".join(vals)
    return ""


# WRITE timestamps before fixture dates. The first version tried match_date first and reported
# `last_dt = 2026-08-30` for contamination found today -- a FUTURE date, because match_date says
# when the fixture is PLAYED, not when the row was captured. Bounding contamination in time needs
# the capture instant; a fixture date cannot bound anything, since a board written once can list
# fixtures months out. Same distinction as _WRITE_COLS in weekly_audit.
_SPAN_COLS = ("observed_at", "captured_at", "snapshot_ts", "entry_ts", "ingested_at",
              "match_date")


def _span(d: pd.DataFrame, mask) -> tuple[str, str, str]:
    """(first, last, which_column). The column is returned so the span is interpretable."""
    for c in _SPAN_COLS:
        if c in d.columns:
            t = pd.to_datetime(d.loc[mask, c], errors="coerce", utc=True).dropna()
            if len(t):
                return (t.min().strftime("%Y-%m-%d"), t.max().strftime("%Y-%m-%d"), c)
    return ("", "", "")


def _derive_clv_flags(d: pd.DataFrame) -> pd.DataFrame:
    """CLV_IMPLAUSIBLE, derived at scan time rather than trusted from the row.

    `clv` rows predate the flag vocabulary, so nothing has ever written a flag onto them. The
    implausibility test is cheap and deterministic, so it is applied here instead of requiring a
    re-import of history — a |clv_pct| of 120% is not a bad price, it is a mis-joined or in-play
    one, and 174 such rows once carried a segment past its MIN_CLV_N gate.
    """
    if "clv_pct" not in d.columns:
        return d
    out = d.copy()
    if "quality_flags" not in out.columns:
        out["quality_flags"] = ""
    v = pd.to_numeric(out["clv_pct"], errors="coerce")
    out["quality_flags"] = q.add_flag(out["quality_flags"],
                                      v.notna() & (v.abs() > q.CLV_PLAUSIBLE_ABS),
                                      "CLV_IMPLAUSIBLE")
    return out


def _adopt_v11_vocabulary(d: pd.DataFrame) -> pd.DataFrame:
    """Translate v11's `clv_quality` into Pro's flag vocabulary.

    v11 computes its own flags in a single-valued `clv_quality` column because it needs the FIRST
    disqualifying reason to decide eligibility. Pro needs the same information in its
    multi-valued `quality_flags` so one taxonomy covers every table. Translated here rather than
    renamed at source: v11 owns its calculation and Pro must not reach into it (movement brief
    section 18).
    """
    if "clv_quality" not in d.columns:
        return d
    out = d.copy()
    if "quality_flags" not in out.columns:
        out["quality_flags"] = ""
    mapping = {"POST_KICKOFF_ENTRY": "POST_KICKOFF_PRICE",
               "POST_KICKOFF_CLOSE": "POST_KICKOFF_PRICE",
               "MISSING_KICKOFF": "MISSING_KICKOFF",
               "MISSING_CLOSE": "MISSING_OPPOSITE_SIDE",
               "MISSING_OPPOSITE_SIDE": "MISSING_OPPOSITE_SIDE",
               "INVALID_MARKET_MAPPING": "MARKET_MAPPING_INVALID",
               "INSUFFICIENT_BOOKS": "INSUFFICIENT_BOOKS"}
    src = out["clv_quality"].astype(str)
    for v11_flag, pro_flag in mapping.items():
        out["quality_flags"] = q.add_flag(out["quality_flags"], src == v11_flag, pro_flag)
    return out


def _status(*, flag: str, is_wrong: bool, n_flagged) -> str:
    """FAIL / WARN / PASS for one finding.

    season_store.REQUIRED["data_quality"] is ("check", "status"), so the table's grain was fixed
    before this writer existed: a named check with a verdict. Mapping the flag taxonomy onto it
    rather than inventing a parallel shape keeps one vocabulary — a definitely-wrong flag FAILs,
    an unverified one WARNs, and the CLEAN/STRICT_CLEAN distinction survives intact in the row.
    """
    if flag == "NO_FLAGS":
        return "PASS"
    if flag in ("NOT_CLASSIFIED", "TABLE_UNREADABLE"):
        return "FAIL" if flag == "TABLE_UNREADABLE" else "WARN"
    if n_flagged in (None, 0):
        return "PASS"
    return "FAIL" if is_wrong else "WARN"


def scan(season: str | None = None, *, quiet: bool = False) -> pd.DataFrame:
    """One row per (table, flag) finding, plus a NO_FLAGS row per clean table."""
    now = pd.Timestamp.now(tz="UTC")
    rows = []
    for table in SCAN_TABLES:
        try:
            d = store.read(table, season)
        except Exception as e:                                    # noqa: BLE001
            rows.append({"observed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "table": table,
                         "flag": "TABLE_UNREADABLE", "is_wrong": True, "n_rows": 0,
                         "n_flagged": 0, "pct_flagged": None, "n_clean": None,
                         "n_strict_clean": None, "first_dt": "", "last_dt": "",
                         "span_col": "", "sample_keys": "",
                         "why": f"{type(e).__name__}: {e}"})
            continue
        if d is None or d.empty:
            continue
        if table == "clv":
            d = _derive_clv_flags(d)
        elif table == "market_snapshots":
            # Derived at scan time so HISTORICAL rows are covered without a re-import. The
            # importer flags this going forward, but the 271 contaminated rows were stored before
            # the flag existed and re-importing them is neither cheap nor necessary.
            d = q.flag_btts_first_half(d)
        elif table == "movement_observations":
            d = _adopt_v11_vocabulary(d)

        s = q.summarise(d)
        base = {"observed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "table": table,
                "n_rows": s["rows"], "n_clean": s["levels"][q.CLEAN],
                "n_strict_clean": s["levels"][q.STRICT_CLEAN]}

        # A table with no flags column cannot be CLASSIFIED, and reporting "0 clean" would read
        # as "everything is bad". Recorded as its own finding so the gap is actionable.
        if not s.get("classified", True):
            rows.append({**base, "flag": "NOT_CLASSIFIED", "is_wrong": False, "n_flagged": None,
                         "pct_flagged": None, "first_dt": "", "last_dt": "", "span_col": "",
                         "sample_keys": "",
                         "why": "table has no quality_flags column, so no row can be placed at "
                                "CLEAN or STRICT_CLEAN. A WIRING gap, not a data problem: add "
                                "flagging to whatever writes this table"})
            continue

        if not s["flags"]:
            rows.append({**base, "flag": "NO_FLAGS", "is_wrong": False, "n_flagged": 0,
                         "pct_flagged": 0.0, "first_dt": "", "last_dt": "",
                         "span_col": "", "sample_keys": "",
                         "why": "no quality flag present on any row at scan time"})
            continue

        for flag, n in s["flags"].items():
            mask = d["quality_flags"].map(lambda x: flag in q.split_flags(x))
            lo, hi, span_col = _span(d, mask)
            meta = q.FLAGS.get(flag)
            rows.append({**base, "flag": flag,
                         "is_wrong": bool(meta.wrong) if meta else False,
                         "n_flagged": int(n),
                         "pct_flagged": round(n / max(1, s["rows"]), 6),
                         "first_dt": lo, "last_dt": hi, "span_col": span_col,
                         "sample_keys": _sample_keys(d, mask),
                         "why": meta.why if meta else
                                "flag not in the registry; treated as UNVERIFIED"})

    out = pd.DataFrame(rows)
    if not out.empty:
        # `check` and `status` are REQUIRED by season_store; without them the append raises
        # SchemaError. It did, on the first run — which is the schema guard doing its job.
        out["check"] = out["flag"]
        out["status"] = [
            _status(flag=r["flag"], is_wrong=bool(r["is_wrong"]), n_flagged=r["n_flagged"])
            for _, r in out.iterrows()]
    if not quiet:
        if out.empty:
            print("[data_quality] no populated tables to scan")
        else:
            mix = dict(out["status"].value_counts())
            print(f"[data_quality] {len(out)} finding(s) across "
                  f"{out['table'].nunique()} table(s)  {mix}")
            for t, g in out.groupby("table", sort=True):
                r0 = g.iloc[0]
                def _n(v):
                    return "      -" if v is None or pd.isna(v) else f"{int(v):>7,}"
                print(f"  {t:24} {int(r0['n_rows']):>7,} rows  "
                      f"CLEAN {_n(r0['n_clean'])}  STRICT {_n(r0['n_strict_clean'])}")
                for _, r in g[~g["flag"].isin(("NO_FLAGS",))].iterrows():
                    mark = "WRONG " if r["is_wrong"] else "unver."
                    nf = ("      -" if r["n_flagged"] is None or pd.isna(r["n_flagged"])
                          else f"{int(r['n_flagged']):>7,}")
                    pf = ("" if r["pct_flagged"] is None or pd.isna(r["pct_flagged"])
                          else f" ({r['pct_flagged']:.2%})")
                    print(f"      [{mark}] {r['flag']:<28} {nf}{pf}"
                          + (f"  {r['first_dt']}..{r['last_dt']}" if r["first_dt"] else ""))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Populate the canonical data_quality table")
    ap.add_argument("--dry-run", action="store_true", help="scan and report, write nothing")
    a = ap.parse_args()
    d = scan()
    if d.empty:
        return 0
    if a.dry_run:
        print("[data_quality] dry run — nothing written")
        return 0
    try:
        store.append("data_quality", d, source="pro:data_quality",
                     source_sha=store.pro_git_sha(), rid=f"{cfg.run_id()}-dq")
    except store.LocalWriteRefused as e:
        # A local run has still done something useful — the scan above printed every finding.
        # Reported as a normal outcome rather than a traceback, and exit 0, because refusing to
        # write locally is the DESIGNED behaviour, not a failure of this pipeline.
        print(f"[data_quality] scan complete; NOT written — {e}")
        return 0
    print(f"[data_quality] {len(d)} finding(s) appended to the canonical store")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
